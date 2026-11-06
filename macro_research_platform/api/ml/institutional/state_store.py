"""System 2 async writers / System 1 synchronous, bitemporal SQLite snapshots."""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
from collections.abc import Iterator
import json
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
from io import BytesIO
from pathlib import Path
import sqlite3
from typing import Callable
from uuid import uuid4
import torch
from torch import Tensor


@dataclass(frozen=True)
class TensorSlot:
    """Explicit tensor schema; None axes remain bounded by max_axis/byte budget."""
    shape:tuple[int|None,...]
    dtype:torch.dtype=torch.float32
    max_age:timedelta|None=None


class StatefulFeatureStore:
    """WAL-based local backend; no Redis service or network round-trip required.

    Receipt time is assigned by the trusted writer after CPU serialization. A
    delayed computation cannot retroactively become available at its source date.
    Atomic groups prevent mixing graph tensors from different research updates.
    SQLite transactions provide coherent reads without waiting on LLM execution.
    """
    def __init__(self,path:Path,slots:dict[str,TensorSlot],*,schema_id:str,
                 atomic_groups:tuple[tuple[str,...],...]=(),max_bytes:int=16*1024*1024,max_axis:int=4096,
                 clock:Callable[[],datetime]|None=None,max_pending_writes:int=2) -> None:
        if not slots or not schema_id or max_bytes<1024 or max_axis<1:raise ValueError('Bounded feature schema required')
        if any(not set(group)<=set(slots) for group in atomic_groups):raise ValueError('Unknown atomic slot')
        if max_pending_writes<1:raise ValueError('Positive writer concurrency required')
        self._writers=asyncio.Semaphore(max_pending_writes)
        self.path,self.slots,self.schema_id=path,dict(slots),schema_id
        self.groups,self.max_bytes,self.max_axis=atomic_groups,max_bytes,max_axis
        self.clock=clock or (lambda:datetime.now(timezone.utc));path.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS state_schema(id TEXT PRIMARY KEY,definition TEXT)')
            definition=json.dumps({'slots':{k:[v.shape,str(v.dtype),v.max_age.total_seconds() if v.max_age else None] for k,v in sorted(slots.items())},'groups':atomic_groups},sort_keys=True)
            c.execute('INSERT OR IGNORE INTO state_schema VALUES(?,?)',(schema_id,definition))
            if c.execute('SELECT definition FROM state_schema WHERE id=?',(schema_id,)).fetchone()[0]!=definition:raise ValueError('State schema ID reused with incompatible slots')
            c.execute('CREATE TABLE IF NOT EXISTS tensor_state(schema_id TEXT,key TEXT,version TEXT,effective_at TEXT,recorded_at TEXT,payload BLOB,PRIMARY KEY(schema_id,key,version))')
            c.execute('CREATE INDEX IF NOT EXISTS tensor_lookup ON tensor_state(schema_id,key,recorded_at,effective_at)')

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        c=sqlite3.connect(self.path,timeout=.2);c.execute('PRAGMA busy_timeout=200')
        try:
            with c:yield c
        finally:c.close()

    @staticmethod
    def _timestamp(value:datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:raise ValueError('Explicit timezone required')
        return value.astimezone(timezone.utc).isoformat(timespec='microseconds')

    def _check(self,key:str,tensor:Tensor) -> None:
        if key not in self.slots:raise ValueError('Unregistered research feature')
        slot=self.slots[key]
        if tensor.layout!=torch.strided or tensor.dtype!=slot.dtype or tensor.ndim!=len(slot.shape):raise ValueError('Research tensor dtype/rank mismatch')
        if any(size<1 or size>self.max_axis or (expected is not None and size!=expected) for size,expected in zip(tensor.shape,slot.shape)):raise ValueError('Research tensor shape exceeds registered schema')
        if tensor.is_floating_point() and not torch.isfinite(tensor).all():raise ValueError('Nonfinite research tensor')

    async def publish(self,tensors:dict[str,Tensor],*,effective_at:datetime) -> str:
        """Async append-only update; the caller must not mutate inputs while awaiting."""
        if not tensors:raise ValueError('Empty research update')
        for group in self.groups:
            if set(group)&set(tensors) and not set(group)<=set(tensors):raise ValueError('Partial atomic graph update')
        # Clone/serialize inside the worker thread; cap bytes before allocating clones.
        size=sum(t.numel()*t.element_size() for t in tensors.values())
        if size>self.max_bytes:raise MemoryError('Research update exceeds tensor byte budget')
        async with self._writers:
            return await asyncio.to_thread(self._publish,tensors,effective_at)

    def _publish(self,tensors:dict[str,Tensor],effective_at:datetime) -> str:
        effective=self._timestamp(effective_at);payloads={}
        for key,value in tensors.items():
            self._check(key,value);stream=BytesIO();torch.save(value.detach().to('cpu').contiguous().clone(),stream);payloads[key]=stream.getvalue()
        if sum(map(len,payloads.values()))>self.max_bytes:raise MemoryError('Serialized research update exceeds byte budget')
        recorded=self._timestamp(self.clock())
        if effective>recorded:raise ValueError('Future-effective research update rejected')
        version=uuid4().hex
        with self._connect() as c:
            c.executemany('INSERT INTO tensor_state VALUES(?,?,?,?,?,?)',[(self.schema_id,key,version,effective,recorded,value) for key,value in payloads.items()])
        return version

    def get_tensor_snapshot(self,timestamp:datetime) -> dict[str,Tensor]:
        """Synchronous PIT slice; select release AND actual receipt <= origin.

        Returned tensors are private CPU copies. Reads have a short lock timeout;
        the serving supervisor should retain its incumbent on store unavailability.
        """
        origin=self._timestamp(timestamp);result={};versions={}
        with self._connect() as c:
            c.execute('BEGIN')
            rows=c.execute('''SELECT key,version,recorded_at,size,rid FROM (SELECT key,version,recorded_at,length(payload) AS size,rowid AS rid,ROW_NUMBER() OVER(PARTITION BY key ORDER BY recorded_at DESC,rowid DESC) AS position FROM tensor_state
                WHERE schema_id=? AND effective_at<=? AND recorded_at<=?) WHERE position=1''',(self.schema_id,origin,origin)).fetchall()
            selected={}
            for row in rows:selected.setdefault(row[0],row)
            if sum(r[3] for r in selected.values())>self.max_bytes:raise MemoryError('Snapshot exceeds tensor byte budget')
            for key,version,recorded,_,rowid in selected.values():
                max_age=self.slots[key].max_age
                if max_age is not None and datetime.fromisoformat(origin)-datetime.fromisoformat(recorded)>max_age:continue
                payload=c.execute('SELECT payload FROM tensor_state WHERE rowid=?',(rowid,)).fetchone()[0]
                tensor=torch.load(BytesIO(payload),map_location='cpu',weights_only=True);self._check(key,tensor)
                result[key]=tensor;versions[key]=version
            for group in self.groups:
                present=set(group)&set(result)
                if present and (present!=set(group) or len({versions[k] for k in group})!=1):raise ValueError('Incoherent research graph snapshot')
        return result

"""Bitemporal append-only observations and mixed-frequency, origin-frozen views."""
from __future__ import annotations
from dataclasses import dataclass
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
import hashlib
import json
import math
import sqlite3
import pandas as pd


def utc(value: object) -> pd.Timestamp:
    """Reject ambiguous naive times rather than guessing an exchange timezone."""
    t = pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError('An explicit timezone is required')
    return t.tz_convert('UTC')


@dataclass(frozen=True)
class Observation:
    entity: str
    feature: str
    period_end: str
    released_at: str
    ingested_at: str
    value: float
    source_digest: str


@dataclass(frozen=True)
class FeatureSpec:
    entity: str
    feature: str
    aggregation: str = 'last'
    lookback: str = '90D'
    max_age: str = '120D'


class PITFeatureStore:
    """Operational PIT: both release time and actual ingestion time must precede origin.

    Importing old records today does not make them operationally known yesterday.
    Offline vintage reconstruction needs a separately audited source-vintage store.
    Quarterly observations carry only within each feature's explicit max_age.
    """
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS observations(
                id TEXT PRIMARY KEY, entity TEXT, feature TEXT, period_end TEXT,
                released_at TEXT, ingested_at TEXT, value REAL, source_digest TEXT)''')
            c.execute('CREATE INDEX IF NOT EXISTS obs_lookup ON observations(entity,feature,released_at,ingested_at)')

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path,timeout=30)
        c.execute('PRAGMA journal_mode=WAL')
        try:
            with c:
                yield c
        finally:
            c.close()

    def append(self, observation: Observation, *, now: object) -> str:
        period,release,ingestion,current = map(utc,(observation.period_end,observation.released_at,observation.ingested_at,now))
        if ingestion != current:
            raise ValueError('Ingestion timestamp must equal the trusted receipt clock')
        if not period <= release <= ingestion <= current or not math.isfinite(observation.value):
            raise ValueError('Invalid observation availability or value')
        if len(observation.source_digest)!=64:
            raise ValueError('A source snapshot SHA256 is required')
        row = (observation.entity,observation.feature,period.isoformat(),release.isoformat(),ingestion.isoformat(),float(observation.value),observation.source_digest)
        identity = hashlib.sha256(json.dumps(row).encode()).hexdigest()
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?)',(identity,*row))
        return identity

    def view(self, origin: object, specs: list[FeatureSpec]) -> tuple[dict[str,float],str]:
        as_of = utc(origin)
        values,provenance = {},[]
        with self.connect() as c:
            for spec in specs:
                rows = c.execute('''SELECT id,period_end,released_at,ingested_at,value FROM observations
                    WHERE entity=? AND feature=? AND period_end<=? AND released_at<=? AND ingested_at<=?
                    ORDER BY period_end,released_at,ingested_at,id''',
                    (spec.entity,spec.feature,*([as_of.isoformat()]*3))).fetchall()
                # Select latest known vintage separately for each observation period.
                vintages = {r[1]:r for r in rows}
                eligible = list(vintages.values())
                key = spec.entity+':'+spec.feature
                if not eligible or as_of-utc(eligible[-1][1]) > pd.Timedelta(spec.max_age):
                    values[key] = float('nan')
                    continue
                if spec.aggregation=='last':
                    chosen = eligible[-1:]
                    value = chosen[0][4]
                else:
                    chosen = [r for r in eligible if utc(r[1]) > as_of-pd.Timedelta(spec.lookback)]
                    x = [r[4] for r in chosen]
                    if spec.aggregation not in ('mean','sum'):
                        raise ValueError('Use an explicit supported aggregation')
                    value = (sum(x)/len(x) if spec.aggregation=='mean' else sum(x)) if x else float('nan')
                values[key] = value
                provenance.extend(r[0] for r in chosen)
        digest = hashlib.sha256(json.dumps({'origin':as_of.isoformat(),'records':sorted(provenance),'specs':[vars(s) for s in specs]},sort_keys=True).encode()).hexdigest()
        return values,digest


class PointInTimeFeatureStore(PITFeatureStore):
    """Existing bitemporal store with immutable KG-aligned snapshot artifacts."""
    def snapshot_graph(self,origin:object,node_specs:dict[str,FeatureSpec],destination:Path) -> tuple[dict[str,float],str]:
        """Align daily/monthly/quarterly series using each spec's age/aggregation.

        Provenance/model nodes have no scalar observation and cannot be supplied
        as economic variables. None represents unavailable observations on disk.
        """
        from api.ml.institutional.lineage import digest,write_once
        if any(not key.startswith('feature:') for key in node_specs):raise ValueError('Only observed feature nodes can be snapshotted')
        values,source=self.view(origin,list(node_specs.values()))
        mapped={node:values[spec.entity+':'+spec.feature] for node,spec in node_specs.items()}
        payload={'schema':'macro.pit_graph.v1','origin':utc(origin).isoformat(),'source_snapshot':source,
                 'node_ids':sorted(mapped),'values':{k:v if math.isfinite(v) else None for k,v in mapped.items()},
                 'specs':{node:vars(spec) for node,spec in node_specs.items()}}
        identity=digest(payload);path=destination/(identity+'.json')
        try:write_once(path,payload)
        except FileExistsError:
            if json.loads(path.read_text())!=payload:raise RuntimeError('Snapshot identity conflict')
        return mapped,identity

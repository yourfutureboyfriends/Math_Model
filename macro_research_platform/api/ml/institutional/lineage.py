"""Local append-only audit records. Use a WORM/object-lock sink in production."""
from __future__ import annotations
from contextlib import AbstractContextManager
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()


def write_once(path: Path, record: dict[str,Any]) -> None:
    """Fsync and atomic no-clobber publication; never overwrite an audit artifact."""
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp = tempfile.mkstemp(dir=path.parent,prefix='.pending-')
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(record,f,sort_keys=True,allow_nan=False)
            f.flush(); os.fsync(f.fileno())
        os.link(temp,path)  # Fails if an existing record would be replaced.
        directory = os.open(path.parent,os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temp): os.unlink(temp)


@dataclass(frozen=True)
class InferenceManifest:
    data_snapshot_sha256: str
    feature_logic_sha256: str
    preprocessing_sha256: str
    graph_snapshot_sha256: str
    model_weights_sha256: str
    target_schema_sha256: str
    calibration_sha256: str
    source_tree_sha256: str
    configuration_sha256: str
    code_commit: str

    def validate(self) -> None:
        for key,value in asdict(self).items():
            if key!='code_commit' and (len(value)!=64 or any(c not in '0123456789abcdef' for c in value)):
                raise ValueError(f'Invalid immutable artifact digest: {key}')
        if not self.code_commit:
            raise ValueError('Source revision is required')


class InferenceAudit(AbstractContextManager):
    """Failure to persist audit raises before the prediction can be returned.

    Caller must load the exact immutable artifacts referenced by the manifest,
    verify file digests at load, and never mutate a serving model in place.
    An unmatched *.started.json identifies interrupted inference after a crash.
    """
    def __init__(self, root: Path, manifest: InferenceManifest, input_digest: str, origin: str) -> None:
        from api.ml.institutional.data import utc
        manifest.validate()
        self.root,self.id = root,uuid4().hex
        self.record = {'schema':'macro.inference.v1','id':self.id,'origin':utc(origin).isoformat(),
                       'manifest':asdict(manifest),'input_sha256':input_digest}
        self.output_digest: str | None = None

    def __enter__(self) -> 'InferenceAudit':
        self.record['started_at'] = datetime.now(timezone.utc).isoformat()
        self.record['record_sha256'] = digest(self.record)
        write_once(self.root/(self.id+'.started.json'),self.record)
        return self

    def result(self, serializable_output: Any) -> None:
        self.output_digest = digest(serializable_output)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        record = {'schema':'macro.inference.v1','id':self.id,'started_record_sha256':self.record['record_sha256'],
                  'completed_at':datetime.now(timezone.utc).isoformat(),'output_sha256':self.output_digest,
                  'status':'failed' if exc_type or self.output_digest is None else 'completed',
                  'error_type':exc_type.__name__ if exc_type else None}
        record['record_sha256'] = digest(record)
        write_once(self.root/(self.id+'.completed.json'),record)
        from api.ml.institutional.provenance import prov_document
        write_once(self.root/(self.id+'.prov.json'),prov_document(InferenceManifest(**self.record['manifest']),identifier=self.id,started=self.record['started_at'],ended=record['completed_at'],output_digest=self.output_digest,status=record['status']))
        if exc_type is None and self.output_digest is None:
            raise RuntimeError('Inference returned without a recorded output')
        return False

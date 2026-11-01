"""Versioned research records; all access is scoped explicitly to fund AND owner."""
import json
import sqlite3
from datetime import datetime, timezone


class Conflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    from api.core.app_db import app_db_path
    c = sqlite3.connect(app_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript('''
    CREATE TABLE IF NOT EXISTS workflow_records (
      fund TEXT NOT NULL, owner TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
      version INTEGER NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
      PRIMARY KEY(fund,owner,id));
    CREATE INDEX IF NOT EXISTS workflow_scope ON workflow_records(fund,owner,kind);
    CREATE TABLE IF NOT EXISTS workflow_versions (
      fund TEXT NOT NULL, owner TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL,
      payload TEXT NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY(fund,owner,id,version));
    CREATE TABLE IF NOT EXISTS workflow_monitors (
      fund TEXT NOT NULL, owner TEXT NOT NULL, symbols TEXT NOT NULL, interval_minutes INTEGER NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 0, next_run TEXT, last_run TEXT, status TEXT,
      PRIMARY KEY(fund,owner));
    CREATE TABLE IF NOT EXISTS workflow_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,fund TEXT NOT NULL,owner TEXT NOT NULL,
      fingerprint TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
      UNIQUE(fund,owner,fingerprint));
    ''')
    return c


def unpack(r):
    return {**dict(r), 'payload': json.loads(r['payload'])}


def records(fund, owner):
    with connect() as c:
        return [unpack(r) for r in c.execute('SELECT * FROM workflow_records WHERE fund=? AND owner=? ORDER BY updated_at DESC LIMIT 2000',(fund,owner))]


def put(fund, owner, rid, kind, payload, expected_version=0, event=None):
    if kind not in ('observation','thesis','reconciliation'):
        raise ValueError('Unsupported record type')
    if 'id' in payload and str(payload['id'])!=rid:
        raise ValueError('Payload identifier must match the record identifier')
    payload={**payload,'id':rid}
    raw = json.dumps(payload, allow_nan=False)
    if len(raw.encode()) > 1_000_000 or not rid or len(rid)>128:
        raise ValueError('Record exceeds the 1 MB / 128-character identifier limit')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        prior = c.execute('SELECT * FROM workflow_records WHERE fund=? AND owner=? AND id=?',(fund,owner,rid)).fetchone()
        if (prior['version'] if prior else 0) != expected_version:
            raise Conflict('Record changed elsewhere. Reload before updating it.')
        if prior and prior['kind'] != kind:
            raise ValueError('Record type cannot be changed')
        if not prior and c.execute('SELECT count(*) FROM workflow_records WHERE fund=? AND owner=?',(fund,owner)).fetchone()[0]>=2000:
            raise ValueError('Research record limit reached (2,000); export a backup and review server retention capacity.')
        current_bytes=c.execute('SELECT COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM workflow_records WHERE fund=? AND owner=?',(fund,owner)).fetchone()[0]
        if current_bytes-(len(prior['payload'].encode()) if prior else 0)+len(raw.encode())>50_000_000:
            raise ValueError('Account/fund research storage limit is 50 MB for current records.')
        version=expected_version+1; stamp=now()
        c.execute('INSERT OR REPLACE INTO workflow_records VALUES(?,?,?,?,?,?,?,?)',(fund,owner,rid,kind,version,raw,prior['created_at'] if prior else stamp,stamp))
        c.execute('INSERT INTO workflow_versions VALUES(?,?,?,?,?,?)',(fund,owner,rid,version,raw,stamp))
        if event is not None:
            c.execute('INSERT INTO workflow_events(fund,owner,fingerprint,payload,created_at) VALUES(?,?,?,?,?)',(fund,owner,f'{rid}:{version}',json.dumps(event,allow_nan=False),stamp))
        return {'id':rid,'kind':kind,'version':version,'payload':payload,'updated_at':stamp,'server_received_at':stamp}


def history(fund,owner,rid):
    with connect() as c:
        return [unpack(r) for r in c.execute('SELECT * FROM workflow_versions WHERE fund=? AND owner=? AND id=? ORDER BY version DESC LIMIT 200',(fund,owner,rid))]


def monitor(fund,owner,config=None):
    with connect() as c:
        if config is not None:
            c.execute('INSERT INTO workflow_monitors(fund,owner,symbols,interval_minutes,enabled,next_run) VALUES(?,?,?,?,?,?) ON CONFLICT(fund,owner) DO UPDATE SET symbols=excluded.symbols,interval_minutes=excluded.interval_minutes,enabled=excluded.enabled,next_run=excluded.next_run',
                      (fund,owner,json.dumps(config['symbols']),config['interval_minutes'],int(config['enabled']),now()))
        row=c.execute('SELECT * FROM workflow_monitors WHERE fund=? AND owner=?',(fund,owner)).fetchone()
        return {**dict(row),'symbols':json.loads(row['symbols'])} if row else None


def events(fund,owner):
    with connect() as c:
        return [{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM workflow_events WHERE fund=? AND owner=? ORDER BY id DESC LIMIT 100',(fund,owner))]


def queue_monitor(fund,owner):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT enabled,symbols FROM workflow_monitors WHERE fund=? AND owner=?',(fund,owner)).fetchone()
        if not row or not row['enabled'] or not json.loads(row['symbols']):
            raise ValueError('Enable monitoring with at least one symbol before queuing a scan.')
        c.execute('UPDATE workflow_monitors SET next_run=?,status=? WHERE fund=? AND owner=?',(now(),'Queued for next scheduler tick',fund,owner))
    return {'queued':True,'note':'Runs on the next scheduler tick while the API is active.'}

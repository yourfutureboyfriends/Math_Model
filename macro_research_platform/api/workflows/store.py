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
    stamp=now()
    if kind=='observation':
        from api.workflows.evidence import envelope
        payload.pop('_evidence',None)
        payload['_evidence']=envelope(payload,stamp)
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
        history_bytes=c.execute('SELECT COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM workflow_versions WHERE fund=? AND owner=?',(fund,owner)).fetchone()[0]
        if history_bytes+len(raw.encode())>100_000_000:raise ValueError('Immutable research history limit is 100 MB per account/fund. Export and review retention capacity.')
        version=expected_version+1
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


def observations_at(fund,owner,cutoff,symbol=None):
    from api.workflows.evidence import instant
    cutoff=instant(cutoff)
    with connect() as c:
        rows=c.execute("SELECT v.* FROM workflow_versions v JOIN workflow_records r USING(fund,owner,id) WHERE v.fund=? AND v.owner=? AND r.kind='observation' AND v.recorded_at<=? ORDER BY v.recorded_at DESC,v.version DESC",(fund,owner,cutoff))
        selected={}
        for r in rows:
            if r['id'] not in selected:selected[r['id']]=unpack(r)
        return [r for r in selected.values() if not symbol or r['payload'].get('symbol','').upper()==symbol.upper()]


def event_review(fund,owner,event_id,status,expected_status):
    if status not in ('unreviewed','reviewed','dismissed'):raise ValueError('Invalid review status')
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workflow_event_reviews (fund TEXT,owner TEXT,event_id INTEGER,status TEXT,updated_at TEXT,PRIMARY KEY(fund,owner,event_id))')
        c.execute('CREATE TABLE IF NOT EXISTS workflow_event_review_history (id INTEGER PRIMARY KEY AUTOINCREMENT,fund TEXT,owner TEXT,event_id INTEGER,old_status TEXT,new_status TEXT,recorded_at TEXT)')
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM workflow_events WHERE id=? AND fund=? AND owner=?',(event_id,fund,owner)).fetchone():raise ValueError('Event not found in this account/fund')
        old=c.execute('SELECT status FROM workflow_event_reviews WHERE fund=? AND owner=? AND event_id=?',(fund,owner,event_id)).fetchone()
        if (old['status'] if old else 'unreviewed')!=expected_status:raise Conflict('Review status changed; reload the inbox')
        stamp=now();c.execute('INSERT OR REPLACE INTO workflow_event_reviews VALUES(?,?,?,?,?)',(fund,owner,event_id,status,stamp))
        c.execute('INSERT INTO workflow_event_review_history(fund,owner,event_id,old_status,new_status,recorded_at) VALUES(?,?,?,?,?,?)',(fund,owner,event_id,expected_status,status,stamp))
        return {'event_id':event_id,'status':status,'updated_at':stamp}


def inbox(fund,owner):
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workflow_event_reviews (fund TEXT,owner TEXT,event_id INTEGER,status TEXT,updated_at TEXT,PRIMARY KEY(fund,owner,event_id))')
        rows=c.execute("SELECT e.*,COALESCE(r.status,'unreviewed') AS review_status FROM workflow_events e LEFT JOIN workflow_event_reviews r ON e.id=r.event_id AND e.fund=r.fund AND e.owner=r.owner WHERE e.fund=? AND e.owner=? ORDER BY e.id DESC LIMIT 200",(fund,owner))
        return [{**dict(r),'payload':json.loads(r['payload'])} for r in rows]

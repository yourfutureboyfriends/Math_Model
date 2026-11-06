"""Append-only, tenant-scoped macro expectations and source actuals. No backdated receipt."""
import json
import uuid
from datetime import datetime,timezone
from api.workflows import store
from api.workflows.evidence import canonical,digest,instant,valid_source_url


def connect():
    c=store.connect()
    c.execute('''CREATE TABLE IF NOT EXISTS macro_release_entries (
        fund TEXT NOT NULL,owner TEXT NOT NULL,id TEXT NOT NULL,event_id TEXT NOT NULL,
        entry_type TEXT NOT NULL,payload TEXT NOT NULL,recorded_at TEXT NOT NULL,
        PRIMARY KEY(fund,owner,id))''')
    c.execute('CREATE INDEX IF NOT EXISTS macro_release_scope ON macro_release_entries(fund,owner,event_id,recorded_at)')
    return c


def add(fund,owner,body):
    body=dict(body);valid_source_url(body['source_url'])
    scheduled=instant(body['scheduled_at']);published=instant(body['published_at']) if body.get('published_at') else None
    body.update(scheduled_at=scheduled,published_at=published)
    key={k:body[k].strip() for k in ('country','indicator','reference_period','units','transformation','seasonal_adjustment')}
    key['indicator']=key['indicator'].casefold()
    event_id=digest(key);kind=body['entry_type']
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');stamp=store.now();now=datetime.fromisoformat(stamp)
        if published and datetime.fromisoformat(published)>now:raise ValueError('Publication cannot be in the future')
        if kind!='forecast' and not published:raise ValueError('Actuals/revisions require a source publication timestamp')
        rows=c.execute('SELECT * FROM macro_release_entries WHERE fund=? AND owner=? AND event_id=? ORDER BY recorded_at,rowid',(fund,owner,event_id)).fetchall()
        actuals=[json.loads(r['payload']) for r in rows if r['entry_type']!='forecast']
        if kind=='actual' and actuals:raise store.Conflict('A first recorded actual already exists. Append a revision with its reference ID.')
        if kind=='revision':
            if not actuals or body.get('supersedes')!=actuals[-1]['id']:raise store.Conflict('Revision must reference the latest recorded actual/revision')
            if datetime.fromisoformat(published)<=datetime.fromisoformat(actuals[-1]['published_at']):raise ValueError('Revision publication must follow the previous source publication')
        elif body.get('supersedes'):raise ValueError('Only revisions can supersede an actual')
        # Merely importing an old forecast never creates a pre-release track record.
        eligible=kind=='forecast' and not actuals and now<datetime.fromisoformat(scheduled)
        payload={**body,'id':str(uuid.uuid4()),'event_id':event_id,'server_received_at':stamp,
                 'predeclared_before_scheduled_release':eligible,'publisher_schedule_verified':False,
                 'availability_basis':'Server receipt; supplied publication/schedule and source contents are not independently verified'}
        if c.execute('SELECT COUNT(*) FROM macro_release_entries WHERE fund=? AND owner=?',(fund,owner)).fetchone()[0]>=10000:raise ValueError('Release ledger limit reached (10,000 entries per account/fund)')
        # Deduplicate the exact submitted evidence while retaining legitimate forecast updates.
        signature=digest(body)
        if any(json.loads(r['payload']).get('submission_sha256')==signature for r in rows):raise store.Conflict('This exact release evidence is already recorded')
        payload['submission_sha256']=signature
        raw=canonical(payload)
        if len(raw.encode())>16000:raise ValueError('Release evidence exceeds 16 KB')
        used=c.execute('SELECT COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM macro_release_entries WHERE fund=? AND owner=?',(fund,owner)).fetchone()[0]
        if used+len(raw.encode())>25_000_000:raise ValueError('Release evidence storage limit is 25 MB per account/fund')
        c.execute('INSERT INTO macro_release_entries VALUES(?,?,?,?,?,?,?)',(fund,owner,payload['id'],event_id,kind,raw,stamp))
        if kind!='forecast':
            event={'kind':'macro_release','symbol':(body.get('linked_symbols') or [''])[0],
                   'linked_symbols':body.get('linked_symbols',[]),'event_id':event_id,'entry_id':payload['id'],
                   'summary':f"{body['country']} {body['indicator']} {body['reference_period']}: {body['value']} {body['units']} ({kind})",
                   'source_url':body['source_url'],'relationship_basis':'Analyst-supplied linked securities; no causal return claim'}
            c.execute('INSERT INTO workflow_events(fund,owner,fingerprint,payload,created_at) VALUES(?,?,?,?,?)',
                      (fund,owner,'macro_release:'+payload['id'],canonical(event),stamp))
    return payload


def ledger(fund,owner,cutoff=None):
    cutoff=instant(cutoff) if cutoff else store.now()
    with connect() as c:
        rows=c.execute('SELECT payload FROM macro_release_entries WHERE fund=? AND owner=? AND recorded_at<=? ORDER BY recorded_at DESC,rowid DESC LIMIT 2001',(fund,owner,cutoff)).fetchall()
    entries=[json.loads(r['payload']) for r in rows[:2000]];events={}
    for entry in reversed(entries):events.setdefault(entry['event_id'],[]).append(entry)
    result=[]
    for eid,items in events.items():
        actual=next((r for r in items if r['entry_type']=='actual'),None)
        latest=next((r for r in reversed(items) if r['entry_type']!='forecast'),None)
        forecasts={}
        for row in items:
            if row['entry_type']!='forecast':continue
            if not row['predeclared_before_scheduled_release']:continue
            # Late imported actuals still exclude forecasts received after their stated publication.
            if actual and datetime.fromisoformat(row['server_received_at'])>=datetime.fromisoformat(actual['published_at']):continue
            forecasts[(row['source'],row['forecast_basis'])]=row
        comparisons=[{'forecast_id':f['id'],'source':f['source'],'forecast_basis':f['forecast_basis'],
                      'forecast':f['value'],'first_recorded_actual':actual['value'],
                      'surprise':actual['value']-f['value'],'latest_revision':latest['value'] if latest else None}
                     for f in forecasts.values()] if actual else []
        result.append({'event_id':eid,'identity':{k:items[-1][k] for k in ('country','indicator','reference_period','units','transformation','seasonal_adjustment')},
                       'entries':items,'comparisons':comparisons,'latest_actual_id':latest['id'] if latest else None})
    return {'events':result,'cutoff':cutoff,'truncated':len(rows)>2000,
            'note':'Append-only account/fund evidence. Surprise compares the last eligible forecast per named source/basis with the first recorded actual, not a verified first official print. Raw surprise units are preserved; no cross-indicator z-score or market-impact claim is inferred. Retrospective forecasts are retained but excluded from pre-release scoring.'}

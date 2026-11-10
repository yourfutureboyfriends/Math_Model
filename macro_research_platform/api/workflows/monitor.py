"""Opt-in research scans. Persistent leases and deduplicated observations; no messages or trades."""
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from api.workflows import store

logger=logging.getLogger(__name__)


def run_due():
    from api.funds import CURRENT, get, can_open
    from api.core.accounts import get_user
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        due=c.execute('SELECT * FROM workflow_monitors WHERE enabled=1 AND (next_run IS NULL OR next_run<=?) ORDER BY next_run LIMIT 2',(store.now(),)).fetchall()
        for r in due:
            next_run=(datetime.now(timezone.utc)+timedelta(minutes=r['interval_minutes'])).isoformat()
            c.execute('UPDATE workflow_monitors SET next_run=?,status=? WHERE fund=? AND owner=?',(next_run,'Scanning',r['fund'],r['owner']))
    for row in due:
        user=get_user(row['owner']);fund=get(row['fund'])
        if not user or user.get('disabled') or user.get('must_change_password') or not fund or not can_open(user,fund):
            with store.connect() as c:c.execute('UPDATE workflow_monitors SET enabled=0,status=? WHERE fund=? AND owner=?',('Disabled: account or fund access changed',row['fund'],row['owner']))
            continue
        token=CURRENT.set(row['fund'])
        try:
            from api.positions import apply_to_user
            if apply_to_user(user).get('role') not in {'pm','quant','analyst','risk','trader','admin'}:
                with store.connect() as c:c.execute('UPDATE workflow_monitors SET enabled=0,status=? WHERE fund=? AND owner=?',('Disabled: position no longer permits research writes',row['fund'],row['owner']))
                continue
            scan(row['fund'],row['owner'],json.loads(row['symbols']))
        except Exception as e:
            logger.warning('Research monitor failed (%s)',type(e).__name__)
            with store.connect() as c:c.execute('UPDATE workflow_monitors SET status=? WHERE fund=? AND owner=?',(f'Failed: {type(e).__name__}',row['fund'],row['owner']))
        finally:CURRENT.reset(token)


def scan(fund,owner,symbols):
    from api.marketdata import security,research
    failures=[];new_events=0
    for symbol in symbols[:10]:
        for kind,fn in [('earnings',security.earnings),('filings',research.filings)]:
            try:
                payload=fn(symbol)
                if payload.get('stale'):
                    failures.append(f'{symbol} {kind}: stale response; baseline retained')
                    continue
                # Exclude volatile metadata/price reaction; only publish meaningful changes.
                evidence=payload.get('estimates',{}) if kind=='earnings' else sorted(r.get('url','') for r in payload.get('filings',[]))
                fingerprint=hashlib.sha256(json.dumps([symbol,kind,evidence],sort_keys=True,default=str).encode()).hexdigest()
                rid=f'monitor:{symbol}:{kind}'
                with store.connect() as c:
                    old=c.execute('SELECT version,payload FROM workflow_records WHERE fund=? AND owner=? AND id=?',(fund,owner,rid)).fetchone()
                if old:
                    prior=json.loads(old['payload'])
                    old_payload=prior.get('payload') or {}
                    previous=old_payload.get('estimates',{}) if kind=='earnings' else sorted(r.get('url','') for r in old_payload.get('filings',[]))
                    if json.dumps(previous,sort_keys=True,default=str)==json.dumps(evidence,sort_keys=True,default=str):continue
                observation={'id':rid,'symbol':symbol,'kind':kind,'observedAt':store.now(),'payload':payload,'collection':'scheduled','fingerprint':fingerprint}
                event={'symbol':symbol,'kind':kind,'baseline':old is None,'summary':'Baseline created' if old is None else 'New estimate snapshot' if kind=='earnings' else 'Filing sample changed','fingerprint':fingerprint}
                event.update(record_id=rid,prior_version=old['version'] if old else None,source=payload.get('source'))
                if kind=='filings':
                    earlier=set(previous) if old else set()
                    event['new_filing_urls']=[url for url in evidence if url and url not in earlier]
                    event['source_url']=next(iter(event['new_filing_urls']),None)
                else:
                    from api.workflows.intelligence import estimate_revisions
                    revisions=estimate_revisions(([{'payload':prior,'version':old['version'],'recorded_at':prior.get('observedAt','')}] if old else [])+[{'payload':observation,'version':(old['version'] if old else 0)+1,'recorded_at':observation['observedAt']}])
                    event['matched_estimate_changes']=revisions['changes'];event['unmatched_period_rows']=revisions['unmatched_period_rows']
                store.put(fund,owner,rid,'observation',observation,old['version'] if old else 0,event=event)
                new_events+=1
            except Exception as e:failures.append(f'{symbol} {kind}: {type(e).__name__}')
    with store.connect() as c:
        c.execute('UPDATE workflow_monitors SET last_run=?,status=? WHERE fund=? AND owner=?',(store.now(),f'{new_events} new snapshots; '+('; '.join(failures) if failures else 'feeds checked'),fund,owner))
    return {'new_snapshots':new_events,'failures':failures}

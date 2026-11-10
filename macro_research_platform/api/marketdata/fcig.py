"""Official Federal Reserve FCI-G observations and published contribution reconciliation."""
import csv
import io
import math
from datetime import date,datetime,timezone
from api.marketdata.core import _cached,Upstream

URL='https://www.federalreserve.gov/econres/notes/feds-notes/fci_g_public_monthly_3yr.csv'
COMPONENTS=('FFR','10Yr Treasury','Mortgage Rate','BBB','Stock Market','House Prices','Dollar')
INDEX='FCI-G Index (baseline)'


def parse(text):
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not {'date',INDEX,*COMPONENTS}<=set(reader.fieldnames or []):raise ValueError('Official FCI-G schema changed; review the adapter')
    rows=[];seen=set()
    for row in reader:
        day=date.fromisoformat(row['date'])
        if day in seen:raise ValueError('Duplicate official FCI-G date')
        seen.add(day)
        values={k:float(row[k]) for k in (INDEX,*COMPONENTS)}
        if not all(math.isfinite(v) for v in values.values()):raise ValueError('Nonfinite FCI-G observation')
        residual=values[INDEX]-sum(values[k] for k in COMPONENTS)
        if abs(residual)>1e-7:raise ValueError('Official contributions do not reconcile; no replacement weights were invented')
        rows.append({'date':day.isoformat(),'value':values[INDEX],'contributions':{k:values[k] for k in COMPONENTS},'residual':residual})
    rows.sort(key=lambda r:r['date'])
    if not rows:raise ValueError('Official FCI-G history is empty')
    return rows


def conditions():
    def fetch():
        import requests
        import hashlib
        from api.workflows.telemetry import stage
        with stage('other'):
            with requests.get(URL,timeout=25,stream=True) as response:
                response.raise_for_status();chunks=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>2_000_000:raise ValueError('FCI-G response exceeded 2 MB')
                    chunks.append(chunk)
        raw=b''.join(chunks)
        rows=parse(raw.decode('utf-8-sig'));latest=rows[-1];previous=rows[-2] if len(rows)>1 else None
        delta={k:latest['contributions'][k]-previous['contributions'][k] for k in COMPONENTS} if previous else {}
        return {'latest':latest,'previous':previous,'change_contributions':delta,
                'change':latest['value']-previous['value'] if previous else None,'history':rows[-120:],
                'source':'Federal Reserve Board FCI-G, baseline three-year lookback','source_url':URL,
                'source_sha256':hashlib.sha256(raw).hexdigest(),
                'retrieved_at':datetime.now(timezone.utc).isoformat(),'publication_timestamp':None,
                'units':'Percentage-point contribution to the index’s modeled one-year-ahead GDP-growth headwind; positive = tightening/headwind',
                'vintage_basis':'Current published revised history; not an archived real-time vintage',
                'note':'Published component contributions and their changes reconcile to the official total. This is FCI-G, not Goldman Sachs FCI, Bloomberg FCI or an independent GDP forecast. Statistical contributions are model-dependent, not identified causal effects.'}
    try:
        result=dict(_cached('macro:fcig:v1',21600,fetch))
        result['observation_age_days']=(date.today()-date.fromisoformat(result['latest']['date'])).days
        result['stale_observation']=result['observation_age_days']>100
        return result
    except Exception as e:raise Upstream(f'Official FCI-G unavailable: {type(e).__name__}') from e

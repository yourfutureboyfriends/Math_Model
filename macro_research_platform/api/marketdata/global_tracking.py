"""Optional licensed tracking feeds, bounded acquisition, and observed coverage diagnostics.

Credentials stay server-side. Each paid feed requires an enable flag, credentials and a
positive daily request budget. Missing entitlement is never represented as zero traffic.
"""
from __future__ import annotations
import json
import math
import os
import re
import socket
import sqlite3
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from api.marketdata.tracker_quality import position, recent

DATA = Path(__file__).resolve().parents[2] / 'data' / 'processed'
REGIONS = [
    ('shanghai','Shanghai / Yangshan',31.0,121.8), ('ningbo','Ningbo / Zhoushan',29.9,122.0),
    ('qingdao','Qingdao',36.0,120.3), ('tianjin','Tianjin',38.9,117.8),
    ('shenzhen','Shenzhen / Pearl River',22.5,113.9), ('hong-kong','Hong Kong',22.3,114.0),
    ('zhengzhou','Zhengzhou air cargo',34.5,113.8), ('beijing','Beijing',40.1,116.6),
    ('singapore','Singapore / Malacca',1.3,103.8), ('hormuz','Hormuz / Gulf',26.5,56.3),
    ('dubai','Dubai',25.3,55.4), ('mumbai','Mumbai',19.1,72.9), ('delhi','Delhi',28.6,77.1),
    ('jakarta','Jakarta',-6.1,106.8), ('mombasa','Mombasa',-4.1,39.7),
    ('lagos','Lagos',6.4,3.4), ('cape-town','Cape Town',-33.9,18.4),
    ('johannesburg','Johannesburg',-26.1,28.2), ('santos','Santos / Sao Paulo',-24.0,-46.3),
    ('panama','Panama',9.0,-79.6), ('lima','Lima',-12.0,-77.1),
]
AIR_ONLY_REGIONS={'zhengzhou','beijing','delhi','johannesburg'}
SPECS = {
    'shipxy': ('ship', 'Shipxy', ['SHIPXY_API_KEY']),
    'kpler': ('ship', 'Kpler Maritime 2.0', ['KPLER_AIS_TOKEN']),
    'vesselfinder': ('ship', 'VesselFinder subscription area', ['VESSELFINDER_API_KEY']),
    'flightaware': ('flight', 'FlightAware Firehose', ['FLIGHTAWARE_FIREHOSE_USERNAME','FLIGHTAWARE_FIREHOSE_API_KEY']),
}
_lock = threading.RLock()
_cached_regions: dict[tuple, dict] = {}
_last_attempt: dict[tuple, float] = {}
_fetch_locks: dict[tuple, threading.Lock] = {}
_states: dict[str, dict] = {}
_flight_records: dict[str, dict] = {}
_worker: threading.Thread | None = None


def _db():
    DATA.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(DATA/'tracking_acquisition.sqlite3',timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS usage (day TEXT, provider TEXT, calls INTEGER, PRIMARY KEY(day,provider))')
    db.execute('CREATE TABLE IF NOT EXISTS evidence (at REAL, provider TEXT, region TEXT, accepted INTEGER, rejected INTEGER, p50 REAL, p95 REAL, status TEXT)')
    return db


def _int_env(name, default, low=0, high=10000):
    try: return max(low,min(high,int(os.getenv(name,str(default)))))
    except ValueError: return default


def enabled(provider):
    return os.getenv(f'TRACKING_{provider.upper()}_ENABLED','').lower() in ('1','true','yes')


def provider_status(provider):
    kind,label,keys=SPECS[provider]
    configured=all(bool(os.getenv(k)) for k in keys)
    budget=_int_env(f'TRACKING_{provider.upper()}_DAILY_REQUESTS',0)
    active=enabled(provider) and configured and budget>0
    status='ready' if active else 'disabled' if not enabled(provider) else 'credentials missing' if not configured else 'request budget not set'
    return {'id':provider,'kind':kind,'name':label,'configured':configured,'enabled':enabled(provider),
            'active':active,'daily_request_limit':budget,**_states.get(provider,{}),'status':_states.get(provider,{}).get('status',status) if active else status}


def reserve_request(provider):
    """Persistent atomic call cap; never infer currency cost from a request count."""
    if not provider_status(provider)['active']: return False
    day=datetime.now(timezone.utc).date().isoformat()
    with _lock, _db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO usage VALUES (?,?,0)',(day,provider))
        used=db.execute('SELECT calls FROM usage WHERE day=? AND provider=?',(day,provider)).fetchone()[0]
        if used>=_int_env(f'TRACKING_{provider.upper()}_DAILY_REQUESTS',0):
            _states[provider]={'status':'daily request cap reached','cap_day':day}
            return False
        db.execute('UPDATE usage SET calls=calls+1 WHERE day=? AND provider=?',(day,provider))
    return True


def epoch(value):
    if isinstance(value,(float,int)) and not isinstance(value,bool): return float(value) if math.isfinite(value) else None
    if not isinstance(value,str): return None
    try:
        text=value.removesuffix(' UTC').strip().replace('Z','+00:00')
        if re.fullmatch(r'\d+(\.\d+)?',text): return float(text)
        d=datetime.fromisoformat(text)
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError,OverflowError): return None


def num(x):
    try:
        v=float(x)
        return v if not isinstance(x,bool) and math.isfinite(v) else None
    except (ValueError,TypeError): return None


def clean_ship(raw,provider,now):
    m=num(raw.get('mmsi'));lat=num(raw.get('lat'));lon=num(raw.get('lon'));at=epoch(raw.get('timestamp'))
    if m is None or not m.is_integer() or not 100000000<=m<=999999999 or not position(lat,lon) or not recent(at,now,3600): return None
    def bounded(x,maximum):
        n=num(x);return n if n is not None and 0<=n<maximum else None
    return {**raw,'mmsi':int(m),'lat':lat,'lon':lon,'seen':at,'received_at':now,'source':provider,
            'time_basis':'provider_report','speed':bounded(raw.get('speed'),60.01),
            'heading':bounded(raw.get('heading'),360),'course':bounded(raw.get('course'),360),
            'name':str(raw.get('name') or ''),'type':str(raw.get('type') or 'Unknown')}


def _ship_type(code):
    from api.marketdata.tracking import _ship_type as classify
    if isinstance(code,(int,float)): return classify(code)
    s=str(code or '').upper()
    if 'TANKER' in s or 'GAS_CARRIER' in s: return 'Tanker'
    if any(k in s for k in ('CARGO','CONTAINER','BULK','CARRIER','REEFER')): return 'Cargo'
    if 'FISH' in s:return 'Fishing'
    if 'PASSENGER' in s:return 'Passenger'
    return 'Other' if s else 'Unknown'


def parse_shipxy(payload,now):
    if not isinstance(payload,dict) or payload.get('status')!=0: raise ValueError('provider rejected request')
    body=payload.get('data') or {};rows=[];rejected=0
    for v in body.get('ship_list') or []:
        record=clean_ship({'mmsi':v.get('mmsi'),'imo':v.get('imo'),'lat':v.get('lat'),'lon':v.get('lng'),
            'timestamp':v.get('last_time_utc'),'name':v.get('ship_name'),'type':_ship_type(v.get('ship_type')),
            'speed':v.get('sog'),'heading':v.get('hdg'),'course':v.get('cog'),'status':v.get('navistat'),
            'destination':v.get('dest'),'collection_type':'provider source code '+str(v.get('data_source'))},'shipxy',now)
        if record:rows.append(record)
        else:rejected+=1
    return rows,rejected,bool(body.get('continue')),body.get('scode')


def parse_kpler(payload,now):
    if not isinstance(payload,dict) or payload.get('errors'):raise ValueError('provider rejected query')
    body=(payload.get('data') or {}).get('vessels')
    if not isinstance(body,dict):raise ValueError('provider schema unavailable')
    rows=[];rejected=0
    for v in body.get('nodes') or []:
        s=v.get('staticData') or {};p=v.get('lastPositionUpdate') or {}
        record=clean_ship({'mmsi':s.get('mmsi'),'imo':s.get('imo'),'name':s.get('name'),'type':_ship_type(s.get('shipType')),
            'lat':p.get('latitude'),'lon':p.get('longitude'),'timestamp':p.get('timestamp'),'speed':p.get('speed'),
            'heading':p.get('heading'),'course':p.get('course'),'status':None,'collection_type':p.get('collectionType') or 'unknown'},'kpler',now)
        if record:rows.append(record)
        else:rejected+=1
    page=body.get('pageInfo') or {}
    return rows,rejected,bool(page.get('hasNextPage')),page.get('endCursor')


def parse_vesselfinder(payload,now):
    if not isinstance(payload,list):raise ValueError('provider rejected request')
    rows=[];rejected=0
    for v in payload:
        p=v.get('AIS') or {}
        record=clean_ship({'mmsi':p.get('MMSI'),'imo':p.get('IMO'),'name':p.get('NAME'),'type':_ship_type(p.get('TYPE')),
            'lat':p.get('LATITUDE'),'lon':p.get('LONGITUDE'),'timestamp':p.get('TIMESTAMP'),'speed':p.get('SPEED'),
            'heading':p.get('HEADING'),'course':p.get('COURSE'),'status':p.get('NAVSTAT'),
            'collection_type':{'TER':'terrestrial','SAT':'satellite'}.get(p.get('SRC'),'unknown')},'vesselfinder',now)
        if record:rows.append(record)
        else:rejected+=1
    return rows,rejected,False,None


def _request(provider,method,url,**kwargs):
    import requests
    if not reserve_request(provider):raise ValueError('request cap or configuration prevents acquisition')
    # No redirects: query credentials must not reach an alternate host or appear in errors.
    r=requests.request(method,url,timeout=20,allow_redirects=False,**kwargs)
    if r.status_code!=200:raise ValueError(f'provider HTTP {r.status_code}')
    if len(r.content)>16*1024*1024:raise ValueError('provider response exceeds size limit')
    return r.json()


def _fetch_ships(provider,region,deadline=None):
    _,_,lat,lon=region;half=.2
    polygon=[[lon-half,lat-half],[lon+half,lat-half],[lon+half,lat+half],[lon-half,lat+half],[lon-half,lat-half]]
    rows=[];rejected=0;cursor=None;partial=False
    pages=_int_env('TRACKING_MAX_PAGES',1,1,3)
    for _ in range(pages):
        if deadline is not None and time.monotonic()>=deadline:
            partial=True
            break
        if provider=='shipxy':
            params={'key':os.environ['SHIPXY_API_KEY'],'region':'-'.join(f'{x},{y}' for x,y in polygon),'output':1}
            if cursor is not None:params['scode']=cursor
            payload=_request(provider,'GET','https://api.shipxy.com/apicall/v3/GetAreaShip',params=params)
            batch,bad,partial,cursor=parse_shipxy(payload,time.time())
        elif provider=='kpler':
            query='query Region($aoi: AreaOfInterest, $after: String) { vessels(first: 500, areaOfInterest: $aoi, after: $after) { pageInfo { hasNextPage endCursor } nodes { staticData { mmsi imo name shipType } lastPositionUpdate { timestamp latitude longitude speed course heading collectionType } } } }'
            payload=_request(provider,'POST','https://api.sml.kpler.com/graphql',headers={'Authorization':'Bearer '+os.environ['KPLER_AIS_TOKEN']},
                json={'query':query,'variables':{'aoi':{'polygon':{'type':'Polygon','coordinates':[polygon]}},'after':cursor}})
            batch,bad,partial,cursor=parse_kpler(payload,time.time())
        else:
            payload=_request(provider,'GET','https://api.vesselfinder.com/livedata',params={'userkey':os.environ['VESSELFINDER_API_KEY'],'format':'json','interval':60})
            batch,bad,partial,cursor=parse_vesselfinder(payload,time.time())
        rows+=batch;rejected+=bad
        if not partial or cursor is None:break
    return rows,rejected,partial


def _record_evidence(provider,region,rows,rejected,status):
    now=time.time();ages=sorted(now-r['seen'] for r in rows)
    percentile=lambda p:ages[min(len(ages)-1,int((len(ages)-1)*p))] if ages else None
    with _db() as db:
        db.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)',(now,provider,region,len(rows),rejected,percentile(.5),percentile(.95),status))
        db.execute('DELETE FROM evidence WHERE at < ?',(now-14*86400,))


def ship_region(region_id):
    region=next((r for r in REGIONS if r[0]==region_id),None)
    if not region or region_id in AIR_ONLY_REGIONS:raise ValueError('unknown maritime tracking region')
    out=[];reports=[]
    deadline=time.monotonic()+60
    interval=_int_env('TRACKING_POLL_SECONDS',900,60,86400)
    for provider,(kind,_,_) in SPECS.items():
        if kind!='ship':continue
        state=provider_status(provider)
        if not state['active']:reports.append(state);continue
        key=(provider,region_id)
        with _lock:
            gate=_fetch_locks.setdefault(key,threading.Lock())
        # Never hold the global map lock while a vendor is slow or unavailable.
        with gate:
            with _lock:cached=_cached_regions.get(key)
            if time.time()-_last_attempt.get(key,0)>=interval:
                _last_attempt[key]=time.time()
                try:
                    rows,bad,partial=_fetch_ships(provider,region,deadline)
                    cached={"rows":rows,"received_at":time.time(),"partial":partial}
                    with _lock:_cached_regions[key]=cached
                    _states[provider]={"status":"partial sample" if partial else "report received","last_success":time.time(),"rejected":bad}
                    _record_evidence(provider,region_id,rows,bad,_states[provider]["status"])
                except Exception:
                    _states[provider]={"status":"request failed or request cap reached","last_attempt":time.time()}
                    _record_evidence(provider,region_id,[],0,"request failed")
            if cached:out+=cached["rows"]
        reports.append(provider_status(provider))
    newest={}
    for r in out:
        if recent(r['seen'],time.time(),3600) and (r['mmsi'] not in newest or r['seen']>newest[r['mmsi']]['seen']):newest[r['mmsi']]=r
    return {'region':region_id,'vessels':list(newest.values()),'providers':reports,'computed_at':time.time(),
            'scope':'Requested 0.4 degree port catchment; VesselFinder uses its contracted area. Not complete regional traffic.'}


def ship_snapshot():
    """Read-only cache: global map refreshes must never initiate paid requests."""
    with _lock:
        all_rows=[r for sample in _cached_regions.values() for r in sample['rows'] if recent(r['seen'],time.time(),3600)]
    newest={}
    for r in all_rows:
        if r['mmsi'] not in newest or r['seen']>newest[r['mmsi']]['seen']:newest[r['mmsi']]=r
    return list(newest.values())


def parse_firehose(message,now):
    if message.get('type') not in ('position','ground_position'):return None
    # Estimated/datalink/unknown source codes stay out of the observed-fix layer.
    if message.get('updateType') not in ('A','M','R'):return None
    h=str(message.get('hexid') or '').lower();lat=num(message.get('lat'));lon=num(message.get('lon'));fix=epoch(message.get('clock'))
    if not re.fullmatch('[0-9a-f]{6}',h) or not position(lat,lon) or not recent(fix,now,1200):return None
    return {'hex':h,'flight':str(message.get('ident') or ''),'lat':lat,'lon':lon,'fix':fix,'alt':num(message.get('alt')),
            'on_ground':message.get('type')=='ground_position' or message.get('air_ground')=='G','speed':num(message.get('gs')),
            'track':num(message.get('heading')),'type':message.get('aircrafttype'),'source':'flightaware',
            'collection_type':str(message.get('facility_name') or 'licensed observed source'),'received_at':now}


def firehose_command():
    user=os.getenv('FLIGHTAWARE_FIREHOSE_USERNAME','');key=os.getenv('FLIGHTAWARE_FIREHOSE_API_KEY','')
    if not user or not key or any(c.isspace() for c in user+key):raise ValueError('invalid stream credentials')
    raw=os.getenv('FLIGHTAWARE_FIREHOSE_BOUNDS','5 60 55 145')
    bounds=[float(x) for x in raw.split()]
    if len(bounds)!=4 or not position(bounds[0],bounds[1]) or not position(bounds[2],bounds[3]) or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:raise ValueError('invalid stream bounds')
    return f'live username {user} password {key} events "position ground_position" latlong "{" ".join(str(n) for n in bounds)}"\n'


def _firehose_loop():
    backoff=5
    while provider_status('flightaware')['active']:
        try:
            command=firehose_command()
            if not reserve_request('flightaware'):return
            context=ssl.create_default_context()
            with socket.create_connection(('firehose.flightaware.com',1501),timeout=20) as raw:
                with context.wrap_socket(raw,server_hostname='firehose.flightaware.com') as conn:
                    conn.settimeout(300);conn.sendall(command.encode())
                    _states['flightaware']={'status':'connected; waiting for observed positions'}
                    with conn.makefile('rb') as stream:
                        while provider_status('flightaware')['active']:
                            line=stream.readline(1024*1024+1)
                            if not line or len(line)>1024*1024:raise ValueError('stream interrupted')
                            message=json.loads(line)
                            if message.get('type')=='error':raise ValueError('stream rejected subscription')
                            row=parse_firehose(message,time.time())
                            if row:
                                with _lock:
                                    old=_flight_records.get(row['hex'])
                                    if old is None or row['fix']>old['fix']:_flight_records[row['hex']]=row
                                    if len(_flight_records)>100000:
                                        for h in list(_flight_records):
                                            if not recent(_flight_records[h]['fix'],time.time(),1200):_flight_records.pop(h,None)
                                        if len(_flight_records)>100000:_flight_records.pop(next(iter(_flight_records)))
                                _states['flightaware']={'status':'observed positions received','last_success':time.time()}
                                backoff=5
        except Exception:
            _states['flightaware']={'status':'disconnected or subscription unavailable','last_attempt':time.time()}
            time.sleep(backoff);backoff=min(300,backoff*2)


def flight_snapshot():
    global _worker
    state=_states.get('flightaware',{})
    capped_today=state.get('status')=='daily request cap reached' and state.get('cap_day')==datetime.now(timezone.utc).date().isoformat()
    if provider_status('flightaware')['active'] and not capped_today:
        with _lock:
            if _worker is None or not _worker.is_alive():
                _worker=threading.Thread(target=_firehose_loop,name='licensed-flight-feed',daemon=True);_worker.start()
    with _lock:return [dict(r) for r in _flight_records.values() if recent(r['fix'],time.time(),1200)]


def regional_summary(rows,kind,now=None):
    now=now or time.time();out=[]
    radius=150 if kind=='flight' else 60
    from api.marketdata.tracking import _km
    for ident,name,lat,lon in REGIONS:
        if kind=='ship' and ident in AIR_ONLY_REGIONS:continue
        found=[r for r in rows if position(r.get('lat'),r.get('lon')) and recent(r.get('fix') if kind=='flight' else r.get('seen'),now,1200 if kind=='flight' else 3600)
               and _km(lat,lon,r['lat'],r['lon'])<=radius]
        ages=sorted(now-(r.get('fix') if kind=='flight' else r['seen']) for r in found)
        out.append({'id':ident,'name':name,'lat':lat,'lon':lon,'radius_km':radius,'observed':len(found),
                    'median_age_s':ages[len(ages)//2] if ages else None,'p95_age_s':ages[int((len(ages)-1)*.95)] if ages else None,
                    'coverage':'observations available' if found else 'no recent observations; coverage unknown'})
    return out


def status(kind):
    from api.marketdata import airtraffic as A, tracking as T
    if kind=='ship':
        c=T.ais_collector();rows=(c.all() if c else [])+ship_snapshot()
        rows=list({r['mmsi']:r for r in sorted(rows,key=lambda r:r.get('seen',0))}.values())
        auth={'mode':'community receiver reports','configured':bool(os.getenv('AISSTREAM_API_KEY'))}
    else:
        rows=[]
        for r in A._sweep_rows():rows.append({'hex':r[0],'lat':r[4],'lon':r[3],'fix':r[11]})
        rows+=flight_snapshot()
        rows=list({r['hex']:r for r in sorted(rows,key=lambda r:r.get('fix',0))}.values())
        auth={'mode':'authenticated credentials configured' if A._authenticated() else 'anonymous',
              'credentials_complete':A._authenticated(),'authentication_succeeded':bool(A._token.get('value') and A._token.get('expires',0)>time.time())}
    # No baseline world fetch here: opening a coverage panel must not spend extra OpenSky credits.
    with A._sweep_lock:sweep=[dict(v) for v in A._sweep_health.values()] if kind=='flight' else []
    return {'source':'Locally retained tracking observations and server provider readiness','kind':kind,'as_of':time.time(),'regions':regional_summary(rows,kind),'providers':[provider_status(p) for p,v in SPECS.items() if v[0]==kind],
            'base_feed':auth,'sweep':sweep,'note':'Regional counts cover recent locally retained receiver/supplement observations only; they exclude historical cells and do not measure completeness. Overlapping catchments are not additive.'}


def benchmark():
    with _db() as db:
        rows=db.execute('SELECT provider,region,COUNT(*),SUM(accepted),SUM(rejected),AVG(p50),MAX(p95),SUM(status LIKE ? ) FROM evidence WHERE at>=? GROUP BY provider,region',('%failed%',time.time()-14*86400)).fetchall()
    return {'days':14,'samples':[dict(zip(['provider','region','samples','accepted_reports','rejected_reports','mean_sample_median_age_s','worst_sample_p95_age_s','failed_samples'],r)) for r in rows],
            'note':'Acquisition samples, not independently measured detection rates. No completeness score without a reference dataset.'}

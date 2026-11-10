"""US macro research using ALFRED revision intervals; no revised-data fallback."""
from datetime import date
import asyncio
import hashlib
import json
import pandas as pd
from api.model.data import MACRO_SERIES, transform


def panel_at(history, cutoff, spec=None):
    """Rebuild training history as known at a month-end, including revisions known then.

    Inputs are labelled by their original publication month; historical observations may
    be revised within this vintage. Incomplete observation months are excluded. ALFRED
    supplies daily availability, not intraday timestamps.
    """
    cutoff=date.fromisoformat(str(cutoff)[:10]); cols={}; selected={}; coverage=[]
    for sid,(_,how,_) in (spec or MACRO_SERIES).items():
        rows=history.get(sid,[]); first={}; current={}
        for row in rows:
            if row.get('value') is None:continue
            d=row['date'];a=row['available_from']
            if a<=cutoff.isoformat():first[d]=min(first.get(d,a),a)
            if a<=cutoff.isoformat()<=row['available_until'] and d[:7]<cutoff.isoformat()[:7]:
                if d not in current or a>current[d]['available_from']:current[d]=row
        if not current:
            coverage.append({'series':sid,'observations':0,'status':'unavailable_at_cutoff'});continue
        raw=pd.DataFrame([{'date':pd.Timestamp(d),'value':r['value'],'released':pd.Timestamp(first[d])} for d,r in sorted(current.items())]).set_index('date')
        monthly=raw.value.resample('MS').mean()
        publication=raw.released.groupby(raw.index.to_period('M')).max()
        publication.index=publication.index.to_timestamp()
        values=transform(monthly,how); mapped={}
        for month,value in values.dropna().items():
            released=publication.get(month)
            if pd.notna(released) and released.date()<=cutoff:
                # Process observation months oldest first; newest available observation wins.
                mapped[released.to_period('M').to_timestamp()]=float(value)
        cols[sid]=pd.Series(mapped,dtype=float)
        selected[sid]=[{k:r[k] for k in ('date','value','available_from')} for _,r in sorted(current.items())]
        coverage.append({'series':sid,'observations':len(current),'latest_observation':max(current),'status':'available'})
    panel=pd.DataFrame(cols).sort_index()
    if panel.empty:panel.index=pd.DatetimeIndex([])
    checksum=hashlib.sha256(json.dumps(selected,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return panel,{'cutoff':cutoff.isoformat(),'input_sha256':checksum,'coverage':coverage,
                  'basis':'ALFRED daily revision intervals; completed observation months only; earliest archived availability-month alignment',
                  'intraday_verified':False}


def changes_between(history,before,after,limit=250):
    def snapshot(cutoff):
        result={}
        for sid,rows in history.items():
            for r in rows:
                if r['available_from']<=cutoff<=r['available_until'] and r['date'][:7]<cutoff[:7]:
                    key=(sid,r['date'])
                    if key not in result or r['available_from']>result[key]['available_from']:result[key]=r
        return result
    old,new=snapshot(before),snapshot(after);changes=[];counts={'new_observation':0,'revision':0,'withdrawn':0}
    for key in sorted(old.keys()|new.keys()):
        a,b=old.get(key),new.get(key)
        av,bv=(a or {}).get('value'),(b or {}).get('value')
        if av==bv:continue
        kind='new_observation' if av is None and bv is not None else 'withdrawn' if bv is None else 'revision'
        counts[kind]+=1
        if len(changes)<limit:changes.append({'series':key[0],'observation_date':key[1],'before':av,'after':bv,'kind':kind,
                                             'available_from':(b or a)['available_from']})
    return {'from':before,'through':after,'counts':counts,'changes':changes,'truncated':sum(counts.values())>limit,
            'note':'Source observation changes, not causal contributions to forecast probability. Monthly aggregation and re-estimation can also change factors.'}


async def load_history(start='1965-01-01'):
    from api.providers.alfred import vintage_history
    sem=asyncio.Semaphore(3)
    async def one(sid):
        async with sem:
            try:return sid,await asyncio.to_thread(vintage_history,sid,start),None
            except Exception:return sid,[], 'Vintage source unavailable or incomplete; no revised-data substitution'
    rows=await asyncio.gather(*(one(sid) for sid in MACRO_SERIES))
    return {sid:data for sid,data,_ in rows},[{'series':sid,'reason':error} for sid,_,error in rows if error]

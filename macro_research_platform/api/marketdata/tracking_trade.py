"""Calendar-aligned PortWatch trade context, separate from receiver marker counts."""
import time
from datetime import date, timedelta
from collections import defaultdict
from api.marketdata.core import _cached, Upstream
from api.marketdata.tracker_quality import calendar_average, finite
from api.marketdata.edge import PW, _get

PORTS=['Shanghai','Ningbo-Zhoushan','Shenzhen','Guangzhou','Qingdao','Tianjin','Hong Kong','Singapore','Port Klang',
       'Jebel Ali','Mundra','Colombo','Mombasa','Durban','Cape Town','Santos','Callao','Los Angeles-Long Beach','Rotterdam']


def summarize(rows,partial=False):
    # One terminal/date record; identical duplicate pages must not double reported cargo.
    terminals=defaultdict(dict)
    for r in rows:
        name=str(r.get('portname') or '')
        base=next((p for p in sorted(PORTS,key=len,reverse=True) if name.startswith(p)),None)
        try:day=date.fromisoformat(str(r.get('date'))[:10]).isoformat()
        except ValueError:continue
        if not base:continue
        key=(name,day)
        record={k:r.get(k) if finite(r.get(k)) and r[k]>=0 else None for k in ('import','export','portcalls')}
        if key in terminals[base]:
            old=terminals[base][key]
            record={k:v if old.get(k)==v else None for k,v in record.items()}
        terminals[base][key]=record
    out=[]
    for base,records in terminals.items():
        end=max(day for _,day in records)
        names={name for name,_ in records}
        daily=[]
        for day in sorted({day for _,day in records}):
            reports=[records.get((name,day)) for name in names]
            row={'date':day}
            for field in ('import','export','portcalls'):
                vals=[r.get(field) if r else None for r in reports]
                row[field]=sum(vals) if all(v is not None for v in vals) else None
            daily.append(row)
        end_day=date.fromisoformat(end)
        avg=lambda field,offset=0:calendar_average(daily,end_day-timedelta(days=offset),28,field)
        imp,exp,calls=(None,None,None) if partial else (avg('import'),avg('export'),avg('portcalls'))
        total=imp+exp if imp is not None and exp is not None else None
        prev_i,prev_e=avg('import',364),avg('export',364)
        previous=prev_i+prev_e if prev_i is not None and prev_e is not None else None
        out.append({'port':base,'as_of':end,'reporting_terminals':len(names),'imports_t_day':imp,'exports_t_day':exp,'calls_day':calls,
                    'tonnes_day':total,'tonnes_yoy':total/previous-1 if total is not None and previous is not None and previous>0 else None,
                    'window_days':28,'complete_window':all(v is not None for v in (imp,exp,calls)) and not partial,
                    'note':'Reporting terminal sample; terminal inventory completeness is not independently verified.'})
    return {'as_of':max((r['as_of'] for r in out),default=None),'ports':out,'partial':partial,'source':'IMF PortWatch Daily_Ports_Data',
            'basis':'Estimated maritime imports/exports, tonnes per day; observed port calls. Full 28-calendar-day windows required; nulls and absent dates are not zero.',
            'comparison':'Same-length window ending 364 days earlier; modelled cargo estimates, not customs-cleared trade or manifests.'}


def port_trade():
    def load():
        today=date.today();recent=(today-timedelta(days=110)).isoformat();ly0=(today-timedelta(days=414)).isoformat();ly1=(today-timedelta(days=354)).isoformat()
        names=' OR '.join("portname LIKE '"+p.replace("'","''")+"%'" for p in PORTS)
        where=f"({names}) AND (date >= '{recent}' OR (date >= '{ly0}' AND date <= '{ly1}'))"
        rows=[];partial=False
        deadline=time.monotonic()+65
        for page in range(8):
            remaining=deadline-time.monotonic()
            if remaining<1:
                partial=True
                break
            j=_get(f'{PW}/Daily_Ports_Data/FeatureServer/0/query',params={'f':'json','where':where,'outFields':'date,portname,country,portcalls,import,export',
                  'orderByFields':'date,portname','resultOffset':page*2000,'resultRecordCount':2000},timeout=min(20,remaining)).json()
            if j.get('error'):raise Upstream('PortWatch trade data unavailable')
            batch=[f.get('attributes',{}) for f in j.get('features',[])];rows+=batch
            partial=bool(j.get('exceededTransferLimit'))
            if not partial or not batch:break
        if not rows:raise Upstream('PortWatch returned no port-trade observations')
        return summarize(rows,partial)
    return _cached('tracking:trade-calendar:v1',6*3600,load)

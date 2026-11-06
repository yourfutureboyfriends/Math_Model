"""Evidence-based research views assembled from scoped captures, not inferred private flows."""
import math
from datetime import datetime, timezone
from api.workflows import evidence


def estimate_revisions(records):
    previous={};changes=[];unmatched=0
    for record in sorted(records,key=lambda r:(r.get('recorded_at',r.get('updated_at','')),r.get('version',0))):
        p=record.get('payload') or {}
        if p.get('kind')!='earnings':continue
        capture=p.get('_evidence') or {};received=capture.get('server_received_at') or record.get('recorded_at')
        for metric,rows in (p.get('payload',{}).get('estimates') or {}).items():
            if metric not in ('eps','revenue'):continue
            for row in rows:
                end=row.get('period_end') or row.get('endDate') or row.get('fiscalDateEnding')
                # Relative 0q/0y labels roll; never call their difference a same-period revision.
                if not end:unmatched+=1;continue
                value=row.get('avg');key=(p.get('symbol'),metric,str(end),p.get('payload',{}).get('currency'))
                if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):continue
                old=previous.get(key)
                if old and old['value']!=value:
                    changes.append({'symbol':key[0],'metric':metric,'period_end':key[2],'currency':key[3],'before':old['value'],'after':value,'change':value-old['value'],'from_received_at':old['received'],'received_at':received,'source':p.get('payload',{}).get('source')})
                previous[key]={'value':value,'received':received}
    return {'changes':changes,'unmatched_period_rows':unmatched,'note':'Prospective captured history only. Relative period labels without an explicit fiscal end are not matched. Server receipt dates bound historical availability; publisher times are not invented.'}


def validate_values(rows):
    groups={};rejected=[];seen=set()
    now=datetime.now(timezone.utc).isoformat()
    for index,r in enumerate(rows):
        try:
            issued,actual,trained=[evidence.instant(r[k]) for k in ('issued_at','actual_at','trained_through')]
            if not trained<=issued<actual<=now:raise ValueError('Training, issue and observed outcome timestamps are inconsistent')
            for k in ('forecast','actual','benchmark'):
                if not isinstance(r[k],(int,float)) or isinstance(r[k],bool) or not math.isfinite(r[k]):raise ValueError('Finite forecast, outcome and benchmark required')
            if not str(r.get('source_url','')).startswith(('https://','http://')):raise ValueError('Outcome evidence URL required')
            if not r.get('currency'):raise ValueError('Forecast/outcome currency is required')
            horizon=round((datetime.fromisoformat(actual)-datetime.fromisoformat(issued)).total_seconds()/86400,3)
            key=(r.get('symbol'),r.get('model'),r.get('target'),issued,actual)
            if key in seen:raise ValueError('Duplicate forecast/outcome')
            seen.add(key);group=(r.get('model','unspecified'),r.get('region','unspecified'),r.get('sector','unspecified'),r.get('target','unspecified'),r['currency'],horizon)
            groups.setdefault(group,[]).append(r)
        except (ValueError,KeyError,TypeError) as e:rejected.append({'row':index+1,'reason':str(e)})
    result=[]
    for (model,region,sector,target,currency,horizon),sample in groups.items():
        mse=sum((r['forecast']-r['actual'])**2 for r in sample)/len(sample);base=sum((r['benchmark']-r['actual'])**2 for r in sample)/len(sample)
        result.append({'model':model,'region':region,'sector':sector,'target':target,'currency':currency,'horizon_days':horizon,'count':len(sample),'mae':sum(abs(r['forecast']-r['actual']) for r in sample)/len(sample),'rmse':math.sqrt(mse),'benchmark_rmse':math.sqrt(base),'skill_mse':1-mse/base if base else None})
    return {'groups':result,'accepted':sum(r['count'] for r in result),'rejected':rejected,'note':'Evaluates supplied dated outcomes and baselines; timestamp consistency is checked, independent provenance and genuine out-of-sample training are not certified. Match forecast horizons and currencies before importing.'}


def execution_cost(row):
    sign=1 if row['side']=='BUY' else -1
    quantity=row['quantity'];fill=row['fill_price'];arrival=row.get('arrival_price');trades=row.get('trades') or []
    total=sum(t['volume'] for t in trades)
    vwap=sum(t['price']*t['volume'] for t in trades)/total if total else None
    shortfall=sign*(fill-arrival)*quantity if arrival is not None else None
    fees=row.get('fees');net=shortfall+fees if shortfall is not None and fees is not None else None
    fx=row.get('fx_to_base')
    return {'method_version':'supplied-prints-tca-v1','input_sha256':evidence.digest(row),'shortfall_local':shortfall,'fees_local':fees,'total_cost_local':net,'total_cost_base':net*fx if net is not None and fx is not None else None,
            'currency':row['currency'],'base_currency':row['base_currency'],'vwap':vwap,'sample_volume':total,
            'vs_vwap_bps':sign*(fill/vwap-1)*10000 if vwap else None,'vs_arrival_bps':sign*(fill/arrival-1)*10000 if arrival else None,
            'fill_at':row['fill_at'],'decision_at':row['decision_at'],'fx_at':row.get('fx_at'),'source_url':row['source_url'],
            'note':'VWAP uses only supplied prints in the declared interval, not a consolidated-market guarantee. Fees and FX remain unavailable unless supplied. No separation of spread and market impact is inferred.'}

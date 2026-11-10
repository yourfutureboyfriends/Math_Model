"""Country × sector DCF regression audit; public data, never a price-target optimizer.

Discovery uses primary stocks already in the platform universe. Empty cells mean
universe/provider coverage gaps, not proof that an economy has no such companies.
Snapshots are immutable and resumable. --offline replays captured inputs only.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from contextlib import ExitStack
from datetime import datetime, timezone
import csv
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from api.markets import COUNTRIES
from api.marketdata import core, dcf, dcf_fundamentals
from api.marketdata.dcf_expectations import apply_risk_basis, expectations, reprice_rate_shift
from scripts.audit_dcf_markets import SECTORS, size, fetch


def sectors():return [SECTORS.get(s,s) for s in core.SECTORS]


def discover(country,sector,stocks):
    """Query sector membership; require an existing primary-universe listing."""
    from yfinance import EquityQuery as Q
    spec=COUNTRIES[country]
    if not spec['exch']:
        return {'country':country,'sector':SECTORS.get(sector,sector),'rows':[],'error':'No supported primary exchange configured; market cannot be screened by this provider.'}
    q=Q('and',[Q('is-in',['exchange',*spec['exch']]),Q('eq',['sector',sector])])
    if country=='US':q=Q('and',[q,Q('eq',['region','us'])])
    res=core._yscreen(q,size=250,sortField='intradaymarketcap',sortAsc=False)
    symbols={r['symbol'] for r in res.get('quotes',[])}
    rows=[{**r,'sector':SECTORS.get(sector,sector)} for r in stocks if r['country']==country and r['symbol'] in symbols]
    return {'country':country,'sector':SECTORS.get(sector,sector),'provider_total':res.get('total'),'rows':rows,'as_of':datetime.now(timezone.utc).isoformat()}


def select_rows(rows,minimum=2):
    """One large and one smaller distinct issuer; then fill uncovered cap bands."""
    rows=sorted(rows,key=lambda r:r.get('mcap_usd',0),reverse=True)
    chosen=[];seen=set()
    from api.global_universe import name_key
    def add(r):
        issuer=name_key(r.get('name') or r['symbol'])
        if issuer not in seen:chosen.append({**r,'size':size(r.get('mcap_usd',0)),'selection':'country/sector; size-diverse distinct issuers'});seen.add(issuer)
    if rows:
        add(rows[0]);add(rows[-1])
    for bucket in ('small','mid','large'):
        candidates=[r for r in rows if size(r.get('mcap_usd',0))==bucket]
        if candidates and not any(r['size']==bucket for r in chosen):add(candidates[len(candidates)//2])
    for r in rows:
        if len(chosen)>=minimum:break
        add(r)
    return chosen


def balanced_rows(rows):
    """Round-robin countries so a request budget is not exhausted alphabetically."""
    from collections import defaultdict,deque
    groups=defaultdict(deque)
    for row in rows:groups[row['country']].append(row)
    result=[]
    while any(groups.values()):
        for country in sorted(groups):
            if groups[country]:result.append(groups[country].popleft())
    return result


def provider_limited(record):
    message=str(record.get('error','')).lower()
    return any(s in message for s in ('rate-limit','rate limit','too many requests','429','provider cooldown'))


def fetch_checkpoints(rows,outdir,workers=2,fetcher=fetch):
    """Bound submissions, and defer remaining work after provider cooldown.

    Do not launch hundreds of doomed requests or mislabel cooldown as missing company data.
    Resume requires --retry-provider; completed observations remain immutable.
    """
    iterator=iter(rows);stopped=False
    with ThreadPoolExecutor(max_workers=max(1,min(workers,4))) as pool:
        pending={}
        def submit():
            try:row=next(iterator)
            except StopIteration:return
            pending[pool.submit(fetcher,row)]=row
        for _ in range(max(1,min(workers,4))):submit()
        completed=0
        while pending:
            done,_=wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                row=pending.pop(future)
                try:record=future.result()
                except Exception as exc:record={'selection':row,'error':f'{type(exc).__name__}: {exc}'}
                (outdir/(row['symbol']+'.json')).write_text(json.dumps(record,indent=2,default=str,allow_nan=False))
                completed+=1
                print(f'fetch {completed}/{len(rows)} {row["symbol"]}: {record.get("error","saved")}',flush=True)
                stopped=stopped or provider_limited(record)
            if not stopped:
                for _ in done:submit()
        if stopped:
            for row in iterator:
                record={'selection':row,'error':'Provider cooldown: deferred without requesting company data; resume with --retry-provider.'}
                (outdir/(row['symbol']+'.json')).write_text(json.dumps(record,indent=2))
            print('Provider cooldown: remaining requests deferred; no automatic retry burst.',flush=True)


def evaluate(snapshot):
    row=snapshot['selection'];out={k:row.get(k) for k in ('symbol','name','country','sector','size')}
    out['snapshot_as_of']=snapshot.get('fetched_at');out['snapshot_provenance']=snapshot.get('snapshot_provenance','not_captured' if snapshot.get('error') else 'fresh_capture');out['fresh_fetch_error']=snapshot.get('fresh_fetch_error');out['checks']={};out['issues']=[]
    if snapshot.get('error'):return {**out,'status':'provider_deferred' if provider_limited(snapshot) else 'source_conflict' if 'currency' in snapshot['error'].lower() and 'disagrees' in snapshot['error'].lower() else 'data_unavailable','error':snapshot['error']}
    inp,erp=apply_risk_basis(snapshot['inputs']);out['input_as_of']=inp.get('as_of')
    def convert(amount,currency):
        rate=snapshot.get('fx_usd_per',{}).get(currency)
        return amount*rate if amount is not None and rate is not None else None
    with ExitStack() as stack:
        stack.enter_context(patch.object(dcf,'_info',return_value=snapshot.get('info',{})))
        stack.enter_context(patch.object(dcf,'_dividend_history',return_value=snapshot.get('dividends',[])))
        stack.enter_context(patch.object(dcf,'to_usd',side_effect=convert))
        try:
            industry=inp.get('industry') or ''
            try:dividend=dcf.value_ddm(inp,erp=erp)
            except core.NotFound:dividend=None
            model='excess_return' if inp.get('is_financial') else 'ddm' if industry.startswith(('REIT','Utilities')) and dividend else 'fcff'
            engine={'fcff':dcf.value,'ddm':dcf.value_ddm,'excess_return':dcf.value_financial}[model]
            try:v=dividend if model=='ddm' else engine(inp,erp=erp)
            except core.NotFound as exc:
                original=exc;v=None
                if model=='excess_return' and not inp.get('is_bank_like',False):
                    try:v=dcf.value(inp,erp=erp);model='fcff'
                    except core.NotFound:pass
                if v is None and dividend is not None:v=dividend;model='ddm'
                if v is None:raise original
                out['fallback_reason']=str(original)
            if model=='fcff' and v.get('equity_negative') and dividend and (dividend.get('dividend_yield') or 0)>=.015:
                model='ddm';v=dividend;out['fallback_reason']='FCFF leaves no equity value; using the regular-dividend fallback, matching the application.'
            out.update(model=model,price=inp.get('price'),currency=inp.get('price_currency'),cashflow_currency=inp.get('currency'),value=v.get('per_share'),terminal_share=v.get('terminal_share'))
            out['research_status']=dcf_fundamentals.research_status(inp,v,model,dcf_fundamentals.diagnostics(inp,v,model))
            if snapshot.get('fresh_fetch_error'):
                reason='Prior snapshot replay only; current observation is not verified: '+str(snapshot['fresh_fetch_error'])
                out['research_status']['reasons'].append(reason);out['research_status'].update(eligible=False,status='research_required')
            if model=='ddm' and not snapshot.get('dividends'):
                reason='Dividend history was not captured; this replay uses quoted payout inputs and requires growth/payout review.'
                out['issues'].append(reason);out['research_status']['reasons'].append(reason);out['research_status'].update(eligible=False,status='research_required')
            checks=out['checks'];checks['finite_nonnegative_value']=v.get('per_share') is not None and math.isfinite(v['per_share']) and v['per_share']>=0
            if v.get('per_share') is None:
                out.update(status='data_unavailable',error='No comparable per-share value; check price, share count and listing/reporting currency conversion.')
                return out
            if model=='fcff':
                close=lambda x,y: math.isclose(x,y,rel_tol=1e-7,abs_tol=1e-4)
                checks['enterprise_pv_bridge']=close(v['enterprise_value'],sum(r['pv'] for r in v['projection'])+v['pv_terminal'])
                equity=v['enterprise_value']-(inp.get('debt') or 0)+(inp.get('cash') or 0)+(inp.get('investments') or 0)-(inp.get('minority_interest') or 0)
                checks['equity_bridge']=close(v['equity_value'],max(0.,equity))
                checks['reporting_share_bridge']=close(v['per_share_reporting_ccy'],v['equity_value']/inp['shares'])
                split=dict(inp,shares=inp['shares']*10,price=inp.get('price')/10 if inp.get('price') is not None else None)
                sv=dcf.value(split,erp=erp)
                checks['ten_for_one_split']=sv.get('per_share') is not None and close(sv['per_share']*10,v['per_share'])
                e=expectations(inp,v,{'erp':erp});out['expectations']=e
                near=lambda x,y:x is not None and y is not None and math.isclose(x,y,rel_tol=1e-7,abs_tol=1e-6)
                checks['grid_center']=near(e['grid'][4].get('per_share'),v.get('per_share'))
                if v.get('equity_value',0)>0 and v.get('per_share') is not None:
                    checks['zero_rate_shift']=near(reprice_rate_shift(v,0),v['per_share'])
                # Negative cash flows can produce non-monotonic rate sensitivity; review, not a formula failure.
                positives=all(r.get('fcff',0)>=0 for r in v.get('projection',[])) and v.get('terminal_fcff',0)>=0
                if positives and v.get('per_share',0)>0 and all(r.get('per_share') is not None for r in e['rate_stress']):
                    checks['rate_monotonicity']=e['rate_stress'][1]['per_share']<=e['rate_stress'][0]['per_share']<=v['per_share']+1e-6
                if any(r.get('per_share') is None for r in e['grid']):out['issues'].append('some_operating_scenarios_unavailable')
            out['status']='mechanics_failed' if not all(checks.values()) else 'research_required' if not out['research_status']['eligible'] else 'checks_passed'
        except Exception as exc:out.update(status='model_unavailable',error=f'{type(exc).__name__}: {exc}')
    return out


def report(outdir,countries,discoveries,selected,results):
    by_symbol={r['symbol']:r for r in results};cells=[]
    for country in countries:
        for sector in sectors():
            rows=[r for r in selected if r['country']==country and r['sector']==sector]
            tested=[by_symbol[r['symbol']] for r in rows if r['symbol'] in by_symbol]
            usable=[r for r in tested if r.get('status') in ('checks_passed','research_required')]
            d=next((x for x in discoveries if x['country']==country and x['sector']==sector),{})
            cells.append({'country':country,'sector':sector,'available_in_universe':len(d.get('rows',[])), 'selected':len(rows),'attempted':len(tested),'valued':len(usable),'eligible':sum(r.get('status')=='checks_passed' for r in tested),'prior_snapshot_replays':sum(r.get('snapshot_provenance')=='prior_snapshot' for r in usable),'mechanics_failed':sum(r.get('status')=='mechanics_failed' for r in tested),'coverage':'multiple_valued' if len(usable)>=2 else 'one_valued' if usable else 'no_valuation','discovery_error':d.get('error'),'symbols':' '.join(r['symbol'] for r in rows)})
    from collections import Counter
    summary={'created_at':datetime.now(timezone.utc).isoformat(),'countries':len(countries),'sectors':len(sectors()),'cells':len(cells),'selected':len(selected),'attempted':len(results),'status_counts':dict(Counter(r['status'] for r in results)),'provenance_counts':dict(Counter(r['snapshot_provenance'] for r in results)),'coverage_counts':dict(Counter(c['coverage'] for c in cells)),'mechanics_failures':[r for r in results if r['status']=='mechanics_failed'],'note':'A successful mechanical check is not source verification, a backtest or evidence of investment accuracy. Empty cells describe platform-universe/provider gaps, not absence of an economic sector.'}
    summary['valued_companies']=sum(r['status'] in ('checks_passed','research_required') for r in results)
    summary['valued_markets']=len({r['country'] for r in results if r['status'] in ('checks_passed','research_required')})
    for name,data in [('results',results),('coverage',cells),('summary',summary)]:
        (outdir/(name+'.json')).write_text(json.dumps(data,indent=2,default=str,allow_nan=False))
    with (outdir/'coverage.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(cells[0]));w.writeheader();w.writerows(cells)
    columns=['symbol','name','country','sector','size','model','status','snapshot_provenance','snapshot_as_of','input_as_of','currency','cashflow_currency','price','value','terminal_share','fallback_reason','selected_growth','implied_growth','implied_margin','rate_stress_1pp','rate_stress_2pp','checks','research_reasons','error','fresh_fetch_error']
    with (outdir/'results.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader()
        for row in results:
            e=row.get('expectations',{});shocks=e.get('rate_stress',[])
            w.writerow({**row,'selected_growth':e.get('selected_growth'),'implied_growth':e.get('implied_growth'),'implied_margin':e.get('implied_margin'),'rate_stress_1pp':shocks[0].get('per_share') if shocks else None,'rate_stress_2pp':shocks[1].get('per_share') if len(shocks)>1 else None,'research_reasons':' | '.join(row.get('research_status',{}).get('reasons',[]))})
    print(json.dumps({k:v for k,v in summary.items() if k!='mechanics_failures'}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'data/processed/dcf_matrix_2026-10-31');p.add_argument('--offline',action='store_true');p.add_argument('--workers',type=int,default=2);p.add_argument('--retry-provider',action='store_true');p.add_argument('--max-fetch',type=int);p.add_argument('--request-rate',type=float,default=2.0);p.add_argument('--countries',nargs='*');p.add_argument('--minimum',type=int,default=2);p.add_argument('--prior-snapshots',type=Path);a=p.parse_args()
    if not 0<a.request_rate<=4:p.error('--request-rate must be greater than zero and at most 4 requests/second')
    core.YAHOO_RATE=a.request_rate;core.YAHOO_BURST=4.;core._YH_BUCKET['tokens']=4.
    a.output.mkdir(parents=True,exist_ok=True)
    for d in ('discovery','snapshots'):(a.output/d).mkdir(exist_ok=True)
    stocks=json.loads((ROOT/'data/processed/global_universe.json').read_text())['stocks'];countries=a.countries or sorted(COUNTRIES)
    discoveries=[];jobs=[]
    for c in countries:
        for s in core.SECTORS:
            path=a.output/'discovery'/f'{c}_{s.replace(" ","_")}.json'
            if path.exists():
                cached=json.loads(path.read_text())
                if not a.offline and a.retry_provider and provider_limited(cached):jobs.append((c,s,path))
                else:discoveries.append(cached)
            elif not a.offline:jobs.append((c,s,path))
    with ThreadPoolExecutor(max_workers=max(1,min(a.workers,4))) as pool:
        pending={pool.submit(discover,c,s,stocks):(c,s,path) for c,s,path in jobs}
        for n,f in enumerate(as_completed(pending),1):
            c,s,path=pending[f]
            try:r=f.result()
            except Exception as exc:r={'country':c,'sector':SECTORS.get(s,s),'rows':[],'error':f'{type(exc).__name__}: {exc}'}
            path.write_text(json.dumps(r,indent=2,default=str));discoveries.append(r)
            print(f'discovery {n}/{len(jobs)} {c} {s}: {len(r["rows"])} {r.get("error","")}',flush=True)
    selected=[r for d in discoveries for r in select_rows(d.get('rows',[]),a.minimum)]
    prior={}
    if a.prior_snapshots:
        for path in sorted(a.prior_snapshots.glob('*.json')):
            record=json.loads(path.read_text());row=dict(record['selection'])
            if row['country'] not in countries or record.get('error'):continue
            sector=record.get('info',{}).get('sector') or row.get('sector');row['sector']=SECTORS.get(sector,sector)
            if row['sector'] not in sectors():continue
            prior[row['symbol']]=record
            if not any(r['symbol']==row['symbol'] for r in selected):selected.append({**row,'selection':'Prior snapshot audit supplement; not a fresh observation'})
    (a.output/'manifest.json').write_text(json.dumps({'selection':selected,'countries':countries,'minimum_per_cell':a.minimum},indent=2))
    missing=[]
    for row in selected:
        path=a.output/'snapshots'/(row['symbol']+'.json')
        if not path.exists() or (a.retry_provider and provider_limited(json.loads(path.read_text()))):missing.append(row)
    missing=balanced_rows(missing)
    if not a.offline:fetch_checkpoints(missing[:a.max_fetch] if a.max_fetch is not None else missing,a.output/'snapshots',a.workers)
    results=[]
    for n,row in enumerate(selected,1):
        path=a.output/'snapshots'/(row['symbol']+'.json')
        snap=json.loads(path.read_text()) if path.exists() else None
        if (snap is None or snap.get('error')) and row['symbol'] in prior:
            old=dict(prior[row['symbol']]);old['snapshot_provenance']='prior_snapshot';old['fresh_fetch_error']=snap.get('error') if snap else 'No fresh observation';snap=old
        if snap is not None:
            snap['selection']=row;results.append(evaluate(snap))
        if n%25==0:print(f'evaluate {n}/{len(selected)}',flush=True)
    report(a.output,countries,discoveries,selected,results)

if __name__=='__main__':main()

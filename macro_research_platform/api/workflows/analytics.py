"""Pure, inspectable calculations. No implicit quote or FX downloads."""
import copy
import math


def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)


def valuation_bridge(before,after,method="ordered"):
    """Ordered counterfactual bridge of captured FCFF projections; sums exactly to the change."""
    def extract(p):
        p=p.get('payload',p)
        primary=p.get('primary') or p.get('base') or p
        v=primary.get('valuation',primary)
        inp=primary.get('inputs') or {}
        if (v.get('model') or p.get('model'))!='fcff':
            raise ValueError('The counterfactual bridge requires two FCFF snapshots; other models retain numeric comparison.')
        rows=v.get('projection') or []
        if not rows or not all(all(finite(r.get(k)) for k in ('revenue','nopat','reinvestment','discount_factor')) and r['revenue']!=0 for r in rows):
            raise ValueError('Captured projections are incomplete')
        eq=v.get('equity_value'); ps=v.get('per_share'); ev=v.get('enterprise_value'); tv=v.get('pv_terminal')
        if not all(finite(x) for x in (eq,ps,ev,tv)) or eq<=0:
            raise ValueError('Positive captured equity and complete terminal/bridge values are required')
        shares=inp.get('shares')
        # Unit conversion combines listing units, ADR ratio and FX when they are embedded in per-share value.
        return {'revenue':[r['revenue'] for r in rows], 'margin_tax':[r['nopat']/r['revenue'] for r in rows],
                'reinvestment':[r['reinvestment'] for r in rows], 'discount':[r['discount_factor'] for r in rows],
                'terminal':tv,'bridge':eq-ev,'units':ps/eq,'years':[r.get('year') for r in rows], 'shares':shares,'price':ps,
                'currency':p.get('currency') or inp.get('price_currency')}
    old,new=extract(before),extract(after)
    if old['years']!=new['years'] or old['currency']!=new['currency']:
        raise ValueError('Projection years and listing currency must match')
    def value(s):
        ev=sum((r*m-i)*d for r,m,i,d in zip(s['revenue'],s['margin_tax'],s['reinvestment'],s['discount']))+s['terminal']
        return (ev+s['bridge'])*s['units']
    state=copy.deepcopy(old); prior=value(state); result=[]
    if abs(prior-old['price'])>max(1e-6,abs(old['price'])*1e-6):
        raise ValueError('Captured cash flows do not reconcile to the saved valuation')
    for key,label in [('revenue','Revenue / earnings scale'),('margin_tax','Operating margin and tax'),('reinvestment','Reinvestment'),('discount','Explicit-period discount factors'),('terminal','Terminal value including terminal discount'),('bridge','Debt, cash, stakes and minority interests'),('units','Share count, FX and listing units')]:
        state[key]=new[key]; current=value(state)
        result.append({'driver':label,'contribution':current-prior,'value_after':current});prior=current
    if abs(prior-new['price'])>max(1e-6,abs(new['price'])*1e-6):
        raise ValueError('Comparison cash flows do not reconcile to the saved valuation')
    if method not in ('ordered','shapley'):raise ValueError('Unknown attribution method')
    if method=='shapley':
        groups=['revenue','margin_tax','reinvestment','discount','terminal','bridge','units'];n=len(groups);cache={}
        for mask in range(1<<n):
            state={**old,**{k:new[k] for i,k in enumerate(groups) if mask&(1<<i)}}
            cache[mask]=value(state)
        for i,row in enumerate(result):
            total=0.
            for mask in range(1<<n):
                if mask&(1<<i):continue
                size=mask.bit_count();weight=math.factorial(size)*math.factorial(n-size-1)/math.factorial(n)
                total+=weight*(cache[mask|(1<<i)]-cache[mask])
            row.update(contribution=total,value_after=None)
    return {'before':old['price'],'after':new['price'],'change':new['price']-old['price'],'contributions':result,
            'residual':new['price']-old['price']-sum(r['contribution'] for r in result),'currency':old['currency'],
            'method':('Exact Shapley allocation across seven captured driver groups; interactions shared across all substitution orders. Not causal attribution. No path value is implied.' if method=='shapley' else 'Ordered counterfactual substitution of captured projections; order-dependent, not causal attribution.')+' Terminal discount effects remain in the terminal group. No provider data is fetched.'}


def reconcile(broker,book,quantity_tolerance=1e-6):
    def aggregate(rows):
        out={}
        for r in rows:
            s=str(r.get('symbol','')).strip().upper();q=r.get('quantity')
            if not s or not finite(q):raise ValueError('Each row requires symbol and finite quantity')
            currency=str(r.get('currency') or 'UNKNOWN');currency=currency if currency in ('GBp','GBX','ZAc') else currency.upper();key=(s,currency)
            item=out.setdefault(key,{'quantity':0.,'cash':0.,'cash_known':True,'value':0.,'value_known':True,'value_currency':r.get('value_currency'),'price_sum':0.,'price_weight':0.,'price_known':True,'fx':r.get('fx_rate',r.get('fx_rate_to_base'))})
            item['quantity']+=q
            if finite(r.get('cash')):item['cash']+=r['cash']
            else:item['cash_known']=False
            if finite(r.get('market_value')) and r.get('value_currency') and r.get('value_currency')==item['value_currency']:item['value']+=r['market_value']
            else:item['value_known']=False
            price=r.get('price',r.get('current_price'))
            if finite(price):item['price_sum']+=price*abs(q);item['price_weight']+=abs(q)
            else:item['price_known']=False
            fx=r.get('fx_rate',r.get('fx_rate_to_base'))
            if not finite(fx) or fx!=item['fx']:item['fx']=None
        return out
    a,b=aggregate(broker),aggregate(book);rows=[]
    for key in sorted(a.keys()|b.keys()):
        x,y=a.get(key),b.get(key);qx=x['quantity'] if x else 0;qy=y['quantity'] if y else 0
        status='missing_in_book' if not y else 'missing_at_broker' if not x else 'quantity_break' if abs(qx-qy)>quantity_tolerance else 'matched'
        cash=x['cash']-y['cash'] if x and y and x['cash_known'] and y['cash_known'] else None
        value=x['value']-y['value'] if x and y and x['value_known'] and y['value_known'] and x['value_currency']==y['value_currency'] else None
        price=x['price_sum']/x['price_weight']-y['price_sum']/y['price_weight'] if x and y and x['price_known'] and y['price_known'] and x['price_weight'] and y['price_weight'] else None
        fx=x['fx']-y['fx'] if x and y and x['value_currency'] and x['value_currency']==y['value_currency'] and finite(x['fx']) and finite(y['fx']) else None
        if status=='matched' and ((value is not None and abs(value)>.01) or (fx is not None and abs(fx)>1e-6) or (cash is not None and abs(cash)>.01)):status='valuation_or_cash_break'
        ratio=qx/qy if qy else None
        hint='Review split, consolidation or share-class treatment; no correction inferred.' if status=='quantity_break' and ratio and any(abs(ratio-r)<1e-5 for r in (.1,.2,.25,1/3,.5,2,3,4,5,10)) else None
        rows.append({'symbol':key[0],'currency':key[1],'broker_quantity':qx,'book_quantity':qy,'quantity_difference':qx-qy,'status':status,
                     'cash_difference':cash,'market_value_difference':value,'value_currency':x['value_currency'] if x and y and x['value_currency']==y['value_currency'] else None,'price_difference':price,'fx_rate_difference':fx,'review_hint':hint})
    return {'rows':rows,'breaks':sum(r['status']!='matched' for r in rows),'comparison_coverage':{k:sum(r[k] is not None for r in rows) for k in ('cash_difference','market_value_difference','price_difference','fx_rate_difference')},
            'note':'Read-only comparison. Currency mismatches remain separate rows. Market values require the same explicit value currency; FX rates must both be to that currency. Pricing dates may differ. Split hints are review prompts, not inferred corrections. No position, cash or corporate-action booking is changed.'}


def quality(inp):
    cf=inp.get('cashflow_evidence') or {};ni=inp.get('net_income');cfo=cf.get('cfo');rev=inp.get('revenue');sbc=cf.get('sbc',inp.get('sbc'));capex=cf.get('capex')
    def ratio(a,b):return a/b if finite(a) and finite(b) and b!=0 else None
    checks=[]
    matched=cf.get('status')=='matched'
    conversion=ratio(cfo,ni) if matched and finite(ni) and ni>0 else None
    if conversion is not None and conversion<.8:checks.append('Operating cash flow is below 80% of earnings; review working capital and noncash items.')
    if finite(ni) and ni>0 and finite(cfo) and cfo<0:checks.append('Positive accounting earnings but negative operating cash flow.')
    if not matched:checks.append('Cash-flow evidence is not period-matched; cash conversion/accrual comparisons are withheld.')
    return {'source':inp.get('source'),'as_of':inp.get('as_of'),'currency':inp.get('currency'),'cashflow_evidence':cf,
            'reported_net_income':ni,'operating_cash_flow':cfo,'revenue':rev,'shares':inp.get('shares'),'cash_conversion':conversion,'cash_earnings_gap_to_sales':ratio(ni-cfo,rev) if matched and finite(ni) and finite(cfo) else None,
            'sbc_to_sales':ratio(sbc,rev) if matched else None,'cash_after_capex_and_sbc':cfo-capex-sbc if matched and all(finite(x) for x in (cfo,capex,sbc)) else None,
            'checks':checks,'reported_adjusted_reconciliation':{'available':False,'reason':'No audited, period-matched provider adjustment bridge supplied. No adjusted earnings are invented.'},
            'note':'Accrual proxy uses earnings minus operating cash flow / sales; it is not the balance-sheet Sloan accrual measure. SBC is treated as a cost, not added back.'}


def scenario(positions,equity_shock,fx_shock,cash,long_margin,short_margin):
    rows=[];pnl=0;required=0;missing=[]
    for p in positions:
        mv=p.get('market_value')
        if not finite(mv):missing.append(p.get('symbol'));continue
        change=(1+equity_shock)*(1+fx_shock)-1;loss=mv*change;stressed=mv+loss;pnl+=loss
        margin=abs(stressed)*(long_margin if stressed>=0 else short_margin);required+=margin
        rows.append({'symbol':p['symbol'],'market_value':mv,'scenario_pnl':loss,'stressed_value':stressed,'indicative_margin':margin})
    complete=not missing
    net=sum(r['market_value'] for r in rows)
    equity=cash+net+pnl
    return {'scenario_model':'linear','positions':rows,'scenario_pnl':pnl if complete else None,'known_position_pnl':pnl,
            'indicative_margin':required if complete else None,'known_position_margin':required,'cash_balance':cash,
            'stressed_equity':equity if complete else None,'equity_buffer_after_margin':equity-required if complete else None,
            'indicative_funding_gap':max(0,required-equity) if complete else None,
            'unpriced':missing,'coverage_complete':complete,
            'note':'Uniform user-specified price and FX shocks, multiplicative; all positions share the FX shock. Net cash/debit is unchanged by an unrealized mark-to-market move. Stressed equity = net cash + signed stressed position values. Margin rates are user assumptions, not broker requirements. Full-account totals are withheld if positions are unpriced. No cross-asset Greeks/full repricing, netting or collateral offsets are inferred.'}



def validate_forecasts(rows):
    from datetime import datetime
    valid=[];rejected=0;seen=set();duplicates=0
    for r in rows:
        try:
            issued=datetime.fromisoformat(r['issued_at'].replace('Z','+00:00'));actual_at=datetime.fromisoformat(r['actual_at'].replace('Z','+00:00'));trained=datetime.fromisoformat(r['trained_through'].replace('Z','+00:00'))
            p=r['probability'];actual=r['actual'];benchmark=r.get('benchmark_probability',.5)
            if not all(t.tzinfo is not None for t in (issued,actual_at,trained)) or not trained<=issued<actual_at or not finite(p) or not 0<=p<=1 or actual not in (0,1) or not finite(benchmark) or not 0<=benchmark<=1:raise ValueError()
            identity=(issued,actual_at,r.get('target',''),r.get('model',''),p,actual,benchmark)
            if identity in seen:
                duplicates+=1
                continue
            seen.add(identity)
            valid.append((issued,p,actual,benchmark))
        except (ValueError,KeyError,TypeError):rejected+=1
    valid.sort();n=len(valid)
    brier=sum((p-a)**2 for _,p,a,_ in valid)/n if n else None;baseline=sum((b-a)**2 for _,_,a,b in valid)/n if n else None
    bins=[]
    for lo in (0,.2,.4,.6,.8):
        group=[(p,a) for _,p,a,_ in valid if min(int(p*5),4)==round(lo*5)]
        bins.append({'lower':lo,'count':len(group),'predicted':sum(p for p,_ in group)/len(group) if group else None,'observed':sum(a for _,a in group)/len(group) if group else None})
    half=n//2
    drift=None if n<20 else {'earlier_brier':sum((p-a)**2 for _,p,a,_ in valid[:half])/half,'recent_brier':sum((p-a)**2 for _,p,a,_ in valid[half:])/(n-half)}
    return {'accepted':n,'rejected':rejected,'duplicates_excluded':duplicates,'brier':brier,'benchmark_brier':baseline,'skill':1-brier/baseline if baseline and brier is not None else None,'calibration':bins,'drift':drift,
            'evidence':'User-supplied timestamp-consistent rows; provenance is not independently verified. A 0.5 reference forecast is used when benchmark probabilities are absent. Fewer than 20 outcomes do not produce a drift comparison.'}

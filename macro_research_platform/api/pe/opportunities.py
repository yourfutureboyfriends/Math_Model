"""Evidence-led sourcing for direct equity, fund commitments and property.

Screening models are deliberately separate from the LBO capital structure. A source
link is a citation supplied by the analyst, not verified vendor data or an offer.
"""
from __future__ import annotations
import json
import math
import sqlite3
from datetime import date, datetime, timezone
from urllib.parse import urlparse

KINDS=('company','fund','property')
STAGES=('Research','Shortlist','Diligence','Investment committee','Passed')
# key, label, display unit; no invented financial defaults for a real opportunity.
FIELDS={
 'company': [('revenue','Current revenue','money'),('ebitda','Current EBITDA','money'),('pre_money','Pre-money equity value','money'),('investment','New primary equity','money'),('growth','Annual revenue growth','pct'),('exit_margin','Exit EBITDA margin','pct'),('exit_multiple','Exit EV / EBITDA','x'),('exit_net_debt','Exit net debt (cash negative)','money'),('dilution','Further ownership dilution','pct'),('years','Holding period','years'),('hurdle','Required annual return','pct')],
 'fund': [('paid_in','Paid-in capital, net LP basis','money'),('distributed','Distributions to LPs','money'),('nav','Residual NAV, net LP basis','money'),('commitment','Total commitment','money'),('unfunded','Remaining unfunded commitment','money'),('liquid_reserve','Liquid reserve for calls','money'),('price','Listed share price, currency units','money'),('nav_per_share','NAV/share, same currency units','money'),('nav_haircut','NAV downside haircut','pct'),('management_fee','Annual management fee','pct'),('carry','Carried interest','pct'),('minimum_ticket','Minimum commitment','money'),('budget','Available investment budget','money'),('vintage','Fund vintage','year')],
 'property': [('purchase','Property / land purchase price','money'),('acquisition_costs','Taxes, legal and acquisition costs','money'),('works','Hard / refurbishment costs','money'),('soft_costs','Design, planning and other soft costs','money'),('contingency','Contingency on hard + soft costs','pct'),('annual_rent','Gross annual rent at full occupancy','money'),('vacancy','Vacancy / non-collection','pct'),('opex','Annual landlord operating costs','money'),('maintenance','Annual capital reserve','money'),('rent_growth','Annual rent growth','pct'),('ltv','Loan / purchase price','pct'),('interest','Annual interest-only loan rate','pct'),('exit_yield','Exit capitalisation rate','pct'),('sale_cost','Selling costs / exit value','pct'),('years','Hold / development period','years'),('gdv','Development gross sale value','money'),('profit_target','Required development profit on cost','pct'),('hurdle','Required annual return','pct')]
}
REQUIRED={
 'company':['revenue','ebitda','pre_money','investment','growth','exit_margin','exit_multiple','exit_net_debt','dilution','years','hurdle'],
 'fund':[],
 'property':['purchase','acquisition_costs','works','soft_costs','contingency','ltv','interest','sale_cost','years','hurdle']}
CHECKS={
 'company':['Accounts and quality of earnings','Customer concentration and retention','Management and ownership rights','Market competition and investment thesis','Capex, working capital and funding plan','Legal, tax and exit rights'],
 'fund':['Manager identity and regulatory record','Net track record by vintage and strategy','Realised distributions and NAV valuation policy','Fees, carry and subscription line effects','Team stability, GP commitment and governance','Eligibility, liquidity and unfunded obligations'],
 'property':['Title, tenure and legal access','Planning permission and permitted use','Comparable sale and rental evidence','Building condition, utilities and survey','Flood, contamination and environmental risks','Local tax, tenancy and financing terms']}


def catalogue():
    return {'fields':FIELDS,'stages':STAGES,'checks':CHECKS,'markets':['United States','Canada','United Kingdom','Europe','Japan','Australia','New Zealand','Singapore','Hong Kong'],
      'sources':[
       {'kind':'company','name':'Companies House — UK company filings','url':'https://find-and-update.company-information.service.gov.uk/','scope':'UK register; registration does not mean a business is for sale.'},
       {'kind':'company','name':'SEC EDGAR — company filings','url':'https://www.sec.gov/edgar/search/','scope':'US reporting companies; listed candidates are proxies, not private deal availability.'},
       {'kind':'company','name':'SEDAR+ — Canadian issuer filings','url':'https://www.sedarplus.ca/','scope':'Canada; financial and ownership diligence.'},
       {'kind':'fund','name':'AIC — listed investment company directory','url':'https://www.theaic.co.uk/','scope':'Filter private equity; an asset manager stock is not a fund interest.'},
       {'kind':'fund','name':'SEC Investment Adviser Public Disclosure','url':'https://adviserinfo.sec.gov/','scope':'Manager identity and Form ADV; no verified private-fund performance or subscription availability.'},
       {'kind':'fund','name':'ILPA manager due diligence framework','url':'https://ilpa.org/resources-tools/resource-library/due-diligence-questionnaire/','scope':'Request net, vintage-specific performance, governance and fees.'},
       {'kind':'property','name':'Savills international property search','url':'https://www.savills.com/find-a-property/','scope':'Residential, land and commercial listings; asking prices are not closed transactions.'},
       {'kind':'property','name':'JLL commercial property — Europe','url':'https://property.jll.eu/','scope':'Commercial property listings; verify availability and local planning.'},
       {'kind':'property','name':'JLL commercial property — US','url':'https://property.jll.com/','scope':'Commercial listing discovery; no automatic listings ingestion.'}],
      'fund_seeds':[{'name':'HgCapital Trust','symbol':'HGT.L','url':'https://www.hgcapitaltrust.com/','scope':'Listed PE exposure; no current valuation or recommendation.'},{'name':'Partners Group Private Equity Limited','symbol':'PEY.L','url':'https://www.partnersgroupprivateequitylimited.com/','scope':'Listed investment company with global private equity exposure; confirm share class and currency.'},{'name':'Pantheon International','symbol':'PIN.L','url':'https://www.pantheon-international.com/','scope':'Listed global private-equity investment trust; request latest reported NAV and commitments.'}],
      'methodology':[{'name':'ILPA DDQ','url':'https://ilpa.org/resources-tools/resource-library/due-diligence-questionnaire/'},{'name':'RICS residual valuation and comparable cross-check','url':'https://www.rics.org/content/rics/uk/en/journals/property-journal/apc-5-valuation-methods.html'}]}


def validate(kind,values):
    if kind not in KINDS:raise ValueError('Unknown opportunity type')
    allowed={x[0] for x in FIELDS[kind]}
    if set(values)-allowed:raise ValueError('Unrecognised financial input')
    for k,v in values.items():
        if v is None:continue
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1e16:raise ValueError(f'Invalid number: {k}')
        if k not in ('ebitda','exit_net_debt','growth','rent_growth') and v<0:raise ValueError(f'{k} cannot be negative')
        if k in ('growth','rent_growth') and not -.95<=v<=1:raise ValueError(f'{k} must be between -95% and 100%')
        if k in ('dilution','vacancy','contingency','sale_cost','profit_target','nav_haircut','management_fee','carry','exit_margin','ltv') and not 0<=v<=1:raise ValueError(f'{k} must be between 0% and 100%')
        if k in ('interest','exit_yield','hurdle') and not 0<=v<=1:raise ValueError(f'{k} must be between 0% and 100%')
        if k=='years' and (not 1<=v<=30 or int(v)!=v):raise ValueError('Holding period must be 1–30 whole years')
    return values


def _return(initial,terminal,years):
    return {'moic':terminal/initial,'irr':(terminal/initial)**(1/years)-1 if terminal>0 else -1.0}


def analyse(kind,values,subtype='',as_of=None,nav_date=None,checks=None):
    v=validate(kind,values);warnings=[];metrics={};cases=[];flows=[];breakdown=[]
    subtypes={'company':('growth','control'),'fund':('listed','private'),'property':('residential','commercial','land','development')}
    if subtype not in subtypes[kind]:raise ValueError('Choose a valid investment type')
    if set(checks or [])-set(CHECKS[kind]):raise ValueError('Unknown diligence check')
    if nav_date and date.fromisoformat(nav_date)>date.today():raise ValueError('NAV date cannot be in the future')
    required=REQUIRED[kind][:]
    if kind=='property':
        required+=['gdv','profit_target'] if subtype in ('land','development') else ['annual_rent','vacancy','opex','maintenance','rent_growth','exit_yield']
    missing=[k for k in required if v.get(k) is None]
    today=date.today()
    if not as_of:warnings.append('Financial evidence is undated.')
    else:
        d=date.fromisoformat(as_of)
        if d>today:raise ValueError('Evidence date cannot be in the future')
        if (today-d).days>180:warnings.append('Financial evidence is more than 180 days old; refresh before comparing.')
    if missing:return {'metrics':{},'cases':[],'cashflows':[],'breakdown':[],'missing':missing,'warnings':warnings,'status':'Incomplete inputs','reviewed':len(checks or []),'total_checks':len(CHECKS[kind])}
    if kind=='company':
        if v['pre_money']<=0 or v['investment']<=0 or v['revenue']<=0 or v['exit_multiple']<=0:raise ValueError('Revenue, entry valuation, investment and exit multiple must be positive')
        stake=v['investment']/(v['pre_money']+v['investment']);years=int(v['years'])
        for label,growth,mult in [('Downside',max(-.95,v['growth']-.03),v['exit_multiple']*.8),('Base',v['growth'],v['exit_multiple']),('Upside',min(1,v['growth']+.03),v['exit_multiple']*1.2)]:
            revenue=v['revenue']*(1+growth)**years;ev=revenue*v['exit_margin']*mult
            proceeds=max(0,ev-v['exit_net_debt'])*stake*(1-v['dilution'])
            cases.append({'case':label,**_return(v['investment'],proceeds,years),'exit_equity_proceeds':proceeds})
        base=cases[1];metrics={**base,'entry_ownership':stake,'exit_ownership':stake*(1-v['dilution']),'current_margin':v['ebitda']/v['revenue'],'required_proceeds':v['investment']*(1+v['hurdle'])**years,'hurdle_met':base['irr']>=v['hurdle']}
        breakdown=['Post-money ownership = primary investment / (pre-money equity value + primary investment).','Exit revenue = current revenue × (1 + annual growth)^years.','Exit enterprise value = exit revenue × exit EBITDA margin × exit EV/EBITDA.','Equity proceeds = max(0, exit EV − exit net debt) × initial ownership × (1 − further dilution).','Annual return = (proceeds / primary investment)^(1/years) − 1. No interim distributions, follow-on investments or preference waterfall.']
        warnings+=['Growth-equity screening case, not a negotiated term sheet. Check liquidation preferences, rights, cash burn and future funding.','Downside/upside shift growth ±3 percentage points and exit multiple ±20%; these are stress assumptions, not forecasts.']
    elif kind=='fund':
        paid=v.get('paid_in');dist=v.get('distributed');nav=v.get('nav')
        if paid is not None and paid>0 and dist is not None and nav is not None:metrics.update(dpi=dist/paid,rvpi=nav/paid,tvpi=(dist+nav)/paid,realised_share=dist/(dist+nav) if dist+nav else None)
        else:warnings.append('Enter paid-in capital, distributions and residual NAV on the same net LP basis for performance multiples.')
        if all(v.get(k) is not None for k in ('unfunded','liquid_reserve')):metrics['call_coverage']=v['liquid_reserve']/v['unfunded'] if v['unfunded']>0 else None
        if all(v.get(k) is not None for k in ('minimum_ticket','budget')):metrics['ticket_fits']=v['budget']>=v['minimum_ticket']
        if subtype=='listed':
            price=v.get('price');nps=v.get('nav_per_share')
            if price is not None and nps is not None and nps>0:
                metrics['discount']=1-price/nps
                haircut=v.get('nav_haircut')
                if haircut is not None:metrics['stressed_discount']=1-price/(nps*(1-haircut)) if haircut<1 else None
            if not nav_date:warnings.append('NAV date is required to interpret the listed discount.')
            elif as_of:
                nd=date.fromisoformat(nav_date)
                if nd>today:raise ValueError('NAV date cannot be in the future')
                if abs((date.fromisoformat(as_of)-nd).days)>90:warnings.append('Price / NAV dates differ by more than 90 days; the discount may be stale.')
            warnings.append('Share price and NAV/share must use the same currency and units; convert pence/cents and any FX before entry. Discount is not a fair-value conclusion.')
        else:warnings.append('Private fund availability, investor eligibility, minimum commitment and terms require confirmation from the manager.')
        if v.get('commitment') is not None and paid is not None and paid>v['commitment']:warnings.append('Paid-in exceeds commitment; verify recallable distributions, fees and denominator definitions.')
        breakdown=['DPI = distributions / paid-in; RVPI = residual NAV / paid-in; TVPI = (distributions + NAV) / paid-in.','Listed discount = 1 − share price / NAV per share. Stressed NAV = NAV per share × (1 − haircut).','Call coverage = liquid reserve / unfunded commitments. Fee terms are recorded, not deducted a second time from net LP metrics.']
        warnings.append('Compare net returns within vintage, strategy, currency and valuation date. No manager ranking from IRR alone; use Fund performance for dated cash-flow XIRR and PME.')
    else:
        if v['purchase']<=0:raise ValueError('Purchase price must be positive')
        years=int(v['years']);loan=v['purchase']*v['ltv'];works=(v['works']+v['soft_costs'])*(1+v['contingency']);cost=v['purchase']+v['acquisition_costs']+works;initial=cost-loan
        if initial<=0:raise ValueError('Initial equity must be positive')
        annual_interest=loan*v['interest'];dev=subtype in ('land','development')
        if not dev and v['exit_yield']<=0:raise ValueError('Exit capitalisation rate must be positive')
        def scenario(sale_factor=1,cost_factor=1):
            equity=v['purchase']+v['acquisition_costs']+works*cost_factor-loan
            annual=[]
            for y in range(1,years+1):
                noi=0 if dev else (v['annual_rent']*(1-v['vacancy'])-v['opex'])*(1+v['rent_growth'])**(y-1)
                annual.append(noi-(0 if dev else v['maintenance']*(1+v['rent_growth'])**(y-1))-annual_interest)
            next_noi=0 if dev else (v['annual_rent']*(1-v['vacancy'])-v['opex'])*(1+v['rent_growth'])**years
            sale=(v['gdv'] if dev else max(0,next_noi/v['exit_yield']))*sale_factor
            annual[-1]+=sale*(1-v['sale_cost'])-loan
            # Full recourse equity cash flows: a shortfall is an additional equity contribution.
            from api.pe.fundmath import xirr
            base=date(2020,1,1);dated=[{'date':base.isoformat(),'amount':-equity}]+[{'date':base.replace(year=base.year+i+1).isoformat(),'amount':a} for i,a in enumerate(annual)]
            signs=[1 if f['amount']>0 else -1 for f in dated if f['amount']!=0]
            changes=sum(a!=b for a,b in zip(signs,signs[1:]))
            irr=xirr(dated) if changes==1 else None;invested=equity+sum(-a for a in annual if a<0);returned=sum(a for a in annual if a>0)
            return {'irr':irr,'moic':returned/invested,'profit':sum(annual)-equity,'initial_equity':equity,'sale_value':sale,'cashflows':[{'year':0,'equity_cashflow':-equity}]+[{'year':i+1,'equity_cashflow':a} for i,a in enumerate(annual)]}
        for label,sale,cost_factor in [('Downside',.9,1.1),('Base',1,1),('Upside',1.1,1)]:
            cases.append({'case':label,**scenario(sale,cost_factor)})
        base=cases[1];flows=base.pop('cashflows');metrics={k:value for k,value in base.items() if k!='case'};metrics.update(total_cost=cost,loan=loan,hurdle_met=metrics['irr'] is not None and metrics['irr']>=v['hurdle'])
        if dev:
            profit=v['gdv']*(1-v['sale_cost'])-cost-annual_interest*years
            metrics['profit_on_cost']=profit/(cost+annual_interest*years)
            # Static unlevered residual: land tax/fees are fixed supplied amounts.
            metrics['residual_land_value']=v['gdv']*(1-v['sale_cost'])/(1+v['profit_target'])-works-v['acquisition_costs']
            warnings.append('Development is a conservative upfront-cost screen with annual interest paid by equity and a single completion sale. Residual land value is unlevered, before finance, using the separate profit-on-cost target; cross-check local land transactions.')
        else:
            noi=v['annual_rent']*(1-v['vacancy'])-v['opex'];metrics.update(noi=noi,cap_rate=noi/v['purchase'],dscr=noi/annual_interest if annual_interest>0 else None,cash_yield=(noi-v['maintenance']-annual_interest)/initial)
        breakdown=['Total cost = purchase + acquisition costs + (hard + soft costs) × (1 + contingency).','Loan = purchase × LTV; initial equity = total cost − loan. Interest-only, fixed principal, no refinancing.','Rental NOI = rent × (1 − vacancy) − landlord operating costs; capital reserve is below NOI.','Rental exit value uses next-year NOI / exit cap rate; development uses entered gross development value. Deduct selling costs and repay loan.','Equity IRR uses dated annual cash flows; negative operating cash flow is additional invested equity. MOIC = positive receipts / total equity contributions.']
        if metrics['irr'] is None:warnings.append('No unique conventional equity IRR is available; review all cash flows, including additional contributions and exit repayment.')
        warnings+=['Before investor income/capital-gains tax and currency movements. Enter local acquisition taxes and irrecoverable VAT/GST in costs.','Downside: sale value −10%, works +10%. Upside: sale value +10%. Planning permission and actual availability are not inferred.']
    return {'metrics':metrics,'cases':cases,'cashflows':flows,'breakdown':breakdown,'missing':missing,'warnings':warnings,'status':'Screen calculated' if metrics else 'More evidence required','reviewed':len(checks or []),'total_checks':len(CHECKS[kind])}


def _conn():
    from api import funds
    c=sqlite3.connect(funds.db_path(),timeout=10);c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS pe_opportunities(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, body TEXT NOT NULL, analysis TEXT NOT NULL, owner TEXT, updated_at TEXT)')
    return c


def save(owner,body,opportunity_id=None):
    body=dict(body)
    if body['stage'] not in STAGES:raise ValueError('Unknown opportunity stage')
    if not body['name'].strip():raise ValueError('Opportunity name is required')
    if body.get('source_url'):
        u=urlparse(body['source_url'])
        if u.scheme not in ('http','https') or not u.netloc or u.username or u.password:raise ValueError('Use a public http/https source link without credentials')
    allowed=CHECKS.get(body['kind'],[])
    if set(body.get('checks',[]))-set(allowed):raise ValueError('Unknown diligence check')
    result=analyse(body['kind'],body['values'],body.get('subtype',''),body.get('as_of'),body.get('nav_date'),body.get('checks'))
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    with _conn() as c:
        if opportunity_id is None:
            opportunity_id=c.execute('INSERT INTO pe_opportunities(kind,name,body,analysis,owner,updated_at) VALUES(?,?,?,?,?,?)',(body['kind'],body['name'],json.dumps(body,allow_nan=False),json.dumps(result,allow_nan=False),owner,now)).lastrowid
        else:
            if not c.execute('SELECT id FROM pe_opportunities WHERE id=?',(opportunity_id,)).fetchone():raise LookupError('Opportunity not found')
            c.execute('UPDATE pe_opportunities SET kind=?,name=?,body=?,analysis=?,owner=?,updated_at=? WHERE id=?',(body['kind'],body['name'],json.dumps(body,allow_nan=False),json.dumps(result,allow_nan=False),owner,now,opportunity_id))
    return {'id':opportunity_id,**body,'analysis':result,'owner':owner,'updated_at':now}


def list_opportunities(kind):
    if kind not in KINDS:raise ValueError('Unknown opportunity type')
    with _conn() as c:
        rows=c.execute('SELECT * FROM pe_opportunities WHERE kind=? ORDER BY updated_at DESC',(kind,)).fetchall()
    return [{'id':r['id'],**json.loads(r['body']),'analysis':json.loads(r['analysis']),'owner':r['owner'],'updated_at':r['updated_at']} for r in rows]

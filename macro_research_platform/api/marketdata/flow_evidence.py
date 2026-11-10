"""Evidence-led capital signals. Disclosure records and estimates are never labelled live cash transfers."""
from datetime import date,timedelta,datetime,timezone
import math
import xml.etree.ElementTree as ET


def parse_form4(content, accession, filed, url, form='4'):
    root=ET.fromstring(content)
    for element in root.iter():element.tag=element.tag.split('}')[-1]
    owner=root.findtext('.//reportingOwner/reportingOwnerId/rptOwnerName') or ''
    owner_cik=root.findtext('.//reportingOwner/reportingOwnerId/rptOwnerCik')
    rel=root.find('.//reportingOwner/reportingOwnerRelationship');roles=[]
    if rel is not None:
        for flag,label in [('isDirector','Director'),('isOfficer',rel.findtext('officerTitle') or 'Officer'),('isTenPercentOwner','10% owner')]:
            if (rel.findtext(flag) or '').strip().lower() in ('1','true'):roles.append(label)
    flag=(root.findtext('aff10b5One') or '').strip().lower()
    planned=True if flag in ('1','true') else False if flag in ('0','false') else None
    def number(text):
        try:v=float(text);return v if math.isfinite(v) else None
        except (ValueError,TypeError):return None
    footnotes={n.attrib.get('id'):''.join(n.itertext()).strip() for n in root.findall('.//footnote')}
    rows=[]
    for index,t in enumerate(root.findall('.//nonDerivativeTable/nonDerivativeTransaction')):
        sh=number(t.findtext('transactionAmounts/transactionShares/value'));px=number(t.findtext('transactionAmounts/transactionPricePerShare/value'))
        ad=t.findtext('transactionAmounts/transactionAcquiredDisposedCode/value');code=t.findtext('transactionCoding/transactionCode') or ''
        rows.append({'accession':accession,'row':index,'form':form,'amendment':form=='4/A','filed':filed,'date':t.findtext('transactionDate/value'),'insider':owner.title(),'owner_cik':owner_cik,'role':', '.join(roles) or '—','security':t.findtext('securityTitle/value'),'code':code,'shares':sh,'price':px,'value':sh*px if sh is not None and px is not None else None,'direction':'buy' if ad=='A' else 'sell' if ad=='D' else None,'owned_after':number(t.findtext('postTransactionAmounts/sharesOwnedFollowingTransaction/value')),'ownership':t.findtext('ownershipNature/directOrIndirectOwnership/value'),'plan_10b5_1':planned,'plan_basis':'Filing checkbox; filing-level indicator, not independent transaction-level verification' if planned is not None else 'Checkbox unavailable; plan status unknown','footnotes':[footnotes[n.attrib.get('id')] for n in t.findall('.//footnoteId') if n.attrib.get('id') in footnotes],'url':url})
    return rows


def insider_summary(payload, days=30, today=None):
    today=today or date.today();cutoff=today-timedelta(days=days-1);accepted=[];excluded=0;seen=set()
    group=lambda r:(r.get('owner_cik') or r.get('insider'),r.get('date'),r.get('security'))
    amended=set()
    for r in payload.get('transactions',[]):
        if not (r.get('amendment') or r.get('form')=='4/A'):continue
        try:known=date.fromisoformat(r.get('filed') or '')<=today
        except (ValueError,TypeError):continue
        if known:amended.add(group(r))
    for r in payload.get('transactions',[]):
        try:day=date.fromisoformat(r.get('date') or '');filed=date.fromisoformat(r.get('filed') or '')
        except (ValueError,TypeError):excluded+=1;continue
        if not cutoff<=day<=today or filed>today or filed<day:continue
        if group(r) in amended:excluded+=1;continue
        if r.get('code') not in ('P','S'):excluded+=1;continue
        if (r['code']=='P' and r.get('direction')!='buy') or (r['code']=='S' and r.get('direction')!='sell'):excluded+=1;continue
        key=tuple(r.get(k) for k in ('owner_cik','insider','date','code','security','shares','price','owned_after','ownership'))
        if key in seen:excluded+=1;continue
        seen.add(key);accepted.append(r)
    buys=[r for r in accepted if r['code']=='P'];sales=[r for r in accepted if r['code']=='S']
    value=lambda rows:sum(r['value'] for r in rows if isinstance(r.get('value'),(int,float)) and math.isfinite(r['value']) and r['value']>=0)
    buyers={r.get('owner_cik') or r.get('insider') for r in buys if r.get('owner_cik') or r.get('insider')}
    return {'window_days':days,'as_of':today.isoformat(),'purchase_usd_known':value(buys),'sale_usd_known':value(sales),'purchase_transactions':len(buys),'sale_transactions':len(sales),'distinct_reporting_buyers':len(buyers),'multiple_buyers':len(buyers)>=2,'planned_transactions':sum(r.get('plan_10b5_1') is True for r in accepted),'unknown_plan_transactions':sum(r.get('plan_10b5_1') is None for r in accepted),'missing_value_transactions':sum(r.get('value') is None for r in accepted),'excluded_rows':excluded,'amendment_affected_groups':len(amended),'transactions':accepted,'coverage':'partial' if payload.get('failed_filings') else 'sampled_recent_filings','filings_requested':payload.get('filings_requested'),'filings_parsed':payload.get('filings_parsed'),'oldest_filing':min((r['filed'] for r in payload.get('transactions',[]) if r.get('filed')),default=None),'latest_filing':max((r['filed'] for r in payload.get('transactions',[]) if r.get('filed')),default=None),'note':'P/S include open-market or private transactions. Amounts are disclosed transaction values, not company cash inflows. Amendment-affected owner/date/security groups and duplicate rows are excluded from this screen, not reconciled into an authoritative ownership ledger. Multiple reporting owners may be related. Unknown plan status does not mean discretionary. Sampled filings are not an exhaustive market scan.'}


def estimate_etf_flows(series, today=None):
    """Sum interval share changes × interval valuation price; never mix with price/volume pressure."""
    today=today or date.today();records=[]
    for key,row in sorted(series):
        try:
            d=date.fromisoformat(key);shares,px=float(row[0]),float(row[1])
            if d<=today and math.isfinite(shares) and math.isfinite(px) and shares>0 and px>0:records.append((d,shares,px))
        except (ValueError,TypeError,IndexError):continue
    if len(records)<2:return {'quality':'insufficient_history','note':'Two valid share-count snapshots are needed; price/volume pressure is not substituted.'}
    end=records[-1];result={'as_of':end[0].isoformat(),'aum_usd':end[1]*end[2],'since':records[0][0].isoformat(),'quality':'estimated','valuation_basis':'Issuance may be in-kind, not cash. Snapshot valuation price (NAV where available, otherwise market-price proxy); share-count effective dates are not independently verified.'}
    if (today-end[0]).days>7:return {**result,'quality':'stale','note':'Latest snapshot is more than seven calendar days old; no current flow estimate.'}
    def window(start):
        rows=[r for r in records if r[0]>=start[0]]
        if any(abs(b[1]/a[1]-1)>=.4 for a,b in zip(rows,rows[1:])):return None
        return sum((b[1]-a[1])*b[2] for a,b in zip(rows,rows[1:]))
    last=window(records[-2]);result.update(last_usd=last,last_dates=[records[-2][0].isoformat(),end[0].isoformat()])
    baseline=[r for r in records if r[0]<=end[0]-timedelta(days=7)]
    if baseline and (end[0]-baseline[-1][0]).days<=10:
        start=baseline[-1];result.update(week_usd=window(start),week_start=start[0].isoformat(),week_end=end[0].isoformat(),week_days=(end[0]-start[0]).days,baseline_aum_usd=start[1]*start[2])
    if last is None or ('week_usd' in result and result['week_usd'] is None):result.update(quality='review_required',note='Large share-count discontinuity: possible split, data revision or exceptional issuance. Flow amount withheld pending verification.')
    return result


def disclosures(symbol):
    from api.marketdata import extras
    p=extras.insiders(symbol,20)
    return {'symbol':p['symbol'],'company':p.get('company'),'insiders':insider_summary(p),'filing_transactions':p.get('transactions',[]),'failed_filings':p.get('failed_filings',[]),'source':p.get('source'),'retrieved_at':p.get('fetched_at'),'assembled_at':datetime.now(timezone.utc).isoformat(),'delay':'SEC Form 4 disclosures are generally due within two business days; late filings, amendments and coverage gaps occur. Not a live insider-money feed.'}

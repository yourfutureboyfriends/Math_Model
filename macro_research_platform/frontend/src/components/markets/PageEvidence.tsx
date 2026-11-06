import { findFunction, type MktFunction } from './functions';
const GROUP_NOTES: Record<MktFunction['group'], string> = {
 'Security':'Check the listing currency, reporting currency, fiscal period and share basis before comparing companies. A quote timestamp does not date financial statements.',
 'Markets':'Compare matched trading dates, currency bases and eligible universes. Missing quotes are unavailable observations, not unchanged prices or zero activity.',
 'Rates & FX':'Check quote direction, percent versus basis points, tenor and observation date. Indicative curves and calculated forwards are not executable dealer prices.',
 'Economy & policy':'Distinguish observation period, release date and revision vintage. Current revised series cannot establish what was known at the time of a backtest.',
 'Alternative data':'Coverage and reporting delays determine what can be inferred. Observed activity and model proxies do not establish complete real-world flows.',
 'Research':'Check sample coverage, event dates and publication dates. Rankings and model outputs depend on their inputs and are research screens.',
 'My tools':'User entries, saved captures and model responses have different provenance from provider observations. Saved views do not update their historical inputs automatically.',
};
const NOTES: Record<string,string> = {};
function note(codes:string,text:string){for(const code of codes.split(' '))NOTES[code]=text;}
note('DCF VAL','Inspect cash-flow basis, currency-matched discount rates, reinvestment, dilution and terminal assumptions. Compare scenarios and reverse expectations; valuation is a conditional model output.');
note('GE WPE RV EQS','Negative or missing earnings do not create meaningful P/E multiples. Compare trailing versus forward EPS, accounting periods, currency and sector composition; inspect the covered sample.');
note('OMON OVDV OSA OVME PROB IMPM UOA','Inspect bid/ask spreads, quote age and open interest date. Greeks and implied probabilities are model estimates; option-implied distributions are risk-neutral rather than forecasts of actual outcomes.');
note('SI BORROW DARK','Short-sale volume is trading activity, not outstanding short interest. Off-exchange reports and short-interest snapshots have separate dates; public observations do not establish current borrow availability.');
note('INSD MGMT HDS 13F','Use trade, filing and reporting dates separately. Insider transactions can be planned or private; institutional holdings are delayed snapshots and do not reveal all shorts or an actual purchase ledger.');
note('ECO ECST ECOS ECFC NOW','Use release-time vintages for historical signals. A trend-based surprise differs from actual-minus-consensus. Revisions and missing releases can change apparent model skill.');
note('COT','CFTC reports generally describe Tuesday positions published Friday; holidays change the schedule. Net positioning is an outstanding exposure, not a live cash-flow measure.');
note('SHIP','AIS is a receiver sample. Historical grid cells are approximate and delayed. Reported at-anchor status does not prove a berth queue, and draft or typical capacity does not establish actual cargo.');
note('FLY','Aircraft counts depend on receiver coverage. Last position time differs from last radio contact. Optional projected coordinates, usual callsign routes and typical capacity are estimates, not confirmed location, itinerary or load.');
note('CORR BETA FAC','Inspect aligned observation counts, return intervals and currency bases. Cross-market closing times affect correlations; missing observations must not be silently treated as zero returns.');
note('COMP TRA MRR','Compare the same date window and dividend-adjustment basis. Local-currency performance differs from investor-currency performance. A return/volatility ratio is not a cash-rate-adjusted Sharpe ratio.');
note('PORT AWP HGRL','Risk depends on return alignment, weights, FX and available history. Historical volatility/correlation and VaR are conditional estimates; missing holdings can understate exposure.');
note('SEAS TECH RRG EDGE ALPHA PROOF','Inspect sample size, benchmark, observation cutoff and out-of-sample results. Many tested rules inflate apparent significance; costs, survivorship and data revisions matter.');
note('CDSX CDSA CRED TRACE','Distinguish transactions, spread indices and dealer quotes. Reported bond/CDS activity is delayed and incomplete; a proxy spread is not an executable single-name CDS price.');
note('ETFA FSRC FLOW','Match price, NAV, shares-outstanding dates and currency. Issuance estimates and ETF pressure are different quantities; creations can be in-kind, so estimates are not observed cash transfers.');
note('WIRP FOMC FWCV SWAP FRD','Check day-count, compounding and interpolation assumptions. Futures-implied rates include premia; model-implied probabilities depend on the assumed policy-rate outcomes.');
note('FA EM ERN EARN PGEO DDIS CRPR','Check fiscal versus calendar periods, units, restatements and GAAP versus adjusted fields. Synthetic credit assessments are model outputs, not agency ratings.');
note('MAP WEI RMON CTRY IMAP MOST BRDT IMOV MEMB','Check exchange/session time and constituent coverage. An incomplete sample can bias movers, breadth, aggregate valuation and country comparisons. Exchange pins are approximate city locations.');
note('N CN TRAN DS CF AI','Read the original source and publication/filing date. Search extracts and generated summaries may omit qualifications; confirm numerical claims against the linked document.');
note('PRED','Prices are venue-specific, contract-specific observations with fees, liquidity and resolution rules. They are not objective probabilities or a cross-venue risk-free arbitrage guarantee.');
note('WETR EIA QUAK','Check observed versus forecast values, reporting period, units and geographic coverage. Physical observations do not by themselves establish a security-price effect.');
export function pageEvidence(code:string):string {
 const f=findFunction(code);return NOTES[f?.code ?? code] ?? (f ? GROUP_NOTES[f.group] : GROUP_NOTES.Markets);
}
/** `inline`: a small pill in the page's data line (SourcesBar) that opens to the full note, instead of its own row. */
export function PageEvidence({code,compact=false,inline=false}:{code:string;compact?:boolean;inline?:boolean}) {
 if(compact)return null;
 return <details className={inline?'rounded-full open:basis-full open:rounded-lg border border-border-subtle bg-surface-1/60 px-2 py-0.5 open:px-3 open:py-2 text-[10px] open:text-[11px]':'rounded-lg border border-border-subtle bg-surface-1/60 px-3 py-2 mb-3 text-[11px]'}>
  <summary className="cursor-pointer text-text-secondary">Using this page · data basis & interpretation</summary>
  <p className="text-text-secondary mt-2 leading-relaxed">{pageEvidence(code)}</p>
  <p className="text-text-tertiary mt-2">Open “Source details & freshness” for returned provider metadata and raw responses. Unknown metadata remains unknown; retrieval time is not observation time.</p>
 </details>;
}

import { ExpectationsPanel } from './ExpectationsPanel';
import { ValuationCapture } from './ValuationCapture';
// VAL: the valuation hub. Everything is filled in automatically (DCF or excess-return model, dividend
// model, peer multiples, analysts, a 24-month outlook); the user moves only the handful of drivers that
// actually change the answer, sees bear / base / bull at once, and a blended fair value with its range.
import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { ErrorBox, fmtBig, fmtPct, fmtPrice, Loading, Panel, useJSON } from './shared';
import { PriceOutlook } from './SecurityFunctions';

const enc = encodeURIComponent;
type Driver = { key: string; label: string; short?: string; hint: string; min: number; max: number; step: number; pct: boolean };
type Vals = Record<string, number | undefined>;

const FCFF_DRIVERS: Driver[] = [
  { key: 'growth', label: 'Revenue growth, next 3 years', short: 'Growth y1–3', hint: 'The biggest lever for growth companies. Default: analyst consensus.', min: -0.2, max: 0.6, step: 0.005, pct: true },
  { key: 'target_margin', label: 'Long-run operating margin', short: 'Margin', hint: 'Where profitability settles by the end of the explicit forecast.', min: -0.1, max: 0.7, step: 0.005, pct: true },
  { key: 'discount', label: 'Discount rate (WACC)', short: 'Discount rate', hint: 'The return investors require. +1 point typically cuts value 10–20%.', min: 0.03, max: 0.18, step: 0.0025, pct: true },
  { key: 'fade_years', label: 'Years of excess returns after the forecast (moat)', short: 'Moat years', hint: 'Morningstar: about 1 (no moat), 10 (narrow), 20 (wide).', min: 0, max: 30, step: 1, pct: false },
];
const FCFF_DRIVERS_2STAGE: Driver[] = [
  ...FCFF_DRIVERS.slice(0, 3),
  { key: 'terminal_growth', label: 'Growth forever after the forecast', short: 'Growth ∞', hint: 'Keep at or below the risk-free rate.', min: 0, max: 0.06, step: 0.0025, pct: true },
];
type Opts = { erp_basis?: 'normalized' | 'market_implied'; normalized_erp?: number; method?: 'three_stage' | 'two_stage'; ke_method?: 'capm' | 'building_block' };
const ER_DRIVERS: Driver[] = [
  { key: 'roe', label: 'Return on equity now', short: 'ROE', hint: 'Profit per unit of book equity — the engine of a bank’s value.', min: -0.1, max: 0.4, step: 0.005, pct: true },
  { key: 'terminal_roe', label: 'Long-run ROE', short: 'Long-run ROE', hint: 'Where returns settle. Above the cost of equity = worth more than book.', min: 0.02, max: 0.35, step: 0.005, pct: true },
  { key: 'discount', label: 'Cost of equity', short: 'Discount rate', hint: 'The return shareholders require.', min: 0.04, max: 0.2, step: 0.0025, pct: true },
  { key: 'terminal_growth', label: 'Growth forever', short: 'Growth ∞', hint: 'Keep at or below the risk-free rate.', min: 0, max: 0.06, step: 0.0025, pct: true },
];
const DDM_DRIVERS: Driver[] = [
  { key: 'growth', label: 'Dividend growth, next 5 years', short: 'Growth y1–3', hint: 'Default: the lower of ROE × retention and 5-year dividend growth.', min: -0.1, max: 0.2, step: 0.0025, pct: true },
  { key: 'terminal_growth', label: 'Dividend growth forever', short: 'Growth ∞', hint: 'Capped by the risk-free rate and 2% real + inflation.', min: 0, max: 0.06, step: 0.0025, pct: true },
  { key: 'discount', label: 'Cost of equity', short: 'Discount rate', hint: 'The return shareholders require.', min: 0.04, max: 0.18, step: 0.0025, pct: true },
];

function defaultsFor(d: any): Vals {
  if (!d) return {};
  const a = d.valuation.assumptions, w = d.valuation.wacc ?? {};
  if (d.model === 'excess_return') return { roe: a.roe_now, terminal_roe: a.roe_terminal, discount: a.cost_of_equity, terminal_growth: a.terminal_growth, working_capital_ratio: a.working_capital_ratio };
  if (d.model === 'ddm') return { growth: a.growth, terminal_growth: a.terminal_growth, discount: a.cost_of_equity };
  return a.method === 'three_stage'
    ? { growth: a.growth, target_margin: a.target_margin, discount: w.wacc, fade_years: a.fade_years, working_capital_ratio: a.working_capital_ratio }
    : { growth: a.growth, target_margin: a.target_margin, discount: w.wacc, terminal_growth: a.terminal_growth, working_capital_ratio: a.working_capital_ratio };
}

function urlFor(symbol: string, model: string, v: Vals, o: Opts = {}) {
  const p = new URLSearchParams({ model });
  if (o.erp_basis) p.set('erp_basis', o.erp_basis);
  if (o.normalized_erp != null) p.set('normalized_erp', String(o.normalized_erp));
  if (o.method) p.set('method', o.method);
  if (o.ke_method) p.set('ke_method', o.ke_method);
  for (const [k, x] of Object.entries(v)) if (x != null && Number.isFinite(x)) p.set(k, String(Math.round(x * 1e5) / 1e5));
  return `/api/v1/mkt/dcf/${enc(symbol)}?${p}`;
}

/** Bear / bull: the operating drivers pushed each way from wherever they are now (defaults + the user's
 *  overrides), and the required return moved through the equity risk premium (±0.75 point) so the
 *  discount rate keeps its normal path to stable growth — unless the user fixed the rate by hand. */
function shift(model: string, eff: Vals, ov: Vals, erp0: number, dir: -1 | 1, fixedRate = false): Vals {
  const out: Vals = { ...ov };
  if (ov.discount != null || fixedRate) out.discount = Math.max(0.03, (ov.discount ?? eff.discount ?? 0.08) - 0.01 * dir);
  else out.erp = Math.max(0.01, erp0 - 0.0075 * dir);
  if (model === 'excess_return') {
    out.roe = (eff.roe ?? 0.1) + 0.03 * dir;
    out.terminal_roe = Math.max(0.03, (eff.terminal_roe ?? 0.1) + 0.02 * dir);
  } else {
    out.growth = (eff.growth ?? 0.05) + 0.03 * dir;
    out.target_margin = (eff.target_margin ?? 0.1) * (dir > 0 ? 1.1 : 0.85);
  }
  return out;
}

function useDebounced<T>(v: T, ms = 450): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

const pc = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);

// Responses from the previous symbol or assumption URL must not enter a new blend.
function useValuationJSON<T>(url: string | null) {
  const result = useJSON<T>(url);
  return { ...result, data: result.current ? result.data : null,
    loading: result.loading || (!!url && !result.current && !result.error) };
}

export function ValuationHub({ symbol, onGo }: { symbol: string; onGo: (fn: string, s?: string) => void }) {
  const [optsKey, setOptsKey] = useState('');
  const base = useValuationJSON<any>(`/api/v1/mkt/dcf/${enc(symbol)}${optsKey}`);
  const rv = useValuationJSON<any>(`/api/v1/mkt/rv/${enc(symbol)}`);
  const primaryModel: string | null = base.data ? (base.data.model === 'ddm' ? (base.data.inputs.is_financial ? 'excess_return' : 'fcff') : base.data.model) : null;
  const hasDdm = !!(base.data?.ddm || base.data?.model === 'ddm');
  const [ov, setOv] = useState<Vals>({});           // primary-model overrides
  const [dv, setDv] = useState<Vals>({});           // dividend-model overrides
  const [hl, setHl] = useState(3);
  const [use, setUse] = useState({ primary: true, ddm: true, peers: false });
  const [opts, setOpts] = useState<Opts>({});      // valuation structure and cost-of-equity basis (server defaults when unset)
  useEffect(() => { setOv({}); setDv({}); }, [symbol]);
  useEffect(() => {
    const p = new URLSearchParams(); if (opts.method) p.set('method', opts.method); if (opts.ke_method) p.set('ke_method', opts.ke_method);
    if (opts.erp_basis) p.set('erp_basis', opts.erp_basis);
    if (opts.normalized_erp != null) p.set('normalized_erp', String(opts.normalized_erp));
    setOptsKey(p.toString() ? `?${p}` : '');
  }, [opts]);
  useEffect(() => { setOv({}); }, [opts.method, opts.ke_method]);

  // defaults: from the primary model's own response (fetch it explicitly when the server chose the DDM)
  const primDefaultsReq = useValuationJSON<any>(base.data && primaryModel && base.data.model !== primaryModel ? urlFor(symbol, primaryModel, {}, opts) : null);
  const primBase = base.data?.model === primaryModel ? base.data : primDefaultsReq.data;
  const ddmBaseReq = useValuationJSON<any>(base.data && hasDdm && base.data.model !== 'ddm' ? urlFor(symbol, 'ddm', {}, opts) : null);
  const ddmBase = base.data?.model === 'ddm' ? base.data : ddmBaseReq.data;
  const pDef = useMemo(() => defaultsFor(primBase), [primBase]);
  const dDef = useMemo(() => defaultsFor(ddmBase), [ddmBase]);
  const pVals: Vals = { ...pDef, ...ov }, dVals: Vals = { ...dDef, ...dv };
  const ovD = useDebounced(ov), dvD = useDebounced(dv);
  const pEff = { ...pDef, ...ovD };
  const erp0: number = primBase?.valuation?.wacc?.erp ?? primBase?.valuation?.assumptions?.erp ?? 0.045;
  const primUrl = primaryModel && primBase ? (Object.keys(ovD).length ? urlFor(symbol, primaryModel, ovD, opts) : null) : null;
  const prim = useValuationJSON<any>(primUrl);
  const primary = (Object.keys(ovD).length ? prim.data : primBase) ?? null;
  const bbKe = primBase?.valuation?.wacc?.ke_method === 'building_block';
  const bear = useValuationJSON<any>(primaryModel && primBase ? urlFor(symbol, primaryModel, shift(primaryModel, pEff, ovD, erp0, -1, bbKe), opts) : null);
  const bull = useValuationJSON<any>(primaryModel && primBase ? urlFor(symbol, primaryModel, shift(primaryModel, pEff, ovD, erp0, 1, bbKe), opts) : null);
  const ddmReq = useValuationJSON<any>(hasDdm && Object.keys(dvD).length ? urlFor(symbol, 'ddm', dvD, opts) : null);
  const ddm = (Object.keys(dvD).length ? ddmReq.data : ddmBase) ?? null;

  if (base.loading && !base.data) return <Loading label="Filling in the model — financials, cost of capital, peers, dividends…" />;
  if (base.error && !base.data) return <ErrorBox msg={base.error} />;
  if (!base.data || !primaryModel) return null;
  const inp = base.data.inputs;
  const price: number = inp.price;
  const ccy = inp.price_currency ?? inp.currency ?? '';
  const home = rv.data?.home_region;
  const imp = rv.data?.implied_price ?? {};
  const peerVals = ['forward_pe', 'pe', 'ev_ebitda'].map((k) => imp[k]?.[home] ?? imp[k]?.global).filter((x: any) => x != null && x > 0) as number[];
  const peer = peerVals.length ? [...peerVals].sort((a, b) => a - b)[Math.floor(peerVals.length / 2)] : null;
  const pv = primary?.valuation?.equity_negative ? null : primary?.valuation?.per_share;
  const dval = ddm?.valuation?.per_share;
  const ddmUseful = ddm && (ddm.valuation.dividend_yield ?? 0) >= 0.015;
  const parts: [string, number][] = [
    ...(use.primary && pv ? [[primaryModel === 'excess_return' ? 'Excess return' : 'DCF', pv] as [string, number]] : []),
    ...(use.ddm && dval && ddmUseful ? [['Dividend model', dval] as [string, number]] : []),
    ...(use.peers && peer ? [['Peers', peer] as [string, number]] : []),
  ];
  const fair = parts.length ? Math.exp(parts.reduce((a, [, x]) => a + Math.log(x), 0) / parts.length) : null;   // geometric mean
  const bv = bear.data?.valuation?.per_share, uv = bull.data?.valuation?.per_share;
  const spread = parts.length > 1 ? Math.max(...parts.map((p) => p[1])) / Math.min(...parts.map((p) => p[1])) : null;
  const conf = spread == null ? 'one method only' : spread < 1.35 ? 'methods agree' : spread < 2 ? 'methods differ' : 'methods disagree widely';
  const up = fair ? fair / price - 1 : null;
  // Morningstar's margin of safety: the discount needed to buy (and premium to sell) widens with uncertainty
  const unc = base.data.uncertainty ?? null;
  const buyBelow: number = unc?.buy_below ?? 0.8, sellAbove: number = unc?.sell_above ?? 1.25;
  const details = primary?.calculation_details ?? base.data.calculation_details;
  const research = primary?.research_status ?? base.data.research_status;
  const dividendNeedsReview = !!(use.ddm && dval && ddmUseful && ddm?.research_status?.eligible !== true);
  const canClassify = research?.eligible === true && !dividendNeedsReview;
  const verdict = !canClassify ? 'Research required' : !fair ? '—' : price <= fair * buyBelow ? 'Undervalued' : price >= fair * sellAbove ? 'Overvalued' : 'Fairly valued';
  const three = primBase?.valuation?.method === 'three_stage';
  const moat = primBase?.valuation?.moat;
  const mainDrivers = primaryModel === 'excess_return' ? ER_DRIVERS : three ? FCFF_DRIVERS : FCFF_DRIVERS_2STAGE;
  const drivers = primaryModel === 'fcff' && inp.net_capex_to_revenue != null ? [...mainDrivers, { key: 'working_capital_ratio', label: 'Working capital / sales (optional)', short: 'WC / sales', hint: 'Balance-sheet intensity × revenue change; optional research assumption. The automatic estimate has mixed historical evidence.', min: -0.5, max: 0.5, step: 0.01, pct: true }] : mainDrivers;
  const implied = primaryModel === 'excess_return' ? { k: 'roe', v: primBase?.market_implied_roe, label: 'ROE the price implies' }
    : { k: 'growth', v: primBase?.market_implied_growth, label: 'Growth the price implies' };
  const out = primary?.outlook;

  return (
    <div className="space-y-3">
      <ValuationCapture symbol={symbol} disabled={!primary || !!base.loading || !!prim.loading || !!prim.error || !!base.refreshError || (use.ddm && (!!ddmReq.loading || !!ddmBaseReq.loading || !!ddmReq.error)) || (use.peers && (!!rv.loading || !!rv.error)) || JSON.stringify(ov)!==JSON.stringify(ovD) || JSON.stringify(dv)!==JSON.stringify(dvD)} payload={{symbol,model:primaryModel,base:base.data,primary,ddm,peers:rv.data,assumptions:{primary:pVals,dividend:dVals,options:opts,halfLife:hl,methods:use},fairValue:fair,currency:ccy,inputDates:{price:inp.price_date,financials:inp.as_of},method:base.data.method}}/>
      {/* verdict */}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1.6fr)] gap-3">
        <div className="border border-border bg-surface-1 rounded-md p-3">
          <div className="text-[10px] uppercase tracking-wider text-text-tertiary">Selected-model estimate ({ccy})</div>
          <div className="flex items-baseline gap-3 mt-0.5">
            <span className="text-3xl font-mono text-text-primary">{fair ? fmtPrice(fair) : '—'}</span>
            {up != null && <span className={cn('font-mono text-lg', up >= 0 ? 'text-green' : 'text-red')}>{fmtPct(up, 1)}</span>}
            <span className={cn('px-2 py-0.5 rounded-sm text-xs font-semibold', verdict === 'Undervalued' ? 'bg-green/15 text-green' : verdict === 'Overvalued' ? 'bg-red/15 text-red' : 'bg-surface-3 text-text-secondary')}>{verdict}</span>
          </div>
          <div className="text-2xs text-text-secondary mt-1">Price {fmtPrice(price)} · {conf}{spread ? ` (high ÷ low ${spread.toFixed(2)}×)` : ''}</div>
          {fair != null && canClassify && <div className="text-2xs text-text-secondary mt-0.5" title="Morningstar's rule: the discount required to buy widens with the uncertainty of the value (here from the stock's 1-year volatility, one notch higher when most of the value is in the terminal value).">
            Uncertainty <span className="text-text-primary">{unc?.rating ?? 'medium'}</span> · buy below <span className="font-mono text-green">{fmtPrice(fair * buyBelow)}</span> · sell above <span className="font-mono text-red">{fmtPrice(fair * sellAbove)}</span></div>}
          {!canClassify && <div className="text-[10px] text-bloomberg mt-1">{research?.reasons?.join(' ') || (dividendNeedsReview ? 'The selected dividend model requires research. ' + (ddm?.research_status?.reasons?.join(' ') ?? '') : 'Waiting for data and model checks.')}</div>}
          {moat && primaryModel === 'fcff' && <div className="text-[10px] text-text-tertiary mt-0.5">Moat (from the data): <span className="text-text-secondary">{moat.rating}</span> — {moat.basis}; excess returns assumed for {primBase.valuation.assumptions.fade_years} more years.</div>}
          {bv != null && uv != null && <ScenarioBar bear={bv} base={pv ?? null} bull={uv} price={price} fair={fair} />}
          <div className="mkt-controls flex flex-wrap gap-1 mt-2 text-[11px]">
            <span className="text-text-tertiary mr-1">Blend</span>
            {([['primary', primaryModel === 'excess_return' ? 'Excess return' : 'DCF', !!pv], ['ddm', 'Dividend model', !!(dval && ddmUseful)], ['peers', 'Peers', !!peer]] as const).map(([k, l, ok]) => (
              <button key={k} disabled={!ok} onClick={() => setUse({ ...use, [k]: !use[k] })}
                className={cn('px-2 py-0.5 border rounded-sm', !ok ? 'border-border-subtle text-text-tertiary opacity-50' : use[k] ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>))}
          </div>
          <div className="text-[10px] text-text-tertiary mt-1">Geometric mean of the selected methods; agreement is not independent validation. The dividend model joins when the yield is at least 1.5%.</div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Tile label={primaryModel === 'excess_return' ? 'Excess return model' : 'DCF (free cash flow)'} v={pv} price={price} sub={primary?.valuation?.equity_negative ? 'debt exceeds operating value' : prim.loading ? 'recalculating…' : `${implied.label}: ${pc(implied.v)}`} />
          <Tile label="Dividend model" v={dval} price={price} sub={ddm ? `yield ${pc(ddm.valuation.dividend_yield)} · price implies ${pc(ddm.valuation.implied_growth)} growth` : 'no dividend'} />
          <Tile label={`Peer multiples${home ? ` (${home})` : ''}`} v={peer} price={price} sub={rv.loading && !rv.data ? 'loading…' : peer ? 'median of P/E, fwd P/E, EV/EBITDA' : 'not meaningful'} />
          <Tile label="Analysts’ 12-month target" v={out?.analyst_target} price={price} sub={out?.analysts ? `${out.analysts} analysts · ${fmtPrice(out.analyst_low)}–${fmtPrice(out.analyst_high)}` : '—'} />
        </div>
      </div>

      <p className="text-[10px] text-text-tertiary">Peer multiples and analyst targets describe market pricing. Peers are excluded from the headline intrinsic estimate by default; enabling them can import an expensive market’s pricing into the blend.</p>

      {primary?.expectations && <ExpectationsPanel data={primary.expectations}/>}
      {primary?.market_views && <Panel title="Fundamentals and current market pricing">
        <div className="text-[10px] text-text-tertiary mb-2">Normalized assumptions and market-implied pricing are separate lenses. The default primary ERP is a 5% mature-market research assumption plus country risk, not a fit to market prices. Manual discount-rate choices remain in the main model. Country risk: {primary.market_views.country_risk.basis}.</div>
        {primary.market_views.suitability?.status === 'review_required' && <div className="text-2xs text-bloomberg mb-2">
          Model review required: {primary.market_views.suitability.reasons.join(' ')}
        </div>}
        <label className="flex items-center gap-2 text-2xs text-text-secondary mb-2">Primary valuation premium basis
          <select value={opts.erp_basis ?? 'normalized'} onChange={(e) => setOpts({ ...opts, erp_basis: e.target.value as Opts['erp_basis'] })} className="bg-background border border-border rounded-sm px-2 py-0.5"><option value="normalized">Normalized research assumption</option><option value="market_implied">Current market-implied premium</option></select>
        </label>
        <label className="flex items-center gap-2 text-2xs text-text-secondary mb-2">Normalized mature-market ERP
          <select value={opts.normalized_erp ?? 0.05} onChange={(e) => setOpts({ ...opts, normalized_erp: Number(e.target.value) })} className="bg-background border border-border rounded-sm px-2 py-0.5">
            {[0.04, 0.045, 0.05, 0.055, 0.06].map((v) => <option key={v} value={v}>{pc(v)}</option>)}
          </select>
        </label>
        <div className="overflow-x-auto"><table className="w-full text-2xs text-right">
          <thead><tr className="text-text-tertiary"><th className="text-left py-1">Scenario</th><th>Fundamental value</th><th>Current-market value</th></tr></thead>
          <tbody>{(['base', 'expansion', 'recession', 'inflation_shock'] as const).map((regime) => {
            const f = primary.market_views.fundamental.scenarios[regime];
            const m = primary.market_views.current_market.scenarios[regime];
            return <tr key={regime} className="border-t border-border-subtle"><td className="text-left py-1 capitalize">{regime.replace('_', ' ')}</td>
              <td title={f.error}>{fmtPrice(f.per_share)}</td><td title={m.error}>{fmtPrice(m.per_share)}</td></tr>;
          })}</tbody>
        </table></div>
        <div className="text-[10px] text-text-tertiary mt-2">Mature-market ERP: normalized {pc(primary.market_views.fundamental.mature_erp)}; current {pc(primary.market_views.current_market.mature_erp)}. {primary.market_views.note}</div>
      </Panel>}

      {details && <Panel title={`Calculation breakdown — amounts in ${inp.currency}`}>
        {!!details.asset_references?.length && <div className="text-2xs text-text-secondary mb-3 space-y-1">
          {details.asset_references.map((ref: any) => <div key={ref.metric}><a href={ref.source} target="_blank" rel="noreferrer" className="text-bloomberg hover:underline">{ref.metric}</a>: {fmtPrice(ref.per_share)} {ref.currency} · {ref.as_of} ({ref.age_days} days old{ref.stale ? ', stale' : ''}). Historical asset reference, excluded from the blend.</div>)}
        </div>}
        {details.issuer_adjustment && <div className="text-2xs text-text-secondary mb-2">Operating profit uses a <a href={details.issuer_adjustment.source} target="_blank" rel="noreferrer" className="text-bloomberg hover:underline">verified issuer source</a> for {details.issuer_adjustment.as_of}; the provider-defined figure is retained in the audit trail.</div>}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-5 gap-y-1 text-2xs">
          {([['Operating profit after tax', details.cashflow?.nopat], ['Capital expenditure', details.cashflow?.capex],
            ['Depreciation and amortization', details.cashflow?.dna], ['Working-capital investment', details.cashflow?.working_capital_investment],
            ['Reconstructed period FCFF', details.cashflow?.observed_fcff], ['Operating cash flow (reported)', details.cashflow?.cfo],
            ['Stock compensation', details.cashflow?.sbc], ['Funding gap after cash', details.funding_gap_after_cash]] as [string, any][]).map(([label, value]) => (
              <div key={label} className="flex justify-between gap-2 border-b border-border-subtle py-1"><span className="text-text-tertiary">{label}</span><span className="font-mono">{fmtBig(value)}</span></div>))}
        </div>
        <div className="text-[10px] text-text-tertiary mt-2">FCFF = operating profit after tax − (capital expenditure − depreciation) − working-capital investment. Positive working-capital investment uses cash. SBC stays expensed in operating profit.</div>
        <div className="text-[10px] text-text-tertiary mt-1">{details.cashflow?.status === 'matched' ? `${details.cashflow.as_of}: ${details.cashflow.source}. ${details.cashflow.working_capital_basis}.` : details.cashflow?.reason}</div>
        {!!details.forecast_steps?.length && <div className="overflow-x-auto mt-3"><table className="w-full text-2xs text-right font-mono">
          <thead className="text-text-tertiary"><tr><th className="text-left">Year</th><th>Revenue</th><th>EBIT</th><th>Modeled tax</th><th>Reinvestment</th><th>FCFF</th><th>PV</th></tr></thead>
          <tbody>{details.forecast_steps.map((row: any) => <tr key={row.year} className="border-t border-border-subtle"><td className="text-left py-1">{row.year}</td>
            {[row.revenue, row.ebit, row.modeled_tax, row.reinvestment, row.fcff, row.present_value].map((v, n) => <td key={n}>{fmtBig(v)}</td>)}</tr>)}</tbody>
        </table></div>}
        <div className="text-[10px] text-text-tertiary mt-2">{details.checks?.join(' ')} {details.note}</div>
      </Panel>}

      {/* the levers */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title={`Key drivers — ${primaryModel === 'excess_return' ? 'excess-return model' : 'cash-flow model'}`} right={<button onClick={() => setOv({})} className="text-[11px] text-text-tertiary hover:text-text-primary">Reset</button>}>
          {!primBase ? <Loading /> : <div className="space-y-3">{drivers.map((d) => (
            <Slider key={d.key} d={d} value={pVals[d.key] ?? (d.key === 'working_capital_ratio' ? 0 : undefined)} def={pDef[d.key] ?? (d.key === 'working_capital_ratio' ? 0 : undefined)} implied={implied.k === d.key ? implied.v : undefined}
              onChange={(x) => setOv({ ...ov, [d.key]: x })} />))}
            {prim.error && Object.keys(ovD).length > 0 && <div className="text-2xs text-red">{prim.error}</div>}
          </div>}
        </Panel>
        <Panel title="Dividend model drivers" right={hasDdm ? <button onClick={() => setDv({})} className="text-[11px] text-text-tertiary hover:text-text-primary">Reset</button> : undefined}>
          {!hasDdm ? <div className="text-2xs text-text-tertiary">{symbol} doesn’t pay a regular dividend, so the dividend model doesn’t apply.</div>
            : !ddmBase ? <Loading /> : <div className="space-y-3">{DDM_DRIVERS.map((d) => (
              <Slider key={d.key} d={d} value={dVals[d.key]} def={dDef[d.key]} implied={d.key === 'growth' ? ddmBase.valuation.implied_growth : undefined}
                onChange={(x) => setDv({ ...dv, [d.key]: x })} />))}
              {ddmReq.error && Object.keys(dvD).length > 0 && <div className="text-2xs text-red">{ddmReq.error}</div>}
              <div className="text-[10px] text-text-tertiary">Dividend {fmtPrice(ddmBase.valuation.dps)} a share; 5-year dividend growth {pc(ddmBase.valuation.dividend_cagr_5y)}.</div>
            </div>}
          <div className="mt-4 pt-3 border-t border-border-subtle">
            <div className="flex items-center gap-2 text-2xs"><span className="text-text-secondary flex-1">How fast the price closes the gap to fair value (outlook)</span>
              {[1, 2, 3, 5, 8].map((h) => <button key={h} onClick={() => setHl(h)} className={cn('px-2 py-0.5 border rounded-sm', hl === h ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{h}y</button>)}</div>
            <div className="text-[10px] text-text-tertiary mt-0.5">Illustrative gap half-life; convergence timing is an assumption, not an estimated forecast.</div>
          </div>
        </Panel>
      </div>

      {/* scenarios */}
      <Panel title="Scenarios — the same model with the key drivers pushed each way">
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Scenario</th>
            {drivers.map((d) => <th key={d.key} className="text-right font-normal px-1.5 whitespace-nowrap" title={d.label}>{d.short ?? d.label}</th>)}
            <th className="text-right font-normal px-1.5">Value / share</th><th className="text-right font-normal px-1.5">vs price</th></tr></thead>
          <tbody>{([['Bear', bear], ['Base', { data: primary, loading: prim.loading }], ['Bull', bull]] as const).map(([n, r]: any) => {
            const x = r.data?.valuation?.per_share;
            const v = defaultsFor(r.data);
            return (
              <tr key={n} className={cn('border-t border-border-subtle', n === 'Base' && 'bg-bloomberg/5 font-semibold')}>
                <td className={cn('py-1 font-sans', n === 'Bear' ? 'text-red' : n === 'Bull' ? 'text-green' : 'text-text-primary')}>{n}</td>
                {drivers.map((d) => <td key={d.key} className="text-right px-1.5 text-text-secondary">{d.pct ? pc(v[d.key]) : v[d.key] != null ? `${v[d.key]}y` : '—'}</td>)}
                <td className="text-right px-1.5 text-text-primary">{x != null ? fmtPrice(x) : r.loading ? '…' : '—'}</td>
                <td className={cn('text-right px-1.5', x != null && (x >= price ? 'text-green' : 'text-red'))}>{x != null ? fmtPct(x / price - 1, 0) : ''}</td></tr>);
          })}</tbody>
        </table></div>
        <div className="text-[10px] text-text-tertiary mt-1">{primaryModel === 'excess_return' ? 'Bear/bull: ROE ∓3 points, long-run ROE ∓2, equity risk premium ±0.75 point.' : 'Bear/bull: growth ∓3 points, margin ×0.85 / ×1.10, equity risk premium ±0.75 point.'} Move the drivers and every scenario moves with them.</div>
        {/* Cost-of-capital lens: market-implied (calibrated default) vs the appraisal standard */}
        {(() => {
          const kroll = +(0.05 + (inp.country_risk_premium ?? 0)).toFixed(4);
          const onKroll = ov.erp != null && Math.abs(ov.erp - kroll) < 1e-6;
          const lens = (k: boolean) => setOv((o) => { const n = { ...o }; if (k) n.erp = kroll; else delete n.erp; return n; });
          return (
            <div className="mkt-controls flex flex-wrap items-center gap-2 mt-2 text-[10.5px]">
              <span className="text-text-tertiary">Equity risk premium lens:</span>
              <button type="button" onClick={() => lens(false)} aria-pressed={!onKroll}
                className={`px-1.5 py-0.5 border ${!onKroll ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary'}`}>
                Market-implied {pc(inp.erp_implied != null ? inp.erp_implied + (inp.country_risk_premium ?? 0) : inp.erp, 1)}</button>
              <button type="button" onClick={() => lens(true)} aria-pressed={onKroll}
                className={`px-1.5 py-0.5 border ${onKroll ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary'}`}>
                Appraisal standard {pc(kroll, 1)}</button>
              <button type="button" onClick={() => setOpts((o) => ({ ...o, ke_method: o.ke_method === 'building_block' ? undefined : 'building_block' }))}
                aria-pressed={opts.ke_method === 'building_block'}
                className={`px-1.5 py-0.5 border ${opts.ke_method === 'building_block' ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary'}`}>
                Building blocks (Morningstar)</button>
              <span className="text-text-tertiary">Market-implied (Damodaran) is the default. The appraisal standard (Kroll's 5% + country risk) is what valuation reports use; building blocks is Morningstar's cost of equity — a 6.75% real market return + inflation (9% for an average US stock) ± a step for systematic risk, insensitive to today's bond yield.</span>
            </div>
          );
        })()}
        {primaryModel === 'fcff' && (
          <div className="mkt-controls flex flex-wrap items-center gap-2 mt-2 text-[10.5px]">
            <span className="text-text-tertiary">Structure:</span>
            {([['three_stage', 'Three-stage (Morningstar)'], ['two_stage', 'Two-stage (Damodaran)']] as const).map(([k, l]) => {
              const on = (opts.method ?? (three ? 'three_stage' : 'two_stage')) === k;
              return <button key={k} type="button" aria-pressed={on} onClick={() => setOpts((o) => ({ ...o, method: k }))}
                className={`px-1.5 py-0.5 border ${on ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary'}`}>{l}</button>;
            })}
            <span className="text-text-tertiary">Three-stage: explicit forecast, a fade whose length follows the moat, then new investment earns only its cost of capital. Two-stage: growth forever after the forecast with half of today's excess return kept.</span>
          </div>
        )}
      </Panel>

      {out && canClassify && <PriceOutlook o={out} ccy={ccy} value={fair} halfLife={hl} title={`Price path to the blended fair value — next 24 months (${ccy})`} />}

      {/* what was filled in */}
      <details className="border border-border bg-surface-1 rounded-md px-3 py-2">
        <summary className="cursor-pointer text-2xs text-text-secondary">Everything filled in automatically (click to see the inputs and sources)</summary>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-x-6 gap-y-1 mt-2 text-2xs">
          {([['Revenue (valuation base)', fmtBig(inp.revenue)], ['Operating margin', pc(inp.margin)], ['Shares', fmtBig(inp.shares)], ['Debt', fmtBig(inp.debt)], ['Cash', fmtBig(inp.cash)],
            ['Beta', inp.beta?.toFixed(2)], ['Risk-free rate', pc(inp.risk_free, 2)], ['Equity risk premium', pc(inp.erp, 2)], ['Tax (marginal)', pc(inp.tax_marginal, 0)],
            ['Sales-to-capital', inp.sales_to_capital?.toFixed(2)], ['ROIC', pc(inp.roic)], ['Payout ratio', pc(inp.payout_ratio, 0)]] as [string, any][]).map(([k, x]) => (
            <div key={k} className="flex justify-between border-b border-border-subtle py-0.5"><span className="text-text-tertiary">{k}</span><span className="font-mono text-text-primary">{x ?? '—'}</span></div>))}
        </div>
        <div className="mt-2 text-[10px] text-text-tertiary space-y-0.5">
          <div>Financials: {inp.source}. Risk-free: {inp.risk_free_source}. ERP: {inp.erp_source}. Beta: {inp.beta_source}.</div>
          <div>Growth: {inp.growth_source}.{inp.target_margin_source ? ` Margin: ${inp.target_margin_source}.` : ''}</div>
        </div>
        <div className="flex gap-2 mt-2 text-[11px]">
          <button onClick={() => onGo('DCF', symbol)} className="px-2 py-0.5 border border-border hover:border-bloomberg hover:text-bloomberg">Full model (DCF)</button>
          <button onClick={() => onGo('RV', symbol)} className="px-2 py-0.5 border border-border hover:border-bloomberg hover:text-bloomberg">Peers (RV)</button>
          <button onClick={() => onGo('FA', symbol)} className="px-2 py-0.5 border border-border hover:border-bloomberg hover:text-bloomberg">Financials (FA)</button>
        </div>
      </details>
    </div>
  );
}

function Tile({ label, v, price, sub }: { label: string; v: number | null | undefined; price: number; sub: string }) {
  return (
    <div className="border border-border bg-surface-1 rounded-md px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className="flex items-baseline gap-2"><span className="font-mono text-lg text-text-primary">{v != null && v > 0 ? fmtPrice(v) : '—'}</span>
        {v != null && v > 0 && <span className={cn('font-mono text-2xs', v >= price ? 'text-green' : 'text-red')}>{fmtPct(v / price - 1, 0)}</span>}</div>
      <div className="text-[10px] text-text-tertiary leading-tight">{sub}</div>
    </div>
  );
}

function Slider({ d, value, def, implied, onChange }: { d: Driver; value: number | undefined; def: number | undefined; implied?: number | null; onChange: (x: number) => void }) {
  const v = value ?? def ?? 0;
  const lo = Math.min(d.min, v, def ?? v), hi = Math.max(d.max, v, def ?? v);
  const pos = (x: number) => `${((x - lo) / (hi - lo)) * 100}%`;
  const changed = def != null && Math.abs(v - def) > 1e-9;
  const k = d.pct ? 100 : 1, unit = d.pct ? '%' : 'y';
  return (
    <div>
      <div className="flex items-baseline gap-2 text-2xs">
        <span className="text-text-primary font-medium flex-1">{d.label}</span>
        <input type="number" step={d.step * k} value={(v * k).toFixed(d.pct ? 2 : 0)} onChange={(e) => { const n = Number(e.target.value); if (Number.isFinite(n)) onChange(n / k); }}
          className={cn('w-20 bg-surface-1 border px-1.5 py-0.5 font-mono text-right', changed ? 'border-bloomberg text-bloomberg' : 'border-border text-text-primary')} />
        <span className="text-text-tertiary">{unit}</span>
      </div>
      <div className="relative mt-1">
        <input type="range" min={lo} max={hi} step={d.step} value={v} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[rgb(var(--c-bloomberg))]" aria-label={d.label} />
        {def != null && <span className="absolute top-0 h-1.5 w-0.5 bg-text-tertiary pointer-events-none" style={{ left: pos(def) }} title={`default ${(def * k).toFixed(d.pct ? 1 : 0)}${unit}`} />}
        {implied != null && Number.isFinite(implied) && implied >= lo && implied <= hi && <span className="absolute -top-0.5 h-2.5 w-0.5 bg-amber pointer-events-none" style={{ left: pos(implied) }} title={`price implies ${(implied * 100).toFixed(1)}%`} />}
      </div>
      <div className="flex justify-between text-[10px] text-text-tertiary">
        <span>{d.hint}</span>
        <span className="shrink-0 ml-2">default {def != null ? `${(def * k).toFixed(d.pct ? 1 : 0)}${unit}` : '—'}{implied != null ? <> · <span className="text-amber">price implies {(implied * 100).toFixed(1)}%</span></> : null}</span>
      </div>
    </div>
  );
}

function ScenarioBar({ bear, base, bull, price, fair }: { bear: number; base: number | null; bull: number; price: number; fair: number | null }) {
  const xs = [bear, bull, price, ...(base ? [base] : []), ...(fair ? [fair] : [])].filter((x) => x > 0);
  const lo = Math.min(...xs) * 0.95, hi = Math.max(...xs) * 1.05;
  const pos = (x: number) => `${((x - lo) / (hi - lo || 1)) * 100}%`;
  return (
    <div className="relative h-11 mt-3" aria-label="Bear to bull range">
      <div className="absolute top-4 h-2 rounded-full bg-gradient-to-r from-red/40 via-surface-3 to-green/40" style={{ left: pos(Math.max(bear, lo)), width: `calc(${pos(bull)} - ${pos(Math.max(bear, lo))})` }} />
      <Mark x={pos(Math.max(bear, lo))} label={`bear ${fmtPrice(bear)}`} cls="text-red" below />
      <Mark x={pos(bull)} label={`bull ${fmtPrice(bull)}`} cls="text-green" below />
      {fair && <Mark x={pos(fair)} label={`fair ${fmtPrice(fair)}`} cls="text-blue" />}
      <div className="absolute top-2 h-6 w-0.5 bg-bloomberg" style={{ left: pos(price) }} title={`price ${fmtPrice(price)}`} />
    </div>
  );
}
function Mark({ x, label, cls, below }: { x: string; label: string; cls: string; below?: boolean }) {
  return <div className={cn('absolute text-[10px] font-mono -translate-x-1/2 whitespace-nowrap', below ? 'top-7' : 'top-0', cls)} style={{ left: x }}>{label}</div>;
}

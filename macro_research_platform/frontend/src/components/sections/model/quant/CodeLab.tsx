/**
 * Code Lab — write a strategy in Python, test it in the browser (Pyodide worker), see it net of every
 * cost, walk-forward optimised, Monte-Carlo'd and deep-analysed; save it or deploy it to a paper trader
 * (deployment runs the code in the server's sandbox). Engine: api/quant/codelab.py.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useConfirm } from '@/components/ui/ConfirmDialog';
import { Loader2, Play, Rocket, Save, ShieldCheck, ShieldAlert, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { BarList } from '@/components/ui/BarList';
import { CATEGORICAL } from '@/lib/chartPalette';
import { DeepReport } from './DeepReport';
import { LeanOptimizer } from './LeanOptimizer';
import { TEMPLATES } from './templates';
import { Attribution, Capacity, Charts, Heatmap, Risk, Signal, Trades, Validation } from './ResearchPanels';
import { api, ErrorNote, Field, inputCls, money, num, pct, spct, tone, usd } from './shared';

export const STARTER = `# Global configured equities; USD valuations/FX and venue costs supplied by Macro Terminal.
# Server-job strategy. Account sessions use ACWI's observed calendar.
# Today's global constituents remain retrospective, not historically unbiased.
import numpy as np
import pandas as pd

UNIVERSE = ["ACWI", "SPY"]
TRADABLE_UNIVERSE = "GLOBAL"
ACCOUNT_CALENDAR = "ACWI"
START = "2011-01-03"
BENCHMARK = "ACWI"
PARAMS = {"core_share": [0.30, 0.50], "weight_mode": ["plain", "buffered", "shrunk"]}


def strategy(data, core_share=0.30, weight_mode="buffered", picks=30,
             broad_share=0.30, target_vol=0.20, max_stock=0.04,
             country_cap=0.20, us_stock_cap=0.40, min_traded_value=10000000.0,
             stress_budget=0.50, **params):
    if params or weight_mode not in ["plain","buffered","shrunk"]:
        raise ValueError("Unknown parameters or weighting mode")
    if not 0 <= core_share <= .8 or not 0 <= broad_share <= 1-core_share:
        raise ValueError("Invalid sleeve allocation")
    if not .05 <= target_vol <= .30 or not 0 < max_stock <= .10 or not 0 < country_cap <= .5:
        raise ValueError("Invalid risk limits")
    if not 0 < us_stock_cap <= .5 or not .20 <= stress_budget <= .98 or min_traded_value <= 0:
        raise ValueError("Invalid country, stress or liquidity settings")
    if isinstance(picks,bool) or not isinstance(picks,int) or not 10 <= picks <= 100:
        raise ValueError("picks must be an integer from 10 to 100")
    if data.provenance.get("account_currency") != "USD":
        raise ValueError("Global research requires the platform's USD-converted data loader")
    px = data.close.astype(float)
    if "ACWI" not in px.columns or len(px.columns)>4000 or not px.columns.is_unique:
        raise ValueError("Include ACWI and use no more than 4000 unique instruments")
    if not px.index.is_unique or not px.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and increasing")
    if np.isinf(px.to_numpy()).any() or (px <= 0).any().any():
        raise ValueError("Bad price observations must be cleaned by the data loader")
    observed = data.observed.reindex(index=px.index,columns=px.columns).fillna(False)
    volume = data.volume.reindex(index=px.index,columns=px.columns)
    countries = [data.instruments[c].get("country","") for c in px.columns]
    groups = {c:np.array([i for i,x in enumerate(countries) if x==c],dtype=int) for c in sorted(set(countries)) if c}
    core_index = list(px.columns).index("ACWI")
    stock = np.ones(len(px.columns),dtype=bool)
    stock[core_index] = False
    if "SPY" in px.columns: stock[list(px.columns).index("SPY")] = False
    ret = px.pct_change(fill_method=None)
    ready = observed.rolling(253,min_periods=253).sum() >= 220
    valid = observed & (volume>0) & px.notna()
    # USD price times actual share volume; avoids comparing JPY/GBp values to dollars.
    adv = (px*volume).where(observed & (volume>0)).rolling(63,min_periods=45).mean()
    vol = ret.rolling(63,min_periods=63).std()*np.sqrt(252)
    eligible = ready & valid & (adv>=min_traded_value) & (vol>=.03) & (vol<=1.)
    eligible.iloc[:,~stock] = False
    mom12 = px.shift(21)/px.shift(252)-1.
    mom6 = px.shift(21)/px.shift(126)-1.
    score = .6*mom12.where(eligible).rank(axis=1,pct=True)+.4*mom6.where(eligible).rank(axis=1,pct=True)
    score = score.where((mom12>0)&(mom6>0))
    tax = np.array([float(data.instruments[c].get("tax_buy_bps") or 0)+float(data.instruments[c].get("tax_sell_bps") or 0) for c in px.columns])
    if weight_mode != "plain":
        # Cost hurdle proxy, not a calibrated forecast: four modeled annual round trips.
        score = score-np.minimum(4*tax/10000/.20,.25)
    moving_average = px["ACWI"].rolling(200,min_periods=200).mean()
    market_vol = ret["ACWI"].rolling(20,min_periods=20).std()*np.sqrt(252)
    market_dd = px["ACWI"]/px["ACWI"].rolling(252,min_periods=252).max()-1.
    stress = (market_vol>=.30)|(market_dd<=-.15)
    months = px.index.to_period("M");weeks=px.index.to_period("W")
    monthly = np.r_[True,months[1:]!=months[:-1]]
    weekly = np.r_[True,weeks[1:]!=weeks[:-1]]
    out = np.full(px.shape,np.nan)
    last = np.zeros(len(px.columns));previous=[];initialized=False
    for t in range(len(px)):
        if not valid["ACWI"].iloc[t] or not ready["ACWI"].iloc[t]:continue
        if monthly[t] or not initialized:
            candidate = np.zeros(len(px.columns))
            budget = .98*(1. if px["ACWI"].iloc[t]>=moving_average.iloc[t] else .85)
            candidate[core_index] = budget*core_share
            broad = eligible.iloc[t].to_numpy()
            if broad.any():candidate[broad] += budget*broad_share/broad.sum()
            ranks = score.iloc[t].rank(ascending=False,method="first")
            buffer = 1. if weight_mode=="plain" else 1.8
            kept = [j for j in previous if pd.notna(ranks.iloc[j]) and ranks.iloc[j]<=buffer*picks]
            selected = sorted(kept,key=lambda j:float(ranks.iloc[j]))[:picks]
            for j in np.argsort(ranks.fillna(1e9).to_numpy()):
                if len(selected)>=picks:break
                if j not in selected and pd.notna(ranks.iloc[j]):selected.append(int(j))
            previous = selected
            if selected:
                v = vol.iloc[t,selected].to_numpy()
                allocation = 1/np.sqrt(v)
                if weight_mode=="shrunk":
                    h = ret.iloc[t-62:t+1,selected].to_numpy()
                    if np.isfinite(h).all():
                        # EPO-inspired covariance regularization on selected names only.
                        # This is a constrained rank proxy, not a published EPO replication.
                        covariance = np.atleast_2d(np.cov(h,rowvar=False))*252
                        covariance = .5*covariance+.5*np.diag(np.diag(covariance))
                        view = np.maximum(score.iloc[t,selected].to_numpy(),.01)
                        allocation = np.maximum(np.linalg.solve(covariance+np.eye(len(selected))*1e-6,view),0)
                if allocation.sum()>0:candidate[selected] += allocation/allocation.sum()*budget*(1-core_share-broad_share)
            candidate[stock] = np.minimum(candidate[stock],max_stock)
            for country,indices in groups.items():
                indices = indices[stock[indices]]
                total = candidate[indices].sum()
                limit = us_stock_cap if country=="US" else country_cap
                if total>limit:candidate[indices] *= limit/total
            # Exact portfolio variance by projection, not an O(N squared) full-universe covariance.
            active=candidate>0;history=ret.iloc[max(0,t-62):t+1,active].to_numpy()
            if len(history)==63 and np.isfinite(history).all():
                risk=np.std(history@candidate[active],ddof=1)*np.sqrt(252)
                if risk>0:candidate*=min(1.,target_vol/risk)
            else:candidate*=0.
            if stress.iloc[t] and candidate.sum()>stress_budget:candidate*=stress_budget/candidate.sum()
            last=candidate;out[t]=last;initialized=last.sum()>0
        elif weekly[t] and stress.iloc[t] and last.sum()>stress_budget:
            last=last*stress_budget/last.sum();out[t]=last
    return pd.DataFrame(out,index=px.index,columns=px.columns)
`;

export const UNIVERSE_LIMIT = 80;   // api/quant/codelab.py UNIVERSE_LIMIT: larger lists run on the server
export const COST_DEFAULTS = { capital: 1_000_000, commission_bps: 0.35, spread_mult: 1, impact_coef_bps: 11.21, borrow_fee: 0.003,
  financing_spread: 0.01, cash_spread: 0, no_trade_band: 0.0025, delist_haircut: 0, fx_cost_bps: 2,
  fx_hedge_cost_bps: 15, dividend_wht: 1, wht_treaty_cap: 0.15, board_lots: 1, exec_price: 0, max_participation: 0.1,
  borrow_tiers: 1, maintenance_margin: 0.25, commission_per_share: 0, commission_min: 0, commission_max_pct: 0, crypto_fee_bps: 10 };

// Broker fee models (approximate public pricing, 2025; check your broker's schedule). `spread_mult` > 1 for
// payment-for-order-flow brokers: no commission, but fills slightly worse than the quoted midpoint model.
const BROKERS: { id: string; name: string; set: Partial<Costs>; note: string }[] = [
  { id: 'inst', name: 'Institutional (default)', set: { commission_bps: 0.35, commission_per_share: 0, commission_min: 0, commission_max_pct: 0, spread_mult: 1 },
    note: '0.35 bp of value — a large algorithmic trader' },
  { id: 'ibkr_fixed', name: 'IBKR Pro — Fixed', set: { commission_bps: 0, commission_per_share: 0.005, commission_min: 1, commission_max_pct: 0.01, spread_mult: 1 },
    note: '$0.005/share, $1 minimum, 1% maximum per order (US)' },
  { id: 'ibkr_tiered', name: 'IBKR Pro — Tiered', set: { commission_bps: 0, commission_per_share: 0.004, commission_min: 0.35, commission_max_pct: 0.01, spread_mult: 1 },
    note: '≈$0.0035/share + exchange/regulatory ≈ $0.004, $0.35 minimum, 1% maximum (US, small volume tier)' },
  { id: 'zero', name: '$0 commission (IBKR Lite, Schwab, Fidelity, Robinhood, Alpaca)', set: { commission_bps: 0, commission_per_share: 0, commission_min: 0, commission_max_pct: 0, spread_mult: 1.15 },
    note: 'No commission; routed for payment for order flow — fills modelled 15% worse on the spread' },
  { id: 'ibkr_global', name: 'IBKR Pro — non-US markets', set: { commission_bps: 5, commission_per_share: 0, commission_min: 3, commission_max_pct: 0, spread_mult: 1 },
    note: '≈0.05% of value, ≈3 (account currency) minimum per order — Europe/Asia tiered schedules vary by exchange' },
];
export type Costs = typeof COST_DEFAULTS;
const MC_DEFAULTS = { mc_years: 10, max_leverage: 2, dd_limit: 0.5 };

// ── Python runner (Web Worker) ──────────────────────────────────────────────
type Msg = { type: string; [k: string]: any };
let shared: { worker: Worker; ready: Promise<void> } | null = null;

function getWorker(onStatus: (s: string) => void, onStdout: (s: string) => void) {
  if (!shared) {
    const worker = new Worker('/quant-py-worker.js', { type: 'module' });
    const ready = (async () => {
      const r = await fetch('/api/v1/quant/code/engine');
      if (!r.ok) throw new Error(r.status === 401 ? 'Sign in to run code.' : `Could not load the engine (HTTP ${r.status}).`);
      const engine = await r.text();
      const rq = await fetch('/api/v1/quant/code/engine?module=qcalgo');
      const qcalgo = rq.ok ? await rq.text() : '';             // the QuantConnect-style API (optional)
      await new Promise<void>((res, rej) => {
        const h = (ev: MessageEvent<Msg>) => {
          if (ev.data.type === 'ready') { worker.removeEventListener('message', h); res(); }
          if (ev.data.type === 'error') { worker.removeEventListener('message', h); rej(new Error(ev.data.error)); }
        };
        worker.addEventListener('message', h);
        worker.postMessage({ type: 'init', engine, qcalgo });
      });
    })();
    ready.catch(() => { shared = null; });
    shared = { worker, ready };
  }
  const w = shared.worker;
  w.onmessage = (ev: MessageEvent<Msg>) => {
    if (ev.data.type === 'status') onStatus(ev.data.text);
    if (ev.data.type === 'stdout') onStdout(ev.data.text);
  };
  return shared;
}

/** Fold research_checks() output into a result shown before the checks ran. */
function mergeChecks(r: any, k: any) {
  const { checks_pending, ...rest } = r;  // eslint-disable-line @typescript-eslint/no-unused-vars
  return {
    ...rest,
    validation: { ...(r.validation ?? {}), causality: k.causality ?? r.validation?.causality },
    ...(k.capacity ? { capacity: k.capacity } : {}),
    ...(k.signal ? { signal: k.signal } : {}),
    risk: r.risk ? { ...r.risk, ...(k.factor_model ? { factor_model: k.factor_model } : {}) } : r.risk,
  };
}

function call(worker: Worker, msg: Msg, expect: string, timeoutMs: number): Promise<any> {
  const id = Math.random().toString(36).slice(2);
  return new Promise((res, rej) => {
    const timer = setTimeout(() => { cleanup(); worker.terminate(); shared = null; rej(new Error(`Stopped after ${timeoutMs / 1000}s — the strategy took too long.`)); }, timeoutMs);
    const h = (ev: MessageEvent<Msg>) => {
      if (ev.data.id !== id) return;
      if (ev.data.type === expect) { cleanup(); res(ev.data); }
      if (ev.data.type === 'error') { cleanup(); rej(new Error(ev.data.error)); }
    };
    const cleanup = () => { clearTimeout(timer); worker.removeEventListener('message', h); };
    worker.addEventListener('message', h);
    worker.postMessage({ ...msg, id });
  });
}

// ── Editor ──────────────────────────────────────────────────────────────────
// Completions: what strategy code can use (api/quant/codelab.py).
const DATA_FIELDS: [string, string][] = [
  ['close', 'closes (dates × tickers), account currency, adjusted'], ['open', 'opens — the execution price'], ['high', 'highs'],
  ['low', 'lows'], ['volume', 'share volume'], ['observed', 'True where a real bar exists'], ['rf', 'daily cash rate (Series)'],
  ['vix', 'VIX close (Series)'], ['info', 'tickers × country, currency, sector, region'], ['instruments', 'per-ticker metadata dict'],
  ['account_currency', 'the account currency'], ['usd_per_unit', 'USD per account unit (Series)'], ['members', 'index membership (SP500_PIT)'],
  ['opt', 'option analytics: delta, iv, strike, dte, spot, roll …'], ['fund', 'point-in-time fundamentals (FUNDAMENTALS)'],
  ['option_names', 'synthetic option columns'], ['tickers', 'column names'], ['returns()', 'daily returns'],
  ['custom["name"]', 'uploaded custom data (CUSTOM_DATA), as of each session'],
];
const CTX_FIELDS: [string, string][] = [
  ['history("close", 252)', 'rows up to today (field, last n)'], ['close', "today's closes"], ['positions', 'weights held now'],
  ['units', 'units held'], ['nav', 'account value'], ['cash', 'cash balance'], ['fills', "the last session's fills"],
  ['state', 'your dict, kept between bars'], ['date', 'this bar'], ['pre("name")', 'a setup() series up to today'],
  ['opt("delta")', 'option analytics up to today'], ['fund("book_to_price")', 'fundamentals up to today'], ['info', 'instrument metadata'],
  ['target({"SPY": 0.5})', 'market orders to these weights'], ['limit("SPY", 1.0, 400.0)', 'limit order to a weight'],
  ['stop("SPY", 0.0, 380.0)', 'stop order to a weight'], ['cancel()', 'cancel open limit/stop orders'], ['orders', 'open limit/stop orders'],
  ['stop_limit("SPY", 0.0, 380.0, 375.0)', 'stop that becomes a limit'], ['trailing_stop("SPY", 0.0, 0.10)', 'stop trailing 10% behind'],
  ['bracket("SPY", 0.0, 450.0, 380.0)', 'take-profit + stop, one cancels the other'], ['plot("Chart", "name", value)', "today's point on a custom chart"],
];
const NAMES: [string, string][] = [
  ['momentum(data.close, 252, 21)', 'return over n days, skipping the last `skip`'], ['ewma_vol(data.close, 42)', 'annualised EWMA volatility'],
  ['vol_target(w, data.close, 0.10)', 'scale weights to a volatility target'], ['normalize_gross(w)', 'gross exposure to 1'],
  ['hold_monthly(w)', 'decide on the first session of each month'], ['hold_weekly(w)', 'decide weekly'],
  ['on_rolls(w, data, "SPY_P100_1M")', 'decide on option expiries'], ['cov_shrink(returns)', 'Ledoit–Wolf covariance'],
  ['optimize(expected, cov, risk_aversion=5.0, max_weight=0.1)', 'mean–variance QP with constraints'],
  ['min_variance(cov)', 'minimum-variance weights'], ['risk_parity(cov)', 'equal risk contribution'],
  ['style_exposures(data, date)', 'tickers × momentum, volatility, size, value, quality'],
  ['sma(data.close, 50)', 'simple moving average'], ['ema(data.close, 20)', 'exponential moving average'], ['wma(data.close, 20)', 'weighted MA'],
  ['hma(data.close, 20)', 'Hull MA'], ['rsi(data.close, 14)', 'RSI 0–100'], ['macd(data.close)', '{macd, signal, hist}'],
  ['bollinger(data.close, 20, 2)', '{middle, upper, lower, pct_b, width}'], ['atr(data, 14)', 'average true range'],
  ['adx(data, 14)', 'trend strength 0–100'], ['stochastic(data, 14)', '{k, d}'], ['williams_r(data, 14)', '−100–0'],
  ['cci(data, 20)', 'commodity channel index'], ['roc(data.close, 10)', 'rate of change'], ['zscore(data.close, 20)', 'rolling z-score'],
  ['donchian(data, 20)', '{upper, lower} of the previous n days'], ['keltner(data, 20)', '{middle, upper, lower}'],
  ['obv(data)', 'on-balance volume'], ['mfi(data, 14)', 'money flow index'], ['vwap(data, 20)', 'rolling VWAP'],
  ['beta(data.close, data.close["SPY"], 252)', 'rolling beta'], ['drawdown(data.close)', 'below running high'],
  ['rebalance(w, "M")', 'decide D/W/M/Q/Y or every n sessions'], ['top_liquid(data, 100)', 'the n most traded names each day'],
  ['plot("Chart", "series", values)', 'a custom chart in the results'],
  ['UNIVERSE = ["SPY"]', 'tickers to trade'], ['TRADABLE_UNIVERSE = "GLOBAL"', 'a named universe, country or region'],
  ['ACCOUNT_CURRENCY = "USD"', 'the account currency'], ['FX_HEDGE = 1.0', 'share of currency risk hedged'],
  ['OPTIONS = [{"underlying": "SPY", "type": "put", "moneyness": 0.95}]', 'synthetic listed options'],
  ['FUNDAMENTALS = True', 'point-in-time SEC fundamentals'], ['START = "2010-01-01"', 'first record date'],
  ['CUSTOM_DATA = ["name"]', 'an uploaded CSV (Quant Lab → Custom data)'],
  ['import scipy.stats as st', 'scipy, scikit-learn, statsmodels are available'],
  ['BENCHMARK = "SPY"', 'comparison series'], ['PARAMS = {"lookback": [126, 252]}', 'walk-forward grid'],
  ['HOLDOUT = "2023-01-01"', 'untouched holdout from this date'],
  ['def strategy(data, **params):', 'target weights for every date'], ['def on_bar(ctx, **params):', 'event-driven: after every close'],
  ['def setup(data, **params):', 'precomputed indicators for on_bar'], ['def signal(data, **params):', 'scores for IC analysis'],
];

// QuantConnect-style algorithms (api/quant/qcalgo.py): self.<method> inside a QCAlgorithm class
const SELF_FIELDS: [string, string][] = [
  ['set_start_date(2016, 1, 1)', 'first trading day (literal)'], ['set_end_date(2024, 12, 31)', 'last day (literal)'],
  ['set_cash(100000)', 'starting capital'], ['set_benchmark("SPY")', 'benchmark'], ['set_warm_up(200)', 'bars before the start fed to on_data / indicators'],
  ['add_equity("SPY", Resolution.DAILY)', 'add a security → .symbol'], ['add_universe(self.select)', 'selector on point-in-time S&P 500 members'],
  ['schedule.on(self.date_rules.month_start("SPY"), self.time_rules.after_market_open("SPY", 30), self.rebalance)', 'scheduled event (daily: at the close decision)'],
  ['set_holdings(symbol, 0.5)', 'target a fraction of portfolio value'], ['liquidate(symbol)', 'sell everything in symbol'],
  ['market_order(symbol, 100)', 'shares at the next open'], ['market_on_close_order(symbol, 100)', 'shares at the next close'],
  ['limit_order(symbol, 100, price)', 'limit order (ticket)'], ['stop_market_order(symbol, -100, price)', 'stop'],
  ['stop_limit_order(symbol, -100, stop, limit)', 'stop-limit'], ['trailing_stop_order(symbol, -100, 0.1)', 'trailing stop (10%)'],
  ['ema(symbol, 50)', 'EMA (stateful)'], ['sma(symbol, 200)', 'SMA'], ['rsi(symbol, 14)', 'Wilder RSI'], ['atr(symbol, 14)', 'ATR'],
  ['bb(symbol, 20, 2)', 'Bollinger Bands'], ['macd(symbol, 12, 26, 9)', 'MACD'], ['adx(symbol, 14)', 'ADX'], ['roc(symbol, 21)', 'rate of change'],
  ['history(symbol, 60)', 'last 60 daily bars (symbol, time) × OHLCV'], ['portfolio[symbol].quantity', 'shares held'],
  ['portfolio.total_portfolio_value', 'NAV'], ['securities[symbol].price', 'latest close'], ['transactions.get_open_orders()', 'working orders'],
  ['is_warming_up', 'True during set_warm_up'], ['time', 'current bar time'], ['debug("…")', 'log a line'], ['plot("chart", "series", value)', 'custom chart'],
  ['get_parameter("name")', 'current PARAMS value'],
  ['set_alpha(EmaCrossAlphaModel(12, 26))', 'Algorithm Framework: insights'], ['add_alpha(MyAlpha())', 'another alpha model'],
  ['set_portfolio_construction(EqualWeightingPortfolioConstructionModel())', 'insights → targets'],
  ['set_risk_management(MaximumDrawdownPercentPerSecurity(0.05))', 'risk model'], ['set_execution(ImmediateExecutionModel())', 'targets → orders'],
  ['set_universe_selection(ManualUniverseSelectionModel([Symbol.create("SPY", SecurityType.EQUITY, Market.USA)]))', 'framework universe'],
  ['emit_insights(Insight.price(symbol, timedelta(days=5), InsightDirection.UP))', 'insights from your own code'],
  ['consolidate(symbol, Calendar.WEEKLY, self.on_week)', 'weekly / monthly bars from daily'],
  ['register_indicator(symbol, indicator, Calendar.WEEKLY)', 'an indicator on weekly bars'],
  ['object_store.save("key", text)', 'state kept between runs'], ['object_store.read("key")', 'read it back'],
  ['add_data(MyData, "name")', 'uploaded custom data → slice[symbol].value'],
];

function suggest(value: string, pos: number): { from: number; items: [string, string][] } | null {
  const before = value.slice(0, pos);
  const sm = before.match(/\bself\.(\w*)$/);
  if (sm && value.includes('QCAlgorithm')) {
    const items = SELF_FIELDS.filter(([k]) => k.startsWith(sm[1]) && k !== sm[1]);
    return items.length ? { from: pos - sm[1].length, items } : null;
  }
  const m = before.match(/\b(data|ctx)\.(\w*)$/);
  if (m) {
    const list = m[1] === 'data' ? DATA_FIELDS : CTX_FIELDS;
    const items = list.filter(([k]) => k.startsWith(m[2]) && k !== m[2]);
    return items.length ? { from: pos - m[2].length, items: items.slice(0, 8) } : null;
  }
  const w = before.match(/(?:^|[^\w.])([A-Za-z_]\w{1,})$/);
  if (w) {
    const items = NAMES.filter(([k]) => k.toLowerCase().startsWith(w[1].toLowerCase()) && k !== w[1]);
    return items.length ? { from: pos - w[1].length, items: items.slice(0, 8) } : null;
  }
  return null;
}

function CodeEditor({ value, onChange, onRun }: { value: string; onChange: (v: string) => void; onRun: () => void }) {
  const ta = useRef<HTMLTextAreaElement>(null);
  const gutter = useRef<HTMLDivElement>(null);
  const [sug, setSug] = useState<{ from: number; to: number; items: [string, string][] } | null>(null);
  const [sel, setSel] = useState(0);
  const lines = value.split('\n').length;
  const refresh = (el: HTMLTextAreaElement, v: string) => {
    const pos = el.selectionStart;
    const s = el.selectionStart === el.selectionEnd ? suggest(v, pos) : null;
    setSug(s ? { ...s, to: pos } : null);
    setSel(0);
  };
  const accept = (el: HTMLTextAreaElement, text: string) => {
    if (!sug) return;
    const next = value.slice(0, sug.from) + text + value.slice(sug.to);
    onChange(next);
    setSug(null);
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = sug.from + text.length; });
  };
  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); onRun(); return; }
    if (sug) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSel((x) => (x + 1) % sug.items.length); return; }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSel((x) => (x - 1 + sug.items.length) % sug.items.length); return; }
      if (e.key === 'Escape') { e.preventDefault(); setSug(null); return; }
      if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); accept(e.currentTarget, sug.items[sel][0]); return; }
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      const el = e.currentTarget, s = el.selectionStart, end = el.selectionEnd;
      const next = value.slice(0, s) + '    ' + value.slice(end);
      onChange(next);
      requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = s + 4; });
    }
  };
  return (
    <div className="relative flex border border-border bg-surface-1 font-mono text-[12px] leading-[18px] h-[460px]">
      <div ref={gutter} className="select-none text-right pr-2 pl-2 py-2 text-text-tertiary overflow-hidden bg-surface-2/40" aria-hidden>
        {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
      </div>
      <textarea ref={ta} value={value} spellCheck={false} aria-label="Strategy code" aria-autocomplete="list"
        onChange={(e) => { onChange(e.target.value); refresh(e.target, e.target.value); }} onKeyDown={onKey}
        onClick={() => setSug(null)} onBlur={() => setTimeout(() => setSug(null), 150)}
        onScroll={(e) => { if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop; }}
        className="flex-1 resize-none bg-transparent p-2 outline-none text-text-primary whitespace-pre overflow-auto" />
      {sug && (
        <div role="listbox" aria-label="Suggestions" className="absolute left-12 right-2 bottom-2 max-h-48 overflow-auto bg-surface-2 border border-border shadow-lg text-[11px]">
          {sug.items.map(([k, d], i) => (
            <div key={k} role="option" aria-selected={i === sel} onMouseDown={(e) => { e.preventDefault(); if (ta.current) accept(ta.current, k); }}
              className={cn('flex gap-3 px-2 py-0.5 cursor-pointer', i === sel ? 'bg-bloomberg/20' : 'hover:bg-surface-1')}>
              <span className="text-text-primary">{k}</span><span className="ml-auto font-sans text-text-tertiary truncate">{d}</span>
            </div>))}
          <div className="px-2 py-0.5 font-sans text-[10px] text-text-tertiary border-t border-border">Tab / Enter to insert · ↑↓ to choose · Esc to close</div>
        </div>)}
    </div>
  );
}

// ── Main ────────────────────────────────────────────────────────────────────
export function CodeLab({ code, setCode, name, setName, strategyId, setStrategyId, canSave, canDeploy, onSaved }: {
  code: string; setCode: (c: string) => void; name: string; setName: (n: string) => void;
  strategyId: number | null; setStrategyId: (id: number | null) => void; canSave: boolean; canDeploy: boolean; onSaved: () => void;
}) {
  const [costs, setCosts] = useState<Costs>(COST_DEFAULTS);
  const [mc, setMc] = useState(MC_DEFAULTS);
  const [status, setStatus] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [check, setCheck] = useState<{ ok: boolean; error?: string; tradable?: string | null; account?: string; universe?: string[]; fx_hedge?: number | null; options?: any[]; mode?: string; params?: Record<string, any[]> } | null>(null);
  const [busy, setBusy] = useState(false);
  const [capital, setCapital] = useState(1_000_000);
  const [jobId, setJobId] = useState<string | null>(null);
  const [dialog, ask] = useConfirm();

  const ccy = check?.ok ? check.account ?? 'USD' : 'USD';
  // keep the header (account currency, universe size) current while editing, without running anything
  useEffect(() => {
    const t = setTimeout(() => { api('/api/v1/quant/code/check', { json: { code } }).then(setCheck).catch(() => {}); }, 800);
    return () => clearTimeout(t);
  }, [code]);
  // the server sandbox: big universes, and event-driven strategies with a PARAMS grid (a Python loop per bar per
  // parameter set is several times faster natively than in the browser)
  const combos = (chk: any) => Object.values(chk?.params ?? {}).reduce((n: number, v: any) => n * (Array.isArray(v) ? v.length : 1), 1);
  // server: a named universe, a long list, a parameter grid, or libraries the browser does not carry (torch, arch …)
  const onServer = (chk: any) => chk?.ok && (chk.tradable || (chk.universe?.length ?? 0) > UNIVERSE_LIMIT || (chk.mode === 'event' && combos(chk) > 1) || chk.runtime === 'full');

  // FX hedge: the code's FX_HEDGE unless overridden here (null = follow the code)
  const [hedge, setHedge] = useState<number | null>(null);
  const runCosts = useMemo(() => (hedge == null ? costs : { ...costs, fx_hedge: hedge }), [costs, hedge]);
  const runOnServer = async (chk: any) => {
    // TRADABLE_UNIVERSE or a long UNIVERSE list: run in the server sandbox as a background job (one cross-section)
    const job = await api('/api/v1/quant/code/jobs', { json: { code, costs: runCosts } });
    setJobId(job.id);
    let j = job;
    while (j.state === 'queued' || j.state === 'running') {
      setStatus(`${j.message} (${Math.round(j.elapsed_s ?? 0)} s)`);
      await new Promise((res) => setTimeout(res, 2000));
      j = await api(`/api/v1/quant/code/jobs/${job.id}`);
    }
    setJobId(null);
    if (j.state !== 'done') throw new Error(j.state === 'cancelled' ? 'Cancelled.' : (j.error || 'The job failed.'));
    return { ...j.result, benchmark_label: chk.benchmark };
  };

  // every run is stored for reopening and comparison (Runs & compare tab); a failed save never blocks the result
  const storeRun = (r: any, a: any) => {
    api('/api/v1/quant/code/runs', { json: { label: name || 'Strategy', result: r, analysis: a, code } })
      .then((j) => setNote(`Stored as run #${j.id} — reopen or compare it in Runs & compare.`)).catch(() => {});
  };

  // QuantConnect algorithms on QuantConnect's own LEAN engine (unmodified; platform daily data) as a server job
  const [lean, setLean] = useState<any>(null);
  const [leanOk, setLeanOk] = useState<any>(null);
  useEffect(() => { api('/api/v1/quant/lean/status').then(setLeanOk).catch(() => setLeanOk(null)); }, []);
  const runLean = async () => {
    setBusy(true); setErr(null); setNote(null); setLean(null); setResult(null); setAnalysis(null);
    try {
      const job = await api('/api/v1/quant/lean/jobs', { json: { code } });
      setJobId(job.id);
      let j = job;
      while (j.state === 'queued' || j.state === 'running') {
        setStatus(`${j.message} (${Math.round(j.elapsed_s ?? 0)} s)`);
        await new Promise((res) => setTimeout(res, 2000));
        j = await api(`/api/v1/quant/code/jobs/${job.id}`);
      }
      setJobId(null);
      if (j.state !== 'done') throw new Error(j.state === 'cancelled' ? 'Cancelled.' : (j.error || 'The LEAN run failed.'));
      setLean(j.result);
      const r = j.result?.codelab;
      if (r) {                     // LEAN's equity curve through the same results view, deep analysis and run store
        setResult(r);
        setStatus('Monte Carlo and deep analysis of the LEAN result…');
        const a = await api('/api/v1/quant/code/analyze', { json: { dates: r.dates, returns: r.returns, benchmark: r.benchmark, label: `${name || 'Strategy'} (LEAN)`, benchmark_label: r.benchmark_label, provenance: r.provenance, ...mc } });
        setAnalysis(a);
        storeRun(r, a);
      }
    } catch (e: any) { setErr(e.message); } finally { setStatus(null); setBusy(false); }
  };

  const isQc = code.includes('QCAlgorithm');
  const leanFirst = isQc && !!leanOk?.available;     // QuantConnect algorithms run on real LEAN whenever it is installed

  const cancelJob = async () => {
    if (jobId) await api(`/api/v1/quant/code/jobs/${jobId}`, { method: 'DELETE' }).catch(() => {});
  };

  const run = useCallback(async () => {
    setBusy(true); setErr(null); setNote(null); setLog([]); setResult(null); setAnalysis(null); setLean(null);
    let chk: any = null;
    try { chk = await api('/api/v1/quant/code/check', { json: { code } }); setCheck(chk); } catch { setCheck(null); }
    try {
      if (onServer(chk)) {
        const r = await runOnServer(chk);
        setResult(r);
        setStatus('Monte Carlo and deep analysis…');
        const a = await api('/api/v1/quant/code/analyze', { json: { dates: r.dates, returns: r.returns, benchmark: r.benchmark, label: name || 'Strategy', benchmark_label: chk.benchmark, provenance: r.provenance, ...mc } });
        setAnalysis(a);
        setStatus(null);
        storeRun(r, a);
        return;
      }
      const sh = getWorker(setStatus, (s) => setLog((l) => [...l.slice(-200), s]));
      await sh.ready;
      setStatus('Reading your code…');
      const { header } = await call(sh.worker, { type: 'prepare', code }, 'prepared', 60_000);
      setStatus(`Loading prices for ${header.universe.length} ticker${header.universe.length > 1 ? 's' : ''}…`);
      const data = await api(`/api/v1/quant/code/data?universe=${encodeURIComponent(header.universe.join(','))}&start=${header.start}&benchmark=${encodeURIComponent(header.benchmark)}&account=${encodeURIComponent(header.account || 'USD')}${header.options?.length ? `&options=${encodeURIComponent(JSON.stringify(header.options))}` : ''}${header.fundamentals?.length ? `&fundamentals=${encodeURIComponent(header.fundamentals.join(','))}` : ''}${header.custom?.length ? `&custom=${encodeURIComponent(header.custom.join(','))}` : ''}`);
      setStatus('Backtesting (net of costs)…');
      const { result: r } = await call(sh.worker, { type: 'run', code, data, costs: runCosts }, 'result', 600_000);
      setResult({ ...r, benchmark_label: header.benchmark });
      setStatus('Monte Carlo and deep analysis…');
      const a = await api('/api/v1/quant/code/analyze', { json: { dates: r.dates, returns: r.returns, benchmark: r.benchmark, label: name || 'Strategy', benchmark_label: header.benchmark, provenance: r.provenance, ...mc } });
      setAnalysis(a);
      // the slower checks (look-ahead re-runs, capacity, factor risk, signal research) fill in after the result is shown
      let full = { ...r, benchmark_label: header.benchmark };
      setStatus('Checking for look-ahead, capacity and factor risk…');
      try {
        const { checks } = await call(sh.worker, { type: 'checks' }, 'checked', 600_000);
        full = mergeChecks(full, checks);
        setResult(full);
      } catch (e: any) {
        setNote(`Result shown; the extra checks did not finish (${e.message}).`);
      }
      setStatus(null);
      storeRun(full, a);
    } catch (e: any) { setErr(e.message); setStatus(null); } finally { setBusy(false); }
  }, [code, runCosts, mc, name]);   // eslint-disable-line react-hooks/exhaustive-deps
  const primaryRun = leanFirst ? runLean : run;

  const save = async (asNew: boolean) => {
    setErr(null);
    const spec = { kind: 'code', name: name || 'Untitled strategy', code };
    try {
      const j = asNew || strategyId == null
        ? await api('/api/v1/quant/strategies', { json: { spec } })
        : await api(`/api/v1/quant/strategies/${strategyId}`, { method: 'PUT', json: { spec } });
      setStrategyId(j.id); setNote(`Saved “${j.name}”.`); onSaved();
    } catch (e: any) { setErr(e.message); }
  };
  const deploy = async () => {
    if (!(await ask({ title: `Deploy “${name || 'this strategy'}”?`, confirmLabel: 'Deploy',
      body: `Paper capital ${money(capital, ccy)}${ccy !== 'USD' ? ` (the account is kept in ${ccy})` : ''}. The server re-runs your code daily in a locked-down sandbox; no real orders are placed.` }))) return;
    setErr(null); setBusy(true); setStatus('Deploying…');
    try {
      const d = await api('/api/v1/quant/trader/deploy', { json: { spec: { kind: 'code', name: name || 'Code strategy', code, costs: runCosts }, capital, strategy_id: strategyId } });
      const label = ({ macro: 'Macro', fundamental: 'Fundamental', technical: 'Technical' } as Record<string, string>)[d.book] ?? 'Macro';
      setNote(`Deployed “${d.name}” to the ${label} Quant Trader — live from the session after ${d.deployed_at}.${d.preparing ? ' Its backtest is being prepared in the background (a large universe can take a few minutes) — it already shows in the trader as preparing.' : ''}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); setStatus(null); }
  };
  const loadTemplate = async (id: string) => {
    const t = TEMPLATES.find((x) => x.id === id);
    if (!t) return;
    if (code.trim() && code.trim() !== t.code.trim() && !(await ask({ title: `Replace the editor with “${t.name}”?`,
      body: `${t.about}\n\nYour current code is replaced (save it first if you want to keep it).`, confirmLabel: 'Replace' }))) return;
    setCode(t.code); setName(t.name); setStrategyId(null); setResult(null); setAnalysis(null); setErr(null);
    setNote(`Loaded the “${t.name}” template — press Run.`);
  };
  const set = (k: keyof Costs) => (e: React.ChangeEvent<HTMLInputElement>) => setCosts({ ...costs, [k]: Number(e.target.value) });
  const flag = (k: keyof Costs) => (e: React.ChangeEvent<HTMLInputElement>) => setCosts({ ...costs, [k]: e.target.checked ? 1 : 0 });

  return (
    <div className="space-y-3">
      {dialog}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Name" className="w-64"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="My strategy" /></Field>
            <Field label="Start from a template" className="w-56">
              <select className={inputCls} value="" onChange={(e) => loadTemplate(e.target.value)}>
                <option value="">Choose…</option>
                {TEMPLATES.map((t) => <option key={t.id} value={t.id} title={t.about}>{t.name}</option>)}
              </select></Field>
            <button onClick={primaryRun} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1 text-2xs bg-bloomberg text-bg disabled:opacity-50" aria-label="Run (Ctrl/⌘ + Enter)"
              title={leanFirst ? `Ctrl/⌘ + Enter · runs on QuantConnect's own LEAN engine (${leanOk.image}), unmodified, with the platform's free data` : 'Ctrl/⌘ + Enter'}>
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}Run{leanFirst ? ' (LEAN)' : ''}
            </button>
            {isQc && leanFirst && (
              <button onClick={run} disabled={busy} title="The platform's Python re-implementation of LEAN's API: adds look-ahead, capacity and Monte Carlo checks and paper deployment; approximates LEAN"
                className="inline-flex items-center gap-1 px-3 py-1 text-2xs border border-border text-text-secondary hover:border-bloomberg disabled:opacity-40">
                <Play className="w-3 h-3" />Run on built-in layer
              </button>)}
            {isQc && !leanFirst && leanOk && (
              <span className="text-[10px] text-amber" title={leanOk?.reason}>Real LEAN unavailable ({leanOk?.reason ?? 'checking…'}) — running on the built-in layer</span>)}
            {canSave && <button onClick={() => save(false)} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1 text-2xs border border-border hover:border-bloomberg"><Save className="w-3 h-3" />{strategyId ? 'Save' : 'Save as'}</button>}
            {canSave && strategyId && <button onClick={() => save(true)} disabled={busy} className="px-3 py-1 text-2xs border border-border hover:border-bloomberg">Save copy</button>}
            {canDeploy && (
              <span className="inline-flex items-end gap-1 ml-auto">
                <Field label={`Paper capital (${ccy})`} className="w-32"><input type="number" className={inputCls} value={capital} onChange={(e) => setCapital(Number(e.target.value))} /></Field>
                <button onClick={deploy} disabled={busy || check?.ok === false} title={check?.ok === false ? check.error : undefined}
                  className="inline-flex items-center gap-1 px-3 py-1 text-2xs border border-bloomberg text-bloomberg disabled:opacity-40"><Rocket className="w-3 h-3" />Deploy</button>
              </span>)}
          </div>
          <CodeEditor value={code} onChange={setCode} onRun={primaryRun} />
          {check && (
            <div className={cn('text-[10px] flex items-center gap-1', check.ok ? 'text-text-tertiary' : 'text-amber')}>
              {check.ok ? <ShieldCheck className="w-3 h-3" /> : <ShieldAlert className="w-3 h-3" />}
              {check.ok
                ? `${check.tradable ? `Tradable universe '${check.tradable}'` : `${check.universe?.length ?? 0} ticker${(check.universe?.length ?? 0) === 1 ? '' : 's'}`}${check.options?.length ? ` + ${check.options.length} option${check.options.length === 1 ? '' : 's'} (${check.options.map((o: any) => o.name).join(', ')})` : ''} · account in ${ccy} · ${onServer(check) ? 'runs on the server as a sandboxed job' : 'runs in your browser'}; deployable.`
                : `Runs here, but can't be deployed: ${check.error}`}
            </div>)}
          {(check as any)?.qc && <QcReport qc={(check as any).qc} />}
          {leanFirst && (
            <div className="text-[10px] text-bloomberg">QuantConnect algorithm — <b>Run</b> executes it unmodified on QuantConnect's own LEAN engine with the platform's free data (US equities, point-in-time S&amp;P 500 universes with SEC fundamentals, crypto, FX, custom data from your get_source). The report below is the built-in layer's; it does not limit a LEAN run.</div>)}
          {lean && <LeanResult r={lean} />}
          {leanFirst && <LeanOptimizer code={code} disabled={busy} />}
          <CustomData />
          {status && <div className="flex items-center gap-2 text-2xs text-text-secondary"><Loader2 className="w-3 h-3 animate-spin" />{status}
            {jobId && <button onClick={cancelJob} className="ml-2 px-2 py-0.5 border border-border hover:border-red hover:text-red">Cancel</button>}</div>}
          <ErrorNote msg={err} />
          {note && <div className="px-3 py-2 border border-green/40 bg-green/5 text-xs text-green">{note}</div>}
          {log.length > 0 && (
            <details open className="text-[11px]"><summary className="cursor-pointer text-text-tertiary inline-flex items-center gap-1"><Terminal className="w-3 h-3" />Output</summary>
              <pre className="mt-1 max-h-40 overflow-auto bg-surface-1 border border-border p-2 font-mono text-text-secondary">{log.join('\n')}</pre></details>)}
        </div>
        <div className="space-y-3">
          <div className="p-3 bg-surface-1 border border-border space-y-2">
            <div className="text-xs font-semibold text-text-primary">Costs & execution</div>
            <div className="grid grid-cols-2 gap-2">
              <Field label={`Capital (${ccy})`} hint={`In the account currency (ACCOUNT_CURRENCY = "${ccy}"). Size matters: market impact grows with the square root of your share of daily traded value`}><input type="number" className={inputCls} value={costs.capital} onChange={set('capital')} /></Field>
              <Field label="Commission (bp / side)" hint="Basis points of traded notional, each side. 0.35 bp ≈ $0.0035/share at $100"><input type="number" step={0.05} className={inputCls} value={costs.commission_bps} onChange={set('commission_bps')} /></Field>
              <Field label="Spread multiplier (×)" hint="A multiplier, not basis points: scales the modelled half-spread (from each asset's volatility and dollar volume)"><input type="number" step={0.25} className={inputCls} value={costs.spread_mult} onChange={set('spread_mult')} /></Field>
              <Field label="Impact (bp × √%ADV)" hint="Basis points × √(% of 63-day dollar volume traded). 11.2 = AQR live-trade calibration (Frazzini, Israel & Moskowitz 2018)"><input type="number" step={0.5} className={inputCls} value={costs.impact_coef_bps} onChange={set('impact_coef_bps')} /></Field>
              <Field label="Borrow fee (annual, decimal)" hint="0.003 = 0.3% a year on short market value (general collateral)"><input type="number" step={0.001} className={inputCls} value={costs.borrow_fee} onChange={set('borrow_fee')} /></Field>
              <Field label="Margin spread (annual, decimal)" hint={`Negative cash pays the ${ccy} cash rate plus this; 0.01 = 1%`}><input type="number" step={0.0025} className={inputCls} value={costs.financing_spread} onChange={set('financing_spread')} /></Field>
              <Field label="No-trade band (fraction of NAV)" hint="Skip trades smaller than this fraction of NAV; 0.0025 = 0.25%"><input type="number" step={0.0025} className={inputCls} value={costs.no_trade_band} onChange={set('no_trade_band')} /></Field>
              <Field label="Cash yield cut (annual, decimal)" hint={`Positive cash earns the ${ccy} short rate minus this (US T-bills for USD). 0 = the full rate (institutional); many retail brokers pay far less`}><input type="number" step={0.0025} className={inputCls} value={costs.cash_spread} onChange={set('cash_spread')} /></Field>
              <Field label="FX conversion (bp)" hint={`Basis points of traded value, charged only when a listing's currency differs from the account's (${ccy}). ≈1–2 bp at an institutional broker for majors; retail platforms often charge 25–100 bp`}><input type="number" step={0.5} className={inputCls} value={costs.fx_cost_bps} onChange={set('fx_cost_bps')} /></Field>
              <Field label="FX hedge ratio (0–1)" hint={`Share of each foreign currency's exposure hedged with daily-settled forwards: removes that share of the currency's moves and earns/pays the interest differential (${ccy} rate − foreign rate). Blank = the code's FX_HEDGE (${check?.ok && check.fx_hedge != null ? check.fx_hedge : 'not set: 0'}). Currencies with no free rate history stay unhedged`}>
                <input type="number" step={0.25} min={0} max={1} className={inputCls} value={hedge ?? ''} placeholder={check?.ok && check.fx_hedge != null ? String(check.fx_hedge) : '0'}
                  onChange={(e) => setHedge(e.target.value === '' ? null : Math.min(1, Math.max(0, Number(e.target.value))))} /></Field>
              <Field label="Hedge cost (bp / yr)" hint="Forward-roll dealing costs per year on the hedged notional; the interest differential itself is modelled separately"><input type="number" step={5} className={inputCls} value={costs.fx_hedge_cost_bps} onChange={set('fx_hedge_cost_bps')} /></Field>
              <Field label="Treaty cap on dividend tax" hint="Withholding = the listing country's statutory non-resident rate, capped at this treaty rate. 0.15 is the usual treaty rate for portfolio dividends; 1 = no treaty relief"><input type="number" step={0.05} className={inputCls} value={costs.wht_treaty_cap} onChange={set('wht_treaty_cap')} /></Field>
              <label className="flex items-center gap-1 text-[10px] text-text-secondary self-end" title="Tax withheld at source on dividends of listings in another currency than the account's"><input type="checkbox" checked={!!costs.dividend_wht} onChange={flag('dividend_wht')} />Dividend withholding tax</label>
              <label className="flex items-center gap-1 text-[10px] text-text-secondary self-end" title="Orders rounded to whole board lots (JP 100, HK per stock, TW 1,000 …) at the capital above; small books can't hold some names"><input type="checkbox" checked={!!costs.board_lots} onChange={flag('board_lots')} />Whole board lots</label>
              <Field label="Broker fee model" hint={BROKERS.map((b) => `${b.name}: ${b.note}`).join('\n')}>
                <select className={inputCls} value="" onChange={(e) => { const b = BROKERS.find((x) => x.id === e.target.value); if (b) { setCosts({ ...costs, ...b.set }); setNote(`Costs set to ${b.name}: ${b.note}.`); } }}>
                  <option value="">Choose a broker…</option>
                  {BROKERS.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select></Field>
              <Field label={`Per share (${ccy})`} hint="Broker commission per share (0 = none); uses traded share prices"><input type="number" step={0.0005} className={inputCls} value={costs.commission_per_share} onChange={set('commission_per_share')} /></Field>
              <Field label={`Min per order (${ccy})`} hint="Minimum commission per order"><input type="number" step={0.05} className={inputCls} value={costs.commission_min} onChange={set('commission_min')} /></Field>
              <Field label="Max per order (fraction)" hint="Commission cap as a fraction of the order's value; 0.01 = 1%; 0 = no cap"><input type="number" step={0.001} className={inputCls} value={costs.commission_max_pct} onChange={set('commission_max_pct')} /></Field>
              <Field label="Crypto fee (bp)" hint="Exchange taker fee on crypto trades: Binance ≈ 10, Kraken Pro ≈ 25–40, Coinbase Advanced ≈ 40–60 (small accounts)"><input type="number" step={1} className={inputCls} value={costs.crypto_fee_bps} onChange={set('crypto_fee_bps')} /></Field>
              <Field label="Fill at" hint="Orders decided at a close fill at the next session's open (default), its VWAP (≈ average of open, high, low and close) or its close (market-on-close)">
                <select className={inputCls} value={costs.exec_price} onChange={(e) => setCosts({ ...costs, exec_price: Number(e.target.value) })}>
                  <option value={0}>next open</option><option value={1}>next-day VWAP</option><option value={2}>next close</option></select></Field>
              <Field label="Max participation (of ADV)" hint="Largest share of an asset's average daily traded value you trade in one day; bigger orders fill over several days. 0.1 = 10%; 0 = no limit"><input type="number" step={0.01} className={inputCls} value={costs.max_participation} onChange={set('max_participation')} /></Field>
              <Field label="Maintenance margin" hint="Margin call when NAV < this × gross stock value (+ 15% of written options' notional): every position is cut. 0.25 = Reg-T"><input type="number" step={0.05} className={inputCls} value={costs.maintenance_margin} onChange={set('maintenance_margin')} /></Field>
              <label className="flex items-center gap-1 text-[10px] text-text-secondary self-end" title="Stock borrow costs more for thinly traded names: ≥$100m/day the base fee, $20–100m 0.75%, $5–20m 2%, under $5m 5% a year"><input type="checkbox" checked={!!costs.borrow_tiers} onChange={flag('borrow_tiers')} />Hard-to-borrow tiers</label>
              <Field label="Delisting haircut (fraction)" hint="A held listing that ends is settled at its last close × (1 − this)"><input type="number" step={0.05} className={inputCls} value={costs.delist_haircut} onChange={set('delist_haircut')} /></Field>
              <button onClick={() => setCosts(COST_DEFAULTS)} className="self-end text-[10px] underline text-text-tertiary">reset to research defaults</button>
            </div>
          </div>
          <div className="p-3 bg-surface-1 border border-border space-y-2">
            <div className="text-xs font-semibold text-text-primary">Monte Carlo</div>
            <div className="grid grid-cols-3 gap-2">
              <Field label="Years"><input type="number" className={inputCls} value={mc.mc_years} onChange={(e) => setMc({ ...mc, mc_years: Number(e.target.value) })} /></Field>
              <Field label="Max lev." hint="Leverage cap for the sizing recommendation (Reg-T margin ≈ 2×)"><input type="number" step={0.5} className={inputCls} value={mc.max_leverage} onChange={(e) => setMc({ ...mc, max_leverage: Number(e.target.value) })} /></Field>
              <Field label="DD limit" hint="Sizing keeps P(drawdown beyond this) ≤ 5%"><input type="number" step={0.05} className={inputCls} value={mc.dd_limit} onChange={(e) => setMc({ ...mc, dd_limit: Number(e.target.value) })} /></Field>
            </div>
          </div>
          <ApiHelp />
          <UniverseHelp />
        </div>
      </div>
      {result && <CodeResults r={result} a={analysis} />}
    </div>
  );
}

function ApiHelp() {
  return (
    <details className="p-3 bg-surface-1 border border-border text-[11px] text-text-secondary">
      <summary className="cursor-pointer text-xs font-semibold text-text-primary">What your code can use</summary>
      <ul className="mt-2 space-y-1 list-disc pl-4">
        <li><code>data.close/open/high/low/volume</code> — DataFrames, dates × UNIVERSE, adjusted for splits and dividends.</li>
        <li>Prices are in the account currency (<code>ACCOUNT_CURRENCY</code>, default USD), converted at as-of FX: closes at that day's rate, opens at the previous close.</li>
        <li><code>data.rf</code> daily cash rate of the account currency · <code>data.vix</code> VIX close · <code>data.account_currency</code>.</li>
        <li><code>data.info</code> — tickers × country, currency, sector, region, market_class (e.g. <code>data.info["sector"]</code> to neutralise by sector) · <code>data.members</code> for SP500_PIT.</li>
        <li>Helpers: <code>momentum(px, n, skip)</code>, <code>ewma_vol(px, halflife)</code>, <code>vol_target(w, px, target)</code>, <code>normalize_gross(w)</code>, <code>hold_monthly(w)</code>, <code>hold_weekly(w)</code>; <code>np</code>, <code>pd</code>, <code>math</code>.</li>
        <li>Universe: <code>TRADABLE_UNIVERSE = "GLOBAL"</code> (or a country, region or <code>"JP+HK"</code> — see below) trades that universe in a server job. Without it, <code>UNIVERSE</code> is your own list of any listings (VOD.L, 7203.T, 0700.HK…): up to {UNIVERSE_LIMIT} run in your browser, longer lists on the server. No live trading.</li>
        <li><code>data.observed</code> flags actual bars. Return all-NaN rows between decisions to hold and drift; populated rows request a rebalance at the next observed open.</li>
        <li>Optional: <code>ACCOUNT_CURRENCY</code>, <code>FX_HEDGE</code> (0–1), <code>START</code>, <code>BENCHMARK</code> (converted to the account currency), <code>PARAMS</code> (≤ 48 combinations, walk-forward), <code>HOLDOUT</code>.</li>
        <li><b>Options</b>: <code>OPTIONS = [{'{'}"underlying": "SPY", "type": "put", "moneyness": 0.95{'}'}]</code> adds a column <code>SPY_P95_1M</code> (keys: <code>type</code> call/put, <code>moneyness</code> K/S or <code>delta</code> 0.05–0.95, <code>expiry</code> monthly/weekly/quarterly, <code>months</code>, or <code>tenor_days</code>; up to 12). Its weight is the <i>underlying notional</i> as a fraction of NAV (−1.0 = write on 100% of NAV); expiring contracts settle at intrinsic value and a standing weight rolls into the next contract. <code>data.opt["delta" | "elasticity" | "iv" | "strike" | "dte" | "spot" | "roll"]</code>; <code>on_rolls(w, data, name)</code> decides only at expiries. Prices are modelled (Black–Scholes on the VIX family where it exists, else realised vol × the market's implied/realised ratio, with skew) — not quotes; see the library's Options strategies.</li>
        <li>Portfolio construction: <code>cov_shrink(returns)</code> (Ledoit–Wolf), <code>optimize(expected, cov, risk_aversion, max_weight, long_only, gross, net, prev, turnover_penalty, groups, group_max, exposures, factor_bounds)</code> (an exact quadratic programme; e.g. <code>exposures=style_exposures(data, date), factor_bounds={'{'}"momentum": (-0.1, 0.1){'}'}</code>), <code>min_variance(cov)</code>, <code>risk_parity(cov)</code>.</li>
        <li><b>Indicators</b>: <code>sma ema wma hma rsi macd bollinger atr adx stochastic williams_r cci roc zscore donchian keltner obv mfi vwap beta drawdown</code> (whole frames at once, causal). Scheduling: <code>rebalance(w, "W" | "M" | "Q" | n)</code>. Dynamic universe: <code>top_liquid(data, 100)</code>. Custom charts: <code>plot("Chart", "series", values)</code>.</li>
        <li><b>Asset classes</b>: stocks and ETFs (any market), crypto (<code>BTC-USD</code>, <code>ETH-USD</code> — every day, exchange fee), forex pairs (<code>EURUSD=X</code>, <code>JPY=X</code> — spot + carry, ≈5% margin) and modelled options (<code>OPTIONS</code>). Futures are refused (no roll-adjusted free data).</li>
        <li><b>Fundamentals</b>: <code>FUNDAMENTALS = True</code> (or a list: book_to_price, earnings_yield, roe, gross_profitability, fcf_yield, market_cap, eps_ttm, …) adds point-in-time SEC data as <code>data.fund["…"]</code> — each figure from the day after it was filed, as first filed (US filers).</li>
        <li><b>Event-driven</b>: define <code>on_bar(ctx, **params)</code> instead of <code>strategy</code>. It runs after every close and sees only the past: <code>ctx.history("close", n)</code>, <code>ctx.positions</code>, <code>ctx.nav</code>, <code>ctx.cash</code>, <code>ctx.fills</code>, <code>ctx.state</code> (yours). Orders: <code>ctx.target({'{'}"SPY": 0.5{'}'})</code>, <code>ctx.limit("SPY", 1.0, 400)</code>, <code>ctx.stop("SPY", 0.0, 380)</code>, <code>ctx.stop_limit(…)</code>, <code>ctx.trailing_stop("SPY", 0.0, 0.1)</code>, <code>ctx.bracket("SPY", 0.0, 450, 380)</code>, <code>ctx.cancel()</code>, <code>ctx.plot(…)</code>. Optional <code>setup(data, **params)</code> precomputes indicators (read with <code>ctx.pre(name)</code>; checked for look-ahead).</li>
        <li>Optional <code>signal(data, **params)</code> returning scores (dates × tickers): the lab reports its information coefficient by horizon, quintile returns and turnover.</li>
        <li>Every run is checked for look-ahead (decisions recomputed from earlier data must match) and, with PARAMS, for overfitting (PBO); you also get attribution, today's ex-ante risk with crisis stress tests and a capacity curve.</li>
        <li><b>Python</b>: ordinary Python — your own classes and inheritance, decorators, <code>@dataclass</code>, properties, <code>super()</code> — and numpy, pandas, scipy, scikit-learn, statsmodels plus the standard library without I/O (math, statistics, collections, itertools, functools, datetime, re, json…), in the browser and when deployed. Not available: files, network, <code>os</code>/<code>sys</code>/<code>subprocess</code>, <code>eval</code>/<code>exec</code>, and the engine's internals (they hold future prices).</li>
        <li><b>Multi-file QuantConnect projects</b>: paste each extra file below a line <code># file: alpha.py</code> (folders: <code># file: alphas/rsi.py</code> → <code>import alphas.rsi</code>); <code>main.py</code> is everything above the first marker.</li>
        <li><b>Real LEAN</b>: a QuantConnect algorithm runs on QuantConnect's own engine by default (Run) — exact LEAN behaviour on the platform's free daily data: US equities, point-in-time S&amp;P 500 universes (LEAN's coarse and SPY-constituent files) with SEC fundamentals in <code>Fundamental</code>, crypto, FX, and custom data fetched from the algorithm's own <code>get_source</code>. Minute / hour requests are served as daily (the run says so). <b>Run on built-in layer</b> uses the Python re-implementation (paper deployment, look-ahead and Monte Carlo checks).</li>
        <li><b>Custom data</b>: upload a CSV (below the editor) and use <code>CUSTOM_DATA = ["name"]</code> → <code>data.custom["name"]</code> (as of each session; <code>_new</code> marks fresh rows).</li>
        <li><b>Server runs</b> happen in a throwaway Docker container — no network, read-only filesystem, no capabilities, unprivileged — or a process sandbox when Docker is not running. <code>print()</code> shows in Output.</li>
      </ul>
    </details>
  );
}

function UniverseHelp() {
  const [cat, setCat] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = () => { if (!cat) api('/api/v1/quant/code/universes').then(setCat).catch((e) => setErr(e.message)); };
  return (
    <details className="p-3 bg-surface-1 border border-border text-[11px] text-text-secondary" onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) load(); }}>
      <summary className="cursor-pointer text-xs font-semibold text-text-primary">Universes & currencies</summary>
      <ErrorNote msg={err} />
      {!cat && !err && <div className="mt-2 text-text-tertiary">Loading…</div>}
      {cat && (
        <div className="mt-2 space-y-2">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-0.5">TRADABLE_UNIVERSE · {cat.total.toLocaleString()} stocks</div>
            <ul className="space-y-0.5">{cat.universes.map((u: any) => (
              <li key={u.name}><code>"{u.name}"</code>{u.count != null && <span className="text-text-tertiary"> · {u.count.toLocaleString()}</span>} — {u.about}</li>))}</ul>
            <div className="mt-1">…or a listing country, alone or combined: <code>"JP"</code>, <code>"GB+DE+FR"</code>, <code>["HK", "CN"]</code>.</div>
            <div className="mt-1 flex flex-wrap gap-1 font-mono">{cat.countries.map((c: any) => (
              <span key={c.code} title={`${c.name ?? c.code} · quoted in ${c.currencies.join(', ')}`} className="px-1 border border-border">{c.code} {c.count}</span>))}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-0.5">ACCOUNT_CURRENCY — prices, NAV, costs and cash interest in that currency</div>
            <table className="w-full"><tbody>{cat.account_currencies.map((c: any) => (
              <tr key={c.code} className="border-t border-border-subtle align-top">
                <td className="pr-2 font-mono">{c.code}</td>
                <td className={cn(!c.known && 'text-amber')}>{c.known ? `${c.source}${c.kind === 'proxy' ? ' (pegged: proxy)' : ''}${c.stale_since ? ` · no data since ${c.stale_since}` : ''}` : 'no free cash-rate series: cash earns 0'}</td>
              </tr>))}</tbody></table>
          </div>
        </div>)}
    </details>
  );
}

// ── Results (shared with the strategy library) ──────────────────────────────
function curve(dates: string[], rets: number[], bench?: number[] | null, gross?: number[] | null, base?: number[] | null) {
  const n = dates.length, step = Math.max(1, Math.ceil(n / 900));
  let e = 1, g = 1, b = 1, q = 1;
  const rows: any[] = [];
  for (let i = 0; i < n; i++) {
    e *= 1 + rets[i]; if (gross) g *= 1 + gross[i]; if (bench) b *= 1 + (bench[i] || 0); if (base) q *= 1 + (base[i] || 0);
    if (i % step === 0 || i === n - 1) rows.push({ date: dates[i], net: +e.toFixed(4), ...(gross ? { gross: +g.toFixed(4) } : {}),
      ...(bench ? { bench: +b.toFixed(4) } : {}), ...(base ? { base: +q.toFixed(4) } : {}) });
  }
  return rows;
}

const RESULT_TABS = [['summary', 'Summary'], ['trades', 'Trades'], ['validation', 'Validation'], ['risk', 'Risk'], ['attribution', 'Attribution'],
  ['charts', 'Charts'], ['signal', 'Signal'], ['deep', 'Deep report']] as const;
type ResultTab = (typeof RESULT_TABS)[number][0];

export function CodeResults({ r, a }: { r: any; a: any | null }) {
  const m = r.metrics ?? {}, g = r.metrics_gross, c = r.costs, b = r.benchmark_metrics, opt = r.optimisation ?? {};
  const rows = useMemo(() => curve(r.dates, r.returns, r.benchmark, r.gross, r.baseline_returns), [r]);
  const ew = r.baseline_equal_weight, prov = r.provenance ?? {}, ex = r.execution, reg = a?.registry;
  const mc = a?.monte_carlo;
  const [tab, setTab] = useState<ResultTab>('summary');
  return (
    <div className="space-y-3">
      <KpiStrip cols={8} items={[
        { label: 'CAGR (net)', value: spct(m.cagr), sub: g ? `gross ${spct(g.cagr)}` : undefined, tone: tone(m.cagr), accent: true },
        { label: 'Sharpe (net)', value: num(m.sharpe), sub: g ? `gross ${num(g.sharpe)}` : undefined, tone: tone(m.sharpe) },
        { label: 'Max drawdown', value: pct(m.max_drawdown), tone: 'down' },
        { label: 'Volatility', value: pct(m.vol) },
        { label: 'Trading costs /yr', value: c ? pct(c.total_trading, 2) : '—', sub: c ? `turnover ${num(c.turnover, 1)}×/yr` : undefined, tone: c && c.total_trading > 0.01 ? 'warn' : null },
        { label: 'Calmar', value: num(m.calmar) },
        { label: ew ? 'Equal-weight universe' : (r.benchmark_label || 'Benchmark'), value: ew ? spct(ew.cagr) : b ? spct(b.cagr) : '—',
          sub: ew ? `same names & costs · Sharpe ${num(ew.sharpe)}` : b ? `Sharpe ${num(b.sharpe)} · DD ${pct(b.max_drawdown, 0)}` : undefined,
          tone: ew && m.cagr != null && ew.cagr != null && ew.cagr > m.cagr ? 'warn' : null },
        { label: 'Record', value: opt.walk_forward ? 'Walk-forward' : 'Exploratory', sub: `${r.dates[0]} → ${r.dates[r.dates.length - 1]}` },
      ]} />
      <Verdict r={r} reg={reg} />
      <div className="flex flex-wrap border border-border w-fit" role="tablist" aria-label="Result sections">
        {RESULT_TABS.filter(([k]) => (k !== 'signal' || r.signal) && (k !== 'trades' || r.trades) && (k !== 'charts' || (r.charts && Object.keys(r.charts).length))).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={cn('px-3 py-1 text-2xs', tab === k ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>{l}</button>))}
      </div>
      {tab === 'summary' && (<>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div className="xl:col-span-2">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Growth of {r.account_currency && r.account_currency !== 'USD' ? `1 ${r.account_currency}` : '$1'} — net of all costs{r.gross ? ', before costs' : ''}{r.baseline_returns ? ', equal-weight universe (same costs)' : ''}{r.benchmark ? `, and ${r.benchmark_label || 'benchmark'}` : ''}</div>
          <LineChart rows={rows} x="date" height={260} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
            lines={[{ key: 'net', label: 'Net', color: CATEGORICAL[0] }, ...(r.gross ? [{ key: 'gross', label: 'Before costs', color: CATEGORICAL[3] }] : []),
              ...(r.baseline_returns ? [{ key: 'base', label: 'Equal-weight universe', color: CATEGORICAL[2] }] : []),
              ...(r.benchmark ? [{ key: 'bench', label: `${r.benchmark_label || 'Benchmark'} (frictionless)`, color: CATEGORICAL[6] }] : [])]} />
        </div>
        {c ? (
          <div className="space-y-2">
            <BarList title="Average cost per year (% of capital)" fmt={(v) => `${(v * 100).toFixed(2)}%`}
              data={[{ label: 'Market impact', value: c.impact }, { label: 'Spread', value: c.spread }, { label: 'Commission', value: c.commission },
                { label: 'Fees, taxes & FX', value: c.fees, note: 'SEC fee on US sales, stamp duties and transaction taxes by listing country, FX conversion on cross-currency trades' }, { label: 'Borrow', value: c.borrow },
                ...(c.dividend_tax ? [{ label: 'Dividend withholding', value: c.dividend_tax, note: 'Tax withheld at source on foreign dividends' }] : []),
                ...(c.hedge_pnl ? [{ label: 'FX hedge (net)', value: -c.hedge_pnl, note: 'Positive = the hedge cost money (currency gains given up, rate differential, roll costs); negative = it earned' }] : []),
                { label: 'Financing (net)', value: -c.financing_net, note: 'Positive = paid; negative = interest earned on cash' }]} />
            <div className="text-[10px] text-text-tertiary">Average long {pct(c.avg_long, 0)} · short {pct(c.avg_short, 0)} of capital.</div>
            {r.weights_last && Object.keys(r.weights_last).length > 0 && (
              <BarList title="Latest target (what the model wants)" diverging fmt={(v) => `${(v * 100).toFixed(1)}%`}
                data={Object.entries(r.weights_last).sort((x: any, y: any) => Math.abs(y[1]) - Math.abs(x[1])).slice(0, 12).map(([k, v]) => {
                  const isOpt = !!r.provenance?.market_rules?.options?.[k];
                  return { label: isOpt ? `${k} (notional)` : k, value: v as number,
                    sub: r.holdings_last ? `held ${((r.holdings_last[k] ?? 0) * 100).toFixed(1)}%${isOpt ? ' in premium' : ''}` : undefined };
                })} />)}
            {r.holdings_last && <div className="text-[10px] text-text-tertiary">“held” is the simulated account after drift and unfilled orders — a target is not a position.</div>}
            {r.exposure?.currency && Object.keys(r.exposure.currency).length > 1 && (
              <BarList title={`Currency exposure (account ${r.account_currency ?? 'USD'})`} diverging fmt={(v) => `${(v * 100).toFixed(1)}%`}
                data={Object.entries(r.exposure.currency).slice(0, 10).map(([k, v]) => ({ label: k, value: v as number }))} />)}
            {r.exposure?.country && Object.keys(r.exposure.country).length > 1 && (
              <BarList title="Holdings by listing country" diverging fmt={(v) => `${(v * 100).toFixed(1)}%`}
                data={Object.entries(r.exposure.country).slice(0, 10).map(([k, v]) => ({ label: k, value: v as number }))} />)}
          </div>
        ) : r.weights_last && (
          <BarList title="Current allocation" fmt={(v) => `${(v * 100).toFixed(1)}%`}
            data={Object.entries(r.weights_last).map(([k, v]) => ({ label: k, value: v as number }))} />)}
      </div>
      <RecordPanel r={r} prov={prov} ex={ex} reg={reg} />
        </>)}
      {tab === 'validation' && (
        <div className="space-y-3">
          <Validation v={r.validation} />
          {opt.walk_forward && opt.chosen && <Optimisation opt={opt} m={m} />}
          <Heatmap opt={opt} />
          {opt.variants && <Variants opt={opt} />}
          <Capacity c={r.capacity} />
        </div>)}
      {tab === 'risk' && (
        <div className="space-y-3">
          <Risk r={r.risk} />
          {a?.factor_lens && <FactorLens f={a.factor_lens} />}
          {mc ? <MonteCarlo mc={mc} /> : a === null && <div className="flex items-center gap-2 text-2xs text-text-tertiary"><Loader2 className="w-3 h-3 animate-spin" />Monte Carlo…</div>}
        </div>)}
      {tab === 'attribution' && <Attribution a={r.attribution} />}
      {tab === 'trades' && <Trades t={r.trades} />}
      {tab === 'charts' && <Charts c={r.charts} />}
      {tab === 'signal' && <Signal s={r.signal} />}
      {tab === 'deep' && (a?.deep ? <DeepReport d={a.deep} />
        : <div className="flex items-center gap-2 text-2xs text-text-tertiary"><Loader2 className="w-3 h-3 animate-spin" />Deep analysis…</div>)}
    </div>
  );
}

/** One line on whether to trust the result: look-ahead, overfitting, out-of-sample, baseline, risk-adjusted return,
 *  capacity — each a pass or a named problem. */
function Verdict({ r, reg }: { r: any; reg: any }) {
  const v = r.validation ?? {}, m = r.metrics ?? {}, ew = r.baseline_equal_weight, opt = r.optimisation ?? {};
  const checks: { label: string; ok: boolean | null; why: string; critical?: boolean }[] = [
    { label: 'No look-ahead', ok: r.checks_pending ? null : v.causality?.passed ?? null, critical: true,
      why: r.checks_pending ? 'checking…' : v.causality?.passed === false ? 'decisions use future data — the result cannot be trusted' : v.causality?.passed ? 'decisions only use past data' : 'not checked' },
    ...(v.pbo?.pbo != null ? [{ label: 'Not overfit (PBO)', ok: v.pbo.pbo < 0.5, why: `probability of overfitting ${pct(v.pbo.pbo, 0)}` }] : []),
    ...(reg?.deflated_sharpe != null ? [{ label: 'Survives multiple testing', ok: reg.deflated_sharpe >= 0.9,
      why: `deflated Sharpe ${pct(reg.deflated_sharpe, 0)} after ${reg.distinct_trials} trial${reg.distinct_trials === 1 ? '' : 's'}` }] : []),
    { label: 'Out-of-sample record', ok: !!opt.walk_forward, why: opt.walk_forward ? 'walk-forward' : 'single specification over the full history (exploratory)' },
    ...(ew ? [{ label: 'Beats equal weight', ok: m.cagr != null && ew.cagr != null && m.cagr > ew.cagr,
      why: `${spct(m.cagr)} vs ${spct(ew.cagr)} for the same names, same costs` }] : []),
    { label: 'Worth the risk', ok: m.sharpe != null ? m.sharpe >= 0.5 : null, why: `Sharpe ${num(m.sharpe)} above cash, after costs` },
    ...(r.capacity ? [{ label: 'Scales', ok: (r.capacity.capacity ?? 0) >= 1e7, why: r.capacity.capacity ? `capacity ≈ ${usd(r.capacity.capacity)}` : 'loses half its Sharpe below $1m' }] : []),
  ];
  const known = checks.filter((c) => c.ok !== null);
  const passed = known.filter((c) => c.ok).length;
  const fatal = checks.some((c) => c.critical && c.ok === false);
  // "promising" needs enough evidence: at least four checks run and only one failed
  const level = fatal ? 'fatal' : known.length && passed === known.length ? 'pass' : known.length >= 4 && passed === known.length - 1 ? 'caveat' : 'weak';
  const tone = { fatal: 'border-red/60 bg-red/5', pass: 'border-green/50 bg-green/5', caveat: 'border-amber/50 bg-amber/5', weak: 'border-red/40 bg-red/5' }[level];
  const head = { fatal: 'Do not trust this result', pass: 'Passes every check', caveat: 'Promising, with one caveat', weak: 'Weak evidence' }[level];
  return (
    <div className={cn('p-2.5 border text-[11px] space-y-1.5', tone)}>
      <div className="text-xs font-semibold text-text-primary">{head} <span className="font-normal text-text-tertiary">— {passed} of {known.length} checks passed{r.checks_pending ? ' · look-ahead, capacity and factor checks still running…' : ''}</span></div>
      <div className="flex flex-wrap gap-1">
        {checks.map((c) => (
          <span key={c.label} title={c.why} className={cn('px-1.5 py-0.5 border', c.ok === null ? 'border-border text-text-tertiary' : c.ok ? 'border-green/50 text-green' : 'border-red/50 text-red')}>
            {c.ok === null ? '·' : c.ok ? '✓' : '✗'} {c.label}{c.ok === false ? `: ${c.why}` : ''}</span>))}
      </div>
    </div>
  );
}


function Optimisation({ opt, m }: { opt: any; m: any }) {
  const ib = opt.in_sample_best;
  const changes = opt.chosen.filter((c: any, i: number) => i === 0 || JSON.stringify(c.params) !== JSON.stringify(opt.chosen[i - 1].params));
  return (
    <div className="p-3 bg-surface-1 border border-border text-[11px] space-y-1">
      <div className="text-xs font-semibold text-text-primary">Walk-forward optimisation</div>
      <div className="text-text-secondary">
        {opt.grid?.length ?? '?'} parameter sets; each January the set with the best long-run growth on data up to then was traded for the year, in one continuous account (switches trade from current holdings and pay the costs{opt.switches ? ` — ${opt.switches.length} switch${opt.switches.length === 1 ? '' : 'es'}` : ''}).
        Out-of-sample from {opt.oos_start}: CAGR {spct(m.cagr)}, Sharpe {num(m.sharpe)}.
        {ib && <> Picking the best set with hindsight would have shown CAGR {spct(ib.cagr)} / Sharpe {num(ib.sharpe)} — the gap is the overfitting a single backtest hides.</>}
      </div>
      <div className="flex flex-wrap gap-1 font-mono">
        {changes.map((c: any) => <span key={c.year} className="px-1.5 py-0.5 border border-border">{c.year}: {Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join(', ')}</span>)}
      </div>
    </div>
  );
}

function RecordPanel({ r, prov, ex, reg }: { r: any; prov: any; ex: any; reg: any }) {
  const h = r.holdout;
  return (
    <div className="p-3 bg-surface-1 border border-border text-[11px] space-y-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <div className="text-xs font-semibold text-text-primary">What this record is</div>
        <span className="px-1.5 border border-border text-text-secondary">{reg?.record_label || prov.record_type || 'backtest'}</span>
        {reg && <span className="text-text-tertiary">trial {reg.distinct_trials} of this family ({reg.runs} runs) · deflated Sharpe {reg.deflated_sharpe != null ? pct(reg.deflated_sharpe, 0) : '—'} probability of real skill after all trials</span>}
      </div>
      {prov.rf_known === false && <div className="text-amber">{prov.cash_rate?.note || `The ${prov.account_currency || 'USD'} cash rate was unavailable`}: cash earned 0% and Sharpe is on raw returns.</div>}
      {prov.cash_rate?.kind === 'proxy' && <div className="text-text-secondary">{prov.cash_rate.note}.</div>}
      {prov.cash_rate?.stale_since && <div className="text-amber">The {prov.account_currency} cash rate has no observation since {prov.cash_rate.stale_since}; the last value is carried forward.</div>}
      {prov.fx?.dropped_no_fx?.length > 0 && <div className="text-amber">No FX history for {prov.fx.missing_fx.join(', ')}: {prov.fx.dropped_no_fx.length} listing(s) left out.</div>}
      {prov.engine_mismatch && <div className="text-amber">{prov.engine_mismatch}</div>}
      {prov.stale_symbols?.length > 0 && <div className="text-amber">Served from an out-of-date cache (download failed): {prov.stale_symbols.join(', ')}.</div>}
      {h && (
        <table className="font-mono"><tbody>
          <tr><td className="pr-3 text-text-tertiary">Before holdout ({h.start})</td><td className="pr-3">CAGR {spct(h.in_sample?.cagr)}</td><td>Sharpe {num(h.in_sample?.sharpe)}</td></tr>
          <tr><td className="pr-3 text-text-tertiary">Holdout</td><td className="pr-3">CAGR {spct(h.holdout?.cagr)}</td><td>Sharpe {num(h.holdout?.sharpe)}</td></tr>
          <tr><td className="pr-3 text-text-tertiary">Equal-weight universe, holdout</td><td className="pr-3">CAGR {spct(h.baseline_holdout?.cagr)}</td><td>Sharpe {num(h.baseline_holdout?.sharpe)}</td></tr>
        </tbody></table>)}
      {ex && <div className="text-text-secondary">Execution: {ex.unfilled_order_days} day(s) with orders that could not fill (no opening print or no volume) · {ex.stale_position_days} position-day(s) valued at a stale price · {ex.listings_ended} listing(s) ended while held (settled at last close).</div>}
      {ex?.option_notional_avg != null && <div className="text-text-secondary">Options: underlying notional averaged {pct(ex.option_notional_avg, 0)} of NAV (peak {pct(ex.option_notional_max, 0)}) · {ex.options_expired} contract expir{ex.options_expired === 1 ? 'y' : 'ies'} settled. Option prices are modelled, not historical quotes ({Object.values(prov.market_rules?.options ?? {}).map((o: any) => o.vol_source).filter((v, i, a) => a.indexOf(v) === i).join('; ')}).</div>}
      {ex && (ex.board_lots || ex.fx_hedged?.length > 0 || ex.fx_unhedged?.length > 0) && (
        <div className="text-text-secondary">
          {ex.board_lots && <>Board lots: on average {pct(ex.lot_residual_avg, 3)} of NAV per day left untraded by rounding to whole lots{prov.market_rules?.board_lot_listings ? ` (${Object.keys(prov.market_rules.board_lot_listings).length} listing(s) trade in lots)` : ''}. </>}
          {ex.fx_hedged?.length > 0 && <>Hedged: {ex.fx_hedged.join(', ')}. </>}
          {ex.fx_unhedged?.length > 0 && <span className="text-amber">Unhedged (no free short-rate history to price the forward): {ex.fx_unhedged.join(', ')}.</span>}
        </div>)}
      <details><summary className="cursor-pointer text-text-tertiary">Provenance</summary>
        <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-x-4 font-mono text-[10px] text-text-tertiary">
          <div>engine {prov.engine_version} · cost schema {prov.cost_schema_version}</div><div>runtime {prov.runtime ?? 'server'}</div>
          <div>data {prov.data_first} → {prov.data_last} · hash {prov.data_hash}</div><div>code hash {prov.code_hash ?? '—'}</div>
          <div className="md:col-span-2 font-sans">{prov.adjustment}</div>
          {prov.account_currency && <div className="md:col-span-2 font-sans">Account {prov.account_currency} · cash: {prov.cash_rate?.source ?? 'none'}{prov.fx?.pairs ? ` · ${Object.keys(prov.fx.pairs).length} listing(s) converted at as-of FX` : ''}</div>}
          <div className="md:col-span-2 font-sans">{prov.universe_selection}</div>
          {r.benchmark_definition && <div className="md:col-span-2 font-sans">Benchmark: {r.benchmark_definition}</div>}
        </div>
      </details>
      {r.events?.length > 0 && (
        <details><summary className="cursor-pointer text-text-tertiary">{r.events.length} account event(s)</summary>
          <ul className="mt-1 font-mono text-[10px] text-text-tertiary">{r.events.map((e: any, i: number) => <li key={i}>{e.date} {e.ticker ?? ''} {e.event}</li>)}</ul></details>)}
    </div>
  );
}

function Variants({ opt }: { opt: any }) {
  return (
    <div className="p-3 bg-surface-1 border border-border text-[11px] space-y-2">
      <div className="text-xs font-semibold text-text-primary">What each layer of the platform adds</div>
      <table className="w-full font-mono">
        <thead className="text-text-tertiary"><tr>{['Version', 'CAGR', 'Vol', 'Sharpe', 'Max DD', 'Calmar'].map((h) => <th key={h} className="text-right first:text-left font-normal px-1.5">{h}</th>)}</tr></thead>
        <tbody>{opt.variants.map((v: any) => (
          <tr key={v.label} className="border-t border-border-subtle">
            <td className="px-1.5 font-sans">{v.label}</td><td className="text-right px-1.5">{spct(v.cagr)}</td><td className="text-right px-1.5">{pct(v.vol)}</td>
            <td className="text-right px-1.5">{num(v.sharpe)}</td><td className="text-right px-1.5">{pct(v.max_drawdown)}</td><td className="text-right px-1.5">{num(v.calmar)}</td></tr>))}</tbody>
      </table>
      {opt.events?.length > 0 && (
        <details><summary className="cursor-pointer text-text-tertiary">{opt.n_events ?? opt.events.length} risk events (pods cut, closed, re-hired) — latest {opt.events.length}</summary>
          <div className="mt-1 flex flex-wrap gap-1 font-mono">{opt.events.slice().reverse().map((e: any, i: number) => (
            <span key={i} className={cn('px-1.5 py-0.5 border', e.event.startsWith('closed') ? 'border-red/50 text-red' : e.event.startsWith('capital') ? 'border-amber/50 text-amber' : 'border-border text-text-tertiary')}>
              {e.date} {e.pod}: {e.event}</span>))}</div></details>)}
    </div>
  );
}

function FactorLens({ f }: { f: any }) {
  return (
    <div className="p-3 bg-surface-1 border border-border text-[11px] space-y-2">
      <div className="flex flex-wrap items-baseline gap-2">
        <div className="text-xs font-semibold text-text-primary">Factor lens (Two Sigma-style)</div>
        <div className="text-[10px] text-text-tertiary">{f.start} → {f.end}, {f.weeks} weeks · factors explain {pct(f.r2, 0)} of the variation</div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)] gap-3">
        <div className={cn('p-2 border', Math.abs(f.alpha_t) >= 2 ? (f.alpha > 0 ? 'border-green/50' : 'border-red/50') : 'border-border')}>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Alpha after factors</div>
          <div className={cn('text-lg font-mono', f.alpha > 0 ? 'text-green' : 'text-red')}>{spct(f.alpha)}<span className="text-xs text-text-tertiary"> /yr</span></div>
          <div className="text-[10px] text-text-tertiary">t = {num(f.alpha_t)} — {Math.abs(f.alpha_t) >= 2 ? 'statistically meaningful' : 'not distinguishable from zero'}</div>
        </div>
        <table className="w-full font-mono">
          <thead className="text-text-tertiary"><tr>{['Factor', 'Exposure (β)', 't', 'Return explained /yr'].map((h) => <th key={h} className="text-right first:text-left font-normal px-1.5">{h}</th>)}</tr></thead>
          <tbody>{f.factors.map((x: any) => (
            <tr key={x.factor} className={cn('border-t border-border-subtle', Math.abs(x.t) < 2 && 'text-text-tertiary')}>
              <td className="px-1.5 font-sans">{x.factor}</td><td className="text-right px-1.5">{num(x.beta)}</td>
              <td className="text-right px-1.5">{num(x.t)}</td><td className="text-right px-1.5">{spct(x.contribution, 2)}</td></tr>))}</tbody>
        </table>
      </div>
      <div className="text-[10px] text-text-tertiary">{f.note}</div>
    </div>
  );
}

function MonteCarlo({ mc }: { mc: any }) {
  const maxCount = Math.max(...mc.hist.map((h: any) => h.count), 1);
  return (
    <div className="p-3 bg-surface-1 border border-border space-y-3">
      <div className="flex flex-wrap items-baseline gap-2">
        <div className="text-xs font-semibold text-text-primary">Monte Carlo — {mc.paths.toLocaleString()} futures of {mc.years} years</div>
        <div className="text-[10px] text-text-tertiary">Stationary block bootstrap of the daily net returns (mean block {mc.mean_block_days} days, Politis & Romano 1994) from {mc.based_on_days.toLocaleString()} days of history.</div>
      </div>
      <KpiStrip compact cols={6} items={[
        { label: 'Median CAGR', value: spct(mc.cagr_pct['50']), sub: `5–95%: ${spct(mc.cagr_pct['5'])} to ${spct(mc.cagr_pct['95'])}`, tone: tone(mc.cagr_pct['50']) },
        { label: 'P(lose money)', value: pct(mc.p_loss, 1), tone: mc.p_loss > 0.2 ? 'down' : null },
        { label: 'Median worst drawdown', value: pct(-mc.max_dd_pct['50'], 0), sub: `95th pct ${pct(-mc.max_dd_pct['95'], 0)}`, tone: 'down' },
        { label: 'P(drawdown > 30%)', value: pct(mc.p_dd['30'], 1) },
        { label: 'Growth-optimal leverage', value: `${mc.growth_optimal_leverage}×`, sub: mc.kelly_full != null ? `full Kelly ≈ ${mc.kelly_full}×` : undefined },
        { label: 'Recommended leverage', value: `${mc.recommended_leverage}×`, sub: 'max growth within risk limits', accent: true },
      ]} />
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div className="xl:col-span-2">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Growth of $1 — percentiles across simulated futures</div>
          <LineChart rows={mc.fan} x="year" height={220} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
            lines={[{ key: 'p95', label: '95th', color: CATEGORICAL[2] }, { key: 'p75', label: '75th', color: CATEGORICAL[5] }, { key: 'p50', label: 'Median', color: CATEGORICAL[0] },
              { key: 'p25', label: '25th', color: CATEGORICAL[3] }, { key: 'p5', label: '5th', color: CATEGORICAL[7] }]} />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Distribution of {mc.years}-year CAGR</div>
          <div className="flex items-end gap-px h-[180px] border-b border-border" role="img" aria-label="Histogram of simulated CAGR">
            {mc.hist.map((h: any, i: number) => (
              <div key={i} title={`${spct(h.cagr)}: ${h.count} paths`} className={cn('flex-1 rounded-t-sm', h.cagr < 0 ? 'bg-red/70' : 'bg-bloomberg/70')}
                style={{ height: `${(h.count / maxCount) * 100}%` }} />))}
          </div>
          <div className="flex justify-between text-[10px] text-text-tertiary font-mono mt-0.5"><span>{spct(mc.hist[0]?.cagr)}</span><span>{spct(mc.hist[mc.hist.length - 1]?.cagr)}</span></div>
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Leverage — what more risk buys (financing at T-bill + spread above 1×)</div>
        <table className="w-full text-[11px] font-mono">
          <thead className="text-text-tertiary"><tr>{['Leverage', 'Median CAGR', '5th pct CAGR', 'Median worst DD', 'P(DD beyond limit)', 'P(loss)'].map((h) => <th key={h} className="text-right first:text-left font-normal px-1.5">{h}</th>)}</tr></thead>
          <tbody>{mc.leverage.map((x: any) => (
            <tr key={x.leverage} className={cn('border-t border-border-subtle', x.leverage === mc.recommended_leverage && 'bg-bloomberg/10 font-semibold')}>
              <td className="px-1.5">{x.leverage}×{x.leverage === mc.recommended_leverage ? ' ← recommended' : ''}</td>
              <td className={cn('text-right px-1.5', x.median_cagr >= 0 ? 'text-green' : 'text-red')}>{spct(x.median_cagr)}</td>
              <td className="text-right px-1.5">{spct(x.p5_cagr)}</td><td className="text-right px-1.5">{pct(-x.median_max_dd, 0)}</td>
              <td className={cn('text-right px-1.5', x.p_dd > 0.05 && 'text-amber')}>{pct(x.p_dd, 1)}</td><td className="text-right px-1.5">{pct(x.p_loss, 1)}</td></tr>))}</tbody>
        </table>
        <div className="text-[10px] text-text-tertiary mt-1">{mc.rule} Full Kelly maximises long-run growth only if the estimated edge is exactly right; half-Kelly keeps ~75% of the growth with far smaller drawdowns.</div>
      </div>
    </div>
  );
}

export { usd };


/** QuantConnect compatibility report for an imported LEAN algorithm (static — nothing is executed to produce it). */
function QcReport({ qc }: { qc: any }) {
  const rows: any[] = qc.report ?? [];
  const unsupported = rows.filter((r) => r.level === 'unsupported');
  const checks = rows.filter((r) => r.level === 'check');
  return (
    <details open={unsupported.length > 0} className="text-[10px] border border-border bg-surface-1 px-2 py-1">
      <summary className="cursor-pointer text-text-secondary">
        QuantConnect algorithm <span className="font-mono">{qc.class}</span> · {qc.api_version ?? 'qc-compat'} ·{' '}
        {unsupported.length ? <span className="text-red">{unsupported.length} unsupported</span> : <span className="text-green">runs here</span>}
        {checks.length > 0 && <span className="text-red"> · {checks.length} not in the layer</span>}
        {rows.length - unsupported.length - checks.length > 0 && <span className="text-amber"> · {rows.length - unsupported.length - checks.length} approximated</span>}
        {qc.universe?.length > 0 && <span className="text-text-tertiary"> · {qc.universe.join(', ')}</span>}
        {qc.dynamic_universe && <span className="text-text-tertiary"> · dynamic universe on point-in-time S&amp;P 500</span>}
        {qc.start && <span className="text-text-tertiary"> · {qc.start}{qc.end ? ` → ${qc.end}` : ''}</span>}
      </summary>
      {qc.error && <div className="text-red">{qc.error}</div>}
      <div className="mt-1 space-y-0.5 font-mono">
        {rows.map((r, i) => (
          <div key={i} className="flex gap-2">
            <span className={r.level === 'unsupported' || r.level === 'check' ? 'text-red' : 'text-amber'}>{r.level === 'check' ? 'not in layer' : r.level}</span>
            <span className="text-text-tertiary">line {r.line ?? '—'}</span><span>{r.feature}</span><span className="text-text-secondary">— {r.message}</span>
          </div>))}
        {rows.length === 0 && <div className="text-text-tertiary">Every construct maps directly (daily bars; orders fill at the next open unless market-on-close).</div>}
      </div>
    </details>
  );
}


/** Uploaded custom datasets: CUSTOM_DATA = ["name"] in a strategy, or self.add_data(MyData, "name") in an algorithm. */
function CustomData() {
  const [list, setList] = useState<any[] | null>(null);
  const [name, setName] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api('/api/v1/quant/custom-data').then((j: any) => setList(j.datasets)).catch(() => setList([])), []);
  useEffect(() => { load(); }, [load]);
  const upload = async (file: File) => {
    const n = (name || file.name.replace(/\.[^.]+$/, '')).toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^[^a-z]+/, '').slice(0, 40);
    if (!n) { setErr('Give the dataset a name (letters, digits, _).'); return; }
    setBusy(true); setErr(null);
    try {
      await api('/api/v1/quant/custom-data', { method: 'POST', json: { name: n, csv: await file.text() } });
      setName(''); load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const del = async (n: string) => { try { await api(`/api/v1/quant/custom-data/${n}`, { method: 'DELETE' }); load(); } catch (e: any) { setErr(e.message); } };
  return (
    <details className="text-[11px]">
      <summary className="cursor-pointer text-text-tertiary">Custom data {list?.length ? `(${list.length})` : ''}</summary>
      <div className="mt-1 p-2 border border-border bg-surface-1 space-y-1.5">
        <div className="text-text-tertiary">A CSV with a date column and numeric columns. Use it with <span className="font-mono">CUSTOM_DATA = ["name"]</span> →
          <span className="font-mono"> data.custom["name"]</span>, or <span className="font-mono">self.add_data(PythonData, "name")</span> in an algorithm. Each row is known from its date's close.</div>
        <div className="flex flex-wrap items-center gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="name (optional)" className={cn(inputCls, 'w-40 font-mono')} />
          <label className={cn('px-2 py-1 border border-border cursor-pointer hover:border-bloomberg', busy && 'opacity-50')}>
            {busy ? 'Uploading…' : 'Upload CSV'}
            <input type="file" accept=".csv,text/csv" className="hidden" disabled={busy}
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.currentTarget.value = ''; }} />
          </label>
        </div>
        {err && <div className="text-amber">{err}</div>}
        {list && list.length > 0 && (
          <table className="w-full"><tbody>{list.map((d) => (
            <tr key={d.name} className="border-t border-border-subtle">
              <td className="py-0.5 font-mono text-text-primary">{d.name}</td>
              <td className="text-text-tertiary">{d.columns.join(', ')}</td>
              <td className="text-text-tertiary">{d.first} → {d.last} · {d.rows} rows · {d.owner}</td>
              <td className="text-right"><button onClick={() => del(d.name)} className="text-text-tertiary hover:text-red">Delete</button></td>
            </tr>))}</tbody></table>)}
      </div>
    </details>
  );
}


/** A backtest from QuantConnect's own LEAN engine: its statistics, equity curve and orders, as LEAN reports them. */
function LeanResult({ r }: { r: any }) {
  const stats: [string, any][] = Object.entries(r.statistics ?? {});
  const curve = (r.equity_curve ?? []).map((p: any) => ({ date: p.date, equity: p.equity }));
  return (
    <div className="border border-bloomberg/40 bg-surface-1 p-2 space-y-2 text-[11px]">
      <div className="text-xs font-semibold text-text-primary">Real LEAN result <span className="font-normal text-text-tertiary">· {r.engine} · {r.image}{r.image_date ? ` (${r.image_date})` : ''} · {r.order_count} orders</span></div>
      {curve.length > 1 && <LineChart rows={curve} x="date" height={220} fmt={(v) => v.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        lines={[{ key: 'equity', label: 'Equity (LEAN)', color: '#3987e5' }]} />}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-0.5 font-mono">
        {stats.map(([k, v]) => <div key={k} className="flex justify-between gap-2"><span className="text-text-tertiary truncate">{k}</span><span className="text-text-primary">{String(v)}</span></div>)}
      </div>
      {r.runtime_errors?.length > 0 && <div className="text-red">{r.runtime_errors.join(' | ')}</div>}
      {r.data?.skipped?.length > 0 && <div className="text-amber">Not run on LEAN (no data in a format LEAN takes): {r.data.skipped.join(', ')}</div>}
      {r.data?.notes?.length > 0 && <div className="text-amber">{r.data.notes.join(' · ')}</div>}
      <div className="text-text-tertiary">Data: {r.data?.source} · {r.data?.data_start} → {r.data?.data_end}. Isolation: {r.isolation}.</div>
    </div>
  );
}

/**
 * Code Lab — write a strategy in Python, test it in the browser (Pyodide worker), see it net of every
 * cost, walk-forward optimised, Monte-Carlo'd and deep-analysed; save it or deploy it to a paper trader
 * (deployment runs the code in the server's sandbox). Engine: api/quant/codelab.py.
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import { useConfirm } from '@/components/ui/ConfirmDialog';
import { Loader2, Play, Rocket, Save, ShieldCheck, ShieldAlert, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { BarList } from '@/components/ui/BarList';
import { CATEGORICAL } from '@/lib/chartPalette';
import { DeepReport } from './DeepReport';
import { api, ErrorNote, Field, inputCls, num, pct, spct, tone, usd } from './shared';

export const STARTER = `# Shared USD US-listed stock universe. Sparse decisions for ledger.2.
# Keeps the prior equity selection; adds a weekly market stress budget.
# Retrospective universe, no proven future alpha. No leverage or live orders.
# Equity momentum research strategy: paste into Quant Lab, replace UNIVERSE as needed.
# The configured server universe supports up to 1000 symbols in one USD cross-section.
# Only price/volume signals: no claims of fundamental quality or guaranteed alpha.
import numpy as np
import pandas as pd

UNIVERSE = ["SPY"]
TRADABLE_UNIVERSE = "US"
START = "2011-01-03"
BENCHMARK = "SPY"
PARAMS = {}


def equity_targets(data, core_symbol="SPY", core_share=0.30, broad_share=0.35, picks=15,
             target_vol=0.20, max_stock=0.08, min_traded_value=10000000.0,
             participation=0.01, capital=1000000.0, risk_off=0.65, **params):
    px = data.close.astype(float)
    volume = data.volume.reindex(index=px.index, columns=px.columns).astype(float)
    if not isinstance(px.index, pd.DatetimeIndex) or not px.index.is_unique or not px.index.is_monotonic_increasing:
        raise ValueError("Dates must be unique and increasing")
    if core_symbol not in px.columns:
        raise ValueError("Include the tradable core ETF in UNIVERSE")
    if not px.columns.is_unique or len(px.columns) > 1000:
        raise ValueError("Use at most 1000 unique tickers")
    if np.isinf(px.to_numpy()).any() or (px <= 0).any().any():
        raise ValueError("Prices must be positive; missing histories are allowed")
    if params or not 0 <= core_share <= 0.8 or not 0 <= broad_share <= 1-core_share or not 0.05 <= target_vol <= 0.30:
        raise ValueError("Unknown parameters or invalid core_share/target_vol")
    if isinstance(picks,bool) or not isinstance(picks,int) or not 5 <= picks <= 50:
        raise ValueError("picks must be an integer from 5 through 50")
    if not 0 < max_stock <= .10 or min_traded_value <= 0 or capital <= 0 or not 0 < participation <= .02 or not 0 <= risk_off <= 1:
        raise ValueError("Invalid concentration, liquidity, capital or regime settings")
    ret = px.pct_change(fill_method=None)
    ready = px.notna().rolling(253,min_periods=253).sum().eq(253)
    vol = ret.rolling(63,min_periods=63).std()*np.sqrt(252)
    adv = (px*volume).rolling(63,min_periods=63).mean()
    liquid = (adv >= min_traded_value) & (volume > 0)
    eligible = ready & liquid & ((vol >= .03) & (vol <= 1.0))
    eligible.loc[:,core_symbol] = False
    mom12 = px.shift(21)/px.shift(252)-1
    mom6 = px.shift(21)/px.shift(126)-1
    # Cross-sectional ranks avoid hand-picked absolute score coefficients.
    score = .6*mom12.where(eligible).rank(axis=1,pct=True) + .4*mom6.where(eligible).rank(axis=1,pct=True)
    # Requiring positive momentum is a hypothesis, not an optimized threshold.
    score = score.where(eligible & (mom12 > 0) & (mom6 > 0))
    regime = px[core_symbol] >= px[core_symbol].rolling(200,min_periods=200).mean()
    core_ready = ready[core_symbol] & (volume[core_symbol] > 0)
    weights = np.zeros(px.shape)
    last = np.zeros(len(px.columns))
    core_index = list(px.columns).index(core_symbol)
    previous = []
    # First observed trading day of each month; determined without future calendar rows.
    months = px.index.to_period("M")
    decisions = np.r_[True, months[1:] != months[:-1]]
    next_ready = True
    for t in range(len(px)):
        if not core_ready.iloc[t]:
            weights[t] = 0.0
            last = np.zeros(len(px.columns))
            next_ready = True
            continue
        if decisions[t] or next_ready:
            candidate = np.zeros(len(px.columns))
            ranks = score.iloc[t].rank(ascending=False,method="first")
            # Keep incumbents within top 1.5*picks to reduce unnecessary turnover.
            keep = [j for j in previous if pd.notna(ranks.iloc[j]) and ranks.iloc[j] <= 1.5*picks]
            keep = sorted(keep,key=lambda j:float(ranks.iloc[j]))[:picks]
            ordered = np.argsort(ranks.fillna(1e9).to_numpy())
            selected = list(keep)
            for j in ordered:
                if len(selected) >= picks: break
                if j not in selected and pd.notna(ranks.iloc[j]): selected.append(int(j))
            previous = selected
            budget = .98*(1.0 if regime.iloc[t] else risk_off)
            if selected:
                inv = 1/np.sqrt(vol.iloc[t,selected].to_numpy())
                allocation = inv/inv.sum()*budget*(1-core_share-broad_share)
                capacity = adv.iloc[t,selected].to_numpy()*participation/capital
                candidate[selected] = allocation
                # Residual stock budget stays cash; never hides concentration in core.
                candidate[core_index] = budget*core_share
            else:
                candidate[core_index] = budget*core_share
            # Blend a diversified equity sleeve with concentrated momentum.
            broad = eligible.iloc[t].to_numpy()
            if broad.any():
                candidate[broad] += budget*broad_share/float(broad.sum())
            stock_mask = np.ones(len(px.columns),dtype=bool)
            stock_mask[core_index] = False
            capacity = adv.iloc[t].fillna(0).to_numpy()*participation/capital
            candidate[stock_mask] = np.minimum(np.minimum(candidate[stock_mask],max_stock),capacity[stock_mask])
            active = candidate > 0
            history = ret.iloc[max(0,t-62):t+1,active].to_numpy()
            if len(history)==63 and np.isfinite(history).all():
                cov = np.atleast_2d(np.cov(history,rowvar=False,ddof=1))*252
                a = candidate[active]
                risk = np.sqrt(max(float(a@cov@a),0))
                candidate *= min(1.,target_vol/risk) if risk>0 else 1.
            else:
                candidate *= 0
            last = candidate
            next_ready = False
        # Sell invalid / zero-volume names on the next execution opportunity.
        valid_now = ready.iloc[t].to_numpy() & (volume.iloc[t].to_numpy()>0)
        last = np.where(valid_now,last,0)
        weights[t] = last
    return pd.DataFrame(weights,index=px.index,columns=px.columns)


def strategy(data, stress_budget=0.50, stress_drawdown=0.15, stress_vol=0.30, **params):
    if not .20 <= stress_budget <= .98 or not .05 <= stress_drawdown <= .30 or not .15 <= stress_vol <= .60:
        raise ValueError("Invalid market stress settings")
    # Upstream parameters remain the previous frozen equity specification.
    targets = equity_targets(data, **params)
    px = data.close["SPY"]
    market_return = px.pct_change(fill_method=None)
    market_vol = market_return.rolling(20,min_periods=20).std()*np.sqrt(252)
    market_dd = px/px.rolling(252,min_periods=252).max()-1.
    stress = (market_dd <= -stress_drawdown) | (market_vol >= stress_vol)
    months = px.index.to_period("M")
    weeks = px.index.to_period("W")
    monthly = np.r_[True, months[1:]!=months[:-1]]
    weekly = np.r_[True, weeks[1:]!=weeks[:-1]]
    out = np.full(targets.shape,np.nan)
    last = np.zeros(len(targets.columns))
    initialized = False
    for t in range(len(targets)):
        if monthly[t] or (not initialized and targets.iloc[t].sum()>0):
            last = targets.iloc[t].to_numpy().copy()
            if stress.iloc[t] and last.sum()>stress_budget:
                last *= stress_budget/last.sum()
            out[t] = last
            initialized = last.sum()>0
        elif weekly[t] and stress.iloc[t] and last.sum()>stress_budget:
            last = last*stress_budget/last.sum()
            out[t] = last
    return pd.DataFrame(out,index=targets.index,columns=targets.columns)
`;

export const COST_DEFAULTS = { capital: 1_000_000, commission_bps: 0.35, spread_mult: 1, impact_coef_bps: 11.21, borrow_fee: 0.003,
  financing_spread: 0.01, cash_spread: 0, no_trade_band: 0.0025, delist_haircut: 0 };
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
      await new Promise<void>((res, rej) => {
        const h = (ev: MessageEvent<Msg>) => {
          if (ev.data.type === 'ready') { worker.removeEventListener('message', h); res(); }
          if (ev.data.type === 'error') { worker.removeEventListener('message', h); rej(new Error(ev.data.error)); }
        };
        worker.addEventListener('message', h);
        worker.postMessage({ type: 'init', engine });
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
function CodeEditor({ value, onChange, onRun }: { value: string; onChange: (v: string) => void; onRun: () => void }) {
  const ta = useRef<HTMLTextAreaElement>(null);
  const gutter = useRef<HTMLDivElement>(null);
  const lines = value.split('\n').length;
  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); onRun(); return; }
    if (e.key === 'Tab') {
      e.preventDefault();
      const el = e.currentTarget, s = el.selectionStart, end = el.selectionEnd;
      const next = value.slice(0, s) + '    ' + value.slice(end);
      onChange(next);
      requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = s + 4; });
    }
  };
  return (
    <div className="flex border border-border bg-surface-1 font-mono text-[12px] leading-[18px] h-[460px]">
      <div ref={gutter} className="select-none text-right pr-2 pl-2 py-2 text-text-tertiary overflow-hidden bg-surface-2/40" aria-hidden>
        {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
      </div>
      <textarea ref={ta} value={value} spellCheck={false} aria-label="Strategy code"
        onChange={(e) => onChange(e.target.value)} onKeyDown={onKey}
        onScroll={(e) => { if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop; }}
        className="flex-1 resize-none bg-transparent p-2 outline-none text-text-primary whitespace-pre overflow-auto" />
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
  const [check, setCheck] = useState<{ ok: boolean; error?: string; tradable?: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [capital, setCapital] = useState(1_000_000);
  const [jobId, setJobId] = useState<string | null>(null);
  const [dialog, ask] = useConfirm();

  const runOnServer = async (chk: any) => {
    // TRADABLE_UNIVERSE: hundreds of tickers — run in the server sandbox as a background job (one global cross-section)
    const job = await api('/api/v1/quant/code/jobs', { json: { code, costs } });
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

  const cancelJob = async () => {
    if (jobId) await api(`/api/v1/quant/code/jobs/${jobId}`, { method: 'DELETE' }).catch(() => {});
  };

  const run = useCallback(async () => {
    setBusy(true); setErr(null); setNote(null); setLog([]); setResult(null); setAnalysis(null);
    let chk: any = null;
    try { chk = await api('/api/v1/quant/code/check', { json: { code } }); setCheck(chk); } catch { setCheck(null); }
    try {
      if (chk?.ok && chk.tradable) {
        const r = await runOnServer(chk);
        setResult(r);
        setStatus('Monte Carlo and deep analysis…');
        const a = await api('/api/v1/quant/code/analyze', { json: { dates: r.dates, returns: r.returns, benchmark: r.benchmark, label: name || 'Strategy', benchmark_label: chk.benchmark, provenance: r.provenance, ...mc } });
        setAnalysis(a);
        setStatus(null);
        return;
      }
      const sh = getWorker(setStatus, (s) => setLog((l) => [...l.slice(-200), s]));
      await sh.ready;
      setStatus('Reading your code…');
      const { header } = await call(sh.worker, { type: 'prepare', code }, 'prepared', 60_000);
      setStatus(`Loading prices for ${header.universe.length} ticker${header.universe.length > 1 ? 's' : ''}…`);
      const data = await api(`/api/v1/quant/code/data?universe=${encodeURIComponent(header.universe.join(','))}&start=${header.start}&benchmark=${encodeURIComponent(header.benchmark)}`);
      setStatus('Backtesting (net of costs)…');
      const { result: r } = await call(sh.worker, { type: 'run', code, data, costs }, 'result', 300_000);
      setResult({ ...r, benchmark_label: header.benchmark });
      setStatus('Monte Carlo and deep analysis…');
      const a = await api('/api/v1/quant/code/analyze', { json: { dates: r.dates, returns: r.returns, benchmark: r.benchmark, label: name || 'Strategy', benchmark_label: header.benchmark, provenance: r.provenance, ...mc } });
      setAnalysis(a);
      setStatus(null);
    } catch (e: any) { setErr(e.message); setStatus(null); } finally { setBusy(false); }
  }, [code, costs, mc, name]);   // eslint-disable-line react-hooks/exhaustive-deps

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
      body: `Paper capital $${capital.toLocaleString()}. The server re-runs your code daily in a locked-down sandbox; no real orders are placed.` }))) return;
    setErr(null); setBusy(true); setStatus('Running your code in the server sandbox…');
    try {
      const d = await api('/api/v1/quant/trader/deploy', { json: { spec: { kind: 'code', name: name || 'Code strategy', code, costs }, capital, strategy_id: strategyId } });
      const label = ({ macro: 'Macro', fundamental: 'Fundamental', technical: 'Technical' } as Record<string, string>)[d.book] ?? 'Macro';
      setNote(`Deployed “${d.name}” to the ${label} Quant Trader — live from the session after ${d.deployed_at}.`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); setStatus(null); }
  };
  const set = (k: keyof Costs) => (e: React.ChangeEvent<HTMLInputElement>) => setCosts({ ...costs, [k]: Number(e.target.value) });

  return (
    <div className="space-y-3">
      {dialog}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-3">
        <div className="space-y-2">
          <div className="flex flex-wrap items-end gap-2">
            <Field label="Name" className="w-64"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="My strategy" /></Field>
            <button onClick={run} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1 text-2xs bg-bloomberg text-bg disabled:opacity-50" aria-label="Run (Ctrl/⌘ + Enter)" title="Ctrl/⌘ + Enter">
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}Run
            </button>
            {canSave && <button onClick={() => save(false)} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1 text-2xs border border-border hover:border-bloomberg"><Save className="w-3 h-3" />{strategyId ? 'Save' : 'Save as'}</button>}
            {canSave && strategyId && <button onClick={() => save(true)} disabled={busy} className="px-3 py-1 text-2xs border border-border hover:border-bloomberg">Save copy</button>}
            {canDeploy && (
              <span className="inline-flex items-end gap-1 ml-auto">
                <Field label="Paper capital" className="w-32"><input type="number" className={inputCls} value={capital} onChange={(e) => setCapital(Number(e.target.value))} /></Field>
                <button onClick={deploy} disabled={busy || check?.ok === false} title={check?.ok === false ? check.error : undefined}
                  className="inline-flex items-center gap-1 px-3 py-1 text-2xs border border-bloomberg text-bloomberg disabled:opacity-40"><Rocket className="w-3 h-3" />Deploy</button>
              </span>)}
          </div>
          <CodeEditor value={code} onChange={setCode} onRun={run} />
          {check && (
            <div className={cn('text-[10px] flex items-center gap-1', check.ok ? 'text-text-tertiary' : 'text-amber')}>
              {check.ok ? <ShieldCheck className="w-3 h-3" /> : <ShieldAlert className="w-3 h-3" />}
              {check.ok ? (check.tradable ? `Tradable universe '${check.tradable}': runs on the server as a sandboxed job (hundreds of tickers); deployable.` : 'Deployable: passes the server sandbox rules.') : `Runs here, but can't be deployed: ${check.error}`}
            </div>)}
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
              <Field label="Capital (USD)" hint="Account currency USD. Size matters: market impact grows with the square root of your share of daily volume"><input type="number" className={inputCls} value={costs.capital} onChange={set('capital')} /></Field>
              <Field label="Commission (bp / side)" hint="Basis points of traded notional, each side. 0.35 bp ≈ $0.0035/share at $100"><input type="number" step={0.05} className={inputCls} value={costs.commission_bps} onChange={set('commission_bps')} /></Field>
              <Field label="Spread multiplier (×)" hint="A multiplier, not basis points: scales the modelled half-spread (from each asset's volatility and dollar volume)"><input type="number" step={0.25} className={inputCls} value={costs.spread_mult} onChange={set('spread_mult')} /></Field>
              <Field label="Impact (bp × √%ADV)" hint="Basis points × √(% of 63-day dollar volume traded). 11.2 = AQR live-trade calibration (Frazzini, Israel & Moskowitz 2018)"><input type="number" step={0.5} className={inputCls} value={costs.impact_coef_bps} onChange={set('impact_coef_bps')} /></Field>
              <Field label="Borrow fee (annual, decimal)" hint="0.003 = 0.3% a year on short market value (general collateral)"><input type="number" step={0.001} className={inputCls} value={costs.borrow_fee} onChange={set('borrow_fee')} /></Field>
              <Field label="Margin spread (annual, decimal)" hint="Negative cash pays the T-bill rate plus this; 0.01 = 1%"><input type="number" step={0.0025} className={inputCls} value={costs.financing_spread} onChange={set('financing_spread')} /></Field>
              <Field label="No-trade band (fraction of NAV)" hint="Skip trades smaller than this fraction of NAV; 0.0025 = 0.25%"><input type="number" step={0.0025} className={inputCls} value={costs.no_trade_band} onChange={set('no_trade_band')} /></Field>
              <Field label="Cash yield cut (annual, decimal)" hint="Positive cash earns the T-bill rate minus this. 0 = full T-bill (institutional); many retail brokers pay far less"><input type="number" step={0.0025} className={inputCls} value={costs.cash_spread} onChange={set('cash_spread')} /></Field>
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
        <li><code>data.rf</code> daily T-bill rate · <code>data.vix</code> VIX close.</li>
        <li>Helpers: <code>momentum(px, n, skip)</code>, <code>ewma_vol(px, halflife)</code>, <code>vol_target(w, px, target)</code>, <code>normalize_gross(w)</code>, <code>hold_monthly(w)</code>, <code>hold_weekly(w)</code>; <code>np</code>, <code>pd</code>, <code>math</code>.</li>
        <li>Universe: <code>TRADABLE_UNIVERSE = "US"</code> uses the shared configured US listings in a server job. Remove that line for a custom <code>UNIVERSE</code> (up to 80 symbols). USD only; no live trading.</li>
        <li><code>data.observed</code> flags actual bars. Return all-NaN rows between decisions to hold and drift; populated rows request a rebalance at the next observed open.</li>
        <li>Optional: <code>START</code>, <code>BENCHMARK</code>, <code>PARAMS</code> (≤ 48 combinations, walk-forward), <code>HOLDOUT</code>.</li>
        <li><code>print()</code> shows in Output. In the browser you can also import scipy, scikit-learn or statsmodels; deployable code is limited to numpy, pandas and math.</li>
      </ul>
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

export function CodeResults({ r, a }: { r: any; a: any | null }) {
  const m = r.metrics ?? {}, g = r.metrics_gross, c = r.costs, b = r.benchmark_metrics, opt = r.optimisation ?? {};
  const rows = useMemo(() => curve(r.dates, r.returns, r.benchmark, r.gross, r.baseline_returns), [r]);
  const ew = r.baseline_equal_weight, prov = r.provenance ?? {}, ex = r.execution, reg = a?.registry;
  const mc = a?.monte_carlo;
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
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div className="xl:col-span-2">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Growth of $1 — net of all costs{r.gross ? ', before costs' : ''}{r.baseline_returns ? ', equal-weight universe (same costs)' : ''}{r.benchmark ? `, and ${r.benchmark_label || 'benchmark'}` : ''}</div>
          <LineChart rows={rows} x="date" height={260} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
            lines={[{ key: 'net', label: 'Net', color: CATEGORICAL[0] }, ...(r.gross ? [{ key: 'gross', label: 'Before costs', color: CATEGORICAL[3] }] : []),
              ...(r.baseline_returns ? [{ key: 'base', label: 'Equal-weight universe', color: CATEGORICAL[2] }] : []),
              ...(r.benchmark ? [{ key: 'bench', label: `${r.benchmark_label || 'Benchmark'} (frictionless)`, color: CATEGORICAL[6] }] : [])]} />
        </div>
        {c ? (
          <div className="space-y-2">
            <BarList title="Average cost per year (% of capital)" fmt={(v) => `${(v * 100).toFixed(2)}%`}
              data={[{ label: 'Market impact', value: c.impact }, { label: 'Spread', value: c.spread }, { label: 'Commission', value: c.commission },
                { label: 'SEC fees', value: c.fees }, { label: 'Borrow', value: c.borrow },
                { label: 'Financing (net)', value: -c.financing_net, note: 'Positive = paid; negative = interest earned on cash' }]} />
            <div className="text-[10px] text-text-tertiary">Average long {pct(c.avg_long, 0)} · short {pct(c.avg_short, 0)} of capital.</div>
            {r.weights_last && Object.keys(r.weights_last).length > 0 && (
              <BarList title="Latest target (what the model wants)" diverging fmt={(v) => `${(v * 100).toFixed(1)}%`}
                data={Object.entries(r.weights_last).sort((x: any, y: any) => Math.abs(y[1]) - Math.abs(x[1])).slice(0, 12).map(([k, v]) => ({ label: k, value: v as number, sub: r.holdings_last ? `held ${((r.holdings_last[k] ?? 0) * 100).toFixed(1)}%` : undefined }))} />)}
            {r.holdings_last && <div className="text-[10px] text-text-tertiary">“held” is the simulated account after drift and unfilled orders — a target is not a position.</div>}
          </div>
        ) : r.weights_last && (
          <BarList title="Current allocation" fmt={(v) => `${(v * 100).toFixed(1)}%`}
            data={Object.entries(r.weights_last).map(([k, v]) => ({ label: k, value: v as number }))} />)}
      </div>
      <RecordPanel r={r} prov={prov} ex={ex} reg={reg} />
      {opt.walk_forward && opt.chosen && <Optimisation opt={opt} m={m} />}
      {opt.variants && <Variants opt={opt} />}
      {a?.factor_lens && <FactorLens f={a.factor_lens} />}
      {mc ? <MonteCarlo mc={mc} /> : a === null && <div className="flex items-center gap-2 text-2xs text-text-tertiary"><Loader2 className="w-3 h-3 animate-spin" />Monte Carlo…</div>}
      {a?.deep && (
        <div className="border border-border p-3">
          <div className="text-xs font-semibold text-text-primary mb-2">Deep analysis</div>
          <DeepReport d={a.deep} />
        </div>)}
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
      {prov.rf_known === false && <div className="text-amber">The T-bill rate was unavailable: cash earned 0% and Sharpe is on raw returns. Statistics will differ when the rate loads.</div>}
      {prov.engine_mismatch && <div className="text-amber">{prov.engine_mismatch}</div>}
      {prov.stale_symbols?.length > 0 && <div className="text-amber">Served from an out-of-date cache (download failed): {prov.stale_symbols.join(', ')}.</div>}
      {h && (
        <table className="font-mono"><tbody>
          <tr><td className="pr-3 text-text-tertiary">Before holdout ({h.start})</td><td className="pr-3">CAGR {spct(h.in_sample?.cagr)}</td><td>Sharpe {num(h.in_sample?.sharpe)}</td></tr>
          <tr><td className="pr-3 text-text-tertiary">Holdout</td><td className="pr-3">CAGR {spct(h.holdout?.cagr)}</td><td>Sharpe {num(h.holdout?.sharpe)}</td></tr>
          <tr><td className="pr-3 text-text-tertiary">Equal-weight universe, holdout</td><td className="pr-3">CAGR {spct(h.baseline_holdout?.cagr)}</td><td>Sharpe {num(h.baseline_holdout?.sharpe)}</td></tr>
        </tbody></table>)}
      {ex && <div className="text-text-secondary">Execution: {ex.unfilled_order_days} day(s) with orders that could not fill (no opening print or no volume) · {ex.stale_position_days} position-day(s) valued at a stale price · {ex.listings_ended} listing(s) ended while held (settled at last close).</div>}
      <details><summary className="cursor-pointer text-text-tertiary">Provenance</summary>
        <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-x-4 font-mono text-[10px] text-text-tertiary">
          <div>engine {prov.engine_version} · cost schema {prov.cost_schema_version}</div><div>runtime {prov.runtime ?? 'server'}</div>
          <div>data {prov.data_first} → {prov.data_last} · hash {prov.data_hash}</div><div>code hash {prov.code_hash ?? '—'}</div>
          <div className="md:col-span-2 font-sans">{prov.adjustment}</div>
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

/**
 * Code Lab — write a strategy in Python, test it in the browser (Pyodide worker), see it net of every
 * cost, walk-forward optimised, Monte-Carlo'd and deep-analysed; save it or deploy it to a paper trader
 * (deployment runs the code in the server's sandbox). Engine: api/quant/codelab.py.
 */
import { useCallback, useMemo, useRef, useState } from 'react';
import { Loader2, Play, Rocket, Save, ShieldCheck, ShieldAlert, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { BarList } from '@/components/ui/BarList';
import { CATEGORICAL } from '@/lib/chartPalette';
import { DeepReport } from './DeepReport';
import { api, ErrorNote, Field, inputCls, num, pct, spct, tone, usd } from './shared';

export const STARTER = `# Your strategy. Runs in your browser (Python 3 + numpy + pandas).
# Return target weights: dates × tickers, fraction of capital (+long / −short).
# A row decided with data up to that day's close is traded at the next day's open,
# net of commission, spread, market impact, fees, borrow and financing.
UNIVERSE = ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC"]
START = "2007-01-01"
# Optional: a small grid — each January the best set on past data (net of costs) is used,
# so the record you see is out-of-sample (walk-forward).
PARAMS = {"lookback": [126, 252], "target_vol": [0.10, 0.12]}


def strategy(data, lookback=252, target_vol=0.10):
    px = data.close                                   # also: data.open/high/low/volume, data.rf, data.vix
    trend = momentum(px, lookback, 21) > 0            # helpers: momentum, ewma_vol, vol_target,
    w = trend / ewma_vol(px, 63)                      #          normalize_gross, hold_monthly, hold_weekly
    w = normalize_gross(w)                            # sum |w| = 1
    w = vol_target(w, px, target_vol, max_leverage=2.0)
    return hold_monthly(w)                            # trade once a month
`;

export const COST_DEFAULTS = { capital: 1_000_000, commission_bps: 0.35, spread_mult: 1, impact_coef_bps: 11.21, borrow_fee: 0.003,
  financing_spread: 0.01, no_trade_band: 0.0025 };
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
  const [check, setCheck] = useState<{ ok: boolean; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [capital, setCapital] = useState(1_000_000);

  const run = useCallback(async () => {
    setBusy(true); setErr(null); setNote(null); setLog([]); setResult(null); setAnalysis(null);
    api('/api/v1/quant/code/check', { json: { code } }).then(setCheck).catch(() => setCheck(null));
    try {
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
      const a = await api('/api/v1/quant/code/analyze', { json: { dates: r.dates, returns: r.returns, benchmark: r.benchmark, label: name || 'Strategy', benchmark_label: header.benchmark, ...mc } });
      setAnalysis(a);
      setStatus(null);
    } catch (e: any) { setErr(e.message); setStatus(null); } finally { setBusy(false); }
  }, [code, costs, mc, name]);

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
    if (!window.confirm(`Deploy “${name || 'this strategy'}” with $${capital.toLocaleString()} of paper capital? The server re-runs your code daily in a locked-down sandbox; no real orders.`)) return;
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
              {check.ok ? 'Deployable: passes the server sandbox rules.' : `Runs here, but can't be deployed: ${check.error}`}
            </div>)}
          {status && <div className="flex items-center gap-2 text-2xs text-text-secondary"><Loader2 className="w-3 h-3 animate-spin" />{status}</div>}
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
              <Field label="Capital ($)" hint="Size matters: market impact grows with the square root of your share of daily volume"><input type="number" className={inputCls} value={costs.capital} onChange={set('capital')} /></Field>
              <Field label="Commission (bp)" hint="Per side, of traded notional. 0.35 bp ≈ $0.0035/share at $100"><input type="number" step={0.05} className={inputCls} value={costs.commission_bps} onChange={set('commission_bps')} /></Field>
              <Field label="Spread ×" hint="Multiplier on the modelled half-spread (from each asset's volatility and dollar volume)"><input type="number" step={0.25} className={inputCls} value={costs.spread_mult} onChange={set('spread_mult')} /></Field>
              <Field label="Impact coef (bp)" hint="bp × √(% of daily dollar volume). 11.2 = AQR live-trade calibration (Frazzini, Israel & Moskowitz 2018)"><input type="number" step={0.5} className={inputCls} value={costs.impact_coef_bps} onChange={set('impact_coef_bps')} /></Field>
              <Field label="Borrow fee (/yr)" hint="Annual fee on short notional; 0.3% = general collateral"><input type="number" step={0.001} className={inputCls} value={costs.borrow_fee} onChange={set('borrow_fee')} /></Field>
              <Field label="Margin spread (/yr)" hint="Borrowing above 100% gross long pays the T-bill rate plus this"><input type="number" step={0.0025} className={inputCls} value={costs.financing_spread} onChange={set('financing_spread')} /></Field>
              <Field label="No-trade band" hint="Skip rebalancing a position by less than this fraction of capital"><input type="number" step={0.0025} className={inputCls} value={costs.no_trade_band} onChange={set('no_trade_band')} /></Field>
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
        <li>Optional: <code>START</code>, <code>BENCHMARK</code>, <code>PARAMS</code> (≤ 48 combinations, walk-forward).</li>
        <li><code>print()</code> shows in Output. In the browser you can also import scipy, scikit-learn or statsmodels; deployable code is limited to numpy, pandas and math.</li>
      </ul>
    </details>
  );
}

// ── Results (shared with the strategy library) ──────────────────────────────
function curve(dates: string[], rets: number[], bench?: number[] | null, gross?: number[] | null) {
  const n = dates.length, step = Math.max(1, Math.ceil(n / 900));
  let e = 1, g = 1, b = 1;
  const rows: any[] = [];
  for (let i = 0; i < n; i++) {
    e *= 1 + rets[i]; if (gross) g *= 1 + gross[i]; if (bench) b *= 1 + (bench[i] || 0);
    if (i % step === 0 || i === n - 1) rows.push({ date: dates[i], net: +e.toFixed(4), ...(gross ? { gross: +g.toFixed(4) } : {}), ...(bench ? { bench: +b.toFixed(4) } : {}) });
  }
  return rows;
}

export function CodeResults({ r, a }: { r: any; a: any | null }) {
  const m = r.metrics ?? {}, g = r.metrics_gross, c = r.costs, b = r.benchmark_metrics, opt = r.optimisation ?? {};
  const rows = useMemo(() => curve(r.dates, r.returns, r.benchmark, r.gross), [r]);
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
        { label: r.benchmark_label || 'Benchmark', value: b ? spct(b.cagr) : '—', sub: b ? `Sharpe ${num(b.sharpe)} · DD ${pct(b.max_drawdown, 0)}` : undefined },
        { label: 'Record', value: opt.walk_forward ? 'Out-of-sample' : 'Full sample', sub: `${r.dates[0]} → ${r.dates[r.dates.length - 1]}` },
      ]} />
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <div className="xl:col-span-2">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Growth of $1 — net of all costs{r.gross ? ', before costs' : ''}{r.benchmark ? `, and ${r.benchmark_label || 'benchmark'}` : ''}</div>
          <LineChart rows={rows} x="date" height={260} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
            lines={[{ key: 'net', label: 'Net', color: CATEGORICAL[0] }, ...(r.gross ? [{ key: 'gross', label: 'Before costs', color: CATEGORICAL[3] }] : []),
              ...(r.benchmark ? [{ key: 'bench', label: r.benchmark_label || 'Benchmark', color: CATEGORICAL[6] }] : [])]} />
        </div>
        {c ? (
          <div className="space-y-2">
            <BarList title="Average cost per year (% of capital)" fmt={(v) => `${(v * 100).toFixed(2)}%`}
              data={[{ label: 'Market impact', value: c.impact }, { label: 'Spread', value: c.spread }, { label: 'Commission', value: c.commission },
                { label: 'SEC fees', value: c.fees }, { label: 'Borrow', value: c.borrow },
                { label: 'Financing (net)', value: -c.financing_net, note: 'Positive = paid; negative = interest earned on cash' }]} />
            <div className="text-[10px] text-text-tertiary">Average long {pct(c.avg_long, 0)} · short {pct(c.avg_short, 0)} of capital.</div>
            {r.weights_last && Object.keys(r.weights_last).length > 0 && (
              <BarList title="Current target weights" diverging fmt={(v) => `${(v * 100).toFixed(1)}%`}
                data={Object.entries(r.weights_last).sort((x: any, y: any) => Math.abs(y[1]) - Math.abs(x[1])).slice(0, 12).map(([k, v]) => ({ label: k, value: v as number }))} />)}
          </div>
        ) : r.weights_last && (
          <BarList title="Current allocation" fmt={(v) => `${(v * 100).toFixed(1)}%`}
            data={Object.entries(r.weights_last).map(([k, v]) => ({ label: k, value: v as number }))} />)}
      </div>
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
        {opt.grid?.length ?? '?'} parameter sets; each January the set with the best long-run growth on data up to then was traded for the year.
        Out-of-sample from {opt.oos_start}: CAGR {spct(m.cagr)}, Sharpe {num(m.sharpe)}.
        {ib && <> Picking the best set with hindsight would have shown CAGR {spct(ib.cagr)} / Sharpe {num(ib.sharpe)} — the gap is the overfitting a single backtest hides.</>}
      </div>
      <div className="flex flex-wrap gap-1 font-mono">
        {changes.map((c: any) => <span key={c.year} className="px-1.5 py-0.5 border border-border">{c.year}: {Object.entries(c.params).map(([k, v]) => `${k}=${v}`).join(', ')}</span>)}
      </div>
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

/**
 * Macro Model — the systematic model as one workflow, for three economies:
 *   United States (FRED; the only model with a tradeable sleeve), Euro area (Eurostat + ECB, in EUR) and
 *   Rest of the world (OECD leading indicators and unemployment + BIS CPI for nine economies, in USD).
 *   World strip (every economy's regime) → 1 Economic state → 2 Regime probabilities → 3 Expected returns &
 *   portfolio → 4 Walk-forward backtest → 5 Orders (US only; staged into the four-eyes workflow) → 6 Time machine
 *   (scrub or play through what the model said at each month, with hindsight).
 * Parameters can be changed and the model re-run (quant / PM); every run is recorded with its economy.
 * Reads /api/v1/model?economy=, /api/v1/model/world, /api/v1/model/params, /api/v1/model/run, /api/v1/model/orders/*.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Cpu, History, RefreshCw, Settings2, Send } from 'lucide-react';
import { LineChart } from '@/components/ui/LineChart';
import { useAuth } from '@/context/AuthContext';
import { useMacroStore } from '@/store/macroStore';
import { pct } from '@/lib/format';
import { TimeMachine } from './TimeMachine';

// Categorical slots validated on the dark surface (#0d1117): fixed order, never cycled.
const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500'];

const sgn = (v: number | null | undefined, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(d)}`);

type Economy = 'us' | 'ea' | 'row';
const ECONOMIES: { id: Economy; label: string; short: string }[] = [
  { id: 'us', label: 'United States', short: 'US' },
  { id: 'ea', label: 'Euro area', short: 'EA' },
  { id: 'row', label: 'Rest of world', short: 'RoW' },
];
const ECON_KEY = 'model_economy';
const readEconomy = (): Economy => {
  try { const v = localStorage.getItem(ECON_KEY); return v === 'ea' || v === 'row' ? v : 'us'; } catch { return 'us'; }
};
const arrow = (v?: number | null) => (v == null ? '' : v > 0.02 ? '▲' : v < -0.02 ? '▼' : '■');

/** The three economies side by side; a card opens that economy's model below. */
function WorldStrip({ active, onPick }: { active: Economy; onPick: (e: Economy) => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetch('/api/v1/model/world').then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => { if (alive) setRows(j.economies ?? []); })
      .catch((e) => { if (alive) setErr(e?.message || 'unavailable'); });
    return () => { alive = false; };
  }, []);
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-2" role="tablist" aria-label="Economy">
      {ECONOMIES.map((e) => {
        const r = rows?.find((x) => x.economy?.id === e.id);
        const on = active === e.id;
        return (
          <button key={e.id} role="tab" aria-selected={on} onClick={() => onPick(e.id)}
            className={`text-left p-2.5 border transition-colors ${on ? 'border-bloomberg bg-bloomberg/10' : 'border-border bg-surface-1 hover:border-border-strong'}`}>
            <div className="flex items-center gap-2">
              <span className={`text-[10px] font-mono font-bold px-1 ${on ? 'bg-bloomberg text-bg' : 'border border-border text-text-secondary'}`}>{e.short}</span>
              <span className="text-xs font-semibold text-text-primary">{e.label}</span>
              {r?.economy?.currency && <span className="text-[10px] text-text-tertiary font-mono">{r.economy.currency}</span>}
              <span className="ml-auto text-[10px] text-text-tertiary font-mono">{r?.available ? `to ${r.factor_as_of}` : ''}</span>
            </div>
            {!rows && !err && <div className="mt-2 h-8 animate-pulse bg-surface-2" />}
            {(err || (r && !r.available)) && <div className="mt-1.5 text-[10px] text-amber">{r?.reason || err}</div>}
            {r?.available && (
              <>
                <div className="mt-1.5 flex items-baseline gap-2">
                  <span className="text-sm font-semibold text-text-primary">{r.regime}</span>
                  <span className="font-mono text-xs text-bloomberg">{pct(r.probabilities[r.regime], 0)}</span>
                </div>
                <div className="mt-1 grid grid-cols-2 gap-x-3 text-[10px] font-mono text-text-tertiary">
                  <span>Growth <span className="text-text-primary">{sgn(r.growth_factor)}σ</span>{' '}
                    <span className={r.growth_change_3m > 0 ? 'text-green' : r.growth_change_3m < 0 ? 'text-red' : ''}>{arrow(r.growth_change_3m)}</span></span>
                  <span>Inflation <span className="text-text-primary">{sgn(r.inflation_factor)}σ</span>{' '}
                    <span className={r.inflation_change_3m > 0 ? 'text-red' : r.inflation_change_3m < 0 ? 'text-green' : ''}>{arrow(r.inflation_change_3m)}</span></span>
                  <span>P(growth ↑) <span className="text-text-primary">{pct(r.p_growth_rising, 0)}</span></span>
                  <span>P(inflation ↑) <span className="text-text-primary">{pct(r.p_inflation_rising, 0)}</span></span>
                </div>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}


function Step({ n, title, children, right }: { n: number; title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="p-3 bg-surface-1 border border-border">
      <div className="flex items-center gap-2 mb-2">
        <span className="w-5 h-5 inline-flex items-center justify-center text-2xs font-mono border border-bloomberg/50 text-bloomberg">{n}</span>
        <span className="text-xs font-semibold text-text-primary uppercase tracking-wider">{title}</span>
        <span className="ml-auto">{right}</span>
      </div>
      {children}
    </div>
  );
}

export function MacroModelSection() {
  const signalRegime = useMacroStore((st) => st.regime.current);
  const { user } = useAuth();
  const canRun = user && ['quant', 'pm', 'admin'].includes(user.role);
  const canStage = user && ['pm', 'quant', 'admin'].includes(user.role);
  const [data, setData] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [params, setParams] = useState<Record<string, number>>({});
  const [showParams, setShowParams] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [which, setWhich] = useState<'strategic' | 'tactical'>('strategic');
  const [orders, setOrders] = useState<any>(null);
  const [staged, setStaged] = useState<any>(null);
  const [economy, setEconomyState] = useState<Economy>(readEconomy);
  const [showInputs, setShowInputs] = useState(false);
  // the <GO> line ("EA MODEL") and links can switch the economy shown
  useEffect(() => {
    const h = (e: Event) => { const v = (e as CustomEvent).detail; if (v === 'us' || v === 'ea' || v === 'row') { setEconomyState(v); setOrders(null); setStaged(null); } };
    window.addEventListener('model-economy', h);
    return () => window.removeEventListener('model-economy', h);
  }, []);
  const setEconomy = (e: Economy) => {
    setEconomyState(e); setOrders(null); setStaged(null);
    try { localStorage.setItem(ECON_KEY, e); } catch { /* storage unavailable */ }
  };

  const load = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const get = async (u: string) => {
        const r = await fetch(u);
        const j = await r.json().catch(() => null);
        if (!r.ok || !j) throw new Error((typeof j?.detail === 'string' && j.detail) || `HTTP ${r.status}`);
        return j;
      };
      const [m, p] = await Promise.all([get(`/api/v1/model?economy=${economy}`), get('/api/v1/model/params')]);
      if (m.available === false) throw new Error(m.reason);
      if (!m.state || !m.portfolios) throw new Error('Model response incomplete');
      setData(m); setMeta(p); setParams(m.params);
    } catch (e: any) { setError(e?.message || 'Model unavailable'); }
    finally { setBusy(false); }
  }, [economy]);
  useEffect(() => { setData(null); load(); }, [load]);

  const rerun = async () => {
    setBusy(true); setError(null); setOrders(null); setStaged(null);
    try {
      const r = await fetch('/api/v1/model/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ params, economy }) });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : `HTTP ${r.status}`);
      if (j.available === false || !j.state) throw new Error(j.reason || 'Model response incomplete');
      setData(j);
    } catch (e: any) { setError(e?.message); } finally { setBusy(false); }
  };

  const orderCall = async (path: 'preview' | 'stage') => {
    setBusy(true); setError(null);
    try {
      const r = await fetch(`/api/v1/model/orders/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ portfolio: which, params: data?.params }) });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : `HTTP ${r.status}`);
      path === 'preview' ? setOrders(j) : setStaged(j);
    } catch (e: any) { setError(e?.message); } finally { setBusy(false); }
  };

  const port = data?.portfolios?.[which];
  const econ = data?.economy;
  const tradeable = econ ? econ.tradeable !== false : economy === 'us';
  const series: any[] = data?.data?.series ?? [];
  const bt = data?.backtest;
  const assetRows = useMemo(() => port ? Object.keys(port.weights).map((a) => ({
    asset: a, etf: port.etfs[a], w: port.weights[a], rc: port.risk_contributions[a],
    er: data.expected_returns[a]?.posterior, model: data.expected_returns[a]?.model,
  })).sort((x, y) => y.w - x.w) : [], [port, data]);

  return (
    <div id="macro-model" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Cpu className="w-3 h-3" /></span>
          <h2 className="section-title">Macro Model</h2>
          {econ && <span className="text-2xs font-mono text-bloomberg">{econ.name} · {econ.currency}</span>}
          {data && <span className="text-2xs text-text-tertiary font-mono">v{data.version} · data to {data.as_of} · {data.run_id ? `run ${data.run_id}` : (data as any).snapshot ? `computed ${String((data as any).snapshot.saved_at).slice(0, 16).replace('T', ' ')} UTC` : (data as any).computed_at ? `computed ${String((data as any).computed_at).slice(0, 16).replace('T', ' ')} UTC` : 'not yet recorded'} · params {data.params_hash}</span>}
        </div>
        <div className="flex items-center gap-1">
          {canRun && (
            <button onClick={() => setShowParams((s) => !s)} className="p-1 text-text-tertiary hover:text-bloomberg" title="Parameters" aria-label="Parameters">
              <Settings2 className="w-3.5 h-3.5" />
            </button>
          )}
          <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
            <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <WorldStrip active={economy} onPick={setEconomy} />

      {error && <div className="mb-2 p-2 text-xs text-amber border border-amber/30 bg-amber-dim">{error}</div>}
      {!data && busy && <div className="p-3 text-2xs text-text-tertiary">Running the {ECONOMIES.find((e) => e.id === economy)?.label} model… a first run fetches the official statistics (up to a minute).</div>}

      {showParams && meta && (
        <div className="mb-3 p-3 bg-surface-1 border border-border">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {Object.keys(meta.defaults).map((k) => (
              <label key={k} className="text-2xs text-text-tertiary" title={meta.descriptions[k]}>
                <span className="block mb-0.5">{meta.descriptions[k]}</span>
                <input type="number" step="any" value={params[k] ?? ''} aria-label={k}
                  onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })}
                  className="w-full bg-bg border border-border px-2 py-1 font-mono text-xs text-text-primary" />
              </label>
            ))}
          </div>
          <div className="flex gap-2 mt-2">
            <button onClick={rerun} disabled={busy} className="px-3 py-1 text-xs bg-bloomberg text-bg disabled:opacity-50">Re-run model</button>
            <button onClick={() => setParams(meta.defaults)} className="px-3 py-1 text-xs border border-border text-text-secondary">Reset to defaults</button>
          </div>
        </div>
      )}

      {data && (
        <div className="space-y-2">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
            <Step n={1} title="Economic state" right={<span className="text-2xs text-text-tertiary">factors to {data.state.factor_as_of}</span>}>
              <div className="grid grid-cols-2 gap-2 mb-2 text-xs">
                <div><div className="text-2xs text-text-tertiary">Growth factor</div>
                  <span className="font-mono text-text-primary">{sgn(data.state.growth_factor)}σ</span>
                  <span className="text-2xs text-text-tertiary"> · 3M {sgn(data.state.growth_change_3m)}</span></div>
                <div><div className="text-2xs text-text-tertiary">Inflation factor</div>
                  <span className="font-mono text-text-primary">{sgn(data.state.inflation_factor)}σ</span>
                  <span className="text-2xs text-text-tertiary"> · 3M {sgn(data.state.inflation_change_3m)}</span></div>
              </div>
              <LineChart rows={data.state.history.slice(-60)} x="month" height={170} baseline={0}
                fmt={(v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}σ`} axisFmt={(v) => `${v.toFixed(1)}σ`}
                lines={[{ key: 'growth', label: 'Growth', color: SERIES[0] }, { key: 'inflation', label: 'Inflation', color: SERIES[1] }]} />
              <div className="text-[10px] text-text-tertiary">{data.methodology.factors}{' '}
                {series.length > 0 && <button onClick={() => setShowInputs((v) => !v)} className="text-bloomberg hover:underline">
                  {showInputs ? 'Hide inputs' : `Show the ${series.length} inputs`}</button>}</div>
              {showInputs && series.length > 0 && (
                <div className="mt-2 max-h-56 overflow-y-auto border border-border-subtle">
                  <table className="w-full text-[10px]">
                    <thead className="sticky top-0 bg-surface-2"><tr className="text-text-tertiary text-left">
                      <th className="font-normal px-1.5 py-0.5">Series</th><th className="font-normal">Block</th>
                      <th className="font-normal text-right">Loading</th><th className="font-normal text-right">From</th>
                      <th className="font-normal text-right">Latest</th><th className="font-normal text-right px-1.5" title="Publication lag applied, months">Lag</th></tr></thead>
                    <tbody>{series.map((c) => {
                      const load = data.state.loadings?.[c.block]?.[c.key];
                      return (
                        <tr key={c.key} className={`border-t border-border-subtle ${c.used ? '' : 'opacity-50'}`}
                          title={c.used ? `${c.key} · ${c.transform}` : `${c.key}: left out — latest observation ${c.months_behind} months behind`}>
                          <td className="px-1.5 py-0.5 text-text-secondary">{c.label}{!c.used && <span className="ml-1 text-amber">stale</span>}</td>
                          <td className="text-text-tertiary">{c.block}</td>
                          <td className="text-right font-mono text-text-primary">{load != null ? load.toFixed(2) : '—'}</td>
                          <td className="text-right font-mono text-text-tertiary">{c.first ?? '—'}</td>
                          <td className="text-right font-mono text-text-secondary">{c.last ?? '—'}</td>
                          <td className="text-right font-mono text-text-tertiary px-1.5">{c.lag_months}</td>
                        </tr>);
                    })}</tbody>
                  </table>
                </div>
              )}
            </Step>

            <Step n={2} title="Regime probabilities — next month">
              <div className="space-y-1.5">
                {Object.entries(data.regime.probabilities as Record<string, number>).sort((a, b) => b[1] - a[1]).map(([q, p]) => (
                  <div key={q} title={`${q}: ${pct(p)} · ${data.regime.observations_per_regime[q]} months of history`}>
                    <div className="flex justify-between text-2xs">
                      <span className={q === data.regime.most_likely ? 'text-text-primary' : 'text-text-secondary'}>{q}</span>
                      <span className="font-mono text-text-primary">{pct(p)}</span>
                    </div>
                    <div className="h-1.5 bg-surface-3"><div className="h-1.5 bg-bloomberg" style={{ width: `${p * 100}%` }} /></div>
                  </div>
                ))}
              </div>
              {economy === 'us' && signalRegime && data.regime.most_likely && signalRegime.toLowerCase() !== String(data.regime.most_likely).toLowerCase() && (
                <div className="mt-2 p-2 border border-border-subtle bg-surface-2 text-2xs text-text-secondary">
                  <span className="text-text-primary">Why this differs from the Signal Regime ({signalRegime}):</span> this model
                  forecasts <em>next month's</em> quadrant from slow-moving economic data (growth &amp; inflation factors),
                  while the Signal Regime classifies <em>today</em> from market prices. A disagreement is a heads-up that the
                  macro data points to a change the market hasn't priced yet — not an error.
                </div>
              )}
              <div className="grid grid-cols-2 gap-2 mt-2 text-2xs text-text-tertiary">
                <div>P(growth rising) <span className="font-mono text-text-primary">{pct(data.regime.p_growth_rising, 0)}</span> (base {pct(data.regime.base_rates.growth_rising, 0)})</div>
                <div>P(inflation rising) <span className="font-mono text-text-primary">{pct(data.regime.p_inflation_rising, 0)}</span> (base {pct(data.regime.base_rates.inflation_rising, 0)})</div>
                {data.regime.markov_switching?.p_contraction_regime != null && (
                  <div className="col-span-2">Markov-switching contraction regime: <span className="font-mono text-text-primary">{pct(data.regime.markov_switching.p_contraction_regime)}</span>
                    {data.regime.markov_switching.expected_duration_months && <> · typical duration {data.regime.markov_switching.expected_duration_months} months</>}</div>
                )}
              </div>
              {bt?.forecast_skill?.growth_direction && (
                <div className="mt-2 text-[10px] text-text-tertiary">
                  Out-of-sample skill ({bt.forecast_skill.months_scored} months): growth direction {pct(bt.forecast_skill.growth_direction.accuracy, 0)} correct
                  (Brier skill {bt.forecast_skill.growth_direction.skill}); inflation {pct(bt.forecast_skill.inflation_direction.accuracy, 0)} (skill {bt.forecast_skill.inflation_direction.skill}).
                </div>
              )}
            </Step>
          </div>

          <Step n={3} title="Expected returns & portfolio" right={
            <div className="flex gap-1">
              {(['strategic', 'tactical'] as const).map((k) => (
                <button key={k} onClick={() => { setWhich(k); setOrders(null); setStaged(null); }}
                  className={`px-2 py-0.5 text-2xs uppercase border ${which === k ? 'bg-bloomberg text-bg border-bloomberg' : 'border-border text-text-secondary'}`}>{k}</button>
              ))}
            </div>}>
            {port && <>
              <div className="flex flex-wrap gap-4 text-2xs text-text-tertiary mb-2">
                <span>Expected vol <span className="font-mono text-text-primary">{pct(port.expected_vol)}</span></span>
                <span>Expected excess return <span className="font-mono text-text-primary">{pct(port.expected_excess_return)}</span></span>
                <span>Gross <span className="font-mono text-text-primary">{pct(port.gross, 0)}</span></span>
                <span>{port.cash >= 0 ? 'Cash' : 'Financing'} <span className="font-mono text-text-primary">{pct(Math.abs(port.cash), 0)}</span></span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-2xs font-mono">
                  <thead><tr className="text-text-tertiary text-left">
                    <th className="font-normal pb-1 font-sans">Asset class</th><th className="font-normal pb-1">{tradeable ? 'ETF' : 'Instrument'}</th>
                    <th className="font-normal pb-1 text-right">Weight</th><th className="font-normal pb-1 text-right">Risk share</th>
                    <th className="font-normal pb-1 text-right" title="Black–Litterman posterior, annualised excess return">E[r] posterior</th>
                    <th className="font-normal pb-1 text-right" title="Regime-conditional model view">Model view</th></tr></thead>
                  <tbody>
                    {assetRows.map((r) => (
                      <tr key={r.asset} className="border-t border-border-subtle">
                        <td className="py-0.5 font-sans text-text-secondary">{r.asset}</td>
                        <td className="text-text-tertiary" data-symbol={r.etf}>{r.etf}</td>
                        <td className="text-right text-text-primary">{pct(r.w)}</td>
                        <td className="text-right text-text-secondary">{pct(r.rc)}</td>
                        <td className="text-right text-text-secondary">{pct(r.er)}</td>
                        <td className="text-right text-text-tertiary">{pct(r.model)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="text-[10px] text-text-tertiary mt-1">{which === 'strategic'
                ? 'Strategic: equal risk to each growth/inflation environment, scaled to the volatility target. No views.'
                : data.methodology.portfolio}</div>
            </>}
          </Step>

          {bt?.available && (
            <Step n={4} title={`Walk-forward backtest ${bt.start} → ${bt.end}`} right={<span className="text-2xs text-text-tertiary">{bt.returns_are}</span>}>
              <LineChart rows={bt.equity_curve} x="month" height={220} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`} axisFmt={(v) => `${v >= 1 ? v.toFixed(0) : v.toFixed(1)}×`}
                lines={[{ key: 'model', label: 'Tactical', color: SERIES[0] }, { key: 'strategic', label: 'Strategic', color: SERIES[1] },
                        { key: 'sixty_forty', label: bt.sixty_forty ? `60/40 (${bt.sixty_forty.equity} / ${bt.sixty_forty.bonds})` : '60/40', color: SERIES[2] }, { key: 'risk_parity', label: 'Risk parity', color: SERIES[3] }]} />
              <div className="overflow-x-auto mt-2">
                <table className="w-full text-2xs font-mono">
                  <thead><tr className="text-text-tertiary text-left">
                    <th className="font-normal pb-1 font-sans">Strategy</th><th className="font-normal text-right">CAGR</th><th className="font-normal text-right">Vol</th>
                    <th className="font-normal text-right">Sharpe</th><th className="font-normal text-right">Sortino</th><th className="font-normal text-right">Max DD</th>
                    <th className="font-normal text-right">Calmar</th><th className="font-normal text-right">Months</th></tr></thead>
                  <tbody>
                    {Object.entries(bt.stats as Record<string, any>).map(([k, s]) => (
                      <tr key={k} className="border-t border-border-subtle">
                        <td className="py-0.5 font-sans text-text-secondary">{k}</td>
                        <td className="text-right text-text-primary">{pct(s.cagr)}</td><td className="text-right">{pct(s.vol)}</td>
                        <td className="text-right text-text-primary">{s.sharpe ?? '—'}</td><td className="text-right">{s.sortino ?? '—'}</td>
                        <td className="text-right">{pct(s.max_drawdown)}</td><td className="text-right">{s.calmar ?? '—'}</td>
                        <td className="text-right text-text-tertiary">{s.months}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {bt.tactical_vs_strategic && (
                <div className="text-2xs text-text-secondary mt-2">
                  Tactical tilt vs strategic: {sgn(bt.tactical_vs_strategic.annualised_diff * 100, 2)}% a year,
                  t-stat {bt.tactical_vs_strategic.t_stat}, information ratio {bt.tactical_vs_strategic.information_ratio} —{' '}
                  <span className={bt.tactical_vs_strategic.significant_5pct ? 'text-green' : 'text-amber'}>
                    {bt.tactical_vs_strategic.significant_5pct ? 'statistically significant at 5%' : 'not statistically significant'}
                  </span>.
                </div>
              )}
              <div className="text-[10px] text-text-tertiary mt-1">
                Re-estimated every month on data available at the time; costs {data.params.cost_bps}bp per unit turnover;
                average monthly turnover {pct(bt.avg_turnover_monthly, 0)}. Limitations: {data.methodology.limitations.join(' ')}
                {data.data?.sources?.length > 0 && <> Sources: {data.data.sources.join('; ')}.</>}
              </div>
            </Step>
          )}

          {!tradeable ? (
            <Step n={5} title="Orders">
              <div className="text-2xs text-text-tertiary">
                Research view: the {econ?.name ?? 'selected'} model's portfolio is not traded. Orders are generated for the
                US model's sleeve only (book “Macro Model”). The instruments listed are the liquid UCITS / US ETFs that
                track each asset class.
              </div>
            </Step>
          ) : (
          <Step n={5} title={`Orders — ${which} portfolio`} right={
            <div className="flex gap-1">
              {canStage && <button onClick={() => orderCall('preview')} disabled={busy} className="px-2 py-0.5 text-2xs border border-border text-text-secondary hover:text-bloomberg disabled:opacity-50">Preview orders</button>}
              {canStage && orders && orders.order_count > 0 && !staged && (
                <button onClick={() => orderCall('stage')} disabled={busy} className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs bg-bloomberg text-bg disabled:opacity-50">
                  <Send className="w-3 h-3" />Stage {orders.order_count} for approval
                </button>
              )}
            </div>}>
            {!canStage && <div className="text-2xs text-text-tertiary">Order generation is available to the PM and quant roles.</div>}
            {canStage && !orders && <div className="text-2xs text-text-tertiary">The model manages its own sleeve (book “Macro Model”, its ten ETFs); other holdings are never traded.</div>}
            {orders && (
              <div>
                <div className="text-2xs text-text-tertiary mb-1">
                  Sleeve capital {orders.sleeve_capital?.toLocaleString()} ({orders.sleeve_capital_basis}) · turnover {pct(orders.turnover_pct_nav)} · estimated cost {orders.est_total_cost?.toLocaleString()}
                </div>
                {orders.clipped_by_limits && Object.keys(orders.clipped_by_limits).length > 0 && (
                  <div className="text-2xs text-amber mb-1">
                    Capped at the fund's single-name limit ({pct(orders.single_name_limit, 0)} of NAV, all books), excess held in cash:{' '}
                    {Object.entries(orders.clipped_by_limits).map(([s, c]: [string, any]) => `${s} ${pct(c.model_weight)} → ${pct(c.capped_weight)}`).join(', ')}
                  </div>
                )}
                {orders.order_count === 0 ? <div className="text-2xs text-green">Sleeve already at target.</div> : (
                  <table className="w-full text-2xs font-mono">
                    <thead><tr className="text-text-tertiary text-left"><th className="font-normal pb-1">ETF</th><th className="font-normal">Action</th>
                      <th className="font-normal">Side</th><th className="font-normal text-right">Qty</th><th className="font-normal text-right">Notional</th>
                      <th className="font-normal text-right">Target</th></tr></thead>
                    <tbody>{orders.orders.map((o: any) => (
                      <tr key={o.symbol} className="border-t border-border-subtle">
                        <td className="py-0.5 text-text-primary">{o.symbol}</td><td className="text-text-tertiary">{o.action}</td>
                        <td className={o.side === 'BUY' ? 'text-green' : 'text-red'}>{o.side}</td>
                        <td className="text-right">{o.quantity.toLocaleString()}</td><td className="text-right">{o.notional.toLocaleString()}</td>
                        <td className="text-right">{pct(o.target_weight)}</td>
                      </tr>))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
            {staged && (() => {
              const dec = (staged.orders || []).map((o: any) => o.pretrade?.decision);
              const warn = dec.filter((d: string) => d === 'WARN').length, block = dec.filter((d: string) => d === 'BLOCK').length;
              return <div className="mt-2 text-2xs text-green">{staged.staged} orders staged with pre-trade checks — awaiting risk approval in Fund Overview.
                {(warn > 0 || block > 0) && <span className={block ? 'text-red' : 'text-amber'}> Pre-trade: {block} block, {warn} need risk sign-off.</span>}</div>;
            })()}
          </Step>
          )}

          {bt?.available && (
            <Step n={6} title="Time machine — what the model said then" right={<History className="w-3.5 h-3.5 text-text-tertiary" />}>
              <TimeMachine timeline={bt.timeline} sixtyForty={bt.sixty_forty} />
            </Step>
          )}
        </div>
      )}
    </div>
  );
}

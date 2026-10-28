/**
 * Options research — staged experiments on four defined-risk option strategies (bull put credit, bull call debit,
 * bear put debit, short iron condor), regime models and portfolio construction, with validation, a research registry,
 * a sealed holdout and the controlled export of approved configurations for the Quant Algorithm.
 * Reads /api/v1/quant/options-research/* (api/routers/optresearch.py, api/quant/optresearch).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, FlaskConical, Loader2, Lock, Play, RotateCcw, ShieldAlert, Square, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import { LineChart } from '@/components/ui/LineChart';
import { CATEGORICAL, OTHER_GRAY } from '@/lib/chartPalette';
import { api, ErrorNote, num, pct, Pills, spct } from './shared';

const BASE = '/api/v1/quant/options-research';
type View = 'results' | 'registry' | 'configs' | 'performance';
type RTab = 'summary' | 'strategies' | 'regimes' | 'portfolio' | 'data' | 'holdout';

const STATUS: Record<string, string> = {
  survived: 'text-green border-green/40', rejected: 'text-red border-red/40', inconclusive: 'text-amber border-amber/40',
  proposed: 'text-text-tertiary border-border', testing: 'text-bloomberg border-bloomberg/40',
};

function Badge({ s }: { s: string }) {
  return <span className={cn('px-1.5 py-0.5 border text-[10px] uppercase tracking-wide', STATUS[s] ?? STATUS.proposed)}>{s}</span>;
}

function Card({ title, children, note }: { title: string; children: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="p-3 bg-surface-1 border border-border space-y-2">
      <div className="text-xs font-semibold text-text-primary">{title}</div>
      {children}
      {note && <div className="text-[10px] text-text-tertiary">{note}</div>}
    </div>
  );
}

function Table({ cols, rows, dense }: { cols: { k: string; label: string; f?: (v: any, r: any) => React.ReactNode; right?: boolean }[]; rows: any[]; dense?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-2xs font-mono">
        <thead><tr className="text-text-tertiary border-b border-border">
          {cols.map((c) => <th key={c.k} className={cn('px-1.5 py-1 font-normal whitespace-nowrap', c.right ? 'text-right' : 'text-left')}>{c.label}</th>)}
        </tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i} className="border-b border-border/40 hover:bg-surface-2/50">
            {cols.map((c) => <td key={c.k} className={cn('px-1.5', dense ? 'py-0.5' : 'py-1', c.right ? 'text-right' : 'text-left', 'whitespace-nowrap')}>
              {c.f ? c.f(r[c.k], r) : (r[c.k] ?? '—')}</td>)}
          </tr>))}
        </tbody>
      </table>
    </div>
  );
}

const sh = (v: any) => <span className={v == null ? '' : v > 0 ? 'text-green' : 'text-red'}>{num(v, 2)}</span>;
const pc = (v: any) => <span className={v == null ? '' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : ''}>{spct(v, 1)}</span>;
const dd = (v: any) => <span className="text-red">{pct(v, 1)}</span>;

export function OptionsResearch() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const canRun = ['admin', 'pm', 'quant'].includes(user?.role ?? '');
  const [ov, setOv] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<View>('results');
  const [stage, setStage] = useState<'1' | '2' | '3' | '4'>('2');
  const [job, setJob] = useState<any>(null);
  const [eid, setEid] = useState<string | null>(null);
  const [res, setRes] = useState<any>(null);

  const load = useCallback(() => api(`${BASE}/overview`).then((o) => {
    setOv(o);
    setEid((cur) => cur ?? (o.experiments.find((e: any) => e.state === 'done' && e.stage > 1)?.id ?? null));
  }).catch((e) => setErr(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!eid) return;
    setRes(null);
    api(`${BASE}/experiments/${eid}`).then(setRes).catch((e) => setErr(e.message));
  }, [eid]);
  // job polling
  useEffect(() => {
    if (!job || ['done', 'failed', 'cancelled'].includes(job.state)) return;
    const t = setTimeout(() => api(`${BASE}/jobs/${job.id}`).then((j) => {
      setJob(j);
      if (j.state === 'done') { load(); if (j.result?.experiment_id) setEid(j.result.experiment_id); }
    }).catch(() => {}), 2000);
    return () => clearTimeout(t);
  }, [job, load]);

  const start = () => api(`${BASE}/run`, { method: 'POST', json: { stage: Number(stage) } }).then(setJob).catch((e) => setErr(e.message));
  const cancel = () => job && api(`${BASE}/jobs/${job.id}`, { method: 'DELETE' }).then(() => setJob({ ...job, state: 'cancelled' }));

  if (!ov) return <div className="text-2xs text-text-tertiary flex items-center gap-2">{err ? <ErrorNote msg={err} /> : <><Loader2 className="w-3 h-3 animate-spin" />Loading the research…</>}</div>;
  const running = job && !['done', 'failed', 'cancelled'].includes(job.state);
  return (
    <div className="space-y-3">
      <div className="p-3 bg-surface-1 border border-border space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <FlaskConical className="w-3.5 h-3.5 text-bloomberg" />
          <span className="text-xs font-semibold">Options strategy research</span>
          <span className="text-[10px] text-text-tertiary">research only — nothing here trades. Option prices are model-based (no free historical option quotes); every result is labelled.</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pills label="Stage" value={stage} onChange={setStage} options={[['1', '1 · correctness'], ['2', '2 · index ETFs'], ['3', '3 · intermediate'], ['4', '4 · full universe']] as const} />
          {canRun && (running
            ? <button onClick={cancel} className="inline-flex items-center gap-1 px-2 py-1 text-2xs border border-border hover:border-red"><Square className="w-3 h-3" />Cancel</button>
            : <button onClick={start} className="inline-flex items-center gap-1 px-2 py-1 text-2xs bg-bloomberg text-bg"><Play className="w-3 h-3" />Run stage {stage}</button>)}
          <span className="text-[10px] text-text-tertiary">{ov.stages[stage]}</span>
        </div>
        {job && (
          <div className={cn('text-2xs font-mono flex items-center gap-2', job.state === 'failed' ? 'text-red' : 'text-text-secondary')}>
            {running && <Loader2 className="w-3 h-3 animate-spin" />}
            <span>{job.state}</span><span>· {job.message}</span><span className="text-text-tertiary">· {Math.round(job.elapsed_s)} s</span>
            {job.error && <span className="text-red">{job.error}</span>}
          </div>
        )}
        <div className="text-[10px] text-text-tertiary">
          Development {ov.segments.development.join(' → ')} (searched) · validation {ov.segments.validation.join(' → ')} · holdout from {ov.segments.holdout_start} (sealed).
          A smaller stage never replaces stage 4: configurations exported from stages 1–3 are marked "not validated on the full universe".
        </div>
      </div>
      <ErrorNote msg={err} />
      <div className="flex flex-wrap gap-2 items-center">
        <Pills label="View" value={view} onChange={setView} options={[['results', 'Experiments & results'], ['registry', 'Research registry'], ['configs', 'Configurations'], ['performance', 'Backtest performance']] as const} />
      </div>
      {view === 'results' && <Results ov={ov} eid={eid} setEid={setEid} res={res} reload={load} canRun={canRun} />}
      {view === 'registry' && <Registry ov={ov} />}
      {view === 'configs' && <Configs ov={ov} res={res} eid={eid} isAdmin={isAdmin} canRun={canRun} reload={load} />}
      {view === 'performance' && <Performance ov={ov} />}
    </div>
  );
}

// ── experiments and results ──────────────────────────────────────────────────
function Results({ ov, eid, setEid, res, reload, canRun }: any) {
  const [tab, setTab] = useState<RTab>('summary');
  const exps = ov.experiments as any[];
  const r = res?.result;
  return (
    <div className="space-y-3">
      <Card title="Experiment history">
        <Table dense cols={[
          { k: 'id', label: 'Experiment', f: (v) => <button onClick={() => setEid(v)} className={cn('underline-offset-2 hover:underline', v === eid ? 'text-bloomberg' : '')}>{v}</button> },
          { k: 'stage', label: 'Stage' }, { k: 'state', label: 'State' }, { k: 'owner', label: 'By' },
          { k: 'runtime_s', label: 'Runtime', right: true, f: (v) => v == null ? '—' : `${Math.round(v)} s` },
          { k: 'peak_mb', label: 'Peak memory', right: true, f: (v) => v == null ? '—' : `${Math.round(v)} MB` },
          { k: 'trials', label: 'Configs tried', right: true },
          { k: 'summary', label: 'Survived', f: (v) => v?.superseded ? <span className="text-amber" title={v.superseded}>superseded — not a valid result</span> : v?.strategies ? Object.entries(v.strategies).filter(([, x]: any) => x.survived).map(([k]) => k).join(', ') || 'none' : v?.passed != null ? (v.passed ? 'all checks passed' : 'checks failed') : (v?.error ?? '—') },
          { k: 'holdout_reveals', label: 'Holdout views', right: true },
        ]} rows={exps.slice(0, 12)} />
      </Card>
      {!eid ? <div className="text-2xs text-text-tertiary">Run a stage to see results.</div> : !res ? <div className="text-2xs text-text-tertiary flex gap-2"><Loader2 className="w-3 h-3 animate-spin" />Loading {eid}…</div> : !r ? (
        <div className="text-2xs text-text-tertiary">No result file for this experiment ({res.meta?.state}). {res.meta?.summary?.error}</div>
      ) : r.stage === 1 ? <StageOne r={r} /> : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Pills label="Result" value={tab} onChange={setTab} options={[['summary', 'Summary & systems'], ['strategies', 'Strategies'], ['regimes', 'Regimes'], ['portfolio', 'Portfolio construction'], ['data', 'Data & validity'], ['holdout', 'Holdout']] as const} />
            <span className="text-[10px] text-text-tertiary">stage {r.stage} · {r.universe.underlyings} underlyings{r.universe.point_in_time ? ' (point-in-time S&P 500)' : ''} · {Math.round(r.runtime_s)} s · {Math.round(r.peak_rss_mb)} MB · {r.trials} configurations</span>
          </div>
          {tab === 'summary' && <Summary r={r} />}
          {tab === 'strategies' && <Strategies r={r} />}
          {tab === 'regimes' && <Regimes r={r} />}
          {tab === 'portfolio' && <PortfolioResearch r={r} />}
          {tab === 'data' && <DataValidity r={r} />}
          {tab === 'holdout' && <Holdout eid={eid} reload={reload} canRun={canRun} />}
        </>
      )}
    </div>
  );
}

function StageOne({ r }: { r: any }) {
  return (
    <Card title={`Stage 1 — correctness (${r.passed ? 'all passed' : 'FAILED'})`}>
      <div className="space-y-1">{r.checks.map((c: any) => (
        <div key={c.name} className="text-2xs flex gap-2 items-start">
          {c.passed ? <CheckCircle2 className="w-3 h-3 text-green shrink-0 mt-0.5" /> : <XCircle className="w-3 h-3 text-red shrink-0 mt-0.5" />}
          <span>{c.name}</span><span className="text-text-tertiary font-mono truncate">{JSON.stringify(c.detail).slice(0, 160)}</span>
        </div>))}
      </div>
    </Card>
  );
}

const SEG_COLS = (seg: string, label: string) => [
  { k: `${seg}_cagr`, label: `${label} CAGR`, right: true, f: pc }, { k: `${seg}_sharpe`, label: 'Sharpe', right: true, f: sh },
  { k: `${seg}_mdd`, label: 'Max DD', right: true, f: dd },
];

function Summary({ r }: { r: any }) {
  const sys = r.systems.systems;
  const order: string[] = r.systems.order;
  const rows = order.map((k) => {
    const s = sys[k];
    const d = s.segments.development, v = s.segments.validation, w = s.segments.walk_forward_window;
    return { key: k, label: s.label, dev_cagr: d.cagr, dev_sharpe: d.sharpe, dev_mdd: d.max_drawdown, val_cagr: v.cagr,
             val_sharpe: v.sharpe, val_mdd: v.max_drawdown, wf_sharpe: w.sharpe, trades: s.trades?.trades, costs: s.trades?.costs_pct_capital_per_year,
             survived: r.strategies[k]?.survival?.survived };
  });
  const colorOf = (i: number) => (i < CATEGORICAL.length ? CATEGORICAL[i] : OTHER_GRAY);
  const chart = useMemo(() => {
    const keys = order.filter((k) => sys[k].curve && k !== 'baseline_options_only');   // 8 lines: the seven systems + SPY
    const dates: string[] = sys[keys[0]].curve.dates;
    const at = Object.fromEntries(keys.map((k) => [k, new Map(sys[k].curve.dates.map((d: string, i: number) => [d, sys[k].curve.series[0][i]]))]));
    const atd = Object.fromEntries(keys.map((k) => [k, new Map(sys[k].curve.dates.map((d: string, i: number) => [d, sys[k].curve.series[1][i]]))]));
    return {
      eq: dates.map((d) => ({ d, ...Object.fromEntries(keys.map((k) => [k, at[k].get(d) ?? null])) })),
      dd: dates.map((d) => ({ d, ...Object.fromEntries(keys.map((k) => [k, atd[k].get(d) ?? null])) })),
      lines: keys.slice(0, 8).map((k, i) => ({ key: k, label: sys[k].label.replace(' (recorded)', ''), color: colorOf(i) })),
    };
  }, [r]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="space-y-3">
      <Card title="Did any strategy survive validation?" note={`Pre-declared tests (validation and walk-forward out-of-sample, net of modelled costs): Sharpe > 0, bootstrap 5th percentile > 0, profitable at 1.5× spreads and with implied vols 10% lower, deflated Sharpe ≥ 0.90 for ${r.trials} configurations, PBO < 0.5.`}>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {Object.entries(r.strategies).map(([k, s]: any) => (
            <div key={k} className={cn('p-2 border', s.survival.survived ? 'border-green/50' : 'border-border')}>
              <div className="flex items-center gap-1.5 text-2xs font-semibold">{s.survival.survived ? <CheckCircle2 className="w-3 h-3 text-green" /> : <XCircle className="w-3 h-3 text-red" />}{s.label}</div>
              <div className="text-[10px] text-text-tertiary">{s.data_class} · {s.trials} configs</div>
              <div className="mt-1 space-y-0.5">{s.survival.tests.map((t: any) => (
                <div key={t.test} className="flex justify-between gap-2 text-[10px] font-mono">
                  <span className={t.passed ? 'text-text-secondary' : 'text-red'}>{t.test}</span><span>{t.value == null ? '—' : typeof t.value === 'number' ? num(t.value, 3) : String(t.value)}</span>
                </div>))}
              </div>
            </div>))}
        </div>
      </Card>
      <Card title="Seven systems, identical accounting" note={<>{r.systems.assumptions.accounting}. Capital {r.systems.assumptions.capital.toLocaleString()} USD; {r.systems.assumptions.portfolio.max_positions} positions, {pct(r.systems.assumptions.portfolio.risk_per_trade, 0)} max loss per trade, {pct(r.systems.assumptions.portfolio.max_total_risk, 0)} total. {sys.baseline?.note}</>}>
        <Table cols={[{ k: 'label', label: 'System' }, ...SEG_COLS('dev', 'Development'), ...SEG_COLS('val', 'Validation'),
          { k: 'wf_sharpe', label: 'WF-window Sharpe', right: true, f: sh }, { k: 'trades', label: 'Trades', right: true },
          { k: 'costs', label: 'Costs/yr', right: true, f: (v) => pct(v, 2) }]} rows={rows} />
      </Card>
      <div className="grid lg:grid-cols-2 gap-3">
        <Card title="Growth of $1 (development + validation)"><LineChart rows={chart.eq} x="d" lines={chart.lines} height={240} baseline={1} fmt={(v) => num(v, 2)} /></Card>
        <Card title="Drawdown"><LineChart rows={chart.dd} x="d" lines={chart.lines} height={240} baseline={0} fmt={(v) => pct(v, 1)} /></Card>
      </div>
      <Card title="Limitations"><ul className="list-disc pl-4 text-2xs text-text-secondary space-y-0.5">{r.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul></Card>
    </div>
  );
}

function Strategies({ r }: { r: any }) {
  const keys = Object.keys(r.strategies);
  const [k, setK] = useState(keys[0]);
  const s = r.strategies[k];
  const t = s.trades;
  const b = s.breakdowns;
  const bcols = [{ k: 'group', label: 'Group' }, { k: 'trades', label: 'Trades', right: true }, { k: 'win_rate', label: 'Win', right: true, f: (v: any) => pct(v, 0) },
    { k: 'expectancy_r', label: 'Exp. R', right: true, f: (v: any) => num(v, 3) }, { k: 'r_t_stat', label: 't', right: true, f: (v: any) => num(v, 1) },
    { k: 'pnl', label: 'P&L $', right: true, f: (v: any) => (v == null ? '—' : Math.round(v).toLocaleString()) }];
  const seg = (m: any) => `${spct(m?.cagr)} · Sharpe ${num(m?.sharpe)} · max DD ${pct(m?.max_drawdown)}`;
  return (
    <div className="space-y-3">
      <Pills label="Strategy" value={k} onChange={setK} options={keys.map((x) => [x, r.strategies[x].label]) as any} />
      <div className="grid lg:grid-cols-3 gap-3">
        <Card title="Chosen on development (2016–2021)">
          <div className="text-2xs font-mono space-y-0.5">{Object.entries(s.chosen.params).map(([p, v]) => <div key={p} className="flex justify-between"><span className="text-text-tertiary">{p}</span><span>{v == null ? 'none' : String(v)}</span></div>)}</div>
          <div className="text-[10px] text-text-tertiary">{s.data_class} · observed-IV share {pct(s.observed_iv_share, 0)}</div>
        </Card>
        <Card title="In-sample, validation, walk-forward">
          <div className="text-2xs font-mono space-y-1">
            <div><span className="text-text-tertiary">development </span>{seg(s.segments.development)}</div>
            <div><span className="text-text-tertiary">validation </span>{seg(s.segments.validation)}</div>
            <div><span className="text-text-tertiary">walk-forward 2018–23 </span>{seg(s.walk_forward.metrics)}</div>
            <div><span className="text-text-tertiary">bootstrap Sharpe 90% </span>{num(s.walk_forward.bootstrap?.sharpe_p05)} … {num(s.walk_forward.bootstrap?.sharpe_p95)}</div>
            <div><span className="text-text-tertiary">validation mean R 90% </span>{num(s.trade_bootstrap_validation?.p05, 3)} … {num(s.trade_bootstrap_validation?.p95, 3)}</div>
            <div><span className="text-text-tertiary">PBO </span>{num(s.overfitting.pbo?.pbo, 2)} <span className="text-text-tertiary">· DSR </span>{num(s.overfitting.deflated_sharpe?.dsr, 3)} <span className="text-text-tertiary">({s.overfitting.trials} trials)</span></div>
          </div>
        </Card>
        <Card title="Cost and model-risk stress (2016–2023)">
          <Table dense cols={[{ k: 'k', label: 'Stress' }, { k: 'cagr', label: 'CAGR', right: true, f: pc }, { k: 'excess_cagr', label: 'vs cash', right: true, f: pc }, { k: 'sharpe', label: 'Sharpe', right: true, f: sh }]}
            rows={Object.entries(s.cost_stress).map(([kk, v]: any) => ({ k: kk.replace(/_/g, ' '), ...v }))} />
        </Card>
      </div>
      <Card title="Trading">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 text-2xs font-mono">
          {[['Trades', t.trades], ['Win rate', pct(t.win_rate, 0)], ['Profit factor', num(t.profit_factor)], ['Expectancy', `$${Math.round(t.expectancy ?? 0)}`],
            ['Exp. R', num(t.expectancy_r, 3)], ['Avg win / loss', `$${Math.round(t.avg_win ?? 0)} / $${Math.round(t.avg_loss ?? 0)}`], ['Trades/yr', t.trades_per_year],
            ['Avg hold', `${t.avg_holding_days} d`], ['Turnover', num(t.turnover)], ['Capital use', `${pct(t.capital_utilisation_avg, 0)} avg · ${pct(t.capital_utilisation_peak, 0)} peak`],
            ['Costs / yr', pct(t.costs_pct_capital_per_year, 2)], ['Costs / gross', pct(t.costs_share_of_gross, 0)], ['Assignments', `${t.assignments} (${pct(t.assignment_rate, 1)})`],
            ['Underlyings', t.underlyings], ['Top-5 P&L share', pct(t.top5_pnl_share, 0)]].map(([l, v]) => (
            <div key={l as string} className="p-1.5 border border-border"><div className="text-[10px] text-text-tertiary">{l}</div><div>{v ?? '—'}</div></div>))}
        </div>
        <div className="text-[10px] text-text-tertiary">Costs: {Object.entries(t.costs ?? {}).map(([kk, v]: any) => `${kk.replace('_', ' ')} $${Math.round(v).toLocaleString()}`).join(' · ')}. Greeks (÷ NAV): {Object.entries(s.greeks ?? {}).map(([g, v]: any) => `${g} avg ${num(v.avg, 4)} peak ${num(v.peak_abs, 4)}`).join(' · ')}</div>
      </Card>
      <div className="grid lg:grid-cols-3 gap-3">
        {[['By exit', b.by_exit], ['By days to expiry at entry', b.by_dte], ['By premium ÷ max risk', b.by_premium_to_risk], ['By volatility regime (VIX at entry)', b.by_vol_regime],
          ['By implied-vol class', b.by_iv_class], ['By year of entry', b.by_year]].map(([title, rows]: any) => (
          <Card key={title} title={title}><Table dense cols={bcols} rows={rows ?? []} /></Card>))}
      </div>
      <Card title="Parameter sensitivity (development, others at the chosen values)" note="A flat profile is robust; a single spike is fragile. Missing values were not evaluated by the successive search.">
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Object.entries(s.sensitivity).filter(([, rows]: any) => rows.length).map(([p, rows]: any) => (
            <div key={p}><div className="text-[10px] text-text-tertiary mb-0.5">{p}</div>
              <Table dense cols={[{ k: 'value', label: 'Value', f: (v) => v == null ? 'none' : String(v) }, { k: 'dev_sharpe', label: 'Sharpe', right: true, f: sh },
                { k: 'dev_cagr', label: 'CAGR', right: true, f: pc }, { k: 'expectancy_r', label: 'Exp. R', right: true, f: (v) => num(v, 3) }, { k: 'trades', label: 'Trades', right: true }]} rows={rows} />
            </div>))}
        </div>
      </Card>
    </div>
  );
}

function Regimes({ r }: { r: any }) {
  const g = r.regimes;
  const rows = g.models.map((m: any) => ({ model: m.model, dev_bal: m.classification_dev?.balanced_accuracy, val_bal: m.classification_val?.balanced_accuracy,
    maj: m.classification_val?.majority_accuracy, ...Object.fromEntries(['cagr', 'sharpe', 'max_drawdown'].flatMap((x) => [[`pd_${x}`, m.portfolio_dev?.[x]], [`pv_${x}`, m.portfolio_val?.[x]]])),
    current: g.current?.[m.model] }));
  return (
    <div className="space-y-3">
      <Card title="Regime models, out of sample (refitted each January, 21-session embargo)" note={`Chosen for the regime-switching system by ${g.chosen_by}: ${g.chosen}. Balanced accuracy for 3 classes: 0.33 is chance; "majority" is always predicting the most common class. Fixed combined portfolio: development Sharpe ${num(g.fixed_combined.dev.sharpe)}, validation ${num(g.fixed_combined.val.sharpe)}.`}>
        <Table cols={[{ k: 'model', label: 'Model' }, { k: 'dev_bal', label: 'Bal. acc dev', right: true, f: (v) => num(v, 3) }, { k: 'val_bal', label: 'Bal. acc val', right: true, f: (v) => num(v, 3) },
          { k: 'maj', label: 'Majority (val)', right: true, f: (v) => num(v, 3) }, { k: 'pd_cagr', label: 'Gated dev CAGR', right: true, f: pc }, { k: 'pd_sharpe', label: 'Sharpe', right: true, f: sh },
          { k: 'pv_cagr', label: 'Gated val CAGR', right: true, f: pc }, { k: 'pv_sharpe', label: 'Sharpe', right: true, f: sh }, { k: 'pv_max_drawdown', label: 'Max DD', right: true, f: dd },
          { k: 'current', label: 'Latest call' }]} rows={rows} />
        {g.error && <ErrorNote msg={g.error} />}
      </Card>
      <Card title="Gating (pre-declared, not optimised)">
        <Table dense cols={[{ k: 'regime', label: 'Regime' }, ...['bull_put', 'bull_call', 'bear_put', 'iron_condor'].map((s) => ({ k: s, label: s.replace('_', ' '), right: true, f: (v: any) => `${Math.round(v * 100)}%` }))]}
          rows={Object.entries(g.gates).map(([reg, m]: any) => ({ regime: reg, ...m }))} />
        <div className="text-[10px] text-text-tertiary">Features: {g.features.join(', ')}.</div>
      </Card>
    </div>
  );
}

function PortfolioResearch({ r }: { r: any }) {
  const p = r.portfolio_research;
  const grid = p.rows.filter((x: any) => x.group === 'positions_x_risk');
  return (
    <div className="space-y-3">
      <Card title="Maximum positions × risk per trade (combined portfolio)" note={p.note}>
        <Table cols={[{ k: 'label', label: 'Setting' }, { k: 'dev_s', label: 'Dev Sharpe', right: true, f: sh }, { k: 'dev_c', label: 'Dev CAGR', right: true, f: pc }, { k: 'dev_m', label: 'Dev max DD', right: true, f: dd },
          { k: 'val_s', label: 'Val Sharpe', right: true, f: sh }, { k: 'val_c', label: 'Val CAGR', right: true, f: pc }, { k: 'val_m', label: 'Val max DD', right: true, f: dd },
          { k: 'avg_positions', label: 'Avg positions', right: true }, { k: 'capital_use', label: 'Capital use', right: true, f: (v) => pct(v, 0) }, { k: 'peak_delta', label: 'Peak |Δ|/NAV', right: true, f: (v) => num(v, 2) }]}
          rows={grid.map((x: any) => ({ ...x, dev_s: x.dev.sharpe, dev_c: x.dev.cagr, dev_m: x.dev.max_drawdown, val_s: x.val.sharpe, val_c: x.val.cagr, val_m: x.val.max_drawdown }))} />
        <div className="text-[10px] text-text-tertiary">Best on development: {p.best_on_development}. Reference: {p.reference}.</div>
      </Card>
      <Card title="Risk budgets, concentration, correlation, Greeks, drawdown control, ranking, allocation">
        <Table cols={[{ k: 'group', label: 'Group' }, { k: 'label', label: 'Setting' }, { k: 'dev_s', label: 'Dev Sharpe', right: true, f: sh }, { k: 'dev_m', label: 'Dev max DD', right: true, f: dd },
          { k: 'val_s', label: 'Val Sharpe', right: true, f: sh }, { k: 'val_c', label: 'Val CAGR', right: true, f: pc }, { k: 'val_m', label: 'Val max DD', right: true, f: dd }, { k: 'peak_delta', label: 'Peak |Δ|/NAV', right: true, f: (v) => num(v, 2) }]}
          rows={p.rows.filter((x: any) => x.group !== 'positions_x_risk').map((x: any) => ({ ...x, dev_s: x.dev.sharpe, dev_m: x.dev.max_drawdown, val_s: x.val.sharpe, val_c: x.val.cagr, val_m: x.val.max_drawdown }))} />
      </Card>
    </div>
  );
}

function DataValidity({ r }: { r: any }) {
  const dq = r.data_quality;
  const rep = dq.cboe_replication;
  const cmp = (x: any) => x ? `corr ${num(x.corr, 2)} · model ${spct(x.model_excess_annual)} vs CBOE ${spct(x.cboe_excess_annual)} excess/yr · gap ${spct(x.mean_gap_annual, 2)} · TE ${pct(x.tracking_error_annual, 1)}` : '—';
  const acc = dq.iv_model?.accuracy;
  return (
    <div className="space-y-3">
      {rep && (
        <Card title="The option model against CBOE's observed strategy indices (SPY, observed VIX term structure)" note={rep.note}>
          <div className="text-2xs font-mono space-y-1">
            <div><span className="text-text-tertiary">Calibrated on 2011–2017: </span>VIX→ATM scale {num(rep.atm_scale, 2)} ({spct(rep.atm_scale_vs_default - 1)} vs default) · index put-side smile slope {rep.chosen_put_slope}</div>
            <div><span className="text-text-tertiary">PutWrite (PUT), 2018 → out of sample: </span>{cmp(rep.out_of_sample.put)}</div>
            <div><span className="text-text-tertiary">… before calibration: </span>{cmp(rep.before_calibration_out_of_sample.put)}</div>
            <div><span className="text-text-tertiary">Iron condor (CNDR), 2018 → out of sample: </span>{cmp(rep.out_of_sample.cndr)}</div>
            <div className="text-amber">A positive gap means the model earned more than CBOE's published index: credit strategies here are likely overstated by about that much (hence the implied-vol −10% survival test).</div>
          </div>
        </Card>
      )}
      {acc?.summary && (
        <Card title="Implied-volatility model vs CBOE volatility indices" note={`Fit: ${dq.iv_model.fit?.terms?.join(', ')} on ${dq.iv_model.fit?.n} observations to ${dq.iv_model.fit?.train_end}; residual sd ${num(dq.iv_model.fit?.resid_sd, 3)} (log IV).`}>
          <div className="text-2xs font-mono">{Object.entries(acc.summary).map(([k, v]: any) => <div key={k}><span className="text-text-tertiary">{k.replace('_', ' ')}: </span>MAE {v.mae_vol_pts} vol pts · bias {v.bias_vol_pts} · median corr {v.median_corr} ({v.underlyings} underlyings)</div>)}</div>
          <Table dense cols={[{ k: 'underlying', label: 'Underlying' }, { k: 'segment', label: 'Segment' }, { k: 'days', label: 'Days', right: true }, { k: 'mae_vol_pts', label: 'MAE pts', right: true },
            { k: 'bias_vol_pts', label: 'Bias pts', right: true }, { k: 'corr', label: 'Corr', right: true }, { k: 'mean_observed', label: 'Mean IV', right: true }]} rows={acc.by_underlying} />
        </Card>
      )}
      <div className="grid lg:grid-cols-2 gap-3">
        <Card title="Universe and coverage">
          <div className="text-2xs font-mono space-y-0.5">
            <div>{dq.underlyings} underlyings in this stage; panel {dq.panel.tickers} built {dq.panel.first} → {dq.panel.last} ({dq.panel.sessions} sessions)</div>
            <div>{dq.panel.former_members_with_data} former S&P 500 members with price history; {dq.panel.missing?.length} requested names without free history</div>
            <div className="text-text-tertiary">{dq.panel.survivorship}</div>
            <div>Observed-IV underlyings here: {dq.observed_iv_underlyings.join(', ') || 'none'}</div>
            <div>Candidates (loosest filters): {Object.entries(dq.candidates).map(([k, v]: any) => `${k} ${v.toLocaleString()}`).join(' · ')}</div>
          </div>
        </Card>
        <Card title="Missing data (documented, never fabricated)"><ul className="list-disc pl-4 text-2xs text-text-secondary">{dq.missing_data.map((m: string) => <li key={m}>{m}</li>)}</ul>
          {dq.panel.missing?.length > 0 && <div className="text-[10px] text-text-tertiary font-mono break-words">No free history: {dq.panel.missing.slice(0, 80).join(' ')}{dq.panel.missing.length > 80 ? ' …' : ''}</div>}
        </Card>
        <Card title="Look-ahead check (prefix invariance)">
          <div className="text-2xs">{r.leakage ? (r.leakage.passed ? <span className="text-green">Passed — features recomputed on data cut at {r.leakage.cut} are identical.</span> : <span className="text-red">Failed: {JSON.stringify(r.leakage.differing_values)}</span>) : 'not run'}</div>
        </Card>
        <Card title="Survivorship (point-in-time members vs today's US list)">
          {r.survivorship ? <Table dense cols={[{ k: 's', label: 'Strategy' }, { k: 'a', label: 'PIT Sharpe', right: true, f: sh }, { k: 'b', label: "Today's list Sharpe", right: true, f: sh }, { k: 'bias', label: 'Bias', right: true, f: (v) => num(v, 2) }]}
            rows={Object.entries(r.survivorship).map(([k, v]: any) => ({ s: k, a: v.point_in_time.sharpe, b: v.todays_list.sharpe, bias: v.sharpe_bias }))} /> : <div className="text-2xs text-text-tertiary">Stage 3 and 4 only.</div>}
        </Card>
      </div>
      <Card title="Runtime and memory by section">
        <Table dense cols={[{ k: 'k', label: 'Section' }, { k: 'seconds', label: 'Seconds', right: true }, { k: 'peak_rss_mb', label: 'Peak MB', right: true }]}
          rows={Object.entries(r.timings).map(([k, v]: any) => ({ k, ...v }))} />
      </Card>
    </div>
  );
}

function Holdout({ eid, reload, canRun }: { eid: string; reload: () => void; canRun: boolean }) {
  const [txt, setTxt] = useState('');
  const [h, setH] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const go = () => api(`${BASE}/experiments/${eid}/holdout`, { method: 'POST', json: { confirm: txt } }).then((x) => { setH(x); reload(); }).catch((e) => setErr(e.message));
  return (
    <Card title="Protected holdout (2024 → latest data)" note="The holdout is computed once, with the development choices, and sealed. Looking is logged; any change made after looking is no longer an out-of-sample test.">
      {!h ? (
        <div className="flex flex-wrap items-center gap-2 text-2xs">
          <Lock className="w-3.5 h-3.5 text-amber" />
          <span>Sealed.</span>
          {canRun && <><input value={txt} onChange={(e) => setTxt(e.target.value)} placeholder='type "REVEAL HOLDOUT"' className="bg-surface-2 border border-border px-2 py-1 font-mono text-2xs w-48" />
            <button onClick={go} disabled={txt !== 'REVEAL HOLDOUT'} className="px-2 py-1 border border-amber/50 text-amber disabled:opacity-40">Reveal and log</button></>}
          <ErrorNote msg={err} />
        </div>
      ) : (
        <div className="space-y-2">
          <div className="text-2xs text-amber flex gap-1.5"><ShieldAlert className="w-3.5 h-3.5" />{h.warning} (reveals so far: {h.reveals_total})</div>
          <Table cols={[{ k: 'k', label: 'System' }, { k: 'cagr', label: 'CAGR', right: true, f: pc }, { k: 'sharpe', label: 'Sharpe', right: true, f: sh }, { k: 'max_drawdown', label: 'Max DD', right: true, f: dd }, { k: 'years', label: 'Years', right: true }]}
            rows={Object.entries(h.results).map(([k, v]: any) => ({ k, ...v }))} />
        </div>
      )}
    </Card>
  );
}

// ── registry, configurations, performance ────────────────────────────────────
function Registry({ ov }: { ov: any }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Card title="Research registry" note="Seeded from the earlier research notes; status changes only from experiment results (stage 4 is required for 'survived').">
      <div className="space-y-1">{ov.hypotheses.map((h: any) => (
        <div key={h.id} className="border border-border">
          <button onClick={() => setOpen(open === h.id ? null : h.id)} className="w-full flex items-center gap-2 px-2 py-1 text-left text-2xs hover:bg-surface-2/50">
            <span className="font-mono text-text-tertiary w-8">{h.id}</span><Badge s={h.status} /><span className="font-semibold">{h.title}</span>
            <span className="ml-auto text-[10px] text-text-tertiary">{(h.experiments ?? []).length} experiments</span>
          </button>
          {open === h.id && (
            <div className="px-3 pb-2 text-2xs space-y-1 text-text-secondary">
              <div><span className="text-text-tertiary">Hypothesis: </span>{h.hypothesis}</div>
              <div><span className="text-text-tertiary">Evidence / source: </span>{h.evidence}</div>
              {h.method && <div><span className="text-text-tertiary">Method: </span>{h.method}</div>}
              {h.dataset && <div><span className="text-text-tertiary">Data: </span>{h.dataset}</div>}
              {h.config && <div className="font-mono text-[10px] break-words"><span className="text-text-tertiary">Configuration: </span>{JSON.stringify(h.config)}</div>}
              {h.results && <pre className="font-mono text-[10px] whitespace-pre-wrap break-words max-h-60 overflow-auto bg-surface-2 p-1.5">{JSON.stringify(h.results, null, 1)}</pre>}
              {h.limitations && <div><span className="text-text-tertiary">Limitations: </span>{h.limitations}</div>}
              <div className="text-[10px] text-text-tertiary">Experiments: {(h.experiments ?? []).join(', ') || 'none yet'}</div>
            </div>)}
        </div>))}
      </div>
    </Card>
  );
}

function Configs({ ov, res, eid, isAdmin, canRun, reload }: any) {
  const c = ov.configs;
  const r = res?.result;
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, { confirm: string; ack: boolean; reason: string }>>({});
  const exportIt = (strategy: string) => api(`${BASE}/configs/export`, { method: 'POST', json: { experiment_id: eid, strategy } })
    .then((x) => { setMsg(`Exported ${x.file}`); reload(); }).catch((e) => setErr(e.message));
  const approve = (file: string) => {
    const f = form[file] ?? { confirm: '', ack: false, reason: '' };
    api(`${BASE}/configs/approve`, { method: 'POST', json: { file, confirm: f.confirm, acknowledge: f.ack, reason: f.reason } })
      .then((x) => { setMsg(`Approved ${x.approved}${x.warnings.length ? ` (with warnings: ${x.warnings.join('; ')})` : ''}`); reload(); }).catch((e) => setErr(e.message));
  };
  const rollback = (strategy: string) => api(`${BASE}/configs/rollback`, { method: 'POST', json: { strategy, reason: 'rollback from dashboard' } })
    .then((x) => { setMsg(`${strategy}: now ${x.active ?? 'no active configuration'}`); reload(); }).catch((e) => setErr(e.message));
  const set = (file: string, patch: any) => setForm((s) => ({ ...s, [file]: { ...{ confirm: '', ack: false, reason: '' }, ...s[file], ...patch } }));
  return (
    <div className="space-y-3">
      {msg && <div className="text-2xs text-green">{msg}</div>}
      <ErrorNote msg={err} />
      <Card title="Export a candidate from the selected experiment" note="Exporting writes a versioned candidate file (config/quant_algo/candidates). It does not change production.">
        {!r || r.stage === 1 ? <div className="text-2xs text-text-tertiary">Select a stage 2–4 experiment under Experiments & results.</div> : (
          <div className="flex flex-wrap gap-2">{Object.entries(r.strategies).map(([k, s]: any) => (
            <button key={k} disabled={!canRun} onClick={() => exportIt(k)} className="px-2 py-1 text-2xs border border-border hover:border-bloomberg disabled:opacity-40">
              {s.label} <span className={s.survival.survived ? 'text-green' : 'text-red'}>({s.survival.survived ? 'survived' : 'failed validation'})</span> · stage {r.stage}
            </button>))}
          </div>)}
      </Card>
      <Card title="Candidates" note={'Approval: administrators only, by typing "APPROVE <strategy>-v<N>". A configuration that failed validation or lacks a stage 4 test also needs an explicit acknowledgement and a reason — both recorded.'}>
        {c.candidates.length === 0 ? <div className="text-2xs text-text-tertiary">None.</div> : c.candidates.map((x: any) => {
          const approved = c.approved.some((a: any) => a.file === x.file);
          const f = form[x.file] ?? { confirm: '', ack: false, reason: '' };
          return (
            <div key={x.file} className="border border-border p-2 space-y-1 text-2xs">
              <div className="flex flex-wrap items-center gap-2"><span className="font-mono">{x.file}</span><span className="text-text-tertiary">stage {x.stage} · {x.data_class} · {x.created}</span>
                <span className={x.survived ? 'text-green' : 'text-red'}>{x.survived ? 'survived validation' : 'did not survive validation'}</span>{x.stage < 4 && <span className="text-amber">not validated on the full universe</span>}
                {approved && <span className="text-green">approved</span>}</div>
              <div className="font-mono text-[10px] text-text-tertiary break-words">{JSON.stringify(x.params)}</div>
              {isAdmin && !approved && (
                <div className="flex flex-wrap items-center gap-2">
                  <input value={f.confirm} onChange={(e) => set(x.file, { confirm: e.target.value })} placeholder={`APPROVE ${x.strategy_id}-v${x.version}`} className="bg-surface-2 border border-border px-2 py-0.5 font-mono text-2xs w-56" />
                  {(!x.survived || x.stage < 4) && <><label className="flex items-center gap-1"><input type="checkbox" checked={f.ack} onChange={(e) => set(x.file, { ack: e.target.checked })} />I accept the warnings</label>
                    <input value={f.reason} onChange={(e) => set(x.file, { reason: e.target.value })} placeholder="reason" className="bg-surface-2 border border-border px-2 py-0.5 text-2xs w-48" /></>}
                  <button onClick={() => approve(x.file)} className="px-2 py-0.5 border border-green/50 text-green">Approve for production</button>
                </div>)}
            </div>);
        })}
      </Card>
      <Card title="Production (what the Quant Algorithm reads: GET /api/v1/quant/options-research/configs/production)">
        {Object.keys(c.production.active).length === 0 ? <div className="text-2xs text-text-tertiary">No approved configuration is active.</div> : (
          <Table dense cols={[{ k: 's', label: 'Strategy' }, { k: 'f', label: 'Active version' }, { k: 'x', label: '', f: (_, row) => isAdmin ? <button onClick={() => rollback(row.s)} className="inline-flex items-center gap-1 text-amber"><RotateCcw className="w-3 h-3" />Roll back</button> : null }]}
            rows={Object.entries(c.production.active).map(([s, f]) => ({ s, f }))} />)}
        {c.production.history.length > 0 && <Table dense cols={[{ k: 'at', label: 'When' }, { k: 'by', label: 'By' }, { k: 'action', label: 'Action' }, { k: 'strategy', label: 'Strategy' }, { k: 'from', label: 'From' }, { k: 'to', label: 'To' }, { k: 'reason', label: 'Reason' }]}
          rows={[...c.production.history].reverse().slice(0, 20)} />}
      </Card>
    </div>
  );
}

function Performance({ ov }: { ov: any }) {
  const p = ov.profiles as Record<string, any>;
  const names = Object.keys(p);
  const stages = Array.from(new Set(names.flatMap((n) => Object.keys(p[n].stages))));
  const ab = ov.ab;
  const avg = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  return (
    <div className="space-y-3">
    {ab && (
      <Card title="Like-for-like measurements (A/B)" note={ab.measured}>
        <Table cols={[{ k: 'what', label: 'What' }, { k: 'b', label: 'Before (s)', right: true }, { k: 'a', label: 'After (s)', right: true },
          { k: 'x', label: 'Speed-up', right: true }, { k: 'check', label: 'Equivalence check' }]}
          rows={ab.rows.map((r: any) => ({ ...r, b: r.before_s.join(' / '), a: r.after_s.join(' / '), x: `${(avg(r.before_s) / avg(r.after_s)).toFixed(2)}×` }))} />
        <div className="text-[10px] text-text-tertiary">{ab.rows.map((r: any) => r.how).join(' · ')}. {ab.profiles_note}</div>
      </Card>)}
    <Card title="The 10-year, ~3,100-stock global Code Lab backtest — measured before and after optimisation" note="Same strategy file, same data, same machine; profiled stage by stage (scripts/profile_global_backtest.py). Only measured runs are shown.">
      {names.length === 0 ? <div className="text-2xs text-text-tertiary">No profiles yet.</div> : (
        <Table cols={[{ k: 'stage', label: 'Stage' }, ...names.flatMap((n) => [{ k: `${n}_s`, label: `${n} seconds`, right: true }, { k: `${n}_m`, label: `${n} peak MB`, right: true }])]}
          rows={[...stages.map((s) => ({ stage: s, ...Object.fromEntries(names.flatMap((n) => [[`${n}_s`, p[n].stages[s]?.seconds ?? '—'], [`${n}_m`, p[n].stages[s]?.peak_rss_mb ?? '—']])) })),
            { stage: 'total', ...Object.fromEntries(names.map((n) => [`${n}_s`, p[n].total_seconds])) }]} />)}
    </Card>
    </div>
  );
}

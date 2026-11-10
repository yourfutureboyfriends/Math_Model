/**
 * ML — the machine-learning workbench (top-bar mode 'ml'). Built like an ML platform on proven libraries:
 * Apache ECharts (zoomable, linked charts with export), TanStack Table (sortable, filterable grids), TanStack Query
 * (cached, polling data), Radix UI (accessible controls) and react-resizable-panels (split panes).
 *
 * Tabs: Overview · Model lab · Network visualizer · Explainability · Monitoring · Registry · Knowledge · Method.
 * Colour: the validated categorical palette, at most four highlighted models (fixed colour per selection slot),
 * everything else muted; "yes" periods are a neutral band.
 */
import { useEffect, useMemo, useState } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { Panel as RPanel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { Download, Pause, Play, RefreshCw } from 'lucide-react';
import { pct } from '@/lib/format';
import { EChart, axisStyle, chartTheme } from '@/components/ml/ui/EChart';
import { DataGrid } from '@/components/ml/ui/DataGrid';
import { Hint, Panel, RangeSlider, Segmented, Stat } from '@/components/ml/ui/Controls';
import { DriftBullet } from '@/components/ml/DriftBullet';
import { StreamBadge } from '@/components/ml/StreamBadge';
import { useAuth } from '@/context/AuthContext';
import { useNeuralStream } from '@/hooks/useNeuralStream';
import { AutonomousStatus } from '@/components/ml/AutonomousStatus';
import { OnlineDataStatus } from '@/components/ml/OnlineDataStatus';
import { ResearchNetwork } from '@/components/ml/ResearchNetwork';
import { LiveModularFlow } from '@/components/ml/LiveModularFlow';
import { ModularNetwork } from '@/components/ml/ModularNetwork';
import { NeuralFlow } from '@/components/ml/NeuralFlow';
import { mlQueryClient, send, useFeaturesQ, useHistoryQ, useInputsQ, useVisualizerQ, useKnowledgeQ, useRegistryQ, useTaskQ, useTasksQ } from '@/components/ml/api';
import { KNOWN_TASKS, ML_TABS, ensemble, forward, validWeights, setMlTab, setMlTask, skillText, useMlTab, useMlTask, type Weights } from '@/components/ml/mlShared';

const MODEL_ORDER = ['champion', 'network', 'factor_logit', 'factor_network', 'forest', 'boosting', 'regime_switch', 'deep_sequence', 'sections', 'autonomous_tft', 'average'];
const SHORT: Record<string, string> = { champion: 'Logistic', network: 'Neural net', factor_logit: 'Factor', factor_network: 'Factor NN', forest: 'Forest',
  boosting: 'Boosting', regime_switch: 'Regime', deep_sequence: 'Deep GRU', sections: 'Sections', autonomous_tft: 'Autonomous TFT', average: 'Average' };
/** A model's short label; unknown keys are shown as sent rather than as a blank. */
const short = (m: string | undefined | null) => (m ? SHORT[m] ?? m : '—');
const PICK_KEY = 'ml_compare';
const span = (n: number) => ({ gridColumn: `span ${n} / span ${n}` });
const toneOf = (v: number | null | undefined) => (v == null ? '' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : '');

function usePicked() {
  const [p, setP] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(PICK_KEY) ?? 'null') ?? ['champion', 'network', 'boosting', 'deep_sequence']; } catch { return ['champion', 'network', 'boosting', 'deep_sequence']; } });
  useEffect(() => { try { localStorage.setItem(PICK_KEY, JSON.stringify(p)); } catch { /* storage unavailable */ } }, [p]);
  const toggle = (m: string) => setP((x) => (x.includes(m) ? x.filter((k) => k !== m) : [...x, m].slice(-4)));
  return { picked: p.slice(0, 4), toggle };
}
const colourFor = (picked: string[], m: string) => { const i = picked.indexOf(m); return i >= 0 ? chartTheme().series[i] : chartTheme().muted; };

function Skeleton({ h = 280 }: { h?: number }) { return <div className="ml-skeleton" style={{ height: h }} />; }
function Training({ d, onRetry }: { d: any; onRetry?: () => void }) {
  if (d?.training) return (
    <div className="ml-panel"><div className="ml-panel-body flex items-center gap-3 text-xs text-text-secondary" role="status">
      <span className="w-2 h-2 rounded-full bg-bloomberg animate-pulse" />{d.inspection_only?'Preparing the interactive shallow network':'Training models and building their walk-forward records'} — {d.elapsed_s ?? 0}s. This page updates by itself.
    </div></div>);
  return <div className="ml-panel"><div className="ml-panel-body text-xs text-amber">Unavailable — {d?.reason ?? 'error'} {onRetry && <button className="ml-btn ml-2" onClick={onRetry}>Retry</button>}</div></div>;
}

// ── Toolbar ───────────────────────────────────────────────────────────────────
function Toolbar({ tasks, period, setPeriod, picked, toggle, models, onExport, stream }: {
  tasks: any[] | undefined; period: string; setPeriod: (p: any) => void; picked: string[]; toggle: (m: string) => void; models: string[]; onExport?: () => void; stream: ReturnType<typeof useNeuralStream>;
}) {
  const sel = useMlTask();
  const tab = useMlTab();
  const t = ML_TABS.find((x) => x.id === tab) ?? ML_TABS[0];
  const [busy, setBusy] = useState(false);
  const notReady = (tasks ?? []).filter((x) => !x.ready);
  const perTask = !['overview', 'registry', 'knowledge', 'method'].includes(tab);
  return (
    <div className="ml-toolbar">
      <div className="ml-toolbar-title"><h1>Machine learning</h1><span>{t.desc}</span></div>
      <div className="ml-auto flex flex-wrap items-center gap-2 ml-auto" style={{ marginLeft: 'auto' }}>
        {perTask && <select value={sel} onChange={(e) => setMlTask(e.target.value)} aria-label="Forecast task" className="ml-btn pr-6">
          {(tasks?.length ? tasks : KNOWN_TASKS).map((x: any) => <option key={x.task} value={x.task}>{x.title}{x.ready === false ? ' (training)' : ''}</option>)}</select>}
        {tab === 'lab' && <Segmented label="Period" value={period} onChange={setPeriod} options={[{ value: 'all', label: 'All' }, { value: '2000', label: '2000–' }, { value: '2013', label: '2013–' }]} />}
        {notReady.length > 0 && <button className="ml-btn" data-variant="primary" disabled={busy} onClick={async () => { setBusy(true); await Promise.all(notReady.map((x) => fetch(`/api/v1/ml/tasks/${x.task}`).catch(() => null))); setBusy(false); mlQueryClient.invalidateQueries({ queryKey: ['ml'] }); }}>
          <Play className="w-3 h-3" />{busy ? 'Starting…' : `Train ${notReady.length}`}</button>}
        {onExport && <button className="ml-btn" onClick={onExport}><Download className="w-3 h-3" />Export CSV</button>}
        <StreamBadge {...stream} />
        <button className="ml-btn" onClick={() => mlQueryClient.invalidateQueries({ queryKey: ['ml'] })} aria-label="Refresh"><RefreshCw className="w-3 h-3" /></button>
      </div>
      {tab === 'lab' && models.length > 0 && <div className="w-full flex flex-wrap items-center gap-1.5">
        <span className="text-2xs text-text-tertiary mr-1">Compare (up to 4)</span>
        {models.map((m) => <button key={m} className="ml-model-chip" aria-pressed={picked.includes(m)} onClick={() => toggle(m)}>
          <span className="ml-dot" style={{ background: picked.includes(m) ? colourFor(picked, m) : 'var(--border)' }} />{SHORT[m]}</button>)}
      </div>}
    </div>
  );
}

// ── Overview ──────────────────────────────────────────────────────────────────
function Overview({ tasks }: { tasks: any[] | undefined }) {
  const reg = useRegistryQ();
  const [deepBusy,setDeepBusy]=useState(false),[deepMessage,setDeepMessage]=useState('');
  const deep=reg.data?.deep_sequence_training;
  const ready = (tasks ?? []).filter((t) => t.ready);
  const models = MODEL_ORDER.filter((m) => ready.some((t) => t.models?.[m]));
  const rows = (tasks?.length ? tasks : KNOWN_TASKS) as any[];
  const warnings = ready.reduce((s, t) => s + (t.flags?.length ?? 0), 0);
  const heat = useMemo(() => {
    const t = chartTheme();
    const data: any[] = [];
    rows.forEach((r, yi) => models.forEach((m, xi) => { const v = r.models?.[m]?.probability; if (v != null) data.push([xi, yi, Math.round(v * 1000) / 10, r.models[m].skill]); }));
    return {
      tooltip: { formatter: (p: any) => { const r = rows[p.value[1]]; return `${r.title}${r.question ? `<br/>${r.question}` : ''}<br/>${SHORT[models[p.value[0]]]}: <b>${p.value[2].toFixed(1)}%</b><br/>walk-forward skill ${skillText(p.value[3])}`; } },
      grid: { left: 210, right: 70, top: 10, bottom: 56 },
      xAxis: { type: 'category', data: models.map((m) => SHORT[m]), ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, interval: 0, rotate: 30 }, splitArea: { show: false } },
      yAxis: { type: 'category', data: rows.map((r) => r.title), inverse: true, ...axisStyle(t) },
      visualMap: { min: 0, max: 100, calculable: false, orient: 'vertical', right: 0, top: 'center', itemHeight: 140, text: ['100%', '0%'], textStyle: { color: t.mutedText, fontSize: 10 },
        inRange: { color: ['rgba(57,135,229,0.12)', t.series[0]] } },
      toolbox: { show: false }, legend: { show: false },
      series: [{ type: 'heatmap', data, label: { show: true, color: t.textStrong, fontSize: 10, formatter: (p: any) => `${p.value[2].toFixed(0)}%` },
        itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 4 }, emphasis: { itemStyle: { borderColor: t.textStrong, borderWidth: 1 } } }],
    };
  }, [rows, models]);
  const cols: ColumnDef<any, any>[] = [
    { header: 'Question', accessorKey: 'title', cell: (c) => (
      // The engine serves the exact event each task is trained on; the short title alone is
      // ambiguous for recession_12m, where "within 12 months" does not say whether the question is
      // month t+12 or any month in the window. A native title matches the Skill column beside it and
      // costs one attribute rather than a tooltip provider per row. Nothing is supplied from the
      // frontend when the server has not answered — an invented definition is worse than none.
      <span className="text-text-primary" title={[c.row.original.question, ...(c.row.original.notes ?? [])].filter(Boolean).join(' ') || undefined}>{c.getValue()}</span>) },
    { header: 'Signal', accessorFn: (r) => r.signal?.probability, meta: { numeric: true }, cell: (c) => <b>{c.getValue() == null ? '—' : pct(c.getValue())}</b> },
    { header: 'Model', accessorFn: (r) => r.signal?.model, cell: (c) => c.getValue() ? (c.getValue() === 'autonomous_tft'
      ? <Hint text="Promoted by automated evidence gates without a PM or risk approval"><span className="ml-pill" data-tone="warn">{short(c.getValue())} · no sign-off</span></Hint>
      : <span className="ml-pill" data-tone="prod">{short(c.getValue())}</span>) : <span className="text-text-tertiary">training…</span> },
    { header: 'Skill', accessorFn: (r) => r.signal?.skill_vs_base_rate, meta: { numeric: true, title: 'Out-of-sample Brier skill vs the base rate' }, cell: (c) => <span className={toneOf(c.getValue())}>{skillText(c.getValue())}</span> },
    { header: 'Best record', accessorFn: (r) => r.best_by_record, cell: (c) => c.getValue() ? `${short(c.getValue())} (${skillText(c.row.original.models?.[c.getValue()]?.skill)})` : '—' },
    { header: 'Network range', accessorFn: (r) => r.network_probability, meta: { numeric: true }, cell: (c) => c.getValue() == null ? '—' : `${pct(c.getValue())} (${pct(c.row.original.network_range[0])}–${pct(c.row.original.network_range[1])})` },
    { header: 'Data', accessorFn: (r) => r.flags?.length ?? 0, cell: (c) => c.row.original.ready ? (c.getValue() ? <span className="ml-pill" data-tone="warn">⚠ {c.getValue()}</span> : <span className="ml-pill" data-tone="ok">✓ OK</span>) : '—' },
    { header: 'Used for', accessorKey: 'used_for', cell: (c) => <span className="text-text-tertiary">{c.getValue()}</span> },
  ];
  return (
    <div className="space-y-2.5">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5">
        <Stat label="Tasks live" value={`${ready.length}/${rows.length}`} delta={ready.length < rows.length ? 'training or queued' : 'all trained this month'} />
        <Stat label="Models per task" value={models.length || '—'} delta={models.length ? 'simple → deep, walk-forward' : 'none trained yet'} />
        <Stat label="Signals with skill" value={`${ready.filter((t) => t.signal?.useful).length}/${ready.length}`} tone="good" delta="beat the base rate out of sample" />
        <Stat label="Promotions" value={reg.data?.promotions ? reg.data.promotions.filter((p:any)=>p.active!==false).length : '—'} delta="challengers serving" />
        <Stat label="Forecasts logged" value={reg.data ? new Set(reg.data.recent_forecasts.map((r: any) => `${r.task}${r.month}`)).size : '—'} delta="task-months, never rewritten" />
        <Stat label="Data warnings" value={warnings} tone={warnings ? 'warn' : 'good'} delta="inputs out of range or shifted" />
      </div>
      {deep&&<Panel title="Neural capacity & continual refinement" sub="Research profiles are versioned challengers. Training updates do not promote a model.">
       <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-2"><Stat label="Configured profile" value={deep.configured.profile} delta={`${deep.configured.hidden} units × ${deep.configured.layers} GRU layers`}/><Stat label="Temporal attention" value={deep.configured.attention_heads} delta="heads over past observations"/><Stat label="Ensemble" value={deep.configured.seeds} delta={`up to ${deep.configured.epochs} epochs / seed`}/><Stat label="Training state" value={deep.training?'Rebuilding':'Ready / idle'} delta={`Version ${deep.fingerprint}`}/></div>
       <p className="text-xs text-text-secondary mt-3">{deep.learning}</p><p className="text-xs text-text-tertiary mt-2">{deep.validation}</p><p className="text-xs text-text-tertiary mt-2">{deep.promotion}</p>
       {deep.stages&&<div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-2 mt-4" aria-label="Neural processing pipeline">{deep.stages.map((stage:any,i:number)=><div key={stage.name} className="border border-border rounded-lg p-3"><p className="text-xs font-medium">{i+1}. {stage.name}</p><p className="text-[11px] text-text-secondary mt-1">{stage.detail}</p></div>)}</div>}
       {deep.continual&&<div className="mt-3 text-xs space-y-2"><p>Automatic learning: {deep.continual.enabled?'On':'Off'} · {deep.continual.action??'Awaiting first check'} · Architecture: {deep.configured.architecture}</p><p className="text-text-tertiary">{deep.continual.schedule} Research refits are normally weekly; newly matured outcomes can permit a daily update. All incoming data must pass quality checks.</p><p className="text-text-tertiary">{deep.continual.policy}</p>{deep.continual.observation&&<p>Latest learning inputs: {deep.continual.observation.as_of} · {deep.continual.observation.months} months · {deep.continual.observation.tasks?.length} tasks. {deep.continual.observation.limitation}</p>}{deep.continual.error&&<p role="alert">{deep.continual.error}</p>}</div>}
       {deep.routing?.length>0&&<div className="mt-3"><p className="text-xs font-medium">Latest specialist routing</p><div className="grid sm:grid-cols-3 gap-2 mt-2">{Object.keys(deep.routing[0]).map((name:string)=>{const weight=deep.routing.reduce((sum:number,row:any)=>sum+(row[name]??0),0)/deep.routing.length;return <div key={name} className="text-xs border border-border rounded p-2"><span>{name.replace(/_/g,' ')}</span><span className="float-right font-mono">{(weight*100).toFixed(1)}%</span><div className="h-1 bg-border rounded mt-2"><div className="h-1 bg-amber rounded" style={{width:`${Math.max(0,Math.min(100,weight*100))}%`}}/></div></div>;})}</div><p className="text-[10px] text-text-tertiary mt-2">Learned internal routing weights averaged across seeds; these are not causal importance or portfolio allocations.</p></div>}
       <details className="mt-3 text-xs"><summary>Available capacity profiles</summary><div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr><th>Profile</th><th>Hidden units</th><th>Layers</th><th>Attention</th></tr></thead><tbody>{Object.entries(deep.profiles).map(([name,c]:[string,any])=><tr key={name}><td>{name}</td><td>{c.hidden}</td><td>{c.layers}</td><td>{c.attention_heads}</td></tr>)}</tbody></table></div><p className="text-text-tertiary mt-2">{deep.limits} The server’s configuration selects the profile; no profile is certified more accurate before testing.</p></details>
       <button className="ml-btn mt-3" disabled={deepBusy||deep.training} onClick={async()=>{setDeepBusy(true);setDeepMessage('');try{await send('/api/v1/ml/deep/retrain','POST');setDeepMessage('Research rebuild queued. Existing promotion gates remain in force.');reg.refetch();}catch(e){setDeepMessage(e instanceof Error?e.message:'Could not queue training.');}finally{setDeepBusy(false);}}}>Rebuild research record</button><button className="ml-btn mt-3 ml-2" disabled={deepBusy} title="Check for changed validated inputs or newly matured answers and run a research refit if due (PM or quant)"
         onClick={async()=>{setDeepBusy(true);setDeepMessage('');try{const r:any=await send('/api/v1/ml/deep/learn','POST');setDeepMessage(r?.action?`Learning cycle: ${r.action}.`:'Learning cycle checked. Promotion gates are unchanged.');reg.refetch();}catch(e){setDeepMessage(e instanceof Error?e.message:'Could not run the learning cycle.');}finally{setDeepBusy(false);}}}>Run learning cycle</button>{deepMessage&&<p role="status" className="text-xs mt-2">{deepMessage}</p>}{deep.error&&<p role="alert" className="text-xs text-red mt-2">{deep.error}</p>}
      </Panel>}
      <AutonomousStatus/>
      <OnlineDataStatus/>
      <div className="ml-grid-12">
        <div style={span(7)} className="ml-span-7"><Panel title="Probability — every task × every model" sub="Shade = today's probability. Hover for the model's walk-forward skill; click a cell to open the model lab.">
          {ready.length ? <EChart option={heat} height={300} ariaLabel="Heatmap of probabilities by task and model"
            onReady={(c) => c.on('click', (p: any) => { setMlTask(rows[p.value[1]].task); setMlTab('lab'); })} /> : <Skeleton h={300} />}
        </Panel></div>
        <div style={span(5)} className="ml-span-5"><Panel title="Skill vs the base rate — served model per task" sub="Out-of-sample Brier skill; right of zero beats always guessing the average. A task with no bar has no walk-forward skill recorded yet — that is not skill of zero.">
          {ready.length ? <EChart height={300} ariaLabel="Skill by task" option={(() => { const t = chartTheme();
            // An unrecorded skill plots as no bar. Defaulting it to 0 drew a bar exactly on the
            // zero line, which reads as the specific claim "no better than the base rate".
            const d = ready.map((r) => ({ name: r.title, v: r.signal.skill_vs_base_rate ?? null }));
            return { grid: { left: 210, right: 20, top: 10, bottom: 30 }, tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => skillText(v) }, toolbox: { show: false }, legend: { show: false },
              xAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
              yAxis: { type: 'category', data: d.map((x) => x.name), inverse: true, ...axisStyle(t) },
              series: [{ type: 'bar', data: d.map((x) => ({ value: x.v, itemStyle: { color: x.v === null ? t.muted : x.v >= 0 ? t.series[0] : t.red, borderRadius: x.v !== null && x.v < 0 ? [4, 0, 0, 4] : [0, 4, 4, 0] } })), barMaxWidth: 16,
                markLine: { symbol: 'none', data: [{ xAxis: 0 }], lineStyle: { color: t.mutedText }, label: { show: false } } }] }; })()} /> : <Skeleton h={300} />}
        </Panel></div>
      </div>
      <Panel title="Signals served" sub="What the desk, the playbook and the research assistant read — the champion until a challenger is promoted.">
        <DataGrid data={rows} columns={cols} onRowClick={(r) => { setMlTask(r.task); setMlTab('lab'); }} filterPlaceholder="Filter tasks…" />
      </Panel>
    </div>
  );
}

// ── Model lab ─────────────────────────────────────────────────────────────────
function ModelLab({ period, picked }: { period: string; picked: string[] }) {
  const sel = useMlTask();
  const q = useTaskQ(sel);
  const d = q.data;
  const ready = !!d?.available;
  const hq = useHistoryQ(sel, ready);
  const models: string[] = ready ? MODEL_ORDER.filter((m) => d.models?.[m]) : [];
  const sel4 = picked.filter((m) => models.includes(m));
  const eras = ready ? Object.keys(d.backtest?.by_era ?? {}) : [];
  const recentEra = eras[eras.length - 1];
  const H = useMemo(() => {
    const h = hq.data; if (!h) return null;
    const cut = period === 'all' ? '' : `${period}-01`;
    const keep = h.months.map((m: string, i: number) => [m, i] as const).filter(([m]: any) => m >= cut).map(([, i]: any) => i);
    return { months: keep.map((i: number) => h.months[i]), outcome: keep.map((i: number) => h.outcome[i]),
      models: Object.fromEntries(Object.entries(h.models).map(([k, v]: any) => [k, keep.map((i: number) => v[i])])) as Record<string, number[]> };
  }, [hq.data, period]);
  if (!ready) return q.isLoading ? <Skeleton /> : <Training d={d ?? { reason: (q.error as Error)?.message }} onRetry={() => q.refetch()} />;
  const t = chartTheme();
  const bands = H ? (() => { const out: any[] = []; let s: number | null = null; H.outcome.forEach((y: number, i: number) => { if (y === 1 && s === null) s = i; if ((y !== 1 || i === H.outcome.length - 1) && s !== null) { out.push([{ xAxis: H.months[s] }, { xAxis: H.months[y === 1 ? i : i - 1] }]); s = null; } }); return out; })() : [];
  // the four compared models in colour (legend + emphasis); the rest thin and muted behind; yes-months as a band
  const lines = H ? [
    ...models.filter((m) => H.models[m] && !sel4.includes(m)).map((m) => ({ name: d.models[m].name, type: 'line', data: H.models[m], showSymbol: false, z: 1, silent: true,
      lineStyle: { width: 1, color: t.muted }, itemStyle: { color: t.muted }, tooltip: { show: false } })),
    ...sel4.filter((m) => H.models[m]).map((m) => ({ name: d.models[m].name, type: 'line', data: H.models[m], showSymbol: false, z: 3,
      lineStyle: { width: 2, color: colourFor(sel4, m) }, itemStyle: { color: colourFor(sel4, m) }, emphasis: { focus: 'series' } })),
    { name: 'answer was yes', type: 'line', data: [], markArea: { silent: true, itemStyle: { color: t.outcome }, data: bands } },
  ] : [];
  const timeline = H && {
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`) },
    legend: { top: 4, left: 0, right: 150, type: 'scroll', data: sel4.filter((m) => H.models[m]).map((m) => d.models[m].name) },
    grid: { left: 48, right: 16, top: 40, bottom: 64 },
    xAxis: { type: 'category', data: H.months, boundaryGap: false, ...axisStyle(t) },
    yAxis: { type: 'value', min: 0, max: 1, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
    dataZoom: [{ type: 'inside', zoomOnMouseWheel: 'shift', moveOnMouseWheel: false }, { type: 'slider', height: 18, bottom: 10, borderColor: t.border, textStyle: { color: t.mutedText }, fillerColor: 'rgba(120,120,120,.15)' }],
    series: lines,
  };
  const rocOf = (p: number[], y: number[]) => { const ix = p.map((_, i) => i).sort((a, b) => p[b] - p[a]); const P = y.filter((v) => v === 1).length, N = y.length - P; let tp = 0, fp = 0, auc = 0, pf = 0, pt = 0; const pts: number[][] = [[0, 0]];
    for (const i of ix) { if (y[i] === 1) tp++; else fp++; const f = fp / (N || 1), tr = tp / (P || 1); auc += (f - pf) * (tr + pt) / 2; pf = f; pt = tr; pts.push([f, tr]); } return { pts, auc }; };
  const roc = H && { tooltip: { trigger: 'item', formatter: (p: any) => `${p.seriesName}<br/>catches ${(p.value[1] * 100).toFixed(0)}% of yes-months at ${(p.value[0] * 100).toFixed(0)}% false alarms` },
    grid: { left: 44, right: 12, top: 40, bottom: 40 }, legend: { top: 4, left: 0 },
    xAxis: { type: 'value', min: 0, max: 1, name: 'false-alarm rate', nameLocation: 'middle', nameGap: 24, ...axisStyle(t) },
    yAxis: { type: 'value', min: 0, max: 1, name: 'hit rate', nameLocation: 'middle', nameGap: 30, ...axisStyle(t) },
    series: [...sel4.filter((m) => H.models[m]).map((m) => { const r = rocOf(H.models[m], H.outcome); return { name: `${SHORT[m]} · AUC ${r.auc.toFixed(3)}`, type: 'line', data: r.pts, showSymbol: false, lineStyle: { width: 2, color: colourFor(sel4, m) }, itemStyle: { color: colourFor(sel4, m) } }; }),
      { name: 'coin flip', type: 'line', data: [[0, 0], [1, 1]], showSymbol: false, lineStyle: { type: 'dashed', color: t.mutedText, width: 1 }, itemStyle: { color: t.mutedText }, silent: true, tooltip: { show: false } }] };
  const relOf = (p: number[], y: number[]) => { const out: number[][] = []; for (let b = 0; b < 8; b++) { const ix = p.map((_, i) => i).filter((i) => p[i] >= b / 8 && (p[i] < (b + 1) / 8 || b === 7)); if (ix.length) out.push([ix.reduce((s, i) => s + p[i], 0) / ix.length, ix.reduce((s, i) => s + y[i], 0) / ix.length, ix.length]); } return out; };
  const rel = H && { tooltip: { trigger: 'item', formatter: (p: any) => `${p.seriesName}<br/>forecasts ~${(p.value[0] * 100).toFixed(0)}% → yes ${(p.value[1] * 100).toFixed(0)}% (${p.value[2]} months)` },
    grid: { left: 44, right: 12, top: 40, bottom: 40 }, legend: { top: 4, left: 0 },
    xAxis: { type: 'value', min: 0, max: 1, name: 'forecast probability', nameLocation: 'middle', nameGap: 24, ...axisStyle(t) },
    yAxis: { type: 'value', min: 0, max: 1, name: 'observed frequency', nameLocation: 'middle', nameGap: 30, ...axisStyle(t) },
    series: [...sel4.filter((m) => H.models[m]).map((m) => ({ name: SHORT[m], type: 'line', data: relOf(H.models[m], H.outcome), symbol: 'circle', symbolSize: (v: number[]) => Math.min(18, 6 + Math.sqrt(v[2]) * 0.8),
      lineStyle: { width: 2, color: colourFor(sel4, m) }, itemStyle: { color: colourFor(sel4, m), borderColor: t.surface, borderWidth: 2 } })),
      { name: 'perfect', type: 'line', data: [[0, 0], [1, 1]], showSymbol: false, lineStyle: { type: 'dashed', color: t.mutedText, width: 1 }, itemStyle: { color: t.mutedText }, silent: true, tooltip: { show: false } }] };
  const eraOpt = { tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => skillText(v) }, legend: { top: 4, left: 0 }, grid: { left: 48, right: 12, top: 40, bottom: 28 },
    xAxis: { type: 'category', data: eras, ...axisStyle(t) }, yAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
    series: sel4.map((m) => ({ name: SHORT[m], type: 'bar', barMaxWidth: 18, barGap: '15%', data: eras.map((e) => d.backtest.by_era[e]?.[m]?.skill_vs_base_rate ?? null), itemStyle: { color: colourFor(sel4, m), borderRadius: [3, 3, 0, 0] } })) };
  const lb = models.map((m) => { const r = d.models[m]?.record ?? {}; return { m, name: d.models[m].name, what: d.models[m].what, now: d.models[m].probability, skill: r.skill_vs_base_rate, recent: d.backtest?.by_era?.[recentEra]?.[m]?.skill_vs_base_rate,
    auroc: r.auroc, brier: r.brier, hit: r.hit_rate, p: d.models[m]?.gain?.p_no_gain, gate: d.models[m].gate, serving: d.signal.model === m }; });
  const cols: ColumnDef<any, any>[] = [
    { id: 'model', header: 'Model', accessorKey: 'name', enableHiding: false, cell: (c) => <Hint text={c.row.original.what}><span className="inline-flex items-center gap-2"><span className="ml-dot" style={{ background: sel4.includes(c.row.original.m) ? colourFor(sel4, c.row.original.m) : 'var(--border)' }} /><span className="text-text-primary">{c.getValue()}</span></span></Hint> },
    { header: 'Today', accessorKey: 'now', meta: { numeric: true }, cell: (c) => pct(c.getValue()) },
    { header: 'Skill', accessorKey: 'skill', meta: { numeric: true, title: 'Brier skill vs the base rate, whole period' }, cell: (c) => <span className={toneOf(c.getValue())}>{skillText(c.getValue())}</span> },
    { header: recentEra ?? 'Recent', accessorKey: 'recent', meta: { numeric: true }, cell: (c) => <span className={toneOf(c.getValue())}>{skillText(c.getValue())}</span> },
    { header: 'AUROC', accessorKey: 'auroc', meta: { numeric: true } },
    { header: 'Brier', accessorKey: 'brier', meta: { numeric: true }, sortDescFirst: false },
    { header: 'Hit rate', accessorKey: 'hit', meta: { numeric: true }, cell: (c) => (c.getValue() == null ? '—' : pct(c.getValue())) },
    { header: 'P(luck)', accessorKey: 'p', meta: { numeric: true, title: 'Chance the gain over the champion is luck (year-block bootstrap)' }, cell: (c) => (c.getValue() == null ? '—' : pct(c.getValue())) },
    { header: 'Stage', accessorKey: 'gate', cell: (c) => c.row.original.serving ? <span className="ml-pill" data-tone="prod">production</span> : c.row.original.m === 'champion' ? <span className="ml-pill">baseline</span>
      : <Hint text={c.getValue()}><span className="ml-pill" data-tone={c.getValue() === 'eligible' ? 'eligible' : 'shadow'}>{c.getValue() === 'eligible' ? 'eligible' : 'shadow'}</span></Hint> },
  ];
  return (
    <div className="space-y-2.5">
      <AutonomousNotice d={d} />
      <Panel title={`Leaderboard — ${d.title}`} sub={<>
        {/* Every probability on this page answers the question below, not the short title above it. */}
        {d.question && <span className="block">{d.question}</span>}
        {`Walk-forward ${d.backtest?.from}–${d.backtest?.to} · ${d.backtest?.forecasts} monthly forecasts · base rate ${pct(d.positive_share)} · promotion bar P(luck) < ${pct(d.promotion.bar)} (${d.promotion.comparisons} comparisons)`}
        {!!d.notes?.length && <span className="block">{d.notes.join(' ')}</span>}
      </>}>
        <DataGrid data={lb} columns={cols} initialSort={[{ id: 'skill', desc: true }]} filterPlaceholder="Filter models…" rowClassName={(r) => (r.serving ? 'bg-surface-2' : '')} />
      </Panel>
      <Panel title="Forecasts over time" sub="Out-of-sample probability by month; shaded = the answer was yes. Shift-scroll or drag the slider to zoom; click legend items to show or hide; the toolbox saves a PNG or shows the data.">
        {H ? <EChart option={timeline!} height={340} group={`lab-${sel}`} ariaLabel="Forecast probability over time" /> : hq.isError ? <div className="text-xs text-amber">{(hq.error as Error).message}</div> : <Skeleton h={340} />}
      </Panel>
      <div className="ml-grid-12">
        <div style={span(4)} className="ml-span-4"><Panel title="ROC — ranking quality" sub="Up and left is better; the diagonal is a coin flip.">{H ? <EChart option={roc!} height={300} ariaLabel="ROC curves" /> : <Skeleton h={300} />}</Panel></div>
        <div style={span(4)} className="ml-span-4"><Panel title="Calibration — honest probabilities?" sub="On the diagonal = probabilities mean what they say; marker size = months.">{H ? <EChart option={rel!} height={300} ariaLabel="Calibration curves" /> : <Skeleton h={300} />}</Panel></div>
        <div style={span(4)} className="ml-span-4"><Panel title="Skill by era" sub="Below zero = worse than always guessing the base rate.">{eras.length ? <EChart option={eraOpt} height={300} ariaLabel="Skill by era" /> : <Skeleton h={300} />}</Panel></div>
      </div>
    </div>
  );
}

// ── Network visualizer ────────────────────────────────────────────────────────
function Visualizer() {
 const [view,setView]=useState('research');
 return <div className="space-y-3"><p className="text-xs text-[var(--text-secondary)]">One evidence map and one live model view. Specialist modules are parts of the same model; baseline models remain for validation.</p><Segmented label="Research workspace" value={view} onChange={setView} options={[{value:'research',label:'Research map'},{value:'live',label:'Live model'}]}/>{view==='research'?<ResearchNetwork/>:<><LiveModularFlow/><details className="rounded border p-3"><summary className="cursor-pointer text-xs">Model architecture and baseline diagnostics</summary><ModularNetwork/><ShallowVisualizer/></details></>}</div>;

}
function ShallowVisualizer() {
  const sel = useMlTask();
  const q = useVisualizerQ(sel);
  const d = q.data;
  const [x, setX] = useState<number[] | null>(null);
  const [netIdx, setNetIdx] = useState(0);
  const [curve, setCurve] = useState(0);
  // replay: step the real monthly inputs through the network
  const hq = useInputsQ(sel, !!d?.available);
  const [idx, setIdx] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<'1' | '3' | '8'>('3');
  useEffect(() => { if (d?.available) { setX(d.features.map((f: any) => d.inputs[f.key])); setCurve(0); setNetIdx(0); } }, [d?.available, d?.month, d?.task, sel]);
  useEffect(() => { setIdx(null); setPlaying(false); }, [sel]);
  useEffect(() => {
    const n = hq.data?.months?.length ?? 0;
    if (!playing || !n) return;
    const id = window.setInterval(() => setIdx((i) => {
      const k = i == null || i >= n - 1 ? Math.max(0, n - 240) : i + 1;             // start 20 years back
      if (k >= n - 1) setPlaying(false);
      return k;
    }), 900 / Number(speed));
    return () => window.clearInterval(id);
  }, [playing, speed, hq.data]);
  useEffect(() => { if (idx != null && hq.data) setX(hq.data.values[idx]); }, [idx, hq.data]);
  const recent = useMemo(() => {
    const h = hq.data; if (!h?.values?.length) return undefined;
    const end = (idx ?? h.values.length - 1) + 1, rows = h.values.slice(Math.max(0, end - 24), end);
    return rows[0].map((_: number, i: number) => rows.map((r: number[]) => r[i]));
  }, [hq.data, idx]);
  if (!d?.available || d.task!==sel || !x || x.length!==d.features?.length) return q.isLoading ? <Skeleton /> : <Training d={d} onRetry={() => q.refetch()} />;
  if(!validWeights(d.network?.weights,d.features.length)) return <Panel title="Network export unavailable"><p role="alert">The exported weights are incomplete or incompatible. Refresh the model before replaying it.</p></Panel>;
  const w: Weights = d.network.weights, cal = d.network.calibration;
  const selectedNet=Math.min(netIdx,w.nets.length-1);
  const labels: string[] = d.features.map((f: any) => f.label), keys: string[] = d.features.map((f: any) => f.key);
  const ranges = keys.map((k) => d.data_checks.inputs[k]);
  const now = ensemble(w, cal, x);
  const t = chartTheme();
  const lo = ranges[curve].train_min, hi = ranges[curve].train_max;
  const pts = Array.from({ length: 61 }, (_, k) => { const v = lo + ((hi - lo) * k) / 60; const xx = [...x]; xx[curve] = v; const e = ensemble(w, cal, xx); return [v, e.p, e.lo, e.hi]; });
  const respOpt = { tooltip: { trigger: 'axis', formatter: (p: any) => `${labels[curve]} = ${p[0].value[0].toFixed(2)}<br/>probability <b>${(p[0].value[1] * 100).toFixed(1)}%</b>` },
    grid: { left: 48, right: 16, top: 16, bottom: 40 }, legend: { show: false },
    xAxis: { type: 'value', min: lo, max: hi, name: labels[curve], nameLocation: 'middle', nameGap: 24, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, showMinLabel: false, showMaxLabel: false } },
    yAxis: { type: 'value', min: 0, max: 1, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
    series: [
      { type: 'line', data: pts.map((p) => [p[0], p[2]]), showSymbol: false, lineStyle: { width: 1, type: 'dashed', color: t.series[0], opacity: 0.5 }, silent: true },
      { type: 'line', data: pts.map((p) => [p[0], p[3]]), showSymbol: false, lineStyle: { width: 1, type: 'dashed', color: t.series[0], opacity: 0.5 }, silent: true },
      { type: 'line', data: pts.map((p) => [p[0], p[1]]), showSymbol: false, lineStyle: { width: 2, color: t.series[0] },
        markLine: { symbol: 'none', silent: true, data: [{ xAxis: x[curve] }], lineStyle: { color: t.mutedText, type: 'dashed' }, label: { formatter: 'now', color: t.mutedText } } }] };
  const ensOpt = { toolbox: { show: false }, tooltip: { trigger: 'item', formatter: (p: any) => `network ${p.dataIndex + 1}: ${(p.value[0] * 100).toFixed(1)}%` }, grid: { left: 16, right: 16, top: 24, bottom: 26 }, legend: { show: false },
    xAxis: { type: 'value', min: 0, max: 1, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } }, yAxis: { type: 'value', show: false, min: -1, max: 1 },
    series: [{ type: 'scatter', data: now.each.map((p) => [p, 0]), symbolSize: 12, itemStyle: { color: t.series[0], opacity: 0.75, borderColor: t.surface, borderWidth: 2 },
      markLine: { symbol: 'none', silent: true, data: [{ xAxis: now.p }], lineStyle: { color: t.textStrong, width: 2 }, label: { formatter: `average ${(now.p * 100).toFixed(1)}%`, color: t.textStrong } } }] };
  const hidden = forward(w.nets[selectedNet], w, x).h;
  const h = hq.data;
  const months: string[] = h?.months ?? [];
  const jump = (m: string) => { const k = months.findIndex((v) => v >= m); if (k >= 0) { setPlaying(false); setIdx(k); } };
  const live = idx == null;
  const whatIf=live&&keys.some((k,i)=>Math.abs(x[i]-d.inputs[k])>1e-8);
  return (
    <div className="space-y-2.5">
      <p className="text-xs text-text-secondary">{d.calibration_basis??"Interactive shallow neural model — distinct from the modular sequence network."} Historical replay applies today’s fitted weights to past inputs; it is not an out-of-sample forecast.</p>
      <Panel title={`Signal flow — network ${selectedNet + 1} of ${w.nets.length}: ${labels.length} inputs → ${hidden.length} hidden (tanh) → 1 output`}
        sub="Particles carry each connection's live signal (weight × activation): faster and brighter = stronger; blue and amber show positive and negative local signals, not causal effects. Hidden units pulse with their activation. Press play to replay the real monthly inputs through the network."
        actions={<Segmented label="Network" value={String(netIdx)} onChange={(v) => setNetIdx(Number(v))} options={w.nets.map((_, i) => ({ value: String(i), label: String(i + 1) }))} />}>
        <NeuralFlow w={w} netIdx={selectedNet} x={x} labels={labels} cal={cal} recent={recent}
          month={live ? `${d.as_of_inputs} · ${whatIf?'what-if':'live'}` : months[idx]} outcome={live ? null : h?.outcome?.[idx] ?? null} />
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <button className="ml-btn" data-variant="primary" disabled={!h} onClick={() => setPlaying((p) => !p)} aria-label={playing ? 'Pause' : 'Play'}>
            {playing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}{playing ? 'Pause' : live ? 'Replay history' : 'Play'}</button>
          <Segmented label="Speed" value={speed} onChange={setSpeed} options={[{ value: '1', label: '1×' }, { value: '3', label: '3×' }, { value: '8', label: '8×' }]} />
          <div className="flex-1 min-w-[180px] px-1">{h && <RangeSlider label="Month" value={idx ?? months.length - 1} min={0} max={months.length - 1} step={1}
            onChange={(v) => { setPlaying(false); setIdx(Math.round(v)); }} />}</div>
          <span className="font-mono text-2xs text-text-secondary w-16 text-right">{live ? (whatIf?'what-if':'live') : months[idx]}</span>
          {[['2001-03', 'Dot-com'], ['2007-12', 'GFC'], ['2020-02', 'Covid'], ['2022-06', 'Inflation']].map(([m, l]) => (
            <button key={m} className="ml-btn" disabled={!h} onClick={() => jump(m)}>{l}</button>))}
          <button className="ml-btn" onClick={() => { setPlaying(false); setIdx(null); setX(keys.map((k) => d.inputs[k])); }}>Live</button>
        </div>
        {hq.isError && <div className="text-2xs text-amber mt-1">Input history unavailable — {(hq.error as Error).message}</div>}
      </Panel>
      <PanelGroup direction="horizontal" autoSaveId="ml-visualizer-2" style={{ height: 'auto', overflow: 'visible' }}>
        <RPanel defaultSize={55} minSize={35} style={{ overflow: 'visible' }}>
          <div className="space-y-2.5 pr-1">
            <Panel title="Response curve" sub={`Probability as one input moves (others held); dashed = lowest and highest of ${w.nets.length} networks.`}
              actions={<select value={curve} onChange={(e) => setCurve(Number(e.target.value))} className="ml-btn" aria-label="Input">{labels.map((l, i) => <option key={l} value={i}>{l}</option>)}</select>}>
              <EChart option={respOpt} height={260} ariaLabel="Response curve" />
            </Panel>
            {d.deep && d.models?.deep_sequence && <Panel title="Deep sequence network (GRU)" sub={`Reads ${d.deep.sequence_months} months × ${d.deep.inputs_per_month} inputs; answers all six questions at once. Five independently trained seeds.`}>
              <EChart height={90} ariaLabel="Deep network seeds" option={{ ...ensOpt, series: [{ ...ensOpt.series[0], data: (d.deep.seeds ?? []).map((p: number) => [p, 0]), itemStyle: { color: t.series[1], opacity: 0.8, borderColor: t.surface, borderWidth: 2 },
                markLine: { symbol: 'none', silent: true, data: [{ xAxis: d.models.deep_sequence.probability }], lineStyle: { color: t.textStrong, width: 2 }, label: { formatter: `${(d.models.deep_sequence.probability * 100).toFixed(1)}%`, color: t.textStrong } } }] }} />
              <div className="text-2xs text-text-tertiary">Walk-forward skill {skillText(d.models.deep_sequence.record?.skill_vs_base_rate)} · AUROC {d.models.deep_sequence.record?.auroc ?? '—'}</div>
            </Panel>}
          </div>
        </RPanel>
        <PanelResizeHandle className="ml-resize-handle" />
        <RPanel defaultSize={45} minSize={28} style={{ overflow: 'visible' }}>
          <div className="space-y-2.5 pl-1">
            <Panel title="What if…" sub={`Recomputed in your browser from the exported weights. ${live ? `Inputs as of ${d.as_of_inputs}.` : `Inputs from ${months[idx]}.`}`}
              actions={<button className="ml-btn" onClick={() => { setPlaying(false); setIdx(null); setX(keys.map((k) => d.inputs[k])); }}>Reset to today</button>}>
              <div className="flex items-baseline gap-3 mb-1"><span className="ml-stat-value">{pct(now.p)}</span><span className="text-2xs text-text-tertiary">networks {pct(now.lo)}–{pct(now.hi)} · logistic reference today {pct(d.champion.probability)}</span></div>
              <EChart option={ensOpt} height={90} ariaLabel="Each network's probability" />
              <div className="space-y-2 mt-2">{keys.map((k, i) => (
                <div key={k} className="grid grid-cols-[150px_1fr_60px] items-center gap-3 text-2xs">
                  <span className="truncate text-text-secondary" title={labels[i]}>{labels[i]}</span>
                  <RangeSlider label={labels[i]} value={Math.max(ranges[i].train_min, Math.min(ranges[i].train_max, x[i]))} min={ranges[i].train_min} max={ranges[i].train_max}
                    onChange={(v) => { setPlaying(false); setIdx(null); const n = [...x]; n[i] = v; setX(n); }} />
                  <span className="font-mono text-right">{x[i].toFixed(2)}</span>
                </div>))}</div>
            </Panel>
            {d.tuned_settings && <Panel title="Settings chosen this month" sub="Tuned on a validation slice of the training window only (with a gap equal to the answer delay).">
              <div className="text-xs space-y-1">{d.tuned_settings.network && <div>Neural network: <b>{d.tuned_settings.network.hidden_units}</b> hidden units, L2 <b>{d.tuned_settings.network.l2_alpha}</b></div>}
                {d.tuned_settings.boosting && <div>Gradient boosting: <b>{d.tuned_settings.boosting.leaves}</b> leaves, <b>{d.tuned_settings.boosting.trees}</b> trees</div>}</div>
            </Panel>}
          </div>
        </RPanel>
      </PanelGroup>
    </div>
  );
}

// ── Explainability ────────────────────────────────────────────────────────────
function Explain() {
  const sel = useMlTask();
  const q = useTaskQ(sel);
  const d = q.data;
  if (!d?.available) return q.isLoading ? <Skeleton /> : <Training d={d} onRetry={() => q.refetch()} />;
  const t = chartTheme();
  const lab = Object.fromEntries(d.features.map((f: any) => [f.key, f.label]));
  const diverging = (title: string, a: Record<string, number>, scale = 100, unit = 'pts') => {
    const e = Object.entries(a).sort((p, q2) => Math.abs(p[1]) - Math.abs(q2[1]));
    return { tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => `${v > 0 ? '+' : ''}${(v * scale).toFixed(2)} ${unit}` }, legend: { show: false }, title: { show: false, text: title },
      grid: { left: 170, right: 24, top: 10, bottom: 24 }, xAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => (v * scale).toFixed(1) } },
      yAxis: { type: 'category', data: e.map(([k]) => lab[k] ?? k), ...axisStyle(t) },
      series: [{ type: 'bar', barMaxWidth: 14, data: e.map(([, v]) => ({ value: v, itemStyle: { color: v >= 0 ? t.red : t.green, borderRadius: v >= 0 ? [0, 3, 3, 0] : [3, 0, 0, 3] } })),
        markLine: { symbol: 'none', silent: true, data: [{ xAxis: 0 }], lineStyle: { color: t.mutedText }, label: { show: false } } }] };
  };
  const groupOpt = (k: string) => { const g = Object.entries(d.importance[k].by_group).sort((a: any, b: any) => a[1] - b[1]);
    return { tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => pct(v) }, legend: { show: false }, grid: { left: 150, right: 30, top: 10, bottom: 24 },
      xAxis: { type: 'value', ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
      yAxis: { type: 'category', data: g.map(([n]) => n), ...axisStyle(t) },
      series: [{ type: 'bar', data: g.map(([, v]) => v), barMaxWidth: 14, itemStyle: { color: t.series[0], borderRadius: [0, 3, 3, 0] } }] }; };
  const regime = d.regime?.history;
  const regOpt = regime && { tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${(v * 100).toFixed(1)}%` }, legend: { show: false }, grid: { left: 44, right: 16, top: 16, bottom: 56 },
    xAxis: { type: 'category', data: regime.map((r: any) => r.month), boundaryGap: false, ...axisStyle(t) },
    yAxis: { type: 'value', min: 0, max: 1, ...axisStyle(t), axisLabel: { ...axisStyle(t).axisLabel, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
    dataZoom: [{ type: 'inside', zoomOnMouseWheel: 'shift', moveOnMouseWheel: false }, { type: 'slider', height: 16, bottom: 10, borderColor: t.border }],
    series: [{ type: 'line', data: regime.map((r: any) => r.p), showSymbol: false, lineStyle: { width: 2, color: t.series[1] }, areaStyle: { color: t.series[1], opacity: 0.15 }, name: 'low-growth state' }] };
  const topCols: ColumnDef<any, any>[] = [
    { header: 'Series', accessorKey: 'label', cell: (c) => <span className="text-text-primary">{c.getValue()}</span> },
    { header: 'Group', accessorKey: 'group' },
    { header: 'Share', accessorKey: 'share', meta: { numeric: true }, cell: (c) => pct(c.getValue()) },
  ];
  return (
    <div className="space-y-2.5">
      <div className="ml-grid-12">
        <div style={span(6)} className="ml-span-6"><Panel title="What moved today's network forecast" sub="Forecast minus forecast with the input at its average (occlusion ≈ Shapley). Red raises, green lowers; points of probability.">
          <EChart option={diverging('network', d.attributions.network)} height={280} ariaLabel="Network attributions" /></Panel></div>
        <div style={span(6)} className="ml-span-6"><Panel title="Champion: standardised coefficients" sub="Change in log-odds per standard deviation of each input.">
          <EChart option={diverging('coef', d.champion.coefficients, 1, 'log-odds / sd')} height={280} ariaLabel="Champion coefficients" /></Panel></div>
      </div>
      {d.importance && <div className="ml-grid-12">{(['boosting', 'forest'] as const).map((k) => d.importance[k] && (
        <div key={k} style={span(6)} className="ml-span-6"><Panel title={`${d.models[k]?.name}: importance by data group`} sub={`${d.panel?.series ?? 0} panel series + ${d.features.length} core + text & news. Importance = error reduction; it shows use, not cause.`}>
          <EChart option={groupOpt(k)} height={240} ariaLabel={`${k} importance by group`} />
          <div className="mt-2"><DataGrid data={d.importance[k].top} columns={topCols} initialSort={[{ id: 'share', desc: true }]} maxHeight={220} filterPlaceholder="Filter series…" /></div>
        </Panel></div>))}</div>}
      {regOpt && <Panel title="Regime-switching model — probability of the low-growth state (real time)" sub={`Two-state Markov model of production, payrolls, real income and consumption (Hamilton; Chauvet & Piger). Now ${pct(d.regime.low_growth_state_probability)}; mapped to this question ${pct(d.models?.regime_switch?.probability)}.`}>
        <EChart option={regOpt} height={260} ariaLabel="Low-growth state probability" /></Panel>}
    </div>
  );
}

// ── Monitoring ────────────────────────────────────────────────────────────────
function Monitoring() {
  const sel = useMlTask();
  const q = useTaskQ(sel);
  const d = q.data;
  const reg = useRegistryQ();
  const cov = useFeaturesQ();
  const t = chartTheme();
  const checks = d?.available ? d.features.map((f: any) => ({ ...f, ...d.data_checks.inputs[f.key] })) : [];
  const shiftOpt = d?.available && { tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)} sd` }, legend: { show: false },
    grid: { left: 190, right: 30, top: 10, bottom: 24 }, xAxis: { type: 'value', min: -3, max: 3, ...axisStyle(t) },
    yAxis: { type: 'category', data: checks.map((c: any) => c.label), ...axisStyle(t) },
    series: [{ type: 'bar', barMaxWidth: 12, data: checks.map((c: any) => ({ value: Math.max(-3, Math.min(3, c.shift_12m_sd)), itemStyle: { color: Math.abs(c.shift_12m_sd) > 1.5 || c.outside_training_range ? t.amber : t.series[0], borderRadius: 3 } })),
      markArea: { silent: true, itemStyle: { color: t.outcome }, data: [[{ xAxis: -1.5 }, { xAxis: 1.5 }]] }, markLine: { symbol: 'none', silent: true, data: [{ xAxis: 0 }], lineStyle: { color: t.mutedText }, label: { show: false } } }] };
  const checkCols: ColumnDef<any, any>[] = [
    { header: 'Input', accessorKey: 'label', cell: (c) => <span className="text-text-primary">{c.getValue()} <span className="text-text-tertiary">{c.row.original.unit}</span></span> },
    { header: 'Today', accessorKey: 'value', meta: { numeric: true } },
    { header: 'Train min', accessorKey: 'train_min', meta: { numeric: true } }, { header: 'Train max', accessorKey: 'train_max', meta: { numeric: true } },
    { header: 'z', accessorKey: 'z', meta: { numeric: true } },
    { header: '12m shift', accessorKey: 'shift_12m_sd', cell: (c) => <span className="inline-flex items-center gap-2"><DriftBullet shift={c.getValue()} outside={c.row.original.outside_training_range} /><span className="font-mono">{c.getValue() > 0 ? '+' : ''}{c.getValue()}σ</span></span> },
    { header: 'Status', id: 'status', accessorFn: (r) => (r.outside_training_range ? 2 : Math.abs(r.shift_12m_sd) > 1.5 ? 1 : 0), cell: (c) => c.getValue() === 2 ? <span className="ml-pill" data-tone="warn">outside range</span> : c.getValue() === 1 ? <span className="ml-pill" data-tone="warn">shifted</span> : <span className="ml-pill" data-tone="ok">OK</span> },
  ];
  const retrainCols: ColumnDef<any, any>[] = [
    { header: 'Task', accessorKey: 'task' }, { header: 'Month', accessorKey: 'month' },
    { header: 'Trained', accessorKey: 'trained_at', cell: (c) => c.getValue()?.slice(0, 16).replace('T', ' ') },
    { header: 'Months', accessorKey: 'training_months', meta: { numeric: true } },
    { header: 'Checks', accessorKey: 'data_ok', cell: (c) => c.getValue() ? <span className="ml-pill" data-tone="ok">pass</span> : <Hint text={(c.row.original.flags ?? []).join('; ')}><span className="ml-pill" data-tone="warn">{c.row.original.flags?.length} warnings</span></Hint> },
  ];
  const featCols: ColumnDef<any, any>[] = [
    { header: 'Feature', accessorKey: 'label', cell: (c) => <span className="text-text-primary">{c.getValue()}</span> }, { header: 'Source', accessorKey: 'source' },
    { header: 'From', accessorKey: 'from' }, { header: 'To', accessorKey: 'to' }, { header: 'Months', accessorKey: 'months', meta: { numeric: true } },
  ];
  return (
    <div className="space-y-2.5">
      {!d?.available ? (q.isLoading ? <Skeleton /> : <Training d={d} onRetry={() => q.refetch()} />) : (
        <div className="ml-grid-12">
          <div style={span(5)} className="ml-span-5"><Panel title="Input drift — last 12 months vs training" sub="Shift of each input's recent average in training standard deviations; the band is the ±1.5 alarm zone.">
            <EChart option={shiftOpt} height={300} ariaLabel="Input drift" /></Panel></div>
          <div style={span(7)} className="ml-span-7"><Panel title={`Input checks — ${d.title}`} sub={`Inputs as of ${d.as_of_inputs}. Networks extrapolate badly outside their training range.`}
            actions={d.data_checks.ok ? <span className="ml-pill" data-tone="ok">all checks pass</span> : <span className="ml-pill" data-tone="warn">{d.data_checks.flags.length} warnings</span>}>
            <DataGrid data={checks} columns={checkCols} filterPlaceholder="Filter inputs…" /></Panel></div>
        </div>)}
      <div className="ml-grid-12">
        <div style={span(5)} className="ml-span-5"><Panel title="Retraining log" sub="Every monthly retrain and whether its input checks passed.">
          {reg.data ? <DataGrid data={reg.data.retrains} columns={retrainCols} maxHeight={320} initialSort={[{ id: 'trained_at', desc: true }]} /> : <Skeleton h={200} />}</Panel></div>
        <div style={span(7)} className="ml-span-7"><Panel title="Feature store" sub={d?.panel ? `${d.panel.series} panel series · ${Object.entries(d.panel.groups).map(([g, n]: any) => `${g} ${n}`).join(' · ')}` : 'Every input, as known at the time.'}>
          {cov.data ? <DataGrid data={Object.entries(cov.data.features).map(([k, v]: any) => ({ key: k, ...v }))} columns={featCols} maxHeight={320} filterPlaceholder="Filter features…" /> : <Skeleton h={200} />}</Panel></div>
      </div>
    </div>
  );
}

// ── Registry ──────────────────────────────────────────────────────────────────
function Registry() {
  const reg = useRegistryQ();
  const [msg, setMsg] = useState<string | null>(null);
  if (!reg.data) return reg.isError ? <Training d={{ reason: (reg.error as Error).message }} onRetry={() => reg.refetch()} /> : <Skeleton />;
  const act = async (task: string, method: 'POST' | 'DELETE') => { setMsg(null); try { await send(`/api/v1/ml/tasks/${task}/promote`, method); setMsg(method === 'POST' ? `Promoted for ${task}.` : `${task} returned to its champion.`); } catch (e: any) { setMsg(e.message); } };
  const byTask: Record<string, any> = {};
  for (const s of reg.data.stages) (byTask[s.task] ??= { task: s.task, title: s.task_title, models: {} }).models[s.model] = s;
  const rows = Object.values(byTask);
  const stageCols: ColumnDef<any, any>[] = [
    { header: 'Task', accessorKey: 'title', enableHiding: false, cell: (c) => <span className="text-text-primary whitespace-nowrap">{c.getValue()}</span> },
    ...MODEL_ORDER.map((m): ColumnDef<any, any> => ({ id: m, header: SHORT[m], accessorFn: (r) => r.models[m]?.stage, cell: (c) => { const s = c.row.original.models[m]; if (!s) return '—';
      return <Hint text={<>{s.model_name}<br />skill {skillText(s.skill)} · today {pct(s.probability)}<br />{s.gate}</>}><span className="ml-pill" data-tone={s.stage === 'production' ? 'prod' : s.gate === 'eligible' ? 'eligible' : 'shadow'}>{s.stage === 'production' ? 'production' : s.gate === 'eligible' ? 'eligible' : 'shadow'}</span></Hint>; } })),
    { id: 'action', header: 'Action', cell: (c) => { const r = c.row.original; const prom = reg.data.promotions.find((p: any) => p.task === r.task); const el = Object.values(r.models).filter((s: any) => s.gate === 'eligible') as any[];
      return prom ? <button className="ml-btn" onClick={() => act(r.task, 'DELETE')}>Demote</button> : el.length ? <button className="ml-btn" data-variant="primary" onClick={() => act(r.task, 'POST')}>Promote {SHORT[el[0].model]}</button> : <span className="text-text-tertiary">none eligible</span>; } },
  ];
  const auditCols: ColumnDef<any, any>[] = [
    { header: 'Logged', accessorKey: 'logged_at', cell: (c) => c.getValue()?.slice(0, 16).replace('T', ' ') }, { header: 'Task', accessorKey: 'task' },
    { header: 'Model', accessorKey: 'model', cell: (c) => short(c.getValue()) }, { header: 'Month', accessorKey: 'month' },
    { header: 'Probability', accessorKey: 'probability', meta: { numeric: true }, cell: (c) => pct(c.getValue()) },
  ];
  return (
    <div className="space-y-2.5">
      {msg && <div className="ml-panel"><div className="ml-panel-body text-xs">{msg}</div></div>}
      <Panel title="Model registry" sub="Production serves the signal; shadow models are trained, logged and scored monthly without serving. Promotion needs the gate and a PM or risk approval; demotion is the kill switch.">
        <DataGrid data={rows} columns={stageCols} filterPlaceholder="Filter tasks…" />
      </Panel>
      <div className="ml-grid-12">
        <div style={span(4)} className="ml-span-4"><Panel title="Approvals">{reg.data.promotions.length ? reg.data.promotions.map((p: any) => <div key={p.task} className="text-xs py-0.5">{p.task}: <b>{SHORT[p.model] ?? p.model}</b> — {p.approved_by}, {p.approved_at?.slice(0, 10)}</div>) : <div className="text-xs text-text-tertiary">No promotions — every task is served by its champion.</div>}</Panel></div>
        <div style={span(8)} className="ml-span-8"><Panel title="Forecast audit log" sub="One forecast per model per task per month, written once and never rewritten — scored when the answer is known.">
          <DataGrid data={reg.data.recent_forecasts} columns={auditCols} maxHeight={360} initialSort={[{ id: 'logged_at', desc: true }]} filterPlaceholder="Filter log…" /></Panel></div>
      </div>
    </div>
  );
}

// ── Knowledge scanner ─────────────────────────────────────────────────────────
function Knowledge() {
  const k = useKnowledgeQ();
  const [msg, setMsg] = useState<string | null>(null);
  const act = async (s: string, method: 'POST' | 'DELETE') => { try { await send(`/api/v1/ml/knowledge/${s}/approve`, method); setMsg(`${s} ${method === 'POST' ? 'approved' : 'removed'}`); } catch (e: any) { setMsg(e.message); } };
  if (!k.data) return k.isError ? <Training d={{ reason: (k.error as Error).message }} /> : <Skeleton />;
  const res = k.data.scan?.results ?? [];
  const t = chartTheme();
  const opt = { tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => (v == null ? '—' : v.toFixed(4)) }, legend: { top: 4, left: 0 }, grid: { left: 210, right: 20, top: 40, bottom: 24 },
    xAxis: { type: 'value', ...axisStyle(t) }, yAxis: { type: 'category', data: res.map((r: any) => r.label), inverse: true, ...axisStyle(t) },
    series: [{ name: 'Brier gain, all', type: 'bar', data: res.map((r: any) => r.brier_gain), itemStyle: { color: t.series[0], borderRadius: 3 }, barMaxWidth: 10 },
      { name: 'since 2005', type: 'bar', data: res.map((r: any) => r.brier_gain_since_2005), itemStyle: { color: t.series[1], borderRadius: 3 }, barMaxWidth: 10 }] };
  const cols: ColumnDef<any, any>[] = [
    { header: 'Indicator', accessorKey: 'label', cell: (c) => <Hint text={c.row.original.why}><span className="text-text-primary">{c.getValue()} <span className="text-text-tertiary">{c.row.original.series}</span></span></Hint> },
    { header: 'Gain', accessorKey: 'brier_gain', meta: { numeric: true }, cell: (c) => <span className={toneOf(c.getValue())}>{c.getValue() ?? '—'}</span> },
    { header: 'Since 2005', accessorKey: 'brier_gain_since_2005', meta: { numeric: true }, cell: (c) => <span className={toneOf(c.getValue())}>{c.getValue() ?? '—'}</span> },
    { header: 'P(luck)', accessorKey: 'p_no_gain', meta: { numeric: true }, cell: (c) => (c.getValue() == null ? '—' : pct(c.getValue())) },
    { header: 'Status', accessorKey: 'status', cell: (c) => c.getValue() === 'proposed' ? <button className="ml-btn" data-variant="primary" onClick={() => act(c.row.original.series, 'POST')}>Approve</button> : <span className="ml-pill">{c.getValue()}</span> },
  ];
  return (
    <div className="space-y-2.5">
      {msg && <div className="ml-panel"><div className="ml-panel-body text-xs">{msg}</div></div>}
      <div className="ml-grid-12">
        <div style={span(6)} className="ml-span-6"><Panel title="Candidate indicators — walk-forward Brier gain when added" sub={`Proposed only if the gain is significant after allowing for every candidate (bar ${k.data.scan ? pct(k.data.scan.bar) : '—'}). Last scan ${k.data.scan?.run_at?.slice(0, 10) ?? '—'}.`}>
          {res.length ? <EChart option={opt} height={340} ariaLabel="Candidate indicator gains" /> : <div className="text-xs text-text-tertiary">No scan yet — it runs on the 2nd of each month.</div>}</Panel></div>
        <div style={span(6)} className="ml-span-6"><Panel title="Scan results" sub="A person approves a proposal; it then joins the networks' inputs and is re-tested there.">
          <DataGrid data={res} columns={cols} initialSort={[{ id: 'p_no_gain', desc: false }]} filterPlaceholder="Filter indicators…" />
          <div className="mt-2 text-2xs text-text-tertiary">Approved: {k.data.approved?.length ? k.data.approved.map((a: any) => <span key={a.series} className="mr-2">{a.series} <button className="underline" onClick={() => act(a.series, 'DELETE')}>remove</button></span>) : 'none yet'}</div>
        </Panel></div>
      </div>
    </div>
  );
}

const RESEARCH: [string, string, string][] = [
  ['Walk-forward, conservative validation', 'Federal Reserve Board — Puglia & Tucker (2020): neural networks and trees beat probit under ordinary cross-validation, but the ranking reversed under time-respecting validation.', 'https://www.federalreserve.gov/econres/feds/files/2020038pap.pdf'],
  ['Purging, embargo, counting trials', 'López de Prado (Cornell / Advances in Financial ML); Bailey & López de Prado, the deflated Sharpe ratio.', 'https://en.wikipedia.org/wiki/Purged_cross-validation'],
  ['Deep ensembles for uncertainty', 'DeepMind — Lakshminarayanan, Pritzel & Blundell (2017): averaging independently trained networks gives calibrated uncertainty; their spread is shown here.', 'https://ar5iv.arxiv.org/html/1612.01474'],
  ['Calibrate after pooling', 'Rahaman & Thiery (NeurIPS 2020); Guo et al. (Cornell, 2017) on miscalibrated networks.', 'https://arxiv.org/pdf/2101.05397'],
  ['Tables are hard for networks', 'INRIA — Grinsztajn, Oyallon & Varoquaux (NeurIPS 2022): trees still beat deep learning on typical tabular data; networks struggle with uninformative inputs — so inputs are few and chosen from economics.', 'https://arxiv.org/abs/2207.08815'],
  ['Foundation models for small tables', 'University of Freiburg — Hollmann et al., TabPFN (Nature 2025): a pre-trained transformer for up to 10,000 rows; a candidate challenger (needs PyTorch).', 'https://pubmed.ncbi.nlm.nih.gov/39780007/'],
  ['Shape constraints', 'Google — deep lattice networks and shape constraints (NeurIPS 2017–18): monotonic constraints as tuning-free regularisation from domain knowledge.', 'https://papers.neurips.cc/paper_files/paper/2018/file/caa202034f268232c26fac9435f54e15-Paper.pdf'],
  ['Explaining each forecast', 'University of Washington — Lundberg & Lee, SHAP (NeurIPS 2017); Bank of England interpretable-ML workflow (2022); Anthropic attribution graphs (2025).', 'https://arxiv.org/abs/1705.07874'],
  ['Seeing the network', 'Google — Smilkov, Carter & Sculley, TensorFlow Playground: weight thickness and colour, live activations, direct manipulation.', 'https://poloclub.gatech.edu/idea2016/papers/p115-smilkov.pdf'],
  ['Machine learning for macro forecasting', 'Goulet Coulombe, Leroux, Stevanovic & Surprenant (J. Applied Econometrics 2022): non-linearity is the game changer, factors the best regulariser, gains concentrated in uncertain times; Medeiros et al. (JBES 2021): random forests on FRED-MD.', 'https://ideas.repec.org/a/wly/japmet/v37y2022i5p920-964.html'],
  ['The data-rich panel', 'McCracken & Ng, FRED-MD (St. Louis Fed, JBES 2016): the standard ~130-series monthly macro dataset and its stationarity transforms.', 'https://econpapers.repec.org/RePEc:fip:fedlwp:2015-012'],
  ['Regime switching', 'Hamilton (Econometrica 1989); Chauvet & Piger — the St. Louis Fed’s smoothed recession probabilities from a Markov-switching dynamic factor model.', 'https://fred.stlouisfed.org/series/RECPROUSM156N'],
  ['Text as data', 'Baker, Bloom & Davis — Economic Policy Uncertainty (QJE 2016) and the equity-market-volatility trackers; Shapiro, Sudhof & Wilson — SF Fed Daily News Sentiment (J. Econometrics 2022).', 'https://www.frbsf.org/research-and-insights/data-and-indicators/daily-news-sentiment-index/'],
  ['Continuous training with gates', 'Google — Sculley et al., Hidden Technical Debt in ML Systems (NeurIPS 2015) and TFX: retrain continuously, but validate data and models before serving.', 'https://proceedings.neurips.cc/paper/2015/file/86df7dcfd896fcaf2674f757a2463eba-Paper.pdf'],
  ['Champion / challenger, human control', 'Federal Reserve SR 11-7 model-risk guidance; Bridgewater AIA (humans control risk, data and the kill switch); Man AHL on overfitting; AQR (Israel, Kelly & Moskowitz) on ML in finance.', 'https://www.man.com/insights/overfitting-and-its-impact-on-the-investor'],
];

/** Research components that exist and are exercised by api/tests/test_institutional_components.py
 *  (21 tests) but are imported by nothing outside that file. Listed here because a passing test is
 *  evidence a component works, not evidence it is in the serving path — and the evidence map beside
 *  this tab already uses the word "fusion" for a different thing. */
const UNWIRED: { name: string; what: string; status: string }[] = [
  { name: 'state_store.py', what: 'Bitemporal SQLite feature store — asynchronous System 2 writers, synchronous System 1 reads.',
    status: 'No importer. The served path builds its features in features.py and panel.py instead.' },
  { name: 'fusion.py', what: 'Shape-checked graph cross-attention and FiLM modulation, written to sit on the existing TFT encoder.',
    status: 'No importer. The “Fusion & temporal memory” node on the evidence map is the modular network’s own concatenation layer, not this.' },
  { name: 'incremental_graph.py', what: 'Bounded sliding-window VAR-Lasso updates; positive lags give a temporal DAG.',
    status: 'No importer, and deliberately so — see the note below.' },
  { name: 'foraging_agent.py', what: 'Behaviour-cloned PPO agent for source selection, with bounded offline and online execution paths.',
    status: 'No importer. The learning panel’s foraging figures come from recorded query history and report live PPO selection as inactive.' },
];

function Method() {
  return (
    <div className="ml-grid-12">
      <div style={span(5)} className="ml-span-5"><Panel title="How it works">
        <ol className="list-decimal pl-5 text-xs text-text-secondary space-y-1.5">
          <li><b>Tasks.</b> Six questions tied to platform decisions, each with economically chosen inputs, every value as known at the time.</li>
          <li><b>Nine models, simple to deep.</b> Logistic champion; tuned neural network; factor model and factor network (8 factors from ~70 FRED-MD-style series); random forest and tuned gradient boosting on every series plus text & news; regime-switching (Markov) model; deep sequence network (GRU, PyTorch) reading 24 months of everything for all six questions; and the average.</li>
          <li><b>Walk-forward.</b> Refit every January on months whose answers were known; recalibrated on each model's own earlier forecasts; scored by era against the base rate.</li>
          <li><b>Gate.</b> A challenger serves only after a significant gain (allowing for every comparison), no damage since 2013, 24 live months ahead, and a person's approval.</li>
          <li><b>Self-teaching.</b> Retrains monthly, tunes its own settings on past data only, logs forecasts it can never rewrite, scores itself, checks its inputs for drift.</li>
          <li><b>Self-feeding.</b> The knowledge scanner tests new indicators monthly; only those that pass the gate can be approved.</li>
          <li><b>Used everywhere.</b> Skilful signals are quoted beside the desk playbook's calls; the Claude research assistant reads every signal.</li>
        </ol></Panel></div>
      <div style={span(7)} className="ml-span-7"><Panel title="The research it follows">
        <div className="space-y-2">{RESEARCH.map(([title, s, u]) => <div key={title} className="text-xs"><div className="text-text-primary font-semibold">{title}</div><div className="text-text-secondary">{s} <a href={u} target="_blank" rel="noopener noreferrer" className="text-bloomberg underline">source</a></div></div>)}</div>
      </Panel></div>
      <div style={span(12)} className="ml-span-12"><Panel title="Built and tested, not in the serving path"
        sub="Four research components are exercised by the test suite and imported by nothing else. A passing test says a component works; it does not say anything on this platform reads from it.">
        <div className="grid sm:grid-cols-2 gap-2 text-xs">
          {UNWIRED.map((c) => <div key={c.name} className="border border-border rounded-lg p-3">
            <b className="font-mono">{c.name}</b><p className="mt-1 text-text-secondary">{c.what}</p><p className="mt-1 text-text-tertiary">{c.status}</p>
          </div>)}
        </div>
        <p className="mt-3 text-xs text-amber">The causal graph updater is schema-compatible with the graph on the evidence map but is not the same graph: it fits a VAR-Lasso DAG over macro variables, while the map served here is an event and knowledge graph. Replacing one with the other would change what the models train on and invalidate the saved checkpoints, so whether to replace, supplement or leave it is an owner’s decision rather than a gap to close.</p>
        <p className="mt-2 text-[11px] text-text-tertiary">Listed from the source tree as at this commit; nothing here is served by an endpoint, so this panel is the only place their wiring state is stated.</p>
      </Panel></div>
    </div>
  );
}

/** Shown wherever a task's served signal came from the autonomous model, which is promoted by automated evidence gates
 *  rather than the PM / risk approval the other challengers need. */
function AutonomousNotice({ d }: { d: any }) {
  if (d?.promotion?.requires_human_approval !== false && d?.signal?.model !== 'autonomous_tft') return null;
  const prov = d.autonomous_provenance ?? {};
  return (
    <div className="ml-panel" role="note"><div className="ml-panel-body text-xs flex flex-wrap items-center gap-2">
      <span className="ml-pill" data-tone="warn">Autonomous model serving</span>
      <span className="text-text-secondary">This task's signal comes from the autonomous TFT/GAT model, promoted by automated evidence gates <b>without a PM or risk approval</b>.
        {prov.model_id ? ` Model ${String(prov.model_id).slice(0, 12)}, forecast origin ${String(prov.origin ?? '').slice(0, 16).replace('T', ' ')}.` : ''}
        {d.legacy_signal?.probability != null ? ` The approved champion would read ${pct(d.legacy_signal.probability)}.` : ''}</span>
    </div></div>
  );
}

/** Section experts and the situation gate: what each economic section says, how much it is trusted now, and its own
 *  out-of-sample record. Data: the task's `sections_detail` and the `sections` model record. */
function Sections() {
  const sel = useMlTask();
  const q = useTaskQ(sel);
  const d = q.data;
  const t = chartTheme();
  if (!d?.available) return q.isLoading ? <Skeleton /> : <Training d={d} onRetry={() => q.refetch()} />;
  const sx = d.sections_detail;
  const m = d.models?.sections;
  if (!sx) return (
    <Panel title="Section experts not computed for this month yet">
      <p className="text-xs text-text-secondary">They are built with the task's monthly retrain. After a backend update the first request retrains the task, and this view fills in once it finishes.</p>
    </Panel>);
  const rows = [...sx.sections].sort((a: any, b: any) => (b.weight_now ?? 0) - (a.weight_now ?? 0));
  const ax = axisStyle(t);
  const weightOpt = {
    legend: { show: false }, toolbox: { show: false },
    grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps: any[]) => { const r = rows[rows.length - 1 - ps[0].dataIndex];
      return `<b>${r.label}</b><br/>weight now ${pct(r.weight_now ?? 0)}<br/>section says ${r.probability == null ? 'no reading' : pct(r.probability)}`; } },
    xAxis: { type: 'value', max: 1, ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => `${Math.round(v * 100)}%` } },
    yAxis: { type: 'category', data: [...rows].reverse().map((r: any) => r.label), ...ax },
    series: [{ type: 'bar', barMaxWidth: 14, data: [...rows].reverse().map((r: any) => ({ value: r.weight_now ?? 0,
      itemStyle: { color: r.available ? t.series[0] : t.muted, borderRadius: [0, 3, 3, 0] } })),
      label: { show: true, position: 'right', fontSize: 10, color: t.text, formatter: (p: any) => { const r = rows[rows.length - 1 - p.dataIndex]; return r.probability == null ? 'n/a' : pct(r.probability); } } }],
  };
  const contrib = [...sx.sections].filter((r: any) => r.available).sort((a: any, b: any) => Math.abs(a.contribution) - Math.abs(b.contribution));
  const contribOpt = {
    legend: { show: false }, toolbox: { show: false },
    grid: { left: 8, right: 16, top: 8, bottom: 8, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(3)} log-odds` },
    xAxis: { type: 'value', ...ax },
    yAxis: { type: 'category', data: contrib.map((r: any) => r.label), ...ax },
    series: [{ type: 'bar', barMaxWidth: 14, data: contrib.map((r: any) => ({ value: r.contribution, itemStyle: { color: r.contribution >= 0 ? t.red : t.green } })),
      markLine: { symbol: 'none', silent: true, data: [{ xAxis: 0 }], lineStyle: { color: t.borderStrong }, label: { show: false } } }],
  };
  const cols: ColumnDef<any, any>[] = [
    { header: 'Section', accessorKey: 'label', enableHiding: false, cell: (c) => <span className="text-text-primary">{c.getValue()}</span> },
    { header: 'Inputs', accessorKey: 'inputs', meta: { numeric: true } },
    { header: 'Reading now', accessorKey: 'probability', meta: { numeric: true }, cell: (c) => (c.getValue() == null ? <span className="text-text-tertiary">no data</span> : pct(c.getValue())) },
    { header: 'Weight now', accessorKey: 'weight_now', meta: { numeric: true }, cell: (c) => (c.getValue() == null ? '—' : pct(c.getValue())) },
    { header: 'OOS skill', accessorFn: (r) => r.record?.skill_vs_base_rate, meta: { numeric: true, title: 'Out-of-sample Brier skill against the base rate (raw, uncalibrated)' },
      cell: (c) => (c.getValue() == null ? '—' : <span className={toneOf(c.getValue())}>{skillText(c.getValue())}</span>) },
    { header: 'AUROC', accessorFn: (r) => r.record?.auroc, meta: { numeric: true }, cell: (c) => c.getValue() ?? '—' },
    { header: 'Record from', accessorFn: (r) => r.record?.from, cell: (c) => c.getValue() ?? '—' },
    { header: 'Strongest inputs', accessorFn: (r) => (r.top_inputs ?? []).map((x: any) => x.label).join(', '), enableSorting: false,
      cell: (c) => <span className="text-text-secondary">{(c.row.original.top_inputs ?? []).slice(0, 3).map((x: any) => `${x.label} (${x.coef > 0 ? '↑' : '↓'})`).join(' · ') || '—'}</span> },
  ];
  const on = sx.situation.filter((s: any) => s.on);
  return (
    <div className="space-y-2.5">
      <AutonomousNotice d={d} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        <Stat label="Sections model" value={m?.probability != null ? pct(m.probability) : '—'} delta={`raw ${pct(sx.probability_raw)} · calibrated on its own record`} />
        <Stat label="Walk-forward skill" value={skillText(m?.record?.skill_vs_base_rate)} tone={(m?.record?.skill_vs_base_rate ?? 0) > 0 ? 'good' : 'warn'} delta={m?.gate ? 'promotion gate: ' + m.gate : 'shadow challenger'} />
        <Stat label="Inputs" value={sx.inputs_total} delta={`${sx.sections.filter((r: any) => r.available).length} of ${sx.sections.length} sections reading now`} />
        <Stat label="Gate" value={sx.method === 'gate' ? 'Track record' : 'Anchor only'} delta={sx.method === 'gate' ? 'weights from each section\'s earlier out-of-sample skill' : 'not enough history for the gate yet'} />
      </div>
      <Panel title={`Situation now · ${sx.as_of}`} sub="Point-in-time rules. In each situation the gate weights the sections by how they did in earlier months with the same situation (shrunk towards their overall record when a situation is rare).">
        <div className="flex flex-wrap gap-1.5">{sx.situation.map((s: any) => <span key={s.key} className="ml-pill" data-tone={s.on ? 'warn' : undefined}>{s.on ? '● ' : '○ '}{s.label}</span>)}</div>
        <p className="text-2xs text-text-tertiary mt-2">{on.length ? `${on.length} situation${on.length > 1 ? 's' : ''} active — the weights reflect the sections' record in such months.` : 'No situation active — the weights reflect each section\'s overall record.'}</p>
      </Panel>
      <div className="ml-grid-12">
        <div style={span(6)} className="ml-span-6"><Panel title="Who the model trusts now" sub="Each section's weight in today's forecast; the label is what that section alone says. Grey = no reading (too few of its inputs this month).">
          <EChart option={weightOpt} height={Math.max(220, rows.length * 28)} ariaLabel="Section weights now" /></Panel></div>
        <div style={span(6)} className="ml-span-6"><Panel title="What moved the forecast" sub="Each section's contribution to the combined log-odds (weight × its log-odds). Red raises the probability, green lowers it.">
          <EChart option={contribOpt} height={Math.max(220, rows.length * 28)} ariaLabel="Section contributions" /></Panel></div>
      </div>
      <Panel title="Sections and their records" sub="Every section's own out-of-sample record, refit each January on answers known then. A section with a weak record gets little or no weight.">
        <DataGrid data={sx.sections} columns={cols} initialSort={[{ id: 'weight_now', desc: true }]} filterPlaceholder="Filter sections…" />
      </Panel>
      <p className="text-2xs text-text-tertiary">Sections model: a challenger like the others — logged and scored monthly, and served only after the promotion gate and a PM or risk approval. Monthly macro samples are short; more inputs do not by themselves mean more accuracy, which is why its weights come from each section's earlier out-of-sample record rather than a fitted combination.</p>
    </div>
  );
}

function Workbench({ stream }: { stream: ReturnType<typeof useNeuralStream> }) {
  const tab = useMlTab();
  const tasksQ = useTasksQ();
  const sel = useMlTask();
  const taskQ = useTaskQ(sel);
  const [period, setPeriod] = useState<'all' | '2000' | '2013'>('all');
  const { picked, toggle } = usePicked();
  const models = taskQ.data?.available ? MODEL_ORDER.filter((m) => taskQ.data.models?.[m]) : [];
  const hist = useHistoryQ(sel, tab === 'lab' && !!taskQ.data?.available);
  const exportCsv = tab === 'lab' && hist.data ? () => {
    const h = hist.data; const ks = Object.keys(h.models);
    const csv = ['month,outcome,' + ks.join(','), ...h.months.map((m: string, i: number) => [m, h.outcome[i], ...ks.map((k) => h.models[k][i])].join(','))].join('\n');
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = `${sel}_walk_forward.csv`; a.click(); URL.revokeObjectURL(a.href);
  } : undefined;
  return (
    <div className="ml-shell">
      <Toolbar tasks={tasksQ.data} period={period} setPeriod={setPeriod} picked={picked} toggle={toggle} models={models} onExport={exportCsv} stream={stream} />
      <nav className="ml-tabs" role="tablist" aria-label="Machine learning">
        {ML_TABS.map((x) => <button key={x.id} role="tab" aria-selected={tab === x.id} onClick={() => setMlTab(x.id)}>{x.label}</button>)}
      </nav>
      {tasksQ.isError && <div className="ml-panel"><div className="ml-panel-body text-xs text-amber">Could not reach the ML engine — {(tasksQ.error as Error).message}. Retrying…</div></div>}
      {tab === 'overview' && <Overview tasks={tasksQ.data} />}
      {tab === 'lab' && <ModelLab period={period} picked={picked} />}
      {tab === 'sections' && <Sections />}
      {tab === 'visualizer' && <Visualizer />}
      {tab === 'explain' && <Explain />}
      {tab === 'monitoring' && <Monitoring />}
      {tab === 'registry' && <Registry />}
      {tab === 'knowledge' && <Knowledge />}
      {tab === 'method' && <Method />}
    </div>
  );
}

export function MlPage() {
  // Mount the push transport for the whole workbench. The backend samples a topic only while a
  // socket is subscribed, so this is what turns the stream on. All four observability panels now
  // read it, and each one's poll resumes automatically if the socket drops or its producer fails.
  const { token } = useAuth();
  const stream = useNeuralStream({ token });
  return <QueryClientProvider client={mlQueryClient}><Workbench stream={stream} /></QueryClientProvider>;
}

export default MlPage;

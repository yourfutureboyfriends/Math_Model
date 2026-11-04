/**
 * Time machine — scrub or play through the macro model's history and see what it said at the time: where growth and
 * inflation stood (as estimated with the data available then, not today's revised history), the regime
 * probabilities, the portfolio it chose — and, marked as hindsight, the regime that followed and the next 12
 * months' returns against 60/40. Reads the walk-forward backtest's timeline (api/model/backtest.py), so scrubbing
 * is instant.
 *
 * The history ribbon shows the regime the model called each month with the growth and inflation paths over it; drag
 * or click anywhere on it to travel, or use the arrow keys.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { EChart, alpha, axisStyle, color, useChartTheme, type ECharts } from '@/components/charts/EChart';
import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import { cn } from '@/lib/utils';

type Row = {
  decided: string; month: string; growth: number; inflation: number; probs: Record<string, number>; top: string;
  p_g: number; p_i: number; weights: Record<string, number>; cash: number; realised?: string | null;
  next_12m?: { model: number | null; strategic: number | null; sixty_forty: number | null };
  live?: boolean;                                         // the current decision: latest data, no hindsight yet
};

// Regime colours: the macro page's validated categorical slots, fixed per regime (never by rank).
const REGIMES: { name: string; color: string; corner: [number, number] }[] = [
  { name: 'Goldilocks', color: '#199e70', corner: [1, -1] },
  { name: 'Reflation', color: '#c98500', corner: [1, 1] },
  { name: 'Stagflation', color: '#d95926', corner: [-1, 1] },
  { name: 'Deflationary slowdown', color: '#3987e5', corner: [-1, -1] },
];
const COLOR: Record<string, string> = Object.fromEntries(REGIMES.map((r) => [r.name, r.color]));
const colorOf = (q?: string | null) => (q && COLOR[q]) || 'rgb(var(--c-text-tertiary))';
const JUMPS: [string, string][] = [['2000-10', 'Dot-com bust'], ['2008-09', 'Lehman'], ['2020-03', 'Covid crash'], ['2022-06', 'Inflation peak']];
const pct = (v?: number | null, d = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const sig = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}σ`;
const monthName = (m: string) => new Date(`${m}-15`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
const shortMonth = (m: string) => new Date(`${m}-15`).toLocaleDateString(undefined, { month: 'short', year: '2-digit' });

// ── History ribbon: regime called each month, growth and inflation paths, events, draggable playhead (ECharts) ──
function HistoryRibbon({ rows, i, onPick }: { rows: Row[]; i: number; onPick: (k: number) => void }) {
  const t = useChartTheme();
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const lim = useMemo(() => {                              // 98th percentile, so one spike (Covid) doesn't flatten the rest
    const a = rows.flatMap((r) => [Math.abs(r.growth), Math.abs(r.inflation)]).sort((p, q) => p - q);
    return Math.max(1.25, a[Math.floor(a.length * 0.98)] ?? 1.5);
  }, [rows]);
  const option = useMemo(() => {
    const ax = axisStyle(t);
    const months = rows.map((r) => r.month);
    const clip = (v: number) => Math.max(-lim, Math.min(lim, v));
    const growthC = color('rgb(var(--c-text-primary))', t.textStrong), inflC = color('rgb(var(--c-bloomberg))', t.accent);
    const events = JUMPS.map(([m, label]) => ({ m, label, k: rows.findIndex((x) => x.month >= m) })).filter((e) => e.k >= 0 && rows[0].month <= e.m)
      .map((e, n) => ({ xAxis: e.k, label: { formatter: e.label, distance: n % 2 ? 12 : 2 } }));       // alternate heights so neighbours never touch
    const guides = [-1, 0, 1].filter((v) => Math.abs(v) < lim).map((v) => ({ yAxis: v, lineStyle: { color: t.border, opacity: v ? 0.6 : 1, type: v ? 'dashed' : 'solid' },
      label: { show: v !== 0, position: 'insideStartTop', formatter: `${v > 0 ? '+' : '−'}1σ`, color: t.mutedText, fontSize: 9 } }));
    const cur = rows[i];
    return {
      animation: false, legend: { show: false }, toolbox: { show: false },
      tooltip: { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.mutedText, type: 'dashed' } },
        formatter: (ps: any[]) => { const r = rows[ps[0].dataIndex]; return `<b>${monthName(r.month)}</b><br/>Regime called: <b style="color:${color(colorOf(r.top))}">${r.top}</b><br/>Growth ${sig(r.growth)} · Inflation ${sig(r.inflation)}<br/><span style="opacity:.6">click or drag to travel</span>`; } },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      grid: [{ left: 8, right: 8, top: 30, bottom: 44 }, { left: 8, right: 8, height: 14, bottom: 22 }],
      xAxis: [{ type: 'category', data: months, gridIndex: 0, boundaryGap: false, show: false },
        { type: 'category', data: months, gridIndex: 1, boundaryGap: true, ...ax, axisLine: { show: false }, splitLine: { show: false },
          axisLabel: { ...ax.axisLabel, fontFamily: t.mono, interval: (k: number) => months[k].endsWith('-01') && Number(months[k].slice(0, 4)) % (rows.length > 240 ? 5 : 2) === 0, formatter: (m: string) => m.slice(0, 4) } }],
      yAxis: [{ type: 'value', gridIndex: 0, min: -lim, max: lim, show: false },
        { type: 'value', gridIndex: 1, show: false, max: 1 }],
      series: [
        { name: 'Growth', type: 'line', data: rows.map((r) => clip(r.growth)), showSymbol: false, lineStyle: { width: 1.6, color: growthC, opacity: 0.85 }, itemStyle: { color: growthC },
          markLine: { symbol: 'none', silent: true, lineStyle: { color: t.mutedText, type: [2, 3] }, label: { position: 'end', color: t.mutedText, fontSize: 9.5 }, data: [...events, ...guides] } },
        { name: 'Inflation', type: 'line', data: rows.map((r) => clip(r.inflation)), showSymbol: false, lineStyle: { width: 1.6, color: inflC }, itemStyle: { color: inflC },
          markLine: { symbol: 'none', silent: true, animation: false, lineStyle: { color: t.textStrong, width: 1.5, type: 'solid' }, label: { show: false }, data: [{ xAxis: i }] },
          markPoint: { symbol: 'circle', symbolSize: 8, silent: true, label: { show: false }, data: [{ coord: [i, clip(cur.inflation)], itemStyle: { color: inflC, borderColor: t.surface1, borderWidth: 2 } }] } },
        { name: 'Regime', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barCategoryGap: 0, silent: true,
          data: rows.map((r, k) => ({ value: 1, itemStyle: { color: color(colorOf(r.top)), opacity: k === i ? 1 : 0.62 } })) },
      ],
    };
  }, [rows, i, lim, t]);
  const onReady = (c: ECharts) => {
    let down = false;
    const pick = (x: number) => {
      const k = c.convertFromPixel({ xAxisIndex: 1 }, x) as unknown;    // pixel along the axis → month index
      const idx = Array.isArray(k) ? k[0] : k;
      if (typeof idx === 'number' && Number.isFinite(idx)) pickRef.current(Math.max(0, Math.min(rows.length - 1, Math.round(idx))));
    };
    const zr = c.getZr();
    zr.on('mousedown', (e: any) => { down = true; pick(e.offsetX); });
    zr.on('mousemove', (e: any) => { if (down) pick(e.offsetX); });
    zr.on('mouseup', () => { down = false; });
    zr.on('globalout', () => { down = false; });
  };
  return <div className="tm-ribbon select-none cursor-ew-resize"><EChart option={option} height={150} onReady={onReady} ariaLabel="Regime history: growth and inflation with the regime called each month" /></div>;
}

// ── Quadrant map: growth × inflation with regime tints, σ guides, a fading trail and the current point (ECharts) ──
function QuadrantMap({ rows, i }: { rows: Row[]; i: number }) {
  const t = useChartTheme();
  const option = useMemo(() => {
    const trail = rows.slice(Math.max(0, i - 11), i + 1);
    // zoom to the last year's path (never tighter than ±1σ, never wider than ±3σ), in half-σ steps
    const lim = Math.min(3, Math.max(1, Math.ceil(Math.max(...trail.flatMap((r) => [Math.abs(r.growth), Math.abs(r.inflation)])) * 1.35 * 2) / 2));
    const clip = (v: number) => Math.max(-lim, Math.min(lim, v));
    const cur = rows[i], probs = cur.probs ?? {};
    const ax = axisStyle(t);
    const accent = color('rgb(var(--c-bloomberg))', t.accent), curC = color(colorOf(cur.top));
    const quads = REGIMES.map((q) => {
      const [gs, is] = q.corner, on = cur.top === q.name;
      return [{ coord: [gs > 0 ? 0 : -lim, is > 0 ? lim : 0], itemStyle: { color: alpha(q.color, on ? 0.13 : 0.04) },
        label: { show: true, position: gs > 0 ? (is > 0 ? 'insideTopRight' : 'insideBottomRight') : (is > 0 ? 'insideTopLeft' : 'insideBottomLeft'),
          formatter: `${q.name === 'Deflationary slowdown' ? 'Slowdown' : q.name} ${Math.round((probs[q.name] ?? 0) * 100)}%`,
          color: on ? q.color : t.mutedText, fontWeight: on ? 600 : 400, fontSize: 10.5 } },
        { coord: [gs > 0 ? lim : 0, is > 0 ? 0 : -lim] }];
    });
    const axis = (name: string) => ({ type: 'value', min: -lim, max: lim, interval: lim <= 1.5 ? 0.5 : 1, name, nameLocation: 'end', nameGap: 6, ...ax,
      axisLine: { show: false, onZero: false }, splitLine: { lineStyle: { color: t.border, opacity: 0.5 } }, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => (v > 0 ? `+${v}` : `${v}`) } });
    return {
      animationDurationUpdate: 250, legend: { show: false }, toolbox: { show: false },
      tooltip: { trigger: 'item', formatter: (p: any) => { const r = trail[p.dataIndex]; return r ? `<b>${monthName(r.month)}</b><br/>${r.top}<br/>growth ${sig(r.growth)} · inflation ${sig(r.inflation)}` : ''; } },
      grid: { left: 34, right: 14, top: 14, bottom: 30 },
      xAxis: { ...axis('growth (σ)'), nameLocation: 'end', nameTextStyle: { ...ax.nameTextStyle, padding: [22, 0, 0, 0], align: 'right', verticalAlign: 'top' } },
      yAxis: { ...axis('inflation (σ)'), nameTextStyle: { ...ax.nameTextStyle, align: 'left' } },
      series: [
        { type: 'line', data: trail.map((r) => [clip(r.growth), clip(r.inflation)]), smooth: 0.35, showSymbol: false, silent: true, z: 2,
          lineStyle: { width: 2, color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: alpha(accent, 0.05) }, { offset: 1, color: alpha(accent, 0.9) }] } },
          markArea: { silent: true, data: quads },
          markLine: { symbol: 'none', silent: true, lineStyle: { color: t.borderStrong, type: 'solid' }, label: { show: false }, data: [{ xAxis: 0 }, { yAxis: 0 }] } },
        { type: 'scatter', z: 3, data: trail.map((r, k) => ({ value: [clip(r.growth), clip(r.inflation)],
          symbolSize: k === trail.length - 1 ? 12 : 5,
          itemStyle: k === trail.length - 1
            ? { color: curC, borderColor: t.surface1, borderWidth: 2.5, shadowBlur: 16, shadowColor: alpha(curC, 0.7) }
            : { color: color(colorOf(r.top)), opacity: 0.25 + (0.6 * k) / trail.length } })) },
      ],
    };
  }, [rows, i, t]);
  const cur = rows[i];
  return <EChart option={option} height={270} ariaLabel={`Growth ${sig(cur.growth)}, inflation ${sig(cur.inflation)}; regime ${cur.top}`} />;
}

function Card({ title, children, className }: { title: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('tm-card', className)}>
      <div className="tm-card-title">{title}</div>
      {children}
    </div>
  );
}

export function TimeMachine({ timeline, sixtyForty }: { timeline?: Row[]; sixtyForty?: { equity: string; bonds: string } }) {
  const rows = useMemo(() => timeline ?? [], [timeline]);
  const [i, setI] = useState(() => Math.max(0, rows.length - 1));
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval>>();
  useEffect(() => { setI(Math.max(0, rows.length - 1)); setPlaying(false); }, [rows]);
  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => setI((k) => {
      if (k >= rows.length - 1) { setPlaying(false); return k; }
      return k + 1;
    }), 260);
    return () => clearInterval(timer.current);
  }, [playing, rows.length]);
  const go = useCallback((k: number) => { setPlaying(false); setI(Math.max(0, Math.min(rows.length - 1, k))); }, [rows.length]);

  if (!rows.length) {
    return <div className="text-2xs text-text-tertiary">The timeline appears after the model's next full run (a saved result from before this feature has none) — refresh in a minute.</div>;
  }
  const idx = Math.min(i, rows.length - 1);                 // a shorter timeline arrives a render before the index resets
  const r = rows[idx];
  const prev = idx > 0 ? rows[idx - 1] : null;
  const probs = REGIMES.map((q) => [q.name, r.probs?.[q.name] ?? 0] as [string, number]);
  const weights = Object.entries(r.weights).filter(([, w]) => w > 0).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const maxW = Math.max(0.01, ...weights.map(([, w]) => w));
  const jump = (m: string) => { const k = rows.findIndex((x) => x.month >= m); if (k >= 0) go(k); };
  const n = r.next_12m;
  const called = r.realised ? r.realised === r.top : null;
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); go(idx - (e.shiftKey ? 12 : 1)); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); go(idx + (e.shiftKey ? 12 : 1)); }
    else if (e.key === 'Home') { e.preventDefault(); go(0); }
    else if (e.key === 'End') { e.preventDefault(); go(rows.length - 1); }
    else if (e.key === ' ') { e.preventDefault(); if (idx >= rows.length - 1) setI(0); setPlaying((v) => !v); }
  };
  const ret = (label: string, v: number | null | undefined, title?: string) => {
    const scale = Math.max(0.05, ...[n?.model, n?.strategic, n?.sixty_forty].map((x) => Math.abs(x ?? 0)));
    return (
      <div className="tm-ret" title={title}>
        <div className="flex justify-between text-[10.5px]"><span className="text-text-secondary">{label}</span>
          <span className={cn('font-mono font-semibold', v == null ? 'text-text-tertiary' : v >= 0 ? 'text-green' : 'text-red')}>{pct(v)}</span></div>
        <div className="tm-ret-track"><span className={cn('tm-ret-bar', (v ?? 0) >= 0 ? 'pos' : 'neg')}
          style={{ width: `${(Math.abs(v ?? 0) / scale) * 50}%`, [(v ?? 0) >= 0 ? 'left' : 'right']: '50%' } as React.CSSProperties} /></div>
      </div>
    );
  };

  return (
    <div className="tm-root" tabIndex={0} onKeyDown={onKey} aria-label="Time machine: arrow keys move a month, shift+arrow a year, space plays">
      {/* header: date, transport, regime pill, events */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <div className="min-w-[11rem]">
          <div className="text-[10px] uppercase tracking-[0.08em] text-text-tertiary">{r.live ? 'Current decision for' : 'Positioned for'}</div>
          <div className="text-lg font-semibold text-text-primary leading-tight tabular-nums">{monthName(r.month)}</div>
          <div className="text-[10px] text-text-tertiary">with data to the end of {monthName(r.decided)}{r.live && <span className="tm-live">Live</span>}</div>
        </div>
        <div className="tm-transport">
          <button type="button" aria-label="Previous month" onClick={() => go(idx - 1)}><SkipBack className="w-3.5 h-3.5" /></button>
          <button type="button" className="tm-play" aria-label={playing ? 'Pause' : 'Play'} onClick={() => { if (idx >= rows.length - 1) setI(0); setPlaying((v) => !v); }}>
            {playing ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}</button>
          <button type="button" aria-label="Next month" onClick={() => go(idx + 1)}><SkipForward className="w-3.5 h-3.5" /></button>
        </div>
        <span className="tm-pill" style={{ ['--tm' as string]: colorOf(r.top) }}>
          <span className="tm-dot" />{r.top}<span className="font-mono opacity-80">{Math.round((r.probs?.[r.top] ?? 0) * 100)}%</span>
        </span>
        <div className="flex flex-wrap gap-1 ml-auto">
          {JUMPS.filter(([m]) => m >= rows[0].month && m <= rows[rows.length - 1].month).map(([m, label]) => (
            <button key={m} type="button" onClick={() => jump(m)} className={cn('tm-chip', r.month === m && 'on')}>{label}</button>
          ))}
          <button type="button" onClick={() => go(rows.length - 1)} className={cn('tm-chip', idx === rows.length - 1 && 'on')}>Today</button>
        </div>
      </div>

      <HistoryRibbon rows={rows} i={idx} onPick={go} />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5 mb-3 text-[10px] text-text-tertiary">
        <span className="inline-flex items-center gap-1.5"><span className="tm-swatch line" style={{ background: 'rgb(var(--c-text-primary))' }} />Growth</span>
        <span className="inline-flex items-center gap-1.5"><span className="tm-swatch line" style={{ background: 'rgb(var(--c-bloomberg))' }} />Inflation</span>
        <span className="text-text-tertiary">·</span>
        {REGIMES.map((q) => <span key={q.name} className="inline-flex items-center gap-1.5"><span className="tm-swatch" style={{ background: q.color }} />{q.name}</span>)}
        <span className="ml-auto">{shortMonth(rows[0].month)} – {shortMonth(rows[rows.length - 1].month)} · drag, click or use ← → (shift: a year)</span>
      </div>
      <input type="range" min={0} max={rows.length - 1} value={idx} onChange={(e) => go(Number(e.target.value))} aria-label="Month" className="sr-only" />

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3">
        <Card title={<>Growth × inflation <span className="text-text-tertiary font-normal">— as the model saw it then, last 12 months</span></>}>
          <QuadrantMap rows={rows} i={idx} />
          <div className="flex justify-between text-[10.5px] font-mono text-text-secondary mt-1">
            <span>growth {sig(r.growth)}{prev && <span className={cn('ml-1', r.growth - prev.growth >= 0 ? 'text-green' : 'text-red')}>{r.growth - prev.growth >= 0 ? '▲' : '▼'}</span>}</span>
            <span>inflation {sig(r.inflation)}{prev && <span className={cn('ml-1', r.inflation - prev.inflation >= 0 ? 'text-red' : 'text-green')}>{r.inflation - prev.inflation >= 0 ? '▲' : '▼'}</span>}</span>
          </div>
        </Card>

        <Card title={`Regime probabilities — ${monthName(r.month)}`}>
          <div className="tm-stack" role="img" aria-label={probs.map(([q, v]) => `${q} ${Math.round(v * 100)}%`).join(', ')}>
            {probs.map(([q, v]) => <span key={q} style={{ width: `${v * 100}%`, background: COLOR[q] }} title={`${q} ${Math.round(v * 100)}%`} />)}
          </div>
          <div className="space-y-2 mt-3">
            {[...probs].sort((a, b) => b[1] - a[1]).map(([q, v]) => {
              const d = prev ? v - (prev.probs?.[q] ?? 0) : null;
              return (
                <div key={q}>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className={cn('inline-flex items-center gap-1.5', q === r.top ? 'text-text-primary font-medium' : 'text-text-secondary')}>
                      <span className="tm-swatch" style={{ background: COLOR[q] }} />{q}</span>
                    <span className="font-mono text-text-primary">{Math.round(v * 100)}%
                      {d != null && Math.abs(d) >= 0.01 && <span className={cn('ml-1.5 text-[10px]', d > 0 ? 'text-green' : 'text-red')}>{d > 0 ? '+' : ''}{Math.round(d * 100)}</span>}</span>
                  </div>
                  <div className="tm-track"><span style={{ width: `${v * 100}%`, background: COLOR[q] }} /></div>
                </div>
              );
            })}
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            <div className="tm-mini"><span>P(growth ↑)</span><b>{Math.round(r.p_g * 100)}%</b></div>
            <div className="tm-mini"><span>P(inflation ↑)</span><b>{Math.round(r.p_i * 100)}%</b></div>
          </div>
          {r.realised && (
            <div className={cn('tm-hindsight mt-2', called ? 'ok' : 'miss')} title="Hindsight: from the factors as they are known today">
              <span className="italic text-text-tertiary">What followed</span>
              <span className="inline-flex items-center gap-1.5 font-medium"><span className="tm-swatch" style={{ background: colorOf(r.realised) }} />{r.realised}</span>
              <span className={cn('ml-auto text-[10px] font-semibold', called ? 'text-green' : 'text-amber')}>{called ? 'Called correctly' : 'Missed'}</span>
            </div>
          )}
        </Card>

        <Card title="Tactical portfolio chosen">
          <div className="space-y-1.5">
            {weights.map(([a, w]) => {
              const d = prev ? w - (prev.weights?.[a] ?? 0) : null;
              return (
                <div key={a} className="grid grid-cols-[minmax(0,1fr)_minmax(60px,90px)_38px_30px] items-center gap-2 text-[11px]">
                  <span className="truncate text-text-secondary" title={a}>{a}</span>
                  <span className="tm-track"><span style={{ width: `${(w / maxW) * 100}%` }} className="tm-weight" /></span>
                  <span className="text-right font-mono text-text-primary">{Math.round(w * 100)}%</span>
                  <span className={cn('text-right font-mono text-[10px]', d == null || Math.abs(d) < 0.005 ? 'text-text-tertiary' : d > 0 ? 'text-green' : 'text-red')}>
                    {d == null || Math.abs(d) < 0.005 ? '·' : `${d > 0 ? '+' : ''}${Math.round(d * 100)}`}</span>
                </div>
              );
            })}
            {r.cash > 0.005 && <div className="text-[10.5px] text-text-tertiary pt-0.5">Cash {Math.round(r.cash * 100)}%</div>}
          </div>
          <div className="mt-3 pt-2.5 border-t border-border-subtle" title="Hindsight: realised returns over the following 12 months, net of costs">
            <div className="text-[10px] uppercase tracking-[0.06em] text-text-tertiary mb-1.5">Next 12 months <span className="normal-case italic tracking-normal">(hindsight)</span></div>
            {n && (n.model != null || n.sixty_forty != null) ? (
              <div className="space-y-1.5">
                {ret('Tactical', n.model)}
                {ret('Strategic', n.strategic)}
                {ret('60/40', n.sixty_forty, sixtyForty ? `${sixtyForty.equity} / ${sixtyForty.bonds}` : undefined)}
              </div>
            ) : <div className="text-[10.5px] text-text-tertiary">{r.live ? 'The current decision — no hindsight yet.' : 'Not 12 months yet.'}</div>}
          </div>
        </Card>
      </div>
      <div className="mt-2.5 text-[10px] text-text-tertiary leading-relaxed">
        Factors, probabilities and weights are what the model computed with the data available at the end of {monthName(r.decided)} —
        no look-ahead. Hindsight figures are marked in italics. Returns are excess over cash, as in the backtest. Changes are against the month before.
      </div>
    </div>
  );
}

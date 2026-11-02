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
import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import { cn } from '@/lib/utils';

type Row = {
  decided: string; month: string; growth: number; inflation: number; probs: Record<string, number>; top: string;
  p_g: number; p_i: number; weights: Record<string, number>; cash: number; realised?: string | null;
  next_12m?: { model: number | null; strategic: number | null; sixty_forty: number | null };
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

/** Width of an element in real pixels, so SVG text is drawn at its true size instead of being scaled. */
function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.clientWidth);
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

// ── History ribbon: regime called each month, growth and inflation paths, events, draggable playhead ──
function HistoryRibbon({ rows, i, onPick }: { rows: Row[]; i: number; onPick: (k: number) => void }) {
  const [ref, W] = useWidth<HTMLDivElement>();
  const H = 150, band = 16, top = 24, L = 4, R = 4;
  const plotH = H - top - band - 22;
  const n = rows.length;
  const dragging = useRef(false);
  const sx = useCallback((k: number) => L + (n <= 1 ? 0 : (k / (n - 1)) * (Math.max(W, 1) - L - R)), [W, n]);
  const lim = useMemo(() => {                              // 98th percentile, so one spike (Covid) doesn't flatten the rest
    const a = rows.flatMap((r) => [Math.abs(r.growth), Math.abs(r.inflation)]).sort((p, q) => p - q);
    return Math.max(1.25, a[Math.floor(a.length * 0.98)] ?? 1.5);
  }, [rows]);
  const sy = (v: number) => top + plotH / 2 - (Math.max(-lim, Math.min(lim, v)) / lim) * (plotH / 2);
  const path = (key: 'growth' | 'inflation') => rows.map((r, k) => `${k ? 'L' : 'M'}${sx(k).toFixed(1)},${sy(r[key]).toFixed(1)}`).join('');
  const pick = (clientX: number) => {
    const el = ref.current;
    if (!el || n < 2) return;
    const x = clientX - el.getBoundingClientRect().left;
    onPick(Math.max(0, Math.min(n - 1, Math.round(((x - L) / (W - L - R)) * (n - 1)))));
  };
  // year ticks: every k-th January so labels never crowd
  const years = rows.map((r, k) => ({ k, m: r.month })).filter((x) => x.m.endsWith('-01'));
  const every = Math.max(1, Math.ceil(years.length / Math.max(1, Math.floor(W / 60))));
  const r = rows[i];
  return (
    <div ref={ref} className="tm-ribbon relative select-none" style={{ height: H }}
      onPointerDown={(e) => { dragging.current = true; (e.target as Element).setPointerCapture?.(e.pointerId); pick(e.clientX); }}
      onPointerMove={(e) => { if (dragging.current) pick(e.clientX); }}
      onPointerUp={() => { dragging.current = false; }} onPointerCancel={() => { dragging.current = false; }}>
      {W > 0 && (
        <svg width={W} height={H} className="block" aria-hidden>
          {/* zero line and ±1σ guides for the factor paths */}
          {[-1, 0, 1].map((v) => (
            <line key={v} x1={L} x2={W - R} y1={sy(v)} y2={sy(v)} stroke="var(--border)" strokeOpacity={v === 0 ? 0.7 : 0.3} />
          ))}
          <text x={L + 2} y={sy(1) - 3} fontSize={9} fill="var(--text-tertiary)">+1σ</text>
          <text x={L + 2} y={sy(-1) + 10} fontSize={9} fill="var(--text-tertiary)">−1σ</text>
          {/* events */}
          {(() => {
            // events: a label that would touch the previous one drops to a second line
            let lastEnd = -Infinity, row = 0;
            return JUMPS.map(([m, label]) => {
              const k = rows.findIndex((x) => x.month >= m);
              if (k < 0 || rows[0].month > m) return null;
              const w = label.length * 5.4, anchor = sx(k) > W - w / 2 - 4 ? 'end' : sx(k) < w / 2 + 4 ? 'start' : 'middle';
              const start = anchor === 'end' ? sx(k) - w : anchor === 'start' ? sx(k) : sx(k) - w / 2;
              row = start < lastEnd + 6 ? 1 - row : 0;
              lastEnd = start + w;
              return (
                <g key={m}>
                  <line x1={sx(k)} x2={sx(k)} y1={row ? top + 4 : top - 4} y2={H - band - 20} stroke="var(--text-tertiary)" strokeOpacity={0.35} strokeDasharray="2 3" />
                  <text x={sx(k) + (anchor === 'start' ? 3 : anchor === 'end' ? -3 : 0)} y={row ? top + 2 : top - 8} textAnchor={anchor} fontSize={9.5}
                    fill="var(--text-tertiary)" paintOrder="stroke" stroke="var(--surface-1)" strokeWidth={3}>{label}</text>
                </g>
              );
            });
          })()}
          <path d={path('growth')} fill="none" stroke="rgb(var(--c-text-primary))" strokeOpacity={0.85} strokeWidth={1.6} strokeLinejoin="round" />
          <path d={path('inflation')} fill="none" stroke="rgb(var(--c-bloomberg))" strokeWidth={1.6} strokeLinejoin="round" />
          {/* regime band: one cell per month, coloured by the regime the model called */}
          {rows.map((x, k) => {
            const w = Math.max(1, sx(1) - sx(0) + 0.6);
            return <rect key={x.month} x={sx(k) - w / 2} y={H - band - 18} width={w} height={band} fill={colorOf(x.top)} fillOpacity={k === i ? 1 : 0.62} />;
          })}
          {years.filter((_, k) => k % every === 0).map(({ k, m }) => (
            <text key={m} x={sx(k)} y={H - 4} textAnchor="middle" fontSize={9.5} fill="var(--text-tertiary)" className="font-mono">{m.slice(0, 4)}</text>
          ))}
          {/* playhead */}
          <line x1={sx(i)} x2={sx(i)} y1={top - 2} y2={H - 18} stroke="rgb(var(--c-text-primary))" strokeWidth={1.5} />
          <circle cx={sx(i)} cy={sy(r.growth)} r={3.5} fill="rgb(var(--c-text-primary))" stroke="var(--surface-1)" strokeWidth={2} />
          <circle cx={sx(i)} cy={sy(r.inflation)} r={3.5} fill="rgb(var(--c-bloomberg))" stroke="var(--surface-1)" strokeWidth={2} />
          <rect x={sx(i) - 5} y={H - band - 22} width={10} height={band + 8} rx={3} fill="none" stroke="rgb(var(--c-text-primary))" strokeWidth={1.5} />
        </svg>
      )}
    </div>
  );
}

// ── Quadrant map: growth × inflation with regime tints, σ guides, a fading trail and the current point ──
function QuadrantMap({ rows, i }: { rows: Row[]; i: number }) {
  const [ref, W] = useWidth<HTMLDivElement>();
  const H = Math.max(220, Math.min(300, W * 0.82));
  const pad = { l: 30, r: 10, t: 10, b: 26 };
  const trailRows = rows.slice(Math.max(0, i - 11), i + 1);
  // zoom to the last year's path (never tighter than ±1σ, never wider than ±3σ), in half-σ steps
  const lim = Math.min(3, Math.max(1, Math.ceil(Math.max(...trailRows.flatMap((r) => [Math.abs(r.growth), Math.abs(r.inflation)])) * 1.35 * 2) / 2));
  const guides = (lim <= 1.5 ? [-1, -0.5, 0.5, 1] : lim <= 2 ? [-2, -1, 1, 2] : [-3, -2, -1, 1, 2, 3]).filter((v) => Math.abs(v) <= lim);
  const x = (g: number) => pad.l + ((Math.max(-lim, Math.min(lim, g)) + lim) / (2 * lim)) * (W - pad.l - pad.r);
  const y = (v: number) => H - pad.b - ((Math.max(-lim, Math.min(lim, v)) + lim) / (2 * lim)) * (H - pad.t - pad.b);
  const trail = trailRows;
  const cur = rows[i];
  const probs = cur.probs ?? {};
  // smooth trail through the points (Catmull-Rom → cubic Bézier)
  const pts = trail.map((r) => [x(r.growth), y(r.inflation)]);
  const smooth = pts.length < 2 ? '' : pts.reduce((d, p, k) => {
    if (!k) return `M${p[0]},${p[1]}`;
    const p0 = pts[k - 2] ?? pts[k - 1], p1 = pts[k - 1], p3 = pts[k + 1] ?? p;
    const c1 = [p1[0] + (p[0] - p0[0]) / 6, p1[1] + (p[1] - p0[1]) / 6], c2 = [p[0] - (p3[0] - p1[0]) / 6, p[1] - (p3[1] - p1[1]) / 6];
    return `${d} C${c1[0].toFixed(1)},${c1[1].toFixed(1)} ${c2[0].toFixed(1)},${c2[1].toFixed(1)} ${p[0].toFixed(1)},${p[1].toFixed(1)}`;
  }, '');
  const cx = x(cur.growth), cy = y(cur.inflation);
  return (
    <div ref={ref} className="w-full">
      {W > 0 && (
        <svg width={W} height={H} className="block" role="img" aria-label={`Growth ${sig(cur.growth)}, inflation ${sig(cur.inflation)}; regime ${cur.top}`}>
          <defs>
            <linearGradient id="tm-trail" x1="0" x2="1"><stop offset="0%" stopColor="rgb(var(--c-bloomberg))" stopOpacity={0.05} /><stop offset="100%" stopColor="rgb(var(--c-bloomberg))" stopOpacity={0.9} /></linearGradient>
            <radialGradient id="tm-halo"><stop offset="0%" stopColor={colorOf(cur.top)} stopOpacity={0.45} /><stop offset="100%" stopColor={colorOf(cur.top)} stopOpacity={0} /></radialGradient>
          </defs>
          {/* regime quadrants, the called one stronger */}
          {REGIMES.map((q) => {
            const [gs, is] = q.corner;
            const x0 = gs > 0 ? x(0) : pad.l, y0 = is > 0 ? pad.t : y(0);
            const on = cur.top === q.name;
            return (
              <g key={q.name}>
                <rect x={x0} y={y0} width={gs > 0 ? W - pad.r - x(0) : x(0) - pad.l} height={is > 0 ? y(0) - pad.t : H - pad.b - y(0)}
                  fill={q.color} fillOpacity={on ? 0.13 : 0.04} rx={2} />
                <text x={gs > 0 ? W - pad.r - 6 : pad.l + 6} y={is > 0 ? pad.t + 14 : H - pad.b - 8} textAnchor={gs > 0 ? 'end' : 'start'}
                  fontSize={10.5} fontWeight={on ? 600 : 400} fill={on ? q.color : 'var(--text-tertiary)'}>
                  {q.name === 'Deflationary slowdown' ? 'Slowdown' : q.name} <tspan className="font-mono" fontWeight={500}>{Math.round((probs[q.name] ?? 0) * 100)}%</tspan>
                </text>
              </g>
            );
          })}
          {/* σ guides */}
          {guides.map((v) => (
            <g key={v}>
              <line x1={x(v)} x2={x(v)} y1={pad.t} y2={H - pad.b} stroke="var(--border)" strokeOpacity={0.28} />
              <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeOpacity={0.28} />
              <text x={x(v)} y={H - pad.b + 12} textAnchor="middle" fontSize={9} fill="var(--text-tertiary)" className="font-mono">{v > 0 ? `+${v}` : v}</text>
              <text x={pad.l - 5} y={y(v) + 3} textAnchor="end" fontSize={9} fill="var(--text-tertiary)" className="font-mono">{v > 0 ? `+${v}` : v}</text>
            </g>
          ))}
          <line x1={x(0)} x2={x(0)} y1={pad.t} y2={H - pad.b} stroke="var(--border-strong)" strokeOpacity={0.8} />
          <line x1={pad.l} x2={W - pad.r} y1={y(0)} y2={y(0)} stroke="var(--border-strong)" strokeOpacity={0.8} />
          <text x={W - pad.r} y={H - 4} textAnchor="end" fontSize={9.5} fill="var(--text-tertiary)">growth (σ) →</text>
          <text x={10} y={pad.t + 2} transform={`rotate(-90 10 ${pad.t + 2})`} textAnchor="end" fontSize={9.5} fill="var(--text-tertiary)">inflation (σ) →</text>
          {/* crosshair to the axes */}
          <line x1={pad.l} x2={cx} y1={cy} y2={cy} stroke={colorOf(cur.top)} strokeOpacity={0.45} strokeDasharray="2 3" />
          <line x1={cx} x2={cx} y1={cy} y2={H - pad.b} stroke={colorOf(cur.top)} strokeOpacity={0.45} strokeDasharray="2 3" />
          {/* the last 12 months */}
          <path d={smooth} fill="none" stroke="url(#tm-trail)" strokeWidth={2} strokeLinecap="round" />
          {trail.slice(0, -1).map((r, k) => (
            <circle key={r.month} cx={x(r.growth)} cy={y(r.inflation)} r={2.2} fill={colorOf(r.top)} fillOpacity={0.25 + (0.6 * k) / trail.length} />
          ))}
          <circle cx={cx} cy={cy} r={16} fill="url(#tm-halo)" />
          <circle cx={cx} cy={cy} r={5.5} fill={colorOf(cur.top)} stroke="var(--surface-1)" strokeWidth={2.5} />
        </svg>
      )}
    </div>
  );
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
          <div className="text-[10px] uppercase tracking-[0.08em] text-text-tertiary">Model as of</div>
          <div className="text-lg font-semibold text-text-primary leading-tight tabular-nums">{monthName(r.month)}</div>
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
            ) : <div className="text-[10.5px] text-text-tertiary">Not 12 months yet.</div>}
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

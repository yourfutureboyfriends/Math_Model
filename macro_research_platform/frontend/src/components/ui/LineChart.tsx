// Multi-series line chart drawn in real pixels (measured container width), so text is never
// stretched: y-axis with gridlines, date ticks, de-overlapped end labels with leader lines,
// and a hover crosshair with a value tooltip. Optional log scale for cumulative returns.

import { useEffect, useMemo, useRef, useState } from 'react';

export interface ChartLine { key: string; label: string; color: string }

interface Props {
  rows: Record<string, any>[];
  x: string;                         // row key holding the x label ("YYYY-MM" dates get calendar ticks)
  lines: ChartLine[];
  height?: number;
  fmt?: (v: number) => string;       // value format (tooltip, end labels)
  axisFmt?: (v: number) => string;  // y-axis tick format (defaults to fmt)
  log?: boolean;                     // log y scale (values must be > 0)
  baseline?: number;                 // dashed reference line (e.g. 0, or 1 for growth of $1)
  refs?: { value: number; label: string; color?: string }[];   // labelled horizontal levels
}

const FONT = 10;
const NO_REFS: { value: number; label: string; color?: string }[] = [];
const CHAR_W = 6.1;                  // monospace advance at 10px
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function niceStep(span: number, count: number): number {
  const raw = span / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const n = raw / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

function linearTicks(lo: number, hi: number, count: number): number[] {
  const step = niceStep(hi - lo || 1, count);
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return out;
}

function logTicks(lo: number, hi: number): number[] {
  const out: number[] = [];
  const ratio = hi / lo;
  const mult = ratio > 64 ? 10 : 2;
  for (let v = mult ** Math.floor(Math.log(lo) / Math.log(mult)); v <= hi * 1.0001; v *= mult) if (v >= lo * 0.9999) out.push(v);
  return out.length >= 2 ? out : [lo, hi];
}

function monthTicks(labels: string[], maxTicks: number): { i: number; text: string }[] {
  if (labels.length && labels.every((l) => /^\d{4}-\d{2}-\d{2}$/.test(l))) {
    // Daily data: tick the first trading day of every k-th month.
    const firsts = labels.map((l, i) => ({ m: l.slice(0, 7), i })).filter((x, k, a) => k === 0 || a[k - 1].m !== x.m);
    const step = Math.max(1, Math.ceil(firsts.length / Math.max(1, maxTicks)));
    return firsts.filter((_, k) => k % step === 0 && (k > 0 || firsts.length < 3))
      .map(({ m, i }) => ({ i, text: `${MONTHS[Number(m.slice(5)) - 1]} ${m.slice(2, 4)}` }));
  }
  const isMonth = labels.every((l) => /^\d{4}-\d{2}$/.test(l));
  const n = labels.length;
  if (!isMonth) {
    const step = Math.max(1, Math.ceil((n - 1) / Math.max(1, maxTicks - 1)));
    const idx: number[] = [];
    for (let i = 0; i < n; i += step) idx.push(i);
    return idx.map((i) => ({ i, text: labels[i] }));
  }
  const years = n / 12;
  if (years > 3) {
    const step = Math.max(1, Math.ceil(years / Math.max(1, maxTicks)));
    const nice = [1, 2, 5, 10, 20].find((s) => s >= step) ?? step;
    return labels.map((l, i) => ({ l, i })).filter(({ l }) => l.endsWith('-01') && Number(l.slice(0, 4)) % nice === 0)
      .map(({ l, i }) => ({ i, text: l.slice(0, 4) }));
  }
  const step = [1, 2, 3, 6, 12].find((s) => n / s <= maxTicks) ?? 12;
  return labels.map((l, i) => ({ l, i })).filter(({ l }) => (Number(l.slice(5)) - 1) % step === 0)
    .map(({ l, i }) => ({ i, text: `${MONTHS[Number(l.slice(5)) - 1]} ${l.slice(2, 4)}` }));
}

export function LineChart({ rows, x, lines, height = 180, fmt = (v) => v.toFixed(2), axisFmt, log = false, baseline, refs = NO_REFS }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const geo = useMemo(() => {
    if (rows.length < 2 || W === 0) return null;
    const vals = rows.flatMap((r) => lines.map((l) => r[l.key])).filter((v): v is number => typeof v === 'number' && (!log || v > 0));
    if (!vals.length) return null;
    const extra = [...(baseline !== undefined ? [baseline] : []), ...refs.map((r) => r.value)];
    let lo = Math.min(...vals, ...extra);
    let hi = Math.max(...vals, ...extra);
    if (lo === hi) { lo -= 1; hi += 1; }
    let yt: number[];
    if (log) {
      yt = logTicks(lo, hi);
    } else {
      // Round the domain out to whole steps so the outermost gridlines bracket the data.
      const step = niceStep(hi - lo, Math.max(3, Math.floor(height / 45)));
      lo = Math.floor(lo / step + 1e-9) * step;
      hi = Math.ceil(hi / step - 1e-9) * step;
      yt = linearTicks(lo, hi, Math.round((hi - lo) / step));
    }
    const af = axisFmt ?? fmt;
    const L = Math.max(...yt.map((t) => af(t).length)) * CHAR_W + 10;
    const last = rows[rows.length - 1];
    const endText = lines.map((l) => (typeof last[l.key] === 'number' ? `${l.label} ${fmt(last[l.key])}` : ''));
    const R = Math.min(W * 0.35, Math.max(...endText.map((t) => t.length)) * CHAR_W + 22);
    const T = 8, B = 20;
    const f = (v: number) => (log ? Math.log(v) : v);
    const sx = (i: number) => L + (i / (rows.length - 1)) * (W - L - R);
    const sy = (v: number) => T + (1 - (f(v) - f(lo)) / (f(hi) - f(lo) || 1)) * (height - T - B);
    // End labels: sorted by y, pushed apart to >= 13px, kept inside the plot.
    const ends = lines.map((l, k) => ({ l, v: last[l.key], text: endText[k] }))
      .filter((e) => typeof e.v === 'number').map((e) => ({ ...e, y0: sy(e.v), y: sy(e.v) }))
      .sort((a, b) => a.y - b.y);
    const gap = 13;
    for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < gap) ends[k].y = ends[k - 1].y + gap;
    const overflow = ends.length ? ends[ends.length - 1].y - (height - B) : 0;
    if (overflow > 0) ends.forEach((e) => { e.y -= overflow; });
    for (let k = ends.length - 2; k >= 0; k--) if (ends[k + 1].y - ends[k].y < gap) ends[k].y = ends[k + 1].y - gap;
    const xt = monthTicks(rows.map((r) => String(r[x])), Math.max(2, Math.floor((W - L - R) / 70)));
    return { L, R, T, B, sx, sy, yt, xt, ends, af };
  }, [rows, lines, W, height, log, baseline, refs, fmt, axisFmt, x]);

  const legend = (
    <div className="flex flex-wrap gap-x-3 gap-y-1 mb-1">
      {lines.map((l) => (
        <span key={l.key} className="inline-flex items-center gap-1.5 text-2xs text-text-secondary">
          <span className="w-3 h-0.5 rounded-full" style={{ background: l.color }} />{l.label}
        </span>
      ))}
    </div>
  );

  const h = hover !== null ? rows[hover] : null;

  return (
    <div>
      {legend}
      <div ref={ref} className="relative w-full" style={{ height }}>
        {geo && (
          <svg width={W} height={height} className="block select-none"
            onMouseLeave={() => setHover(null)}
            onMouseMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              const px = e.clientX - r.left;
              const i = Math.round(((px - geo.L) / (W - geo.L - geo.R)) * (rows.length - 1));
              setHover(Math.max(0, Math.min(rows.length - 1, i)));
            }}>
            {/* grid + y axis */}
            {geo.yt.map((t) => (
              <g key={t}>
                <line x1={geo.L} x2={W - geo.R} y1={geo.sy(t)} y2={geo.sy(t)} stroke="var(--border-subtle)" />
                <text x={geo.L - 6} y={geo.sy(t) + 3.5} fontSize={FONT} textAnchor="end" fill="var(--text-tertiary)" className="font-mono">{geo.af(t)}</text>
              </g>
            ))}
            {baseline !== undefined && (
              <line x1={geo.L} x2={W - geo.R} y1={geo.sy(baseline)} y2={geo.sy(baseline)} stroke="var(--text-tertiary)" strokeDasharray="3 3" />
            )}
            {refs.map((r) => (
              <g key={r.label}>
                <line x1={geo.L} x2={W - geo.R} y1={geo.sy(r.value)} y2={geo.sy(r.value)}
                  stroke={r.color ?? 'var(--text-tertiary)'} strokeDasharray="4 3" strokeWidth={1} />
                <text x={geo.L + 4} y={geo.sy(r.value) - 3} fontSize={10} fill={r.color ?? 'var(--text-tertiary)'} className="font-mono">
                  {r.label} {fmt(r.value)}
                </text>
              </g>
            ))}
            {/* x axis */}
            <line x1={geo.L} x2={W - geo.R} y1={height - geo.B} y2={height - geo.B} stroke="var(--border)" />
            {geo.xt.map(({ i, text }) => (
              <g key={i}>
                <line x1={geo.sx(i)} x2={geo.sx(i)} y1={height - geo.B} y2={height - geo.B + 3} stroke="var(--border)" />
                <text x={geo.sx(i)} y={height - 5} fontSize={FONT} textAnchor="middle" fill="var(--text-tertiary)" className="font-mono">{text}</text>
              </g>
            ))}
            {/* series */}
            {lines.map((l) => {
              const d = rows.map((r, i) => (typeof r[l.key] === 'number' && (!log || r[l.key] > 0)
                ? `${i && typeof rows[i - 1][l.key] === 'number' ? 'L' : 'M'}${geo.sx(i).toFixed(1)},${geo.sy(r[l.key]).toFixed(1)}` : '')).join('');
              return <path key={l.key} d={d} fill="none" stroke={l.color} strokeWidth={1.75} strokeLinejoin="round" />;
            })}
            {/* end labels with leader lines when displaced */}
            {geo.ends.map((e) => {
              const x0 = W - geo.R;
              return (
                <g key={e.l.key}>
                  <circle cx={x0} cy={e.y0} r={2.5} fill={e.l.color} />
                  {Math.abs(e.y - e.y0) > 1 && <path d={`M${x0 + 3},${e.y0} L${x0 + 8},${e.y}`} stroke="var(--text-tertiary)" fill="none" />}
                  <rect x={x0 + 10} y={e.y - 3} width={6} height={6} rx={1} fill={e.l.color} />
                  <text x={x0 + 20} y={e.y + 3.5} fontSize={FONT} fill="var(--text-secondary)" className="font-mono">{e.text}</text>
                </g>
              );
            })}
            {/* hover */}
            {h && hover !== null && (
              <g pointerEvents="none">
                <line x1={geo.sx(hover)} x2={geo.sx(hover)} y1={geo.T} y2={height - geo.B} stroke="var(--text-tertiary)" strokeDasharray="2 2" />
                {lines.map((l) => typeof h[l.key] === 'number' && (!log || h[l.key] > 0) && (
                  <circle key={l.key} cx={geo.sx(hover)} cy={geo.sy(h[l.key])} r={3.5} fill={l.color} stroke="var(--surface-1)" strokeWidth={2} />
                ))}
              </g>
            )}
          </svg>
        )}
        {geo && h && hover !== null && (() => {
          const px = geo.sx(hover);
          const right = px > (W - geo.R) * 0.6;
          const items = lines.filter((l) => typeof h[l.key] === 'number').sort((a, b) => h[b.key] - h[a.key]);
          return (
            <div className="pointer-events-none absolute top-1 z-10 px-2 py-1.5 bg-surface-3/95 border border-border text-2xs font-mono shadow-lg"
              style={right ? { right: W - px + 10 } : { left: px + 10 }}>
              <div className="text-text-tertiary mb-0.5">{String(h[x])}</div>
              {items.map((l) => (
                <div key={l.key} className="flex items-center gap-2 whitespace-nowrap">
                  <span className="w-2 h-2 rounded-sm" style={{ background: l.color }} />
                  <span className="text-text-secondary">{l.label}</span>
                  <span className="ml-auto pl-3 text-text-primary">{fmt(h[l.key])}</span>
                </div>
              ))}
            </div>
          );
        })()}
      </div>
    </div>
  );
}

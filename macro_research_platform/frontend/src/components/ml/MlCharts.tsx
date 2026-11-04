/**
 * Chart kit for the ML area — SVG, theme tokens, hover on every chart.
 * Colour: at most four highlighted series (--viz-1..4, the validated categorical order, fixed per model so a model
 * keeps its colour when others are toggled); everything else muted. Outcome periods are a neutral band, never a hue.
 */
import { useMemo, useRef, useState } from 'react';
import { pct } from '@/lib/format';

export const SERIES = ['var(--viz-1)', 'var(--viz-2)', 'var(--viz-3)', 'var(--viz-4)'];

/** A model keeps its colour slot while it is selected (slot = its position in the selection). */
export function colourOf(selected: string[], key: string): string {
  const i = selected.indexOf(key);
  return i >= 0 && i < SERIES.length ? SERIES[i] : 'var(--viz-muted)';
}

function useHover<T>() {
  const ref = useRef<HTMLDivElement>(null);
  const [h, setH] = useState<{ x: number; y: number; v: T } | null>(null);
  return { ref, h, setH };
}

export function Legend({ items }: { items: { key: string; label: string; color: string; note?: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-2xs text-text-secondary" role="list">
      {items.map((it) => (
        <span key={it.key} role="listitem" className="inline-flex items-center gap-1.5">
          <span className="inline-block w-3 h-[3px] rounded" style={{ background: it.color }} />{it.label}{it.note && <span className="text-text-tertiary">{it.note}</span>}
        </span>))}
    </div>
  );
}

// ── forecast timeline ─────────────────────────────────────────────────────────
export function Timeline({ months, outcome, series, height = 240 }: {
  months: string[]; outcome: number[]; series: { key: string; label: string; color: string; values: number[] }[]; height?: number;
}) {
  const { ref, h, setH } = useHover<number>();
  const W = 900, H = height, L = 40, R = 12, T = 10, B = 26;
  const n = months.length;
  const sx = (i: number) => L + (i / Math.max(1, n - 1)) * (W - L - R);
  const sy = (p: number) => T + (1 - p) * (H - T - B);
  const bands = useMemo(() => {
    const out: [number, number][] = [];
    let s: number | null = null;
    outcome.forEach((y, i) => { if (y === 1 && s === null) s = i; if ((y !== 1 || i === n - 1) && s !== null) { out.push([s, y === 1 ? i : i - 1]); s = null; } });
    return out;
  }, [outcome, n]);
  const years = months.map((m, i) => [m, i] as const).filter(([m]) => m.endsWith('-01') && Number(m.slice(0, 4)) % 5 === 0);
  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((x - L) / (W - L - R)) * (n - 1));
    if (i >= 0 && i < n) setH({ x: e.clientX - r.left, y: e.clientY - r.top, v: i });
  };
  const ordered = [...series].sort((a, b) => (a.color === 'var(--viz-muted)' ? -1 : 0) - (b.color === 'var(--viz-muted)' ? -1 : 0));
  return (
    <div ref={ref} className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Forecast probability over time against outcomes"
        onMouseMove={onMove} onMouseLeave={() => setH(null)}>
        {bands.map(([a, b]) => <rect key={a} x={sx(a)} y={T} width={Math.max(1, sx(b) - sx(a))} height={H - T - B} fill="var(--viz-outcome)" />)}
        {[0, 0.25, 0.5, 0.75, 1].map((g) => <g key={g}><line x1={L} x2={W - R} y1={sy(g)} y2={sy(g)} stroke="var(--border-subtle)" strokeDasharray={g === 0.5 ? '3 3' : undefined} />
          <text x={L - 6} y={sy(g) + 3} textAnchor="end" fontSize="10" className="fill-[var(--text-tertiary)]">{pct(g)}</text></g>)}
        {years.map(([m, i]) => <text key={m} x={sx(i)} y={H - 8} textAnchor="middle" fontSize="10" className="fill-[var(--text-tertiary)]">{m.slice(0, 4)}</text>)}
        {ordered.map((s) => (
          <path key={s.key} d={s.values.map((v, i) => `${i ? 'L' : 'M'}${sx(i)},${sy(v)}`).join('')} fill="none" stroke={s.color}
            strokeWidth={s.color === 'var(--viz-muted)' ? 1 : 2} strokeLinejoin="round" />))}
        {h && <line x1={sx(h.v)} x2={sx(h.v)} y1={T} y2={H - B} stroke="var(--text-tertiary)" strokeWidth={1} />}
        {h && series.filter((s) => s.color !== 'var(--viz-muted)').map((s) => <circle key={s.key} cx={sx(h.v)} cy={sy(s.values[h.v])} r={4} fill={s.color} stroke="var(--surface-1)" strokeWidth={2} />)}
      </svg>
      {h && (
        <div className="ml-tip" style={{ left: Math.min(h.x + 12, (ref.current?.clientWidth ?? 600) - 220), top: 8 }}>
          <div className="font-semibold mb-1">{months[h.v]} · {outcome[h.v] === 1 ? 'answer was YES' : 'answer was no'}</div>
          {series.filter((s) => s.color !== 'var(--viz-muted)').map((s) => (
            <div key={s.key} className="flex items-center justify-between gap-4"><span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: s.color }} />{s.label}</span><span className="font-mono">{pct(s.values[h.v])}</span></div>))}
        </div>)}
    </div>
  );
}

// ── ROC ───────────────────────────────────────────────────────────────────────
export function rocPoints(p: number[], y: number[]) {
  const idx = p.map((_, i) => i).sort((a, b) => p[b] - p[a]);
  const P = y.filter((v) => v === 1).length, N = y.length - P;
  const pts: [number, number][] = [[0, 0]];
  let tp = 0, fp = 0, auc = 0, prevF = 0, prevT = 0;
  for (const i of idx) { if (y[i] === 1) tp++; else fp++; const f = fp / (N || 1), t = tp / (P || 1); auc += (f - prevF) * (t + prevT) / 2; prevF = f; prevT = t; pts.push([f, t]); }
  return { pts, auc };
}

export function RocChart({ outcome, series }: { outcome: number[]; series: { key: string; label: string; color: string; values: number[] }[] }) {
  const { ref, h, setH } = useHover<{ label: string; f: number; t: number }>();
  const S = 280, M = 34;
  const sc = (v: number) => M + v * (S - M - 8);
  const curves = series.map((s) => ({ ...s, ...rocPoints(s.values, outcome) }));
  return (
    <div ref={ref} className="relative">
      <svg viewBox={`0 0 ${S} ${S}`} className="w-full h-auto max-w-[420px]" role="img" aria-label="ROC curves" onMouseLeave={() => setH(null)}>
        <rect x={sc(0)} y={S - sc(1)} width={sc(1) - sc(0)} height={sc(1) - sc(0)} fill="none" stroke="var(--border-subtle)" />
        <line x1={sc(0)} y1={S - sc(0)} x2={sc(1)} y2={S - sc(1)} stroke="var(--border)" strokeDasharray="3 3" />
        {curves.map((c) => (
          <path key={c.key} d={c.pts.map(([f, t], i) => `${i ? 'L' : 'M'}${sc(f)},${S - sc(t)}`).join('')} fill="none" stroke={c.color}
            strokeWidth={c.color === 'var(--viz-muted)' ? 1 : 2}
            onMouseMove={(e) => { const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect(); const f = ((e.clientX - r.left) / r.width * S - M) / (S - M - 8);
              const near = c.pts.reduce((a, b) => (Math.abs(b[0] - f) < Math.abs(a[0] - f) ? b : a)); setH({ x: e.clientX - r.left, y: e.clientY - r.top, v: { label: c.label, f: near[0], t: near[1] } }); }} />))}
        <text x={S / 2} y={S - 4} textAnchor="middle" fontSize="10" className="fill-[var(--text-tertiary)]">false alarms (share of “no” months flagged)</text>
        <text x={10} y={S / 2} textAnchor="middle" fontSize="10" transform={`rotate(-90 10 ${S / 2})`} className="fill-[var(--text-tertiary)]">hits (share of “yes” months caught)</text>
      </svg>
      {h && <div className="ml-tip" style={{ left: h.x + 10, top: h.y - 10 }}>{h.v.label}: catches {pct(h.v.t)} of yes-months at {pct(h.v.f)} false alarms</div>}
      <Legend items={curves.filter((c) => c.color !== 'var(--viz-muted)').map((c) => ({ key: c.key, label: c.label, color: c.color, note: ` AUC ${c.auc.toFixed(3)}` }))} />
    </div>
  );
}

// ── reliability (calibration) ─────────────────────────────────────────────────
export function reliability(p: number[], y: number[], bins = 8) {
  const out: { mean: number; freq: number; n: number }[] = [];
  for (let b = 0; b < bins; b++) {
    const lo = b / bins, hi = (b + 1) / bins;
    const ix = p.map((_, i) => i).filter((i) => p[i] >= lo && (p[i] < hi || (b === bins - 1 && p[i] <= 1)));
    if (ix.length) out.push({ mean: ix.reduce((s, i) => s + p[i], 0) / ix.length, freq: ix.reduce((s, i) => s + y[i], 0) / ix.length, n: ix.length });
  }
  return out;
}

export function ReliabilityChart({ outcome, series }: { outcome: number[]; series: { key: string; label: string; color: string; values: number[] }[] }) {
  const { ref, h, setH } = useHover<{ label: string; mean: number; freq: number; n: number }>();
  const S = 280, M = 34;
  const sc = (v: number) => M + v * (S - M - 8);
  const shown = series.filter((s) => s.color !== 'var(--viz-muted)');
  const maxN = Math.max(1, ...shown.flatMap((s) => reliability(s.values, outcome).map((b) => b.n)));
  return (
    <div ref={ref} className="relative">
      <svg viewBox={`0 0 ${S} ${S}`} className="w-full h-auto max-w-[420px]" role="img" aria-label="Calibration: forecast probability against how often the answer was yes" onMouseLeave={() => setH(null)}>
        <rect x={sc(0)} y={S - sc(1)} width={sc(1) - sc(0)} height={sc(1) - sc(0)} fill="none" stroke="var(--border-subtle)" />
        <line x1={sc(0)} y1={S - sc(0)} x2={sc(1)} y2={S - sc(1)} stroke="var(--border)" strokeDasharray="3 3" />
        {shown.map((s) => { const bins = reliability(s.values, outcome); return (
          <g key={s.key}>
            <path d={bins.map((b, i) => `${i ? 'L' : 'M'}${sc(b.mean)},${S - sc(b.freq)}`).join('')} fill="none" stroke={s.color} strokeWidth={2} />
            {bins.map((b, i) => <circle key={i} cx={sc(b.mean)} cy={S - sc(b.freq)} r={4 + 6 * Math.sqrt(b.n / maxN)} fill={s.color} fillOpacity={0.8} stroke="var(--surface-1)" strokeWidth={2}
              onMouseMove={(e) => { const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect(); setH({ x: e.clientX - r.left, y: e.clientY - r.top, v: { label: s.label, ...b } }); }} />)}
          </g>); })}
        {[0, 0.5, 1].map((g) => <text key={g} x={sc(g)} y={S - 18} textAnchor="middle" fontSize="10" className="fill-[var(--text-tertiary)]">{pct(g)}</text>)}
        <text x={S / 2} y={S - 4} textAnchor="middle" fontSize="10" className="fill-[var(--text-tertiary)]">forecast probability</text>
        <text x={10} y={S / 2} textAnchor="middle" fontSize="10" transform={`rotate(-90 10 ${S / 2})`} className="fill-[var(--text-tertiary)]">how often the answer was yes</text>
      </svg>
      {h && <div className="ml-tip" style={{ left: h.x + 10, top: h.y - 10 }}>{h.v.label}: forecasts averaging {pct(h.v.mean)} → yes {pct(h.v.freq)} of the time ({h.v.n} months)</div>}
      <Legend items={shown.map((s) => ({ key: s.key, label: s.label, color: s.color }))} />
    </div>
  );
}

// ── skill by era (grouped bars, diverging around zero) ───────────────────────
export function EraBars({ eras, series }: { eras: string[]; series: { key: string; label: string; color: string; values: (number | null)[] }[] }) {
  const { ref, h, setH } = useHover<{ label: string; era: string; v: number }>();
  const W = 560, H = 200, L = 40, B = 24, T = 10;
  const vals = series.flatMap((s) => s.values.filter((v): v is number => v != null));
  const lo = Math.min(-0.2, ...vals), hi = Math.max(0.2, ...vals);
  const sy = (v: number) => T + ((hi - v) / (hi - lo)) * (H - T - B);
  const gw = (W - L - 10) / eras.length, bw = Math.min(22, (gw - 16) / Math.max(1, series.length) - 2);
  return (
    <div ref={ref} className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Skill against the base rate, by era" onMouseLeave={() => setH(null)}>
        {[lo, 0, hi].map((g) => <g key={g}><line x1={L} x2={W - 10} y1={sy(g)} y2={sy(g)} stroke={g === 0 ? 'var(--text-tertiary)' : 'var(--border-subtle)'} />
          <text x={L - 6} y={sy(g) + 3} textAnchor="end" fontSize="10" className="fill-[var(--text-tertiary)]">{g > 0 ? '+' : ''}{(g * 100).toFixed(0)}%</text></g>)}
        {eras.map((e, gi) => (
          <g key={e}>
            {series.map((s, si) => { const v = s.values[gi]; if (v == null) return null; const x = L + gi * gw + 8 + si * (bw + 2); const y0 = sy(0), y1 = sy(v);
              return <rect key={s.key} x={x} y={Math.min(y0, y1)} width={bw} height={Math.max(1, Math.abs(y1 - y0))} rx={3} fill={s.color}
                onMouseMove={(ev) => { const r = (ev.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect(); setH({ x: ev.clientX - r.left, y: ev.clientY - r.top, v: { label: s.label, era: e, v } }); }} />; })}
            <text x={L + gi * gw + gw / 2} y={H - 6} textAnchor="middle" fontSize="10" className="fill-[var(--text-secondary)]">{e}</text>
          </g>))}
      </svg>
      {h && <div className="ml-tip" style={{ left: h.x + 10, top: h.y - 10 }}>{h.v.label} · {h.v.era}: {h.v.v > 0 ? '+' : ''}{(h.v.v * 100).toFixed(1)}% vs base rate</div>}
      <Legend items={series.map((s) => ({ key: s.key, label: s.label, color: s.color }))} />
    </div>
  );
}

// ── task × model heatmap (sequential, one hue) ────────────────────────────────
export function Heatmap({ rows, cols, value, sub, onPick }: {
  rows: { key: string; label: string }[]; cols: { key: string; label: string }[];
  value: (r: string, c: string) => number | null | undefined; sub?: (r: string, c: string) => string | null; onPick?: (r: string, c: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-2xs border-separate" style={{ borderSpacing: 2 }}>
        <thead><tr><th />{cols.map((c) => <th key={c.key} className="font-normal text-text-tertiary px-1 pb-1 text-center align-bottom" style={{ minWidth: 72 }}>{c.label}</th>)}</tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.key}>
            <td className="pr-2 text-text-secondary whitespace-nowrap">{r.label}</td>
            {cols.map((c) => { const v = value(r.key, c.key); const s = sub?.(r.key, c.key);
              return <td key={c.key} onClick={() => onPick?.(r.key, c.key)} title={v == null ? 'not computed' : `${r.label} · ${c.label}: ${pct(v)}${s ? ` · ${s}` : ''}`}
                className={`text-center rounded ${onPick ? 'cursor-pointer hover:outline hover:outline-1 hover:outline-[var(--text-tertiary)]' : ''}`}
                style={{ background: v == null ? 'transparent' : `rgb(var(--viz-seq) / ${0.08 + 0.8 * v})`, height: 34 }}>
                <div className={`font-mono ${v != null && v > 0.55 ? 'text-white' : 'text-text-primary'}`}>{v == null ? '—' : pct(v)}</div>
                {s && <div className={`text-[9px] ${v != null && v > 0.55 ? 'text-white/80' : 'text-text-tertiary'}`}>{s}</div>}
              </td>; })}
          </tr>))}</tbody>
      </table>
    </div>
  );
}

export function Sparkline({ values, outcome, color = 'var(--viz-1)' }: { values: number[]; outcome?: number[]; color?: string }) {
  const W = 160, H = 34, n = values.length;
  if (!n) return null;
  const sx = (i: number) => (i / Math.max(1, n - 1)) * W, sy = (v: number) => 2 + (1 - v) * (H - 4);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-8" aria-hidden="true" preserveAspectRatio="none">
      {outcome?.map((y, i) => y === 1 ? <rect key={i} x={sx(i)} y={0} width={Math.max(1, W / n)} height={H} fill="var(--viz-outcome)" /> : null)}
      <path d={values.map((v, i) => `${i ? 'L' : 'M'}${sx(i)},${sy(v)}`).join('')} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Drift bullet: an input's recent shift in standard deviations against the ±1.5 alarm line. */
export function DriftBullet({ shift, outside }: { shift: number; outside: boolean }) {
  const W = 160, H = 16, c = W / 2, s = (v: number) => c + Math.max(-3, Math.min(3, v)) / 3 * (W / 2 - 4);
  const bad = outside || Math.abs(shift) > 1.5;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-40 h-4" role="img" aria-label={`shift ${shift} standard deviations`}>
      <rect x={s(-1.5)} y={4} width={s(1.5) - s(-1.5)} height={8} fill="var(--viz-outcome)" />
      <line x1={c} x2={c} y1={2} y2={14} stroke="var(--border)" />
      <rect x={Math.min(c, s(shift))} y={6} width={Math.max(1, Math.abs(s(shift) - c))} height={4} rx={2} fill={bad ? 'rgb(var(--c-amber))' : 'var(--viz-1)'} />
    </svg>
  );
}

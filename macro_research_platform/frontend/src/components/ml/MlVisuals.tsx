/**
 * Neural-network visuals for the ML area. After Google's TensorFlow Playground (Smilkov, Carter & Sculley): line
 * thickness = weight size, colour = sign (blue positive, amber negative), node shade = activation for the current
 * inputs. Everything is computed in the browser from the exported weights, so the what-if sliders are instant.
 */
import { useMemo } from 'react';
import { pct } from '@/lib/format';
import { ensemble, forward, type Weights } from './mlShared';

const edge = (v: number, max: number) => ({
  stroke: v >= 0 ? 'rgb(var(--c-blue))' : 'rgb(var(--c-amber))',
  strokeWidth: 0.4 + 3.2 * Math.abs(v) / max, strokeOpacity: 0.2 + 0.65 * Math.abs(v) / max,
});
const shade = (a: number) => (a >= 0 ? `rgb(var(--c-blue) / ${0.15 + 0.7 * Math.min(1, a)})` : `rgb(var(--c-amber) / ${0.15 + 0.7 * Math.min(1, -a)})`);

export function NetworkDiagram({ w, netIdx, x, labels }: { w: Weights; netIdx: number; x: number[]; labels: string[] }) {
  const net = w.nets[netIdx];
  const { z, h, p } = forward(net, w, x);
  const nIn = labels.length, nH = net.b1.length;
  const W = 640, H = Math.max(240, nIn * 36 + 30), xIn = 210, xH = 400, xOut = 570;
  const yIn = (i: number) => 20 + (i + 0.5) * ((H - 40) / nIn);
  const yH = (j: number) => 20 + (j + 0.5) * ((H - 40) / nH);
  const m1 = Math.max(1e-6, ...net.W1.flat().map(Math.abs)), m2 = Math.max(1e-6, ...net.W2.map(Math.abs));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={`Neural network ${netIdx + 1}: ${nIn} inputs, ${nH} hidden units, one output`}>
      <text x={xIn} y={12} textAnchor="middle" fontSize="10" className="fill-[var(--text-tertiary)]">inputs</text>
      <text x={xH} y={12} textAnchor="middle" fontSize="10" className="fill-[var(--text-tertiary)]">hidden layer (tanh)</text>
      <text x={xOut} y={12} textAnchor="middle" fontSize="10" className="fill-[var(--text-tertiary)]">output</text>
      {net.W1.map((row, i) => row.map((v, j) => <line key={`a${i}-${j}`} x1={xIn} y1={yIn(i)} x2={xH} y2={yH(j)} {...edge(v, m1)}><title>{`${labels[i]} → hidden ${j + 1}: weight ${v.toFixed(3)}`}</title></line>))}
      {net.W2.map((v, j) => <line key={`b${j}`} x1={xH} y1={yH(j)} x2={xOut} y2={H / 2} {...edge(v, m2)}><title>{`hidden ${j + 1} → output: weight ${v.toFixed(3)}`}</title></line>)}
      {labels.map((l, i) => (
        <g key={l}>
          <text x={xIn - 13} y={yIn(i) + 4} textAnchor="end" fontSize="11" className="fill-[var(--text-secondary)]">{l}</text>
          <circle cx={xIn} cy={yIn(i)} r={7} fill={shade(Math.tanh(z[i]))} stroke="var(--border)"><title>{`${l}: ${z[i].toFixed(2)} standard deviations from its training average`}</title></circle>
        </g>))}
      {h.map((a, j) => <circle key={j} cx={xH} cy={yH(j)} r={8} fill={shade(a)} stroke="var(--border)"><title>{`hidden unit ${j + 1}: activation ${a.toFixed(2)} (bias ${net.b1[j].toFixed(2)})`}</title></circle>)}
      <circle cx={xOut} cy={H / 2} r={14} fill={`rgb(var(--c-red) / ${0.15 + 0.75 * p})`} stroke="var(--border)" />
      <text x={xOut} y={H / 2 + 32} textAnchor="middle" fontSize="11" className="fill-[var(--text-primary)]">{pct(p)} raw</text>
    </svg>
  );
}

/** All ten networks' readings for the current inputs, as dots on one line: their spread is the uncertainty. */
export function EnsembleStrip({ w, cal, x }: { w: Weights; cal: number[] | null; x: number[] }) {
  const e = ensemble(w, cal, x);
  const W = 600, H = 46, L = 20, R = 20, sx = (p: number) => L + p * (W - L - R);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Each network's probability">
      <line x1={L} x2={W - R} y1={20} y2={20} stroke="var(--border)" />
      {[0, 0.25, 0.5, 0.75, 1].map((g) => <text key={g} x={sx(g)} y={42} textAnchor="middle" fontSize="10" className="fill-[var(--text-tertiary)]">{pct(g)}</text>)}
      <rect x={sx(e.lo)} y={14} width={Math.max(2, sx(e.hi) - sx(e.lo))} height={12} fill="rgb(var(--c-blue) / 0.15)" />
      {e.each.map((p, i) => <circle key={i} cx={sx(p)} cy={20} r={4} fill="rgb(var(--c-blue) / 0.7)"><title>{`network ${i + 1}: ${pct(p)}`}</title></circle>)}
      <line x1={sx(e.p)} x2={sx(e.p)} y1={8} y2={32} stroke="var(--text-primary)" strokeWidth={2} />
    </svg>
  );
}

export function ResponseCurve({ w, cal, x, idx, lo, hi, label }: { w: Weights; cal: number[] | null; x: number[]; idx: number; lo: number; hi: number; label: string }) {
  const pts = useMemo(() => Array.from({ length: 41 }, (_, k) => {
    const v = lo + ((hi - lo) * k) / 40;
    const xx = [...x]; xx[idx] = v;
    return { v, ...ensemble(w, cal, xx) };
  }), [w, cal, x, idx, lo, hi]);
  const W = 560, H = 190, L = 44, R = 10, T = 10, B = 28;
  const sx = (v: number) => L + ((v - lo) / (hi - lo || 1)) * (W - L - R), sy = (p: number) => T + (1 - p) * (H - T - B);
  const line = pts.map((q, k) => `${k ? 'L' : 'M'}${sx(q.v)},${sy(q.p)}`).join('');
  const band = pts.map((q, k) => `${k ? 'L' : 'M'}${sx(q.v)},${sy(q.hi)}`).join('') + [...pts].reverse().map((q) => `L${sx(q.v)},${sy(q.lo)}`).join('') + 'Z';
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={`Probability as ${label} varies`}>
      {[0, 0.5, 1].map((g) => <g key={g}><line x1={L} x2={W - R} y1={sy(g)} y2={sy(g)} stroke="var(--border-subtle)" /><text x={L - 6} y={sy(g) + 4} textAnchor="end" fontSize="10" className="fill-[var(--text-tertiary)]">{pct(g)}</text></g>)}
      <path d={band} fill="rgb(var(--c-blue) / 0.15)" />
      <path d={line} fill="none" stroke="rgb(var(--c-blue))" strokeWidth={2} />
      <line x1={sx(x[idx])} x2={sx(x[idx])} y1={T} y2={H - B} stroke="var(--text-tertiary)" strokeDasharray="3 3" />
      <text x={L} y={H - 8} fontSize="10" className="fill-[var(--text-tertiary)]">{lo.toFixed(2)}</text>
      <text x={W - R} y={H - 8} textAnchor="end" fontSize="10" className="fill-[var(--text-tertiary)]">{hi.toFixed(2)}</text>
      <text x={(L + W) / 2} y={H - 8} textAnchor="middle" fontSize="10" className="fill-[var(--text-secondary)]">{label} — dashed: current · band: range across the networks</text>
    </svg>
  );
}

export function Bars({ title, a, labels }: { title: string; a: Record<string, number>; labels: Record<string, string> }) {
  const rows = Object.entries(a).sort((p, q) => Math.abs(q[1]) - Math.abs(p[1]));
  const m = Math.max(0.001, ...rows.map(([, v]) => Math.abs(v)));
  return (
    <div>
      <div className="text-2xs text-text-tertiary mb-1">{title}</div>
      {rows.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[150px_1fr_48px] items-center gap-2 text-2xs" title={`${labels[k] ?? k}: ${v > 0 ? 'raises' : 'lowers'} the probability by ${(Math.abs(v) * 100).toFixed(1)} points vs its average`}>
          <span className="truncate text-text-secondary">{labels[k] ?? k}</span>
          <div className="h-1.5 bg-surface-3 relative"><div className={`absolute inset-y-0 ${v >= 0 ? 'left-1/2 bg-red/70' : 'right-1/2 bg-green/70'}`} style={{ width: `${(Math.abs(v) / m) * 50}%` }} /></div>
          <span className="font-mono text-right">{v > 0 ? '+' : ''}{(v * 100).toFixed(1)}</span>
        </div>))}
    </div>
  );
}

export function Sliders({ keys, labels, ranges, x, setX }: { keys: string[]; labels: string[]; ranges: any[]; x: number[]; setX: (v: number[]) => void }) {
  return (
    <div className="space-y-1">
      {keys.map((k, i) => (
        <label key={k} className="grid grid-cols-[160px_1fr_64px] items-center gap-2 text-2xs">
          <span className="truncate text-text-secondary" title={labels[i]}>{labels[i]}</span>
          <input type="range" min={ranges[i].train_min} max={ranges[i].train_max} step={(ranges[i].train_max - ranges[i].train_min) / 200 || 0.01}
            value={x[i]} onChange={(e) => { const v = [...x]; v[i] = Number(e.target.value); setX(v); }} aria-label={labels[i]} />
          <span className="font-mono text-right">{x[i].toFixed(2)}</span>
        </label>))}
    </div>
  );
}

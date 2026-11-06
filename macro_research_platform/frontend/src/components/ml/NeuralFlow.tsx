/**
 * Neural-network signal flow — a live, animated view of one network's forward pass (Apache ECharts).
 *
 *  - Layers sit on translucent panels drawn in perspective (the right-hand layers recede), over a grid floor.
 *  - Every connection carries moving particles: their speed, size and brightness follow the signal it actually
 *    carries now (weight × the activation feeding it); colour is the sign (blue raises, amber lowers).
 *  - Hidden units pulse with their activation; the output glows with the calibrated probability.
 *  - Each input shows its own last two years as a small wave next to its name.
 *
 * Everything is the real forward pass of the exported weights, recomputed in the browser — so when the inputs
 * change (what-if sliders, or replaying history month by month) the flow changes with them.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { EChart, alpha, color, useChartTheme } from '@/components/charts/EChart';
import { forward, connectionSignals, selectedPrediction, type Weights } from './mlShared';

// layout in a 0–100 box; P() tilts it so layers further right recede (a camera looking in from the left)
const X = { input: 31, hidden: 62, output: 90 };          // names and waves sit at fixed pixel offsets left of the inputs
const PANELS = [{ x0: 1.5, x1: 34 }, { x0: 38, x1: 98 }];
const P = (x: number, y: number): [number, number] => [x, 50 + (y - 50) * (1 - 0.2 * (x / 100))];
const yAt = (k: number, n: number) => 12 + ((k + 0.5) / n) * 80;
// signal buckets: [min share of the strongest signal, particle period s, particle size]
const BUCKETS: [number, number, number][] = [[0.6, 1.1, 4.5], [0.3, 1.9, 3.5], [0.1, 3.0, 2.5], [0, 0, 0]];

export function NeuralFlow({ w, netIdx, x, labels, cal, recent, month, outcome, height = 470 }: {
  w: Weights; netIdx: number; x: number[]; labels: string[]; cal: number[] | null;
  recent?: number[][];                    // per input: its last values (oldest first), drawn as the wave
  month?: string; outcome?: number | null; height?: number;
}) {
  const t = useChartTheme();
  const net = w.nets[netIdx];
  const option = useMemo(() => {
    const { z, h, p: raw } = forward(net, w, x);
    const pCal = selectedPrediction(net,w,x,cal).p;
    const nIn = labels.length, nH = net.b1.length;
    const pos = color('rgb(var(--c-blue))', t.series[0]), neg = color('rgb(var(--c-amber))', t.amber);
    const glow = (c: string, a: number) => ({ shadowBlur: 6 + 18 * Math.min(1, a), shadowColor: alpha(c, 0.9) });

    // connections, bucketed by the signal they carry now
    const s1 = connectionSignals(net,w,x).input;
    const s2 = net.W2.map((v, j) => v * h[j]);
    const smax = Math.max(1e-6, ...s1.flat().map(Math.abs), ...s2.map(Math.abs));
    const wmax = Math.max(1e-6, ...net.W1.flat().map(Math.abs), ...net.W2.map(Math.abs));
    type Edge = { coords: [number, number][]; s: number; wt: number; tip: string };
    const edges: Edge[] = [
      ...net.W1.flatMap((row, i) => row.map((v, j) => ({ coords: [P(X.input, yAt(i, nIn)), P(X.hidden, yAt(j, nH))] as [number, number][],
        s: s1[i][j], wt: v, tip: `${labels[i]} → hidden ${j + 1}<br/>weight ${v.toFixed(3)} · signal now ${s1[i][j] >= 0 ? '+' : ''}${s1[i][j].toFixed(3)}` }))),
      ...net.W2.map((v, j) => ({ coords: [P(X.hidden, yAt(j, nH)), P(X.output, 50)] as [number, number][],
        s: s2[j], wt: v, tip: `hidden ${j + 1} → output<br/>weight ${v.toFixed(3)} · signal now ${s2[j] >= 0 ? '+' : ''}${s2[j].toFixed(3)}` })),
    ];
    const lineSeries = BUCKETS.flatMap(([min, period, size], b) => [pos, neg].map((c, sgn) => ({
      type: 'lines', coordinateSystem: 'cartesian2d', polyline: false, zlevel: 1, z: 2,
      effect: { show: period > 0, period: period || 1, trailLength: 0.35, symbol: 'circle', symbolSize: size || 1, color: alpha(c, 0.95), loop: true },
      lineStyle: { curveness: 0.08 },
      data: edges.filter((e) => (e.s >= 0) === (sgn === 0) && Math.abs(e.s) / smax >= min && (b === 0 || Math.abs(e.s) / smax < BUCKETS[b - 1][0]))
        .map((e) => ({ coords: e.coords, tip: e.tip, lineStyle: { color: c, width: 0.5 + 2.6 * Math.abs(e.wt) / wmax, opacity: 0.12 + 0.6 * Math.abs(e.s) / smax } })),
    })));

    const shade = (a: number) => alpha(a >= 0 ? pos : neg, 0.25 + 0.7 * Math.min(1, Math.abs(a)));
    const inputs = labels.map((l, i) => { const a = Math.tanh(z[i]), c = a >= 0 ? pos : neg;
      return { value: P(X.input, yAt(i, nIn)), symbolSize: 13, tip: `${l}<br/>${z[i] >= 0 ? '+' : ''}${z[i].toFixed(2)} sd from its training average`,
        itemStyle: { color: shade(a), borderColor: alpha(c, 0.9), borderWidth: 1.5, ...glow(c, Math.abs(a)) } }; });
    const hidden = h.map((a, j) => { const c = a >= 0 ? pos : neg;
      return { value: P(X.hidden, yAt(j, nH)), symbolSize: 11 + 9 * Math.abs(a), tip: `hidden unit ${j + 1}<br/>activation ${a.toFixed(2)} (tanh) · bias ${net.b1[j].toFixed(2)}`,
        itemStyle: { color: shade(a), borderColor: alpha(c, 0.9), borderWidth: 1.5, ...glow(c, Math.abs(a)) } }; });
    const outC = t.red;

    return {
      animationDurationUpdate: 350, animationEasingUpdate: 'cubicOut' as const,
      legend: { show: false }, toolbox: { show: false },
      grid: { left: 0, right: 0, top: 0, bottom: 0 },
      xAxis: { type: 'value', min: 0, max: 100, show: false }, yAxis: { type: 'value', min: 0, max: 100, inverse: true, show: false },
      tooltip: { trigger: 'item', formatter: (q: any) => q.data?.tip ?? '' },
      series: [
        ...lineSeries,
        { type: 'scatter', z: 4, zlevel: 2, data: inputs },
        { type: 'effectScatter', z: 4, zlevel: 2, data: hidden, rippleEffect: { brushType: 'stroke', scale: 2.6, period: 3.2, number: 2 }, showEffectOn: 'render' },
        { type: 'effectScatter', z: 5, zlevel: 2, showEffectOn: 'render', rippleEffect: { brushType: 'stroke', scale: 1.6 + 2 * pCal, period: 2.4, number: 3 },
          data: [{ value: P(X.output, 50), symbolSize: 18 + 26 * pCal, tip: `selected network · probability ${(pCal * 100).toFixed(1)}% (raw ${(raw * 100).toFixed(1)}%)`,
            itemStyle: { color: alpha(outC, 0.25 + 0.7 * pCal), borderColor: outC, borderWidth: 2, ...glow(outC, 0.4 + pCal) } }] },
      ],
    };
  }, [net, w, x, labels, cal, t]);
  // panels, names, waves and readouts as an HTML/SVG overlay: the chart's box is 0–100 on both axes with no margin,
  // so a layout point P(x, y) is simply (x %, y %) of the stage
  const read = useMemo(() => selectedPrediction(net,w,x,cal), [net,w,x,cal]);
  const pos = color('rgb(var(--c-blue))', t.series[0]);
  const at = (xx: number, yy: number) => { const [a, b] = P(xx, yy); return { left: `${a}%`, top: `${b}%` }; };
  const poly = (x0: number, x1: number) => [P(x0, 3), P(x1, 3), P(x1, 97), P(x0, 97)].map(([a, b]) => `${a},${b}`).join(' ');
  const nIn = labels.length;
  const stage = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(800);
  useEffect(() => {
    const el = stage.current; if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => setW(el.clientWidth)); ro.observe(el); setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  const labelMax = Math.max(48, ((X.input - PANELS[0].x0) / 100) * W - 14 - 34 - 8 - 14);   // room left of the wave inside the panel
  return (
    <div ref={stage} className="ml-flow relative overflow-hidden rounded-md" style={{ height }}>
      <div className="ml-flow-floor" aria-hidden />
      <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        <defs>{PANELS.map((_, k) => (
          <linearGradient key={k} id={`nf-panel${k}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={k ? pos : t.textStrong} stopOpacity={0.08} /><stop offset="100%" stopColor={k ? pos : t.textStrong} stopOpacity={0.02} /></linearGradient>))}</defs>
        {PANELS.map((pn, k) => <polygon key={k} points={poly(pn.x0, pn.x1)} fill={`url(#nf-panel${k})`} stroke={alpha(k ? pos : t.textStrong, 0.3)} strokeWidth={1} vectorEffect="non-scaling-stroke" />)}
      </svg>
      <div className="absolute inset-0 z-[1]">
        <EChart option={option} height={height} merge ariaLabel={`Neural network ${netIdx + 1} signal flow: ${labels.length} inputs, ${net.b1.length} hidden units, one output`} />
      </div>
      <div className="absolute inset-0 z-[2] pointer-events-none font-mono text-[10px] text-text-tertiary">
        <span className="absolute" style={{ ...at(PANELS[0].x0 + 1.5, 5), transform: 'translateY(-50%)' }}>Inputs: {nIn} · standardised</span>
        <span className="absolute" style={{ ...at(PANELS[1].x0 + 1.5, 5.5), transform: 'translateY(-50%)' }}>Neurons: {net.b1.length} · Activation: tanh → output (logistic)</span>
        {month && <span className={`absolute whitespace-nowrap font-semibold text-[11px] ${outcome ? 'text-red' : 'text-text-secondary'}`} style={{ ...at(96.5, 5.5), transform: 'translate(-100%,-50%)' }}>
          {month}{outcome == null ? '' : outcome ? ' · answer: yes' : ' · answer: no'}</span>}
        {labels.map((l, i) => { const r = recent?.[i]?.filter((v) => Number.isFinite(v)); const pt = at(X.input, yAt(i, nIn));
          let d = '';
          if (r && r.length > 1) { const lo = Math.min(...r), hi = Math.max(...r), span = hi - lo || 1;
            d = r.map((v, k) => `${k ? 'L' : 'M'}${((k / (r.length - 1)) * 32 + 1).toFixed(1)},${(13 - ((v - lo) / span) * 10).toFixed(1)}`).join(''); }
          return (
            <span key={l} className="absolute flex items-center gap-2" style={{ left: `calc(${pt.left} - 14px)`, top: pt.top, transform: 'translate(-100%,-50%)' }}>
              <span className="font-sans text-[11px] text-text-secondary truncate text-right" style={{ maxWidth: labelMax }} title={l}>{l}</span>
              <svg width={34} height={16} className="shrink-0 rounded-[3px] bg-surface-2/90 border border-border-subtle" aria-hidden>{d && <path d={d} fill="none" stroke={t.green} strokeWidth={1.4} />}</svg>
            </span>); })}
        <span className="absolute text-center" style={{ ...at(X.output, 50), transform: 'translate(-50%, 26px)' }}>
          <span className="block text-[15px] font-semibold text-text-primary">{(read.p * 100).toFixed(1)}%</span>
          <span className="block">selected seed · raw {(read.raw * 100).toFixed(1)}%</span></span>
      </div>
    </div>
  );
}

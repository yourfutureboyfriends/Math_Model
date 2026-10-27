/**
 * Time machine — scrub or play through the macro model's history and see what it said at the time: where growth and
 * inflation stood (as estimated with the data available then, not today's revised history), the regime
 * probabilities, the portfolio it chose — and, greyed as hindsight, the regime that followed and the next 12
 * months' returns against 60/40. Reads the walk-forward backtest's timeline (api/model/backtest.py), so scrubbing
 * is instant.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import { cn } from '@/lib/utils';

type Row = {
  decided: string; month: string; growth: number; inflation: number; probs: Record<string, number>; top: string;
  p_g: number; p_i: number; weights: Record<string, number>; cash: number; realised?: string | null;
  next_12m?: { model: number | null; strategic: number | null; sixty_forty: number | null };
};

const QUAD_POS: Record<string, [number, number]> = {        // [growth sign, inflation sign] of each regime's corner
  Goldilocks: [1, -1], Reflation: [1, 1], Stagflation: [-1, 1], 'Deflationary slowdown': [-1, -1],
};
const JUMPS: [string, string][] = [['2000-10', 'Dot-com bust'], ['2008-09', 'Lehman'], ['2020-03', 'Covid crash'],
  ['2022-06', 'Inflation peak']];
const pct = (v?: number | null, d = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const monthName = (m: string) => new Date(`${m}-15`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });

function QuadrantMap({ rows, i }: { rows: Row[]; i: number }) {
  const W = 220, H = 180, pad = 18;
  const lim = 3;
  const x = (g: number) => pad + ((Math.max(-lim, Math.min(lim, g)) + lim) / (2 * lim)) * (W - 2 * pad);
  const y = (v: number) => H - pad - ((Math.max(-lim, Math.min(lim, v)) + lim) / (2 * lim)) * (H - 2 * pad);
  const trail = rows.slice(Math.max(0, i - 11), i + 1);
  const cur = rows[i];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Growth ${cur.growth}, inflation ${cur.inflation}`}>
      <rect x={pad} y={pad} width={W - 2 * pad} height={H - 2 * pad} fill="none" stroke="var(--border)" />
      <line x1={x(0)} x2={x(0)} y1={pad} y2={H - pad} stroke="var(--border-strong)" />
      <line x1={pad} x2={W - pad} y1={y(0)} y2={y(0)} stroke="var(--border-strong)" />
      {Object.entries(QUAD_POS).map(([q, [gs, is]]) => (
        <text key={q} x={gs > 0 ? W - pad - 3 : pad + 3} y={is > 0 ? pad + 10 : H - pad - 4} textAnchor={gs > 0 ? 'end' : 'start'}
          className={cn('text-[8.5px]', cur.top === q ? 'fill-[rgb(var(--c-bloomberg))] font-semibold' : 'fill-[var(--text-tertiary)]')}>{q}</text>
      ))}
      <text x={W / 2} y={H - 3} textAnchor="middle" className="fill-[var(--text-tertiary)] text-[8px]">growth →</text>
      <text x={6} y={H / 2} transform={`rotate(-90 6 ${H / 2})`} textAnchor="middle" className="fill-[var(--text-tertiary)] text-[8px]">inflation →</text>
      <polyline points={trail.map((r) => `${x(r.growth)},${y(r.inflation)}`).join(' ')} fill="none" stroke="rgb(var(--c-bloomberg))" strokeOpacity={0.45} strokeWidth={1.2} />
      {trail.map((r, k) => (
        <circle key={r.month} cx={x(r.growth)} cy={y(r.inflation)} r={k === trail.length - 1 ? 4.5 : 2}
          fill="rgb(var(--c-bloomberg))" fillOpacity={k === trail.length - 1 ? 1 : 0.2 + (0.6 * k) / trail.length} />
      ))}
    </svg>
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
    }), 320);
    return () => clearInterval(timer.current);
  }, [playing, rows.length]);

  if (!rows.length) {
    return <div className="text-2xs text-text-tertiary">The timeline appears after the model's next full run (a saved result from before this feature has none) — refresh in a minute.</div>;
  }
  const r = rows[i];
  const probs = Object.entries(r.probs).sort((a, b) => b[1] - a[1]);
  const weights = Object.entries(r.weights).filter(([, w]) => w > 0).sort((a, b) => b[1] - a[1]).slice(0, 7);
  const maxW = Math.max(0.01, ...weights.map(([, w]) => w));
  const jump = (m: string) => { const k = rows.findIndex((x) => x.month >= m); if (k >= 0) { setPlaying(false); setI(k); } };
  const n = r.next_12m;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="font-mono text-sm font-semibold text-text-primary min-w-[9.5rem]">{monthName(r.month)}</span>
        <div className="flex items-center gap-0.5">
          <button type="button" className="tm-btn" aria-label="Previous month" onClick={() => { setPlaying(false); setI((k) => Math.max(0, k - 1)); }}><SkipBack className="w-3 h-3" /></button>
          <button type="button" className="tm-btn" aria-label={playing ? 'Pause' : 'Play'} onClick={() => { if (i >= rows.length - 1) setI(0); setPlaying((v) => !v); }}>
            {playing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}</button>
          <button type="button" className="tm-btn" aria-label="Next month" onClick={() => { setPlaying(false); setI((k) => Math.min(rows.length - 1, k + 1)); }}><SkipForward className="w-3 h-3" /></button>
        </div>
        <div className="flex flex-wrap gap-1">
          {JUMPS.filter(([m]) => m >= rows[0].month && m <= rows[rows.length - 1].month).map(([m, label]) => (
            <button key={m} type="button" onClick={() => jump(m)} className={cn('px-1.5 py-0.5 text-[10px] border', r.month === m ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{label}</button>
          ))}
          <button type="button" onClick={() => { setPlaying(false); setI(rows.length - 1); }} className="px-1.5 py-0.5 text-[10px] border border-border text-text-secondary hover:text-text-primary">Today</button>
        </div>
      </div>
      <input type="range" min={0} max={rows.length - 1} value={i} onChange={(e) => { setPlaying(false); setI(Number(e.target.value)); }}
        aria-label="Month" className="whatif-range w-full mb-3" />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <div className="text-[10px] text-text-tertiary mb-1">Growth × inflation — as the model saw it then (last 12 months)</div>
          <QuadrantMap rows={rows} i={i} />
          <div className="text-[10px] font-mono text-text-tertiary">growth {r.growth > 0 ? '+' : ''}{r.growth.toFixed(2)}σ · inflation {r.inflation > 0 ? '+' : ''}{r.inflation.toFixed(2)}σ</div>
        </div>
        <div>
          <div className="text-[10px] text-text-tertiary mb-1">Regime probabilities for {monthName(r.month)}</div>
          <div className="space-y-1.5">
            {probs.map(([q, v]) => (
              <div key={q}>
                <div className="flex justify-between text-2xs"><span className={q === r.top ? 'text-text-primary font-medium' : 'text-text-secondary'}>{q}</span><span className="font-mono">{Math.round(v * 100)}%</span></div>
                <div className="h-1.5 bg-surface-3"><div className="h-1.5 bg-bloomberg transition-[width] duration-200" style={{ width: `${v * 100}%` }} /></div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-[10px] text-text-tertiary">P(growth ↑) {Math.round(r.p_g * 100)}% · P(inflation ↑) {Math.round(r.p_i * 100)}%</div>
          {r.realised && (
            <div className="mt-1.5 text-[10px] text-text-tertiary italic" title="Hindsight: from the factors as they are known today">
              What followed: <span className={r.realised === r.top ? 'text-green not-italic' : 'text-amber not-italic'}>{r.realised}</span>
              {r.realised === r.top ? ' — called correctly' : ''}</div>
          )}
        </div>
        <div>
          <div className="text-[10px] text-text-tertiary mb-1">Tactical portfolio chosen</div>
          <div className="space-y-1">
            {weights.map(([a, w]) => (
              <div key={a} className="grid grid-cols-[minmax(0,1fr)_70px_34px] items-center gap-1.5 text-[10.5px]">
                <span className="truncate text-text-secondary">{a}</span>
                <span className="h-1.5 bg-surface-3"><span className="block h-1.5 bg-bloomberg/80 transition-[width] duration-200" style={{ width: `${(w / maxW) * 100}%` }} /></span>
                <span className="text-right font-mono text-text-primary">{Math.round(w * 100)}%</span>
              </div>
            ))}
            {r.cash > 0.005 && <div className="text-[10.5px] text-text-tertiary">Cash {Math.round(r.cash * 100)}%</div>}
          </div>
          <div className="mt-2 p-1.5 border border-border-subtle text-[10.5px]" title="Hindsight: realised returns over the following 12 months, net of costs">
            <div className="text-[10px] text-text-tertiary mb-0.5 italic">Next 12 months (hindsight)</div>
            {n && (n.model != null || n.sixty_forty != null) ? (
              <div className="grid grid-cols-3 gap-1 font-mono">
                <span>Tactical <span className={(n.model ?? 0) >= 0 ? 'text-green' : 'text-red'}>{pct(n.model)}</span></span>
                <span>Strategic <span className={(n.strategic ?? 0) >= 0 ? 'text-green' : 'text-red'}>{pct(n.strategic)}</span></span>
                <span title={sixtyForty ? `${sixtyForty.equity} / ${sixtyForty.bonds}` : undefined}>60/40 <span className={(n.sixty_forty ?? 0) >= 0 ? 'text-green' : 'text-red'}>{pct(n.sixty_forty)}</span></span>
              </div>
            ) : <div className="text-text-tertiary">Not 12 months yet.</div>}
          </div>
        </div>
      </div>
      <div className="mt-2 text-[10px] text-text-tertiary">
        Factors, probabilities and weights are what the model computed with the data available at the end of {monthName(r.decided)} —
        no look-ahead. Italic figures are hindsight. Returns are excess over cash, as in the backtest.
      </div>
    </div>
  );
}

// Interactive price chart: choose the bar interval (5m, 15m, 1H, 1D, 1W, 1M) and the
// period (1D … Max); candles / line / area; volume; 20/50/200-bar moving averages; log scale;
// plan levels (entry / stop / target) and signal markers. Scroll to zoom around the cursor,
// drag to pan, double-click to reset; the crosshair reads out OHLC, change and volume; arrow
// keys step bar by bar. More bars than pixels are merged into OHLC buckets, so the chart
// stays sharp and fast at any period.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface Bar { t: string; o: number; h: number; l: number; c: number; v: number }
export interface PriceRef { value: number; label: string; color?: string }

const INTERVALS: { key: string; label: string }[] = [
  { key: '5m', label: '5m' }, { key: '15m', label: '15m' }, { key: '1h', label: '1H' },
  { key: '1d', label: '1D' }, { key: '1wk', label: '1W' }, { key: '1mo', label: '1M' },
];
const PERIODS: { key: string; label: string }[] = [
  { key: '1d', label: '1D' }, { key: '5d', label: '5D' }, { key: '1mo', label: '1M' }, { key: '3mo', label: '3M' },
  { key: '6mo', label: '6M' }, { key: 'ytd', label: 'YTD' }, { key: '1y', label: '1Y' }, { key: '2y', label: '2Y' },
  { key: '5y', label: '5Y' }, { key: '10y', label: '10Y' }, { key: 'max', label: 'Max' },
];
const PERIOD_DAYS: Record<string, number> = { '1d': 1, '5d': 5, '1mo': 31, '3mo': 92, '6mo': 183, ytd: 366, '1y': 366, '2y': 731, '5y': 1827, '10y': 3653, max: 1e9 };
const MAX_DAYS: Record<string, number> = { '5m': 60, '15m': 60, '1h': 730 };
const DEFAULT_PERIOD: Record<string, string> = { '5m': '5d', '15m': '1mo', '1h': '3mo', '1d': '1y', '1wk': '5y', '1mo': 'max' };
const allowed = (i: string, p: string) => PERIOD_DAYS[p] <= (MAX_DAYS[i] ?? 1e9);

// theme colours, so the Markets up/down setting (red = up in Asian markets) applies to candles too
const UP = 'rgb(var(--c-green))', DOWN = 'rgb(var(--c-red))';
const WARM = new Set(['1d', '1wk', '1mo']);     // intervals fetched with 200 extra bars so MAs start on the first bar
const MA = [{ n: 20, color: '#c98500' }, { n: 50, color: '#3987e5' }, { n: 200, color: '#d55181' }];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const AXIS_W = 58, PAD_T = 6, PAD_B = 20, PAD_L = 6;

function sma(c: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array(c.length).fill(null);
  let s = 0;
  for (let i = 0; i < c.length; i++) {
    s += c[i];
    if (i >= n) s -= c[i - n];
    if (i >= n - 1) out[i] = s / n;
  }
  return out;
}

function niceTicks(lo: number, hi: number, count: number): number[] {
  const span = hi - lo || Math.abs(hi) || 1;
  const raw = span / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const f = raw / mag;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(v);
  return out;
}

function fmtPx(v: number): string {
  // Precision follows the price level: FX (1.1234) and sub-$10 prices need 4-5 decimals.
  const a = Math.abs(v);
  const dp = a >= 1000 ? 0 : a >= 10 ? 2 : a >= 1 ? 4 : 5;
  return v.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
}
function fmtVol(v: number): string {
  return v >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : String(Math.round(v));
}
function parseT(t: string): Date { return new Date(t.length === 10 ? `${t}T00:00:00` : t); }
function fmtTime(t: string, interval: string, full = false): string {
  const d = parseT(t);
  if (MAX_DAYS[interval]) {
    const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    return full ? `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()} ${hm}` : hm;
  }
  if (interval === '1mo') return full ? `${MONTHS[d.getMonth()]} ${d.getFullYear()}` : `${MONTHS[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`;
  return full ? `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}` : `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** Merge consecutive bars into OHLC buckets of size k. */
function bucket(b: Bar[], k: number): { bars: Bar[]; first: number[] } {
  if (k <= 1) return { bars: b, first: b.map((_, i) => i) };
  const bars: Bar[] = [], first: number[] = [];
  for (let i = 0; i < b.length; i += k) {
    const g = b.slice(i, i + k);
    bars.push({ t: g[0].t, o: g[0].o, c: g[g.length - 1].c, h: Math.max(...g.map((x) => x.h)),
                l: Math.min(...g.map((x) => x.l)), v: g.reduce((s, x) => s + x.v, 0) });
    first.push(i);
  }
  return { bars, first };
}

interface Props {
  symbol: string;
  refs?: PriceRef[];
  markers?: Record<string, boolean>;       // daily-bar dates to flag (e.g. past BUY signals)
  height?: number;
  defaultInterval?: string;
  defaultPeriod?: string;
}

export function PriceChart({ symbol, refs = [], markers, height = 340, defaultInterval = '1d', defaultPeriod = '1y' }: Props) {
  const [interval, setInterval_] = useState(defaultInterval);
  const [period, setPeriod] = useState(defaultPeriod);
  const [range, setRange] = useState<{ start: string; end: string } | null>(null);   // custom dates override the preset
  const [kind, setKind] = useState<'candle' | 'line' | 'area'>('candle');
  const [mas, setMas] = useState<Record<number, boolean>>({ 20: false, 50: true, 200: true });
  const [showVol, setShowVol] = useState(true);
  const [logScale, setLogScale] = useState(false);
  const [data, setData] = useState<Bar[] | null>(null);
  const [meta, setMeta] = useState<{ currency?: string; timezone?: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [win, setWin] = useState<[number, number] | null>(null);       // visible [start, end) in raw bars
  const [base, setBase] = useState(0);                                  // first bar of the chosen window (earlier bars warm up the MAs)
  const [hover, setHover] = useState<number | null>(null);              // index into drawn bars
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const drag = useRef<{ x: number; win: [number, number] } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(Math.max(280, el.clientWidth)));
    ro.observe(el);
    setWidth(Math.max(280, el.clientWidth));
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true); setErr(null);
    fetch(`/api/v1/market/bars?${new URLSearchParams({ ...(range ? { symbol, interval, start: range.start, end: range.end } : { symbol, interval, period }),
      ...(WARM.has(interval) && (range || period !== 'max') ? { warmup: '200' } : {}) })}`)
      .then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : j?.detail?.message || `HTTP ${r.status}`);
        return j;
      })
      .then((j) => { if (!cancelled) { setData(j.bars); setBase(j.first_visible ?? 0); setMeta({ currency: j.currency, timezone: j.timezone }); setWin(null); setHover(null); } })
      .catch((e) => { if (!cancelled) { setErr(e.message); setData(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, interval, period, range]);

  const pickInterval = (i: string) => {
    setInterval_(i);
    if (!allowed(i, period)) setPeriod(DEFAULT_PERIOD[i]);
  };

  const all = useMemo(() => data ?? [], [data]);
  const closes = useMemo(() => all.map((b) => b.c), [all]);
  const maLines = useMemo(() => Object.fromEntries(MA.map((m) => [m.n, sma(closes, m.n)])), [closes]);
  const full: [number, number] = [Math.min(base, Math.max(0, all.length - 1)), all.length];
  const [s0, s1] = win ?? full;
  const plotW = Math.max(100, width - AXIS_W - PAD_L);
  const visible = useMemo(() => all.slice(s0, s1), [all, s0, s1]);
  const k = Math.max(1, Math.ceil(visible.length / (plotW / 3)));
  const { bars, first } = useMemo(() => bucket(visible, k), [visible, k]);

  const volH = showVol ? Math.round((height - PAD_T - PAD_B) * 0.18) : 0;
  const priceH = height - PAD_T - PAD_B - volH - (showVol ? 6 : 0);
  const n = bars.length;
  const slot = n ? plotW / n : plotW;
  const xOf = (i: number) => PAD_L + (i + 0.5) * slot;

  const activeMa = MA.filter((m) => mas[m.n]);
  let lo = Infinity, hi = -Infinity;
  bars.forEach((b, i) => {
    lo = Math.min(lo, kind === 'candle' ? b.l : b.c); hi = Math.max(hi, kind === 'candle' ? b.h : b.c);
    activeMa.forEach((m) => { const v = maLines[m.n][s0 + first[i] + Math.min(k, visible.length - first[i]) - 1]; if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
  });
  if (Number.isFinite(lo)) refs.forEach((r) => { if (r.value > lo * 0.75 && r.value < hi * 1.33) { lo = Math.min(lo, r.value); hi = Math.max(hi, r.value); } });
  if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
  const padY = (hi - lo) * 0.06 || hi * 0.02 || 1;
  lo -= padY; hi += padY;
  const useLog = logScale && lo > 0;
  const tf = (v: number) => (useLog ? Math.log(v) : v);
  const yOf = (v: number) => PAD_T + (1 - (tf(v) - tf(lo)) / (tf(hi) - tf(lo))) * priceH;
  const vMax = Math.max(1, ...bars.map((b) => b.v));
  const volTop = PAD_T + priceH + 6;

  const ticks = useLog
    ? niceTicks(lo, hi, 5).filter((v) => v > 0)
    : niceTicks(lo, hi, Math.max(3, Math.floor(priceH / 48)));
  const xTicks: number[] = [];
  if (n) {
    const every = Math.max(1, Math.round(n / Math.max(2, Math.floor(plotW / 90))));
    for (let i = 0; i < n; i += every) xTicks.push(i);
  }

  const onMove = (e: React.MouseEvent) => {
    const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
    const x = e.clientX - rect.left;
    if (drag.current && all.length) {
      const per = (drag.current.win[1] - drag.current.win[0]) / plotW;
      const shift = Math.round((drag.current.x - x) * per);
      const len = drag.current.win[1] - drag.current.win[0];
      const a = Math.max(0, Math.min(all.length - len, drag.current.win[0] + shift));
      setWin([a, a + len]);
      return;
    }
    const i = Math.floor((x - PAD_L) / slot);
    setHover(i >= 0 && i < n ? i : null);
  };
  const onWheel = useCallback((e: WheelEvent) => {
    if (!all.length) return;
    e.preventDefault();
    const rect = (e.currentTarget as SVGElement).getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left - PAD_L) / plotW));
    const [a, b] = win ?? [base, all.length];
    const len = b - a;
    const newLen = Math.max(10, Math.min(all.length, Math.round(len * (e.deltaY > 0 ? 1.15 : 0.87))));
    const center = a + frac * len;
    let na = Math.round(center - frac * newLen);
    na = Math.max(0, Math.min(all.length - newLen, na));
    setWin(newLen >= all.length ? (base ? [0, all.length] : null) : [na, na + newLen]);
  }, [all.length, plotW, win, base]);
  const svgRef = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [onWheel]);

  const onKey = (e: React.KeyboardEvent) => {
    if (!n) return;
    if (e.key === 'ArrowLeft') { setHover((h) => Math.max(0, (h ?? n) - 1)); e.preventDefault(); }
    if (e.key === 'ArrowRight') { setHover((h) => Math.min(n - 1, (h ?? -1) + 1)); e.preventDefault(); }
    if (e.key === 'Escape') { setWin(null); setHover(null); }
  };

  const hb = hover != null ? bars[hover] : bars[n - 1];
  const prev = hover != null ? (hover > 0 ? bars[hover - 1] : null) : (n > 1 ? bars[n - 2] : null);
  const chg = hb && prev ? hb.c / prev.c - 1 : null;
  const rangeChg = n > 1 ? bars[n - 1].c / bars[0].o - 1 : null;

  const linePath = bars.map((b, i) => `${i ? 'L' : 'M'}${xOf(i).toFixed(1)},${yOf(b.c).toFixed(1)}`).join('');
  const Btn = ({ on, disabled, onClick, children, title }: any) => (
    <button onClick={onClick} disabled={disabled} title={title}
      className={cn('px-1.5 py-0.5 text-[10px] font-mono', on ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary', disabled && 'opacity-30 cursor-not-allowed hover:text-text-secondary')}>
      {children}
    </button>
  );

  return (
    <div ref={wrapRef} className="w-full select-none">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
        <div className="flex border border-border" role="group" aria-label="Bar interval">
          {INTERVALS.map((i) => <Btn key={i.key} on={interval === i.key} onClick={() => pickInterval(i.key)} title={`${i.label} bars`}>{i.label}</Btn>)}
        </div>
        <div className="flex border border-border" role="group" aria-label="Period">
          {PERIODS.map((p) => (
            <Btn key={p.key} on={!range && period === p.key} disabled={!allowed(interval, p.key)} onClick={() => { setRange(null); setPeriod(p.key); }}
              title={allowed(interval, p.key) ? p.label : `${interval} bars only go back ${MAX_DAYS[interval]} days`}>{p.label}</Btn>
          ))}
        </div>
        <div className="flex items-center gap-1 text-[10px] text-text-tertiary" role="group" aria-label="Custom date range">
          <input type="date" aria-label="From" value={range?.start ?? ''} max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => e.target.value && setRange({ start: e.target.value, end: range?.end ?? new Date().toISOString().slice(0, 10) })}
            className="bg-transparent border border-border px-1 py-0.5 font-mono text-text-secondary w-[7.6rem]" />
          <span>–</span>
          <input type="date" aria-label="To" value={range?.end ?? ''} max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => e.target.value && setRange({ start: range?.start ?? e.target.value, end: e.target.value })}
            className="bg-transparent border border-border px-1 py-0.5 font-mono text-text-secondary w-[7.6rem]" />
          {range && <button onClick={() => setRange(null)} className="px-1.5 py-0.5 border border-border text-text-secondary hover:text-text-primary">Reset</button>}
        </div>
        <div className="flex border border-border" role="group" aria-label="Chart type">
          {(['candle', 'line', 'area'] as const).map((t) => <Btn key={t} on={kind === t} onClick={() => setKind(t)}>{t === 'candle' ? 'Candles' : t === 'line' ? 'Line' : 'Area'}</Btn>)}
        </div>
        <div className="flex border border-border" role="group" aria-label="Overlays">
          {MA.map((m) => (
            <Btn key={m.n} on={mas[m.n]} onClick={() => setMas({ ...mas, [m.n]: !mas[m.n] })} title={`${m.n}-bar moving average`}>
              <span style={{ color: mas[m.n] ? undefined : m.color }}>MA{m.n}</span>
            </Btn>
          ))}
          <Btn on={showVol} onClick={() => setShowVol(!showVol)}>Vol</Btn>
          <Btn on={logScale} onClick={() => setLogScale(!logScale)} title="Logarithmic price scale">Log</Btn>
        </div>
        {win && <button onClick={() => setWin(null)} className="inline-flex items-center gap-1 text-[10px] text-text-tertiary hover:text-bloomberg"><RotateCcw className="w-3 h-3" />reset zoom</button>}
        {loading && <Loader2 className="w-3 h-3 animate-spin text-text-tertiary" />}
      </div>

      {/* Readout */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[11px] font-mono mb-1 min-h-[16px]">
        {hb && (
          <>
            <span className="text-text-tertiary">{fmtTime(hb.t, interval, true)}{k > 1 ? ` (+${k - 1} bars)` : ''}</span>
            <span><span className="text-text-tertiary">O</span> {fmtPx(hb.o)}</span>
            <span><span className="text-text-tertiary">H</span> {fmtPx(hb.h)}</span>
            <span><span className="text-text-tertiary">L</span> {fmtPx(hb.l)}</span>
            <span><span className="text-text-tertiary">C</span> <span className="text-text-primary">{fmtPx(hb.c)}</span></span>
            {chg != null && <span className={chg >= 0 ? 'text-green' : 'text-red'}>{chg >= 0 ? '+' : ''}{(chg * 100).toFixed(2)}%</span>}
            {hb.v > 0 && <span><span className="text-text-tertiary">Vol</span> {fmtVol(hb.v)}</span>}
            {rangeChg != null && hover == null && <span className="text-text-tertiary">· view {rangeChg >= 0 ? '+' : ''}{(rangeChg * 100).toFixed(1)}%</span>}
            {meta?.currency && <span className="text-text-tertiary ml-auto">{meta.currency}{meta.timezone ? ` · ${meta.timezone}` : ''}</span>}
          </>
        )}
      </div>

      {err && <div className="p-2 text-xs text-amber border border-amber/30">{err}</div>}
      {!err && (
        <svg ref={svgRef} width={width} height={height} tabIndex={0} onKeyDown={onKey} role="img"
          aria-label={`${symbol} ${interval} price chart`}
          onMouseMove={onMove} onMouseLeave={() => { setHover(null); drag.current = null; }}
          onMouseDown={(e) => { const r = (e.currentTarget as SVGElement).getBoundingClientRect(); drag.current = { x: e.clientX - r.left, win: win ?? [s0, s1] }; }}
          onMouseUp={() => { drag.current = null; }} onDoubleClick={() => setWin(null)}
          className={cn('outline-none', drag.current ? 'cursor-grabbing' : 'cursor-crosshair')}>
          {/* grid + y axis */}
          {ticks.map((v) => (
            <g key={v}>
              <line x1={PAD_L} x2={PAD_L + plotW} y1={yOf(v)} y2={yOf(v)} stroke="var(--border, #1f2630)" strokeWidth={1} opacity={0.5} />
              <text x={PAD_L + plotW + 6} y={yOf(v) + 3} fontSize={10} fill="var(--text-tertiary, #6b7280)" fontFamily="monospace">{fmtPx(v)}</text>
            </g>
          ))}
          {/* x labels */}
          {xTicks.map((i, j) => {
            // Intraday: the date where the day changes between ticks, the time otherwise.
            const day = bars[i].t.slice(0, 10);
            const newDay = MAX_DAYS[interval] && (j === 0 ? bars[0].t.slice(0, 10) !== bars[n - 1].t.slice(0, 10) : day !== bars[xTicks[j - 1]].t.slice(0, 10));
            const label = newDay ? fmtTime(day, '1d') : fmtTime(bars[i].t, interval);
            return (
              <text key={i} x={xOf(i)} y={height - 6} fontSize={10} textAnchor="middle" fontFamily="monospace"
                fill={newDay ? 'var(--text-secondary, #9aa4b2)' : 'var(--text-tertiary, #6b7280)'}>{label}</text>
            );
          })}
          {/* volume */}
          {showVol && bars.map((b, i) => (
            <rect key={`v${i}`} x={xOf(i) - Math.max(0.5, slot * 0.35)} width={Math.max(1, slot * 0.7)}
              y={volTop + volH - (b.v / vMax) * volH} height={(b.v / vMax) * volH}
              fill={b.c >= b.o ? UP : DOWN} opacity={0.35} />
          ))}
          {/* price */}
          {kind === 'candle' && bars.map((b, i) => {
            const up = b.c >= b.o, x = xOf(i), bw = Math.max(1, slot * 0.62);
            const yo = yOf(b.o), yc = yOf(b.c);
            return (
              <g key={i}>
                <line x1={x} x2={x} y1={yOf(b.h)} y2={yOf(b.l)} stroke={up ? UP : DOWN} strokeWidth={1} />
                <rect x={x - bw / 2} width={bw} y={Math.min(yo, yc)} height={Math.max(1, Math.abs(yc - yo))} fill={up ? UP : DOWN} />
              </g>
            );
          })}
          {kind === 'area' && n > 1 && (
            <path d={`${linePath}L${xOf(n - 1).toFixed(1)},${(PAD_T + priceH).toFixed(1)}L${xOf(0).toFixed(1)},${(PAD_T + priceH).toFixed(1)}Z`} fill="#3987e5" opacity={0.1} />
          )}
          {kind !== 'candle' && <path d={linePath} fill="none" stroke="#3987e5" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
          {/* moving averages (computed on the full history, so the first bars of a zoom are right) */}
          {activeMa.map((m) => {
            const pts = bars.map((_, i) => {
              const v = maLines[m.n][s0 + first[i] + Math.min(k, visible.length - first[i]) - 1];
              return v == null ? null : `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`;
            });
            const d = pts.reduce((acc, p, i) => (p ? acc + `${acc && pts[i - 1] ? 'L' : 'M'}${p}` : acc), '');
            return d ? <path key={m.n} d={d} fill="none" stroke={m.color} strokeWidth={1.25} opacity={0.9} /> : null;
          })}
          {/* signal markers (daily) */}
          {markers && interval === '1d' && bars.map((b, i) => (markers[b.t.slice(0, 10)] ? (
            <path key={`m${i}`} d={`M${xOf(i)},${yOf(b.l) + 4}l4,7h-8z`} fill={UP} opacity={0.85} />
          ) : null))}
          {/* plan levels */}
          {refs.filter((r) => r.value >= lo && r.value <= hi).map((r) => (
            <g key={r.label}>
              <line x1={PAD_L} x2={PAD_L + plotW} y1={yOf(r.value)} y2={yOf(r.value)} stroke={r.color ?? '#9aa4b2'} strokeDasharray="4 3" strokeWidth={1} />
              <rect x={PAD_L + plotW + 1} y={yOf(r.value) - 7} width={AXIS_W - 2} height={14} fill={r.color ?? '#9aa4b2'} opacity={0.18} />
              <text x={PAD_L + plotW + 4} y={yOf(r.value) + 3} fontSize={9} fill={r.color ?? '#9aa4b2'} fontFamily="monospace">{r.label} {fmtPx(r.value)}</text>
            </g>
          ))}
          {/* crosshair */}
          {hover != null && bars[hover] && (
            <g pointerEvents="none">
              <line x1={xOf(hover)} x2={xOf(hover)} y1={PAD_T} y2={height - PAD_B} stroke="#9aa4b2" strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
              <line x1={PAD_L} x2={PAD_L + plotW} y1={yOf(bars[hover].c)} y2={yOf(bars[hover].c)} stroke="#9aa4b2" strokeWidth={1} strokeDasharray="2 3" opacity={0.6} />
              <rect x={PAD_L + plotW + 1} y={yOf(bars[hover].c) - 8} width={AXIS_W - 2} height={16} fill="#3987e5" />
              <text x={PAD_L + plotW + 5} y={yOf(bars[hover].c) + 4} fontSize={10} fill="#fff" fontFamily="monospace">{fmtPx(bars[hover].c)}</text>
            </g>
          )}
        </svg>
      )}
      <div className="text-[10px] text-text-tertiary mt-0.5">Scroll to zoom · drag to pan · double-click or Esc to reset · ← → step bars{k > 1 ? ` · ${k} bars per candle at this zoom` : ''}</div>
    </div>
  );
}

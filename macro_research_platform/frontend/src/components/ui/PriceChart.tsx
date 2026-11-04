// Interactive price chart on Apache ECharts: choose the bar interval (5m, 15m, 1H, 1D, 1W, 1M) and the period
// (1D … Max); candles / line / area; a volume pane; 20/50/200-bar moving averages; log scale; plan levels
// (entry / stop / target) and signal markers. Scroll to zoom around the cursor, drag to pan, the slider below
// picks any window, double-click resets; the crosshair reads out OHLC, change and volume; arrow keys step bar
// by bar. ECharts samples large histories itself, so the chart stays fast at any period.

import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, RotateCcw } from 'lucide-react';
import { cn, localToday } from '@/lib/utils';
import { EChart, alpha, axisStyle, color, useChartTheme, type ECharts } from '@/components/charts/EChart';

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
const UP_CSS = 'rgb(var(--c-green))', DOWN_CSS = 'rgb(var(--c-red))';
const WARM = new Set(['1d', '1wk', '1mo']);     // intervals fetched with 200 extra bars so MAs start on the first bar
const MA = [{ n: 20, color: '#c98500' }, { n: 50, color: '#3987e5' }, { n: 200, color: '#d55181' }];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
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
  const [revision,retry]=useState(0);
  const [win, setWin] = useState<[number, number] | null>(null);       // visible [start, end] in bars, null = the chosen window
  const [base, setBase] = useState(0);                                  // first bar of the chosen window (earlier bars warm up the MAs)
  const [hover, setHover] = useState<number | null>(null);              // bar under the crosshair
  const chartRef = useRef<ECharts | null>(null);
  const t = useChartTheme();

  useEffect(() => {
    let cancelled = false;const controller=new AbortController();
    setData(null);setMeta(null);setHover(null);setLoading(true);setErr(null);
    fetch(`/api/v1/market/bars?${new URLSearchParams({ ...(range ? { symbol, interval, start: range.start, end: range.end } : { symbol, interval, period }),
      ...(WARM.has(interval) && (range || period !== 'max') ? { warmup: '200' } : {}) })}`,{signal:controller.signal})
      .then(async (r) => {
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : j?.detail?.message || `HTTP ${r.status}`);
        return j;
      })
      .then((j) => { if (!cancelled) { setData(j.bars); setBase(j.first_visible ?? 0); setMeta({ currency: j.currency, timezone: j.timezone }); setWin(null); setHover(null); } })
      .catch((e) => { if (!cancelled) { setErr(e.message); setData(null); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true;controller.abort(); };
  }, [symbol, interval, period, range,revision]);

  const pickInterval = (i: string) => {
    setInterval_(i);
    if (!allowed(i, period)) setPeriod(DEFAULT_PERIOD[i]);
  };

  const all = useMemo(() => data ?? [], [data]);
  const closes = useMemo(() => all.map((b) => b.c), [all]);
  const maLines = useMemo(() => Object.fromEntries(MA.map((m) => [m.n, sma(closes, m.n)])), [closes]);
  const n = all.length;
  const start = Math.min(base, Math.max(0, n - 1));
  const [s0, s1] = win ?? [start, n - 1];
  const UP = color(UP_CSS, '#22c55e'), DOWN = color(DOWN_CSS, '#ef4444');

  const option = useMemo(() => {
    const ax = axisStyle(t);
    const cats = all.map((b) => b.t);
    const label = (v: string) => fmtTime(v, interval);
    const priceBottom = showVol ? 106 : 52;
    const upDown = (b: Bar) => (b.c >= b.o ? UP : DOWN);
    const levels = refs.map((r) => ({ yAxis: r.value, lineStyle: { color: color(r.color, t.mutedText), type: [4, 3] as any, width: 1 },
      label: { show: true, position: 'end' as const, formatter: `${r.label} ${fmtPx(r.value)}`, color: t.surface1, backgroundColor: color(r.color, t.mutedText),
        padding: [2, 4], borderRadius: 2, fontSize: 9, fontFamily: t.mono } }));
    const marks = markers && interval === '1d' ? all.map((b, i) => (markers[b.t.slice(0, 10)] ? { coord: [i, b.l], value: 'BUY' } : null)).filter(Boolean) : [];
    const priceSeries: any = kind === 'candle'
      ? { name: symbol, type: 'candlestick', data: all.map((b) => [b.o, b.c, b.l, b.h]), barMaxWidth: 14,
          itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN } }
      : { name: symbol, type: 'line', data: closes, showSymbol: false, lineStyle: { width: 2, color: t.series[0] }, itemStyle: { color: t.series[0] },
          ...(kind === 'area' ? { areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: alpha(t.series[0], 0.25) }, { offset: 1, color: alpha(t.series[0], 0) }] } } } : {}) };
    priceSeries.markLine = levels.length ? { symbol: 'none', silent: true, data: levels, animation: false } : undefined;
    priceSeries.markPoint = marks.length ? { symbol: 'triangle', symbolSize: 9, symbolOffset: [0, 10], itemStyle: { color: UP }, label: { show: false }, data: marks } : undefined;
    const series: any[] = [priceSeries,
      ...MA.filter((m) => mas[m.n]).map((m) => ({ name: `MA${m.n}`, type: 'line', data: maLines[m.n], showSymbol: false, lineStyle: { width: 1.25, color: m.color }, itemStyle: { color: m.color }, silent: true })),
      ...(showVol ? [{ name: 'Volume', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: all.map((b) => ({ value: b.v, itemStyle: { color: alpha(upDown(b), 0.45) } })), barMaxWidth: 14 }] : [])];
    const xBase = { type: 'category', data: cats, boundaryGap: true, ...ax, splitLine: { show: false }, axisPointer: { label: { show: false } } };
    return {
      animation: false,
      legend: { show: false }, toolbox: { show: false },
      axisPointer: { link: [{ xAxisIndex: 'all' }], lineStyle: { color: t.mutedText, type: 'dashed' } },
      tooltip: { show: true, trigger: 'axis', axisPointer: { type: 'cross', crossStyle: { color: t.mutedText } }, showContent: false },
      grid: showVol ? [{ left: 6, right: 64, top: 6, bottom: priceBottom }, { left: 6, right: 64, height: 46, bottom: 48 }] : [{ left: 6, right: 64, top: 6, bottom: priceBottom }],
      xAxis: [{ ...xBase, gridIndex: 0, axisLabel: { show: !showVol, ...ax.axisLabel, fontFamily: t.mono, hideOverlap: true, formatter: label } },
        ...(showVol ? [{ ...xBase, gridIndex: 1, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, hideOverlap: true, formatter: label } }] : [])],
      yAxis: [{ type: logScale ? 'log' : 'value', scale: true, position: 'right', gridIndex: 0, ...ax,
          axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => fmtPx(v) },
          axisPointer: { label: { formatter: (p: any) => fmtPx(p.value), backgroundColor: t.series[0], fontFamily: t.mono } } },
        ...(showVol ? [{ type: 'value', gridIndex: 1, position: 'right', ...ax, splitNumber: 2, splitLine: { show: false },
          axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => fmtVol(v) }, axisPointer: { label: { show: false } } }] : [])],
      dataZoom: [{ type: 'inside', xAxisIndex: showVol ? [0, 1] : [0], startValue: s0, endValue: s1, minValueSpan: 10 },
        { type: 'slider', xAxisIndex: showVol ? [0, 1] : [0], startValue: s0, endValue: s1, height: 16, bottom: 4, borderColor: t.border,
          fillerColor: alpha(t.series[0], 0.12), handleStyle: { color: t.surface, borderColor: t.mutedText }, textStyle: { color: t.mutedText, fontSize: 9 },
          labelFormatter: (_: number, v: string) => fmtTime(v, interval), dataBackground: { lineStyle: { color: t.mutedText }, areaStyle: { color: alpha(t.series[0], 0.08) } } }],
      series,
    };
  // the zoom window is applied on load and reset only (s0/s1 left out, so panning never rebuilds the chart)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, closes, maLines, kind, mas, showVol, logScale, refs, markers, interval, symbol, t, base, UP, DOWN]);

  const onReady = (c: ECharts) => {
    chartRef.current = c;
    c.on('updateAxisPointer', (e: any) => { const i = e.axesInfo?.[0]?.value; setHover(typeof i === 'number' ? i : null); });
    c.on('datazoom', () => { const dz = (c.getOption() as any).dataZoom?.[0]; if (dz?.startValue != null) setWin([Number(dz.startValue), Number(dz.endValue)]); });
    c.getZr().on('globalout', () => setHover(null));
    c.getZr().on('dblclick', () => resetZoom());
  };
  const resetZoom = () => {
    setWin(null);
    chartRef.current?.dispatchAction({ type: 'dataZoom', startValue: start, endValue: n - 1 });
  };
  const step = (d: number) => {
    const i = Math.max(s0, Math.min(s1, (hover ?? s1) + d));
    setHover(i);
    chartRef.current?.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: i });
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (!n) return;
    if (e.key === 'ArrowLeft') { step(-1); e.preventDefault(); }
    if (e.key === 'ArrowRight') { step(1); e.preventDefault(); }
    if (e.key === 'Escape') { resetZoom(); setHover(null); }
  };

  const hi_ = hover != null && hover < n ? hover : n - 1;
  const hb = n ? all[hi_] : undefined;
  const prev = hi_ > 0 ? all[hi_ - 1] : null;
  const chg = hb && prev ? hb.c / prev.c - 1 : null;
  const rangeChg = n > 1 && s1 > s0 ? all[s1].c / all[s0].o - 1 : null;
  const Btn = ({ on, disabled, onClick, children, title }: any) => (
    <button onClick={onClick} disabled={disabled} title={title}
      className={cn('px-1.5 py-0.5 text-[10px] font-mono', on ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary', disabled && 'opacity-30 cursor-not-allowed hover:text-text-secondary')}>
      {children}
    </button>
  );

  return (
    <div className="w-full select-none">
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
          <input type="date" aria-label="From" value={range?.start ?? ''} max={localToday()}
            onChange={(e) => e.target.value && setRange({ start: e.target.value, end: range?.end ?? localToday() })}
            className="bg-transparent border border-border px-1 py-0.5 font-mono text-text-secondary w-[7.6rem]" />
          <span>–</span>
          <input type="date" aria-label="To" value={range?.end ?? ''} max={localToday()}
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
        {win && <button onClick={resetZoom} className="inline-flex items-center gap-1 text-[10px] text-text-tertiary hover:text-bloomberg"><RotateCcw className="w-3 h-3" />reset zoom</button>}
        {loading && <Loader2 className="w-3 h-3 animate-spin text-text-tertiary" />}
      </div>

      {/* Readout */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[11px] font-mono mb-1 min-h-[16px]">
        {hb && (
          <>
            <span className="text-text-tertiary">{fmtTime(hb.t, interval, true)}</span>
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

      {err && <div role="alert" className="p-2 text-xs text-amber border border-amber/30 flex justify-between gap-3"><span>{err}</span><button onClick={()=>retry(n=>n+1)} className="underline">Retry chart</button></div>}
      {!err && (
        <div tabIndex={0} onKeyDown={onKey} className="outline-none focus-visible:ring-1 focus-visible:ring-bloomberg/50 rounded">
          {n ? <EChart option={option} height={height} onReady={onReady} ariaLabel={`${symbol} ${interval} price chart`} />
            : <div style={{ height }} className="flex items-center justify-center text-2xs text-text-tertiary">{loading ? 'Loading bars…' : 'No bars for this period.'}</div>}
        </div>
      )}
      <div className="text-[10px] text-text-tertiary mt-0.5">Scroll to zoom · drag to pan · slider picks a window · double-click or Esc to reset · ← → step bars</div>
    </div>
  );
}

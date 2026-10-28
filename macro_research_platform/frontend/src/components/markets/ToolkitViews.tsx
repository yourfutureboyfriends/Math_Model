// TECH (technical analysis), SPRD (pairs / spreads), CBRT (central bank rates), ECOS (FRED explorer).
import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, fmtPrice, Loading, Panel, useJSON } from './shared';

const enc = encodeURIComponent;
const pc = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);
const sp = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(d)}%`);
const bp = (x: number | null | undefined) => (x == null ? '—' : `${x > 0 ? '+' : ''}${Math.round(x)}bp`);
const tone = (x: number | null | undefined) => (x == null ? 'text-text-tertiary' : x >= 0 ? 'text-green' : 'text-red');

function Tile({ label, value, sub, cls }: { label: string; value: React.ReactNode; sub?: React.ReactNode; cls?: string }) {
  return (
    <div className="border border-border bg-surface-1 rounded-md px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className={cn('font-mono text-text-primary', cls)}>{value}</div>
      {sub != null && <div className="text-[10px] text-text-tertiary leading-tight">{sub}</div>}
    </div>
  );
}
function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button onClick={onClick} className={cn('px-2 py-0.5 border rounded-sm text-[11px]', on ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{children}</button>;
}

// ── TECH ────────────────────────────────────────────────────────────────────
const SIG_CLS: Record<string, string> = { buy: 'text-green', sell: 'text-red', neutral: 'text-text-tertiary' };
const LABEL_CLS = (l: string) => (/buy/i.test(l) ? 'text-green' : /sell/i.test(l) ? 'text-red' : 'text-text-secondary');

function Gauge({ title, s }: { title: string; s: any }) {
  const pos = ((s.score + 1) / 2) * 100;
  return (
    <div className="border border-border bg-surface-1 rounded-md px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{title}</div>
      <div className={cn('text-lg font-semibold', LABEL_CLS(s.label))}>{s.label}</div>
      <div className="relative h-1.5 mt-1 rounded-full bg-gradient-to-r from-red/50 via-surface-3 to-green/50">
        <span className="absolute -top-0.5 w-1 h-2.5 bg-text-primary rounded-sm" style={{ left: `calc(${pos}% - 2px)` }} /></div>
      <div className="text-[10px] text-text-tertiary mt-1">{s.buy} buy · {s.neutral} neutral · {s.sell} sell</div>
    </div>
  );
}

export function TechView({ symbol }: { symbol: string }) {
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/tech/${enc(symbol)}`, 900_000);
  if (loading && !d) return <Loading label="Computing indicators and ten years of signal history…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const L = d.levels, f = (v: number | null | undefined) => (v == null ? '—' : fmtPrice(v));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
        <Gauge title="Overall" s={d.summary.overall} /><Gauge title="Oscillators" s={d.summary.oscillators} /><Gauge title="Moving averages" s={d.summary.moving_averages} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
        <Tile label="Trend" value={<span className={cn('capitalize', d.trend.state === 'uptrend' ? 'text-green' : d.trend.state === 'downtrend' ? 'text-red' : '')}>{d.trend.state}</span>} sub={`${sp(d.trend.pct_from_200d)} vs 200-day`} />
        <Tile label="Trend strength (ADX)" value={d.trend.adx?.toFixed(0)} sub={d.trend.adx > 25 ? 'strong trend' : d.trend.adx > 20 ? 'trending' : 'no clear trend'} />
        <Tile label="Last golden cross" value={d.trend.last_golden_cross ?? '—'} sub={`death cross ${d.trend.last_death_cross ?? '—'}`} />
        <Tile label="52-week range" value={`${f(L.low_52w)} – ${f(L.high_52w)}`} sub={`${sp(L.from_high)} from high`} />
        <Tile label="ATR (14)" value={f(L.atr)} sub={`${pc(L.atr_pct)} of price a day`} />
        <Tile label="2×ATR stop" value={f(L.stop_long_2atr)} sub={`for a long; short ${f(L.stop_short_2atr)}`} />
        <Tile label="Bollinger %B" value={d.bollinger.pct_b?.toFixed(2) ?? '—'} sub={`bandwidth ${pc(d.bollinger.bandwidth)}`} />
        <Tile label="Volume" value={`${d.volume.rel_volume?.toFixed(2) ?? '—'}×`} sub={`vs 20-day average · OBV ${d.volume.obv_trend_20d}`} />
      </div>
      <Panel title={`${d.name ?? symbol} — price, 50 / 200-day averages and Bollinger bands (one year)`}>
        <LineChart rows={d.chart} x="date" height={300} fmt={(v) => fmtPrice(v)}
          lines={[{ key: 'close', label: 'Close', color: 'rgb(var(--c-text-primary))' }, { key: 'sma50', label: '50-day', color: 'rgb(var(--c-blue))' },
            { key: 'sma200', label: '200-day', color: 'rgb(var(--c-amber))' }, { key: 'bb_up', label: 'Bollinger upper', color: 'rgb(var(--c-text-tertiary) / 0.6)' },
            { key: 'bb_lo', label: 'Bollinger lower', color: 'rgb(var(--c-text-tertiary) / 0.6)' }]}
          refs={[L.swings.find((x: any) => x.kind === 'support'), L.swings.find((x: any) => x.kind === 'resistance')].filter(Boolean).map((s: any) => ({ value: s.level, label: `${s.kind} ${fmtPrice(s.level)}`, color: s.kind === 'support' ? 'rgb(var(--c-green) / 0.7)' : 'rgb(var(--c-red) / 0.7)' }))} />
      </Panel>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title="RSI (14)"><LineChart rows={d.chart} x="date" height={170} controls={false} fmt={(v) => v.toFixed(1)}
          refs={[{ value: 70, label: 'overbought 70', color: 'rgb(var(--c-red) / 0.6)' }, { value: 30, label: 'oversold 30', color: 'rgb(var(--c-green) / 0.6)' }]}
          lines={[{ key: 'rsi', label: 'RSI', color: 'rgb(168 85 247)' }]} /></Panel>
        <Panel title="MACD (12, 26, 9)"><LineChart rows={d.chart} x="date" height={170} controls={false} fmt={(v) => v.toFixed(2)} baseline={0}
          lines={[{ key: 'macd', label: 'MACD', color: 'rgb(var(--c-blue))' }, { key: 'signal', label: 'Signal', color: 'rgb(var(--c-amber))' }, { key: 'hist', label: 'Histogram', color: 'rgb(var(--c-text-tertiary))' }]} /></Panel>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <Panel title="Oscillators">
          <table className="w-full text-2xs"><tbody>{d.oscillators.map((o: any) => (
            <tr key={o.name} className="border-t border-border-subtle first:border-0" title={o.detail}><td className="py-1 text-text-secondary">{o.name}</td>
              <td className="text-right font-mono">{o.value?.toFixed(1) ?? '—'}</td><td className={cn('text-right w-16 capitalize font-semibold', SIG_CLS[o.signal])}>{o.signal}</td></tr>))}</tbody></table>
        </Panel>
        <Panel title="Moving averages">
          <table className="w-full text-2xs"><tbody>{d.moving_averages.map((o: any) => (
            <tr key={o.name} className="border-t border-border-subtle first:border-0"><td className="py-1 text-text-secondary">{o.name}</td>
              <td className="text-right font-mono">{f(o.value)}</td><td className={cn('text-right font-mono w-16', tone(o.distance))}>{sp(o.distance)}</td>
              <td className={cn('text-right w-14 capitalize font-semibold', SIG_CLS[o.signal])}>{o.signal}</td></tr>))}</tbody></table>
        </Panel>
        <Panel title="Support & resistance">
          <table className="w-full text-2xs"><tbody>
            {[...L.swings].sort((a: any, b: any) => b.level - a.level).map((s: any) => (
              <tr key={`${s.kind}${s.level}`} className="border-t border-border-subtle first:border-0"><td className={cn('py-1 capitalize', s.kind === 'support' ? 'text-green' : 'text-red')}>{s.kind}</td>
                <td className="text-right font-mono">{f(s.level)}</td><td className="text-right text-text-tertiary">{s.touches} touch{s.touches > 1 ? 'es' : ''}</td>
                <td className="text-right font-mono">{sp(s.level / d.price - 1)}</td></tr>))}
            <tr className="border-t border-border"><td className="py-1 text-text-tertiary" colSpan={4}>Floor pivots: {['S2', 'S1', 'P', 'R1', 'R2'].map((k) => `${k} ${f(L.pivots[k])}`).join(' · ')}</td></tr>
          </tbody></table>
          <div className="text-[10px] text-text-tertiary mt-1">Swing highs / lows of the last year, merged within half an ATR; more touches = stronger level.</div>
        </Panel>
      </div>
      <Panel title={`Do these signals work on ${symbol}? — what followed each one over ${d.study_years} years`}>
        <table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Signal</th><th className="text-right font-normal">Times</th><th className="text-right font-normal">Last</th>
            <th className="text-right font-normal">Avg 20 days</th><th className="text-right font-normal">Up after 20d</th><th className="text-right font-normal">Avg 60 days</th><th className="text-right font-normal">Up after 60d</th><th className="text-left font-normal pl-3">vs a typical day</th></tr></thead>
          <tbody>{d.study.map((s: any) => {
            const edge = s.avg_20d != null && s.base_20d != null ? s.avg_20d - s.base_20d : null;
            return (
              <tr key={s.signal} className="border-t border-border-subtle"><td className="py-1 font-sans text-text-primary">{s.signal}</td><td className="text-right">{s.count}</td>
                <td className="text-right text-text-tertiary">{s.last ?? '—'}</td><td className={cn('text-right', tone(s.avg_20d))}>{sp(s.avg_20d)}</td>
                <td className="text-right">{pc(s.hit_20d, 0)}</td><td className={cn('text-right', tone(s.avg_60d))}>{sp(s.avg_60d)}</td><td className="text-right">{pc(s.hit_60d, 0)}</td>
                <td className={cn('pl-3 font-sans', s.count < 8 ? 'text-text-tertiary' : edge == null ? '' : edge > 0.01 ? 'text-green' : edge < -0.01 ? 'text-red' : 'text-text-secondary')}>
                  {s.count < 8 ? 'too few cases to judge' : edge == null ? '—' : `${edge >= 0 ? '+' : ''}${(edge * 100).toFixed(1)} pts over 20 days`}</td></tr>);
          })}</tbody>
        </table>
        <div className="text-[10px] text-text-tertiary mt-1">A typical 20-day return here was {sp(d.study[0]?.base_20d)} (up {pc(d.study[0]?.base_hit_20d, 0)} of the time). Repeat signals within 10 days count once. {d.note}</div>
      </Panel>
      <div className="text-[10px] text-text-tertiary">Source: {d.source}; data to {d.date}.</div>
    </div>
  );
}

// ── SPRD ────────────────────────────────────────────────────────────────────
export function SprdView({ seed }: { seed?: string }) {
  const init = (seed ?? '').split(/[,/ ]+/).filter(Boolean);
  const [a, setA] = useState(init[0]?.toUpperCase() || 'KO');
  const [b, setB] = useState(init[1]?.toUpperCase() || 'PEP');
  const [ia, setIa] = useState(a), [ib, setIb] = useState(b);
  const [yrs, setYrs] = useState(5);
  const [entry, setEntry] = useState(2);
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/sprd?a=${enc(a)}&b=${enc(b)}&years=${yrs}&entry=${entry}`);
  const go = () => { setA(ia.trim().toUpperCase()); setB(ib.trim().toUpperCase()); };
  const PAIRS = [['KO', 'PEP'], ['XOM', 'CVX'], ['GLD', 'SLV'], ['V', 'MA'], ['HD', 'LOW'], ['SPY', 'QQQ'], ['EWA', 'EWC'], ['BHP', 'RIO']];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
        <input value={ia} onChange={(e) => setIa(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()} className="w-24 bg-surface-1 border border-border px-2 py-0.5 font-mono" />
        <span className="text-text-tertiary">vs</span>
        <input value={ib} onChange={(e) => setIb(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && go()} className="w-24 bg-surface-1 border border-border px-2 py-0.5 font-mono" />
        <button onClick={go} className="px-3 py-0.5 bg-bloomberg text-text-inverse">Analyse</button>
        <span className="ml-2 text-text-tertiary">Window</span>{[2, 5, 10].map((y) => <Chip key={y} on={yrs === y} onClick={() => setYrs(y)}>{y}y</Chip>)}
        <span className="ml-2 text-text-tertiary">Entry |z|</span>{[1.5, 2, 2.5].map((z) => <Chip key={z} on={entry === z} onClick={() => setEntry(z)}>{z}</Chip>)}
        <span className="ml-auto flex flex-wrap gap-1">{PAIRS.map(([x, y]) => <Chip key={x + y} on={a === x && b === y} onClick={() => { setA(x); setB(y); setIa(x); setIb(y); }}>{x}/{y}</Chip>)}</span>
      </div>
      {loading && !d ? <Loading label="Testing the pair…" /> : error && !d ? <ErrorBox msg={error} /> : d && <>
        <div className={cn('px-3 py-2 border rounded-md text-xs', d.coint_p != null && d.coint_p < 0.05 ? 'border-green/50 bg-green/5 text-green' : 'border-amber/50 bg-amber/5 text-amber')}>
          {d.name_a} vs {d.name_b}: {d.verdict}{d.coint_p != null ? ` (Engle–Granger p = ${d.coint_p.toFixed(3)})` : ''}.</div>
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
          <Tile label="Spread z-score now" value={d.z_now?.toFixed(2) ?? '—'} cls={d.z_now == null ? '' : Math.abs(d.z_now) >= 2 ? 'text-amber' : ''} sub="60-day window" />
          <Tile label="Full-period z" value={d.z_full_now.toFixed(2)} sub={`since ${d.start}`} />
          <Tile label="Hedge ratio" value={d.hedge_ratio.toFixed(3)} sub={`1 ${d.a} ≈ ${d.hedge_ratio.toFixed(2)} ${d.b} (log terms)`} />
          <Tile label="Half-life" value={d.half_life_days ? `${Math.round(d.half_life_days)} days` : 'none'} sub="time for half a gap to close" />
          <Tile label="Price ratio" value={d.ratio_now.toFixed(4)} sub={`${Math.round(d.ratio_percentile * 100)}th percentile of the window`} />
          <Tile label="Correlation" value={d.corr_now?.toFixed(2) ?? '—'} sub={`60-day · full ${d.corr_full.toFixed(2)}`} />
          <Tile label={`${d.a} return`} value={sp(d.return_a, 0)} cls={tone(d.return_a)} sub="over the window" />
          <Tile label={`${d.b} return`} value={sp(d.return_b, 0)} cls={tone(d.return_b)} sub="over the window" />
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          <Panel title="Both rebased to 100"><LineChart rows={d.rows} x="date" height={230} fmt={(v) => v.toFixed(1)}
            lines={[{ key: 'a', label: d.a, color: 'rgb(var(--c-blue))' }, { key: 'b', label: d.b, color: 'rgb(var(--c-amber))' }]} /></Panel>
          <Panel title="Spread z-score (60-day, out of sample)"><LineChart rows={d.rows} x="date" height={230} fmt={(v) => v.toFixed(2)} baseline={0}
            refs={[{ value: entry, label: `+${entry}`, color: 'rgb(var(--c-red) / 0.6)' }, { value: -entry, label: `−${entry}`, color: 'rgb(var(--c-green) / 0.6)' }]}
            lines={[{ key: 'z', label: 'z-score', color: 'rgb(168 85 247)' }]} /></Panel>
          <Panel title={`Price ratio ${d.a} ÷ ${d.b}`}><LineChart rows={d.rows} x="date" height={200} fmt={(v) => v.toFixed(4)} lines={[{ key: 'ratio', label: 'Ratio', color: 'rgb(var(--c-text-primary))' }]} /></Panel>
          <Panel title="Mean-reversion backtest — equity (per $1 gross)"><LineChart rows={d.rows} x="date" height={200} fmt={(v) => v.toFixed(1)} baseline={100} lines={[{ key: 'equity', label: 'Strategy', color: 'rgb(var(--c-green))' }]} /></Panel>
        </div>
        <Panel title="Backtest">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-2">
            <Tile label="Trades" value={d.backtest.trades} /><Tile label="Win rate" value={pc(d.backtest.win_rate, 0)} />
            <Tile label="Total return" value={sp(d.backtest.total_return)} cls={tone(d.backtest.total_return)} /><Tile label="CAGR" value={sp(d.backtest.cagr)} cls={tone(d.backtest.cagr)} />
            <Tile label="Volatility" value={pc(d.backtest.vol)} /><Tile label="Max drawdown" value={pc(d.backtest.max_drawdown)} cls="text-red" />
          </div>
          {d.backtest.open && <div className="text-2xs text-amber mb-1">Open position: {d.backtest.open.side} since {d.backtest.open.open} (entered at z {d.backtest.open.z.toFixed(2)}), {sp(d.backtest.open.ret)} so far.</div>}
          {d.backtest.recent.length > 0 && <table className="w-full text-2xs font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Opened</th><th className="text-left font-normal">Closed</th><th className="text-left font-normal">Side</th><th className="text-right font-normal">Entry z</th><th className="text-left font-normal pl-3">Exit</th><th className="text-right font-normal">Return</th></tr></thead>
            <tbody>{d.backtest.recent.map((t: any) => (
              <tr key={t.open} className="border-t border-border-subtle"><td className="py-0.5">{t.open}</td><td>{t.close}</td><td className="font-sans text-text-secondary">{t.side}</td>
                <td className="text-right">{t.z.toFixed(2)}</td><td className="pl-3 font-sans text-text-tertiary">{t.reason}</td><td className={cn('text-right', tone(t.ret))}>{sp(t.ret)}</td></tr>))}</tbody></table>}
          <div className="text-[10px] text-text-tertiary mt-1">{d.backtest.rules}</div>
        </Panel>
        <div className="text-[10px] text-text-tertiary">{d.note} Source: {d.source}.</div>
      </>}
    </div>
  );
}

// ── CBRT ────────────────────────────────────────────────────────────────────
const CB_COLORS = ['rgb(var(--c-blue))', 'rgb(var(--c-amber))', 'rgb(var(--c-red))', 'rgb(var(--c-green))', 'rgb(168 85 247)', 'rgb(20 184 166)', 'rgb(234 88 12)', 'rgb(var(--c-text-secondary))'];

export function CbrtView() {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/cbrt', 3_600_000);
  const [sel, setSel] = useState<string[]>(['US', 'XM', 'GB', 'JP', 'CA', 'AU']);
  const [sort, setSort] = useState<'rate' | 'last_move' | 'change_1y_bp'>('rate');
  if (loading && !d) return <Loading label="Loading BIS policy rates…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const rows = [...d.banks].sort((x: any, y: any) => sort === 'last_move' ? String(y.last_move ?? '').localeCompare(String(x.last_move ?? '')) : (y[sort] ?? -1e9) - (x[sort] ?? -1e9));
  const toggle = (c: string) => setSel(sel.includes(c) ? sel.filter((x) => x !== c) : sel.length >= 8 ? sel : [...sel, c]);
  const name = (c: string) => d.banks.find((b: any) => b.code === c)?.country ?? c;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Cutting (12 months)" value={d.easing_1y} cls="text-green" sub={`of ${d.banks.length} central banks are lower than a year ago`} />
        <Tile label="Hiking (12 months)" value={d.tightening_1y} cls="text-red" sub="higher than a year ago" />
        <Tile label="Unchanged" value={d.unchanged_1y} />
        <Tile label="Global cycle" value={d.easing_1y > d.tightening_1y * 1.5 ? 'Easing' : d.tightening_1y > d.easing_1y * 1.5 ? 'Tightening' : 'Mixed'} sub="breadth of moves over the year" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] gap-3">
        <Panel title="Policy rates — click a row to chart it" right={<div className="flex gap-1">{([['rate', 'Rate'], ['last_move', 'Latest move'], ['change_1y_bp', '1-year change']] as const).map(([k, l]) => <Chip key={k} on={sort === k} onClick={() => setSort(k)}>{l}</Chip>)}</div>}>
          <div className="max-h-[520px] overflow-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Central bank</th><th className="text-right font-normal">Rate</th>
              <th className="text-right font-normal">Last move</th><th className="text-right font-normal">Size</th><th className="text-right font-normal">1 year</th><th className="text-right font-normal">Moves (12m)</th></tr></thead>
            <tbody>{rows.map((b: any) => (
              <tr key={b.code} onClick={() => toggle(b.code)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-2', sel.includes(b.code) && 'bg-bloomberg/5')}>
                <td className="py-1 font-sans"><span className="text-text-primary">{b.country}</span> <span className="text-text-tertiary">{b.bank}</span></td>
                <td className="text-right text-text-primary">{b.rate.toFixed(2)}%</td><td className="text-right text-text-secondary">{b.last_move ?? '—'}</td>
                <td className={cn('text-right', b.last_change_bp > 0 ? 'text-red' : b.last_change_bp < 0 ? 'text-green' : '')}>{bp(b.last_change_bp)}</td>
                <td className={cn('text-right', b.change_1y_bp > 0 ? 'text-red' : b.change_1y_bp < 0 ? 'text-green' : '')}>{bp(b.change_1y_bp)}</td>
                <td className="text-right text-text-secondary">{b.cuts_12m ? `${b.cuts_12m}↓` : ''}{b.hikes_12m ? ` ${b.hikes_12m}↑` : ''}{!b.cuts_12m && !b.hikes_12m ? '—' : ''}</td></tr>))}</tbody>
          </table></div>
        </Panel>
        <div className="space-y-3">
          <Panel title="Latest decisions">
            <table className="w-full text-2xs"><tbody>{d.recent_moves.map((b: any) => (
              <tr key={b.code} className="border-t border-border-subtle first:border-0"><td className="py-1 text-text-tertiary font-mono">{b.last_move}</td><td className="text-text-primary">{b.bank}</td>
                <td className={cn('text-right font-mono', b.last_change_bp > 0 ? 'text-red' : 'text-green')}>{bp(b.last_change_bp)}</td><td className="text-right font-mono">{b.rate.toFixed(2)}%</td></tr>))}</tbody></table>
          </Panel>
          <Panel title="Rates over time (weekly)">
            <LineChart rows={d.history} x="date" height={260} fmt={(v) => `${v.toFixed(2)}%`}
              lines={sel.map((c, i) => ({ key: c, label: name(c), color: CB_COLORS[i % CB_COLORS.length] }))} />
          </Panel>
        </div>
      </div>
      <div className="text-[10px] text-text-tertiary">{d.note} Where a bank targets a range (the Fed), the BIS shows its midpoint. Source: {d.source}.</div>
    </div>
  );
}

// ── ECOS ────────────────────────────────────────────────────────────────────
const QUICK = [['CPIAUCSL', 'CPI'], ['UNRATE', 'Unemployment'], ['PAYEMS', 'Payrolls'], ['GDPC1', 'Real GDP'], ['DGS10', '10-year yield'], ['T10Y2Y', '10y−2y'],
  ['FEDFUNDS', 'Fed funds'], ['ICSA', 'Jobless claims'], ['UMCSENT', 'Consumer sentiment'], ['INDPRO', 'Industrial production'], ['HOUST', 'Housing starts'],
  ['M2SL', 'M2'], ['WALCL', 'Fed balance sheet'], ['BAMLH0A0HYM2', 'HY spread'], ['DCOILWTICO', 'WTI'], ['MORTGAGE30US', 'Mortgage rate']];
const EKEY = 'mkt_ecos_v1';
type Tf = 'level' | 'yoy' | 'chg' | 'pct' | 'index';
const TF_LABEL: Record<Tf, string> = { level: 'Level', yoy: 'Year-on-year %', chg: 'Change', pct: '% change', index: 'Rebased = 100' };
const SER_COLORS = ['rgb(var(--c-blue))', 'rgb(var(--c-amber))', 'rgb(var(--c-red))', 'rgb(var(--c-green))'];

function transform(rows: { date: string; value: number }[], tf: Tf) {
  if (tf === 'level') return rows;
  if (tf === 'index') { const b = rows.find((r) => r.value)?.value ?? 1; return rows.map((r) => ({ date: r.date, value: (r.value / b) * 100 })); }
  if (tf === 'chg' || tf === 'pct') return rows.slice(1).map((r, i) => ({ date: r.date, value: tf === 'chg' ? r.value - rows[i].value : rows[i].value ? (r.value / rows[i].value - 1) * 100 : NaN }));
  // year-on-year by date, whatever the frequency
  const t = rows.map((r) => new Date(r.date).getTime());
  const out: { date: string; value: number }[] = [];
  let j = 0;
  for (let i = 0; i < rows.length; i++) {
    const target = t[i] - 365 * 864e5 + 3 * 864e5;
    while (j + 1 < i && t[j + 1] <= target) j++;
    if (t[j] <= target && t[i] - t[j] < 400 * 864e5 && rows[j].value) out.push({ date: rows[i].date, value: (rows[i].value / rows[j].value - 1) * 100 });
  }
  return out;
}

export function EcosView({ seed }: { seed?: string }) {
  const [q, setQ] = useState('');
  const [dq, setDq] = useState('');
  const [ids, setIds] = useState<string[]>(() => {
    if (seed) return [seed.toUpperCase()];
    try { const v = JSON.parse(localStorage.getItem(EKEY) || '[]'); return Array.isArray(v) && v.length ? v : ['UNRATE']; } catch { return ['UNRATE']; }
  });
  const [tf, setTf] = useState<Tf>('level');
  useEffect(() => { const t = setTimeout(() => setDq(q), 350); return () => clearTimeout(t); }, [q]);
  useEffect(() => { try { localStorage.setItem(EKEY, JSON.stringify(ids)); } catch { /* storage unavailable */ } }, [ids]);
  const search = useJSON<any>(dq.length >= 2 ? `/api/v1/mkt/ecos/search?q=${enc(dq)}` : null);
  const s0 = useJSON<any>(ids[0] ? `/api/v1/mkt/ecos/series/${enc(ids[0])}` : null);
  const s1 = useJSON<any>(ids[1] ? `/api/v1/mkt/ecos/series/${enc(ids[1])}` : null);
  const s2 = useJSON<any>(ids[2] ? `/api/v1/mkt/ecos/series/${enc(ids[2])}` : null);
  const s3 = useJSON<any>(ids[3] ? `/api/v1/mkt/ecos/series/${enc(ids[3])}` : null);
  const series = [s0, s1, s2, s3].slice(0, ids.length);
  const add = (id: string) => setIds((cur) => (cur.includes(id) ? cur : [...cur, id].slice(-4)));
  const merged = useMemo(() => {
    const loaded = series.map((s) => s.data).filter(Boolean) as any[];
    if (!loaded.length) return [];
    const maps = loaded.map((d) => new Map(transform(d.rows, tf).map((r) => [r.date, r.value])));
    const dates = [...new Set(maps.flatMap((m) => [...m.keys()]))].sort();
    const last: (number | null)[] = loaded.map(() => null);
    const ends = loaded.map((d) => d.rows[d.rows.length - 1]?.date ?? '');
    return dates.map((dt) => {
      const row: Record<string, any> = { date: dt };
      maps.forEach((m, i) => { const v = m.get(dt); if (v != null && Number.isFinite(v)) last[i] = v; row[loaded[i].id] = dt <= ends[i] ? last[i] : null; });
      return row;
    });
  }, [series.map((s) => s.data?.id).join(','), tf]);   // eslint-disable-line react-hooks/exhaustive-deps
  const first = s0.data;
  const lastObs = first?.rows[first.rows.length - 1];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search 800,000 FRED series — e.g. 'japan cpi', 'housing starts', 'euro area unemployment'"
          className="w-[28rem] max-w-full bg-surface-1 border border-border px-2 py-1 text-xs" />
        <span className="ml-2 flex flex-wrap gap-1">{QUICK.map(([id, l]) => <Chip key={id} on={ids.includes(id)} onClick={() => setIds([id])}>{l}</Chip>)}</span>
      </div>
      {dq.length >= 2 && (
        <Panel title={`Search results for “${dq}” — click to chart, + to add (up to four)`}>
          {search.loading && !search.data ? <Loading /> : search.error ? <ErrorBox msg={search.error} /> : (
            <div className="max-h-64 overflow-auto"><table className="w-full text-2xs"><tbody>{(search.data?.results ?? []).map((r: any) => (
              <tr key={r.id} className={cn('border-t border-border-subtle first:border-0 hover:bg-surface-2', !r.active && 'opacity-50')}>
                <td className="py-1 pr-2"><button onClick={() => { setIds([r.id]); setQ(''); }} className="text-left"><span className="font-mono text-bloomberg">{r.id}</span> <span className="text-text-primary">{r.title}</span></button></td>
                <td className="text-text-tertiary whitespace-nowrap">{r.frequency} · {r.units}{r.sa && r.sa !== 'NSA' ? ` · ${r.sa}` : ''}</td>
                <td className="text-text-tertiary font-mono whitespace-nowrap px-2">{r.start?.slice(0, 4)}–{r.end?.slice(0, 7)}{!r.active && <span className="ml-1 font-sans text-amber">discontinued</span>}</td>
                <td><button onClick={() => add(r.id)} className="px-1.5 border border-border text-text-secondary hover:text-bloomberg" title="Add to chart">+</button></td></tr>))}</tbody></table></div>)}
        </Panel>)}
      <Panel title={first ? `${first.title}${ids.length > 1 ? ` + ${ids.length - 1} more` : ''}` : 'Series'} right={<div className="flex gap-1">{(Object.keys(TF_LABEL) as Tf[]).map((k) => <Chip key={k} on={tf === k} onClick={() => setTf(k)}>{TF_LABEL[k]}</Chip>)}</div>}>
        <div className="flex flex-wrap gap-1 mb-2">{ids.map((id, i) => (
          <span key={id} className="inline-flex items-center gap-1 border border-border rounded-sm px-1.5 py-0.5 text-[11px]">
            <span className="w-2 h-2 rounded-full" style={{ background: SER_COLORS[i] }} /><span className="font-mono">{id}</span>
            <span className="text-text-tertiary truncate max-w-[220px]">{series[i]?.data?.title ?? (series[i]?.error ? 'not found' : '…')}</span>
            {ids.length > 1 && <button onClick={() => setIds(ids.filter((x) => x !== id))} className="text-text-tertiary hover:text-red">✕</button>}</span>))}</div>
        {s0.loading && !first ? <Loading label="Loading from FRED…" /> : s0.error && !first ? <ErrorBox msg={s0.error} /> : merged.length > 0 && (
          <LineChart rows={merged} x="date" height={340} defaultRange="10y" fmt={(v) => (Math.abs(v) >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v.toFixed(2))}
            baseline={tf === 'level' ? undefined : tf === 'index' ? 100 : 0}
            lines={series.map((s, i) => s.data && { key: s.data.id, label: `${s.data.id}${tf === 'level' ? ` (${s.data.units})` : ''}`, color: SER_COLORS[i] }).filter(Boolean) as any} />)}
        {first && <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2">
          <Tile label="Latest" value={lastObs?.value.toLocaleString(undefined, { maximumFractionDigits: 3 })} sub={`${lastObs?.date ?? '—'} · ${first.units}`} />
          <Tile label="Frequency" value={first.frequency} sub={first.sa} />
          <Tile label="Year on year" value={(() => { const y = transform(first.rows, 'yoy'); return y.length ? `${y[y.length - 1].value.toFixed(2)}%` : '—'; })()} />
          <Tile label="History" value={first.rows[0]?.date ? `${first.rows[0].date.slice(0, 4)} →` : '—'} sub={`${first.rows.length.toLocaleString()} observations`} />
          <Tile label="Updated" value={first.updated?.slice(0, 10)} />
        </div>}
        {first?.notes && <details className="mt-2"><summary className="text-2xs text-text-secondary cursor-pointer">About this series</summary><p className="text-2xs text-text-tertiary mt-1 whitespace-pre-wrap">{first.notes}</p></details>}
      </Panel>
      <div className="text-[10px] text-text-tertiary">Source: FRED, Federal Reserve Bank of St. Louis. Different units on one chart: use “Rebased = 100” or “Year-on-year %” to compare.</div>
    </div>
  );
}

// ── ETFA: ETF premium / discount to NAV ─────────────────────────────────────
export function EtfaView({ onOpen }: { onOpen?: (s: string) => void }) {
  const { data: d, error } = useJSON<any>('/api/v1/mkt/etfarb', 900_000);
  const [group, setGroup] = useState('');
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return <Loading label="Reading ETF NAVs…" />;
  const rows = d.rows.filter((r: any) => !group || r.group === group);
  const bp = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}bp`);
  const bn = (v: number | null) => (v == null ? '—' : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}bn` : `$${(v / 1e6).toFixed(0)}m`);
  const why = d.groups.find((g: any) => g.group === group)?.why;
  return (
    <div className="space-y-2">
      <Panel title="ETF premium / discount to NAV">
        <div className="flex flex-wrap gap-1 text-[11px] mb-2">
          <button onClick={() => setGroup('')} className={cn('px-2 py-0.5 border rounded-sm', !group ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>All</button>
          {d.groups.map((g: any) => (
            <button key={g.group} onClick={() => setGroup(g.group)} className={cn('px-2 py-0.5 border rounded-sm', group === g.group ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>
              {g.group} <span className="font-mono text-text-tertiary">{bp(g.median_bp)}</span>
            </button>))}
        </div>
        {why && <div className="text-[11px] text-amber mb-2">{why}</div>}
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] font-mono">
            <thead><tr className="text-text-tertiary">
              {['ETF', 'Name', 'Group', 'Close', 'NAV', 'Premium', 'Since close', 'AUM', 'Expense'].map((h, i) => <th key={h} className={cn('font-normal px-1.5', i < 3 ? 'text-left' : 'text-right')}>{h}</th>)}
            </tr></thead>
            <tbody>{rows.map((r: any) => {
              const flag = d.flagged.includes(r.symbol);
              return (
                <tr key={r.symbol} className="border-t border-border-subtle hover:bg-surface-2">
                  <td className="px-1.5 py-0.5"><button className="text-bloomberg hover:underline" onClick={() => onOpen?.(r.symbol)}>{r.symbol}</button></td>
                  <td className="px-1.5 font-sans text-text-secondary max-w-[220px] truncate">{r.name}</td>
                  <td className="px-1.5 font-sans text-text-tertiary whitespace-nowrap">{r.group}</td>
                  <td className="px-1.5 text-right">{fmtPrice(r.close)}</td><td className="px-1.5 text-right">{fmtPrice(r.nav)}</td>
                  <td className={cn('px-1.5 text-right', flag ? 'text-amber font-semibold' : r.premium_bp >= 0 ? 'text-green' : 'text-red')}>{bp(r.premium_bp)}</td>
                  <td className="px-1.5 text-right text-text-tertiary">{bp(r.move_since_close_bp)}</td>
                  <td className="px-1.5 text-right">{bn(r.aum)}</td>
                  <td className="px-1.5 text-right">{r.expense_pct == null ? '—' : `${Number(r.expense_pct).toFixed(2)}%`}</td>
                </tr>);
            })}</tbody>
          </table>
        </div>
        <div className="text-[10px] text-text-tertiary mt-2">{d.note}{d.missing.length ? ` No NAV from Yahoo for: ${d.missing.join(', ')}.` : ''}
          {d.unreliable?.length ? ` Set aside (NAV looks stale): ${d.unreliable.map((u: any) => `${u.symbol} NAV ${u.nav} vs close ${u.close}`).join('; ')}.` : ''}</div>
      </Panel>
    </div>
  );
}

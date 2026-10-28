// In-depth backtest analysis — the same report for every automated book: Quant Lab strategies and the algos in the
// Macro / Fundamental / Technical Quant Traders, the macro model book, and the stock entry book (api/quant/deep.py).
import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Microscope } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { api, ErrorNote, num, pct, Pills, spct } from './shared';

const MLAB = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const tone = (v: number | null | undefined) => (v == null ? 'text-text-tertiary' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : '');
const heat = (v: number | null | undefined) => (v == null ? undefined : v >= 0 ? `rgb(var(--c-green) / ${Math.min(0.55, 0.08 + v * 5)})` : `rgb(var(--c-red) / ${Math.min(0.55, 0.08 - v * 5)})`);

function Tile({ label, value, sub, cls, title }: { label: string; value: React.ReactNode; sub?: React.ReactNode; cls?: string; title?: string }) {
  return (
    <div className="p-2 bg-surface-1 border border-border" title={title}>
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className={cn('font-mono text-xs text-text-primary', cls)}>{value}</div>
      {sub != null && <div className="text-[10px] text-text-tertiary leading-tight">{sub}</div>}
    </div>
  );
}
const Box = ({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) => (
  <div className="p-3 bg-surface-1 border border-border"><div className="flex items-center mb-1.5"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{title}</div><div className="ml-auto">{right}</div></div>{children}</div>
);

type Tab = 'overview' | 'calendar' | 'drawdowns' | 'regimes' | 'robustness' | 'trades';

/** Collapsible: fetches only when opened. `request` = [url, body?]; body → POST. */
export function DeepAnalysis({ request, title = 'Deep analysis', defaultOpen = false }: { request: [string, any?]; title?: string; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const key = JSON.stringify(request);
  useEffect(() => { setD(null); setErr(null); }, [key]);
  useEffect(() => {
    if (!open || d) return;
    let live = true;
    const [url, body] = request;
    api(url, body !== undefined ? { json: body } : undefined).then((x) => live && setD(x)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [open, key, d]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="border border-border">
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="w-full flex items-center gap-2 px-3 py-2 text-2xs text-left hover:bg-surface-2">
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}<Microscope className="w-3 h-3 text-bloomberg" />
        <span className="font-semibold text-text-primary">{title}</span>
        <span className="text-text-tertiary">— calendar, drawdowns, distribution, rolling risk, benchmark, regimes, crises, Monte Carlo, trades</span>
      </button>
      {open && <div className="p-3 border-t border-border">{err ? <ErrorNote msg={err} /> : !d ? <div className="flex items-center gap-2 text-2xs text-text-tertiary"><Loader2 className="w-3 h-3 animate-spin" />Analysing…</div> : <DeepReport d={d} />}</div>}
    </div>
  );
}

export function DeepReport({ d }: { d: any }) {
  const [tab, setTab] = useState<Tab>('overview');
  const s = d.summary ?? {}, b = d.benchmark_summary, rel = d.relative, rb = d.robustness ?? {};
  const tabs: [Tab, string][] = [['overview', 'Overview'], ['calendar', 'Calendar'], ['drawdowns', 'Drawdowns'], ['regimes', 'Regimes & crises'], ['robustness', 'Robustness'],
    ...(d.trades ? [['trades', 'Trades'] as [Tab, string]] : [])];
  const row = (k: string, l: string, f: (v: any) => string = (v) => spct(v)) => (
    <tr key={k} className="border-t border-border-subtle"><td className="py-0.5 text-text-secondary">{l}</td><td className="text-right text-text-primary">{f(s[k])}</td>{b && <td className="text-right text-text-tertiary">{f(b[k])}</td>}</tr>);
  return (
    <div className="space-y-3 text-2xs">
      <div className="text-text-tertiary">{d.label} · {d.start} → {d.end} · {d.frequency} returns{d.benchmark_label ? ` · vs ${d.benchmark_label}` : ''}{d.deployed_at ? ` · deployed ${d.deployed_at} (${d.live_days} live sessions)` : ''}</div>
      <Pills label="Deep analysis view" value={tab} onChange={setTab} options={tabs as any} />

      {tab === 'overview' && <>
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
          <Tile label="CAGR" value={spct(s.cagr)} cls={tone(s.cagr)} sub={b ? `benchmark ${spct(b.cagr)}` : undefined} />
          <Tile label="Sharpe" value={num(s.sharpe)} sub={`Sortino ${num(s.sortino)}`} />
          <Tile label="Max drawdown" value={pct(s.max_drawdown)} cls="text-red" sub={`Calmar ${num(s.calmar)}`} />
          <Tile label="Ulcer index" value={pct(s.ulcer_index)} sub="depth × length of drawdowns" title="Root-mean-square drawdown — punishes long, deep drawdowns" />
          <Tile label="CVaR 95%" value={pct(s.cvar95, 2)} sub={`per ${({ daily: 'day', weekly: 'week', monthly: 'month' } as Record<string, string>)[d.frequency] ?? 'period'} · VaR ${pct(s.var95, 2)}`} />
          <Tile label="Skew / kurtosis" value={`${num(s.skew)} / ${num(s.excess_kurtosis)}`} sub="negative skew = crash risk" />
          <Tile label="Tail ratio" value={num(s.tail_ratio)} sub="best 5% ÷ worst 5%" />
          <Tile label="Positive periods" value={pct(s.pct_positive, 0)} sub={`streaks +${s.longest_win_streak} / −${s.longest_loss_streak}`} />
        </div>
        {rel && <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
          <Tile label="Alpha (annual)" value={spct(rel.alpha)} cls={tone(rel.alpha)} /><Tile label="Beta" value={num(rel.beta)} sub={`correlation ${num(rel.correlation)}`} />
          <Tile label="Up capture" value={pct(rel.up_capture, 0)} sub="of benchmark up periods" /><Tile label="Down capture" value={pct(rel.down_capture, 0)} cls={(rel.down_capture ?? 1) < 1 ? 'text-green' : 'text-red'} sub="lower is better" />
          <Tile label="Tracking error" value={pct(rel.tracking_error)} /><Tile label="Information ratio" value={num(rel.information_ratio)} />
          <Tile label="Months beating" value={pct(rel.pct_months_beating, 0)} />
          <Tile label="Best / worst year vs bench" value={`${spct(rel.best_relative_year?.diff, 0)} / ${spct(rel.worst_relative_year?.diff, 0)}`} sub={`${rel.best_relative_year?.year ?? '—'} / ${rel.worst_relative_year?.year ?? '—'}`} />
        </div>}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
          <Box title="Growth of 1 (log) and underwater curve">
            <LineChart rows={d.underwater} x="date" height={170} log controls={false} fmt={(v) => `${v.toFixed(2)}×`}
              lines={[{ key: 'equity', label: d.label, color: 'rgb(var(--c-blue))' }, ...(d.benchmark_label ? [{ key: 'benchmark_equity', label: d.benchmark_label, color: 'rgb(var(--c-text-tertiary))' }] : [])]} />
            <LineChart rows={d.underwater} x="date" height={110} controls={false} fmt={(v) => `${(v * 100).toFixed(0)}%`}
              lines={[{ key: 'drawdown', label: 'Drawdown', color: 'rgb(var(--c-red))' }, ...(d.benchmark_label ? [{ key: 'benchmark_drawdown', label: `${d.benchmark_label} drawdown`, color: 'rgb(var(--c-text-tertiary))' }] : [])]} />
          </Box>
          <Box title="Rolling 12 months">
            <LineChart rows={d.rolling} x="date" height={140} controls={false} fmt={(v) => v.toFixed(2)} baseline={0}
              lines={[{ key: 'sharpe_12m', label: 'Sharpe', color: 'rgb(var(--c-blue))' }, ...(rel ? [{ key: 'beta_24m', label: 'Beta (24m)', color: 'rgb(var(--c-amber))' }, { key: 'corr_24m', label: 'Correlation (24m)', color: 'rgb(168 85 247)' }] : [])]} />
            <LineChart rows={d.rolling.map((x: any) => ({ ...x, r: x.return_12m != null ? x.return_12m * 100 : null, v: x.vol_12m != null ? x.vol_12m * 100 : null }))} x="date" height={120} controls={false} fmt={(v) => `${v.toFixed(0)}%`} baseline={0}
              lines={[{ key: 'r', label: '12-month return', color: 'rgb(var(--c-green))' }, { key: 'v', label: '12-month volatility', color: 'rgb(var(--c-red))' }]} />
          </Box>
        </div>
        <Box title="All statistics">
          <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal" /><th className="text-right font-normal">{d.label}</th>{b && <th className="text-right font-normal">{d.benchmark_label}</th>}</tr></thead>
            <tbody>{[row('total_return', 'Total return'), row('cagr', 'CAGR'), row('vol', 'Volatility', (v) => pct(v)), row('sharpe', 'Sharpe', (v) => num(v)), row('sortino', 'Sortino', (v) => num(v)),
              row('calmar', 'Calmar', (v) => num(v)), row('max_drawdown', 'Max drawdown', (v) => pct(v)), row('avg_drawdown', 'Average drawdown', (v) => pct(v)), row('ulcer_performance', 'Ulcer performance index', (v) => num(v)),
              row('gain_pain', 'Gain-to-pain', (v) => num(v)), row('best', 'Best period'), row('worst', 'Worst period'), row('avg_win', 'Average gain'), row('avg_loss', 'Average loss')]}</tbody></table>
        </Box>
        <Box title="Distribution of monthly returns">
          <div className="flex items-end gap-0.5 h-28">{(() => { const mx = Math.max(1, ...d.distribution.flatMap((x: any) => [x.strategy, x.benchmark ?? 0])); return d.distribution.map((x: any) => (
            <div key={x.bin} className="flex-1 flex items-end gap-px h-full" title={`${x.bin}: ${x.strategy} months${x.benchmark != null ? ` (benchmark ${x.benchmark})` : ''}`}>
              <div className="flex-1 bg-blue/70" style={{ height: `${(x.strategy / mx) * 100}%` }} />{x.benchmark != null && <div className="flex-1 bg-text-tertiary/40" style={{ height: `${(x.benchmark / mx) * 100}%` }} />}</div>)); })()}</div>
          <div className="flex justify-between text-[9px] text-text-tertiary mt-0.5"><span>{d.distribution[0]?.bin} or worse</span><span>0</span><span>+{d.distribution[d.distribution.length - 1]?.bin.replace('-', '')} or better</span></div>
        </Box>
      </>}

      {tab === 'calendar' && <Box title="Monthly returns">
        <div className="overflow-x-auto"><table className="w-full font-mono tabular-nums"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Year</th>{MLAB.map((m) => <th key={m} className="text-right font-normal px-1">{m}</th>)}<th className="text-right font-normal px-1">Year</th>{d.benchmark_label && <th className="text-right font-normal px-1">Bench</th>}</tr></thead>
          <tbody>{[...d.calendar].reverse().map((y: any) => (
            <tr key={y.year} className="border-t border-border-subtle"><td className="py-0.5 text-text-secondary">{y.year}</td>
              {MLAB.map((_, i) => { const v = y.months[i + 1]; return <td key={i} className="text-right px-1" style={{ background: heat(v) }}>{v != null ? (v * 100).toFixed(1) : ''}</td>; })}
              <td className={cn('text-right px-1 font-semibold', tone(y.total))}>{(y.total * 100).toFixed(1)}</td>{d.benchmark_label && <td className="text-right px-1 text-text-tertiary">{y.benchmark != null ? (y.benchmark * 100).toFixed(1) : ''}</td>}</tr>))}</tbody></table></div>
      </Box>}

      {tab === 'drawdowns' && <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
        {[[d.label, d.drawdowns], ...(d.benchmark_drawdowns ? [[d.benchmark_label, d.benchmark_drawdowns]] : [])].map(([lab, rows]: any) => (
          <Box key={lab} title={`Five worst drawdowns — ${lab}`}>
            <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Peak</th><th className="text-left font-normal">Trough</th><th className="text-left font-normal">Recovered</th><th className="text-right font-normal">Depth</th><th className="text-right font-normal">Fall</th><th className="text-right font-normal">Recovery</th></tr></thead>
              <tbody>{rows.map((x: any) => (
                <tr key={x.start} className="border-t border-border-subtle"><td className="py-0.5">{x.start}</td><td>{x.trough}</td><td className={x.recovered ? '' : 'text-amber'}>{x.recovered ?? 'not yet'}</td>
                  <td className="text-right text-red">{pct(x.depth)}</td><td className="text-right text-text-secondary">{x.days_to_trough}d</td><td className="text-right text-text-secondary">{x.days_to_recover != null ? `${x.days_to_recover}d` : '—'}</td></tr>))}</tbody></table>
          </Box>))}
      </div>}

      {tab === 'regimes' && <div className="space-y-2">
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-2">
          {([['environment', 'Growth / inflation environment (Bridgewater)'], ['volatility', 'Market stress (VIX)'], ['market_trend', 'Benchmark trend']] as const).map(([k, t]) => d.regimes?.[k]?.length ? (
            <Box key={k} title={t}>
              <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal" /><th className="text-right font-normal">Months</th><th className="text-right font-normal">Return/yr</th><th className="text-right font-normal">Sharpe</th>{d.benchmark_label && <th className="text-right font-normal">Bench/yr</th>}</tr></thead>
                <tbody>{d.regimes[k].map((x: any) => (
                  <tr key={x.regime} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-secondary">{x.regime}</td><td className="text-right">{x.months}</td>
                    <td className={cn('text-right', tone(x.return))}>{spct(x.return)}</td><td className="text-right">{num(x.sharpe)}</td>{d.benchmark_label && <td className="text-right text-text-tertiary">{spct(x.benchmark_return)}</td>}</tr>))}</tbody></table>
            </Box>) : null)}
        </div>
        {d.crises?.length > 0 && <Box title="Crises">
          <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Episode</th><th className="text-left font-normal">Dates</th><th className="text-right font-normal">{d.label}</th>{d.benchmark_label && <><th className="text-right font-normal">{d.benchmark_label}</th><th className="text-right font-normal">Difference</th></>}</tr></thead>
            <tbody>{d.crises.map((c: any) => (
              <tr key={c.episode} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-primary">{c.episode}</td><td className="text-text-tertiary">{c.start} → {c.end}</td>
                <td className={cn('text-right', tone(c.return))}>{spct(c.return)}</td>{d.benchmark_label && <><td className={cn('text-right', tone(c.benchmark))}>{spct(c.benchmark)}</td>
                  <td className={cn('text-right font-semibold', tone(c.benchmark != null ? c.return - c.benchmark : null))}>{c.benchmark != null ? spct(c.return - c.benchmark) : '—'}</td></>}</tr>))}</tbody></table>
        </Box>}
      </div>}

      {tab === 'robustness' && <div className="space-y-2">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Tile label="Probabilistic Sharpe" value={pct(rb.psr, 1)} sub="chance the true Sharpe is above zero" />
          <Tile label="Track record needed" value={rb.min_track_record_years != null ? `${num(rb.min_track_record_years, 1)} years` : 'n/a'} sub={`have ${num(s.years, 1)} years`} cls={rb.min_track_record_years != null && s.years >= rb.min_track_record_years ? 'text-green' : 'text-amber'} />
          <Tile label="Years with positive Sharpe" value={pct(rb.pct_years_positive_sharpe, 0)} sub={`spread of yearly Sharpes ${num(rb.sharpe_dispersion)}`} />
          <Tile label="Max drawdown range" value={`${pct(rb.bootstrap?.max_drawdown?.p50, 0)} typical`} sub={`1-in-20 worst ${pct(rb.bootstrap?.max_drawdown?.p95_worst, 0)}`} />
        </div>
        {rb.bootstrap && <Box title="Monte Carlo — annualised return over the next 1, 3 and 5 years (block bootstrap)">
          <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Horizon</th><th className="text-right font-normal">Bad (5%)</th><th className="text-right font-normal">25%</th><th className="text-right font-normal">Median</th><th className="text-right font-normal">75%</th><th className="text-right font-normal">Good (95%)</th><th className="text-right font-normal">Chance of a loss</th></tr></thead>
            <tbody>{['1y', '3y', '5y'].filter((h) => rb.bootstrap[h]).map((h) => { const x = rb.bootstrap[h]; return (
              <tr key={h} className="border-t border-border-subtle"><td className="py-0.5">{h.replace('y', ' year' + (h === '1y' ? '' : 's'))}</td><td className="text-right text-red">{spct(x.p5)}</td><td className="text-right">{spct(x.p25)}</td>
                <td className="text-right text-text-primary font-semibold">{spct(x.p50)}</td><td className="text-right">{spct(x.p75)}</td><td className="text-right text-green">{spct(x.p95)}</td><td className="text-right">{pct(x.prob_loss, 0)}</td></tr>); })}</tbody></table>
        </Box>}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
          <Box title="Out-of-sample check — first half vs second half">
            <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal" /><th className="text-right font-normal">First half</th><th className="text-right font-normal">Second half</th></tr></thead>
              <tbody>{([['cagr', 'CAGR', spct], ['sharpe', 'Sharpe', num], ['max_drawdown', 'Max drawdown', pct], ['vol', 'Volatility', pct]] as const).map(([k, l, f]) => (
                <tr key={k} className="border-t border-border-subtle"><td className="py-0.5 text-text-secondary">{l}</td><td className="text-right">{(f as any)(rb.first_half?.[k])}</td><td className="text-right">{(f as any)(rb.second_half?.[k])}</td></tr>))}</tbody></table>
            <div className="text-[10px] text-text-tertiary mt-1">A strategy whose edge is real should look similar in both halves; a big drop in the second half often means the first half was fitted or the edge has been arbitraged away.</div>
          </Box>
          <Box title="Year by year">
            <div className="flex items-end gap-0.5 h-32">{(() => { const mx = Math.max(0.01, ...rb.by_year.map((y: any) => Math.abs(y.return ?? 0))); return rb.by_year.map((y: any) => (
              <div key={y.year} className="flex-1 flex flex-col justify-center h-full" title={`${y.year}: ${spct(y.return)} · Sharpe ${num(y.sharpe)}`}>
                <div className="h-1/2 flex items-end"><div className="w-full bg-green/70" style={{ height: `${Math.max(0, y.return) / mx * 100}%` }} /></div>
                <div className="h-1/2 flex items-start"><div className="w-full bg-red/70" style={{ height: `${Math.max(0, -y.return) / mx * 100}%` }} /></div></div>)); })()}</div>
            <div className="flex justify-between text-[9px] text-text-tertiary"><span>{rb.by_year[0]?.year}</span><span>{rb.by_year[rb.by_year.length - 1]?.year}</span></div>
          </Box>
        </div>
      </div>}

      {tab === 'trades' && d.trades && <div className="space-y-2">
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
          <Tile label="Trades" value={d.trades.trades.toLocaleString()} /><Tile label="Win rate" value={pct(d.trades.win_rate, 0)} />
          <Tile label={`Average win (${d.trades.unit})`} value={num(d.trades.avg_win)} cls="text-green" /><Tile label={`Average loss (${d.trades.unit})`} value={num(d.trades.avg_loss)} cls="text-red" />
          <Tile label="Payoff ratio" value={num(d.trades.payoff_ratio)} sub="avg win ÷ avg loss" /><Tile label="Profit factor" value={num(d.trades.profit_factor)} />
          <Tile label="Expectancy" value={`${num(d.trades.expectancy, 3)} ${d.trades.unit}`} cls={tone(d.trades.expectancy)} sub={`t = ${num(d.trades.t_stat)}`} />
          <Tile label="Worst losing streak" value={`${d.trades.max_consecutive_losses} trades`} />
        </div>
        <Box title={`Distribution of trade results (${d.trades.unit === 'R' ? 'R-multiples: profit ÷ initial risk' : 'returns'})`}>
          <div className="flex items-end gap-1 h-28">{(() => { const mx = Math.max(1, ...d.trades.histogram.map((h: any) => h.count)); return d.trades.histogram.map((h: any) => (
            <div key={h.bin} className="flex-1 flex flex-col items-center justify-end h-full" title={`${h.bin}: ${h.count}`}>
              <div className={cn('w-full', h.bin.startsWith('-') ? 'bg-red/60' : 'bg-green/60')} style={{ height: `${(h.count / mx) * 100}%` }} /><span className="text-[8px] text-text-tertiary">{h.bin.split(' to ')[0]}</span></div>)); })()}</div>
        </Box>
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-2">
          {([['by_exit', 'By exit reason'], ['by_holding', 'By holding period'], ['by_group', `By ${d.trades.group_name ?? 'group'}`]] as const).map(([k, t]) => d.trades[k]?.length ? (
            <Box key={k} title={t}>
              <table className="w-full font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal" /><th className="text-right font-normal">Trades</th><th className="text-right font-normal">Win rate</th><th className="text-right font-normal">Average</th><th className="text-right font-normal">Total</th></tr></thead>
                <tbody>{d.trades[k].map((x: any) => (
                  <tr key={x.group} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-secondary">{x.group}</td><td className="text-right">{x.trades}</td><td className="text-right">{pct(x.win_rate, 0)}</td>
                    <td className={cn('text-right', tone(x.avg))}>{num(x.avg, 2)}</td><td className={cn('text-right', tone(x.total))}>{num(x.total, 1)}</td></tr>))}</tbody></table>
            </Box>) : null)}
        </div>
        {d.trades.by_year?.length > 0 && <Box title="By year of entry">
          <table className="w-full font-mono"><tbody>{d.trades.by_year.map((x: any) => (
            <tr key={x.group} className="border-t border-border-subtle first:border-0"><td className="py-0.5 text-text-secondary">{x.group}</td><td className="text-right">{x.trades} trades</td><td className="text-right">{pct(x.win_rate, 0)} won</td>
              <td className={cn('text-right', tone(x.avg))}>{num(x.avg, 2)} avg</td><td className={cn('text-right', tone(x.total))}>{num(x.total, 1)} total</td></tr>))}</tbody></table>
        </Box>}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
          {([['best', 'Best trades'], ['worst', 'Worst trades']] as const).map(([k, t]) => (
            <Box key={k} title={t}><table className="w-full font-mono"><tbody>{d.trades[k].map((x: any, i: number) => (
              <tr key={i} className="border-t border-border-subtle first:border-0"><td className="py-0.5 text-text-primary">{x.symbol ?? '—'}</td><td className="text-text-tertiary">{x.entry_date} → {x.exit_date}</td>
                <td className="text-text-tertiary">{x.reason}</td><td className={cn('text-right', tone(x.r ?? x.ret))}>{x.r != null ? `${num(x.r, 2)}R` : spct(x.ret)}</td></tr>))}</tbody></table></Box>))}
        </div>
      </div>}

      <div className="text-[10px] text-text-tertiary space-y-0.5">{(d.notes ?? []).map((n: string) => <div key={n}>{n}</div>)}{d.trades_note && <div className="text-amber">{d.trades_note}</div>}
        {d.data_quality && <div>Data quality: {d.data_quality.rule} {d.data_quality.excluded_jump_trades != null ? `${d.data_quality.excluded_jump_trades} trades excluded.` : ''}{d.data_quality.positions_closed_on_suspect_jumps != null ? `${d.data_quality.positions_closed_on_suspect_jumps} positions closed this way.` : ''}</div>}</div>
    </div>
  );
}

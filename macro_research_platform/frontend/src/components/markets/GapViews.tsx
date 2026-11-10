// Screens that fill gaps against Bloomberg, IBKR and Futu (backend: api/marketdata/bbgextra.py):
//   BORROW short borrow · DARK off-exchange volume · PROB probability lab · CRPR credit profile · LEAG M&A advisers · SPF consensus
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { BarList } from '@/components/ui/BarList';
import { ErrorBox, Loading, Panel, useJSON } from './shared';
import { Chip, pct, sign, Source, Tile } from './StandardViews';
import { useStickyState } from '@/lib/stickyState';

const big = (v: number | null | undefined) => (v == null ? '—' : v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : v.toFixed(0));
const fee = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(v < 10 ? 2 : 1)}%`);

// ── BORROW: the board, and a card for one stock (used inside SI) ──────────────
export function BorrowCard({ symbol }: { symbol: string }) {
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/borrow/${encodeURIComponent(symbol)}`, 3_600_000);
  if (loading && !d) return <Loading label="Checking the cost to borrow…" />;
  if (error && !d) return <p className="text-[11px] text-text-tertiary">Cost to borrow: {error}</p>;
  if (!d) return null;
  return (
    <Panel title="Cost to borrow (IBKR)" right={<span className="text-[11px] text-text-tertiary">{d.as_of}</span>}>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Borrow fee" value={fee(d.fee)} cls={d.fee >= 5 ? 'text-red' : ''} sub={d.tier} />
        <Tile label="Short rebate" value={fee(d.rebate)} sub="earned on the short sale's cash" />
        <Tile label="Shares available" value={d.available_label.startsWith('>') ? '10M+' : big(d.available)} sub="IBKR lendable inventory" />
        <Tile label="Currency" value={d.currency} sub={d.market_file.replace('.txt', '')} />
      </div>
      <p className="text-[10px] text-text-tertiary mt-2">{d.note}</p>
    </Panel>
  );
}

export function BorrowView({ onOpen }: { onOpen: (s: string) => void }) {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/borrow', 3_600_000);
  const [tab, setTab] = useStickyState<'hardest' | 'index'>('borrow.tab', 'hardest');
  if (loading && !d) return <Loading label="Reading IBKR's stock-loan file…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const rows = tab === 'hardest' ? d.hardest : d.index_members;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Liquid US names" value={d.universe.toLocaleString()} sub="in IBKR's lending file" />
        <Tile label="Hard to borrow" value={d.hard_to_borrow} sub="fee above 5% a year" cls="text-red" />
        <Tile label="Median fee" value={fee(d.median_fee)} sub="general collateral is ~0.25–0.5%" />
        <Tile label="File time" value={d.as_of?.slice(11) ?? '—'} sub={d.as_of?.slice(0, 10)} />
      </div>
      <div className="flex gap-1">
        <Chip on={tab === 'hardest'} onClick={() => setTab('hardest')}>Costliest to short</Chip>
        <Chip on={tab === 'index'} onClick={() => setTab('index')}>S&P 500 / Nasdaq 100 members</Chip>
      </div>
      <Panel title={tab === 'hardest' ? 'Costliest liquid stocks to borrow' : 'Index members with the highest borrow fees'}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Symbol</th><th className="text-left font-normal">Name</th>
            <th className="text-right font-normal px-1">Fee</th><th className="text-right font-normal px-1">Rebate</th><th className="text-right font-normal px-1">Available</th>
            <th className="text-right font-normal px-1">$ traded</th></tr></thead>
          <tbody>{rows.map((r: any) => (
            <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2">
              <td className="py-1 text-text-primary">{r.symbol}</td><td className="font-sans text-text-tertiary truncate max-w-[16rem]">{r.name}</td>
              <td className={cn('text-right px-1 font-semibold', r.fee >= 5 && 'text-red')}>{fee(r.fee)}</td>
              <td className={cn('text-right px-1', sign(r.rebate))}>{fee(r.rebate)}</td>
              <td className="text-right px-1">{r.available_label.startsWith('>') ? '10M+' : big(r.available)}</td>
              <td className="text-right px-1 text-text-secondary">{big(r.dollar_volume)}</td></tr>))}</tbody>
        </table></div>
      </Panel>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── DARK ─────────────────────────────────────────────────────────────────────
export function DarkView({ symbol }: { symbol: string }) {
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/dark/${encodeURIComponent(symbol)}?weeks=12`, 12 * 3_600_000);
  if (loading && !d) return <Loading label="Loading FINRA's weekly off-exchange volume…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Off-exchange share" value={pct(d.off_exchange_share, 1).replace('+', '')} sub={`week of ${d.latest_week}`} />
        <Tile label="Dark pools (ATS)" value={pct(d.ats_share, 1).replace('+', '')} sub="of all shares traded" />
        <Tile label={`${d.weeks.length}-week average`} value={pct(d.avg_off_exchange_share, 1).replace('+', '')} sub="off-exchange share" />
        <Tile label="Largest venue" value={d.venues[0]?.venue ?? '—'} sub={d.venues[0] ? `${Math.round(d.venues[0].share_of_off_exchange * 100)}% of off-exchange volume` : ''} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title="Share of volume traded away from exchanges, by week">
          <div className="mkt-chart-surface"><LineChart rows={d.weeks.map((w: any) => ({ week: w.week, off: w.off_exchange_share != null ? w.off_exchange_share * 100 : null, ats: w.ats_share != null ? w.ats_share * 100 : null }))}
            x="week" height={230} controls={false} fmt={(v) => `${v.toFixed(1)}%`}
            lines={[{ key: 'off', label: 'All off-exchange', color: 'rgb(var(--c-bloomberg))' }, { key: 'ats', label: 'Dark pools', color: 'rgb(var(--c-blue))' }]} /></div>
        </Panel>
        <Panel title="Venues that traded most (all weeks)">
          <table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Venue</th><th className="text-left font-normal">Type</th>
              <th className="text-right font-normal">Shares</th><th className="text-right font-normal">Share</th><th className="text-right font-normal">Avg trade</th></tr></thead>
            <tbody>{d.venues.map((v: any) => (
              <tr key={v.venue} className="border-t border-border-subtle"><td className="py-1 font-sans text-text-primary truncate max-w-[14rem]">{v.venue}</td>
                <td className="font-sans text-text-tertiary">{v.kind}</td><td className="text-right">{big(v.shares)}</td>
                <td className="text-right">{Math.round(v.share_of_off_exchange * 100)}%</td><td className="text-right text-text-secondary">{v.avg_trade != null ? Math.round(v.avg_trade) : '—'}</td></tr>))}</tbody>
          </table>
        </Panel>
      </div>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── PROB ─────────────────────────────────────────────────────────────────────
export function ProbView({ symbol }: { symbol: string }) {
  const [expiry, setExpiry] = useState<string | null>(null);
  const [level, setLevel] = useState('');
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/prob/${encodeURIComponent(symbol)}${expiry ? `?expiry=${expiry}` : ''}`, 900_000);
  const custom = useMemo(() => {
    const L = Number(level);
    if (!d || !(L > 0)) return null;
    const c = d.curve, i = c.findIndex((p: any) => p.price >= L);
    if (i <= 0) return { above: i === 0 ? 1 : 0 };
    const a = c[i - 1], b = c[i], w = (L - a.price) / (b.price - a.price);
    return { above: 1 - (a.cdf + w * (b.cdf - a.cdf)) };
  }, [d, level]);
  if (loading && !d) return <Loading label="Reading the option chain…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const p = d.percentiles, px = (v: number) => v.toFixed(2);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-[11px] text-text-tertiary">Expiry</label>
        <select aria-label="Option expiry" value={d.expiry} onChange={(e) => setExpiry(e.target.value)} className="bg-surface-1 border border-border rounded-sm px-2 py-1 text-xs text-text-primary">
          {d.expirations.map((e: string) => <option key={e} value={e}>{e}</option>)}
        </select>
        <span className="text-[11px] text-text-tertiary">{d.days} days · spot {px(d.spot)} · at-the-money vol {(d.atm_iv * 100).toFixed(1)}%</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label="Chance it finishes higher" value={`${Math.round(d.p_up * 100)}%`} sub={`than ${px(d.spot)} on ${d.expiry}`} />
        <Tile label="Expected move (±1σ)" value={`±${px(d.expected_move)}`} sub={`±${((d.expected_move / d.spot) * 100).toFixed(1)}%`} />
        <Tile label="Middle 50%" value={`${px(p['25'])} – ${px(p['75'])}`} sub="25th to 75th percentile" />
        <Tile label="90% range" value={`${px(p['5'])} – ${px(p['95'])}`} sub="5th to 95th percentile" />
        <Tile label="Crash risk vs lognormal" value={`${d.left_tail_vs_lognormal.toFixed(1)}×`} sub="chance of a 15% fall, market vs plain model" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-3">
        <Panel title="Implied distribution of the price at expiry — chance of finishing in each 1% price band">
          <div className="mkt-chart-surface"><LineChart rows={d.curve.map((c: any) => ({ price: c.price.toFixed(2), market: c.density * c.price, lognormal: c.lognormal * c.price }))}
            x="price" height={250} controls={false} fmt={(v) => `${v.toFixed(2)}%`}
            lines={[{ key: 'market', label: 'Market-implied', color: 'rgb(var(--c-bloomberg))' }, { key: 'lognormal', label: 'Lognormal (ATM vol)', color: 'rgb(var(--c-text-tertiary))' }]} /></div>
        </Panel>
        <Panel title="Probability of finishing above / below">
          <table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Price</th><th className="text-right font-normal">Move</th>
              <th className="text-right font-normal">Below</th><th className="text-right font-normal">Above</th><th className="text-right font-normal">Above (lognormal)</th></tr></thead>
            <tbody>{d.levels.map((l: any) => (
              <tr key={l.level} className="border-t border-border-subtle"><td className="py-1">{px(l.level)}</td><td className={cn('text-right', sign(l.move))}>{pct(l.move, 0)}</td>
                <td className="text-right">{(l.p_below * 100).toFixed(1)}%</td><td className="text-right">{(l.p_above * 100).toFixed(1)}%</td>
                <td className="text-right text-text-tertiary">{(l.p_above_lognormal * 100).toFixed(1)}%</td></tr>))}</tbody>
          </table>
          <form className="flex items-center gap-2 mt-3" onSubmit={(e) => e.preventDefault()}>
            <input value={level} onChange={(e) => setLevel(e.target.value)} inputMode="decimal" placeholder="Any price…" aria-label="Price level"
              className="bg-surface-1 border border-border rounded-sm px-2 py-1 text-xs w-28 text-text-primary" />
            {custom && <span className="text-xs text-text-secondary">{(custom.above * 100).toFixed(1)}% above · {((1 - custom.above) * 100).toFixed(1)}% below</span>}
          </form>
        </Panel>
      </div>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── CRPR ─────────────────────────────────────────────────────────────────────
export function CrprView({ symbol }: { symbol: string }) {
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/crpr/${encodeURIComponent(symbol)}`, 6 * 3_600_000);
  if (loading && !d) return <Loading label="Scoring credit from SEC filings…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const x = (v: number | null | undefined, s = '×') => (v == null ? '—' : `${v.toFixed(1)}${s}`);
  const zone = { safe: 'text-green', grey: 'text-amber', distress: 'text-red' } as Record<string, string>;
  const igLine = ['AAA', 'AA', 'A+', 'A', 'A-', 'BBB'].includes(d.synthetic_rating);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label="Synthetic rating" value={d.synthetic_rating} cls={igLine ? 'text-green' : 'text-red'} sub={igLine ? 'investment grade equivalent' : 'high-yield equivalent'} />
        <Tile label="Interest coverage" value={x(d.interest_coverage)}
          sub={d.interest_basis && d.interest_basis !== 'reported' ? `operating income ÷ interest (${d.interest_basis})` : 'operating income ÷ interest, last 4 quarters'} />
        <Tile label="Default spread" value={`${(d.default_spread * 100).toFixed(2)}%`} sub={d.cost_of_debt != null ? `pre-tax cost of debt ≈ ${(d.cost_of_debt * 100).toFixed(2)}%` : ''} />
        <Tile label="Altman Z" value={d.altman_z != null ? d.altman_z.toFixed(2) : '—'} cls={zone[d.altman_zone] ?? ''} sub={d.altman_zone ? `${d.altman_zone} zone` : 'not enough data'} />
        <Tile label="Piotroski F" value={d.piotroski != null ? `${d.piotroski} / 9` : '—'} cls={d.piotroski >= 7 ? 'text-green' : d.piotroski != null && d.piotroski <= 3 ? 'text-red' : ''} sub="financial-strength tests passed" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <Panel title="Leverage and liquidity">
          <table className="w-full text-2xs font-mono tabular-nums"><tbody>
            {[['Total debt', big(d.total_debt)], ['Cash', big(d.cash)], ['Net debt', big(d.net_debt)], ['EBITDA (last 4 quarters)', big(d.ebitda_ttm)],
              ['Net debt ÷ EBITDA', x(d.net_debt_to_ebitda)], ['Debt ÷ equity', x(d.debt_to_equity)], ['Current ratio', x(d.current_ratio)]].map(([k, v]) => (
              <tr key={k} className="border-t border-border-subtle"><td className="py-1 font-sans text-text-secondary">{k}</td><td className="text-right">{v}</td></tr>))}
          </tbody></table>
        </Panel>
        <Panel title="Piotroski tests (last fiscal year vs the one before)">
          <ul className="space-y-1 text-[11px]">{d.piotroski_tests.map((t: any) => (
            <li key={t.test} className="flex justify-between gap-2"><span className="text-text-secondary">{t.test}</span><span className={t.pass ? 'text-green' : 'text-red'}>{t.pass ? 'Yes' : 'No'}</span></li>))}</ul>
        </Panel>
        <Panel title="Coverage and implied rating by fiscal year">
          <table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Year end</th><th className="text-right font-normal">Coverage</th><th className="text-right font-normal">Rating</th></tr></thead>
            <tbody>{[...d.coverage_history].reverse().map((h: any) => (
              <tr key={h.year_end} className="border-t border-border-subtle"><td className="py-1">{h.year_end}</td><td className="text-right">{x(h.coverage)}</td><td className="text-right">{h.rating ?? '—'}</td></tr>))}</tbody>
          </table>
        </Panel>
      </div>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── LEAG ─────────────────────────────────────────────────────────────────────
export function LeagView({ onGo }: { onGo: (fn: string, s?: string) => void }) {
  const [days, setDays] = useStickyState('leag.days', 365);
  const [bank, setBank] = useState<string | null>(null);
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/leag?days=${days}`, 12 * 3_600_000);
  const controls = <div className="flex gap-1">{[180, 365, 730].map((n) => <Chip key={n} on={days === n} onClick={() => setDays(n)}>{n === 730 ? '2 years' : n === 365 ? '12 months' : '6 months'}</Chip>)}</div>;
  if (loading && !d) return <div className="space-y-2">{controls}<Loading label="Searching SEC merger filings…" /></div>;
  if (error && !d) return <div className="space-y-2">{controls}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  const sel = d.rows.find((r: any) => r.bank === bank) ?? d.rows[0];
  const ticker = (c: string) => c.match(/\(([A-Z.\-]+)[,)]/)?.[1];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">{controls}<span className="text-[11px] text-text-tertiary">{d.from} → {d.to}</span></div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3">
        <Panel title="Fairness opinions in US public-company deals">
          <BarList data={d.rows.slice(0, 20).map((r: any) => ({ label: r.bank, value: r.deals }))} fmt={(v) => `${v}`} labelWidth="12rem"
            onSelect={(label) => setBank(label)} />
        </Panel>
        <Panel title={`${sel.bank}: companies advised (${sel.deals})`}>
          <div className="max-h-96 overflow-y-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Company</th><th className="text-left font-normal">Filing</th><th className="text-right font-normal">First filed</th></tr></thead>
            <tbody>{sel.companies.map((c: any) => {
              const t = ticker(c.company);
              return (
                <tr key={c.company + c.filed} onClick={() => t && onGo('MRGR', t)} className={cn('border-t border-border-subtle', t && 'cursor-pointer hover:bg-surface-2')}>
                  <td className="py-1 font-sans text-text-primary">{c.company}</td><td className="text-text-tertiary">{c.forms.join(', ')}</td><td className="text-right">{c.filed}</td></tr>
              );
            })}</tbody>
          </table></div>
          <div className="flex flex-wrap gap-1 mt-2">{d.rows.slice(0, 12).map((r: any) => <Chip key={r.bank} on={sel.bank === r.bank} onClick={() => setBank(r.bank)}>{r.bank}</Chip>)}</div>
        </Panel>
      </div>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── SPF (shown inside ECFC) ───────────────────────────────────────────────────
export function SpfPanel() {
  const { data: d, error } = useJSON<any>('/api/v1/mkt/spf', 12 * 3_600_000);
  if (error && !d) return <p className="text-[11px] text-text-tertiary">Economist consensus unavailable: {error}</p>;
  if (!d) return null;
  const series = Object.entries(d.series) as [string, any][];
  const periods: string[] = series[0]?.[1].quarters.map((q: any) => q.period) ?? [];
  const years: number[] = Array.from(new Set(series.flatMap(([, s]) => s.annual.map((a: any) => a.year)))).sort();
  const chg = (a: number | null, b: number | null) => (a != null && b != null ? a - b : null);
  return (
    <Panel title={`US economist consensus — Survey of Professional Forecasters, ${d.survey}`} right={<span className="text-[11px] text-text-tertiary">median · change vs last survey</span>}>
      <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
        <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Measure</th>
          {periods.map((p) => <th key={p} className="text-right font-normal px-1">{p}</th>)}{years.map((y) => <th key={y} className="text-right font-normal px-1">{y}</th>)}</tr></thead>
        <tbody>{series.map(([k, s]) => (
          <tr key={k} className="border-t border-border-subtle align-top"><td className="py-1 font-sans text-text-secondary">{s.label}</td>
            {periods.map((p) => { const q = s.quarters.find((x: any) => x.period === p); const c = q ? chg(q.median, q.previous_survey) : null;
              return <td key={p} className="text-right px-1">{q?.median != null ? q.median.toFixed(1) : '—'}{c != null && <span className={cn('block text-[9px]', Math.abs(c) < 0.05 ? 'text-text-tertiary' : c > 0 ? 'text-red' : 'text-green')}>{c > 0 ? '+' : ''}{c.toFixed(1)}</span>}</td>; })}
            {years.map((y) => { const a = s.annual.find((x: any) => x.year === y); const c = a ? chg(a.median, a.previous_survey) : null;
              return <td key={y} className="text-right px-1 font-semibold">{a?.median != null ? a.median.toFixed(1) : '—'}{c != null && <span className={cn('block text-[9px] font-normal', Math.abs(c) < 0.05 ? 'text-text-tertiary' : c > 0 ? 'text-red' : 'text-green')}>{c > 0 ? '+' : ''}{c.toFixed(1)}</span>}</td>; })}
          </tr>))}</tbody>
      </table></div>
      <p className="text-[10px] text-text-tertiary mt-2">{d.note} {d.source}</p>
    </Panel>
  );
}

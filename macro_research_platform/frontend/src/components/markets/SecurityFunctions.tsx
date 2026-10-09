// Security function screens: ERN, ANR, HDS, DVD, OMON, RV, HP, BETA, DCF.
import { useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { Donut } from '@/components/ui/Donut';
import { CATEGORICAL } from '@/lib/chartPalette';
import { Chg, ErrorBox, fmtBig, fmtPct, fmtPrice, Loading, Panel, useJSON } from './shared';

const enc = encodeURIComponent;
const n2 = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(d));

function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: 'up' | 'down' | null }) {
  return (
    <div className="px-3 py-2 bg-surface-1 border border-border min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-text-tertiary truncate">{label}</div>
      <div className={cn('font-mono text-base tabular-nums', tone === 'up' ? 'text-green' : tone === 'down' ? 'text-red' : 'text-text-primary')}>{value}</div>
      {sub && <div className="text-[10px] text-text-tertiary truncate">{sub}</div>}
    </div>
  );
}

function Bars({ data, height = 140, fmt = (v: number) => v.toFixed(2) }: { data: { label: string; a: number | null; b?: number | null }[]; height?: number; fmt?: (v: number) => string }) {
  const vals = data.flatMap((d) => [d.a, d.b]).filter((v): v is number => v != null && Number.isFinite(v));
  if (!vals.length) return <div className="text-2xs text-text-tertiary">No data.</div>;
  const max = Math.max(0, ...vals), min = Math.min(0, ...vals);
  const span = max - min || 1;
  const y = (v: number) => ((max - v) / span) * (height - 18);
  const w = 100 / data.length;
  return (
    <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }} role="img" aria-label="Bar chart">
      <line x1="0" x2="100" y1={y(0)} y2={y(0)} stroke="var(--border)" strokeWidth="0.3" />
      {data.map((d, i) => (
        <g key={d.label}>
          {d.b != null && <rect x={i * w + w * 0.15} width={w * 0.32} y={Math.min(y(d.b), y(0))} height={Math.abs(y(d.b) - y(0))} fill="var(--text-tertiary)" opacity="0.5"><title>{`${d.label} estimate ${fmt(d.b)}`}</title></rect>}
          {d.a != null && <rect x={i * w + (d.b != null ? w * 0.5 : w * 0.25)} width={w * (d.b != null ? 0.32 : 0.5)} y={Math.min(y(d.a), y(0))} height={Math.abs(y(d.a) - y(0))}
            fill={d.b != null ? (d.a >= d.b ? 'rgb(var(--c-green))' : 'rgb(var(--c-red))') : 'rgb(var(--c-bloomberg))'}><title>{`${d.label} ${fmt(d.a)}`}</title></rect>}
          <text x={i * w + w / 2} y={height - 4} fontSize="3.2" textAnchor="middle" fill="var(--text-tertiary)">{d.label}</text>
        </g>
      ))}
    </svg>
  );
}

// ── ERN ──────────────────────────────────────────────────────────────────────
export function ErnView({ symbol }: { symbol: string }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/ern/${enc(symbol)}`);
  if (loading && !data) return <Loading label="Loading earnings…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  const hist = [...data.history].reverse().slice(-12);
  const up = data.upcoming?.[0];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Stat label="Next report" value={up ? up.date : '—'} sub={up?.eps_estimate != null ? `EPS estimate ${n2(up.eps_estimate)} ${data.currency ?? ''}` : 'No date announced'} />
        <Stat label="Beat rate" value={data.beat_rate != null ? fmtPct(data.beat_rate, 0).replace('+', '') : '—'} sub={`of the last ${data.history.length} reports`} />
        <Stat label="Average surprise" value={data.avg_surprise_pct != null ? `${data.avg_surprise_pct > 0 ? '+' : ''}${data.avg_surprise_pct.toFixed(1)}%` : '—'}
          tone={data.avg_surprise_pct > 0 ? 'up' : data.avg_surprise_pct < 0 ? 'down' : null} />
        <Stat label="Last report" value={hist.length ? hist[hist.length - 1].date : '—'} sub={hist.length ? `EPS ${n2(hist[hist.length - 1].eps_reported)} vs ${n2(hist[hist.length - 1].eps_estimate)} est.` : ''} />
      </div>
      <Panel title="Reported EPS vs estimate — green = beat, red = miss (grey = estimate)">
        <Bars data={hist.map((h: any) => ({ label: h.date.slice(2, 7), a: h.eps_reported, b: h.eps_estimate }))} />
      </Panel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="Consensus estimates">
          <EstTable rows={data.estimates.eps} cols={[['avg', 'EPS (avg)'], ['low', 'Low'], ['high', 'High'], ['yearAgoEps', 'Year ago'], ['growth', 'Growth', 'pct'], ['numberOfAnalysts', 'Analysts', 'int']]} />
          <div className="mt-3"><EstTable rows={data.estimates.revenue} cols={[['avg', 'Revenue (avg)', 'big'], ['low', 'Low', 'big'], ['high', 'High', 'big'], ['growth', 'Growth', 'pct'], ['numberOfAnalysts', 'Analysts', 'int']]} /></div>
        </Panel>
        <Panel title="How estimates are moving">
          <EstTable rows={data.estimates.eps_trend} cols={[['current', 'Now'], ['7daysAgo', '7 days ago'], ['30daysAgo', '30 days'], ['60daysAgo', '60 days'], ['90daysAgo', '90 days']]} />
          <div className="mt-3"><EstTable rows={data.estimates.eps_revisions} cols={[['upLast7days', 'Up 7d', 'int'], ['upLast30days', 'Up 30d', 'int'], ['downLast7Days', 'Down 7d', 'int'], ['downLast30days', 'Down 30d', 'int']]} /></div>
          <div className="text-[10px] text-text-tertiary mt-2">Periods: 0q = current quarter, +1q = next, 0y = this fiscal year, +1y = next.</div>
        </Panel>
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source}</div>
    </div>
  );
}

function EstTable({ rows, cols }: { rows: any[]; cols: [string, string, string?][] }) {
  if (!rows?.length) return <div className="text-2xs text-text-tertiary">Not available.</div>;
  const f = (v: any, kind?: string) => v == null ? '—' : kind === 'pct' ? fmtPct(v, 1) : kind === 'big' ? fmtBig(v) : kind === 'int' ? String(Math.round(v)) : n2(v);
  return (
    <table className="w-full text-2xs font-mono">
      <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Period</th>{cols.map(([, l]) => <th key={l} className="text-right font-normal">{l}</th>)}</tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.period} className="border-t border-border-subtle"><td className="text-text-secondary">{r.period}</td>
          {cols.map(([k, l, kind]) => <td key={l} className="text-right">{f(r[k], kind)}</td>)}</tr>))}</tbody>
    </table>
  );
}

// ── ANR ──────────────────────────────────────────────────────────────────────
export function AnrView({ symbol }: { symbol: string }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/anr/${enc(symbol)}`);
  if (loading && !data) return <Loading label="Loading analyst data…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  const t = data.targets ?? {};
  const now = data.summary?.[0];
  const total = now ? ['strongBuy', 'buy', 'hold', 'sell', 'strongSell'].reduce((a, k) => a + (now[k] ?? 0), 0) : 0;
  const up = t.mean && t.current ? t.mean / t.current - 1 : null;
  const pos = (v: number) => (t.high && t.low && t.high > t.low ? ((v - t.low) / (t.high - t.low)) * 100 : 50);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Stat label="Consensus" value={(data.recommendation ?? '—').replace('_', ' ')} sub={`${data.analysts ?? total} analysts`} />
        <Stat label="Mean target" value={fmtPrice(t.mean)} sub={data.currency} />
        <Stat label="Implied move" value={up != null ? fmtPct(up, 1) : '—'} tone={up != null ? (up > 0 ? 'up' : 'down') : null} sub="mean target vs price" />
        <Stat label="Target range" value={t.low != null ? `${fmtPrice(t.low)} – ${fmtPrice(t.high)}` : '—'} />
      </div>
      {t.low != null && t.current != null && (
        <Panel title="Price vs analyst target range">
          <div className="relative h-10 mx-2">
            <div className="absolute top-4 left-0 right-0 h-1.5 bg-surface-3" />
            {[['Low', t.low], ['Mean', t.mean], ['High', t.high]].map(([l, v]) => v != null && (
              <div key={l as string} className="absolute top-2 -translate-x-1/2 text-center" style={{ left: `${pos(v as number)}%` }}>
                <div className="w-0.5 h-5 bg-text-tertiary mx-auto" /><div className="text-[10px] text-text-tertiary whitespace-nowrap">{l} {fmtPrice(v as number)}</div></div>))}
            <div className="absolute top-1 -translate-x-1/2" style={{ left: `${Math.max(0, Math.min(100, pos(t.current)))}%` }} title={`Price ${fmtPrice(t.current)}`}>
              <div className="w-3 h-3 rotate-45 bg-bloomberg mt-1.5" /></div>
          </div>
          <div className="text-[10px] text-text-tertiary mt-3">◆ = current price {fmtPrice(t.current)}</div>
        </Panel>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.4fr] gap-3">
        <Panel title="Ratings over the last 4 months">
          <div className="space-y-2">{(data.summary ?? []).map((r: any) => {
            const tot = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell'].reduce((a, k) => a + (r[k] ?? 0), 0) || 1;
            const segs: [string, number, string][] = [['Strong buy', r.strongBuy, 'rgb(var(--c-green))'], ['Buy', r.buy, 'rgb(var(--c-green) / 0.55)'],
              ['Hold', r.hold, 'var(--text-tertiary)'], ['Sell', r.sell, 'rgb(var(--c-red) / 0.6)'], ['Strong sell', r.strongSell, 'rgb(var(--c-red))']];
            return (
              <div key={r.period} className="grid grid-cols-[3rem_1fr_2rem] items-center gap-2 text-2xs">
                <span className="text-text-tertiary">{r.period === '0m' ? 'Now' : r.period.replace('-', '−').replace('m', ' mo')}</span>
                <div className="flex h-3 overflow-hidden">{segs.map(([l, v, c]) => v ? <div key={l} title={`${l}: ${v}`} style={{ width: `${(v / tot) * 100}%`, background: c }} /> : null)}</div>
                <span className="font-mono text-text-tertiary text-right">{tot}</span>
              </div>);
          })}</div>
          <div className="flex flex-wrap gap-3 mt-2 text-[10px] text-text-tertiary">
            <span><i className="inline-block w-2 h-2 mr-1" style={{ background: 'rgb(var(--c-green))' }} />Strong buy</span>
            <span><i className="inline-block w-2 h-2 mr-1" style={{ background: 'rgb(var(--c-green) / 0.55)' }} />Buy</span>
            <span><i className="inline-block w-2 h-2 mr-1" style={{ background: 'var(--text-tertiary)' }} />Hold</span>
            <span><i className="inline-block w-2 h-2 mr-1" style={{ background: 'rgb(var(--c-red))' }} />Sell</span>
          </div>
        </Panel>
        <Panel title="Recent rating and target changes">
          <div className="max-h-80 overflow-y-auto"><table className="w-full text-2xs">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Date</th><th className="text-left font-normal">Firm</th>
              <th className="text-left font-normal">Rating</th><th className="text-right font-normal">Target</th></tr></thead>
            <tbody>{data.changes.map((c: any, i: number) => (
              <tr key={i} className="border-t border-border-subtle">
                <td className="font-mono text-text-tertiary py-1">{c.date}</td><td className="text-text-primary">{c.Firm}</td>
                <td className="text-text-secondary">{c.FromGrade && c.FromGrade !== c.ToGrade ? <>{c.FromGrade} → </> : null}
                  <span className={/up/i.test(c.Action) ? 'text-green' : /down/i.test(c.Action) ? 'text-red' : ''}>{c.ToGrade}</span></td>
                <td className="text-right font-mono">{c.currentPriceTarget ? <>{c.priorPriceTarget ? <span className="text-text-tertiary">{fmtPrice(c.priorPriceTarget)} → </span> : null}
                  <span className={c.currentPriceTarget > (c.priorPriceTarget ?? c.currentPriceTarget) ? 'text-green' : c.currentPriceTarget < (c.priorPriceTarget ?? 0) ? 'text-red' : ''}>{fmtPrice(c.currentPriceTarget)}</span></> : '—'}</td>
              </tr>))}</tbody>
          </table></div>
        </Panel>
      </div>
    </div>
  );
}

// ── HDS ──────────────────────────────────────────────────────────────────────
export function HdsView({ symbol }: { symbol: string }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/hds/${enc(symbol)}`);
  if (loading && !data) return <Loading label="Loading holders…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  const b = data.breakdown;
  const inst = b.institutionsPercentHeld, ins = b.insidersPercentHeld;
  const other = inst != null && ins != null ? Math.max(0, 1 - inst - ins) : null;
  const table = (rows: any[]) => (
    <table className="w-full text-2xs">
      <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Holder</th><th className="text-right font-normal">% held</th>
        <th className="text-right font-normal">Shares</th><th className="text-right font-normal">Value</th><th className="text-right font-normal">Change</th></tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={i} className="border-t border-border-subtle"><td className="py-1 text-text-primary truncate max-w-[14rem]">{r.Holder}</td>
          <td className="text-right font-mono">{fmtPct(r.pctHeld, 2).replace('+', '')}</td><td className="text-right font-mono">{fmtBig(r.Shares)}</td>
          <td className="text-right font-mono">{fmtBig(r.Value)}</td><td className="text-right"><Chg v={r.pctChange} d={1} /></td></tr>))}</tbody>
    </table>);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3">
        <Panel title="Who owns it">
          {inst != null ? <Donut data={[{ label: 'Institutions', value: inst }, { label: 'Insiders', value: ins ?? 0 }, { label: 'Retail & other', value: other ?? 0 }]}
            fmt={(v) => `${(v * 100).toFixed(1)}%`} centerValue={b.institutionsCount ? Math.round(b.institutionsCount).toLocaleString() : undefined} centerLabel="institutions" />
            : <div className="text-2xs text-text-tertiary">No ownership split available.</div>}
        </Panel>
        <Panel title="Top institutions (13F)">{data.institutions.length ? table(data.institutions) : <div className="text-2xs text-text-tertiary">None reported.</div>}</Panel>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="Top mutual funds">{data.funds.length ? table(data.funds) : <div className="text-2xs text-text-tertiary">None reported.</div>}</Panel>
        <Panel title="Insider transactions (Form 4)">
          {data.insiders.length ? <div className="max-h-80 overflow-y-auto"><table className="w-full text-2xs">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Date</th><th className="text-left font-normal">Insider</th>
              <th className="text-left font-normal">Transaction</th><th className="text-right font-normal">Shares</th><th className="text-right font-normal">Value</th></tr></thead>
            <tbody>{data.insiders.map((r: any, i: number) => (
              <tr key={i} className="border-t border-border-subtle" title={r.Text ?? ''}>
                <td className="font-mono text-text-tertiary py-1">{r['Start Date']}</td><td className="text-text-primary truncate max-w-[10rem]">{r.Insider}<span className="text-text-tertiary"> · {r.Position}</span></td>
                <td className={cn(/sale|sell/i.test(r.Text ?? r.Transaction ?? '') ? 'text-red' : /purchase|buy/i.test(r.Text ?? r.Transaction ?? '') ? 'text-green' : 'text-text-secondary')}>
                  {r.Transaction || (r.Text ?? '').split(' at ')[0]}</td>
                <td className="text-right font-mono">{fmtBig(r.Shares)}</td><td className="text-right font-mono">{fmtBig(r.Value)}</td></tr>))}</tbody>
          </table></div> : <div className="text-2xs text-text-tertiary">No recent insider filings.</div>}
        </Panel>
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source}. 13F holdings are reported quarterly with up to a 45-day lag.</div>
    </div>
  );
}

// ── DVD ──────────────────────────────────────────────────────────────────────
export function DvdView({ symbol }: { symbol: string }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/dvd/${enc(symbol)}`);
  if (loading && !data) return <Loading label="Loading dividends…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  if (!data.payments.length) return <Panel title="Dividends"><div className="text-2xs text-text-tertiary">{symbol} has not paid dividends in Yahoo's records.</div></Panel>;
  const g = data.growth;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Stat label="Yield" value={data.dividend_yield != null ? fmtPct(data.dividend_yield, 2).replace('+', '') : '—'} sub={data.forward_rate ? `${n2(data.forward_rate)} ${data.currency} / yr` : ''} />
        <Stat label="Payout ratio" value={data.payout_ratio != null ? fmtPct(data.payout_ratio, 0).replace('+', '') : '—'} sub="of earnings" />
        <Stat label="Growth 5y / yr" value={g['5y'] != null ? fmtPct(g['5y'], 1) : '—'} tone={g['5y'] > 0 ? 'up' : g['5y'] < 0 ? 'down' : null} sub={g['10y'] != null ? `10y ${fmtPct(g['10y'], 1)}` : ''} />
        <Stat label="Consecutive increases" value={`${data.consecutive_increases} yrs`} sub={data.consecutive_increases >= 50 ? 'Dividend King' : data.consecutive_increases >= 25 ? 'Dividend Aristocrat territory' : ''} />
        <Stat label="Last payment" value={`${n2(data.payments[0].amount, 4)}`} sub={data.payments[0].date} />
      </div>
      <Panel title={`Dividends per share by year (${data.currency})`}>
        <Bars data={data.annual.map((a: any) => ({ label: String(a.year).slice(2), a: a.total }))} fmt={(v) => v.toFixed(3)} />
      </Panel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="Payment history">
          <div className="max-h-72 overflow-y-auto"><table className="w-full text-2xs font-mono"><tbody>{data.payments.map((p: any) => (
            <tr key={p.date} className="border-t border-border-subtle"><td className="text-text-tertiary py-0.5">{p.date}</td><td className="text-right">{n2(p.amount, 4)}</td></tr>))}</tbody></table></div>
        </Panel>
        <Panel title="Stock splits">
          {data.splits.length ? <table className="w-full text-2xs font-mono"><tbody>{data.splits.map((s: any) => (
            <tr key={s.date} className="border-t border-border-subtle"><td className="text-text-tertiary py-0.5">{s.date}</td><td className="text-right">{s.ratio >= 1 ? `${s.ratio}-for-1` : `1-for-${(1 / s.ratio).toFixed(0)}`}</td></tr>))}</tbody></table>
            : <div className="text-2xs text-text-tertiary">No splits.</div>}
        </Panel>
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source}. Amounts are split-adjusted. Increase streak uses each year's median payment.</div>
    </div>
  );
}

// ── OMON ─────────────────────────────────────────────────────────────────────
export function OmonView({ symbol }: { symbol: string }) {
  const [expiry, setExpiry] = useState<string | null>(null);
  const [range, setRange] = useState(10);
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/omon/${enc(symbol)}${expiry ? `?expiry=${expiry}` : ''}`, 300_000);
  const term = useJSON<any>(`/api/v1/mkt/omon/${enc(symbol)}/term`);
  const rows = useMemo(() => {
    if (!data) return [];
    const strikes = Array.from(new Set([...data.calls, ...data.puts].map((r: any) => r.strike))).sort((a: any, b: any) => a - b) as number[];
    const atm = strikes.reduce((b, k) => (Math.abs(k - data.underlying) < Math.abs(b - data.underlying) ? k : b), strikes[0]);
    const i = strikes.indexOf(atm);
    return strikes.slice(Math.max(0, i - range), i + range + 1).map((k) => ({ k, c: data.calls.find((x: any) => x.strike === k), p: data.puts.find((x: any) => x.strike === k), atm: k === atm }));
  }, [data, range]);
  if (loading && !data) return <Loading label="Loading option chain…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  const cell = (r: any, k: string, d = 2) => r?.[k] == null ? '—' : k === 'iv' ? `${(r[k] * 100).toFixed(1)}%` : k === 'open_interest' || k === 'volume' ? fmtBig(r[k]) : n2(r[k], d);
  const cols: [string, string, number?][] = [['bid', 'Bid'], ['ask', 'Ask'], ['iv', 'IV'], ['delta', 'Δ', 3], ['gamma', 'Γ', 4], ['theta', 'Θ/day', 3], ['vega', 'Vega', 3], ['open_interest', 'OI'], ['volume', 'Vol']];
  return (
    <div className="space-y-3">
      {data.warning && <div className="px-3 py-2 border border-amber/50 bg-amber/5 text-2xs text-amber">{data.warning}</div>}
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-2xs text-text-tertiary">Expiry
          <select value={data.expiry} onChange={(e) => setExpiry(e.target.value)} className="ml-2 bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary">
            {data.expirations.map((e: string) => <option key={e} value={e}>{e}</option>)}</select></label>
        <label className="text-2xs text-text-tertiary">Strikes around the money
          <select value={range} onChange={(e) => setRange(Number(e.target.value))} className="ml-2 bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary">
            {[5, 10, 20, 50].map((n) => <option key={n} value={n}>±{n}</option>)}</select></label>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        <Stat label="Underlying" value={fmtPrice(data.underlying)} sub={data.currency} />
        <Stat label="Days to expiry" value={data.days} />
        <Stat label="ATM implied vol" value={data.atm_iv != null ? `${(data.atm_iv * 100).toFixed(1)}%` : '—'} />
        <Stat label="Expected move" value={data.expected_move != null ? `±${fmtPrice(data.expected_move)}` : '—'} sub={data.expected_move ? `±${((data.expected_move / data.underlying) * 100).toFixed(1)}% by expiry (1σ)` : ''} />
        <Stat label="Put / call (OI)" value={n2(data.put_call_oi)} sub={`volume ${n2(data.put_call_volume)}`} />
        <Stat label="Max pain" value={fmtPrice(data.max_pain)} sub="strike with least option payout" />
      </div>
      <Panel title={`Chain — calls left, puts right · ${data.expiry}`}>
        <div className="overflow-x-auto"><table className="w-full text-[11px] font-mono tabular-nums">
          <thead><tr className="text-text-tertiary">
            {cols.map(([, l]) => <th key={`c${l}`} className="font-normal text-right px-1.5">{l}</th>)}
            <th className="font-normal text-center px-2 text-text-primary">Strike</th>
            {cols.map(([, l]) => <th key={`p${l}`} className="font-normal text-right px-1.5">{l}</th>)}</tr></thead>
          <tbody>{rows.map(({ k, c, p, atm }) => (
            <tr key={k} className={cn('border-t border-border-subtle', atm && 'border-y-2 border-bloomberg/60')}>
              {cols.map(([key, l, d]) => <td key={`c${l}`} className={cn('text-right px-1.5 py-0.5', c?.itm && 'bg-blue/5')}>{cell(c, key, d)}</td>)}
              <td className="text-center px-2 font-semibold text-text-primary bg-surface-2">{n2(k)}</td>
              {cols.map(([key, l, d]) => <td key={`p${l}`} className={cn('text-right px-1.5 py-0.5', p?.itm && 'bg-blue/5')}>{cell(p, key, d)}</td>)}
            </tr>))}</tbody>
        </table></div>
        <div className="text-[10px] text-text-tertiary mt-2">Shaded = in the money. Θ is per calendar day; Vega per 1 vol point. {data.source}</div>
      </Panel>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="Volatility smile (out-of-the-money IV by strike)">
          {data.smile.length > 2 ? <LineChart rows={data.smile.map((s: any) => ({ ...s, x: s.strike.toFixed(0) }))} x="x" height={200}
            lines={[{ key: 'iv', label: 'IV', color: CATEGORICAL[0] }]} fmt={(v) => `${(v * 100).toFixed(1)}%`} /> : <div className="text-2xs text-text-tertiary">Not enough quotes.</div>}
        </Panel>
        <Panel title="Term structure (ATM IV by expiry)">
          {term.data?.term?.length > 1 ? <LineChart rows={term.data.term.map((t: any) => ({ ...t, x: t.expiry }))} x="x" height={200}
            lines={[{ key: 'atm_iv', label: 'ATM IV', color: CATEGORICAL[1] }]} fmt={(v) => `${(v * 100).toFixed(1)}%`} />
            : term.loading ? <Loading /> : <div className="text-2xs text-text-tertiary">Not enough expiries priced.</div>}
        </Panel>
      </div>
    </div>
  );
}

// ── RV ───────────────────────────────────────────────────────────────────────
export function RvView({ symbol, onOpen }: { symbol: string; onOpen: (s: string) => void }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/rv/${enc(symbol)}`);
  const [sort, setSort] = useState('market_cap_usd');
  if (loading && !data) return <Loading label="Finding peers in 17 markets…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  const cols: [string, string, 'x' | 'pct' | 'big'][] = [['market_cap_usd', 'Mkt cap $', 'big'], ['pe', 'P/E', 'x'], ['forward_pe', 'Fwd P/E', 'x'], ['ev_ebitda', 'EV/EBITDA', 'x'],
    ['price_to_book', 'P/B', 'x'], ['price_to_sales', 'P/S', 'x'], ['gross_margin', 'Gross mgn', 'pct'], ['operating_margin', 'Op mgn', 'pct'], ['roe', 'ROE', 'pct'],
    ['revenue_growth', 'Rev growth', 'pct'], ['dividend_yield', 'Yield', 'pct']];
  const f = (v: any, kind: string) => v == null ? '—' : kind === 'big' ? fmtBig(v) : kind === 'pct' ? `${(v * 100).toFixed(1)}%` : v.toFixed(1);
  const rows = [...data.rows].sort((a: any, b: any) => (b[sort] ?? -1e18) - (a[sort] ?? -1e18));
  const med = data.peer_median;
  return (
    <Panel title={`${data.industry} peers worldwide — click a column to sort, a row to open`}>
      <div className="overflow-x-auto"><table className="w-full text-2xs">
        <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Company</th>
          {cols.map(([k, l]) => <th key={k} onClick={() => setSort(k)} className={cn('text-right font-normal cursor-pointer hover:text-text-primary px-1.5', sort === k && 'text-bloomberg')}>{l}</th>)}</tr></thead>
        <tbody>
          {rows.map((r: any) => (
            <tr key={r.symbol} onClick={() => !r.subject && onOpen(r.symbol)} className={cn('border-t border-border-subtle', r.subject ? 'bg-bloomberg/10' : 'cursor-pointer hover:bg-surface-3')}>
              <td className="py-1 pr-2"><span className="font-mono text-text-primary">{r.symbol}</span> <span className="text-text-secondary">{r.name}</span>
                {r.country && <span className="text-text-tertiary"> · {r.country}</span>}</td>
              {cols.map(([k, , kind]) => {
                const v = r[k], m = med?.[k];
                const better = m != null && v != null && k !== 'market_cap_usd' ? (kind === 'x' ? v < m : v > m) : null;
                return <td key={k} className={cn('text-right font-mono px-1.5', better === true && 'text-green', better === false && 'text-text-secondary')}>{f(v, kind)}</td>;
              })}
            </tr>))}
          <tr className="border-t-2 border-border font-semibold"><td className="py-1 text-text-secondary">Peer median</td>
            {cols.map(([k, , kind]) => <td key={k} className="text-right font-mono px-1.5 text-text-primary">{k === 'market_cap_usd' ? '' : f(med?.[k], kind)}</td>)}</tr>
        </tbody>
      </table></div>
      <div className="text-[10px] text-text-tertiary mt-2">Green = cheaper (multiples) or stronger (margins, growth) than the peer median. {data.source}</div>
    </Panel>
  );
}

// ── HP ───────────────────────────────────────────────────────────────────────
export function HpView({ symbol }: { symbol: string }) {
  const [period, setPeriod] = useState('1y');
  const [interval, setInterval_] = useState('1d');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/hp/${enc(symbol)}?period=${period}&interval=${interval}`);
  const csv = () => {
    if (!data) return;
    const lines = ['date,open,high,low,close,volume', ...data.rows.map((r: any) => [r.date, r.open, r.high, r.low, r.close, r.volume].join(','))];
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
    a.download = `${symbol}_${period}_${interval}.csv`;
    a.click();
  };
  return (
    <Panel title="Historical prices" right={<div className="flex items-center gap-2">
      <select value={period} onChange={(e) => setPeriod(e.target.value)} className="bg-surface-1 border border-border px-1.5 py-0.5 text-2xs text-text-primary">
        {['1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max'].map((p) => <option key={p}>{p}</option>)}</select>
      <select value={interval} onChange={(e) => setInterval_(e.target.value)} className="bg-surface-1 border border-border px-1.5 py-0.5 text-2xs text-text-primary">
        <option value="1d">Daily</option><option value="1wk">Weekly</option><option value="1mo">Monthly</option></select>
      <button onClick={csv} disabled={!data} className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs border border-border hover:border-bloomberg disabled:opacity-40"><Download className="w-3 h-3" />CSV</button>
    </div>}>
      {loading && !data ? <Loading /> : error ? <ErrorBox msg={error} /> : data && (
        <>
          <div className="max-h-[32rem] overflow-y-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary">{['Date', 'Open', 'High', 'Low', 'Close', 'Change', 'Volume'].map((h) => <th key={h} className={cn('font-normal py-1', h === 'Date' ? 'text-left' : 'text-right')}>{h}</th>)}</tr></thead>
            <tbody>{data.rows.map((r: any) => (
              <tr key={r.date} className="border-t border-border-subtle"><td className="text-text-secondary py-0.5">{r.date}</td>
                <td className="text-right">{fmtPrice(r.open)}</td><td className="text-right">{fmtPrice(r.high)}</td><td className="text-right">{fmtPrice(r.low)}</td>
                <td className="text-right text-text-primary">{fmtPrice(r.close)}</td><td className="text-right"><Chg v={r.change_pct} /></td><td className="text-right">{fmtBig(r.volume)}</td></tr>))}</tbody>
          </table></div>
          <div className="text-[10px] text-text-tertiary mt-2">{data.note} {data.currency}.</div>
        </>
      )}
    </Panel>
  );
}

// ── BETA ─────────────────────────────────────────────────────────────────────
export function BetaView({ symbol }: { symbol: string }) {
  const [bench, setBench] = useState('^GSPC');
  const [period, setPeriod] = useState('2y');
  const [freq, setFreq] = useState('W');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/beta/${enc(symbol)}?benchmark=${enc(bench)}&period=${period}&freq=${freq}`);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center text-2xs text-text-tertiary">
        <label>Benchmark <input value={bench} onChange={(e) => setBench(e.target.value.toUpperCase())} className="ml-1 w-24 bg-surface-1 border border-border px-2 py-1 font-mono text-xs text-text-primary" /></label>
        <span className="flex gap-1">{['^GSPC', '^NDX', '^STOXX50E', '^N225', 'ACWI'].map((b) => <button key={b} onClick={() => setBench(b)} className={cn('px-1.5 py-0.5 border', bench === b ? 'border-bloomberg text-bloomberg' : 'border-border')}>{b}</button>)}</span>
        <select value={period} onChange={(e) => setPeriod(e.target.value)} className="bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary">{['1y', '2y', '3y', '5y', '10y'].map((p) => <option key={p}>{p}</option>)}</select>
        <select value={freq} onChange={(e) => setFreq(e.target.value)} className="bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary"><option value="D">Daily</option><option value="W">Weekly</option><option value="M">Monthly</option></select>
      </div>
      {loading && !data ? <Loading /> : error ? <ErrorBox msg={error} /> : data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <Stat label="Raw beta" value={n2(data.beta)} sub={`± ${n2(data.beta_se)} (1 s.e.)`} />
            <Stat label="Adjusted beta" value={n2(data.adjusted_beta)} sub="0.67 × raw + 0.33" />
            <Stat label="R²" value={n2(data.r2)} sub="share of moves explained" />
            <Stat label="Correlation" value={n2(data.correlation)} />
            <Stat label="Alpha / yr" value={fmtPct(data.alpha_annual, 1)} tone={data.alpha_annual > 0 ? 'up' : 'down'} sub={`${data.observations} observations`} />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Panel title={`Returns: ${symbol} (up) vs ${bench} (across)`}><Scatter pts={data.scatter} beta={data.beta} alpha={data.alpha_annual / ({ D: 252, W: 52, M: 12 } as any)[freq]} /></Panel>
            <Panel title="Rolling beta">{data.rolling.length > 2 ? <LineChart rows={data.rolling} x="date" height={220} baseline={1}
              lines={[{ key: 'beta', label: 'Beta', color: CATEGORICAL[0] }]} fmt={(v) => v.toFixed(2)} /> : <div className="text-2xs text-text-tertiary">Not enough history.</div>}</Panel>
          </div>
          <div className="text-[10px] text-text-tertiary">{data.note}</div>
        </>
      )}
    </div>
  );
}

function Scatter({ pts, beta, alpha }: { pts: { x: number; y: number }[]; beta: number; alpha: number }) {
  const W = 300, H = 220, P = 24;
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  const m = Math.max(...xs.map(Math.abs), ...ys.map(Math.abs), 0.01);
  const sx = (v: number) => P + ((v + m) / (2 * m)) * (W - 2 * P);
  const sy = (v: number) => H - P - ((v + m) / (2 * m)) * (H - 2 * P);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 260 }} role="img" aria-label="Return scatter with regression line">
      <line x1={P} x2={W - P} y1={sy(0)} y2={sy(0)} stroke="var(--border)" />
      <line y1={P} y2={H - P} x1={sx(0)} x2={sx(0)} stroke="var(--border)" />
      {pts.map((p, i) => <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r="1.8" fill="rgb(var(--c-blue))" opacity="0.45" />)}
      <line x1={sx(-m)} y1={sy(alpha + beta * -m)} x2={sx(m)} y2={sy(alpha + beta * m)} stroke="rgb(var(--c-bloomberg))" strokeWidth="1.5" />
      <text x={W - P} y={P - 6} fontSize="9" textAnchor="end" fill="var(--text-secondary)">slope = beta {beta.toFixed(2)}</text>
    </svg>
  );
}

// ── DCF ──────────────────────────────────────────────────────────────────────
export function DcfView({ symbol }: { symbol: string }) {
  const [p, setP] = useState<Record<string, string>>({});
  const qs = Object.entries(p).filter(([, v]) => v !== '').map(([k, v]) => `${k}=${k === 'years' ? v : Number(v) / (k === 'fcf' ? 1 : 100)}`).join('&');
  const [url, setUrl] = useState(`/api/v1/mkt/dcf/${enc(symbol)}`);
  const { data, error, loading } = useJSON<any>(url);
  const inp = data?.inputs, v = data?.valuation;
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setP({ ...p, [k]: e.target.value });
  const field = (k: string, label: string, def: number | null | undefined, unit: string, hint: string) => (
    <label className="text-[10px] uppercase tracking-wider text-text-tertiary" title={hint}>{label}
      <div className="flex items-center mt-0.5"><input type="number" step="any" placeholder={def != null ? String(unit === '%' ? +(def * 100).toFixed(2) : def) : ''} value={p[k] ?? ''} onChange={set(k)}
        className="w-full bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary" /><span className="ml-1 text-text-tertiary normal-case">{unit}</span></div></label>);
  return (
    <div className="space-y-3">
      {loading && !data ? <Loading label="Building the model…" /> : error ? <ErrorBox msg={error} /> : data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Stat label="Value per share" value={fmtPrice(v.per_share)} sub={inp.currency} />
            <Stat label="vs price" value={v.upside != null ? fmtPct(v.upside, 1) : '—'} tone={v.upside != null ? (v.upside > 0 ? 'up' : 'down') : null} sub={inp.price ? `price ${fmtPrice(inp.price)}` : data.currency_note ?? ''} />
            <Stat label="Enterprise value" value={fmtBig(v.enterprise_value, inp.currency)} sub={`net debt ${fmtBig(inp.net_debt)}`} />
            <Stat label="Terminal value share" value={fmtPct(v.terminal_share, 0).replace('+', '')} sub="of enterprise value" />
          </div>
          {inp.investment_warning && <div className="px-3 py-2 border border-amber/50 bg-amber/5 text-2xs text-amber">{inp.investment_warning}</div>}
          <Panel title="Assumptions — blank = default shown in grey">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {field('growth', 'Growth / yr', inp.used.growth, '%', 'Free cash flow growth during the projection years')}
              {field('years', 'Years', inp.used.years, 'yrs', 'Projection years before the terminal value')}
              {field('terminal_growth', 'Terminal growth', inp.used.terminal_growth, '%', 'Perpetual growth after the projection — usually 2–3%')}
              {field('discount', 'Discount rate', inp.used.discount, '%', 'CAPM cost of equity by default: 10-year Treasury + beta × 5%')}
              {field('fcf', 'Starting FCF', inp.used.fcf, inp.currency ?? '', 'Trailing-twelve-month free cash flow')}
            </div>
            <button onClick={() => setUrl(`/api/v1/mkt/dcf/${enc(symbol)}${qs ? `?${qs}` : ''}`)} className="mt-3 px-4 py-1.5 text-xs bg-bloomberg text-text-inverse">Recalculate</button>
            <span className="ml-3 text-[10px] text-text-tertiary">FCF source: {inp.fcf_source} · beta {n2(inp.beta)} · 10y {inp.risk_free != null ? `${(inp.risk_free * 100).toFixed(2)}%` : '—'}</span>
          </Panel>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Panel title="Projected free cash flow">
              <Bars data={v.projection.map((r: any) => ({ label: `Y${r.year}`, a: r.fcf }))} fmt={(x) => fmtBig(x)} />
              <div className="text-[10px] text-text-tertiary mt-1">PV of cash flows {fmtBig(v.pv_cash_flows)} + PV of terminal value {fmtBig(v.pv_terminal)}</div>
            </Panel>
            <Panel title="Sensitivity — value per share (rows: discount rate, columns: terminal growth)">
              <table className="w-full text-2xs font-mono">
                <thead><tr className="text-text-tertiary"><th />{v.sensitivity.terminal_growth.map((g: number) => <th key={g} className="text-right font-normal">{(g * 100).toFixed(1)}%</th>)}</tr></thead>
                <tbody>{v.sensitivity.discount_rates.map((r: number, i: number) => (
                  <tr key={r} className="border-t border-border-subtle"><td className="text-text-tertiary">{(r * 100).toFixed(1)}%</td>
                    {v.sensitivity.per_share[i].map((x: number | null, j: number) => (
                      <td key={j} className={cn('text-right py-0.5', i === 2 && j === 2 && 'text-bloomberg font-semibold',
                        inp.price && x != null && (x > inp.price ? 'text-green' : 'text-red'))}>{x == null ? '—' : fmtPrice(x)}</td>))}</tr>))}</tbody>
              </table>
              <div className="text-[10px] text-text-tertiary mt-1">Green = above today's price. Centre = your assumptions.</div>
            </Panel>
          </div>
          <div className="text-[10px] text-text-tertiary">{inp.note} A DCF is only as good as its assumptions — the terminal value is usually most of the answer.</div>
        </>
      )}
    </div>
  );
}

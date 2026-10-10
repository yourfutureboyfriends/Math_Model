// Security function screens: ERN, ANR, HDS, DVD, OMON, RV, HP, BETA, DCF.
import { useMemo, useRef, useState } from 'react';
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
        <Stat label="Beat rate" value={data.beat_rate != null ? fmtPct(data.beat_rate, 0).replace('+', '') : '—'} sub={data.history.length ? `of the last ${data.history.length} reports` : 'No recent reports'} />
        <Stat label="Average surprise" value={data.avg_surprise_pct != null ? `${data.avg_surprise_pct > 0 ? '+' : ''}${data.avg_surprise_pct.toFixed(1)}%` : '—'}
          tone={data.avg_surprise_pct > 0 ? 'up' : data.avg_surprise_pct < 0 ? 'down' : null} />
        <Stat label="Last report" value={hist.length ? hist[hist.length - 1].date : '—'} sub={hist.length ? `EPS ${n2(hist[hist.length - 1].eps_reported)} vs ${n2(hist[hist.length - 1].eps_estimate)} est.` : ''} />
      </div>
      {data.note && <div className="text-2xs text-amber">{data.note}</div>}
      {hist.length > 0 && <Panel title="Reported EPS vs estimate — green = beat, red = miss (grey = estimate)">
        <Bars data={hist.map((h: any) => ({ label: h.date.slice(2, 7), a: h.eps_reported, b: h.eps_estimate }))} />
      </Panel>}
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
    const shown = strikes.slice(Math.max(0, i - range), i + range + 1);
    const above = shown.find((k) => k >= data.underlying);         // the spot line sits just above this strike
    return shown.map((k) => ({ k, c: data.calls.find((x: any) => x.strike === k), p: data.puts.find((x: any) => x.strike === k), atm: k === atm, spot: k === above && k !== shown[0] }));
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
        <Stat label="Days to expiry" value={data.days} sub={data.sessions != null ? `${+Number(data.sessions).toFixed(1)} trading sessions` : undefined} />
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
          <tbody>{rows.map(({ k, c, p, atm, spot }) => (
            <tr key={k} title={spot ? `Underlying ${fmtPrice(data.underlying)} lies between this strike and the one above` : undefined}
              className={cn('border-t', spot ? 'border-t-2 border-t-bloomberg/70' : 'border-border-subtle', atm && 'bg-surface-2/60')}>
              {cols.map(([key, l, d]) => <td key={`c${l}`} className={cn('text-right px-1.5 py-0.5', c?.itm && 'bg-blue/5')}>{cell(c, key, d)}</td>)}
              <td className="text-center px-2 font-semibold text-text-primary bg-surface-2">{n2(k)}</td>
              {cols.map(([key, l, d]) => <td key={`p${l}`} className={cn('text-right px-1.5 py-0.5', p?.itm && 'bg-blue/5')}>{cell(p, key, d)}</td>)}
            </tr>))}</tbody>
        </table></div>
        <div className="text-[10px] text-text-tertiary mt-2">Shaded = in the money. The orange line marks the underlying price. Θ is per trading day (time measured in trading sessions); Vega per 1 vol point. {data.source}</div>
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
// FCFF at WACC (Damodaran / McKinsey). Every assumption is editable; blank = default.
const DCF_FIELDS: [string, string, 'pct' | 'num' | 'int', string][] = [
  ['growth', 'Revenue growth, years 1–3', 'pct', 'Then fades to terminal growth. Default: analyst consensus (this year, then next year).'],
  ['target_margin', 'Target operating margin', 'pct', 'EBIT margin reached by the last year. Default: today’s (normalised); industry margin for loss-makers; mid-cycle for cyclicals at a peak.'],
  ['years', 'Projection years', 'int', 'Years before the terminal value (3–30).'],
  ['terminal_growth', 'Terminal growth', 'pct', 'Long-run growth. Default: the risk-free rate (Damodaran) — never above it.'],
  ['sales_to_capital', 'Sales-to-capital', 'num', 'Revenue added per unit of reinvestment. Default: firm and industry averaged.'],
  ['ronic', 'Return on new capital (terminal)', 'pct', 'Return on growth investment after year N. = WACC means growth adds no value.'],
  ['beta', 'Beta', 'num', 'Default: bottom-up — industry unlevered beta relevered at the firm’s debt/equity.'],
  ['erp', 'Equity risk premium', 'pct', 'Default: Damodaran’s latest implied ERP + the home country’s risk premium.'],
  ['discount', 'Override discount rate', 'pct', 'Leave blank to use the computed WACC.'],
];

const FIN_FIELDS: [string, string, 'pct' | 'num' | 'int', string][] = [
  ['roe', 'ROE now', 'pct', 'Return on equity today. Default: TTM net income ÷ book equity.'],
  ['terminal_roe', 'Stable ROE', 'pct', 'ROE reached by the last year and kept. Default: half of today’s excess over the cost of equity persists.'],
  ['payout', 'Payout ratio now', 'pct', 'Share of earnings paid out; converges to the payout stable growth needs.'],
  ['years', 'Projection years', 'int', 'Years before stable growth (3–30).'],
  ['terminal_growth', 'Stable growth', 'pct', 'Default: the risk-free rate (capped 1 point below the cost of equity).'],
  ['beta', 'Beta', 'num', 'Default: the industry’s average equity beta (Damodaran).'],
  ['erp', 'Equity risk premium', 'pct', 'Default: Damodaran’s latest implied ERP + country risk premium.'],
  ['discount', 'Override cost of equity', 'pct', 'Leave blank to use risk-free + beta × ERP.'],
];

// allowed ranges (in the units typed: % for pct fields) — mirror the API's limits
const DCF_LIMITS: Record<string, [number, number]> = {
  growth: [-50, 200], target_margin: [-100, 90], years: [3, 30], terminal_growth: [-5, 15], sales_to_capital: [0.05, 20],
  ronic: [0.1, 200], beta: [-1, 5], erp: [0, 15], discount: [0.1, 39.9], roe: [-50, 100], terminal_roe: [0.1, 100], payout: [0, 100],
};

export function DcfView({ symbol }: { symbol: string }) {
  const [form, setForm] = useState<Record<string, string>>({});
  const [leases, setLeases] = useState(false);
  const [midYear, setMidYear] = useState(true);
  const [formErr, setFormErr] = useState<string | null>(null);
  const modelRef = useRef<'fcff' | 'excess_return'>('fcff');
  const build = (): string | null => {
    const p = new URLSearchParams();
    const bad: string[] = [];
    if (modelRef.current === 'excess_return') p.set('model', 'excess_return');
    for (const [k, label, kind] of (modelRef.current === 'excess_return' ? FIN_FIELDS : DCF_FIELDS)) {
      const raw = form[k];
      if (raw === undefined || raw.trim() === '') continue;
      const n = Number(raw);
      const [lo, hi] = DCF_LIMITS[k];
      if (!Number.isFinite(n)) { bad.push(`${label}: not a number`); continue; }
      if (kind === 'int' && !Number.isInteger(n)) { bad.push(`${label}: whole number`); continue; }
      if (n < lo || n > hi) { bad.push(`${label}: ${lo}–${hi}${kind === 'pct' ? '%' : ''}`); continue; }
      p.set(k, String(kind === 'pct' ? n / 100 : n));
    }
    if (bad.length) { setFormErr(`Check: ${bad.join(' · ')}`); return null; }
    setFormErr(null);
    if (leases) p.set('include_leases', 'true');
    if (!midYear) p.set('mid_year', 'false');
    return `/api/v1/mkt/dcf/${enc(symbol)}${p.toString() ? `?${p}` : ''}`;
  };
  const [url, setUrlRaw] = useState(() => `/api/v1/mkt/dcf/${enc(symbol)}`);
  // Recalculate always refetches, even with unchanged inputs (e.g. after a failed request)
  const setUrl = (u: string) => setUrlRaw((prev) => (prev.split('&_=')[0].split('?_=')[0] === u ? `${u}${u.includes('?') ? '&' : '?'}_=${Date.now()}` : u));
  const { data: fresh, error, loading } = useJSON<any>(url);
  // keep the last good model on screen when a recalculation fails, so the inputs can be fixed
  const lastGood = useRef<any>(null);
  if (fresh) lastGood.current = fresh;
  const data = fresh ?? lastGood.current;
  if (loading && !data) return <Loading label="Building the valuation model…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  const isFin = data.model === 'excess_return';
  modelRef.current = isFin ? 'excess_return' : 'fcff';
  const inp = data.inputs, v = data.valuation, a = v.assumptions, w = v.wacc, sens = data.sensitivity;
  const FIELDS = isFin ? FIN_FIELDS : DCF_FIELDS;
  const ccy = inp.currency ?? '';                   // reporting currency (projection, bridge)
  const pccy = inp.price_currency ?? ccy;            // trading currency (value per share)
  const def: Record<string, number | null> = isFin
    ? { years: a.years, roe: a.roe_now, terminal_roe: a.roe_terminal, payout: a.payout_now, terminal_growth: a.terminal_growth, beta: a.beta, erp: a.erp, discount: null }
    : { growth: a.growth, target_margin: a.target_margin, years: a.years, terminal_growth: a.terminal_growth,
        sales_to_capital: a.sales_to_capital, ronic: a.ronic, beta: w.beta, erp: w.erp, discount: null };
  const shown = (k: string, kind: string) => def[k] == null ? 'computed' : kind === 'pct' ? (def[k]! * 100).toFixed(2) : kind === 'int' ? String(def[k]) : def[k]!.toFixed(2);
  const pctS = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);
  const formPanel = (
    <>
      {(formErr || error) && <div className="px-3 py-2 border border-red/60 bg-red/5 text-xs text-red">{formErr ?? `Couldn’t recalculate — ${(error ?? "").replace(/\.$/, "")}. Showing the last valid result.`}</div>}
      <Panel title="Assumptions — blank uses the default shown" right={loading ? <span className="text-[10px] text-text-tertiary">Recalculating…</span> : undefined}>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
          {FIELDS.map(([k, label, kind, hint]) => (
            <label key={k} className="text-[10px] uppercase tracking-wider text-text-tertiary" title={hint}>{label}
              <div className="flex items-center mt-0.5">
                <input type="number" step="any" min={DCF_LIMITS[k][0]} max={DCF_LIMITS[k][1]} placeholder={shown(k, kind)} value={form[k] ?? ''}
                  onChange={(e) => setForm({ ...form, [k]: e.target.value })} onKeyDown={(e) => { if (e.key === 'Enter') { const u = build(); if (u) setUrl(u); } }}
                  className="w-full bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary" />
                <span className="ml-1 text-text-tertiary normal-case w-3">{kind === 'pct' ? '%' : ''}</span></div>
              <span className="normal-case tracking-normal text-[10px] text-text-tertiary leading-tight block mt-0.5">{hint}</span>
            </label>))}
        </div>
        <div className="flex flex-wrap items-center gap-4 mt-3 text-2xs text-text-secondary">
          {!isFin && <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={leases} onChange={(e) => setLeases(e.target.checked)} />Treat operating leases as debt</label>}
          {!isFin && <label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={midYear} onChange={(e) => setMidYear(e.target.checked)} />Mid-year discounting</label>}
          <button onClick={() => { const u = build(); if (u) setUrl(u); }} className="px-4 py-1.5 text-xs bg-bloomberg text-text-inverse">Recalculate</button>
          {!isFin && <a href={url.replace(/^(\/api\/v1\/mkt\/dcf\/[^?]+)/, '$1/xlsx')} download
            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs border border-border hover:border-bloomberg hover:text-bloomberg"
            title="The model with live formulas — change any input in Excel and the value updates"><Download className="w-3.5 h-3.5" />Excel model</a>}
          <button onClick={() => { setForm({}); setLeases(false); setMidYear(true); setFormErr(null); setUrl(`/api/v1/mkt/dcf/${enc(symbol)}`); }} className="text-text-tertiary hover:text-text-primary">Reset to defaults</button>
        </div>
      </Panel>
    </>
  );
  if (isFin) return <FinancialValuation data={data} formPanel={formPanel} pctS={pctS} />;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Stat label="Intrinsic value / share" value={v.per_share != null ? fmtPrice(v.per_share) : '—'} sub={pccy} />
        <Stat label="vs price" value={v.upside != null ? fmtPct(v.upside, 1) : '—'} tone={v.upside != null ? (v.upside > 0 ? 'up' : 'down') : null} sub={v.price ? `price ${fmtPrice(v.price)}` : 'no exchange rate'} />
        <Stat label="Growth the price implies" value={data.market_implied_growth != null ? pctS(data.market_implied_growth)
          : data.market_implied_growth_bound === 'below' ? '< −60%' : data.market_implied_growth_bound === 'above' ? '> +150%' : '—'}
          sub={`years 1–3 revenue growth (model: ${pctS(a.growth)})`} />
        <Stat label="WACC" value={`${pctS(w.wacc, 2)} → ${pctS(a.discount_terminal, 2)}`} sub={`today → stable growth (β ${n2(w.beta)} → ${a.beta_terminal != null ? n2(a.beta_terminal) : '—'})`} />
        <Stat label="Terminal value share" value={pctS(v.terminal_share, 0)} sub={`exit ≈ ${v.implied_ev_ebit_exit ? v.implied_ev_ebit_exit.toFixed(1) : '—'}× EBIT`} />
      </div>
      {v.checks.length > 0 && (
        <div className="px-3 py-2 border border-amber/50 bg-amber/5 space-y-1">{v.checks.map((c: string) => <div key={c} className="text-2xs text-amber">• {c}</div>)}</div>
      )}
      {formPanel}
      <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-3">
        <Panel title={`Projection (${ccy}, millions) — free cash flow to the firm`}>
          <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary">{['Year', 'Growth', 'Revenue', 'EBIT margin', 'NOPAT', 'Reinvestment', 'FCFF', 'WACC', 'PV'].map((h) => <th key={h} className="text-right font-normal px-1.5 first:text-left">{h}</th>)}</tr></thead>
            <tbody>
              <tr className="border-t border-border-subtle text-text-tertiary"><td className="py-0.5">Now</td><td /><td className="text-right px-1.5">{(inp.revenue / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td><td className="text-right px-1.5">{pctS(a.margin_now)}</td><td colSpan={5} /></tr>
              {v.projection.map((r: any) => (
                <tr key={r.year} className="border-t border-border-subtle">
                  <td className="py-0.5">{r.year}</td><td className="text-right px-1.5">{pctS(r.growth)}</td>
                  <td className="text-right px-1.5">{(r.revenue / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td><td className="text-right px-1.5">{pctS(r.margin)}</td>
                  <td className="text-right px-1.5">{(r.nopat / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                  <td className="text-right px-1.5 text-text-secondary">{(-r.reinvestment / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                  <td className={cn('text-right px-1.5', r.fcff < 0 && 'text-red')}>{(r.fcff / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                  <td className="text-right px-1.5 text-text-tertiary">{pctS(r.discount_rate, 1)}</td>
                  <td className="text-right px-1.5 text-text-primary">{(r.pv / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td></tr>))}
              <tr className="border-t-2 border-border"><td colSpan={7} className="py-1 text-text-secondary font-sans">Terminal value (reinvests {pctS(v.terminal_reinvestment_rate, 0)} of NOPAT to grow {pctS(a.terminal_growth)} at {pctS(a.ronic)} return)</td>
                <td className="text-right px-1.5">{(v.terminal_value / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td className="text-right px-1.5 text-text-primary">{(v.pv_terminal / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td></tr>
            </tbody>
          </table></div>
        </Panel>
        <Panel title="From enterprise value to value per share">
          <table className="w-full text-xs"><tbody>
            {[['PV of explicit cash flows', v.pv_explicit], ['PV of terminal value', v.pv_terminal], ['= Enterprise value', v.enterprise_value],
              ['− Debt' + (a.include_leases ? ' (incl. leases)' : '') + (inp.captive_finance_receivables ? ' (industrial only)' : ''), (inp.debt ?? 0) + (a.include_leases ? inp.leases ?? 0 : 0)], ['+ Cash & short-term investments', inp.cash ?? 0],
              ['+ Stakes in other companies', inp.investments ?? 0],
              ['− Minority interest', inp.minority_interest ?? 0], ['= Equity value', v.equity_value]].map(([k, x]) => (
              <tr key={k as string} className={cn('border-t border-border-subtle', String(k).startsWith('=') && 'font-semibold text-text-primary')}>
                <td className="py-1 text-text-secondary">{k}</td><td className="text-right font-mono">{fmtBig(x as number)}</td></tr>))}
            <tr className="border-t-2 border-border font-semibold"><td className="py-1">÷ {fmtBig(inp.shares)} shares</td><td className="text-right font-mono text-bloomberg">{fmtPrice(v.per_share_reporting_ccy)} {ccy}</td></tr>
            {pccy !== ccy && v.per_share != null && <tr><td className="py-1 text-text-secondary">= per traded share, in {pccy}</td><td className="text-right font-mono text-bloomberg">{fmtPrice(v.per_share)} {pccy}</td></tr>}
          </tbody></table>
          {inp.captive_finance_receivables ? <div className="mt-2 text-[10px] text-text-tertiary">Captive finance arm carved out: {fmtBig(inp.captive_finance_receivables)} of loan book offsets its own debt (total debt {fmtBig(inp.debt_total)}).</div> : null}
          <div className="mt-3 text-[10px] text-text-tertiary space-y-0.5">
            <div>WACC = {pctS(w.weight_equity, 0)} × {pctS(w.cost_of_equity, 2)} (rf {pctS(w.risk_free, 2)} + β {n2(w.beta)} × ERP {pctS(w.erp, 1)}) + {pctS(w.weight_debt, 0)} × {pctS(w.cost_of_debt_after_tax, 2)}</div>
            <div>Risk-free: {inp.risk_free_source}.</div>
            <div>ERP: {inp.erp_source}{inp.country_risk_premium ? ` + ${pctS(inp.country_risk_premium, 2)} country risk (${inp.country}${inp.country_rating ? `, ${inp.country_rating}` : ''})` : ''}.</div>
            <div>Beta: {inp.beta_source}. Regression beta for comparison: {n2(inp.beta_regression)}.</div>
            <div>Stable growth: β moves to {a.beta_terminal != null ? n2(a.beta_terminal) : '—'} (bounded 0.8–1.2), so WACC goes {pctS(w.wacc, 2)} → {pctS(a.discount_terminal, 2)} over the fade years.</div>
            {inp.sales_to_capital_source && <div>Sales-to-capital: {inp.sales_to_capital_source}.</div>}
            {inp.target_margin_source && <div>Margin: {inp.target_margin_source}.</div>}
            <div>Tax {pctS(a.tax_now, 0)} today → {pctS(a.tax_terminal, 0)} marginal. Today’s ROIC {pctS(a.roic_now, 0)}. Growth default: {inp.growth_source}.</div>
            <div>Financials: {inp.source}{inp.as_of ? ` to ${inp.as_of}` : ''}. Debt: {inp.debt_source}.</div>
          </div>
        </Panel>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <SensGrid title="Value per share — WACC (rows) × terminal growth (columns)" rows={sens.discount_rates} cols={sens.terminal_growth} grid={sens.per_share} price={v.price} />
        <SensGrid title="Value per share — target margin (rows) × years 1–3 growth (columns)" rows={sens.target_margins} cols={sens.growth_rates} grid={sens.per_share_growth_margin} price={v.price} />
      </div>
      <div className="text-[10px] text-text-tertiary">{data.method} Green cells are above today’s price. A DCF is a structured way to state assumptions — the reverse DCF (growth the price implies) is often the more useful number.</div>
    </div>
  );
}

function FinancialValuation({ data, formPanel, pctS }: { data: any; formPanel: React.ReactNode; pctS: (x: number | null | undefined, d?: number) => string }) {
  const inp = data.inputs, v = data.valuation, a = v.assumptions, sens = data.sensitivity;
  const ccy = inp.currency ?? '', pccy = inp.price_currency ?? ccy;
  const m = (x: number) => (x / 1e6).toLocaleString(undefined, { maximumFractionDigits: 0 });
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Stat label="Intrinsic value / share" value={v.per_share != null ? fmtPrice(v.per_share) : '—'} sub={pccy} />
        <Stat label="vs price" value={v.upside != null ? fmtPct(v.upside, 1) : '—'} tone={v.upside != null ? (v.upside > 0 ? 'up' : 'down') : null} sub={v.price ? `price ${fmtPrice(v.price)}` : '—'} />
        <Stat label="ROE the price implies" value={data.market_implied_roe != null ? pctS(data.market_implied_roe) : '—'} sub={`sustained (model: ${pctS(a.roe_now)} → ${pctS(a.roe_terminal)})`} />
        <Stat label="Cost of equity" value={pctS(a.cost_of_equity, 2)} sub={`rf ${pctS(a.risk_free, 2)} + β ${a.beta?.toFixed(2)} × ${pctS(a.erp, 1)}`} />
        <Stat label="Justified price / book" value={v.price_to_book_implied != null ? `${v.price_to_book_implied.toFixed(2)}×` : '—'} sub="value ÷ book equity" />
      </div>
      {v.checks.length > 0 && (
        <div className="px-3 py-2 border border-amber/50 bg-amber/5 space-y-1">{v.checks.map((c: string) => <div key={c} className="text-2xs text-amber">• {c}</div>)}</div>
      )}
      {formPanel}
      <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-3">
        <Panel title={`Projection (${ccy}, millions) — excess returns`}>
          <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary">{['Year', 'ROE', 'Book value', 'Net income', 'Payout', 'Excess return', 'PV'].map((h) => <th key={h} className="text-right font-normal px-1.5 first:text-left">{h}</th>)}</tr></thead>
            <tbody>{v.projection.map((r: any) => (
              <tr key={r.year} className="border-t border-border-subtle">
                <td className="py-0.5">{r.year}</td><td className="text-right px-1.5">{pctS(r.roe)}</td><td className="text-right px-1.5">{m(r.book_value_start)}</td>
                <td className="text-right px-1.5">{m(r.net_income)}</td><td className="text-right px-1.5">{pctS(r.payout, 0)}</td>
                <td className={cn('text-right px-1.5', r.excess_return < 0 && 'text-red')}>{m(r.excess_return)}</td><td className="text-right px-1.5 text-text-primary">{m(r.pv)}</td></tr>))}
              <tr className="border-t-2 border-border"><td colSpan={5} className="py-1 text-text-secondary font-sans">Stable growth: {pctS(a.terminal_growth)} a year at ROE {pctS(a.roe_terminal)}, payout {pctS(a.payout_terminal, 0)}</td>
                <td className="text-right px-1.5">{m(v.terminal_value)}</td><td className="text-right px-1.5 text-text-primary">{m(v.pv_terminal)}</td></tr>
            </tbody></table></div>
        </Panel>
        <Panel title="From book value to value per share">
          <table className="w-full text-xs"><tbody>
            {[['Book equity today', v.book_value], ['+ PV of excess returns', v.pv_excess], ['+ PV of stable-growth excess returns', v.pv_terminal], ['= Equity value', v.equity_value]].map(([k, x]) => (
              <tr key={k as string} className={cn('border-t border-border-subtle', String(k).startsWith('=') && 'font-semibold text-text-primary')}>
                <td className="py-1 text-text-secondary">{k}</td><td className="text-right font-mono">{fmtBig(x as number)}</td></tr>))}
            <tr className="border-t-2 border-border font-semibold"><td className="py-1">÷ {fmtBig(inp.shares)} shares</td><td className="text-right font-mono text-bloomberg">{fmtPrice(v.per_share_reporting_ccy)} {ccy}</td></tr>
            {pccy !== ccy && v.per_share != null && <tr><td className="py-1 text-text-secondary">= per traded share, in {pccy}</td><td className="text-right font-mono text-bloomberg">{fmtPrice(v.per_share)} {pccy}</td></tr>}
          </tbody></table>
          <div className="mt-3 text-[10px] text-text-tertiary space-y-0.5">
            <div>Risk-free: {inp.risk_free_source}.</div>
            <div>ERP: {inp.erp_source}{inp.country_risk_premium ? ` + ${pctS(inp.country_risk_premium, 2)} country risk` : ''}. Beta: {inp.beta_source}.</div>
            <div>Financials: {inp.source}. Book equity and net income from the latest filings (Yahoo).</div>
          </div>
        </Panel>
      </div>
      <SensGrid title="Value per share — cost of equity (rows) × stable ROE (columns)" rows={sens.costs_of_equity} cols={sens.terminal_roes} grid={sens.per_share} price={v.price} />
      <div className="text-[10px] text-text-tertiary">{data.method}</div>
    </div>
  );
}

function SensGrid({ title, rows, cols, grid, price }: { title: string; rows: number[]; cols: number[]; grid: (number | null)[][]; price: number | null }) {
  return (
    <Panel title={title}>
      <table className="w-full text-2xs font-mono tabular-nums">
        <thead><tr className="text-text-tertiary"><th />{cols.map((c) => <th key={c} className="text-right font-normal">{(c * 100).toFixed(1)}%</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={r} className="border-t border-border-subtle"><td className="text-text-tertiary">{(r * 100).toFixed(1)}%</td>
            {grid[i].map((x, j) => (
              <td key={j} className={cn('text-right py-0.5', i === 2 && j === 2 && 'font-semibold underline', price && x != null && (x > price ? 'text-green' : 'text-red'))}>
                {x == null ? '—' : fmtPrice(x)}</td>))}</tr>))}</tbody>
      </table>
    </Panel>
  );
}

// ── HDS for ETFs and funds: what the fund owns ───────────────────────────────
export function FundHoldingsView({ symbol, onOpen }: { symbol: string; onOpen: (s: string) => void }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/fund/${enc(symbol)}`);
  if (loading && !data) return <Loading label="Loading fund holdings…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  const f = data.facts ?? {};
  const maxW = Math.max(...data.holdings.map((h: any) => h.weight ?? 0), 0.0001);
  const maxS = Math.max(...data.sectors.map((x: any) => x.weight ?? 0), 0.0001);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Stat label="Category" value={f.category ?? '—'} sub={f.family ?? ''} />
        <Stat label="Expense ratio" value={f.expense_ratio != null ? `${(f.expense_ratio * 100).toFixed(2)}%` : '—'} sub="a year" />
        <Stat label="Top 10 weight" value={`${(data.top_weight * 100).toFixed(1)}%`} sub="concentration" />
        <Stat label="Turnover" value={f.turnover != null ? `${(f.turnover * 100).toFixed(0)}%` : '—'} sub="of holdings a year" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Panel title="Top holdings">
          <table className="w-full text-xs"><tbody>
            {data.holdings.map((h: any, i: number) => (
              <tr key={h.symbol} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" onClick={() => onOpen(h.symbol)} title={`Open ${h.symbol}`}>
                <td className="py-1 w-6 text-text-tertiary">{i + 1}</td>
                <td className="py-1"><span className="text-text-primary">{h.name}</span> <span className="font-mono text-text-tertiary">{h.symbol}</span></td>
                <td className="w-32"><div className="h-1.5 bg-surface-3"><div className="h-full bg-bloomberg" style={{ width: `${((h.weight ?? 0) / maxW) * 100}%` }} /></div></td>
                <td className="text-right font-mono w-16">{h.weight != null ? `${(h.weight * 100).toFixed(2)}%` : '—'}</td></tr>))}
          </tbody></table>
        </Panel>
        <Panel title="Sector weights">
          <table className="w-full text-xs"><tbody>
            {data.sectors.map((x: any) => (
              <tr key={x.sector} className="border-t border-border-subtle">
                <td className="py-1 text-text-primary">{x.sector}</td>
                <td className="w-40"><div className="h-1.5 bg-surface-3"><div className="h-full bg-blue" style={{ width: `${(x.weight / maxS) * 100}%` }} /></div></td>
                <td className="text-right font-mono w-16">{(x.weight * 100).toFixed(1)}%</td></tr>))}
          </tbody></table>
          {Object.keys(data.assets).length > 0 && <div className="mt-3 text-[11px] text-text-secondary">Asset mix: {Object.entries<number>(data.assets).map(([k, v]) => `${k} ${(v * 100).toFixed(1)}%`).join(' · ')}</div>}
        </Panel>
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source}. Click a holding to open it.</div>
    </div>
  );
}

const KIND: Record<string, string> = { ETF: 'an ETF', Fund: 'a fund', Index: 'an index', FX: 'a currency pair', Future: 'a futures contract', Crypto: 'a crypto asset' };

/** Shown instead of an error when a company-only function is opened on something else. */
export function NotApplicable({ fn, name, q, onGo }: { fn: string; name: string; q: any; onGo: (fn: string, s?: string) => void }) {
  const alts = q.type === 'ETF' || q.type === 'Fund' ? ['DES', 'HDS', 'GP', 'DVD', 'OMON', 'HP'] : q.type === 'Index' ? ['DES', 'GP', 'HP', 'BETA', 'CN'] : ['DES', 'GP', 'HP', 'CN'];
  return (
    <div className="border border-border bg-surface-1 p-4 space-y-3">
      <div className="text-sm text-text-primary"><span className="font-mono text-bloomberg mr-2">{fn}</span>{name} applies to companies — {q.symbol} is {KIND[q.type] ?? q.type?.toLowerCase() ?? 'not a company'}.</div>
      <div className="flex flex-wrap gap-2">{alts.map((a) => (
        <button key={a} onClick={() => onGo(a, q.symbol)} className="px-2.5 py-1 text-xs border border-border hover:border-bloomberg hover:text-bloomberg"><span className="font-mono font-semibold">{a}</span></button>))}</div>
    </div>
  );
}

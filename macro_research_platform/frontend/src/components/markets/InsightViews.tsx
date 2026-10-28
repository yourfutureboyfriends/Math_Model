// Market internals: VOL (volatility complex), BRDT (S&P 500 breadth), IMPM (earnings implied moves),
// UOA (unusual options activity), RISK (risk-on / risk-off regime).
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, fmtBig, Loading, Panel, Spark, useJSON } from './shared';
import { signedPct as pct } from '@/lib/format';

const tone = (v: number | null | undefined) => (v == null ? 'text-text-tertiary' : v >= 0 ? 'text-green' : 'text-red');

function Frame<T>({ url, label, refresh, children }: { url: string; label: string; refresh?: number; children: (d: T) => React.ReactNode }) {
  const { data, error, loading } = useJSON<T>(url, refresh);
  if (loading && !data) return <Loading label={label} />;
  if (error && !data) return <ErrorBox msg={error} />;
  return data ? <>{children(data)}</> : null;
}

function Kpi({ label, value, sub, tone: t }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: string }) {
  return (
    <div className="border border-border bg-surface-1 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className={cn('font-mono text-text-primary', t)}>{value}</div>
      {sub != null && <div className="text-[10px] text-text-tertiary">{sub}</div>}
    </div>
  );
}

/** A percentile marker on a 0–100 track. */
function PctBar({ p }: { p: number | null | undefined }) {
  if (p == null) return <span className="text-text-tertiary">—</span>;
  return (
    <div className="relative h-1.5 w-24 rounded-full bg-surface-3" title={`${Math.round(p * 100)}th percentile of 3 years`}>
      <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-green/40 via-amber/40 to-red/50" style={{ width: '100%' }} />
      <div className="absolute -top-[3px] w-1.5 h-3 rounded-sm bg-text-primary shadow" style={{ left: `calc(${p * 100}% - 3px)` }} />
    </div>
  );
}

// ── VOL ─────────────────────────────────────────────────────────────────────
export function VolView({ onOpen }: { onOpen: (s: string) => void }) {
  return (
    <Frame<any> url="/api/v1/mkt/ins/vol" label="Loading the volatility complex…" refresh={900_000}>{(d) => {
      const terms = [['Now', d.term.now, 'rgb(var(--c-bloomberg))'], ['1 week ago', d.term.week_ago, 'rgb(var(--c-blue))'], ['1 month ago', d.term.month_ago, 'rgb(var(--c-text-tertiary))']] as const;
      const all = terms.flatMap(([, pts]) => pts.map((p: any) => p.value));
      const lo = Math.floor(Math.min(...all) - 1), hi = Math.ceil(Math.max(...all) + 1);
      const W = 520, H = 220, L = 34, B = 24, xs = [9, 30, 93, 183, 365];
      const sx = (days: number) => L + (Math.log(days / 9) / Math.log(365 / 9)) * (W - L - 12);
      const sy = (v: number) => 10 + (1 - (v - lo) / (hi - lo)) * (H - 10 - B);
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2">
            <Kpi label="VIX" value={d.vix} sub={d.regime} />
            <Kpi label="VIX / VIX3M" value={d.ratio_vix_vix3m.toFixed(3)} sub={`${Math.round((d.ratio_pct_3y ?? 0) * 100)}th pct of 3 years`} tone={d.ratio_vix_vix3m > 1 ? 'text-red' : undefined} />
            <Kpi label="Realised vol (21d)" value={`${d.realised[21]}%`} sub={`10d ${d.realised[10]}% · 63d ${d.realised[63]}%`} />
            <Kpi label="Variance premium" value={`${d.variance_premium > 0 ? '+' : ''}${d.variance_premium}`} sub="VIX − 21-day realised" tone={d.variance_premium < 0 ? 'text-red' : 'text-green'} />
            {d.indices.filter((i: any) => ['^VVIX', '^SKEW', '^MOVE'].includes(i.symbol)).map((i: any) => (
              <Kpi key={i.symbol} label={i.name} value={i.last} sub={`${Math.round((i.pct_3y ?? 0) * 100)}th pct · 1W ${i.chg_1w > 0 ? '+' : ''}${i.chg_1w}`} />))}
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,560px)_minmax(0,1fr)] gap-3">
            <Panel title="VIX term structure">
              <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[600px] mx-auto block" role="img" aria-label="VIX term structure">
                {Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4).map((v) => <g key={v}>
                  <line x1={L} x2={W - 12} y1={sy(v)} y2={sy(v)} stroke="rgb(var(--c-border))" strokeOpacity={0.6} strokeDasharray="2 4" />
                  <text x={L - 6} y={sy(v) + 3} fontSize={10} textAnchor="end" fill="rgb(var(--c-text-tertiary))" className="font-mono">{v.toFixed(0)}</text></g>)}
                {['9D', '1M', '3M', '6M', '1Y'].map((t, i) => <text key={t} x={sx(xs[i])} y={H - 6} fontSize={10} textAnchor="middle" fill="rgb(var(--c-text-tertiary))" className="font-mono">{t}</text>)}
                {[...terms].reverse().map(([n, pts, col]) => <g key={n}>
                  <polyline points={pts.map((p: any) => `${sx(p.days)},${sy(p.value)}`).join(' ')} fill="none" stroke={col} strokeWidth={n === 'Now' ? 2.4 : 1.4} strokeDasharray={n === 'Now' ? undefined : '4 3'} strokeLinejoin="round" />
                  {pts.map((p: any) => <circle key={p.tenor} cx={sx(p.days)} cy={sy(p.value)} r={n === 'Now' ? 3.5 : 2.2} fill={col}><title>{`${n} ${p.tenor}: ${p.value}`}</title></circle>)}</g>)}
              </svg>
              <div className="flex gap-3 text-[10px] text-text-secondary">{terms.map(([n, , c]) => <span key={n} className="inline-flex items-center gap-1"><span className="w-3 h-0.5" style={{ background: c }} />{n}</span>)}</div>
            </Panel>
            <Panel title="VIX vs 3-month VIX and realised volatility">
              <LineChart rows={d.history} x="date" height={250} fmt={(v) => v.toFixed(1)} defaultRange="1y"
                lines={[{ key: 'vix', label: 'VIX', color: 'rgb(var(--c-bloomberg))' }, { key: 'vix3m', label: 'VIX3M', color: 'rgb(var(--c-blue))' }, { key: 'rv21', label: 'S&P 500 realised (21d)', color: 'rgb(var(--c-text-tertiary))' }]} />
            </Panel>
          </div>
          <Panel title="Volatility indices">
            <table className="w-full text-[11px] font-mono [&_th]:px-1.5 [&_td]:px-1.5">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Index</th><th className="text-right font-normal">Last</th><th className="text-right font-normal">1D</th>
                <th className="text-right font-normal">1W</th><th className="font-normal">3-year percentile</th><th className="font-normal">3 months</th></tr></thead>
              <tbody>{d.indices.map((i: any) => (
                <tr key={i.symbol} className="border-t border-border-subtle cursor-pointer" onClick={() => onOpen(i.symbol)}>
                  <td className="py-1 font-sans text-text-primary">{i.name} <span className="font-mono text-text-tertiary">{i.symbol}</span></td>
                  <td className="text-right text-text-primary">{i.last}</td><td className={cn('text-right', tone(-(i.chg_1d ?? 0)))}>{i.chg_1d > 0 ? '+' : ''}{i.chg_1d}</td>
                  <td className={cn('text-right', tone(-(i.chg_1w ?? 0)))}>{i.chg_1w > 0 ? '+' : ''}{i.chg_1w}</td>
                  <td className="px-3"><PctBar p={i.pct_3y} /></td><td><Spark values={i.spark} w={90} h={18} /></td></tr>))}</tbody>
            </table>
            <div className="text-[10px] text-text-tertiary mt-1">{d.note} {d.source}.</div>
          </Panel>
        </div>);
    }}</Frame>
  );
}

// ── BRDT ────────────────────────────────────────────────────────────────────
export function BreadthView() {
  return (
    <Frame<any> url="/api/v1/mkt/ins/breadth" label="Computing S&P 500 breadth (first load ~20 s)…">{(d) => {
      const l = d.latest;
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2">
            <Kpi label="Above 50-day" value={`${l.above50.toFixed(0)}%`} sub={`${Math.round((d.pct_3y.above50 ?? 0) * 100)}th pct of the period`} />
            <Kpi label="Above 200-day" value={`${l.above200.toFixed(0)}%`} sub={`${Math.round((d.pct_3y.above200 ?? 0) * 100)}th pct of the period`} />
            <Kpi label="Advancers / decliners" value={`${l.adv} / ${l.dec}`} sub={`of ${d.members} members, last session`} tone={l.adv >= l.dec ? 'text-green' : 'text-red'} />
            <Kpi label="New 52-week highs" value={l.new_highs} tone="text-green" />
            <Kpi label="New 52-week lows" value={l.new_lows} tone="text-red" />
            <Kpi label="McClellan oscillator" value={`${l.mcclellan > 0 ? '+' : ''}${l.mcclellan.toFixed(0)}`} sub={l.mcclellan > 50 ? 'overbought' : l.mcclellan < -50 ? 'oversold' : 'neutral'} />
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <Panel title="Participation — share of S&P 500 members above their moving averages">
              <LineChart rows={d.rows} x="date" height={240} fmt={(v) => `${v.toFixed(0)}%`} refs={[{ value: 50, label: '50%' }]}
                lines={[{ key: 'above50', label: 'Above 50-day', color: 'rgb(var(--c-bloomberg))' }, { key: 'above200', label: 'Above 200-day', color: 'rgb(var(--c-blue))' }]} />
            </Panel>
            <Panel title="Advance/decline line and McClellan oscillator">
              <LineChart rows={d.rows} x="date" height={120} fmt={(v) => v.toFixed(0)} lines={[{ key: 'ad_line', label: 'Cumulative A/D line', color: 'rgb(var(--c-green))' }]} />
              <LineChart rows={d.rows} x="date" height={110} fmt={(v) => v.toFixed(0)} baseline={0} controls={false} lines={[{ key: 'mcclellan', label: 'McClellan oscillator', color: 'rgb(var(--c-amber))' }]} />
            </Panel>
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <Panel title="New 52-week highs and lows">
              <LineChart rows={d.rows} x="date" height={200} fmt={(v) => v.toFixed(0)} lines={[{ key: 'new_highs', label: 'New highs', color: 'rgb(var(--c-green))' }, { key: 'new_lows', label: 'New lows', color: 'rgb(var(--c-red))' }]} />
            </Panel>
            <Panel title="By sector">
              <table className="w-full text-[11px] font-mono [&_th]:px-1.5 [&_td]:px-1.5">
                <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Sector</th><th className="text-right font-normal">Members</th><th className="font-normal">Above 50-day</th>
                  <th className="text-right font-normal">Above 200d</th><th className="text-right font-normal">Highs / lows</th><th className="text-right font-normal">Median 1M</th></tr></thead>
                <tbody>{d.sectors.map((s: any) => (
                  <tr key={s.sector} className="border-t border-border-subtle"><td className="py-1 font-sans text-text-primary">{s.sector}</td><td className="text-right text-text-tertiary">{s.members}</td>
                    <td className="px-2"><div className="flex items-center gap-2"><div className="flex-1 h-1.5 rounded-full bg-surface-3 overflow-hidden"><div className={cn('h-full rounded-full', s.above50 >= 50 ? 'bg-green/80' : 'bg-red/70')} style={{ width: `${s.above50}%` }} /></div><span className="w-9 text-right">{s.above50.toFixed(0)}%</span></div></td>
                    <td className="text-right">{s.above200.toFixed(0)}%</td><td className="text-right"><span className="text-green">{s.new_highs}</span> / <span className="text-red">{s.new_lows}</span></td>
                    <td className={cn('text-right', tone(s.median_1m))}>{pct(s.median_1m)}</td></tr>))}</tbody>
              </table>
            </Panel>
          </div>
          <div className="text-[10px] text-text-tertiary">{d.note} {d.source}.</div>
        </div>);
    }}</Frame>
  );
}

// ── IMPM ────────────────────────────────────────────────────────────────────
export function ImpmView({ onOpen }: { onOpen: (s: string) => void }) {
  const [sort, setSort] = useState<'date' | 'implied_move' | 'ratio' | 'market_cap'>('date');
  return (
    <Frame<any> url="/api/v1/mkt/ins/impm" label="Pricing earnings straddles (first load ~15 s)…">{(d) => {
      const rows = [...d.rows].sort((a: any, b: any) => (sort === 'date' ? a.date.localeCompare(b.date) : (b[sort] ?? -1) - (a[sort] ?? -1)));
      const maxMove = Math.max(0.01, ...d.rows.map((r: any) => Math.max(r.implied_move, r.avg_abs_move ?? 0)));
      const th = (k: typeof sort, l: string, cls = 'text-right') => <th onClick={() => setSort(k)} className={cn('font-normal cursor-pointer', cls, sort === k && 'text-bloomberg')}>{l}</th>;
      return (
        <Panel title="Earnings in the next 10 days — what options price vs what the stock usually does">
          <table className="w-full text-[11px] font-mono [&_th]:px-1.5 [&_td]:px-1.5">
            <thead><tr className="text-text-tertiary">{th('date', 'Date', 'text-left')}<th className="text-left font-normal">Company</th><th className="text-left font-normal">When</th>
              {th('market_cap', 'Mkt cap')}{th('implied_move', 'Implied ±')}<th className="text-right font-normal">Avg actual ±</th><th className="font-normal w-56">Implied (bar) vs typical (tick)</th>{th('ratio', 'Ratio')}<th className="font-normal">Last 8 reactions</th></tr></thead>
            <tbody>{rows.map((r: any) => (
              <tr key={r.symbol} className="border-t border-border-subtle cursor-pointer" onClick={() => onOpen(r.symbol)}>
                <td className="py-1 text-text-secondary">{r.date.slice(5)}</td>
                <td className="font-sans"><span className="font-mono text-bloomberg mr-1">{r.symbol}</span><span className="text-text-secondary">{r.company}</span></td>
                <td className="font-sans text-text-tertiary">{r.timing ?? ''}</td><td className="text-right text-text-tertiary">{fmtBig(r.market_cap)}</td>
                <td className="text-right text-text-primary">±{(r.implied_move * 100).toFixed(1)}%</td>
                <td className="text-right text-text-secondary">{r.avg_abs_move != null ? `±${(r.avg_abs_move * 100).toFixed(1)}%` : '—'}</td>
                <td className="px-2"><div className="relative h-2 rounded-full bg-surface-3">
                  <div className="absolute inset-y-0 left-0 rounded-full bg-bloomberg/70" style={{ width: `${(r.implied_move / maxMove) * 100}%` }} />
                  {r.avg_abs_move != null && <div className="absolute -top-1 w-0.5 h-4 bg-text-primary" style={{ left: `${(r.avg_abs_move / maxMove) * 100}%` }} />}</div></td>
                <td className={cn('text-right', r.ratio >= 1.3 ? 'text-red' : r.ratio <= 0.8 ? 'text-green' : 'text-text-secondary')}>{r.ratio != null ? `${r.ratio.toFixed(2)}×` : '—'}</td>
                <td className="pl-2"><span className="inline-flex gap-0.5 items-end h-4">{(r.moves ?? []).slice().reverse().map((m: number, i: number) => (
                  <span key={i} title={pct(m)} className={cn('w-1.5 rounded-sm', m >= 0 ? 'bg-green/80' : 'bg-red/80')} style={{ height: `${Math.min(100, 15 + (Math.abs(m) / maxMove) * 85)}%` }} />))}</span></td></tr>))}</tbody>
          </table>
          <div className="text-[10px] text-text-tertiary mt-2">{d.note} {d.source}.</div>
        </Panel>);
    }}</Frame>
  );
}

// ── UOA ─────────────────────────────────────────────────────────────────────
export function UoaView({ onOpen }: { onOpen: (s: string) => void }) {
  const [kind, setKind] = useState<'all' | 'call' | 'put'>('all');
  return (
    <Frame<any> url="/api/v1/mkt/ins/uoa" label="Scanning option chains for unusual activity…" refresh={900_000}>{(d) => {
      const hits = d.hits.filter((h: any) => kind === 'all' || h.kind === kind);
      const maxPrem = Math.max(1, ...d.hits.map((h: any) => h.premium));
      return (
        <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_420px] gap-3">
          <Panel title={`Unusual contracts — ${d.hits.length} found`} right={<span className="flex gap-1">{(['all', 'call', 'put'] as const).map((k) => (
            <button key={k} onClick={() => setKind(k)} className={cn('px-2 py-0.5 border text-[10px] capitalize', kind === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{k === 'all' ? 'All' : `${k}s`}</button>))}</span>}>
            <div className="max-h-[640px] overflow-y-auto">
              <table className="w-full text-[11px] font-mono [&_th]:px-1.5 [&_td]:px-1.5">
                <thead className="sticky top-0"><tr className="text-text-tertiary"><th className="text-left font-normal">Contract</th><th className="text-right font-normal">Volume</th>
                  <th className="text-right font-normal">Open int.</th><th className="text-right font-normal">Vol/OI</th><th className="text-right font-normal">IV</th><th className="text-right font-normal">Moneyness</th><th className="font-normal w-40">Premium</th></tr></thead>
                <tbody>{hits.map((h: any, i: number) => (
                  <tr key={i} className="border-t border-border-subtle cursor-pointer" onClick={() => onOpen(h.symbol)}>
                    <td className="py-1"><span className="text-bloomberg">{h.symbol}</span> <span className="text-text-secondary">{h.expiry.slice(5)}</span> <span className="text-text-primary">{h.strike}</span>{' '}
                      <span className={cn('px-1 rounded text-[9px] uppercase', h.kind === 'call' ? 'bg-green/15 text-green' : 'bg-red/15 text-red')}>{h.kind}</span></td>
                    <td className="text-right text-text-primary">{h.volume.toLocaleString()}</td><td className="text-right text-text-tertiary">{h.open_interest.toLocaleString()}</td>
                    <td className="text-right text-amber">{h.vol_oi != null ? `${h.vol_oi}×` : 'new'}</td><td className="text-right">{(h.iv * 100).toFixed(0)}%</td>
                    <td className={cn('text-right', h.moneyness == null ? '' : (h.kind === 'call' ? h.moneyness > 0 : h.moneyness < 0) ? 'text-text-secondary' : 'text-text-tertiary')}>{pct(h.moneyness)}</td>
                    <td className="px-2"><div className="flex items-center gap-2"><div className="flex-1 h-1.5 rounded-full bg-surface-3 overflow-hidden"><div className={cn('h-full rounded-full', h.kind === 'call' ? 'bg-green/70' : 'bg-red/70')} style={{ width: `${Math.sqrt(h.premium / maxPrem) * 100}%` }} /></div>
                      <span className="w-14 text-right">${fmtBig(h.premium)}</span></div></td></tr>))}</tbody>
              </table>
            </div>
            <div className="text-[10px] text-text-tertiary mt-1">{d.note} {d.source}.</div>
          </Panel>
          <Panel title="Options volume by name — premium and put/call">
            <div className="max-h-[640px] overflow-y-auto">
              <table className="w-full text-[11px] font-mono [&_th]:px-1.5 [&_td]:px-1.5">
                <thead className="sticky top-0"><tr className="text-text-tertiary"><th className="text-left font-normal">Name</th><th className="font-normal">Calls vs puts (premium)</th><th className="text-right font-normal">P/C vol</th><th className="text-right font-normal">Unusual</th></tr></thead>
                <tbody>{d.tickers.map((t: any) => {
                  const tot = (t.call_premium + t.put_premium) || 1;
                  return (
                    <tr key={t.symbol} className="border-t border-border-subtle cursor-pointer" onClick={() => onOpen(t.symbol)}>
                      <td className="py-1 text-bloomberg">{t.symbol}</td>
                      <td className="px-2"><div className="flex h-1.5 rounded-full overflow-hidden bg-surface-3" title={`calls $${fmtBig(t.call_premium)} · puts $${fmtBig(t.put_premium)}`}>
                        <div className="bg-green/75" style={{ width: `${(t.call_premium / tot) * 100}%` }} /><div className="bg-red/75" style={{ width: `${(t.put_premium / tot) * 100}%` }} /></div>
                        <div className="text-[9px] text-text-tertiary">${fmtBig(t.call_premium + t.put_premium)}</div></td>
                      <td className={cn('text-right', (t.put_call ?? 0) > 1 ? 'text-red' : 'text-green')}>{t.put_call ?? '—'}</td>
                      <td className="text-right text-amber">{t.unusual || ''}</td></tr>);
                })}</tbody>
              </table>
            </div>
          </Panel>
        </div>);
    }}</Frame>
  );
}

// ── RISK ────────────────────────────────────────────────────────────────────
export function RiskView() {
  return (
    <Frame<any> url="/api/v1/mkt/ins/risk" label="Reading the regime…">{(d) => {
      const s = d.score, ang = Math.PI * (1 - (Math.max(-2, Math.min(2, s)) + 2) / 4);
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)] gap-3">
            <Panel title="Regime">
              <div className="flex flex-col items-center">
                <svg viewBox="0 0 220 130" className="w-64" role="img" aria-label={`Risk regime ${d.regime}`}>
                  <defs><linearGradient id="rg" x1="0" x2="1"><stop offset="0%" stopColor="rgb(var(--c-red))" /><stop offset="50%" stopColor="rgb(var(--c-amber))" /><stop offset="100%" stopColor="rgb(var(--c-green))" /></linearGradient></defs>
                  <path d="M 20 115 A 90 90 0 0 1 200 115" stroke="url(#rg)" strokeWidth="14" fill="none" strokeLinecap="round" opacity="0.85" />
                  <line x1="110" y1="115" x2={110 + 72 * Math.cos(ang)} y2={115 - 72 * Math.sin(ang)} stroke="rgb(var(--c-text-primary))" strokeWidth="3" strokeLinecap="round" />
                  <circle cx="110" cy="115" r="6" fill="rgb(var(--c-text-primary))" />
                  <text x="20" y="128" fontSize="9" fill="rgb(var(--c-text-tertiary))">Risk-off</text><text x="200" y="128" fontSize="9" textAnchor="end" fill="rgb(var(--c-text-tertiary))">Risk-on</text>
                </svg>
                <div className={cn('text-xl font-semibold', s > 0.5 ? 'text-green' : s < -0.5 ? 'text-red' : 'text-amber')}>{d.regime}</div>
                <div className="text-[11px] text-text-tertiary font-mono">score {s > 0 ? '+' : ''}{s} · as of {d.as_of}</div>
                <div className="mt-3 w-full border-t border-border-subtle pt-2 text-center">
                  <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Recession probability, next 12 months</div>
                  <div className={cn('text-2xl font-mono font-semibold', d.recession_prob_12m >= 0.3 ? 'text-red' : d.recession_prob_12m >= 0.15 ? 'text-amber' : 'text-green')}>{(d.recession_prob_12m * 100).toFixed(1)}%</div>
                  <div className="text-[10px] text-text-tertiary">NY Fed model · 10y − 3m spread {d.curve_3m10y_avg > 0 ? '+' : ''}{d.curve_3m10y_avg}pp</div>
                </div>
              </div>
            </Panel>
            <Panel title="Regime score — 5 years (above 0 = risk-on)">
              <LineChart rows={d.history} x="date" height={280} fmt={(v) => v.toFixed(2)} baseline={0} lines={[{ key: 'score', label: 'Risk score', color: 'rgb(var(--c-bloomberg))' }]} />
            </Panel>
          </div>
          <Panel title="Inputs — each as a z-score against 3 years, signed so positive = risk-on">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">{d.components.map((c: any) => (
              <div key={c.key} className="flex items-center gap-3 text-[11px] py-1 border-b border-border-subtle">
                <span className="w-56 text-text-primary">{c.name}</span>
                <span className="w-20 text-right font-mono text-text-secondary">{c.value}{c.unit}</span>
                <span className="flex-1 relative h-2 rounded-full bg-surface-3">
                  <span className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
                  <span className={cn('absolute inset-y-0 rounded-full', (c.z ?? 0) >= 0 ? 'bg-green/75' : 'bg-red/75')}
                    style={(c.z ?? 0) >= 0 ? { left: '50%', width: `${Math.min(50, Math.abs(c.z ?? 0) * 16.6)}%` } : { right: '50%', width: `${Math.min(50, Math.abs(c.z ?? 0) * 16.6)}%` }} /></span>
                <span className={cn('w-12 text-right font-mono', tone(c.z))}>{c.z != null ? `${c.z > 0 ? '+' : ''}${c.z}` : '—'}</span>
              </div>))}</div>
            <div className="text-[10px] text-text-tertiary mt-2">{d.note} {d.source}.</div>
          </Panel>
        </div>);
    }}</Frame>
  );
}


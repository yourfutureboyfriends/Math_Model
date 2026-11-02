// Data once listed as paid-only, from free public sources (backend: api/marketdata/bbgfree.py):
//   SWAP swap curves · CDSX credit indices · CDSA single-name CDS activity · EXTH extended-hours movers · TRAN call transcripts
import { Fragment, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, Loading, Panel, useJSON } from './shared';
import { Chip, pct, sign, Source, Tile } from './StandardViews';
import { useStickyState } from '@/lib/stickyState';

const big = (v: number | null | undefined) => (v == null ? '—' : v >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(0)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : v.toFixed(0));
const bp = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(d)}`);
const COLORS = ['rgb(var(--c-bloomberg))', 'rgb(var(--c-blue))', 'rgb(var(--c-green))', 'rgb(var(--c-red))', 'rgb(var(--c-text-secondary))', 'rgb(var(--c-text-tertiary))'];

// ── SWAP ─────────────────────────────────────────────────────────────────────
export function SwapView() {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/swap?days=10', 3 * 3_600_000);
  const [code, setCode] = useStickyState('swap.code', 'USD');
  if (loading && !d) return <Loading label="Reading the day's swap trades from DTCC…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const c = d.curves.find((x: any) => x.code === code) ?? d.curves[0];
  const tenors: number[] = Array.from(new Set(d.curves.flatMap((x: any) => x.points.map((p: any) => p.tenor)))).sort((a: any, b: any) => a - b) as number[];
  const shown = tenors.filter((t) => [1, 2, 3, 5, 7, 10, 15, 20, 30].includes(t));
  const at = (x: any, t: number) => x.points.find((p: any) => p.tenor === t);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {['USD', 'EUR', 'GBP', 'JPY'].map((k) => { const x = d.curves.find((y: any) => y.code === k); const p = x && at(x, 10);
          return <Tile key={k} label={`${x?.name ?? k} 10-year`} value={p ? `${p.rate.toFixed(3)}%` : '—'} sub={p?.change_bp != null ? <span className={sign(p.change_bp)}>{bp(p.change_bp)} bp on the day</span> : `${p?.trades ?? 0} trades`} />; })}
      </div>
      <Panel title={`Par swap rates — trades reported on ${d.date}`} right={<span className="text-[11px] text-text-tertiary">daily change in bp below</span>}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Curve</th>{shown.map((t) => <th key={t} className="text-right font-normal px-1">{t}Y</th>)}</tr></thead>
          <tbody>{d.curves.map((x: any) => (
            <tr key={x.code} onClick={() => setCode(x.code)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-2 align-top', x.code === c.code && 'bg-surface-2')}>
              <td className="py-1 font-sans text-text-primary whitespace-nowrap">{x.name}</td>
              {shown.map((t) => { const p = at(x, t);
                return <td key={t} className="text-right px-1" title={p ? `${p.trades} trades · range ${p.low.toFixed(3)}–${p.high.toFixed(3)}%` : 'no spot-starting trades at this maturity'}>
                  {p ? p.rate.toFixed(3) : <span className="text-text-tertiary">—</span>}
                  {p?.change_bp != null && <span className={cn('block text-[9px]', sign(p.change_bp))}>{bp(p.change_bp)}</span>}</td>; })}
            </tr>))}</tbody>
        </table></div>
      </Panel>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title={`${c.name}: curve`}>
          <div className="mkt-chart-surface"><LineChart rows={c.points.map((p: any) => ({ t: `${p.tenor}Y`, rate: p.rate }))} x="t" height={230} controls={false}
            fmt={(v) => `${v.toFixed(3)}%`} axisFmt={(v) => `${v.toFixed(2)}%`} lines={[{ key: 'rate', label: 'Par swap rate', color: COLORS[0] }]} /></div>
        </Panel>
        <Panel title={`${c.name}: 2, 5, 10 and 30 years over recent sessions`}>
          <div className="mkt-chart-surface"><LineChart rows={c.history} x="date" height={230} controls={false} fmt={(v) => `${v.toFixed(3)}%`} axisFmt={(v) => `${v.toFixed(2)}%`}
            lines={[{ key: 'y2', label: '2Y', color: COLORS[0] }, { key: 'y5', label: '5Y', color: COLORS[1] }, { key: 'y10', label: '10Y', color: COLORS[2] }, { key: 'y30', label: '30Y', color: COLORS[4] }]} /></div>
        </Panel>
      </div>
      {d.us_swap_spreads.length > 0 && (
        <Panel title="US swap spreads (SOFR swap minus Treasury)">
          <table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Tenor</th><th className="text-right font-normal">SOFR swap</th><th className="text-right font-normal">Treasury</th><th className="text-right font-normal">Spread (bp)</th></tr></thead>
            <tbody>{d.us_swap_spreads.map((s: any) => (
              <tr key={s.tenor} className="border-t border-border-subtle"><td className="py-1">{s.tenor}Y</td><td className="text-right">{s.swap.toFixed(3)}%</td><td className="text-right">{s.treasury.toFixed(3)}%</td>
                <td className={cn('text-right', sign(s.spread_bp))}>{bp(s.spread_bp)}</td></tr>))}</tbody>
          </table>
        </Panel>
      )}
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── CDSX ─────────────────────────────────────────────────────────────────────
export function CdsxView() {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/cdsx?days=22', 3 * 3_600_000);
  const [sel, setSel] = useStickyState('cdsx.index', 'CDX.NA.IG');
  if (loading && !d) return <Loading label="Reading credit index trades from DTCC…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const row = d.rows.find((r: any) => r.index === sel) ?? d.rows[0];
  const lvl = (r: any) => (r.quote === 'price' ? r.level.toFixed(2) : `${r.level.toFixed(1)} bp`);
  const chg = (r: any, v: number | null) => (v == null ? '—' : r.quote === 'price' ? `${v > 0 ? '+' : ''}${v.toFixed(2)}` : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
  // wider credit is red: a higher spread, or a lower price
  const tone = (r: any, v: number | null) => (v == null || Math.abs(v) < 1e-9 ? '' : (r.quote === 'price' ? -v : v) > 0 ? 'text-red' : 'text-green');
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {d.rows.slice(0, 4).map((r: any) => <Tile key={r.index} label={r.name} value={lvl(r)} sub={<span className={tone(r, r.change_1d)}>{chg(r, r.change_1d)} on the day</span>} />)}
      </div>
      <Panel title={`Credit default swap indices — ${d.date}`}>
        <table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Index</th><th className="text-left font-normal">Maturity</th><th className="text-right font-normal">Level</th>
            <th className="text-right font-normal">Spread equiv.</th><th className="text-right font-normal">1 day</th><th className="text-right font-normal">Period</th><th className="text-right font-normal">Trades</th><th className="text-right font-normal">Notional</th></tr></thead>
          <tbody>{d.rows.map((r: any) => (
            <tr key={r.index} onClick={() => setSel(r.index)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-2', r.index === row.index && 'bg-surface-2')}>
              <td className="py-1 font-sans text-text-primary">{r.name}</td><td className="text-text-tertiary">{r.maturity}</td><td className="text-right font-semibold">{lvl(r)}</td>
              <td className="text-right text-text-secondary">{r.spread_equiv_bp != null ? `≈${Math.round(r.spread_equiv_bp)} bp` : r.quote === 'spread' ? `${r.level.toFixed(0)} bp` : '—'}</td>
              <td className={cn('text-right', tone(r, r.change_1d))}>{chg(r, r.change_1d)}</td><td className={cn('text-right', tone(r, r.change_period))} title={`since ${r.since}`}>{chg(r, r.change_period)}</td>
              <td className="text-right">{r.trades}</td><td className="text-right text-text-secondary">{big(r.notional)}</td></tr>))}</tbody>
        </table>
      </Panel>
      <Panel title={`${row.name}: ${row.quote === 'price' ? 'price' : 'spread (bp)'} over recent sessions`}>
        <div className="mkt-chart-surface"><LineChart rows={row.history} x="date" height={230} controls={false} fmt={(v) => (row.quote === 'price' ? v.toFixed(2) : `${v.toFixed(1)} bp`)}
          lines={[{ key: 'level', label: row.name, color: COLORS[0] }]} /></div>
      </Panel>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── CDSA ─────────────────────────────────────────────────────────────────────
export function CdsaView({ onOpen }: { onOpen: (s: string) => void }) {
  const [days, setDays] = useStickyState('cdsa.days', 5);
  const [kind, setKind] = useState<'all' | 'corp' | 'sov'>('all');
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/cdsa?days=${days}`, 6 * 3_600_000);
  const controls = (
    <div className="flex flex-wrap gap-1">
      {[1, 5, 10].map((n) => <Chip key={n} on={days === n} onClick={() => setDays(n)}>{n === 1 ? 'Last session' : `${n} sessions`}</Chip>)}
      <span className="w-3" />
      {([['all', 'All'], ['corp', 'Companies'], ['sov', 'Sovereigns']] as const).map(([k, l]) => <Chip key={k} on={kind === k} onClick={() => setKind(k)}>{l}</Chip>)}
    </div>
  );
  if (loading && !d) return <div className="space-y-2">{controls}<Loading label="Reading single-name CDS trades…" /></div>;
  if (error && !d) return <div className="space-y-2">{controls}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  const rows = d.rows.filter((r: any) => kind === 'all' || (kind === 'sov') === r.sovereign);
  return (
    <div className="space-y-3">
      {controls}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        <Tile label="Single-name trades" value={d.total_trades.toLocaleString()} sub={`${d.from} → ${d.to}`} />
        <Tile label="Reference entities" value={d.entities} sub="companies and countries traded" />
        <Tile label="Busiest" value={d.rows[0]?.name ?? '—'} sub={d.rows[0] ? `${d.rows[0].trades} trades` : ''} />
      </div>
      <Panel title="Most-traded single-name CDS">
        <table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Reference entity</th><th className="text-left font-normal">Reference bond</th><th className="text-left font-normal">Type</th>
            <th className="text-right font-normal">Trades</th><th className="text-right font-normal">Notional</th><th className="text-right font-normal">Days</th></tr></thead>
          <tbody>{rows.map((r: any) => {
            const eq = r.ticker?.split(' ')[0];
            return (
              <tr key={r.issuer_code} onClick={() => eq && !r.sovereign && onOpen(eq)} className={cn('border-t border-border-subtle', eq && !r.sovereign && 'cursor-pointer hover:bg-surface-2')}>
                <td className="py-1 font-sans text-text-primary">{r.name ?? r.isin}</td><td className="text-text-tertiary">{r.ticker || r.isin}</td>
                <td className="font-sans text-text-secondary">{r.sovereign ? 'Sovereign' : 'Corporate'}</td><td className="text-right font-semibold">{r.trades}</td>
                <td className="text-right text-text-secondary">{big(r.notional)}</td><td className="text-right">{r.days_traded}</td></tr>
            );
          })}</tbody>
        </table>
      </Panel>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── EXTH ─────────────────────────────────────────────────────────────────────
export function ExthView({ onOpen }: { onOpen: (s: string) => void }) {
  const [session, setSession] = useStickyState('exth.session', 'PRE_MARKET');
  const [cap, setCap] = useStickyState('exth.cap', 5e8);
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/exth?session=${session}&min_cap=${cap}`, 60_000);
  const controls = (
    <div className="flex flex-wrap gap-1">
      {([['PRE_MARKET', 'Pre-market'], ['AFTER_MARKET', 'After hours'], ['REGULAR', 'Regular session']] as const).map(([k, l]) => <Chip key={k} on={session === k} onClick={() => setSession(k)}>{l}</Chip>)}
      <span className="w-3" />
      {[[5e7, 'Over $50M'], [5e8, 'Over $500M'], [1e10, 'Over $10B']].map(([v, l]) => <Chip key={v as number} on={cap === v} onClick={() => setCap(v as number)}>{l as string}</Chip>)}
    </div>
  );
  if (loading && !d) return <div className="space-y-2">{controls}<Loading label="Loading movers…" /></div>;
  if (error && !d) return <div className="space-y-2">{controls}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  const when = (s: string | null) => (s ? s.replace('T', ' ').slice(0, 16) : '—');
  const List = ({ title, rows }: { title: string; rows: any[] }) => (
    <Panel title={title}>
      <table className="w-full text-2xs font-mono tabular-nums">
        <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Symbol</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">Change</th>
          <th className="text-right font-normal">Volume</th><th className="text-right font-normal">Mkt cap</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2" title={`${r.name ?? ''} · ${r.sector ?? ''}`}>
            <td className="py-1"><span className="text-text-primary">{r.symbol}</span> <span className="font-sans text-text-tertiary truncate">{(r.name ?? '').slice(0, 22)}</span></td>
            <td className="text-right">{r.price?.toFixed(2)}</td><td className={cn('text-right font-semibold', sign(r.change_pct))}>{pct(r.change_pct, 1)}</td>
            <td className="text-right text-text-secondary">{big(r.volume)}</td><td className="text-right text-text-secondary">{big(r.market_cap)}</td></tr>))}</tbody>
      </table>
      {!rows.length && <p className="text-xs text-text-tertiary py-2">No movers above this size in this session.</p>}
    </Panel>
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">{controls}<span className="text-[11px] text-text-tertiary">{when(d.from)} → {when(d.to)} ET</span></div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <List title="Biggest gainers" rows={d.gainers} />
        <List title="Biggest losers" rows={d.losers} />
      </div>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── TRAN ─────────────────────────────────────────────────────────────────────
function Marked({ text, terms }: { text: string; terms: string[] }) {
  if (!terms.length) return <>{text}</>;
  const re = new RegExp(`\\b(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})[a-z]*`, 'gi');
  const out: React.ReactNode[] = [];
  let last = 0, m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    out.push(<Fragment key={`t${last}`}>{text.slice(last, m.index)}</Fragment>, <mark key={`m${m.index}`} className="bg-bloomberg/25 text-text-primary rounded-sm px-px">{m[0]}</mark>);
    last = m.index + m[0].length;
  }
  out.push(<Fragment key="end">{text.slice(last)}</Fragment>);
  return <>{out}</>;
}

export function TranView({ symbol }: { symbol: string }) {
  const list = useJSON<any>(`/api/v1/mkt/tran/${encodeURIComponent(symbol)}`, 12 * 3_600_000);
  const [callId, setCallId] = useState<number | null>(null);
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [speaker, setSpeaker] = useState<string | null>(null);
  const chosen = useJSON<any>(callId ? `/api/v1/mkt/tran/${encodeURIComponent(symbol)}/call/${callId}` : null);
  const search = useJSON<any>(query ? `/api/v1/mkt/tran/${encodeURIComponent(symbol)}/search?q=${encodeURIComponent(query)}` : null);
  const call = callId ? chosen.data : list.data?.latest;
  const paras = useMemo(() => (call?.paragraphs ?? []).filter((p: any) => !speaker || p.speaker === speaker), [call, speaker]);
  if (list.loading && !list.data) return <Loading label="Loading earnings-call transcripts (first open of a company takes a few seconds)…" />;
  if (list.error && !list.data) return <ErrorBox msg={list.error} />;
  if (!list.data) return null;
  const d = list.data;
  return (
    <div className="space-y-3">
      <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); setQuery(input.trim()); }}>
        <select aria-label="Earnings call" value={callId ?? d.latest.id} onChange={(e) => { setCallId(Number(e.target.value)); setSpeaker(null); }}
          className="bg-surface-1 border border-border rounded-sm px-2 py-1.5 text-xs text-text-primary">
          {d.calls.map((c: any) => <option key={c.id} value={c.id}>{c.date}{c.fiscal_year ? ` · FY${c.fiscal_year} Q${c.fiscal_quarter}` : ''}</option>)}
        </select>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Search four years of calls — e.g. margins, pricing, AI demand" aria-label="Search calls"
          className="bg-surface-1 border border-border rounded-sm px-2 py-1.5 text-xs text-text-primary flex-1 min-w-[16rem]" />
        <button className="px-3 py-1.5 border border-bloomberg text-bloomberg text-[11px] rounded-sm hover:bg-bloomberg/10">Search calls</button>
        {query && <button type="button" onClick={() => { setQuery(''); setInput(''); }} className="text-[11px] text-text-tertiary hover:text-text-primary">Clear</button>}
      </form>
      {query ? (
        <Panel title={`"${query}" across ${symbol}'s calls`} right={<span className="text-[11px] text-text-tertiary">{search.data ? `${search.data.matches} passages` : ''}</span>}>
          {search.loading && !search.data && <Loading label="Searching…" />}
          {search.error && <ErrorBox msg={search.error} />}
          <div className="space-y-2">{(search.data?.hits ?? []).map((h: any, i: number) => (
            <div key={i} className="border-t border-border-subtle pt-2">
              <div className="text-[11px] mb-0.5"><span className="font-semibold text-text-primary">{h.speaker}</span> <span className="text-text-tertiary">· {h.quarter} · {h.date}</span>
                <button onClick={() => { setCallId(h.call_id); setQuery(''); }} className="ml-2 text-bloomberg hover:underline">Open call</button></div>
              <p className="text-xs text-text-secondary leading-relaxed"><Marked text={h.text} terms={search.data.terms} /></p>
            </div>))}</div>
        </Panel>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[14rem_minmax(0,1fr)] gap-3">
          <Panel title="Speakers">
            <div className="space-y-0.5">
              <button onClick={() => setSpeaker(null)} className={cn('w-full text-left text-[11px] px-1.5 py-1 rounded-sm hover:bg-surface-2', !speaker && 'bg-surface-2 text-text-primary')}>Everyone</button>
              {(call?.speakers ?? []).slice(0, 14).map((s: any) => (
                <button key={s.speaker} onClick={() => setSpeaker(s.speaker)} className={cn('w-full text-left text-[11px] px-1.5 py-1 rounded-sm hover:bg-surface-2 truncate', speaker === s.speaker ? 'bg-surface-2 text-text-primary' : 'text-text-secondary')}>
                  {s.speaker} <span className="text-text-tertiary">· {Math.round(s.chars / 1000)}k chars</span></button>))}
            </div>
          </Panel>
          <Panel title={call ? `${symbol} earnings call — ${call.date}${call.fiscal_year ? ` (FY${call.fiscal_year} Q${call.fiscal_quarter})` : ''}` : 'Loading call…'}>
            {chosen.loading && callId && !chosen.data && <Loading label="Loading the call…" />}
            <div className="space-y-3 max-h-[42rem] overflow-y-auto pr-1">{paras.map((p: any, i: number) => (
              <div key={i}><div className="text-[11px] font-semibold text-text-primary mb-0.5">{p.speaker}</div>
                <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-line">{p.text}</p></div>))}</div>
          </Panel>
        </div>
      )}
      <Source>{d.source}</Source>
    </div>
  );
}

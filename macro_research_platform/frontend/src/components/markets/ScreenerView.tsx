// Movers and a global equity screener over 22 markets (Yahoo's screener): any region(s),
// sector, size, valuation, yield and today's move. Market caps are entered in USD and
// converted to each market's currency by the server.
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { REGION_MARKETS, useRegion } from '@/lib/region';
import { Chg, ErrorBox, fmtBig, fmtPrice, Loading, Panel, useJSON } from './shared';

function Table({ rows, onOpen, showSector = true }: { rows: any[]; onOpen: (s: string) => void; showSector?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-2xs">
        <thead><tr className="text-text-tertiary">
          <th className="text-left font-normal pb-1">Symbol</th><th className="text-left font-normal">Name</th>
          <th className="text-right font-normal">Price</th><th className="text-right font-normal">Change</th>
          <th className="text-right font-normal">Market cap</th><th className="text-right font-normal hidden md:table-cell">Volume</th>
          <th className="text-right font-normal hidden md:table-cell">P/E</th><th className="text-right font-normal hidden lg:table-cell">Yield</th>
          {showSector && <th className="text-left font-normal hidden xl:table-cell pl-3">Sector</th>}</tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3">
            <td className="py-1 font-mono text-text-primary">{r.symbol}</td>
            <td className="text-text-secondary max-w-[16rem] truncate" title={r.name}>{r.name}</td>
            <td className="text-right font-mono">{fmtPrice(r.price)} <span className="text-text-tertiary">{r.currency}</span></td>
            <td className="text-right"><Chg v={r.change_pct} /></td>
            <td className="text-right font-mono">{fmtBig(r.market_cap)}</td>
            <td className="text-right font-mono hidden md:table-cell">{fmtBig(r.volume)}</td>
            <td className="text-right font-mono hidden md:table-cell">{r.pe != null ? r.pe.toFixed(1) : '—'}</td>
            <td className="text-right font-mono hidden lg:table-cell">{r.dividend_yield != null ? `${(r.dividend_yield * 100).toFixed(1)}%` : '—'}</td>
            {showSector && <td className="text-text-tertiary hidden xl:table-cell pl-3 truncate">{r.sector ?? ''}</td>}
          </tr>))}</tbody>
      </table>
    </div>
  );
}

export function MoversView({ onOpen }: { onOpen: (s: string) => void }) {
  const meta = useJSON<any>('/api/v1/mkt/meta');
  const area = useRegion();
  const [region, setRegion] = useState(() => REGION_MARKETS[area][0]);
  useEffect(() => { setRegion(REGION_MARKETS[area][0]); }, [area]);         // follow the Markets region
  const [kind, setKind] = useState<'gainers' | 'losers' | 'active'>('gainers');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/movers?region=${region}&kind=${kind}&count=30`, 300_000);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <select value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Market"
          className="bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary">
          {(meta.data?.regions ?? [{ id: 'us', name: 'United States' }]).map((r: any) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <div className="flex border border-border">{(['gainers', 'losers', 'active'] as const).map((k) => (
          <button key={k} onClick={() => setKind(k)} className={cn('px-3 py-1 text-2xs capitalize', kind === k ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>
            {k === 'active' ? 'Most active' : k}</button>))}</div>
      </div>
      {loading && !data ? <Loading /> : error ? <ErrorBox msg={error} /> : data && (
        <Panel title={`${data.region_name} — ${kind === 'active' ? 'most active' : `top ${kind}`} today`}>
          <Table rows={data.rows} onOpen={onOpen} />
          {data.note && <div className="text-[10px] text-text-tertiary mt-2">{data.note}</div>}
        </Panel>
      )}
    </div>
  );
}

const inp = 'w-full bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary';

// One-click screens (from OpenTerminal). Market caps in $bn; P/E and yield as typed in the form.
const PRESETS: [string, Record<string, string>, string][] = [
  ['Mega caps', { market_cap_min: '200' }, 'Companies worth more than $200bn'],
  ['Value', { market_cap_min: '5', pe_max: '12', pe_min: '0.1', sort: 'pe' }, 'P/E below 12, over $5bn, cheapest first'],
  ['Quality value', { market_cap_min: '20', pe_max: '18', pe_min: '0.1', dividend_yield_min: '2' }, 'P/E under 18 with a dividend of 2%+, over $20bn'],
  ['High dividend', { market_cap_min: '5', dividend_yield_min: '4', sort: 'dividend_yield' }, 'Dividend yield 4%+, over $5bn'],
  ['Today\'s winners', { market_cap_min: '2', change_pct_min: '3', sort: 'change' }, 'Up 3%+ today, over $2bn'],
  ['Most traded', { market_cap_min: '1', sort: 'volume' }, 'Highest volume today'],
  ['Small caps', { market_cap_min: '0.3', market_cap_max: '2' }, '$300m – $2bn'],
];

export function ScreenerView({ onOpen }: { onOpen: (s: string) => void }) {
  const meta = useJSON<any>('/api/v1/mkt/meta');
  const area = useRegion();
  const [f, setF] = useState<Record<string, string>>({ regions: REGION_MARKETS[area][0], sector: '', sort: 'market_cap', market_cap_min: '10', pe_max: '', dividend_yield_min: '' });
  useEffect(() => { setF((x) => ({ ...x, regions: REGION_MARKETS[area][0] })); }, [area]);
  const [url, setUrl] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const run = (off = 0, form: Record<string, string> = f) => {
    const f = form;
    const p = new URLSearchParams({ regions: f.regions, sort: f.sort, size: '50', offset: String(off) });
    if (f.sort === 'pe') p.set('ascending', 'true');            // cheapest first
    if (f.sector) p.set('sector', f.sector);
    if (f.market_cap_min) p.set('market_cap_min', String(Number(f.market_cap_min) * 1e9));
    if (f.market_cap_max) p.set('market_cap_max', String(Number(f.market_cap_max) * 1e9));
    if (f.pe_max) p.set('pe_max', f.pe_max);
    if (f.pe_min) p.set('pe_min', f.pe_min);
    if (f.dividend_yield_min) p.set('dividend_yield_min', f.dividend_yield_min);
    if (f.change_pct_min) p.set('change_pct_min', f.change_pct_min);
    setOffset(off);
    setUrl(`/api/v1/mkt/screen?${p.toString()}`);
  };
  const { data, error, loading } = useJSON<any>(url);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const preset = (p: Record<string, string>) => {
    const next = { regions: f.regions, sector: f.sector, sort: 'market_cap', market_cap_min: '', market_cap_max: '', pe_max: '', pe_min: '', dividend_yield_min: '', change_pct_min: '', ...p };
    setF(next); run(0, next);
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1 text-xs">
        <span className="text-text-tertiary mr-1">Presets</span>
        {PRESETS.map(([name, p, tip]) => (
          <button key={name} onClick={() => preset(p)} title={tip} className="px-2 py-0.5 border border-border text-text-secondary hover:text-bloomberg hover:border-bloomberg">{name}</button>))}
        <span className="text-text-tertiary ml-1">(in the market selected below)</span>
      </div>
      <Panel title="Global equity screener — 22 markets">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 items-end">
          <label className="text-[10px] uppercase text-text-tertiary col-span-2">Market
            <select value={f.regions} onChange={set('regions')} className={inp}>
              {(meta.data?.regions ?? []).map((r: any) => <option key={r.id} value={r.id}>{r.name} ({r.currency})</option>)}
              <option value="de,fr,nl,it,es">Eurozone (DE, FR, NL, IT, ES)</option>
            </select></label>
          <label className="text-[10px] uppercase text-text-tertiary col-span-2">Sector
            <select value={f.sector} onChange={set('sector')} className={inp}><option value="">All sectors</option>
              {(meta.data?.sectors ?? []).map((s: string) => <option key={s}>{s}</option>)}</select></label>
          <label className="text-[10px] uppercase text-text-tertiary">Mkt cap ≥ $bn<input type="number" min={0} value={f.market_cap_min} onChange={set('market_cap_min')} className={inp} /></label>
          <label className="text-[10px] uppercase text-text-tertiary">P/E ≤<input type="number" min={0} value={f.pe_max} onChange={set('pe_max')} className={inp} /></label>
          <label className="text-[10px] uppercase text-text-tertiary">Yield ≥ %<input type="number" min={0} step="0.5" value={f.dividend_yield_min} onChange={set('dividend_yield_min')} className={inp} /></label>
          <label className="text-[10px] uppercase text-text-tertiary">Sort
            <select value={f.sort} onChange={set('sort')} className={inp}>
              <option value="market_cap">Market cap</option><option value="change">Today's change</option><option value="volume">Volume</option>
              <option value="pe">P/E</option><option value="dividend_yield">Dividend yield</option></select></label>
        </div>
        <button onClick={() => run(0)} className="mt-3 px-4 py-1.5 text-xs bg-bloomberg text-bg">Screen</button>
        <span className="ml-3 text-[10px] text-text-tertiary">Primary listings only (cross-listings such as Nvidia in Frankfurt are removed). Market caps in USD.</span>
      </Panel>
      {loading && <Loading label="Screening…" />}
      <ErrorBox msg={error} />
      {data && (
        <Panel title={`${data.total?.toLocaleString() ?? '?'} matches`} right={
          <div className="flex gap-1 text-[10px]">
            <button disabled={offset === 0} onClick={() => run(Math.max(0, offset - 50))} className="px-2 border border-border disabled:opacity-40">← Prev</button>
            <button disabled={!data.rows.length} onClick={() => run(offset + 50)} className="px-2 border border-border disabled:opacity-40">Next →</button>
          </div>}>
          {data.rows.length ? <Table rows={data.rows} onOpen={onOpen} /> : <div className="text-2xs text-text-tertiary">No matches — loosen the filters.</div>}
        </Panel>
      )}
    </div>
  );
}

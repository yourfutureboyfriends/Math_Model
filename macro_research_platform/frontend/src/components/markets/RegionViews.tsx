// Regions and countries: the region bar (GLOBAL / AMERICAS / EUROPE / MID EAST & AFRICA /
// ASIA-PACIFIC), RMON (regional monitor: country matrix, indices, movers, news, releases,
// earnings) and CTRY (one country's markets, economy, risk and news on one page).
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { REGIONS, REGION_CCYS, REGION_MARKETS, setRegion, useRegion, type Region } from '@/lib/region';
import { toTerminal } from './bbg';
import { Chart } from './TickerView';
import { Chg, ErrorBox, fmtBig, fmtPrice, Loading, Panel, useJSON } from './shared';

const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v.toFixed(d)}%`);
const MARKET_NAME: Record<string, string> = { us: 'US', ca: 'Canada', br: 'Brazil', mx: 'Mexico', gb: 'UK', de: 'Germany', fr: 'France', ch: 'Switzerland',
  nl: 'Netherlands', it: 'Italy', es: 'Spain', se: 'Sweden', sa: 'Saudi Arabia', za: 'South Africa', jp: 'Japan', cn: 'China', hk: 'Hong Kong',
  in: 'India', kr: 'Korea', tw: 'Taiwan', au: 'Australia', sg: 'Singapore' };

export function RegionBar({ onPick }: { onPick?: (r: Region) => void }) {
  const r = useRegion();
  return (
    <div className="inline-flex flex-wrap items-center gap-0.5 p-0.5 rounded-md bg-surface-2 border border-border-subtle text-[11px]" role="tablist" aria-label="Region">
      <span className="px-2 text-[10px] uppercase tracking-wider text-text-tertiary">Region</span>
      {REGIONS.map((x) => (
        <button key={x.id} role="tab" aria-selected={r === x.id} onClick={() => { setRegion(x.id); onPick?.(x.id); }}
          className={cn('px-3 py-0.5 rounded-sm font-medium tracking-wide border', r === x.id ? 'border-[rgb(255_214_0/0.35)] bg-[rgb(255_214_0/0.08)] text-[#ffd84a]' : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-surface-3')}>{x.short}</button>))}
    </div>
  );
}

// ── RMON ────────────────────────────────────────────────────────────────────
export function RegionMonitor({ onOpen, onGo }: { onOpen: (s: string) => void; onGo: (fn: string, s?: string) => void }) {
  const region = useRegion();
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/region/${region}`, 600_000);
  const macro = useJSON<any>('/api/v1/global-macro', 3_600_000);
  const [mkt, setMkt] = useState<string | null>(null);
  const market = mkt && REGION_MARKETS[region].includes(mkt) ? mkt : REGION_MARKETS[region][0];
  const movers = useJSON<any>(`/api/v1/mkt/movers?region=${market}&kind=active&count=10`, 300_000);
  const news = useJSON<any>(`/api/v1/mkt/news?region=${region}&limit=25`, 600_000);
  const ccys = REGION_CCYS[region];
  const eco = useJSON<any>(`/api/v1/mkt/eco/global?days_back=3&min_impact=Medium${ccys.length ? `&countries=${ccys.join(',')}` : ''}`, 900_000);
  const evts = useJSON<any>('/api/v1/mkt/evts?days=7&min_cap_bn=5&limit=250', 1_800_000);
  const policy: Record<string, any> = useMemo(() => {
    const m: Record<string, any> = {};
    for (const e of macro.data?.economies ?? []) m[e.code] = e;
    return m;
  }, [macro.data]);
  const rows: any[] = (data?.countries ?? []).filter((c: any) => c.index || c.etf || c.gdp_usd_bn > 50).slice(0, region === 'global' ? 40 : 30);
  const earnings = (evts.data?.rows ?? []).filter((r: any) => region === 'global' || r.region === region).slice(0, 12);
  if (loading && !data) return <Loading label="Building the regional monitor (first load can take a minute)…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  const eurozone = ['DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'IE', 'FI', 'PT', 'GR'];
  const pol = (iso: string) => policy[iso]?.policy?.rate ?? (eurozone.includes(iso) ? policy.EA?.policy?.rate : undefined);
  return (
    <div className="space-y-2">
      <Panel title={`${data?.name ?? ''} — markets and economies (${rows.length} countries, largest economies first)`}>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] font-mono tabular-nums">
            <thead><tr className="text-text-tertiary">
              <th className="text-left font-normal">Country</th><th className="text-left font-normal">Index</th><th className="text-right font-normal">Level</th>
              <th className="text-right font-normal">1D</th><th className="text-right font-normal">YTD</th><th className="text-right font-normal">Ccy vs $ YTD</th>
              <th className="text-right font-normal">10Y</th><th className="text-right font-normal">Policy</th><th className="text-right font-normal">CPI</th>
              <th className="text-right font-normal">GDP</th><th className="text-right font-normal">Debt/GDP</th><th className="text-right font-normal">Rating</th><th className="text-right font-normal">GDP $bn</th></tr></thead>
            <tbody>{rows.map((c) => (
              <tr key={c.iso2} className="border-t border-border-subtle cursor-pointer" onClick={() => onGo('CTRY', c.iso2)} title={`Open ${c.name}`}>
                <td className="py-0.5 font-sans text-text-primary whitespace-nowrap"><span className="text-text-tertiary mr-1">{c.iso2}</span>{c.name}</td>
                <td className="text-text-secondary font-sans whitespace-nowrap">{c.index?.label ?? (c.etf ? `${c.etf.etf} (ETF, $)` : '')}</td>
                <td className="text-right text-text-primary">{c.index ? fmtPrice(c.index.price) : c.etf ? fmtPrice(c.etf.price) : ''}</td>
                <td className="text-right"><Chg v={c.index?.change_1d ?? c.change_1d} /></td>
                <td className="text-right"><Chg v={c.index?.change_ytd ?? c.change_ytd} d={1} /></td>
                <td className="text-right">{c.currency === 'USD' ? <span className="text-text-tertiary">USD</span> : c.fx?.pegged ? <span className="text-text-tertiary" title={`Pegged at ${c.fx.per_usd} per USD`}>peg</span> : <Chg v={c.fx?.change_ytd} d={1} />}</td>
                <td className="text-right">{c.yield_10y != null ? c.yield_10y.toFixed(2) : ''}</td>
                <td className="text-right">{pol(c.iso2) != null ? pol(c.iso2).toFixed(2) : ''}</td>
                <td className="text-right">{pct(c.inflation)}</td><td className="text-right">{pct(c.gdp_growth)}</td>
                <td className="text-right">{c.gov_debt != null ? c.gov_debt.toFixed(0) : '—'}</td>
                <td className="text-right text-text-secondary">{c.rating ?? ''}</td>
                <td className="text-right text-text-tertiary">{c.gdp_usd_bn != null ? Math.round(c.gdp_usd_bn).toLocaleString() : ''}</td></tr>))}</tbody>
          </table>
        </div>
        <div className="text-[10px] text-text-tertiary mt-1">Index: local currency (US-listed MSCI ETF in $ where no local index is available). Inflation, GDP growth and debt: IMF {data?.year} estimates. 10Y: OECD (monthly) / US live. Click a country for its page.</div>
      </Panel>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-2">
        <Panel title="Most active" right={<span className="flex gap-1">{REGION_MARKETS[region].map((m) => (
          <button key={m} onClick={() => setMkt(m)} className={cn('px-1 text-[10px]', market === m ? 'text-bloomberg' : 'text-text-tertiary hover:text-text-primary')}>{m.toUpperCase()}</button>))}</span>}>
          {movers.loading && !movers.data ? <Loading /> : (
            <table className="w-full text-[11px] font-mono"><tbody>{(movers.data?.rows ?? []).map((r: any) => (
              <tr key={r.symbol} className="border-t border-border-subtle cursor-pointer" onClick={() => onOpen(r.symbol)} title={r.name}>
                <td className="py-0.5 text-text-primary">{toTerminal(r.symbol)}</td><td className="text-right">{fmtPrice(r.price)}</td>
                <td className="text-right"><Chg v={r.change_pct} /></td><td className="text-right text-text-tertiary">{fmtBig(r.volume)}</td></tr>))}</tbody></table>)}
          <div className="text-[10px] text-text-tertiary mt-1">{MARKET_NAME[market]} · companies over ~$2bn</div>
        </Panel>
        <Panel title="Headlines" right={<button onClick={() => onGo('N')} className="text-[10px] text-text-tertiary hover:text-bloomberg">N &lt;GO&gt;</button>}>
          <ol className="text-[11px] space-y-0.5 max-h-72 overflow-y-auto">{(news.data?.items ?? []).map((n: any, i: number) => (
            <li key={i} className="flex gap-1.5"><span className="text-bloomberg w-5 text-right shrink-0">{i + 1})</span>
              <a href={n.url} target="_blank" rel="noreferrer noopener" className="text-text-primary hover:underline line-clamp-1" title={n.title}>{n.title}</a>
              <span className="text-text-tertiary shrink-0 ml-auto">{n.source}</span></li>))}</ol>
          {news.data && news.data.items.length === 0 && <p className="text-[11px] text-text-tertiary">No recent regional headlines.</p>}
        </Panel>
        <div className="space-y-2">
          <Panel title="Economic releases" right={<button onClick={() => onGo('ECO')} className="text-[10px] text-text-tertiary hover:text-bloomberg">ECO &lt;GO&gt;</button>}>
            {ccys.length === 0 && region !== 'global' ? <p className="text-[11px] text-text-tertiary">The free consensus calendar covers the US, euro area, UK, Japan, China, Canada, Australia, Switzerland and New Zealand.</p> : (
              <table className="w-full text-[11px]"><tbody>{(eco.data?.events ?? []).slice(-10).map((e: any, i: number) => (
                <tr key={i} className="border-t border-border-subtle"><td className="py-0.5 font-mono text-text-tertiary">{String(e.date).slice(5, 10)}</td><td className="text-text-secondary">{e.country}</td>
                  <td className="text-text-primary truncate max-w-[12rem]">{e.title}</td><td className="text-right font-mono">{e.actual ?? e.forecast ?? ''}</td></tr>))}</tbody></table>)}
          </Panel>
          <Panel title="Earnings this week" right={<button onClick={() => onGo('EVTS')} className="text-[10px] text-text-tertiary hover:text-bloomberg">EVTS &lt;GO&gt;</button>}>
            {earnings.length === 0 ? <p className="text-[11px] text-text-tertiary">{evts.loading ? 'Loading…' : 'No large-cap reports in this region this week (the free calendar is US-heavy).'}</p> : (
              <table className="w-full text-[11px]"><tbody>{earnings.map((r: any) => (
                <tr key={r.symbol + r.datetime} className="border-t border-border-subtle cursor-pointer" onClick={() => onOpen(r.symbol)}>
                  <td className="py-0.5 font-mono text-text-tertiary">{String(r.datetime).slice(5, 10)}</td><td className="font-mono text-bloomberg">{r.symbol}</td>
                  <td className="text-text-secondary truncate max-w-[10rem]">{r.company}</td><td className="text-right font-mono">{r.eps_estimate ?? ''}</td></tr>))}</tbody></table>)}
          </Panel>
        </div>
      </div>
    </div>
  );
}

// ── CTRY ────────────────────────────────────────────────────────────────────
export function CountryView({ iso, onOpen, onGo }: { iso?: string; onOpen: (s: string) => void; onGo: (fn: string, s?: string) => void }) {
  const code = (iso || 'US').toUpperCase();
  const { data: c, error, loading } = useJSON<any>(`/api/v1/mkt/country/${code}`, 600_000);
  const macro = useJSON<any>('/api/v1/global-macro', 3_600_000);
  const top = useJSON<any>(c?.market ? `/api/v1/mkt/screen?regions=${c.market}&size=15` : null, 900_000);
  const news = useJSON<any>(`/api/v1/mkt/news?country=${code}&limit=20`, 600_000);
  const eco = useJSON<any>(c?.currency ? `/api/v1/mkt/eco/global?days_back=7&countries=${c.currency}` : null, 900_000);
  const regions = useJSON<any>('/api/v1/mkt/regions');
  const [chartSym, setChartSym] = useState<'index' | 'fx' | 'etf'>('index');
  if (loading && !c) return <Loading label={`Loading ${code}…`} />;
  if (error && !c) return <ErrorBox msg={error} />;
  if (!c) return null;
  const pol = (macro.data?.economies ?? []).find((e: any) => e.code === code) ??
    (['DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'IE', 'FI', 'PT', 'GR'].includes(code) ? (macro.data?.economies ?? []).find((e: any) => e.code === 'EA') : null);
  const sym = chartSym === 'fx' ? c.fx_symbol : chartSym === 'etf' ? c.etf?.etf : (c.index?.symbol ?? c.etf?.etf);
  const sameRegion: string[] = (regions.data?.regions ?? []).find((r: any) => r.id === c.region)?.countries ?? [];
  const peers = ['US', 'CN', 'JP', 'DE', 'GB', 'IN', 'FR', 'IT', 'CA', 'BR', 'KR', 'AU', 'MX', 'ES', 'ID', 'NL', 'SA', 'TR', 'CH', 'TW', 'PL', 'SE', 'HK', 'SG', 'ZA', 'AE', 'IL']
    .filter((x) => sameRegion.includes(x) && x !== code).slice(0, 10);
  const stat = (k: string, v: React.ReactNode, sub?: React.ReactNode) => (
    <div className="border border-border bg-surface-1 px-2.5 py-1.5"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{k}</div><div className="font-mono text-text-primary">{v}</div>{sub && <div className="text-[10px] text-text-tertiary">{sub}</div>}</div>);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="text-xl font-semibold text-text-primary">{c.name}</span>
        <span className="text-text-tertiary text-xs">{c.iso2} · {c.region_name} · {c.currency}{c.rating ? ` · ${c.rating}` : ''}</span>
        <span className="ml-auto flex flex-wrap gap-1 text-[11px]">{peers.map((p) => (
          <button key={p} onClick={() => onGo('CTRY', p)} className="px-1.5 border border-border text-text-secondary hover:text-bloomberg hover:border-bloomberg font-mono">{p}</button>))}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-1.5">
        {stat(c.index?.label ?? 'Equity index', c.index ? fmtPrice(c.index.price) : c.etf ? `${fmtPrice(c.etf.price)} (${c.etf.etf})` : '—', c.index ? <><Chg v={c.index.change_1d} /> · YTD <Chg v={c.index.change_ytd} d={1} /></> : null)}
        {stat(`${c.currency} per USD`, c.fx ? fmtPrice(c.fx.per_usd, 'FX') : '1.00', c.fx?.pegged ? 'pegged to the US dollar' : c.fx && c.currency !== 'USD' ? <>vs $ YTD <Chg v={c.fx.change_ytd} d={1} /></> : null)}
        {stat('10-year yield', c.yield_10y != null ? `${c.yield_10y.toFixed(2)}%` : '—', c.yield_source)}
        {stat('Policy rate', pol?.policy?.rate != null ? `${pol.policy.rate.toFixed(2)}%` : '—', pol ? `${pol.cb ?? ''}${pol.policy?.stance ? ` · ${pol.policy.stance}` : ''}` : 'not in the macro model')}
        {stat('Inflation', pct(c.inflation), `next year ${pct(c.inflation_next)}`)}
        {stat('GDP growth', pct(c.gdp_growth), `next year ${pct(c.gdp_growth_next)}`)}
        {stat('Unemployment', pct(c.unemployment), `govt debt ${c.gov_debt != null ? c.gov_debt.toFixed(0) + '% GDP' : '—'}`)}
        {stat('Country risk', c.crp != null ? `${(c.crp * 100).toFixed(2)}%` : '—', c.erp_total != null ? `equity premium ${(c.erp_total * 100).toFixed(2)}%` : '')}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-2">
        <div className="space-y-1">
          <div className="flex gap-1 text-[11px]">
            {(['index', 'fx', 'etf'] as const).filter((k) => (k === 'index' ? c.index || c.etf : k === 'fx' ? c.fx_symbol : c.etf)).map((k) => (
              <button key={k} onClick={() => setChartSym(k)} className={cn('px-2 py-0.5 border', chartSym === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>
                {k === 'index' ? (c.index?.label ?? 'Equities') : k === 'fx' ? `USD/${c.currency}` : `${c.etf?.etf} (USD ETF)`}</button>))}
            {sym && <button onClick={() => onOpen(sym)} className="ml-auto px-2 py-0.5 border border-border text-text-tertiary hover:text-bloomberg">Open {toTerminal(sym)}</button>}
          </div>
          {sym ? <div className="border border-border"><Chart key={sym} symbol={sym} height={340} /></div> : <p className="text-xs text-text-tertiary">No traded index or currency for this country.</p>}
        </div>
        <Panel title={c.market ? 'Largest listed companies' : 'Equity market'}>
          {!c.market ? <p className="text-[11px] text-text-tertiary">Stock-level screening covers 22 major markets; use the country ETF or index for {c.name}.</p>
            : top.loading && !top.data ? <Loading /> : (
            <table className="w-full text-[11px] font-mono"><tbody>{(top.data?.rows ?? []).map((r: any) => (
              <tr key={r.symbol} className="border-t border-border-subtle cursor-pointer" onClick={() => onOpen(r.symbol)}>
                <td className="py-0.5 text-text-primary">{toTerminal(r.symbol)}</td><td className="font-sans text-text-secondary truncate max-w-[11rem]">{r.name}</td>
                <td className="text-right">{fmtPrice(r.price)}</td><td className="text-right"><Chg v={r.change_pct} /></td><td className="text-right text-text-tertiary">{fmtBig(r.market_cap)}</td></tr>))}</tbody></table>)}
        </Panel>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-2">
        <Panel title={`${c.name} in the news`}>
          {(news.data?.items ?? []).length === 0 ? <p className="text-[11px] text-text-tertiary">{news.loading ? 'Loading…' : 'No recent headlines mention this country.'}</p> : (
            <ol className="text-[11px] space-y-0.5">{news.data.items.map((n: any, i: number) => (
              <li key={i} className="flex gap-1.5"><span className="text-bloomberg w-5 text-right shrink-0">{i + 1})</span>
                <a href={n.url} target="_blank" rel="noreferrer noopener" className="text-text-primary hover:underline line-clamp-1" title={n.summary || n.title}>{n.title}</a>
                <span className="text-text-tertiary shrink-0 ml-auto">{n.source}</span></li>))}</ol>)}
        </Panel>
        <Panel title={`Economic releases — ${c.currency}`}>
          {(eco.data?.events ?? []).length === 0 ? <p className="text-[11px] text-text-tertiary">{eco.loading ? 'Loading…' : 'No releases for this currency in the free consensus calendar this week.'}</p> : (
            <table className="w-full text-[11px]"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Date</th><th className="text-left font-normal">Release</th><th className="text-right font-normal">Actual</th><th className="text-right font-normal">Cons.</th><th className="text-right font-normal">Prev.</th></tr></thead>
              <tbody>{eco.data.events.map((e: any, i: number) => (
                <tr key={i} className="border-t border-border-subtle"><td className="py-0.5 font-mono text-text-tertiary">{String(e.date).slice(5, 16).replace('T', ' ')}</td>
                  <td className="text-text-primary">{e.title}</td><td className="text-right font-mono">{e.actual ?? ''}</td><td className="text-right font-mono text-text-secondary">{e.forecast ?? ''}</td>
                  <td className="text-right font-mono text-text-tertiary">{e.previous ?? ''}</td></tr>))}</tbody></table>)}
        </Panel>
      </div>
    </div>
  );
}

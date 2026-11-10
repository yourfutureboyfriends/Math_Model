// FLOW — where money is moving. A world map of cross-border flows (US Treasury TIC portfolio
// flows into and out of the US, BIS bank lending, country-ETF money flow), then asset-class and
// sector fund flows, stablecoin supply and Fed net liquidity. Every number shown here; nothing
// links out.
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { NUMERIC_TO_ISO2 } from '@/lib/topo';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, Loading, Panel, useJSON } from './shared';

import {atlasGeometry} from './atlasGeometry';
import {countryFlowValues,type FlowLayer} from './flowModel';
import {DisclosedCapital} from './DisclosedCapital';
import { FlowMap } from './FlowMap';

type Layer = FlowLayer;
const LAYERS: [Layer, string, string][] = [
  ['into_us', 'Foreign buying of US securities', 'Net purchases of US securities by reporting/custody country (TIC). Financial centres are not verified end-investor domiciles. Arrows are schematic, not wire-transfer routes.'],
  ['out_of_us', 'US money going abroad', 'US investors’ net purchases of each country’s bonds and stocks (TIC). Arrows: money out of the US.'],
  ['bis', 'Cross-border bank lending', 'Change in all banks’ cross-border claims on each country, exchange-rate adjusted (BIS).'],
  ['etf', 'ETF share-issuance estimates', 'Estimated fund creations/redemptions from share-count snapshots. Country ETF exposure is not evidence of cross-border destination or end-investor identity.'],
  ['pressure', 'Trading pressure · proxy', 'Price/volume pressure only: a dimensionless indicator, not money entering a fund or country.'],
];
const IN_TYPES: [string, string][] = [['total', 'All'], ['treasuries', 'Treasuries'], ['agency', 'Agency'], ['corp_bonds', 'Corp bonds'], ['stocks', 'Stocks']];
const OUT_TYPES: [string, string][] = [['total', 'All'], ['govt_bonds', 'Gov’t bonds'], ['corp_bonds', 'Corp bonds'], ['stocks', 'Stocks']];
const WINDOWS: [('m1' | 'm3' | 'm12'), string][] = [['m1', 'Latest month'], ['m3', '3 months'], ['m12', '12 months']];

const usd = (mn: number | null | undefined, unit: 'mn' | 'usd' | 'bn' = 'mn') => {
  if (mn == null || !Number.isFinite(mn)) return '—';
  const v = unit === 'mn' ? mn * 1e6 : unit === 'bn' ? mn * 1e9 : mn;
  const a = Math.abs(v), s = v < 0 ? '−' : '+';
  return `${s}$${a >= 1e12 ? `${(a / 1e12).toFixed(2)}T` : a >= 1e9 ? `${(a / 1e9).toFixed(1)}B` : a >= 1e6 ? `${(a / 1e6).toFixed(0)}M` : `${(a / 1e3).toFixed(0)}K`}`;
};

export function FlowView({ onOpen }: { onOpen: (s: string) => void }) {
  const [layer, setLayer] = useState<Layer>('into_us');
  const [kind, setKind] = useState('total');
  const [win, setWin] = useState<'m1' | 'm3' | 'm12'>('m3');
  const [sel, setSel] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [motion,setMotion]=useState(true);
  const map=useJSON<import('@/lib/topo').Topology>('/world-atlas/countries-50m.json');
  const topo=map.data;
  const geo = useMemo(() => (topo ? atlasGeometry(topo) : null), [topo]);

  const tic = useJSON<any>('/api/v1/mkt/flow/tic');
  const bis = useJSON<any>(layer === 'bis' ? '/api/v1/mkt/flow/bis' : null);
  const etf = useJSON<any>('/api/v1/mkt/flow/etf', 1_800_000);
  const crypto = useJSON<any>('/api/v1/mkt/flow/crypto', 3_600_000);
  const liq = useJSON<any>('/api/v1/mkt/flow/liquidity', 3_600_000);

  // value per country for the chosen layer
  const values = useMemo(()=>countryFlowValues(layer,tic.data,bis.data,etf.data,win,kind),[layer,tic.data,bis.data,etf.data,win,kind]);
  const vals = Object.values(values).map(Math.abs).sort((a, b) => a - b);
  const max = vals.length ? vals[Math.floor(vals.length * 0.95)] || vals[vals.length - 1] : 0;
  const fmtV = (v: number | null | undefined) => (layer === 'pressure' ? (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}`) : usd(v, layer === 'etf' ? 'usd' : 'mn'));

  const shapeOf = useMemo(() => {
    const m: Record<string, any> = {};
    for (const s of geo?.shapes ?? []) { const iso = NUMERIC_TO_ISO2[s.id]; if (iso && (!m[iso] || s.area > m[iso].area)) m[iso] = s; }
    return m;
  }, [geo]);
  const ranked = Object.entries(values).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const nameOf = (iso: string) => tic.data?.into_us?.find((c: any) => c.iso2 === iso)?.name ?? shapeOf[iso]?.name ?? iso;
  const desc = LAYERS.find((l) => l[0] === layer)!;
  const loading = (layer === 'bis' ? bis : (layer === 'etf' || layer === 'pressure') ? etf : tic);

  return (
    <div className="space-y-4">
      <section className="p-5 rounded-xl border border-border bg-gradient-to-br from-surface-2 to-surface-1"><div className="text-[10px] uppercase tracking-[.2em] text-bloomberg">Capital intelligence</div><h1 className="text-xl font-semibold mt-1">Follow disclosed capital, not just prices</h1><p className="text-xs text-text-secondary mt-2 max-w-3xl">Cross-border securities transactions, bank-credit changes, estimated ETF issuance and insider disclosures. Each layer keeps its own unit, observation period and evidence standard.</p><div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mt-4">{[['TIC observation',tic.data?.latest??'Awaiting source'],['Countries in selected layer',String(Object.keys(values).length)],['ETF snapshot dates',String(etf.data?.snapshots??0)],['Evidence standard','Reported / estimated / proxy']].map(([l,v])=><div key={l} className="border border-border rounded-lg p-3 bg-surface-1/70"><div className="text-[10px] text-text-tertiary">{l}</div><div className="text-xs font-mono mt-1">{v}</div></div>)}</div></section>
      <div className="mkt-controls flex flex-wrap items-center gap-1 text-[11px]">
        {LAYERS.map(([k, l]) => <button key={k} onClick={() => { setLayer(k); setKind('total'); }} className={cn('px-2 py-0.5 border', layer === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{l}</button>)}
        {(layer === 'into_us' || layer === 'out_of_us') && <>
          <span className="mx-1 text-text-tertiary">|</span>
          {(layer === 'into_us' ? IN_TYPES : OUT_TYPES).map(([k, l]) => <button key={k} onClick={() => setKind(k)} className={cn('px-1.5 py-0.5 border', kind === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>)}
          <span className="mx-1 text-text-tertiary">|</span>
          {WINDOWS.map(([k, l]) => <button key={k} onClick={() => setWin(k)} className={cn('px-1.5 py-0.5 border', win === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>)}
        </>}
      </div>
      <div className="text-[11px] text-text-secondary">{desc[2]}{layer === 'into_us' || layer === 'out_of_us' ? ` Data to ${tic.data?.latest ?? '…'}.` : layer === 'bis' ? ` Quarter: ${bis.data?.quarter ?? '…'}.` : ''}</div>
      {loading.error && !loading.data && <ErrorBox msg={loading.error} />}
      <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_360px] gap-3">
        <div className="relative overflow-hidden rounded-xl border border-border bg-surface-1">
          {map.error&&<ErrorBox msg={map.error} onRetry={map.retry}/>}
          {(!geo&&!map.error || (loading.loading && !loading.data)) && <Loading label="Loading flows…" />}
          {geo && <FlowMap layer={layer} values={values} max={max} selected={sel} onSelect={setSel} onHover={setHover} nameOf={nameOf} fmtV={fmtV} animate={motion} />}
          <button onClick={()=>setMotion(!motion)} aria-pressed={motion} className="absolute top-2 left-[104px] z-10 h-7 bg-surface-1/90 border border-border rounded-md text-[10px] px-2">{motion?'Pause flows':'Animate flows'}</button>
          {hover && <div className="absolute top-3 right-3 z-10 pointer-events-none px-3 py-2 text-xs rounded-lg bg-surface-1/95 border border-border font-mono">{nameOf(hover)}: {fmtV(values[hover])}</div>}
          <div className="absolute bottom-2 left-2 text-[10px] bg-surface-1/85 border border-border px-2 py-1 flex items-center gap-2">
            <span className="w-16 h-2" style={{ background: 'linear-gradient(90deg, rgb(var(--c-red)), rgb(var(--c-surface-3)), rgb(var(--c-green)))' }} />
            <span className="text-text-secondary">{layer === 'into_us' ? 'selling ← → buying US assets' : layer === 'out_of_us' ? 'US selling ← → US buying there' : layer === 'bis' ? 'less ← bank lending → more' : layer === 'etf' ? 'redemptions ← → estimated issuance · USD' : 'selling ← pressure index (1M) → buying'}</span>
          </div>
        </div>
        <div className="space-y-2 min-w-0">
          {sel ? <CountryFlows iso={sel} name={nameOf(sel)} values={values} fmtV={fmtV} etf={etf.data} bis={bis.data} onClose={() => setSel(null)} onOpen={onOpen} />
            : <Ranked ranked={ranked} fmtV={fmtV} nameOf={nameOf} onPick={setSel} />}
        </div>
      </div>
      {(layer==='etf' || layer==='pressure') && <p className="text-xs text-text-tertiary">{layer==='etf'?'Missing or unverified share-count estimates stay blank. No price/volume proxy is substituted for dollars. A one-week estimate requires a baseline snapshot 7–10 calendar days before the latest snapshot.':'Trading pressure describes turnover on up versus down days. It does not reveal buyer identity, institutional ownership or net cash entering the fund.'}</p>}
      {tic.data && <UsTotals d={tic.data} />}
      <DisclosedCapital onOpen={onOpen}/>
      <FlowDivergences rows={etf.data?.rows??[]} onOpen={onOpen}/>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <EtfTable title="Asset-class flows" rows={(etf.data?.rows ?? []).filter((r: any) => r.group === 'asset')} note={etf.data?.note} snaps={etf.data?.snapshots} first={etf.data?.first_snapshot} onOpen={onOpen} loading={etf.loading && !etf.data} />
        <EtfTable title="Sector rotation" rows={(etf.data?.rows ?? []).filter((r: any) => r.group === 'sector')} snaps={etf.data?.snapshots} first={etf.data?.first_snapshot} onOpen={onOpen} loading={etf.loading && !etf.data} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Liquidity d={liq.data} error={liq.error} />
        <Stablecoins d={crypto.data} error={crypto.error} />
      </div>
    </div>
  );
}

function FlowDivergences({rows,onOpen}:{rows:any[];onOpen:(s:string)=>void}){
 const candidates=rows.filter(r=>r.flows?.quality==='estimated'&&r.flows?.week_usd!=null&&r.flows?.price_change_same_window!=null&&r.flows.week_usd*r.flows.price_change_same_window<0).sort((a,b)=>Math.abs(b.flows.week_pct_start_aum)-Math.abs(a.flows.week_pct_start_aum)).slice(0,6);
 return <Panel title="Price versus share issuance · research watchlist">
  <p className="text-xs text-text-tertiary mb-3">Funds where price and estimated issuance moved in opposite directions over the snapshot window. Ranked by flow relative to starting fund size, not a buy/sell score. These are not verified institutional orders.</p>
  {candidates.length?<div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">{candidates.map(r=><button key={r.symbol} onClick={()=>onOpen(r.symbol)} className="text-left border border-border rounded-lg p-3 hover:border-bloomberg"><div className="text-xs font-semibold text-bloomberg">{r.symbol} · {r.label}</div><div className="text-xs mt-2">{r.flows.week_usd>0?'Issuance while price declined':'Redemptions while price rose'}</div><div className="font-mono text-xs mt-1">{usd(r.flows.week_usd,'usd')} · {(r.flows.week_pct_start_aum*100).toFixed(2)}% of starting assets</div><div className="text-[10px] text-text-tertiary mt-1">Price {(r.flows.price_change_same_window*100).toFixed(1)}% · {r.flows.price_window?.join(' → ')}</div></button>)}</div>:<p className="text-xs text-text-secondary">No comparable divergence is available. Share-count history, a full baseline window and matching price observations are required; empty coverage is not a neutral signal.</p>}
 </Panel>;
}

function Ranked({ ranked, fmtV, nameOf, onPick }: { ranked: [string, number][]; fmtV: (v: number) => string; nameOf: (iso: string) => string; onPick: (iso: string) => void }) {
  const ins = ranked.filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 12);
  const outs = ranked.filter(([, v]) => v < 0).sort((a, b) => a[1] - b[1]).slice(0, 12);
  const m = Math.max(1, ...ranked.map(([, v]) => Math.abs(v)));
  const list = (rows: [string, number][], pos: boolean) => rows.map(([iso, v]) => (
    <button key={iso} onClick={() => onPick(iso)} className="w-full flex items-center gap-2 text-[11px] hover:bg-surface-3 px-1">
      <span className="w-28 truncate text-left text-text-primary">{nameOf(iso)}</span>
      <span className="flex-1 h-1 rounded-full bg-surface-3 overflow-hidden"><span className={cn('block h-full rounded-full', pos ? 'bg-green/80' : 'bg-red/80')} style={{ width: `${(Math.abs(v) / m) * 100}%` }} /></span>
      <span className="w-20 text-right font-mono">{fmtV(v)}</span></button>));
  return (
    <div className="border border-border bg-surface-1 p-2 space-y-2">
      <div><div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Largest inflows</div>{list(ins, true)}</div>
      <div><div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Largest outflows</div>{list(outs, false)}</div>
      <p className="text-[10px] text-text-tertiary">Click a country for its history.</p>
    </div>
  );
}

function CountryFlows({ iso, name, values, fmtV, etf, bis, onClose, onOpen }: { iso: string; name: string; values: Record<string, number>; fmtV: (v: number) => string;
  etf: any; bis: any; onClose: () => void; onOpen: (s: string) => void }) {
  const h = useJSON<any>(`/api/v1/mkt/flow/tic/${iso}`);
  const er = (etf?.rows ?? []).find((r: any) => r.group === 'country' && r.iso2 === iso);
  const br = (bis?.countries ?? []).find((c: any) => c.iso2 === iso);
  const rows = (h.data?.rows ?? []).map((r: any) => ({ date: r.date, in: r.in_total != null ? r.in_total / 1000 : null, out: r.out_total != null ? r.out_total / 1000 : null }));
  const last = h.data?.rows?.[h.data.rows.length - 1];
  return (
    <div className="border border-border bg-surface-1 p-2.5 text-xs space-y-2">
      <div className="flex justify-between"><span className="text-sm font-semibold text-text-primary">{name}</span><button onClick={onClose} className="text-text-tertiary hover:text-text-primary" aria-label="Close">×</button></div>
      <div className="text-[11px] text-text-secondary">This layer: <b className="font-mono text-text-primary">{fmtV(values[iso])}</b></div>
      {last && <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <div className="col-span-2 text-[10px] uppercase tracking-wide text-text-tertiary">{last.date}: into US securities</div>
        {IN_TYPES.slice(1).map(([k, l]) => <div key={k} className="flex justify-between"><span className="text-text-tertiary">{l}</span><span className="font-mono">{usd(last[`in_${k}`])}</span></div>)}
        <div className="col-span-2 text-[10px] uppercase tracking-wide text-text-tertiary mt-1">US money into {name}</div>
        {OUT_TYPES.slice(1).map(([k, l]) => <div key={k} className="flex justify-between"><span className="text-text-tertiary">{l}</span><span className="font-mono">{usd(last[`out_${k}`])}</span></div>)}
        <div className="col-span-2 flex justify-between border-t border-border-subtle pt-1"><span className="text-text-tertiary">Holds US long-term securities</span><span className="font-mono">{usd(last.holdings_us_securities).replace('+', '')}</span></div>
        <div className="col-span-2 flex justify-between"><span className="text-text-tertiary">of which Treasuries</span><span className="font-mono">{usd(last.holdings_treasuries).replace('+', '')}</span></div>
      </div>}
      {rows.length > 3 && <div className="mkt-chart-surface"><LineChart rows={rows} x="date" height={170} fmt={(v) => `${v.toFixed(0)}bn`} lines={[{ key: 'in', label: 'Into US securities ($bn)', color: 'rgb(var(--c-bloomberg))' }, { key: 'out', label: 'US into this country ($bn)', color: 'rgb(var(--c-blue))' }]} /></div>}
      {h.error && !h.data && <p className="text-[11px] text-text-tertiary">Not reported separately in TIC.</p>}
      {br && <div className="text-[11px] border-t border-border-subtle pt-1">Bank lending {bis.quarter}: <b className="font-mono">{usd(br.last_q)}</b> (4 quarters {usd(br.four_q)}; claims {usd(br.claims).replace('+', '')})</div>}
      {er && <div className="text-[11px] border-t border-border-subtle pt-1"><button onClick={() => onOpen(er.symbol)} className="font-mono text-bloomberg hover:underline">{er.symbol}</button> {er.label}:
        money flow 1W {er.mf_1w != null ? (er.mf_1w * 100).toFixed(0) : '—'} · 1M {er.mf_1m != null ? (er.mf_1m * 100).toFixed(0) : '—'}{er.flows?.week_usd != null ? ` · creations 1W ${usd(er.flows.week_usd, 'usd')}` : ''} · price 1M {(er.chg_1m * 100).toFixed(1)}%</div>}
    </div>
  );
}

function UsTotals({ d }: { d: any }) {
  const i = d.total_into_us ?? {}, o = d.total_out_of_us ?? {};
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-1.5">
      {[['Foreigners → US, all', i.total], ['→ Treasuries', i.treasuries], ['→ Agency', i.agency], ['→ Corp bonds', i.corp_bonds], ['→ US stocks', i.stocks],
        ['US → abroad, all', o.total], ['US → foreign bonds', o.govt_bonds == null || o.corp_bonds == null ? null : o.govt_bonds + o.corp_bonds], ['US → foreign stocks', o.stocks]].map(([k, v]) => (
        <div key={k as string} className="border border-border bg-surface-1 px-2 py-1.5"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{k}</div>
          <div className={cn('font-mono', (v as number) >= 0 ? 'text-green' : 'text-red')}>{usd(v as number)}</div><div className="text-[10px] text-text-tertiary">{d.latest}</div></div>))}
    </div>
  );
}

function EtfTable({ title, rows, note, snaps, first, onOpen, loading }: { title: string; rows: any[]; note?: string; snaps?: number; first?: string | null; onOpen: (s: string) => void; loading: boolean }) {
  const [sort, setSort] = useState<'mf_1w' | 'mf_1m' | 'chg_1m' | 'volume_surge' | 'flow'>('flow');
  const val = (r: any) => (sort === 'flow' ? r.flows?.week_usd ?? -Infinity : r[sort] ?? -Infinity);
  const sorted = [...rows].sort((a, b) => val(b) - val(a));
  const th = (k: typeof sort, l: string) => <th onClick={() => setSort(k)} className={cn('text-right font-normal px-1 cursor-pointer', sort === k && 'text-bloomberg')}>{l}</th>;
  const pressure = (v: number | null) => v == null ? '—' : <span className="inline-flex items-center gap-1 justify-end w-full">
    <span className="w-10 h-1.5 bg-surface-3 relative"><span className={cn('absolute top-0 h-full', v >= 0 ? 'left-1/2 bg-green' : 'right-1/2 bg-red')} style={{ width: `${Math.abs(v) * 50}%` }} /></span>
    <span className="w-7 text-right">{(v * 100).toFixed(0)}</span></span>;
  return (
    <Panel title={title}>
      {loading ? <Loading /> : <>
        <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-[11px] font-mono">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Fund</th>{th('flow', 'Est. issuance 1W')}{th('mf_1w', 'Pressure 1W')}{th('mf_1m', 'Pressure 1M')}{th('chg_1m', 'Price 1M')}{th('volume_surge', 'Volume ×')}</tr></thead>
          <tbody>{sorted.map((r) => (
            <tr key={r.symbol} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" onClick={() => onOpen(r.symbol)} tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}>
              <td className="py-0.5 font-sans"><span className="font-mono text-bloomberg mr-1">{r.symbol}</span><span className="text-text-secondary">{r.label}</span></td>
              <td className={cn('text-right px-1', (r.flows?.week_usd ?? 0) >= 0 ? 'text-green' : 'text-red')}>{r.flows ? usd(r.flows.week_usd, 'usd') : '—'}</td>
              <td className="px-1">{pressure(r.mf_1w)}</td><td className="px-1">{pressure(r.mf_1m)}</td>
              <td className={cn('text-right px-1', r.chg_1m >= 0 ? 'text-green' : 'text-red')}>{(r.chg_1m * 100).toFixed(1)}%</td>
              <td className={cn('text-right px-1', r.volume_surge > 1.5 ? 'text-amber' : 'text-text-secondary')}>{r.volume_surge?.toFixed(2)}</td></tr>))}</tbody>
        </table></div>
        <div className="text-[10px] text-text-tertiary mt-1">{(snaps ?? 0) < 2 ? `Weekly estimates require share snapshots spanning at least seven days (recording since ${first ?? 'today'}). ` : ''}{note}</div>
      </>}
    </Panel>
  );
}

function Liquidity({ d, error }: { d: any; error: string | null }) {
  return (
    <Panel title="Fed liquidity proxy — balance sheet less TGA and reverse repo">
      {error && !d && <ErrorBox msg={error} />}
      {!d && !error && <Loading />}
      {d && <>
        <div className="grid grid-cols-4 gap-1.5 text-[11px] mb-2">
          {[['Net liquidity', `$${(d.latest.net_liquidity / 1000).toFixed(2)}T`], ['4 weeks', usd(d.chg_4w, 'bn')], ['13 weeks', usd(d.chg_13w, 'bn')], ['As of', d.latest.date]].map(([k, v]) => (
            <div key={k}><div className="text-text-tertiary">{k}</div><div className="font-mono text-text-primary">{v}</div></div>))}
        </div>
        <div className="mkt-chart-surface"><LineChart rows={d.rows} x="date" height={220} fmt={(v) => `${(v / 1000).toFixed(2)}T`}
          lines={[{ key: 'net_liquidity', label: 'Net liquidity', color: 'rgb(var(--c-bloomberg))' }, { key: 'fed_balance_sheet', label: 'Fed balance sheet', color: 'rgb(var(--c-blue))' },
            { key: 'tga', label: 'Treasury cash (TGA)', color: 'rgb(var(--c-red))' }, { key: 'reverse_repo', label: 'Reverse repo', color: 'rgb(var(--c-amber))' }]} /></div>
        <div className="text-[10px] text-text-tertiary">{d.note} {d.source}.</div>
      </>}
    </Panel>
  );
}

function Stablecoins({ d, error }: { d: any; error: string | null }) {
  return (
    <Panel title="Crypto money flows — stablecoin supply">
      {error && !d && <ErrorBox msg={error} />}
      {!d && !error && <Loading />}
      {d && <>
        <div className="grid grid-cols-4 gap-1.5 text-[11px] mb-2">
          {[['Supply', `$${(d.total / 1e9).toFixed(1)}B`], ['7 days', usd(d.chg_7d, 'usd')], ['30 days', usd(d.chg_30d, 'usd')], ['90 days', usd(d.chg_90d, 'usd')]].map(([k, v]) => (
            <div key={k}><div className="text-text-tertiary">{k}</div><div className="font-mono text-text-primary">{v}</div></div>))}
        </div>
        <div className="mkt-chart-surface"><LineChart rows={d.history.map((h: any) => ({ date: h.date, usd: h.usd / 1e9 }))} x="date" height={150} fmt={(v) => `$${v.toFixed(0)}B`} lines={[{ key: 'usd', label: 'Stablecoin supply ($bn)', color: 'rgb(var(--c-green))' }]} /></div>
        <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-[11px] font-mono mt-2">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Chain</th><th className="text-right font-normal">Supply</th><th className="text-right font-normal">7 days</th><th className="text-right font-normal">30 days</th></tr></thead>
          <tbody>{d.chains.slice(0, 10).map((c: any) => (
            <tr key={c.chain} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-primary">{c.chain}</td><td className="text-right">${(c.usd / 1e9).toFixed(1)}B</td>
              <td className={cn('text-right', (c.chg_7d ?? 0) >= 0 ? 'text-green' : 'text-red')}>{usd(c.chg_7d, 'usd')}</td><td className={cn('text-right', (c.chg_30d ?? 0) >= 0 ? 'text-green' : 'text-red')}>{usd(c.chg_30d, 'usd')}</td></tr>))}</tbody>
        </table></div>
        <div className="text-[10px] text-text-tertiary mt-1">{d.note} {d.source}.</div>
      </>}
    </Panel>
  );
}

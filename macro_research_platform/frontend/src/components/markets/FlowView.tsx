// FLOW — where money is moving. A world map of cross-border flows (US Treasury TIC portfolio
// flows into and out of the US, BIS bank lending, country-ETF money flow), then asset-class and
// sector fund flows, stablecoin supply and Fed net liquidity. Every number shown here; nothing
// links out.
import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { countryPaths, projectPoint, NUMERIC_TO_ISO2, type Topology } from '@/lib/topo';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, Loading, Panel, useJSON } from './shared';

let topoCache: Topology | null = null;
const W = 1000;

type Layer = 'into_us' | 'out_of_us' | 'bis' | 'etf';
const LAYERS: [Layer, string, string][] = [
  ['into_us', 'Foreign buying of US securities', 'Each country’s investors’ net purchases of US Treasuries, bonds and stocks (TIC). Arrows: money into the US.'],
  ['out_of_us', 'US money going abroad', 'US investors’ net purchases of each country’s bonds and stocks (TIC). Arrows: money out of the US.'],
  ['bis', 'Cross-border bank lending', 'Change in all banks’ cross-border claims on each country, exchange-rate adjusted (BIS).'],
  ['etf', 'Equity money flow (country ETFs)', 'Price × volume pressure in each country’s US-listed ETF, and fund creations/redemptions once recorded.'],
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
const flowColor = (v: number | null | undefined, max: number) => {
  if (v == null || !max) return 'rgb(var(--c-surface-3) / 0.7)';
  const k = Math.min(1, Math.sqrt(Math.abs(v) / max));
  return v >= 0 ? `rgb(var(--c-green) / ${0.1 + 0.5 * k})` : `rgb(var(--c-red) / ${0.1 + 0.5 * k})`;
};

export function FlowView({ onOpen }: { onOpen: (s: string) => void }) {
  const [layer, setLayer] = useState<Layer>('into_us');
  const [kind, setKind] = useState('total');
  const [win, setWin] = useState<'m1' | 'm3' | 'm12'>('m3');
  const [sel, setSel] = useState<string | null>(null);
  const [hover, setHover] = useState<{ iso: string; x: number; y: number } | null>(null);
  const [topo, setTopo] = useState<Topology | null>(topoCache);
  useEffect(() => { if (!topo) fetch('/world-atlas/countries-50m.json').then((r) => r.json()).then((t) => { topoCache = t; setTopo(t); }).catch(() => {}); }, [topo]);
  const geo = useMemo(() => (topo ? countryPaths(topo, W) : null), [topo]);
  const H = W * 0.487;

  const tic = useJSON<any>('/api/v1/mkt/flow/tic');
  const bis = useJSON<any>(layer === 'bis' ? '/api/v1/mkt/flow/bis' : null);
  const etf = useJSON<any>('/api/v1/mkt/flow/etf', 1_800_000);
  const crypto = useJSON<any>('/api/v1/mkt/flow/crypto', 3_600_000);
  const liq = useJSON<any>('/api/v1/mkt/flow/liquidity', 3_600_000);

  // value per country for the chosen layer
  const values: Record<string, number> = useMemo(() => {
    const out: Record<string, number> = {};
    if (layer === 'into_us' || layer === 'out_of_us') {
      for (const c of tic.data?.[layer] ?? []) { const v = c[win]?.[kind]; if (v != null) out[c.iso2] = v; }
    } else if (layer === 'bis') {
      for (const c of bis.data?.countries ?? []) if (c.last_q != null) out[c.iso2] = c.last_q;
    } else {
      for (const r of etf.data?.rows ?? []) if (r.group === 'country' && r.iso2) out[r.iso2] = r.flows?.week_usd ?? r.mf_1m;
    }
    return out;
  }, [layer, tic.data, bis.data, etf.data, win, kind]);
  const etfUsesFlows = layer === 'etf' && (etf.data?.rows ?? []).some((r: any) => r.flows?.week_usd != null);
  const vals = Object.values(values).map(Math.abs).sort((a, b) => a - b);
  const max = vals.length ? vals[Math.floor(vals.length * 0.95)] || vals[vals.length - 1] : 0;
  const fmtV = (v: number | null | undefined) => (layer === 'etf' && !etfUsesFlows ? (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}`) : usd(v, layer === 'etf' ? 'usd' : 'mn'));

  const shapeOf = useMemo(() => {
    const m: Record<string, any> = {};
    for (const s of geo?.shapes ?? []) { const iso = NUMERIC_TO_ISO2[s.id]; if (iso && (!m[iso] || s.area > m[iso].area)) m[iso] = s; }
    return m;
  }, [geo]);
  const us = shapeOf.US?.centroid ?? projectPoint(-98, 39, W);
  const ranked = Object.entries(values).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const arrows = (layer === 'into_us' || layer === 'out_of_us') ? ranked.filter(([iso]) => iso !== 'US' && shapeOf[iso]).slice(0, 14) : [];
  const amax = Math.max(1, ...arrows.map(([, v]) => Math.abs(v)));
  const nameOf = (iso: string) => tic.data?.into_us?.find((c: any) => c.iso2 === iso)?.name ?? shapeOf[iso]?.name ?? iso;
  const desc = LAYERS.find((l) => l[0] === layer)!;
  const loading = (layer === 'bis' ? bis : layer === 'etf' ? etf : tic);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
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
        <div className="relative border border-border bg-surface-1">
          {(!geo || (loading.loading && !loading.data)) && <Loading label="Loading flows…" />}
          {geo && (
            <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Money flow map" onMouseLeave={() => setHover(null)}>
              <defs>
                <marker id="flow-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke" /></marker>
              </defs>
              <rect width={W} height={H} fill="rgb(var(--c-sea) / 0.07)" />
              {geo.shapes.map((s) => {
                const iso = NUMERIC_TO_ISO2[s.id];
                const v = iso ? values[iso] : undefined;
                return <path key={s.id + s.name} d={s.path} fill={iso === 'US' && (layer === 'into_us' || layer === 'out_of_us') ? 'rgb(var(--c-bloomberg) / 0.35)' : flowColor(v, max)}
                  stroke={sel && iso === sel ? 'rgb(var(--c-text-primary))' : 'rgb(var(--c-border-strong) / 0.5)'} strokeWidth={sel && iso === sel ? 1.4 : 0.35}
                  className="cursor-pointer" onClick={() => iso && setSel(iso)}
                  onMouseMove={(e) => { if (!iso) return; const b = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect(); setHover({ iso, x: e.clientX - b.left, y: e.clientY - b.top }); }} />;
              })}
              {arrows.map(([iso, v]) => {
                const [x0, y0] = shapeOf[iso].centroid as [number, number];
                const [a, b] = layer === 'into_us' ? [[x0, y0], us] : [us, [x0, y0]];
                const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2 - Math.min(160, Math.hypot(b[0] - a[0], b[1] - a[1]) * 0.28);
                const w = 0.8 + 3.6 * Math.sqrt(Math.abs(v) / amax);
                const towardUs = layer === 'into_us' ? v >= 0 : v < 0;   // a negative flow runs the other way
                return <path key={iso} d={`M${(towardUs ? a : b)[0]},${(towardUs ? a : b)[1]} Q${mx},${my} ${(towardUs ? b : a)[0]},${(towardUs ? b : a)[1]}`}
                  fill="none" stroke={v >= 0 ? 'rgb(var(--c-green) / 0.85)' : 'rgb(var(--c-red) / 0.8)'} strokeWidth={w} strokeLinecap="round" markerEnd="url(#flow-arrow)"
                  className="flow-dash"><title>{`${nameOf(iso)}: ${fmtV(v)}`}</title></path>;
              })}
            </svg>)}
          {hover && <div className="absolute pointer-events-none px-2 py-1 text-[11px] bg-surface-1/95 border border-border font-mono" style={{ left: Math.min(hover.x + 12, 700), top: hover.y + 10 }}>
            {nameOf(hover.iso)}: {fmtV(values[hover.iso])}</div>}
          <div className="absolute bottom-2 left-2 text-[10px] bg-surface-1/85 border border-border px-2 py-1 flex items-center gap-2">
            <span className="w-16 h-2" style={{ background: 'linear-gradient(90deg, rgb(var(--c-red)), rgb(var(--c-surface-3)), rgb(var(--c-green)))' }} />
            <span className="text-text-secondary">{layer === 'into_us' ? 'selling ← → buying US assets' : layer === 'out_of_us' ? 'US selling ← → US buying there' : layer === 'bis' ? 'less ← bank lending → more' : etfUsesFlows ? 'redemptions ← → creations (1 week)' : 'selling ← pressure (1M) → buying'}</span>
          </div>
        </div>
        <div className="space-y-2 min-w-0">
          {sel ? <CountryFlows iso={sel} name={nameOf(sel)} values={values} fmtV={fmtV} etf={etf.data} bis={bis.data} onClose={() => setSel(null)} onOpen={onOpen} />
            : <Ranked ranked={ranked} fmtV={fmtV} nameOf={nameOf} onPick={setSel} />}
        </div>
      </div>
      {tic.data && <UsTotals d={tic.data} />}
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
      {rows.length > 3 && <LineChart rows={rows} x="date" height={170} fmt={(v) => `${v.toFixed(0)}bn`} lines={[{ key: 'in', label: 'Into US securities ($bn)', color: 'rgb(var(--c-bloomberg))' }, { key: 'out', label: 'US into this country ($bn)', color: 'rgb(var(--c-blue))' }]} />}
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
        ['US → abroad, all', o.total], ['US → foreign bonds', (o.govt_bonds ?? 0) + (o.corp_bonds ?? 0)], ['US → foreign stocks', o.stocks]].map(([k, v]) => (
        <div key={k as string} className="border border-border bg-surface-1 px-2 py-1.5"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{k}</div>
          <div className={cn('font-mono', (v as number) >= 0 ? 'text-green' : 'text-red')}>{usd(v as number)}</div><div className="text-[10px] text-text-tertiary">{d.latest}</div></div>))}
    </div>
  );
}

function EtfTable({ title, rows, note, snaps, first, onOpen, loading }: { title: string; rows: any[]; note?: string; snaps?: number; first?: string | null; onOpen: (s: string) => void; loading: boolean }) {
  const [sort, setSort] = useState<'mf_1w' | 'mf_1m' | 'chg_1m' | 'volume_surge' | 'flow'>('mf_1m');
  const val = (r: any) => (sort === 'flow' ? r.flows?.week_usd ?? r.flows?.last_usd ?? -Infinity : r[sort] ?? -Infinity);
  const sorted = [...rows].sort((a, b) => val(b) - val(a));
  const th = (k: typeof sort, l: string) => <th onClick={() => setSort(k)} className={cn('text-right font-normal px-1 cursor-pointer', sort === k && 'text-bloomberg')}>{l}</th>;
  const pressure = (v: number | null) => v == null ? '—' : <span className="inline-flex items-center gap-1 justify-end w-full">
    <span className="w-10 h-1.5 bg-surface-3 relative"><span className={cn('absolute top-0 h-full', v >= 0 ? 'left-1/2 bg-green' : 'right-1/2 bg-red')} style={{ width: `${Math.abs(v) * 50}%` }} /></span>
    <span className="w-7 text-right">{(v * 100).toFixed(0)}</span></span>;
  return (
    <Panel title={title}>
      {loading ? <Loading /> : <>
        <table className="w-full text-[11px] font-mono">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Fund</th>{th('flow', 'Creations')}{th('mf_1w', 'Flow 1W')}{th('mf_1m', 'Flow 1M')}{th('chg_1m', 'Price 1M')}{th('volume_surge', 'Volume ×')}</tr></thead>
          <tbody>{sorted.map((r) => (
            <tr key={r.symbol} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" onClick={() => onOpen(r.symbol)}>
              <td className="py-0.5 font-sans"><span className="font-mono text-bloomberg mr-1">{r.symbol}</span><span className="text-text-secondary">{r.label}</span></td>
              <td className={cn('text-right px-1', (r.flows?.week_usd ?? r.flows?.last_usd ?? 0) >= 0 ? 'text-green' : 'text-red')}>{r.flows ? usd(r.flows.week_usd ?? r.flows.last_usd, 'usd') : '—'}</td>
              <td className="px-1">{pressure(r.mf_1w)}</td><td className="px-1">{pressure(r.mf_1m)}</td>
              <td className={cn('text-right px-1', r.chg_1m >= 0 ? 'text-green' : 'text-red')}>{(r.chg_1m * 100).toFixed(1)}%</td>
              <td className={cn('text-right px-1', r.volume_surge > 1.5 ? 'text-amber' : 'text-text-secondary')}>{r.volume_surge?.toFixed(2)}</td></tr>))}</tbody>
        </table>
        <div className="text-[10px] text-text-tertiary mt-1">{(snaps ?? 0) < 2 ? `Creations/redemptions appear after two daily share snapshots (recording since ${first ?? 'today'}). ` : ''}{note}</div>
      </>}
    </Panel>
  );
}

function Liquidity({ d, error }: { d: any; error: string | null }) {
  return (
    <Panel title="Fed net liquidity — dollars the Fed system leaves in markets">
      {error && !d && <ErrorBox msg={error} />}
      {!d && !error && <Loading />}
      {d && <>
        <div className="grid grid-cols-4 gap-1.5 text-[11px] mb-2">
          {[['Net liquidity', `$${(d.latest.net_liquidity / 1000).toFixed(2)}T`], ['4 weeks', usd(d.chg_4w, 'bn')], ['13 weeks', usd(d.chg_13w, 'bn')], ['As of', d.latest.date]].map(([k, v]) => (
            <div key={k}><div className="text-text-tertiary">{k}</div><div className="font-mono text-text-primary">{v}</div></div>))}
        </div>
        <LineChart rows={d.rows} x="date" height={220} fmt={(v) => `${(v / 1000).toFixed(2)}T`}
          lines={[{ key: 'net_liquidity', label: 'Net liquidity', color: 'rgb(var(--c-bloomberg))' }, { key: 'fed_balance_sheet', label: 'Fed balance sheet', color: 'rgb(var(--c-blue))' },
            { key: 'tga', label: 'Treasury cash (TGA)', color: 'rgb(var(--c-red))' }, { key: 'reverse_repo', label: 'Reverse repo', color: 'rgb(var(--c-amber))' }]} />
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
        <LineChart rows={d.history.map((h: any) => ({ date: h.date, usd: h.usd / 1e9 }))} x="date" height={150} fmt={(v) => `$${v.toFixed(0)}B`} lines={[{ key: 'usd', label: 'Stablecoin supply ($bn)', color: 'rgb(var(--c-green))' }]} />
        <table className="w-full text-[11px] font-mono mt-2">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Chain</th><th className="text-right font-normal">Supply</th><th className="text-right font-normal">7 days</th><th className="text-right font-normal">30 days</th></tr></thead>
          <tbody>{d.chains.slice(0, 10).map((c: any) => (
            <tr key={c.chain} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-primary">{c.chain}</td><td className="text-right">${(c.usd / 1e9).toFixed(1)}B</td>
              <td className={cn('text-right', (c.chg_7d ?? 0) >= 0 ? 'text-green' : 'text-red')}>{usd(c.chg_7d, 'usd')}</td><td className={cn('text-right', (c.chg_30d ?? 0) >= 0 ? 'text-green' : 'text-red')}>{usd(c.chg_30d, 'usd')}</td></tr>))}</tbody>
        </table>
        <div className="text-[10px] text-text-tertiary mt-1">{d.note} {d.source}.</div>
      </>}
    </Panel>
  );
}

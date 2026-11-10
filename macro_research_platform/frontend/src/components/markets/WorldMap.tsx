// MAP — every country coloured by markets, economy, policy or risk. Markets: USD country-ETF
// returns, local indices, currencies, 10-year yields. Economy: IMF World Economic Outlook.
// Policy: the Research mode's central-bank model. Risk: Damodaran sovereign ratings and
// country risk premiums. Cached cartography, region presets, ranking and country details.
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { NUMERIC_TO_ISO2 as FALLBACK_NUMERIC, type Topology } from '@/lib/topo';
import { Chg, ErrorBox, fmtPct, fmtPrice, Loading, useJSON } from './shared';
import { Globe3D } from './Globe3D';
import { LiveTV } from './LiveTV';
import { EXCHANGES, exchangeById } from './exchanges';
import { atlasGeometry } from './atlasGeometry';
import { AtlasMap2D, type AtlasMapHandle } from './AtlasMap2D';

type Fmt = 'pct' | 'pctpt' | 'pp' | 'bp' | 'usd' | 'ratio';
type Layer = { key: string; group: 'Markets' | 'Economy' | 'Policy' | 'Risk'; label: string; get: (c: any) => number | null | undefined;
  fmt: Fmt; diverging: boolean; goodHigh: boolean; help: string };

const L: Layer[] = [
  { key: 'd1', group: 'Markets', label: 'Stocks today', get: (c) => c.change_1d, fmt: 'pct', diverging: true, goodHigh: true, help: '1-day move of the MSCI country ETF, in USD.' },
  { key: 'm1', group: 'Markets', label: 'Stocks 1M', get: (c) => c.change_1m, fmt: 'pct', diverging: true, goodHigh: true, help: '1-month return in USD.' },
  { key: 'ytd', group: 'Markets', label: 'Stocks YTD', get: (c) => c.change_ytd, fmt: 'pct', diverging: true, goodHigh: true, help: 'Year-to-date return in USD (comparable across countries).' },
  { key: 'y1', group: 'Markets', label: 'Stocks 1Y', get: (c) => c.change_1y, fmt: 'pct', diverging: true, goodHigh: true, help: '12-month return in USD.' },
  { key: 'idx', group: 'Markets', label: 'Local index today', get: (c) => c.index?.change_1d, fmt: 'pct', diverging: true, goodHigh: true, help: 'Main local index, in local currency.' },
  { key: 'idxytd', group: 'Markets', label: 'Local index YTD', get: (c) => c.index?.change_ytd, fmt: 'pct', diverging: true, goodHigh: true, help: 'Main local index year to date, local currency.' },
  { key: 'fx1d', group: 'Markets', label: 'Currency today', get: (c) => c.fx?.change_1d, fmt: 'pct', diverging: true, goodHigh: true, help: 'Currency vs the US dollar today (+ = stronger).' },
  { key: 'fxytd', group: 'Markets', label: 'Currency YTD', get: (c) => c.fx?.change_ytd, fmt: 'pct', diverging: true, goodHigh: true, help: 'Currency vs the US dollar this year (+ = stronger).' },
  { key: 'y10', group: 'Markets', label: '10Y yield', get: (c) => c.yield_10y, fmt: 'pctpt', diverging: false, goodHigh: false, help: '10-year government bond yield — issuers\' daily data for the US, DE, UK, JP, CA and AU; OECD monthly averages elsewhere.' },
  { key: 'gdp', group: 'Economy', label: 'GDP growth', get: (c) => c.gdp_growth, fmt: 'pctpt', diverging: true, goodHigh: true, help: 'Real GDP growth this year — IMF World Economic Outlook.' },
  { key: 'gdpn', group: 'Economy', label: 'GDP growth next yr', get: (c) => c.gdp_growth_next, fmt: 'pctpt', diverging: true, goodHigh: true, help: 'IMF projection for next year.' },
  { key: 'cpi', group: 'Economy', label: 'Inflation', get: (c) => c.inflation, fmt: 'pctpt', diverging: false, goodHigh: false, help: 'Consumer price inflation this year — IMF.' },
  { key: 'ur', group: 'Economy', label: 'Unemployment', get: (c) => c.unemployment, fmt: 'pctpt', diverging: false, goodHigh: false, help: 'Unemployment rate — IMF.' },
  { key: 'debt', group: 'Economy', label: 'Govt debt / GDP', get: (c) => c.gov_debt, fmt: 'pctpt', diverging: false, goodHigh: false, help: 'General government gross debt, % of GDP — IMF.' },
  { key: 'ca', group: 'Economy', label: 'Current account', get: (c) => c.current_account, fmt: 'pctpt', diverging: true, goodHigh: true, help: 'Current-account balance, % of GDP — IMF.' },
  { key: 'gdppc', group: 'Economy', label: 'GDP per person', get: (c) => c.gdp_per_capita, fmt: 'usd', diverging: false, goodHigh: true, help: 'GDP per capita, current US dollars — IMF.' },
  { key: 'policy', group: 'Policy', label: 'Policy rate', get: (c) => c.policy, fmt: 'pctpt', diverging: false, goodHigh: false, help: 'Central bank policy rate (25 economies, Macro area model).' },
  { key: 'real', group: 'Policy', label: 'Real policy rate', get: (c) => c.real_policy_rate, fmt: 'pp', diverging: true, goodHigh: true, help: 'Policy rate minus inflation — positive = restrictive.' },
  { key: 'gap', group: 'Policy', label: 'Inflation vs target', get: (c) => c.inflation_gap, fmt: 'pp', diverging: true, goodHigh: false, help: 'CPI minus the central bank’s target.' },
  { key: 'crp', group: 'Risk', label: 'Country risk premium', get: (c) => c.crp, fmt: 'pct', diverging: false, goodHigh: false, help: 'Extra equity premium for the country (Damodaran), on top of a mature market’s.' },
  { key: 'erp', group: 'Risk', label: 'Equity risk premium', get: (c) => c.erp_total, fmt: 'pct', diverging: false, goodHigh: false, help: 'Mature-market implied ERP + country risk premium (Damodaran).' },
  { key: 'ds', group: 'Risk', label: 'Sovereign default spread', get: (c) => c.default_spread, fmt: 'pct', diverging: false, goodHigh: false, help: 'Default spread for the sovereign’s rating (Damodaran).' },
];
const GROUPS: Layer['group'][] = ['Markets', 'Economy', 'Policy', 'Risk'];
const EUROZONE = ['DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'IE', 'FI', 'PT', 'GR', 'SK', 'SI', 'LT', 'LV', 'EE', 'LU', 'MT', 'CY', 'HR'];
// region presets as lon/lat boxes
const REGIONS: [string, [number, number, number, number]][] = [
  ['World', [-180, -60, 180, 85]], ['N. America', [-170, 5, -50, 75]], ['S. America', [-95, -57, -30, 15]], ['Europe', [-25, 34, 45, 72]],
  ['Africa', [-20, -36, 55, 38]], ['Middle East', [25, 10, 65, 43]], ['Asia', [60, -12, 150, 55]], ['Oceania', [105, -48, 180, 0]],
];

// Seven colour classes per layer. Diverging layers run from weak (red) through a neutral slate to strong (green),
// flipped where lower is better; one-directional layers use a single-hue ramp — amber where high is bad (inflation,
// debt, yields), teal where high is good — so colour always reads the same way: warmer = worse.
const DIV = ['#d9534a', '#b8665e', '#7a5b5f', '#3a4757', '#3f6c64', '#37a283', '#3fd3a2'];
const SEQ_BAD = ['#2f3d50', '#4b4a52', '#6e5546', '#986441', '#c47b3a', '#e39b3f', '#f6c35b'];
const SEQ_GOOD = ['#2b3b50', '#2c4d63', '#2f6077', '#34768c', '#3d8ea2', '#4ca7b7', '#6cc6ce'];
type Classes = { colors: string[]; breaks: number[] };             // breaks: 6 thresholds between 7 classes
function classesFor(layer: Layer, lo: number, hi: number): Classes {
  if (layer.diverging) {
    const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1;
    return { colors: layer.goodHigh ? DIV : [...DIV].reverse(), breaks: [-5, -3, -1, 1, 3, 5].map((k) => (k / 7) * m) };
  }
  const span = hi - lo || 1;
  return { colors: layer.goodHigh ? SEQ_GOOD : SEQ_BAD, breaks: [1, 2, 3, 4, 5, 6].map((k) => lo + (k / 7) * span) };
}
const classOf = (v: number, c: Classes) => c.breaks.filter((b) => v >= b).length;
const FLAG = (iso: string) => (/^[A-Z]{2}$/.test(iso) ? String.fromCodePoint(...[...iso].map((ch) => 0x1f1e6 + ch.charCodeAt(0) - 65)) : '');

let topoCache: Topology | null = null;
let topoRequest: Promise<Topology> | null = null;
function loadTopology() {
  if (topoCache) return Promise.resolve(topoCache);
  if (!topoRequest) topoRequest=fetch('/world-atlas/countries-50m.json').then(r=>{
    if(!r.ok)throw new Error('Map geometry unavailable');return r.json();
  }).then((t:Topology)=>{topoCache=t;return t;}).catch(e=>{topoRequest=null;throw e;});
  return topoRequest;
}

function fmtVal(v: number | null | undefined, f: Fmt, signed = false) {
  if (v == null || !Number.isFinite(v)) return 'no data';
  const s = (x: string) => (signed && v > 0 ? '+' : '') + x;
  if (f === 'pct') return s(`${(v * 100).toFixed(Math.abs(v) < 0.1 ? 2 : 1)}%`);
  if (f === 'pctpt') return s(`${v.toFixed(1)}%`);
  if (f === 'pp') return s(`${v.toFixed(1)} pp`);
  if (f === 'bp') return s(`${v.toFixed(0)} bp`);
  if (f === 'usd') return `$${v >= 10000 ? `${(v / 1000).toFixed(0)}k` : v.toFixed(0)}`;
  return v.toFixed(2);
}

export function WorldMap({ onOpen, onGo }: { onOpen: (s: string) => void; onGo?: (fn: string, s?: string) => void }) {
  const [topo, setTopo] = useState<Topology | null>(topoCache);
  const [layer, setLayer] = useState<Layer>(L[2]);
  const [group, setGroup] = useState<Layer['group']>('Markets');
  const [hover, setHover] = useState<{ iso: string; name: string; x: number; y: number } | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<'2d' | '3d'>(() => { try { return localStorage.getItem('mkt_map_mode') === '3d' ? '3d' : '2d'; } catch { return '2d'; } });
  useEffect(() => { try { localStorage.setItem('mkt_map_mode', mode); } catch { /* storage unavailable */ } }, [mode]);
  const [showLabels,setShowLabels]=useState(false);
  const [showExchanges,setShowExchanges]=useState(true);
  const [exchangeId,setExchangeId]=useState<string|null>(null);
  const selectedExchange=exchangeById(exchangeId);
  const [coverage,setCoverage]=useState(false);
  const mapRef=useRef<AtlasMapHandle>(null);
  const [topoError,setTopoError]=useState('');
  const [retry,setRetry]=useState(0);
  const world = useJSON<any>('/api/v1/mkt/map/world', 600_000);
  const macro = useJSON<any>('/api/v1/global-macro', 3_600_000);
  useEffect(() => {
    if(topo)return;
    let active=true;
    loadTopology().then(t=>{if(active)setTopo(t);}).catch(()=>{if(active)setTopoError('Unable to load map geometry.');});
    return()=>{active=false;};
  },[topo,retry]);
  const geo=useMemo(()=>topo?atlasGeometry(topo):null,[topo]);
  const numToIso: Record<string, string> = world.data?.numeric_to_iso2 ?? FALLBACK_NUMERIC;

  // merged record per ISO-2: world data + Research-mode policy model
  const data = useMemo(() => {
    const out: Record<string, any> = {};
    for (const [iso, c] of Object.entries<any>(world.data?.countries ?? {})) out[iso] = { ...c };
    const pol: Record<string, any> = {};
    for (const e of macro.data?.economies ?? []) pol[e.code] = { policy: e.policy?.available ? e.policy.rate : null, real_policy_rate: e.real_policy_rate,
      inflation_gap: e.inflation_gap, stance: e.policy?.stance, quadrant: e.quadrant, cb: e.cb };
    if (pol.EA) for (const c of EUROZONE) if (!pol[c]) pol[c] = { ...pol.EA, euroArea: true };
    for (const [iso, p] of Object.entries(pol)) out[iso] = { ...(out[iso] ?? {}), ...p };
    return out;
  }, [world.data, macro.data]);

  const values = useMemo(() => Object.entries(data).map(([iso, c]) => [iso, layer.get(c)] as [string, number | null | undefined])
    .filter(([, v]) => v != null && Number.isFinite(v)) as [string, number][], [data, layer]);
  // colour scale from the data's own spread (5th–95th percentile), symmetric for diverging layers
  const scale = useMemo(() => {
    const vs = values.map(([, v]) => v).sort((a, b) => a - b);
    if (!vs.length) return { lo: 0, hi: 1 };
    const q = (p: number) => vs[Math.min(vs.length - 1, Math.max(0, Math.round(p * (vs.length - 1))))];
    if (layer.diverging) { const m = Math.max(Math.abs(q(0.05)), Math.abs(q(0.95))) || 1; return { lo: -m, hi: m }; }
    return { lo: q(0.05), hi: q(0.95) > q(0.05) ? q(0.95) : q(0.05) + 1 };
  }, [values, layer]);
  const classes=useMemo(()=>classesFor(layer,scale.lo,scale.hi),[layer,scale]);
  const fills=useMemo(()=>Object.fromEntries(values.map(([iso,v])=>[iso,classes.colors[classOf(v,classes)]])),[values,classes]);
  const counts=useMemo(()=>{const n=Array(7).fill(0);for(const [,v] of values)n[classOf(v,classes)]++;return n;},[values,classes]);
  const labels=useMemo(()=>Object.fromEntries(values.map(([iso,v])=>[iso,fmtVal(v,layer.fmt,layer.diverging)])),[values,layer]);
  const ranked=useMemo(()=>[...values].sort((a,b)=>b[1]-a[1]),[values]);
  const median=useMemo(()=>{const v=values.map(([,x])=>x).sort((a,b)=>a-b);return v.length?(v.length%2?v[(v.length-1)/2]:(v[v.length/2-1]+v[v.length/2])/2):null;},[values]);
  const rankOf=(iso:string)=>{const k=ranked.findIndex(([i])=>i===iso);return k<0?null:k+1;};
  const selRec = sel ? data[sel] : null;
  const selName = sel ? (selRec?.name ?? geo?.shapes.find((s) => numToIso[s.id] === sel)?.name ?? sel) : null;
  const found = query.trim().length > 1 ? Object.entries(data).filter(([iso, c]) => (c.name ?? '').toLowerCase().includes(query.trim().toLowerCase()) || iso === query.trim().toUpperCase()).slice(0, 6) : [];
  const select=(iso:string)=>{setSel(iso);setExchangeId(null);setQuery('');};
  const selectExchange=(id:string)=>{const e=exchangeById(id);if(e){setExchangeId(id);setSel(e.iso);setQuery('');setShowExchanges(true);}};
  return <div className="world-atlas space-y-3">
    <header className="atlas-heading"><div><div className="atlas-eyebrow">GLOBAL MARKETS / ATLAS</div><h2>World in perspective</h2><p>{layer.help}</p></div><span className="atlas-coverage">{values.length} economies · {layer.label}</span></header>
    <div className="atlas-toolbar">
      <div className="atlas-segments">{GROUPS.map(g=><button key={g} aria-pressed={group===g} onClick={()=>{setGroup(g);setLayer(L.find(l=>l.group===g)!);}}>{g}</button>)}</div>
      <select aria-label="Map data layer" value={layer.key} onChange={e=>setLayer(L.find(l=>l.key===e.target.value)!)}>{L.filter(l=>l.group===group).map(l=><option key={l.key} value={l.key}>{l.label}</option>)}</select>
      <div className="relative ml-auto"><input aria-label="Find a country" placeholder="Find country or ISO code…" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&found[0])select(found[0][0]);if(e.key==='Escape')setQuery('');}}/>
      {found.length>0&&<ul className="atlas-results">{found.map(([iso,c])=><li key={iso}><button onClick={()=>select(iso)}>{c.name} <span>{iso}</span></button></li>)}</ul>}</div>
    </div>
    {ranked.length>0&&<div className="atlas-summary">
      <div><span>Median</span><b>{fmtVal(median,layer.fmt,layer.diverging)}</b><small>{values.length} economies</small></div>
      <button onClick={()=>select(ranked[0][0])}><span>Highest</span><b>{FLAG(ranked[0][0])} {data[ranked[0][0]]?.name??ranked[0][0]}</b><small>{fmtVal(ranked[0][1],layer.fmt,layer.diverging)}</small></button>
      <button onClick={()=>select(ranked[ranked.length-1][0])}><span>Lowest</span><b>{FLAG(ranked[ranked.length-1][0])} {data[ranked[ranked.length-1][0]]?.name??ranked[ranked.length-1][0]}</b><small>{fmtVal(ranked[ranked.length-1][1],layer.fmt,layer.diverging)}</small></button>
      {layer.diverging&&<div><span>Above zero</span><b>{values.filter(([,v])=>v>0).length} / {values.length}</b><small>{Math.round(values.filter(([,v])=>v>0).length/values.length*100)}% of economies</small></div>}
    </div>}
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-3">
      <div className="min-w-0"><div className="atlas-stage">
        <div className="atlas-map-controls"><div className="atlas-segments">{(['2d','3d'] as const).map(m=><button key={m} aria-pressed={mode===m} onClick={()=>{setMode(m);setHover(null);}}>{m==='2d'?'Map':'Globe'}</button>)}</div>
        {mode==='2d'&&<><select aria-label="Map region" defaultValue="World" onChange={e=>{const r=REGIONS.find(r=>r[0]===e.target.value)!;if(r[0]==='World')mapRef.current?.reset();else mapRef.current?.region(r[1]);}}>{REGIONS.map(([n])=><option key={n}>{n}</option>)}</select><button aria-label="Zoom in" onClick={()=>mapRef.current?.zoom(1.4)}>+</button><button aria-label="Zoom out" onClick={()=>mapRef.current?.zoom(1/1.4)}>−</button><button onClick={()=>{mapRef.current?.reset();setExchangeId(null);setSel(null);}}>Reset</button><label><input type="checkbox" checked={showLabels} onChange={e=>setShowLabels(e.target.checked)}/> Values</label></>}
        <label><input type="checkbox" checked={showExchanges} onChange={e=>setShowExchanges(e.target.checked)}/> Exchanges</label>
        <select aria-label="Locate stock exchange" value={exchangeId??''} onChange={e=>{if(e.target.value)selectExchange(e.target.value);else setExchangeId(null);}}><option value="">Locate exchange…</option>{EXCHANGES.map(e=><option key={e.id} value={e.id}>{e.city} · {e.label}</option>)}</select>
        </div>
        {!geo&&!topoError&&<Loading label="Loading atlas…"/>}{topoError&&<div className="p-3"><ErrorBox msg={topoError}/><button className="mt-2 text-xs underline" onClick={()=>{setTopoError('');setRetry(n=>n+1);}}>Retry map</button></div>}{world.error&&!world.data&&<ErrorBox msg={world.error}/>}
        {geo&&mode==='2d'&&<AtlasMap2D ref={mapRef} showExchanges={showExchanges} focusedExchange={exchangeId} onExchange={selectExchange} geo={geo} numToIso={numToIso} fills={fills} selected={sel} labels={labels} showLabels={showLabels} title={`World map: ${layer.label}`} onSelect={select} onHover={setHover}/>}
        {geo&&topo&&mode==='3d'&&<Globe3D onReset={()=>{setExchangeId(null);setSel(null);}} showExchanges={showExchanges} focusedExchange={exchangeId} onExchange={selectExchange} topo={topo} numToIso={numToIso} height={460} selected={sel} fill={iso=>iso?fills[iso]??'#263444':'#263444'} onSelect={select} onHover={setHover}/>}
        {hover&&<div className="atlas-tooltip"><strong>{hover.name}</strong><span>{layer.label} <b>{labels[hover.iso]??'No data'}</b></span></div>}
        <div className="atlas-map-caption">{mode==='2d'?'EQUAL EARTH':'ORTHOGRAPHIC'} / {mode==='2d'?'Drag to pan · Ctrl/⌘ + scroll to zoom':'Drag to rotate · Ctrl/⌘ + scroll to zoom'}</div>
      </div>
      <div className="atlas-classes" role="list" aria-label={`Colour key for ${layer.label}`}>
        {classes.colors.map((col,k)=>{const lo=k?classes.breaks[k-1]:null,hi=k<6?classes.breaks[k]:null;
          return <div key={k} role="listitem" className="atlas-class" title={`${counts[k]} economies`}><i style={{background:col}}/><span>{lo==null?`< ${fmtVal(hi,layer.fmt,layer.diverging)}`:hi==null?`≥ ${fmtVal(lo,layer.fmt,layer.diverging)}`:`${fmtVal(lo,layer.fmt,layer.diverging)} – ${fmtVal(hi,layer.fmt,layer.diverging)}`}</span><small>{counts[k]}</small></div>;})}
        <div className="atlas-class" role="listitem"><i className="atlas-no-data-key"/><span>No data</span></div>
      </div>
      <p className="text-[10px] text-text-tertiary mt-2">{layer.diverging?(layer.goodHigh?'Green = higher, red = lower, slate ≈ zero.':'Green = lower (better), red = higher, slate ≈ zero.'):(layer.goodHigh?'Brighter teal = higher.':'Brighter amber = higher (worse).')} Seven classes spanning the 5th–95th percentile{layer.diverging?', centred on zero':''}; numbers on each key are the class range and how many economies fall in it. Gold dots: major exchanges. Colour shows magnitude, not an investment rating.</p></div>
      <aside className="space-y-3">{selectedExchange&&<div className="atlas-panel atlas-exchange-detail"><div className="atlas-eyebrow">EXCHANGE LOCATION</div><h3>{selectedExchange.label}</h3><p>{selectedExchange.name}</p><p>{selectedExchange.city} · {selectedExchange.iso} · city-level marker</p><a href={selectedExchange.url} target="_blank" rel="noopener noreferrer">Official exchange website ↗</a></div>}<div className="atlas-panel p-3 space-y-2 text-xs">{sel&&selRec?<CountryPanel iso={sel} name={selName!} c={selRec} onOpen={onOpen} onGo={onGo}
        focus={{label:layer.label,value:fmtVal(layer.get(selRec),layer.fmt,layer.diverging),rank:rankOf(sel),of:ranked.length,color:fills[sel]}}/>:<div className="atlas-empty"><span>◎</span><h3>Explore an economy</h3><p>Select a country to inspect its markets, fundamentals and sovereign risk.</p></div>}</div>
      <div className="atlas-panel"><div className="atlas-panel-title">{layer.label} · highest and lowest</div>
        {(()=>{const maxAbs=Math.max(1e-9,...ranked.map(([,v])=>Math.abs(v)));
          const bar=([iso,v]:[string,number])=><button key={iso} onClick={()=>select(iso)} className={cn('atlas-bar-row',sel===iso&&'on')}>
            <span className="atlas-bar-name">{FLAG(iso)} {data[iso]?.name??iso}</span>
            <span className="atlas-bar-track"><i style={{width:`${Math.max(2,Math.abs(v)/maxAbs*100)}%`,background:fills[iso]}}/></span>
            <b>{fmtVal(v,layer.fmt,layer.diverging)}</b></button>;
          return <div className="p-2 space-y-2"><div>{ranked.slice(0,7).map(bar)}</div><div className="atlas-bar-sep">· · ·</div><div>{ranked.slice(-7).map(bar)}</div></div>;})()}
      </div></aside>
    </div>
    <button className="atlas-coverage-toggle" aria-expanded={coverage} onClick={()=>setCoverage(v=>!v)}>{coverage?'Close live coverage':'Open live coverage'}{selName?` · ${selName}`:''}</button>
    {coverage&&<LiveTV iso={sel} name={selName} region={selRec?.region??null}/>}
    <div className="text-[10px] text-text-tertiary">{Object.values<string>(world.data?.sources??{}).join(' · ')}{macro.data?' · Policy: Global Macro model':''} · Geometry: Natural Earth / world-atlas.</div>
  </div>;
}

function Row({ k, v, children }: { k: string; v?: React.ReactNode; children?: React.ReactNode }) {
  return <div className="flex justify-between gap-2"><span className="text-text-secondary">{k}</span><span className="font-mono text-text-primary text-right">{children ?? v}</span></div>;
}

type Focus = { label: string; value: string; rank: number | null; of: number; color?: string };
function CountryPanel({ iso, name, c, onOpen, onGo, focus }: { iso: string; name: string; c: any; onOpen: (s: string) => void; onGo?: (fn: string, s?: string) => void; focus?: Focus }) {
  const pt = (v: number | null | undefined, d = 1, u = '%') => (v == null ? '—' : `${v.toFixed(d)}${u}`);
  const btn = 'px-2 py-1 rounded-md border border-border hover:border-bloomberg hover:text-bloomberg text-[11px]';
  return (
    <>
      <div className="atlas-country-head">
        <span className="atlas-flag" aria-hidden>{FLAG(iso)}</span>
        <div className="min-w-0"><div className="text-base font-semibold text-text-primary truncate">{name}</div>
          <div className="text-[11px] text-text-tertiary">{iso} · {c.currency}{c.rating ? ` · ${c.rating}` : ''}{c.region ? ` · ${c.region}` : ''}</div></div>
      </div>
      {focus && (
        <div className="atlas-focus">
          <div><span>{focus.label}</span><b><i style={{ background: focus.color ?? 'var(--atlas-no-data)' }} />{focus.value}</b></div>
          {focus.rank != null && <div className="text-right"><span>Rank</span><b>#{focus.rank} <small>of {focus.of}</small></b></div>}
          {focus.rank != null && <div className="atlas-focus-track"><i style={{ left: `${focus.of > 1 ? (1 - (focus.rank - 1) / (focus.of - 1)) * 100 : 50}%` }} /></div>}
        </div>
      )}
      <div className="mkt-controls flex flex-wrap gap-1">
        {c.index?.symbol && <button onClick={() => onOpen(c.index.symbol)} className={btn}>{c.index.label}</button>}
        {c.etf?.etf && <button onClick={() => onOpen(c.etf.etf)} className={btn}>{c.etf.etf} ETF</button>}
        {c.fx?.symbol && <button onClick={() => onOpen(c.fx.symbol)} className={btn}>USD/{c.currency}</button>}
        {onGo && <button onClick={() => onGo('N', undefined)} className={btn}>News</button>}
      </div>
      <div className="space-y-0.5">
        <div className="atlas-section-title">Markets</div>
        {c.index && <Row k={c.index.label}>{fmtPrice(c.index.price)} <Chg v={c.index.change_1d} /></Row>}
        {c.index?.change_ytd != null && <Row k="Index YTD (local)"><Chg v={c.index.change_ytd} d={1} /></Row>}
        {c.change_ytd != null && <Row k="Stocks YTD (USD)"><Chg v={c.change_ytd} d={1} /></Row>}
        {c.change_1y != null && <Row k="Stocks 1Y (USD)"><Chg v={c.change_1y} d={1} /></Row>}
        {c.fx && c.currency !== 'USD' && <Row k={`${c.currency} per USD`}>{fmtPrice(c.fx.per_usd, 'FX')} <Chg v={c.fx.change_ytd} d={1} /></Row>}
        {c.yield_10y != null && <Row k="10Y yield" v={`${c.yield_10y.toFixed(2)}%${c.yield_change_1y_bp != null ? ` (${c.yield_change_1y_bp > 0 ? '+' : ''}${c.yield_change_1y_bp.toFixed(0)}bp 1y)` : ''}`} />}
      </div>
      <div className="space-y-0.5">
        <div className="atlas-section-title">Economy (IMF)</div>
        <Row k="GDP growth (this / next yr)" v={`${pt(c.gdp_growth)} / ${pt(c.gdp_growth_next)}`} />
        <Row k="Inflation (this / next yr)" v={`${pt(c.inflation)} / ${pt(c.inflation_next)}`} />
        <Row k="Unemployment" v={pt(c.unemployment)} />
        <Row k="Govt debt / GDP" v={pt(c.gov_debt, 0)} />
        <Row k="Current account / GDP" v={pt(c.current_account)} />
        <Row k="GDP per person" v={c.gdp_per_capita != null ? `$${Math.round(c.gdp_per_capita).toLocaleString()}` : '—'} />
      </div>
      {(c.policy != null || c.stance) && (
        <div className="space-y-0.5">
          <div className="atlas-section-title">Policy{c.cb ? ` — ${c.euroArea ? 'ECB (euro area)' : c.cb}` : ''}</div>
          <Row k="Policy rate" v={pt(c.policy, 2)} />
          <Row k="Real policy rate" v={pt(c.real_policy_rate, 2, ' pp')} />
          {c.stance && <Row k="Stance" v={c.stance} />}
          {c.quadrant && <Row k="Regime" v={c.quadrant} />}
        </div>)}
      {(c.crp != null || c.rating) && (
        <div className="space-y-0.5">
          <div className="atlas-section-title">Risk (Damodaran)</div>
          <Row k="Sovereign rating (Moody's)" v={c.rating ?? '—'} />
          <Row k="Country risk premium" v={c.crp != null ? fmtPct(c.crp, 2) : '—'} />
          <Row k="Equity risk premium" v={c.erp_total != null ? fmtPct(c.erp_total, 2) : '—'} />
        </div>)}
    </>
  );
}

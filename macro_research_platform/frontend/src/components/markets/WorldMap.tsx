// MAP — every country coloured by markets, economy, policy or risk. Markets: USD country-ETF
// returns, local indices, currencies, 10-year yields. Economy: IMF World Economic Outlook.
// Policy: the Research mode's central-bank model. Risk: Damodaran sovereign ratings and
// country risk premiums. Wheel/drag to zoom and pan, region presets, ranking, country panel.
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { countryPaths, NUMERIC_TO_ISO2 as FALLBACK_NUMERIC, projectPoint, type Topology } from '@/lib/topo';
import { Chg, ErrorBox, fmtPct, fmtPrice, Loading, useJSON } from './shared';

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
  { key: 'y10', group: 'Markets', label: '10Y yield', get: (c) => c.yield_10y, fmt: 'pctpt', diverging: false, goodHigh: false, help: '10-year government bond yield (OECD, monthly; US live).' },
  { key: 'gdp', group: 'Economy', label: 'GDP growth', get: (c) => c.gdp_growth, fmt: 'pctpt', diverging: true, goodHigh: true, help: 'Real GDP growth this year — IMF World Economic Outlook.' },
  { key: 'gdpn', group: 'Economy', label: 'GDP growth next yr', get: (c) => c.gdp_growth_next, fmt: 'pctpt', diverging: true, goodHigh: true, help: 'IMF projection for next year.' },
  { key: 'cpi', group: 'Economy', label: 'Inflation', get: (c) => c.inflation, fmt: 'pctpt', diverging: false, goodHigh: false, help: 'Consumer price inflation this year — IMF.' },
  { key: 'ur', group: 'Economy', label: 'Unemployment', get: (c) => c.unemployment, fmt: 'pctpt', diverging: false, goodHigh: false, help: 'Unemployment rate — IMF.' },
  { key: 'debt', group: 'Economy', label: 'Govt debt / GDP', get: (c) => c.gov_debt, fmt: 'pctpt', diverging: false, goodHigh: false, help: 'General government gross debt, % of GDP — IMF.' },
  { key: 'ca', group: 'Economy', label: 'Current account', get: (c) => c.current_account, fmt: 'pctpt', diverging: true, goodHigh: true, help: 'Current-account balance, % of GDP — IMF.' },
  { key: 'gdppc', group: 'Economy', label: 'GDP per person', get: (c) => c.gdp_per_capita, fmt: 'usd', diverging: false, goodHigh: true, help: 'GDP per capita, current US dollars — IMF.' },
  { key: 'policy', group: 'Policy', label: 'Policy rate', get: (c) => c.policy, fmt: 'pctpt', diverging: false, goodHigh: false, help: 'Central bank policy rate (25 economies, Research mode model).' },
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

let topoCache: Topology | null = null;

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
  const world = useJSON<any>('/api/v1/mkt/map/world', 600_000);
  const macro = useJSON<any>('/api/v1/global-macro', 3_600_000);
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(1100);
  const [view, setView] = useState<{ x: number; y: number; k: number }>({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);

  useEffect(() => {
    if (!topo) fetch('/world-atlas/countries-50m.json').then((r) => r.json()).then((t) => { topoCache = t; setTopo(t); }).catch(() => {});
  }, [topo]);
  useEffect(() => {
    const el = box.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(360, Math.round(e.contentRect.width))));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  const geo = useMemo(() => (topo ? countryPaths(topo, W) : null), [topo, W]);
  const H = geo?.height ?? W * 0.487;
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
  const color = (v: number | null | undefined) => {
    if (v == null || !Number.isFinite(v)) return 'rgb(var(--c-surface-3))';
    if (layer.diverging) {
      // square-root ramp with a visible floor: small moves still read as tinted, not as "no data"
      const a = 0.25 + 0.72 * Math.sqrt(Math.min(1, Math.abs(v) / scale.hi));
      const good = layer.goodHigh ? v >= 0 : v <= 0;
      return good ? `rgb(var(--c-green) / ${a})` : `rgb(var(--c-red) / ${a})`;
    }
    const t = Math.min(1, Math.max(0, (v - scale.lo) / (scale.hi - scale.lo)));
    return `rgb(var(--c-bloomberg) / ${0.2 + t * 0.78})`;
  };
  const ranked = useMemo(() => [...values].sort((a, b) => b[1] - a[1]), [values]);

  const zoomTo = (b: [number, number, number, number]) => {
    const [x0, y0] = projectPoint(b[0], b[3], W), [x1, y1] = projectPoint(b[2], b[1], W);
    const k = Math.min(8, Math.max(1, Math.min(W / Math.max(1, x1 - x0), H / Math.max(1, y1 - y0))));
    setView({ k, x: -(x0 + x1) / 2 * k + W / 2, y: -(y0 + y1) / 2 * k + H / 2 });
  };
  const zoomBy = (f: number, cx = W / 2, cy = H / 2) => setView((v) => {
    const k = Math.min(12, Math.max(1, v.k * f));
    const r = k / v.k;
    return k === 1 ? { x: 0, y: 0, k } : { k, x: cx - (cx - v.x) * r, y: cy - (cy - v.y) * r };
  });
  // wheel zoom (non-passive so the page doesn't scroll while zooming the map)
  useEffect(() => {
    const el = box.current?.querySelector('svg'); if (!el) return;
    const h = (e: WheelEvent) => {
      e.preventDefault();
      const r = (el as SVGSVGElement).getBoundingClientRect();
      zoomBy(e.deltaY < 0 ? 1.25 : 0.8, (e.clientX - r.left) * (W / r.width), (e.clientY - r.top) * (H / r.height));
    };
    el.addEventListener('wheel', h, { passive: false });
    return () => el.removeEventListener('wheel', h);
  });

  const selRec = sel ? data[sel] : null;
  const selName = sel ? (selRec?.name ?? geo?.shapes.find((s) => numToIso[s.id] === sel)?.name ?? sel) : null;
  const found = query.trim().length > 1 ? Object.entries(data).filter(([iso, c]) => (c.name ?? '').toLowerCase().includes(query.trim().toLowerCase()) || iso === query.trim().toUpperCase()).slice(0, 6) : [];
  const select = (iso: string) => {
    setSel(iso); setQuery('');
    const shape = geo?.shapes.find((s) => numToIso[s.id] === iso);
    if (shape && view.k < 2.5) {
      const k = 3;
      setView({ k, x: -shape.centroid[0] * k + W / 2, y: -shape.centroid[1] * k + H / 2 });
    }
  };
  const loading = !geo || (world.loading && !world.data);

  return (
    <div className="space-y-2">
      {/* layer picker: groups, then layers */}
      <div className="flex flex-wrap items-center gap-1">
        {GROUPS.map((g) => (
          <button key={g} onClick={() => { setGroup(g); setLayer(L.find((l) => l.group === g)!); }}
            className={cn('px-2.5 py-1 text-[11px] uppercase tracking-wide border', group === g ? 'bg-bloomberg text-black border-bloomberg font-semibold' : 'border-border text-text-secondary hover:text-text-primary')}>{g}</button>))}
        <span className="mx-1 text-text-tertiary">|</span>
        {L.filter((l) => l.group === group).map((l) => (
          <button key={l.key} onClick={() => setLayer(l)} title={l.help}
            className={cn('px-2.5 py-1 text-xs border', layer.key === l.key ? 'border-bloomberg text-text-primary font-semibold bg-bloomberg/10' : 'border-border text-text-secondary hover:text-text-primary')}>{l.label}</button>))}
      </div>
      <div className="grid grid-cols-1 2xl:grid-cols-[1fr_320px] gap-2">
        <div className="space-y-2 min-w-0">
          <div className="flex flex-wrap items-center gap-1 text-[11px]">
            {REGIONS.map(([name, b]) => (
              <button key={name} onClick={() => (name === 'World' ? setView({ x: 0, y: 0, k: 1 }) : zoomTo(b))} className="px-2 py-0.5 border border-border text-text-secondary hover:text-bloomberg hover:border-bloomberg">{name}</button>))}
            <button onClick={() => zoomBy(1.4)} aria-label="Zoom in" className="px-2 py-0.5 border border-border hover:border-bloomberg">+</button>
            <button onClick={() => zoomBy(1 / 1.4)} aria-label="Zoom out" className="px-2 py-0.5 border border-border hover:border-bloomberg">−</button>
            <div className="relative ml-auto">
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a country…" aria-label="Find a country"
                className="w-44 bg-surface-1 border border-border px-2 py-0.5 text-xs text-text-primary placeholder:text-text-tertiary" />
              {found.length > 0 && (
                <ul className="absolute right-0 z-20 mt-1 w-56 bg-surface-1 border border-border shadow-lg">
                  {found.map(([iso, c]) => <li key={iso}><button onClick={() => select(iso)} className="w-full text-left px-2 py-1 text-xs hover:bg-surface-3">{c.name} <span className="text-text-tertiary">{iso}</span></button></li>)}
                </ul>)}
            </div>
          </div>
          <div ref={box} className="relative bg-surface-1 border border-border min-w-0 overflow-hidden select-none"
            onMouseDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false }; }}
            onMouseMove={(e) => {
              const d = drag.current; if (!d || view.k === 1) return;
              const r = box.current!.getBoundingClientRect(), s = W / r.width;
              if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) d.moved = true;
              setView((v) => ({ ...v, x: d.vx + (e.clientX - d.x) * s, y: d.vy + (e.clientY - d.y) * s }));
            }}
            onMouseUp={() => { setTimeout(() => { drag.current = null; }, 0); }} onMouseLeave={() => { drag.current = null; setHover(null); }}>
            {loading && <Loading label="Drawing the map…" />}
            {world.error && !world.data && <ErrorBox msg={world.error} />}
            {geo && (
              <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label={`World map: ${layer.label}`} className={view.k > 1 ? 'cursor-grab' : ''}>
                <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
                  {geo.shapes.map((s) => {
                    const iso = numToIso[s.id];
                    const v = iso && data[iso] ? layer.get(data[iso]) : null;
                    return <path key={s.id + s.name} d={s.path} data-iso={iso} aria-label={s.name} fill={color(v)} stroke="rgb(var(--c-bg))" strokeWidth={0.5 / view.k}
                      className={cn(iso && 'cursor-pointer hover:opacity-80')} style={sel && iso === sel ? { stroke: 'rgb(var(--c-text-primary))', strokeWidth: 1.6 / view.k } : undefined}
                      onMouseMove={(e) => { const r = box.current!.getBoundingClientRect(); setHover({ iso: iso ?? '', name: data[iso]?.name ?? s.name, x: e.clientX - r.left, y: e.clientY - r.top }); }}
                      onClick={() => { if (!drag.current?.moved && iso) setSel(iso); }} />;
                  })}
                  {/* value labels for the larger countries (more appear as you zoom in) */}
                  {geo.shapes.map((s) => {
                    const iso = numToIso[s.id]; if (!iso || !data[iso]) return null;
                    const v = layer.get(data[iso]); if (v == null || !Number.isFinite(v)) return null;
                    const area = s.area ?? 0;
                    if (area * view.k * view.k < 900) return null;
                    return <text key={`t${s.id}`} x={s.centroid[0]} y={s.centroid[1]} textAnchor="middle" dominantBaseline="middle" pointerEvents="none"
                      style={{ fontSize: 9 / view.k, fill: 'rgb(var(--c-text-primary))', paintOrder: 'stroke', stroke: 'rgb(var(--c-bg) / 0.7)', strokeWidth: 2 / view.k }}>
                      {fmtVal(v, layer.fmt, layer.diverging)}</text>;
                  })}
                </g>
              </svg>
            )}
            {hover && (
              <div className="pointer-events-none absolute z-10 px-2.5 py-1.5 bg-surface-2 border border-border shadow-lg text-xs" style={{ left: Math.min(hover.x + 12, (box.current?.clientWidth ?? W) - 200), top: hover.y + 12 }}>
                <div className="font-semibold text-text-primary">{hover.name}</div>
                <div className="text-text-secondary">{layer.label}: <span className="font-mono text-text-primary">{hover.iso && data[hover.iso] ? fmtVal(layer.get(data[hover.iso]), layer.fmt, layer.diverging) : 'no data'}</span></div>
              </div>
            )}
          </div>
          {/* legend */}
          <div className="flex flex-wrap items-center gap-3 text-[10px] text-text-tertiary">
            <span className="font-mono">{fmtVal(scale.lo, layer.fmt, layer.diverging)}</span>
            <span className="h-2 w-48 border border-border" style={{ background: layer.diverging
              ? `linear-gradient(90deg, rgb(var(--c-${layer.goodHigh ? 'red' : 'green'})), rgb(var(--c-surface-3)), rgb(var(--c-${layer.goodHigh ? 'green' : 'red'})))`
              : 'linear-gradient(90deg, rgb(var(--c-bloomberg) / 0.12), rgb(var(--c-bloomberg)))' }} />
            <span className="font-mono">{fmtVal(scale.hi, layer.fmt, layer.diverging)}</span>
            <span>{layer.help}</span>
            <span className="ml-auto">{values.length} countries with data · wheel to zoom, drag to pan</span>
          </div>
        </div>

        {/* right column: country panel + ranking */}
        <div className="space-y-2">
          <div className="bg-surface-1 border border-border p-3 space-y-2 text-xs">
            {!sel || !selRec ? <p className="text-text-tertiary">Click a country (or search) for its markets, economy and risk.</p> : (
              <CountryPanel iso={sel} name={selName!} c={selRec} onOpen={onOpen} onGo={onGo} />
            )}
          </div>
          <div className="bg-surface-1 border border-border">
            <div className="panel-bar px-2 h-6 flex items-center text-[11px] uppercase tracking-wide"><span className="text-bloomberg font-semibold">{layer.label} — ranking</span></div>
            <div className="grid grid-cols-2 gap-x-2 p-1 text-[11px]">
              {[['Highest', ranked.slice(0, 10)], ['Lowest', ranked.slice(-10).reverse()]].map(([t, rows]) => (
                <div key={t as string}>
                  <div className="px-1 text-text-tertiary">{t as string}</div>
                  {(rows as [string, number][]).map(([iso, v], i) => (
                    <button key={iso} onClick={() => select(iso)} className={cn('w-full flex justify-between px-1 hover:bg-surface-3', iso === sel && 'bg-surface-3')}>
                      <span className="truncate text-text-primary"><span className="text-bloomberg mr-1">{i + 1}</span>{data[iso]?.name ?? iso}</span>
                      <span className="font-mono text-text-secondary">{fmtVal(v, layer.fmt, layer.diverging)}</span></button>))}
                </div>))}
            </div>
          </div>
        </div>
      </div>
      <div className="text-[10px] text-text-tertiary">
        {world.data ? Object.values<string>(world.data.sources).join(' · ') : ''}{macro.data ? ' · Policy: Research mode Global Macro (BIS, OECD, FRED, national sources)' : ''} · Map: Natural Earth via world-atlas, Equal Earth projection.
      </div>
    </div>
  );
}

function Row({ k, v, children }: { k: string; v?: React.ReactNode; children?: React.ReactNode }) {
  return <div className="flex justify-between gap-2"><span className="text-text-secondary">{k}</span><span className="font-mono text-text-primary text-right">{children ?? v}</span></div>;
}

function CountryPanel({ iso, name, c, onOpen, onGo }: { iso: string; name: string; c: any; onOpen: (s: string) => void; onGo?: (fn: string, s?: string) => void }) {
  const pt = (v: number | null | undefined, d = 1, u = '%') => (v == null ? '—' : `${v.toFixed(d)}${u}`);
  const btn = 'px-2 py-1 border border-border hover:border-bloomberg hover:text-bloomberg text-[11px]';
  return (
    <>
      <div className="flex items-baseline justify-between">
        <div className="text-base font-semibold text-text-primary">{name}</div>
        <div className="text-[11px] text-text-tertiary">{iso} · {c.currency}{c.rating ? ` · ${c.rating}` : ''}</div>
      </div>
      <div className="flex flex-wrap gap-1">
        {c.index?.symbol && <button onClick={() => onOpen(c.index.symbol)} className={btn}>{c.index.label}</button>}
        {c.etf?.etf && <button onClick={() => onOpen(c.etf.etf)} className={btn}>{c.etf.etf} ETF</button>}
        {c.fx?.symbol && <button onClick={() => onOpen(c.fx.symbol)} className={btn}>USD/{c.currency}</button>}
        {onGo && <button onClick={() => onGo('N', undefined)} className={btn}>News</button>}
      </div>
      <div className="space-y-0.5">
        <div className="text-[10px] uppercase tracking-wider text-bloomberg pt-1">Markets</div>
        {c.index && <Row k={c.index.label}>{fmtPrice(c.index.price)} <Chg v={c.index.change_1d} /></Row>}
        {c.index?.change_ytd != null && <Row k="Index YTD (local)"><Chg v={c.index.change_ytd} d={1} /></Row>}
        {c.change_ytd != null && <Row k="Stocks YTD (USD)"><Chg v={c.change_ytd} d={1} /></Row>}
        {c.change_1y != null && <Row k="Stocks 1Y (USD)"><Chg v={c.change_1y} d={1} /></Row>}
        {c.fx && c.currency !== 'USD' && <Row k={`${c.currency} per USD`}>{fmtPrice(c.fx.per_usd, 'FX')} <Chg v={c.fx.change_ytd} d={1} /></Row>}
        {c.yield_10y != null && <Row k="10Y yield" v={`${c.yield_10y.toFixed(2)}%${c.yield_change_1y_bp != null ? ` (${c.yield_change_1y_bp > 0 ? '+' : ''}${c.yield_change_1y_bp.toFixed(0)}bp 1y)` : ''}`} />}
      </div>
      <div className="space-y-0.5">
        <div className="text-[10px] uppercase tracking-wider text-bloomberg pt-1">Economy (IMF)</div>
        <Row k="GDP growth (this / next yr)" v={`${pt(c.gdp_growth)} / ${pt(c.gdp_growth_next)}`} />
        <Row k="Inflation (this / next yr)" v={`${pt(c.inflation)} / ${pt(c.inflation_next)}`} />
        <Row k="Unemployment" v={pt(c.unemployment)} />
        <Row k="Govt debt / GDP" v={pt(c.gov_debt, 0)} />
        <Row k="Current account / GDP" v={pt(c.current_account)} />
        <Row k="GDP per person" v={c.gdp_per_capita != null ? `$${Math.round(c.gdp_per_capita).toLocaleString()}` : '—'} />
      </div>
      {(c.policy != null || c.stance) && (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wider text-bloomberg pt-1">Policy{c.cb ? ` — ${c.euroArea ? 'ECB (euro area)' : c.cb}` : ''}</div>
          <Row k="Policy rate" v={pt(c.policy, 2)} />
          <Row k="Real policy rate" v={pt(c.real_policy_rate, 2, ' pp')} />
          {c.stance && <Row k="Stance" v={c.stance} />}
          {c.quadrant && <Row k="Regime" v={c.quadrant} />}
        </div>)}
      {(c.crp != null || c.rating) && (
        <div className="space-y-0.5">
          <div className="text-[10px] uppercase tracking-wider text-bloomberg pt-1">Risk (Damodaran)</div>
          <Row k="Sovereign rating (Moody's)" v={c.rating ?? '—'} />
          <Row k="Country risk premium" v={c.crp != null ? fmtPct(c.crp, 2) : '—'} />
          <Row k="Equity risk premium" v={c.erp_total != null ? fmtPct(c.erp_total, 2) : '—'} />
        </div>)}
    </>
  );
}

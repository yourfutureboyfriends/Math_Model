// MAP — world map coloured by markets or macro: country equity performance (USD MSCI
// country ETFs) or the macro layers from the Research mode (policy rate, inflation, real
// rate, unemployment, GDP growth). Click a country for details and its market.
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { countryPaths, NUMERIC_TO_ISO2, type Topology } from '@/lib/topo';
import { Chg, ErrorBox, fmtPct, Loading, useJSON } from './shared';

type Layer = { key: string; label: string; kind: 'market' | 'macro'; field: string; unit: '%' | 'pp'; diverging: boolean; goodHigh: boolean; scale: number; help: string };
const LAYERS: Layer[] = [
  { key: 'd1', label: 'Stocks today', kind: 'market', field: 'change_1d', unit: '%', diverging: true, goodHigh: true, scale: 0.03, help: '1-day move of the country’s MSCI ETF, in USD.' },
  { key: 'ytd', label: 'Stocks YTD', kind: 'market', field: 'change_ytd', unit: '%', diverging: true, goodHigh: true, scale: 0.4, help: 'Year-to-date total return in USD.' },
  { key: '1y', label: 'Stocks 1 year', kind: 'market', field: 'change_1y', unit: '%', diverging: true, goodHigh: true, scale: 0.5, help: '12-month total return in USD.' },
  { key: 'policy', label: 'Policy rate', kind: 'macro', field: 'policy', unit: '%', diverging: false, goodHigh: false, scale: 15, help: 'Central bank policy rate.' },
  { key: 'cpi', label: 'Inflation', kind: 'macro', field: 'cpi', unit: '%', diverging: false, goodHigh: false, scale: 10, help: 'Consumer price inflation, year on year.' },
  { key: 'real', label: 'Real policy rate', kind: 'macro', field: 'real_policy_rate', unit: 'pp', diverging: true, goodHigh: true, scale: 6, help: 'Policy rate minus inflation — positive = restrictive.' },
  { key: 'gap', label: 'Inflation vs target', kind: 'macro', field: 'inflation_gap', unit: 'pp', diverging: true, goodHigh: false, scale: 5, help: 'CPI minus the central bank’s target.' },
  { key: 'unemp', label: 'Unemployment', kind: 'macro', field: 'unemployment', unit: '%', diverging: false, goodHigh: false, scale: 15, help: 'Unemployment rate.' },
  { key: 'gdp', label: 'GDP growth', kind: 'macro', field: 'gdp', unit: '%', diverging: true, goodHigh: true, scale: 6, help: 'Real GDP growth, year on year.' },
];
const EUROZONE = ['DE', 'FR', 'IT', 'ES', 'NL', 'BE', 'AT', 'IE', 'FI', 'PT', 'GR'];

let topoCache: Topology | null = null;

export function WorldMap({ onOpen }: { onOpen: (s: string) => void }) {
  const [topo, setTopo] = useState<Topology | null>(topoCache);
  const [layer, setLayer] = useState<Layer>(LAYERS[1]);
  const [hover, setHover] = useState<{ iso: string; name: string; x: number; y: number } | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const markets = useJSON<any>('/api/v1/mkt/map', 600_000);
  const macro = useJSON<any>('/api/v1/global-macro', 3_600_000);
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(1100);
  useEffect(() => {
    if (!topo) fetch('/world-atlas/countries-50m.json').then((r) => r.json()).then((t) => { topoCache = t; setTopo(t); }).catch(() => {});
  }, [topo]);
  useEffect(() => {
    const el = box.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(360, Math.round(e.contentRect.width))));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  const geo = useMemo(() => (topo ? countryPaths(topo, W) : null), [topo, W]);

  // iso2 → { market, macro } record
  const macroByIso = useMemo(() => {
    const m: Record<string, any> = {};
    for (const e of macro.data?.economies ?? []) {
      const rec = { name: e.name, cb: e.cb, policy: e.policy?.available ? e.policy.rate : null, cpi: e.cpi?.value ?? null, unemployment: e.unemployment?.value ?? null,
        gdp: e.gdp?.value ?? null, real_policy_rate: e.real_policy_rate, inflation_gap: e.inflation_gap, stance: e.policy?.stance, quadrant: e.quadrant };
      m[e.code] = rec;
    }
    if (m.EA) for (const c of EUROZONE) if (!m[c]) m[c] = { ...m.EA, euroArea: true };
    return m;
  }, [macro.data]);
  const valueOf = (iso: string): number | null => {
    if (layer.kind === 'market') return markets.data?.countries?.[iso]?.[layer.field] ?? null;
    return macroByIso[iso]?.[layer.field] ?? null;
  };
  const color = (v: number | null) => {
    if (v == null) return 'var(--surface-3)';
    if (layer.diverging) {
      const a = Math.min(1, Math.abs(v) / layer.scale) * 0.8 + 0.15;
      const good = layer.goodHigh ? v >= 0 : v <= 0;
      return good ? `rgb(var(--c-green) / ${a})` : `rgb(var(--c-red) / ${a})`;
    }
    const a = Math.min(1, Math.max(0, v) / layer.scale) * 0.85 + 0.1;
    return `rgb(var(--c-bloomberg) / ${a})`;
  };
  const fmtV = (v: number | null) => v == null ? 'no data' : layer.kind === 'market' ? fmtPct(v, 1) : `${v > 0 && layer.diverging ? '+' : ''}${v.toFixed(1)}${layer.unit === '%' ? '%' : ' pp'}`;
  const selM = sel ? markets.data?.countries?.[sel] : null, selX = sel ? macroByIso[sel] : null;
  const selName = sel ? geo?.shapes.find((s) => NUMERIC_TO_ISO2[s.id] === sel)?.name : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1">
        {LAYERS.map((l) => (
          <button key={l.key} onClick={() => setLayer(l)} title={l.help}
            className={cn('px-3 py-1.5 text-xs rounded-md border', layer.key === l.key ? 'border-bloomberg bg-bloomberg/10 text-text-primary font-semibold' : 'border-border text-text-secondary hover:text-text-primary')}>{l.label}</button>))}
      </div>
      <div className="grid grid-cols-1 2xl:grid-cols-[1fr_300px] gap-3">
        <div ref={box} className="relative bg-surface-1 border border-border rounded-md p-2 min-w-0">
          {(!geo || (layer.kind === 'market' ? markets.loading && !markets.data : macro.loading && !macro.data)) && <Loading label="Drawing the map…" />}
          {(layer.kind === 'market' ? markets.error : macro.error) && <ErrorBox msg={layer.kind === 'market' ? markets.error : macro.error} />}
          {geo && (
            <svg viewBox={`0 0 ${W} ${geo.height}`} width="100%" height={geo.height} role="img" aria-label={`World map: ${layer.label}`} onMouseLeave={() => setHover(null)}>
              {geo.shapes.map((s) => {
                const iso = NUMERIC_TO_ISO2[s.id];
                const v = iso ? valueOf(iso) : null;
                return <path key={s.id + s.name} d={s.path} data-iso={iso} aria-label={s.name} fill={color(v)} stroke="var(--bg)" strokeWidth={0.5}
                  className={cn(iso && 'cursor-pointer hover:opacity-80', sel && iso === sel && 'stroke-text-primary')} style={sel && iso === sel ? { strokeWidth: 1.5 } : undefined}
                  onMouseMove={(e) => { const r = box.current!.getBoundingClientRect(); setHover({ iso: iso ?? '', name: s.name, x: e.clientX - r.left, y: e.clientY - r.top }); }}
                  onClick={() => iso && setSel(iso)} />;
              })}
            </svg>
          )}
          {hover && (
            <div className="pointer-events-none absolute z-10 px-2.5 py-1.5 rounded-md bg-surface-2 border border-border shadow-lg text-xs" style={{ left: Math.min(hover.x + 12, W - 180), top: hover.y + 12 }}>
              <div className="font-semibold text-text-primary">{hover.name}</div>
              <div className="text-text-secondary">{layer.label}: <span className="font-mono">{hover.iso ? fmtV(valueOf(hover.iso)) : 'no data'}</span></div>
            </div>
          )}
          <div className="flex items-center gap-2 mt-2 text-[10px] text-text-tertiary">
            <span>{layer.help}</span>
            <span className="ml-auto">{layer.diverging ? (layer.goodHigh ? 'red ← lower · higher → green' : 'green ← lower · higher → red') : 'darker = higher'}</span>
          </div>
        </div>
        <div className="bg-surface-1 border border-border rounded-md p-4 space-y-3">
          {!sel ? <p className="text-xs text-text-tertiary">Click a country for its market and economy.</p> : (
            <>
              <div><div className="text-base font-semibold text-text-primary">{selName ?? sel}</div>{selX?.cb && <div className="text-[11px] text-text-tertiary">{selX.euroArea ? 'Euro area data (ECB)' : `Central bank: ${selX.cb}`}</div>}</div>
              {selM ? (
                <div className="space-y-1 text-xs">
                  <div className="text-[10px] uppercase tracking-wider text-text-tertiary">Stock market ({selM.label}, USD)</div>
                  {[['Today', selM.change_1d], ['1 month', selM.change_1m], ['Year to date', selM.change_ytd], ['1 year', selM.change_1y]].map(([k, v]) => (
                    <div key={k as string} className="flex justify-between"><span className="text-text-secondary">{k}</span><Chg v={v as number} d={1} /></div>))}
                  <button onClick={() => onOpen(selM.etf)} className="mt-2 w-full py-1.5 rounded-md bg-bloomberg text-white text-xs font-semibold">Open {selM.etf}</button>
                </div>
              ) : <p className="text-xs text-text-tertiary">No country ETF data.</p>}
              {selX ? (
                <div className="space-y-1 text-xs border-t border-border-subtle pt-3">
                  <div className="text-[10px] uppercase tracking-wider text-text-tertiary">Economy</div>
                  {[['Policy rate', selX.policy, '%'], ['Inflation', selX.cpi, '%'], ['Real policy rate', selX.real_policy_rate, 'pp'], ['Unemployment', selX.unemployment, '%'], ['GDP growth', selX.gdp, '%']].map(([k, v, u]) => (
                    <div key={k as string} className="flex justify-between"><span className="text-text-secondary">{k}</span><span className="font-mono text-text-primary">{v == null ? '—' : `${(v as number).toFixed(2)}${u === '%' ? '%' : ' pp'}`}</span></div>))}
                  {selX.stance && <div className="flex justify-between"><span className="text-text-secondary">Policy stance</span><span className="text-text-primary">{selX.stance}</span></div>}
                  {selX.quadrant && <div className="flex justify-between"><span className="text-text-secondary">Regime</span><span className="text-text-primary">{selX.quadrant}</span></div>}
                </div>
              ) : <p className="text-xs text-text-tertiary border-t border-border-subtle pt-3">Not among the 25 economies tracked by the macro model.</p>}
            </>
          )}
        </div>
      </div>
      <div className="text-[10px] text-text-tertiary">Markets: {markets.data?.source ?? '—'}. Macro: {macro.data ? 'Research mode Global Macro (BIS, OECD, FRED, national sources)' : '—'}. Map: Natural Earth via world-atlas, Equal Earth projection.</div>
    </div>
  );
}

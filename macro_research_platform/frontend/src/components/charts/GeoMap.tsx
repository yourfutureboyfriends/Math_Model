/**
 * World map on Apache ECharts — the platform's one map engine. Countries come from the bundled world-atlas
 * TopoJSON and are drawn in the Equal Earth projection (d3-geo, an equal-area map so sizes are honest).
 *
 *  - layers: country shading (choropleth), points (optionally pulsing), flow lines (curved, arrowed, with moving
 *    particles when animated), country labels;
 *  - navigation: drag to pan; zoom with the buttons, a double-click, or Ctrl/⌘ + scroll (plain scrolling still
 *    scrolls the page); a ref exposes zoom / reset / focus for callers;
 *  - tooltips on every country, point and line; click and hover events by numeric country id or point id.
 */
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { geoCentroid, geoEqualEarth } from 'd3-geo';
import { feature } from 'topojson-client';
import { EChart, alpha, color, echarts, useChartTheme, type ECharts } from './EChart';

export const WORLD = 'world-equal-earth';
export type GeoPoint = { id: string; lon: number; lat: number; size: number; color: string; tip?: string; label?: string; pulse?: boolean; selected?: boolean };
export type GeoLine = { id: string; from: [number, number]; to: [number, number]; color: string; width: number; tip?: string };
export type GeoMapHandle = { zoom: (factor: number) => void; reset: () => void; focus: (lon: number, lat: number, zoom: number) => void;
  focusBounds: (b: [number, number, number, number]) => void; focusRegion: (id: string, zoom?: number) => void };

// one projection for every map; ECharts fits it to the box
const projection = geoEqualEarth();
const PROJ = { project: (p: number[]) => projection(p as [number, number]) as number[], unproject: (p: number[]) => projection.invert!(p as [number, number]) as number[],
  stream: projection.stream };

let world: Promise<Record<string, [number, number]>> | null = null;
/** Register the world map once; resolves to each country's centroid (lon, lat) by numeric id. */
export function loadWorld(): Promise<Record<string, [number, number]>> {
  world ??= fetch('/world-atlas/countries-50m.json').then((r) => r.json()).then((topo) => {
    const fc = feature(topo, topo.objects.countries) as unknown as GeoJSON.FeatureCollection;
    const centroids: Record<string, [number, number]> = {};
    fc.features = fc.features.filter((f) => String(f.id) !== '010').map((f) => {            // Antarctica off
      const id = String(f.id ?? f.properties?.name);
      centroids[id] = geoCentroid(f as never) as [number, number];
      return { ...f, properties: { name: id, label: (f.properties as any)?.name ?? id } };
    });
    echarts.registerMap(WORLD, fc as never);
    (loadWorld as any).labels = Object.fromEntries(fc.features.map((f) => [f.properties!.name, f.properties!.label]));
    return centroids;
  }).catch((e) => { world = null; throw e; });
  return world;
}
export const countryLabel = (id: string): string => (loadWorld as any).labels?.[id] ?? id;

export const GeoMap = forwardRef<GeoMapHandle, {
  height?: number; fills?: Record<string, string>; regionTip?: (id: string, name: string) => string; selected?: string | null;
  points?: GeoPoint[]; lines?: GeoLine[]; animate?: boolean; labels?: Record<string, string>; ariaLabel: string; controls?: boolean;
  onRegionClick?: (id: string) => void; onRegionHover?: (id: string | null) => void; onPointClick?: (id: string) => void; onZoom?: (zoom: number) => void;
  initial?: { center: [number, number]; zoom: number } | null; className?: string;
}>(function GeoMap({ height = 420, fills, regionTip, selected, points, lines, animate = true, labels, ariaLabel, controls = true,
  onRegionClick, onRegionHover, onPointClick, onZoom, initial, className = '' }, ref) {
  const t = useChartTheme();
  const [ready, setReady] = useState<Record<string, [number, number]> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const chart = useRef<ECharts | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const cbs = useRef({ onRegionClick, onRegionHover, onPointClick, onZoom });
  cbs.current = { onRegionClick, onRegionHover, onPointClick, onZoom };
  useEffect(() => { loadWorld().then(setReady).catch((e) => setErr(String(e?.message ?? e))); }, []);

  const view = () => { const g = (chart.current?.getOption() as any)?.geo?.[0]; return { zoom: g?.zoom ?? 1, center: g?.center as [number, number] | undefined }; };
  const setView = (zoom: number, center?: [number, number]) => {
    const z = Math.max(1, Math.min(12, zoom));
    chart.current?.setOption({ geo: { zoom: z, ...(center ? { center } : z === 1 ? { center: null } : {}) } });
    cbs.current.onZoom?.(z);
  };
  const api: GeoMapHandle = {
    zoom: (f) => { const v = view(); setView(v.zoom * f, v.center); },
    reset: () => setView(1, undefined),
    focus: (lon, lat, zoom) => setView(zoom, [lon, lat]),
    focusBounds: ([lon0, lat0, lon1, lat1]) => setView(Math.min(8, Math.max(1, Math.min(300 / Math.max(1, lon1 - lon0), 140 / Math.max(1, lat1 - lat0)) * 0.9)), [(lon0 + lon1) / 2, (lat0 + lat1) / 2]),
    focusRegion: (id, zoom = 2.5) => { const c = ready?.[id]; if (c) setView(Math.max(view().zoom, zoom), c); },
  };
  useImperativeHandle(ref, () => api);

  // Ctrl/⌘ + wheel zooms; a plain wheel scrolls the page
  useEffect(() => {
    const el = box.current; if (!el) return;
    const wheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const c = chart.current; if (!c) return;
      const r = el.getBoundingClientRect(), at = c.convertFromPixel({ geoIndex: 0 }, [e.clientX - r.left, e.clientY - r.top]) as number[] | undefined;
      const v = view(), z = v.zoom * Math.exp(-Math.max(-120, Math.min(120, e.deltaY)) * 0.006);
      setView(z, at && Number.isFinite(at[0]) ? [(v.center?.[0] ?? at[0]) * 0.6 + at[0] * 0.4, (v.center?.[1] ?? at[1]) * 0.6 + at[1] * 0.4] : v.center);
    };
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  const option = useMemo(() => {
    if (!ready) return null;
    const sc = box.current, land = color('var(--atlas-no-data)', alpha(t.mutedText, 0.22), sc), border = color('var(--atlas-border)', alpha(t.mutedText, 0.45), sc);
    const regions = Object.entries(fills ?? {}).map(([name, c]) => ({ name, itemStyle: { areaColor: color(c) } }));
    if (selected) regions.push({ name: selected, itemStyle: { ...(regions.find((r) => r.name === selected)?.itemStyle ?? {}), borderColor: t.textStrong, borderWidth: 1.6 } as any });
    const pts = points ?? [];
    const pointSeries = (pulse: boolean) => ({
      type: pulse ? 'effectScatter' : 'scatter', coordinateSystem: 'geo', geoIndex: 0, zlevel: 2, z: 4, cursor: 'pointer',
      ...(pulse ? { rippleEffect: { brushType: 'stroke', scale: 2.8, period: 3.5 }, showEffectOn: 'render' } : {}),
      labelLayout: { hideOverlap: true },
      data: pts.filter((p) => !!p.pulse === pulse).map((p) => ({ name: p.id, value: [p.lon, p.lat], symbolSize: p.size, tip: p.tip,
        itemStyle: { color: color(p.color), borderColor: p.selected ? t.textStrong : alpha(t.surface1, 0.9), borderWidth: p.selected ? 2 : 1, shadowBlur: p.selected ? 10 : 0, shadowColor: color(p.color) },
        label: p.label ? { show: true, formatter: p.label, position: 'right', color: t.textStrong, fontSize: 10, textBorderColor: t.surface1, textBorderWidth: 3 } : { show: false } })),
    });
    return {
      animation: true, legend: { show: false }, toolbox: { show: false },
      tooltip: { trigger: 'item', formatter: (q: any) => q.componentType === 'geo' ? (regionTip ? regionTip(q.name, countryLabel(q.name)) : countryLabel(q.name)) : q.data?.tip ?? '' },
      geo: {
        map: WORLD, projection: PROJ, roam: 'move', scaleLimit: { min: 1, max: 12 },
        // the view is set once; later data updates merge in place and keep the user's pan and zoom
        ...(chart.current ? {} : { zoom: initial?.zoom ?? 1, ...(initial ? { center: initial.center } : {}) }),
        left: 4, right: 4, top: 4, bottom: 4, selectedMode: false, tooltip: { show: true },
        itemStyle: { areaColor: land, borderColor: border, borderWidth: 0.5 },
        emphasis: { itemStyle: { areaColor: alpha(t.accent, 0.35), borderColor: t.textStrong, borderWidth: 1 }, label: { show: false } },
        label: { show: !!labels, color: color('var(--atlas-label)', t.text, sc), fontSize: 10, textBorderColor: color('var(--atlas-ocean)', t.surface1, sc), textBorderWidth: 2.5,
          formatter: (q: any) => labels?.[q.name] ?? '' },
        regions,
      },
      series: [
        { type: 'lines', coordinateSystem: 'geo', geoIndex: 0, zlevel: 1, z: 3, symbol: ['none', 'arrow'], symbolSize: 7,
          effect: { show: animate && !!lines?.length, period: 3.2, trailLength: 0.25, symbol: 'circle', symbolSize: 4, color: '#fff' },
          lineStyle: { curveness: 0.28 },
          data: (lines ?? []).map((l) => ({ name: l.id, coords: [l.from, l.to], tip: l.tip, lineStyle: { color: color(l.color), width: l.width, opacity: 0.85 } })) },
        pointSeries(false), pointSeries(true),
      ],
    };
  }, [ready, fills, regionTip, selected, points, lines, animate, labels, initial, t]);

  const onReady = (c: ECharts) => {
    chart.current = c;
    c.on('click', (q: any) => {
      if (q.componentType === 'geo') cbs.current.onRegionClick?.(q.name);
      else if (q.seriesType === 'scatter' || q.seriesType === 'effectScatter') cbs.current.onPointClick?.(q.name);
    });
    c.on('mouseover', (q: any) => { if (q.componentType === 'geo') cbs.current.onRegionHover?.(q.name); });
    c.on('mouseout', (q: any) => { if (q.componentType === 'geo') cbs.current.onRegionHover?.(null); });
    c.on('georoam', () => cbs.current.onZoom?.(view().zoom));
    c.getZr().on('dblclick', (e: any) => { const at = c.convertFromPixel({ geoIndex: 0 }, [e.offsetX, e.offsetY]) as number[]; const v = view();
      setView(v.zoom * 1.6, at && Number.isFinite(at[0]) ? [at[0], at[1]] : v.center); });
  };

  return (
    <div ref={box} className={`relative rounded-md overflow-hidden ${className}`} style={{ height,
      background: 'radial-gradient(120% 100% at 50% 40%, var(--atlas-ocean-light, rgb(var(--c-surface-2))) 0%, var(--atlas-ocean, rgb(var(--c-surface-1))) 75%)' }}>
      {err ? <div className="p-3 text-2xs text-amber">World map unavailable — {err}</div>
        : option ? <EChart option={option} height={height} merge onReady={onReady} ariaLabel={ariaLabel} />
        : <div className="h-full grid place-items-center text-2xs text-text-tertiary">Loading the world map…</div>}
      {controls && option && <div className="absolute top-2 left-2 flex gap-1 z-10">
        {([['+', 'Zoom in', () => api.zoom(1.5)], ['−', 'Zoom out', () => api.zoom(1 / 1.5)], ['↺', 'Reset map', () => api.reset()]] as const).map(([s, l, f]) => (
          <button key={l} aria-label={l} title={l} onClick={f} className="w-7 h-7 grid place-items-center bg-surface-1/90 border border-border rounded-md text-xs hover:border-bloomberg">{s}</button>))}
      </div>}
    </div>
  );
});

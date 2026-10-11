// LiveMap: a pannable, zoomable world map on canvas (web Mercator) for live traffic — tens of
// thousands of ships or aircraft at once. Drag to pan, wheel / double-click / buttons to zoom,
// hover for a label, click to select. Land is redrawn only when the view settles; while moving,
// the last land image is shifted and scaled, so panning stays smooth.
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { geoMercator, geoPath, geoTransform } from 'd3-geo';
import { feature, mesh } from 'topojson-client';
import { Minus, Plus, Globe2 } from 'lucide-react';
import { useCssColor } from './cssColor';

export type MapPoint = {
  id: string; lon: number; lat: number; color: string;
  heading?: number | null;           // degrees; draws a pointed glyph when zoomed in
  moving?: boolean;
  big?: boolean;                     // emphasised (emergency, selected kind…)
  ring?: string;                     // outline colour (e.g. military)
  approx?: boolean;                  // position known only roughly (satellite grid): hidden where it falls on land
  label?: string;                    // drawn next to the point when zoomed in
};
export type MapLine = { coords: [number, number][]; color: string; width?: number; dash?: number[] };
export type MapMarker = { lon: number; lat: number; label?: string; color: string; r?: number; id?: string; fill?: boolean };
export type MapView = { lon: number; lat: number; zoom: number };
export type MapBounds = { west: number; south: number; east: number; north: number; zoom: number; lon: number; lat: number; width: number; height: number };
export type LiveMapHandle = { flyTo: (v: Partial<MapView>) => void; fitBounds: (b: [number, number, number, number]) => void };

const TILE = 256;
const MAX_LAT = 85.05;
const clampLat = (lat: number) => Math.max(-MAX_LAT, Math.min(MAX_LAT, lat));
const worldX = (lon: number, S: number) => ((lon + 180) / 360) * S;
const worldY = (lat: number, S: number) => {
  const p = (clampLat(lat) * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(Math.PI / 4 + p / 2)) / Math.PI) / 2) * S;
};
const lonOf = (x: number, S: number) => (x / S) * 360 - 180;
const latOf = (y: number, S: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / S))) * 180) / Math.PI;

let landCache: { land: any; borders: any } | null = null;
// 1:10m coastline for zoomed-in views (1:50m is far too coarse at harbour scale): one polygon per
// island / landmass with its bounding box, so only those in view are drawn
type Poly = { f: any; w: number; s: number; e: number; n: number };
let fineCache: Poly[] | null = null;
let fineLoading = false;

export const LiveMap = forwardRef<LiveMapHandle, {
  points: MapPoint[]; lines?: MapLine[]; markers?: MapMarker[]; selected?: string | null; height?: number;
  initial?: MapView; minZoom?: number; maxZoom?: number; glyph: 'plane' | 'ship';
  onSelect?: (id: string | null) => void; onMarker?: (id: string) => void; hoverText?: (id: string) => string;
  onView?: (b: MapBounds) => void; children?: React.ReactNode;
  density?: number;                  // below this zoom, draw a traffic-density layer instead of individual points
}>(function LiveMap({ points, lines = [], markers = [], selected, height = 560, initial, minZoom = 1, maxZoom = 13, glyph,
  onSelect, onMarker, hoverText, onView, children, density }, ref) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const landCanvas = useRef<HTMLCanvasElement | null>(null);
  const landView = useRef<{ cx: number; cy: number; S: number } | null>(null);
  const landPath = useRef<{ path: Path2D; rule: CanvasFillRule } | null>(null);   // the settled land shape, for land tests
  const [W, setW] = useState(900);
  const [land, setLand] = useState(landCache);
  const [fine, setFine] = useState<Poly[] | null>(fineCache);
  const view = useRef<{ cx: number; cy: number; zoom: number }>({ cx: 0, cy: 0, zoom: initial?.zoom ?? 1.6 });
  const [tick, setTick] = useState(0);               // bumps a redraw
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null);
  const screen = useRef<{ xs: Float32Array; ys: Float32Array; ids: string[] }>({ xs: new Float32Array(0), ys: new Float32Array(0), ids: [] });
  const markerScreen = useRef<{ x: number; y: number; r: number; id: string }[]>([]);
  const settle = useRef<ReturnType<typeof setTimeout> | null>(null);
  const viewCb = useRef<ReturnType<typeof setTimeout> | null>(null);
  const colors = useCssColor();
  const H = height;

  // initial centre
  const inited = useRef(false);
  if (!inited.current) {
    const S = TILE * 2 ** view.current.zoom;
    view.current.cx = worldX(initial?.lon ?? 20, S);
    view.current.cy = worldY(initial?.lat ?? 25, S);
    inited.current = true;
  }

  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(el); return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (land) return;
    fetch('/world-atlas/countries-50m.json').then((r) => r.json()).then((t) => {
      landCache = { land: feature(t, t.objects.land ?? t.objects.countries), borders: mesh(t, t.objects.countries, (a: any, b: any) => a !== b) };
      setLand(landCache);
    }).catch(() => {});
  }, [land]);

  const wantFine = view.current.zoom >= 4.5;
  useEffect(() => {
    if (!wantFine || fine) return;
    if (fineCache) { setFine(fineCache); return; }
    if (fineLoading) return;
    fineLoading = true;
    fetch('/world-atlas/land-10m.json').then((r) => r.json()).then((t) => {
      const fc: any = feature(t, t.objects.land);
      const polys: Poly[] = [];
      for (const f of fc.features ?? [fc]) {
        const g = f.geometry;
        const list = g.type === 'MultiPolygon' ? g.coordinates : [g.coordinates];
        for (const coords of list) {
          let w = 180, so = 90, e = -180, n = -90;
          for (const [x, y] of coords[0]) { if (x < w) w = x; if (x > e) e = x; if (y < so) so = y; if (y > n) n = y; }
          polys.push({ f: { type: 'Polygon', coordinates: coords }, w, s: so, e, n });
        }
      }
      fineCache = polys; setFine(polys); landView.current = null; setTick((x) => x + 1);
    }).catch(() => {}).finally(() => { fineLoading = false; });
  }, [wantFine, fine, tick]);

  const minZ = Math.max(minZoom, Math.log2(H / TILE));            // the world always fills the height
  const S = () => TILE * 2 ** view.current.zoom;

  const clampView = () => {
    const v = view.current;
    v.zoom = Math.max(minZ, Math.min(maxZoom, v.zoom));
    const s = S();
    v.cy = Math.max(H / 2, Math.min(s - H / 2, v.cy));
    v.cx = ((v.cx % s) + s) % s;                                    // wrap around the antimeridian
  };

  const bounds = (): MapBounds => {
    const v = view.current, s = S();
    return { west: lonOf(v.cx - W / 2, s), east: lonOf(v.cx + W / 2, s), north: latOf(Math.max(0, v.cy - H / 2), s), south: latOf(Math.min(s, v.cy + H / 2), s),
      zoom: v.zoom, lon: lonOf(v.cx, s), lat: latOf(v.cy, s), width: W, height: H };
  };
  const emitView = () => {
    if (!onView) return;
    if (viewCb.current) clearTimeout(viewCb.current);
    viewCb.current = setTimeout(() => onView(bounds()), 250);
  };
  const changed = (full = false) => {
    clampView();
    setTick((t) => t + 1);
    emitView();
    if (settle.current) clearTimeout(settle.current);
    settle.current = setTimeout(() => { landView.current = null; setTick((t) => t + 1); }, full ? 0 : 160);
  };

  useImperativeHandle(ref, () => ({
    flyTo: (p) => {
      const v = view.current;
      if (p.zoom != null) v.zoom = p.zoom;
      const s = S();
      if (p.lon != null) v.cx = worldX(p.lon, s);
      if (p.lat != null) v.cy = worldY(p.lat, s);
      changed(true);
    },
    fitBounds: ([w, so, e, n]) => {
      const z0 = 0, s0 = TILE * 2 ** z0;
      const dx = Math.abs(worldX(e, s0) - worldX(w, s0)) || 1e-6, dy = Math.abs(worldY(so, s0) - worldY(n, s0)) || 1e-6;
      const z = Math.log2(Math.min((W * 0.9) / dx, (H * 0.9) / dy));
      const v = view.current;
      v.zoom = Math.max(minZ, Math.min(maxZoom, z));
      const s = S();
      v.cx = (worldX(w, s) + worldX(e, s)) / 2; v.cy = (worldY(so, s) + worldY(n, s)) / 2;
      changed(true);
    },
  }));

  useEffect(() => { clampView(); emitView(); }, [W, H]);           // eslint-disable-line react-hooks/exhaustive-deps

  // ── draw ──
  useEffect(() => {
    const cv = canvas.current; if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    if (cv.width !== W * dpr || cv.height !== H * dpr) { cv.width = W * dpr; cv.height = H * dpr; landView.current = null; }
    const ctx = cv.getContext('2d')!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const v = view.current, s = S();
    const ox = W / 2 - v.cx, oy = H / 2 - v.cy;                      // world px → screen px
    // the world repeats east–west: every copy that overlaps the view is drawn, so panning is continuous
    const copies: number[] = [];
    for (let j = Math.floor(-ox / s) - 1; j <= Math.ceil((W - ox) / s); j++) if (ox + j * s < W && ox + j * s + s > 0) copies.push(j * s);
    const c = colors.resolve;
    ctx.clearRect(0, 0, W, H);                                      // the sea: an opaque base, then a blue tint
    ctx.fillStyle = c('rgb(var(--c-surface-1))'); ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = c('rgb(var(--c-blue) / 0.2)'); ctx.fillRect(0, 0, W, H);

    // land: a fresh render when the view is settled, else the last render shifted / scaled
    if (land) {
      if (!landView.current) {
        const lc = landCanvas.current ?? (landCanvas.current = document.createElement('canvas'));
        lc.width = W * dpr; lc.height = H * dpr;
        const lx = lc.getContext('2d')!;
        lx.setTransform(dpr, 0, 0, dpr, 0, 0);
        lx.clearRect(0, 0, W, H);
        const lp = new Path2D();
        let lpRule: CanvasFillRule = 'nonzero';
        for (const k of copies) {
          const proj = geoMercator().scale(s / (2 * Math.PI)).translate([s / 2 + ox + k, s / 2 + oy]).clipExtent([[0, 0], [W, H]]);
          const path = geoPath(proj, lx);
          lx.beginPath();
          let rule: CanvasFillRule = 'nonzero';
          if (fine && v.zoom >= 4.5) {
            // planar projection: ring winding doesn't matter (d3's spherical fill inverts reversed rings)
            const tf = geoTransform({ point(lon: number, lat: number) { (this as any).stream.point(worldX(lon, s) + ox + k, worldY(lat, s) + oy); } });
            const flat = geoPath(tf, lx), flatP = geoPath(tf, lp as any);
            rule = 'evenodd'; lpRule = 'evenodd';
            const b = bounds(), pad = 1;
            const wrapLon = (b.east - b.west) >= 360;
            for (const pg of fine) {
              if (pg.n < b.south - pad || pg.s > b.north + pad) continue;
              if (!wrapLon && !(pg.e >= b.west - pad && pg.w <= b.east + pad) && !(pg.e >= b.west - 360 - pad && pg.w <= b.east - 360 + pad)
                && !(pg.e >= b.west + 360 - pad && pg.w <= b.east + 360 + pad)) continue;
              flat(pg.f); flatP(pg.f);
            }
          } else { path(land.land); geoPath(proj, lp as any)(land.land); }
          lx.fillStyle = c('rgb(var(--c-border-strong) / 0.6)'); lx.fill(rule);          // land, clearly lighter than the sea
          lx.beginPath(); path(land.borders); lx.strokeStyle = c('rgb(var(--c-text-tertiary) / 0.35)'); lx.lineWidth = 0.6; lx.stroke();
        }
        landView.current = { cx: v.cx, cy: v.cy, S: s };
        landPath.current = { path: lp, rule: lpRule };
      }
      const lv = landView.current!;
      const k = s / lv.S;
      // the cached image's world origin, re-expressed in the current view
      const dx = W / 2 - v.cx - (W / 2 - lv.cx) * k, dy = H / 2 - v.cy - (H / 2 - lv.cy) * k;
      // horizontal wrap: try the shift that keeps the image nearest
      const shifts = [0, s, -s].map((w) => dx + w).sort((a, b) => Math.abs(a) - Math.abs(b));
      ctx.drawImage(landCanvas.current!, 0, 0, W * dpr, H * dpr, shifts[0], dy, W * k, H * k);
    }

    const z = v.zoom;
    const project = (lon: number, lat: number): [number, number] => [worldX(lon, s) + ox, worldY(lat, s) + oy];
    // lines (tracks, routes): longitudes unwrapped so a route across the date line stays one stroke
    for (const ln of lines) {
      if (ln.coords.length < 2) continue;
      let prev: number | null = null;
      const pts = ln.coords.map(([lon, lat]) => {
        let L = lon;
        if (prev != null) { while (L - prev > 180) L -= 360; while (L - prev < -180) L += 360; }
        prev = L;
        return project(L, lat);
      });
      for (const k of copies) {
        ctx.beginPath();
        pts.forEach(([x, y], i) => (i ? ctx.lineTo(x + k, y) : ctx.moveTo(x + k, y)));
        ctx.strokeStyle = c(ln.color); ctx.lineWidth = ln.width ?? 1.6; ctx.setLineDash(ln.dash ?? []); ctx.stroke(); ctx.setLineDash([]);
      }
    }

    const taken = new Set<string>();                                 // label collision grid (60 × 14 px cells)
    const labelOk = (x: number, y: number) => {
      const k = `${Math.floor(x / 60)}:${Math.floor(y / 14)}`;
      if (taken.has(k)) return false;
      taken.add(k); return true;
    };

    // markers (ports, chokepoints, airports)
    markerScreen.current = [];
    ctx.font = '10px ui-sans-serif, system-ui';
    for (const m of markers) for (const k of copies) {
      const [x0, y] = project(m.lon, m.lat), x = x0 + k;
      if (x < -20 || x > W + 20 || y < -20 || y > H + 20) continue;
      const r = (m.r ?? 4) * Math.max(0.45, Math.min(1, (z - 1) / 4));     // smaller at world zoom
      ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
      if (m.fill) { ctx.fillStyle = c(m.color); ctx.globalAlpha = 0.25; ctx.fill(); ctx.globalAlpha = 1; }
      ctx.strokeStyle = c(m.color); ctx.lineWidth = 1.2; ctx.stroke();
      if (m.label && (z >= 5 || (z >= 3.5 && r >= 7)) && labelOk(x, y)) { ctx.fillStyle = c('rgb(var(--c-text-secondary))'); ctx.fillText(m.label, x + r + 3, y + 3); }
      if (m.id) markerScreen.current.push({ x, y, r: Math.max(r, 6), id: m.id });
    }

    // points
    const n = points.length * copies.length;
    const xs = new Float32Array(n), ys = new Float32Array(n), ids: string[] = new Array(n);
    let m = 0;
    const glyphs = z >= (glyph === 'plane' ? 5.5 : 7);
    // approximate positions on land are dropped once zoomed in (only while the land image is current)
    const lv0 = landView.current;
    const landTest = z >= 6.5 && landPath.current && lv0 && lv0.S === s && lv0.cx === v.cx && lv0.cy === v.cy ? landPath.current : null;
    const dot = glyph === 'plane' ? (z < 3 ? 1.8 : z < 5 ? 2.2 : 2.6) : (z < 3 ? 1.7 : z < 5 ? 2 : z < 7 ? 2.4 : 2.8);
    const labels = z >= (glyph === 'plane' ? 7.5 : 11);
    let sel: { x: number; y: number; p: MapPoint } | null = null;
    const dense = density != null && z < density;
    const cell = 2.5, gw = Math.ceil(W / cell), gh = Math.ceil(H / cell);
    const counts = dense ? new Float32Array(gw * gh) : null;
    const byColor = new Map<string, number[]>();                     // batch dots by colour
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      const x0 = worldX(p.lon, s) + ox;
      const y = worldY(p.lat, s) + oy;
      if (y < -10 || y > H + 10) continue;
      for (const k of copies) {
      const x = x0 + k;
      if (x < -10 || x > W + 10) continue;
      if (p.approx && p.id !== selected && landTest && ctx.isPointInPath(landTest.path, x * dpr, y * dpr, landTest.rule)) continue;
      xs[m] = x; ys[m] = y; ids[m] = p.id; m++;
      if (p.id === selected) { if (!sel || Math.abs(x - W / 2) < Math.abs(sel.x - W / 2)) sel = { x, y, p }; continue; }
      if (counts) { const gx = Math.floor(x / cell), gy = Math.floor(y / cell); if (gx >= 0 && gy >= 0 && gx < gw && gy < gh) counts[gy * gw + gx] += 1; continue; }
      if (glyphs || p.big || p.ring) {
        drawGlyph(ctx, glyph, x, y, p, glyphs, c, dot);
      } else {
        const arr = byColor.get(p.color) ?? []; arr.push(x, y); byColor.set(p.color, arr);
      }
      if (labels && p.label && m < 2000 && labelOk(x, y)) { ctx.fillStyle = c('rgb(var(--c-text-tertiary))'); ctx.font = '9px ui-monospace, monospace'; ctx.fillText(p.label, x + 6, y - 4); }
      }
    }
    if (counts) drawDensity(ctx, counts, gw, gh);
    for (const [col, arr] of byColor) {
      ctx.fillStyle = c(col);
      for (let i = 0; i < arr.length; i += 2) ctx.fillRect(arr[i] - dot / 2, arr[i + 1] - dot / 2, dot, dot);
    }
    if (sel) {
      ctx.beginPath(); ctx.arc(sel.x, sel.y, 11, 0, 2 * Math.PI);
      ctx.strokeStyle = c('rgb(var(--c-text-primary))'); ctx.lineWidth = 1.5; ctx.stroke();
      drawGlyph(ctx, glyph, sel.x, sel.y, { ...sel.p, big: true }, true, c, dot);
    }
    screen.current = { xs: xs.subarray(0, m), ys: ys.subarray(0, m), ids: ids.slice(0, m) };
  }, [tick, W, H, land, fine, points, lines, markers, selected, glyph, density]);     // eslint-disable-line react-hooks/exhaustive-deps

  // ── interaction ──
  const drag = useRef<{ x: number; y: number; cx: number; cy: number; moved: boolean } | null>(null);
  const at = (e: { clientX: number; clientY: number }) => { const b = canvas.current!.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top] as const; };
  const pick = (x: number, y: number, r = 8) => {
    const { xs, ys, ids } = screen.current;
    let best = -1, bd = r * r;
    for (let i = 0; i < xs.length; i++) { const d = (xs[i] - x) ** 2 + (ys[i] - y) ** 2; if (d < bd) { bd = d; best = i; } }
    return best >= 0 ? ids[best] : null;
  };
  const zoomAt = (x: number, y: number, dz: number) => {
    const v = view.current;
    const wx = v.cx + (x - W / 2), wy = v.cy + (y - H / 2);
    const nz = Math.max(minZ, Math.min(maxZoom, v.zoom + dz));
    const k = 2 ** (nz - v.zoom);
    v.zoom = nz;
    v.cx = wx * k - (x - W / 2); v.cy = wy * k - (y - H / 2);
    changed();
  };
  useEffect(() => {
    const cv = canvas.current; if (!cv) return;
    const wheel = (e: WheelEvent) => { e.preventDefault(); const [x, y] = at(e); zoomAt(x, y, -e.deltaY * (e.ctrlKey ? 0.01 : 0.0025)); };
    cv.addEventListener('wheel', wheel, { passive: false });
    return () => cv.removeEventListener('wheel', wheel);
  });

  const hoverLabel = hover && hoverText ? hoverText(hover.id) : null;
  const zoomBtn = 'w-7 h-7 grid place-items-center bg-surface-1/90 border border-border text-text-secondary hover:text-text-primary';
  return (
    <div ref={wrap} className="relative w-full select-none" style={{ height: H }}>
      <span ref={colors.probe} className="hidden" aria-hidden="true" />
      <canvas ref={canvas} style={{ width: W, height: H, touchAction: 'none' }} className="block cursor-grab active:cursor-grabbing border border-border"
        role="img" aria-label="Live traffic map"
        onPointerDown={(e) => { const v = view.current; drag.current = { x: e.clientX, y: e.clientY, cx: v.cx, cy: v.cy, moved: false }; (e.target as Element).setPointerCapture(e.pointerId); }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (d) {
            if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) d.moved = true;
            view.current.cx = d.cx - (e.clientX - d.x); view.current.cy = d.cy - (e.clientY - d.y);
            changed(); setHover(null); return;
          }
          const [x, y] = at(e); const id = pick(x, y);
          setHover((h) => (id ? (h?.id === id && Math.abs(h.x - x) < 2 && Math.abs(h.y - y) < 2 ? h : { id, x, y }) : null));
        }}
        onPointerUp={(e) => {
          const d = drag.current; drag.current = null;
          if (d && !d.moved) {
            const [x, y] = at(e);
            const mk = markerScreen.current.find((m) => (m.x - x) ** 2 + (m.y - y) ** 2 <= m.r * m.r);
            const id = pick(x, y, 10);
            if (id) onSelect?.(id); else if (mk && onMarker) onMarker(mk.id); else onSelect?.(null);
          }
        }}
        onPointerLeave={() => setHover(null)}
        onDoubleClick={(e) => { const [x, y] = at(e); zoomAt(x, y, 1); }} />
      <div className="absolute top-2 right-2 flex flex-col gap-1">
        <button className={zoomBtn} aria-label="Zoom in" onClick={() => zoomAt(W / 2, H / 2, 1)}><Plus className="w-3.5 h-3.5" /></button>
        <button className={zoomBtn} aria-label="Zoom out" onClick={() => zoomAt(W / 2, H / 2, -1)}><Minus className="w-3.5 h-3.5" /></button>
        <button className={zoomBtn} aria-label="Whole world" title="Whole world" onClick={() => { view.current.zoom = minZ + 0.2; const s = S(); view.current.cx = worldX(20, s); view.current.cy = worldY(25, s); changed(true); }}><Globe2 className="w-3.5 h-3.5" /></button>
      </div>
      {hoverLabel && hover && (
        <div className="absolute pointer-events-none z-10 px-2 py-1 text-[11px] bg-surface-1/95 border border-border text-text-primary whitespace-pre font-mono shadow"
          style={{ left: Math.min(hover.x + 12, W - 240), top: Math.max(4, hover.y - 10) }}>{hoverLabel}</div>)}
      {children}
    </div>
  );
});

// traffic density: log-scaled counts per 2.5 px cell through a navy → teal → amber → white ramp,
// drawn at cell resolution and scaled up with smoothing so lanes read as soft glowing lines
const RAMP: [number, number, number][] = [[24, 70, 140], [0, 150, 200], [60, 210, 190], [250, 210, 90], [255, 250, 235]];
function drawDensity(ctx: CanvasRenderingContext2D, counts: Float32Array, gw: number, gh: number) {
  const img = new ImageData(gw, gh);
  const ref = Math.log1p(30);
  for (let i = 0; i < counts.length; i++) {
    const c = counts[i];
    if (!c) continue;
    const t = Math.min(1, Math.log1p(c) / ref) * (RAMP.length - 1);
    const k = Math.min(RAMP.length - 2, Math.floor(t)), f = t - k, a = RAMP[k], b = RAMP[k + 1];
    const o = i * 4;
    img.data[o] = a[0] + (b[0] - a[0]) * f; img.data[o + 1] = a[1] + (b[1] - a[1]) * f; img.data[o + 2] = a[2] + (b[2] - a[2]) * f;
    img.data[o + 3] = 120 + 135 * Math.min(1, t / 2);
  }
  const off = document.createElement('canvas');
  off.width = gw; off.height = gh;
  off.getContext('2d')!.putImageData(img, 0, 0);
  ctx.save(); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(off, 0, 0, gw * 2.5, gh * 2.5);
  ctx.restore();
}

function drawGlyph(ctx: CanvasRenderingContext2D, kind: 'plane' | 'ship', x: number, y: number, p: MapPoint, detailed: boolean,
  c: (s: string) => string, dot: number) {
  const col = c(p.color);
  const size = (p.big ? 1.5 : p.approx ? 0.75 : 1) * (detailed ? (kind === 'plane' ? 6 : 5) : dot + 1.5);
  if (kind === 'ship' && detailed && (p.heading == null || !p.moving)) {
    // stationary or heading unknown: a hull at its reported heading (or north), outlined when the
    // heading is unknown so it doesn't look like a precise course
    ctx.save(); ctx.translate(x, y); ctx.rotate(((p.heading ?? 0) * Math.PI) / 180);
    ctx.beginPath();
    ctx.moveTo(0, -size); ctx.lineTo(size * 0.42, -size * 0.25); ctx.lineTo(size * 0.42, size * 0.75); ctx.lineTo(-size * 0.42, size * 0.75); ctx.lineTo(-size * 0.42, -size * 0.25);
    ctx.closePath();
    if (p.heading == null) { ctx.strokeStyle = col; ctx.lineWidth = 1.2; ctx.stroke(); } else { ctx.fillStyle = col; ctx.fill(); }
    ctx.restore();
    return;
  }
  if (p.heading != null && (detailed || p.big) && (kind === 'plane' || p.moving)) {
    ctx.save(); ctx.translate(x, y); ctx.rotate((p.heading * Math.PI) / 180);
    ctx.beginPath();
    if (kind === 'plane') {                          // simple aircraft silhouette
      ctx.moveTo(0, -size); ctx.lineTo(size * 0.18, -size * 0.3); ctx.lineTo(size, size * 0.15); ctx.lineTo(size * 0.18, size * 0.05);
      ctx.lineTo(size * 0.12, size * 0.65); ctx.lineTo(size * 0.42, size * 0.9); ctx.lineTo(0, size * 0.78); ctx.lineTo(-size * 0.42, size * 0.9);
      ctx.lineTo(-size * 0.12, size * 0.65); ctx.lineTo(-size * 0.18, size * 0.05); ctx.lineTo(-size, size * 0.15); ctx.lineTo(-size * 0.18, -size * 0.3);
    } else {                                          // hull pointing along the heading
      ctx.moveTo(0, -size); ctx.lineTo(size * 0.45, -size * 0.2); ctx.lineTo(size * 0.45, size * 0.8); ctx.lineTo(-size * 0.45, size * 0.8); ctx.lineTo(-size * 0.45, -size * 0.2);
    }
    ctx.closePath(); ctx.fillStyle = col; ctx.fill();
    if (p.ring) { ctx.strokeStyle = c(p.ring); ctx.lineWidth = 1.2; ctx.stroke(); }
    ctx.restore();
  } else {
    ctx.beginPath(); ctx.arc(x, y, size / 2 + 0.5, 0, 2 * Math.PI); ctx.fillStyle = col; ctx.fill();
    if (p.ring) { ctx.strokeStyle = c(p.ring); ctx.lineWidth = 1.2; ctx.stroke(); }
  }
}

/** Great-circle points between two lon/lat positions (for route arcs). */
export function greatCircle(a: [number, number], b: [number, number], n = 64): [number, number][] {
  const r = Math.PI / 180;
  const [l1, p1] = [a[0] * r, a[1] * r], [l2, p2] = [b[0] * r, b[1] * r];
  const d = 2 * Math.asin(Math.sqrt(Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2));
  if (d === 0) return [a, b];
  const out: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const f = i / n, A = Math.sin((1 - f) * d) / Math.sin(d), B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(p1) * Math.cos(l1) + B * Math.cos(p2) * Math.cos(l2);
    const y = A * Math.cos(p1) * Math.sin(l1) + B * Math.cos(p2) * Math.sin(l2);
    const z = A * Math.sin(p1) + B * Math.sin(p2);
    out.push([Math.atan2(y, x) / r, Math.atan2(z, Math.sqrt(x * x + y * y)) / r]);
  }
  return out;
}

/** Project a position forward along its track (dead reckoning) — for snapshots minutes old. */
export function project(lon: number, lat: number, trackDeg: number, knots: number, seconds: number): [number, number] {
  const dist = (knots * 1.852 * seconds) / 3600 / 6371;          // radians
  const r = Math.PI / 180, th = trackDeg * r, p1 = lat * r, l1 = lon * r;
  const p2 = Math.asin(Math.sin(p1) * Math.cos(dist) + Math.cos(p1) * Math.sin(dist) * Math.cos(th));
  const l2 = l1 + Math.atan2(Math.sin(th) * Math.sin(dist) * Math.cos(p1), Math.cos(dist) - Math.sin(p1) * Math.sin(p2));
  return [((l2 / r + 540) % 360) - 180, p2 / r];
}

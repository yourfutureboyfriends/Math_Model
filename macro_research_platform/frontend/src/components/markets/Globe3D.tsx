// 3D globe for MAP: an orthographic projection drawn on canvas (smooth at 60 fps), coloured by the
// same layer as the flat map. Drag to rotate, wheel to zoom, click a country to select it (the
// globe turns to it); it spins slowly while idle.
import { useEffect, useMemo, useRef, useState } from 'react';
import { geoCentroid, geoContains, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { Topology } from '@/lib/topo';
import { useCssColor } from './cssColor';

type Feat = { iso: string | undefined; name: string; f: any };

export function Globe3D({ topo, numToIso, fill, selected, onSelect, onHover, height }: {
  topo: Topology; numToIso: Record<string, string>; fill: (iso: string | undefined) => string; selected: string | null;
  onSelect: (iso: string) => void; onHover: (h: { iso: string; name: string; x: number; y: number } | null) => void; height: number;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [W, setW] = useState(900);
  const rot = useRef<[number, number, number]>([-10, -20, 0]);
  const zoom = useRef(1);
  const drag = useRef<{ x: number; y: number; r: [number, number, number]; moved: boolean } | null>(null);
  const idleSince = useRef(performance.now());
  const anim = useRef<{ from: [number, number]; to: [number, number]; t0: number } | null>(null);
  const colors = useCssColor();
  const feats: Feat[] = useMemo(() => {
    const fc: any = feature(topo as any, (topo as any).objects.countries);
    return fc.features.map((f: any) => ({ iso: numToIso[String(f.id)], name: f.properties?.name ?? '', f }));
  }, [topo, numToIso]);
  const fillRef = useRef(fill); fillRef.current = fill;
  const selRef = useRef(selected); selRef.current = selected;

  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(el); return () => ro.disconnect();
  }, []);

  // turn to the selected country
  useEffect(() => {
    if (!selected) return;
    const ft = feats.find((x) => x.iso === selected);
    if (!ft) return;
    const [lon, lat] = geoCentroid(ft.f);
    anim.current = { from: [-rot.current[0], -rot.current[1]], to: [lon, lat], t0: performance.now() };
  }, [selected, feats]);

  useEffect(() => {
    const cv = canvas.current; if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = W * dpr; cv.height = height * dpr;
    const ctx = cv.getContext('2d')!;
    ctx.scale(dpr, dpr);
    const proj = geoOrthographic().clipAngle(90).precision(0.6);
    const path = geoPath(proj, ctx);
    const grat = geoGraticule10();
    let raf = 0, last = performance.now();
    const css = (v: string) => colors.resolve(`rgb(var(${v}))`);
    const draw = (now: number) => {
      const dt = Math.min(64, now - last); last = now;
      if (anim.current) {
        const k = Math.min(1, (now - anim.current.t0) / 900);
        const e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
        const [lon, lat] = geoInterpolate(anim.current.from, anim.current.to)(e);
        rot.current = [-lon, -lat, 0];
        if (k >= 1) { anim.current = null; idleSince.current = now; }
      } else if (!drag.current && now - idleSince.current > 2500) {
        rot.current = [rot.current[0] + dt * 0.006, rot.current[1], 0];        // slow idle spin
      }
      const r = (Math.min(W, height) / 2 - 14) * zoom.current;
      proj.scale(r).translate([W / 2, height / 2]).rotate(rot.current);
      ctx.clearRect(0, 0, W, height);
      // atmosphere glow
      const g = ctx.createRadialGradient(W / 2, height / 2, r * 0.92, W / 2, height / 2, r * 1.12);
      g.addColorStop(0, colors.resolve('rgb(var(--c-blue) / 0.25)'));
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(W / 2, height / 2, r * 1.12, 0, 2 * Math.PI); ctx.fill();
      // ocean with a soft light from the upper left
      const o = ctx.createRadialGradient(W / 2 - r * 0.35, height / 2 - r * 0.4, r * 0.1, W / 2, height / 2, r);
      o.addColorStop(0, css('--c-surface-3')); o.addColorStop(1, css('--c-surface-1'));
      ctx.fillStyle = o; ctx.beginPath(); path({ type: 'Sphere' } as any); ctx.fill();
      ctx.strokeStyle = colors.resolve('rgb(var(--c-border) / 0.5)'); ctx.lineWidth = 0.5;
      ctx.beginPath(); path(grat as any); ctx.stroke();
      // countries
      const bg = css('--c-bg');
      for (const ft of feats) {
        ctx.beginPath(); path(ft.f);
        ctx.fillStyle = colors.resolve(fillRef.current(ft.iso)); ctx.fill();
        ctx.strokeStyle = bg; ctx.lineWidth = 0.4; ctx.stroke();
      }
      const sel = selRef.current && feats.find((x) => x.iso === selRef.current);
      if (sel) { ctx.beginPath(); path(sel.f); ctx.strokeStyle = css('--c-text-primary'); ctx.lineWidth = 1.6; ctx.stroke(); }
      ctx.beginPath(); path({ type: 'Sphere' } as any); ctx.strokeStyle = colors.resolve('rgb(var(--c-border))'); ctx.lineWidth = 1; ctx.stroke();
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    const at = (e: PointerEvent | MouseEvent) => {
      const b = cv.getBoundingClientRect();
      return [e.clientX - b.left, e.clientY - b.top] as [number, number];
    };
    const hit = (p: [number, number]) => {
      const ll = proj.invert?.(p);
      if (!ll) return null;
      // the point must be on the visible hemisphere
      const [cx, cy] = [W / 2, height / 2], rr = proj.scale();
      if ((p[0] - cx) ** 2 + (p[1] - cy) ** 2 > rr * rr) return null;
      return feats.find((x) => geoContains(x.f, ll)) ?? null;
    };
    const down = (e: PointerEvent) => { drag.current = { x: e.clientX, y: e.clientY, r: [...rot.current] as any, moved: false }; anim.current = null; cv.setPointerCapture(e.pointerId); };
    const move = (e: PointerEvent) => {
      const d = drag.current;
      if (d) {
        const k = 0.25 / zoom.current;
        if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) d.moved = true;
        rot.current = [d.r[0] + (e.clientX - d.x) * k, Math.max(-85, Math.min(85, d.r[1] - (e.clientY - d.y) * k)), 0];
        idleSince.current = performance.now();
        onHover(null);
        return;
      }
      const p = at(e), f = hit(p);
      if (f) idleSince.current = performance.now();
      onHover(f && f.iso ? { iso: f.iso, name: f.name, x: p[0], y: p[1] } : null);
    };
    const up = (e: PointerEvent) => {
      const d = drag.current; drag.current = null;
      idleSince.current = performance.now();
      if (d && !d.moved) { const f = hit(at(e)); if (f?.iso) onSelect(f.iso); }
    };
    const wheel = (e: WheelEvent) => { e.preventDefault(); zoom.current = Math.max(0.8, Math.min(6, zoom.current * (e.deltaY < 0 ? 1.12 : 0.9))); idleSince.current = performance.now(); };
    cv.addEventListener('pointerdown', down); cv.addEventListener('pointermove', move); cv.addEventListener('pointerup', up);
    const leave = () => onHover(null);
    cv.addEventListener('pointerleave', leave); cv.addEventListener('wheel', wheel, { passive: false });
    return () => {
      cancelAnimationFrame(raf);
      cv.removeEventListener('pointerdown', down); cv.removeEventListener('pointermove', move); cv.removeEventListener('pointerup', up);
      cv.removeEventListener('pointerleave', leave); cv.removeEventListener('wheel', wheel);
    };
  }, [W, height, feats]);

  return (
    <div ref={wrap} className="relative w-full" style={{ height }}>
      <span ref={colors.probe} className="hidden" aria-hidden="true" />
      <canvas ref={canvas} style={{ width: W, height, touchAction: 'none' }} className="cursor-grab active:cursor-grabbing block" role="img" aria-label="3D globe" />
      <div className="absolute bottom-2 left-2 text-[10px] text-text-tertiary pointer-events-none">drag to rotate · wheel to zoom · click a country</div>
    </div>
  );
}

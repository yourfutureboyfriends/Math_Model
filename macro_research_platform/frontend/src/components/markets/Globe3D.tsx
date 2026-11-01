import { useEffect, useMemo, useRef, useState } from 'react';
import { geoBounds, geoCentroid, geoContains, geoDistance, geoGraticule10, geoInterpolate, geoOrthographic, geoPath } from 'd3-geo';
import { globeCountries } from './atlasGeometry';
import type { Topology } from '@/lib/topo';
import { EXCHANGES, exchangeById, exchangeLabels } from './exchanges';


type Feat = { iso: string | undefined; name: string; bounds:[[number,number],[number,number]]; f: any };

export function Globe3D({ topo, numToIso, fill, selected, onSelect, onHover, height, showExchanges=true, focusedExchange=null, onExchange,onReset }: {
  topo: Topology; numToIso: Record<string, string>; fill: (iso: string | undefined) => string; selected: string | null;
  onSelect: (iso: string) => void; onHover: (h: { iso: string; name: string; x: number; y: number } | null) => void; height: number; showExchanges?:boolean; focusedExchange?:string|null; onExchange?:(id:string)=>void;onReset?:()=>void;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [W, setW] = useState(900);
  const rot = useRef<[number, number, number]>([-10, -20, 0]);
  const zoom = useRef(1);
  const drag = useRef<{ x: number; y: number; r: [number, number, number]; moved: boolean } | null>(null);
  const invalidate=useRef<()=>void>(()=>{});
  const callbacks=useRef({onSelect,onHover,onExchange});callbacks.current={onSelect,onHover,onExchange};
  const anim = useRef<{ from: [number, number]; to: [number, number]; t0: number } | null>(null);
  const exchangeRef=useRef({show:showExchanges,focused:focusedExchange});exchangeRef.current={show:showExchanges,focused:focusedExchange};
  const feats: Feat[] = useMemo(() => {
    return globeCountries(topo).map((f: any) => ({ iso: numToIso[String(f.id)], name: f.properties?.name ?? '', bounds:geoBounds(f), f }));
  }, [topo, numToIso]);
  const fillRef = useRef(fill); fillRef.current = fill;
  const selRef = useRef(selected); selRef.current = selected;

  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(el); return () => ro.disconnect();
  }, []);

  useEffect(()=>{invalidate.current();},[fill,showExchanges]);

  // turn to the selected country
  useEffect(() => {
    if (!selected&&!focusedExchange) return;
    const ft = feats.find((x) => x.iso === selected);
    const exchange=exchangeById(focusedExchange);
    if(!ft&&!exchange)return;
    const [lon, lat] = exchange?.point??geoCentroid(ft!.f);
    anim.current = { from: [-rot.current[0], -rot.current[1]], to: [lon, lat], t0: performance.now() };
    invalidate.current();
  }, [selected, focusedExchange, feats]);

  useEffect(() => {
    const cv = canvas.current; if (!cv) return;
    const dpr = Math.min(1.5, window.devicePixelRatio || 1);
    cv.width = W * dpr; cv.height = height * dpr;
    const ctx = cv.getContext('2d');if(!ctx)return;
    ctx.scale(dpr, dpr);
    const proj = geoOrthographic().clipAngle(90).precision(0.6);
    const path = geoPath(proj, ctx);
    const grat = geoGraticule10();
    let raf = 0, visible=true;
    const schedule=()=>{if(!raf&&visible&&!document.hidden)raf=requestAnimationFrame(draw);};
    invalidate.current=schedule;
    const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const visibility=()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0;}else schedule();};
    document.addEventListener('visibilitychange',visibility);
    const observer=typeof IntersectionObserver!=='undefined'?new IntersectionObserver(([e])=>{visible=e.isIntersecting;if(visible)schedule();else{cancelAnimationFrame(raf);raf=0;}}):null;
    observer?.observe(cv);
    const theme=new MutationObserver(schedule);theme.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme','data-skin','data-brand','style','class']});

    const draw = (now: number) => {
      raf=0;
      if (anim.current) {
        const k = reduced?1:Math.min(1, (now - anim.current.t0) / 650);
        const e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
        const [lon, lat] = geoInterpolate(anim.current.from, anim.current.to)(e);
        rot.current = [-lon, -lat, 0];
        if (k >= 1) anim.current = null;
      }
      const r = (Math.min(W, height) / 2 - 14) * zoom.current;
      proj.scale(r).translate([W / 2, height / 2]).rotate(rot.current);
      ctx.clearRect(0, 0, W, height);
      // atmosphere glow
      const g = ctx.createRadialGradient(W / 2, height / 2, r * 0.92, W / 2, height / 2, r * 1.12);
      g.addColorStop(0, 'rgba(70,150,185,.18)');
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(W / 2, height / 2, r * 1.12, 0, 2 * Math.PI); ctx.fill();
      // ocean with a soft light from the upper left
      const o = ctx.createRadialGradient(W / 2 - r * 0.35, height / 2 - r * 0.4, r * 0.1, W / 2, height / 2, r);
      o.addColorStop(0, '#152b40'); o.addColorStop(1, '#091623');
      ctx.fillStyle = o; ctx.beginPath(); path({ type: 'Sphere' } as any); ctx.fill();
      ctx.strokeStyle = '#294052'; ctx.lineWidth = 0.5;
      ctx.beginPath(); path(grat as any); ctx.stroke();
      // countries
      const bg = '#102332';
      for (const ft of feats) {
        ctx.beginPath(); path(ft.f);
        ctx.fillStyle = fillRef.current(ft.iso); ctx.fill();
        ctx.strokeStyle = bg; ctx.lineWidth = 0.4; ctx.stroke();
      }
      const sel = selRef.current && feats.find((x) => x.iso === selRef.current);
      if (sel) { ctx.beginPath(); path(sel.f); ctx.strokeStyle = '#fff2ce'; ctx.lineWidth = 1.6; ctx.stroke(); }
      ctx.beginPath(); path({ type: 'Sphere' } as any); ctx.strokeStyle = '#41596b'; ctx.lineWidth = 1; ctx.stroke();
      if(exchangeRef.current.show){
        const centre:[number,number]=[-rot.current[0],-rot.current[1]];
        const points=EXCHANGES.filter(e=>geoDistance(e.point,centre)<Math.PI/2-.025).map(e=>{const p=proj(e.point)!;return {...e,x:p[0],y:p[1]};});
        const labels=exchangeLabels(points,exchangeRef.current.focused);
        ctx.font='10px system-ui, sans-serif';ctx.textAlign='left';ctx.textBaseline='middle';
        for(const e of points){
          if(e.x<3||e.x>W-3||e.y<3||e.y>height-3)continue;
          ctx.beginPath();ctx.arc(e.x,e.y,e.id===exchangeRef.current.focused?4.5:3,0,Math.PI*2);ctx.fillStyle='#f3d596';ctx.fill();ctx.strokeStyle='#091623';ctx.lineWidth=1.5;ctx.stroke();
          if(labels.has(e.id)&&e.x+e.label.length*6+10<W){ctx.strokeStyle='#091623';ctx.lineWidth=3;ctx.strokeText(e.label,e.x+7,e.y-7);ctx.fillStyle='#f4e5c3';ctx.fillText(e.label,e.x+7,e.y-7);}
        }
      }
      if(anim.current)schedule();
    };
    schedule();

    const at = (e: PointerEvent | MouseEvent) => {
      const b = cv.getBoundingClientRect();
      return [(e.clientX-b.left)*W/(b.width||W),(e.clientY-b.top)*height/(b.height||height)] as [number, number];
    };
    const hit = (p: [number, number]) => {
      const ll = proj.invert?.(p);
      if (!ll) return null;
      // the point must be on the visible hemisphere
      const [cx, cy] = [W / 2, height / 2], rr = proj.scale();
      if ((p[0] - cx) ** 2 + (p[1] - cy) ** 2 > rr * rr) return null;
      return feats.find(x=>{const [[west,south],[east,north]]=x.bounds;return ll[1]>=south&&ll[1]<=north&&(west<=east?ll[0]>=west&&ll[0]<=east:ll[0]>=west||ll[0]<=east)&&geoContains(x.f,ll);})??null;
    };
    const exchangeAt=(p:[number,number])=>{
      if(!exchangeRef.current.show)return null;
      const centre:[number,number]=[-rot.current[0],-rot.current[1]];
      return EXCHANGES.filter(e=>geoDistance(e.point,centre)<Math.PI/2-.025).map(e=>({e,p:proj(e.point)!})).filter(e=>Math.hypot(e.p[0]-p[0],e.p[1]-p[1])<9).sort((a,b)=>Math.hypot(a.p[0]-p[0],a.p[1]-p[1])-Math.hypot(b.p[0]-p[0],b.p[1]-p[1]))[0]?.e;
    };
    const down = (e: PointerEvent) => { drag.current = { x: e.clientX, y: e.clientY, r: [...rot.current] as any, moved: false }; anim.current = null; cv.setPointerCapture(e.pointerId); };
    let hovered='',hoverFrame=0;
    let pointer:[number,number]|null=null;
    const hoverAt=()=>{
      hoverFrame=0;if(!pointer)return;
      const exchange=exchangeAt(pointer),f=exchange?{iso:exchange.iso,name:`${exchange.label} · ${exchange.city}`} :hit(pointer),id=exchange?.id??f?.iso??'';
      if(id!==hovered){hovered=id;callbacks.current.onHover(f&&f.iso?{iso:f.iso,name:f.name,x:0,y:0}:null);}
    };
    const move = (e: PointerEvent) => {
      const d = drag.current;
      if (d) {
        const k = 0.25 / zoom.current;
        if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 3) d.moved = true;
        rot.current = [d.r[0] + (e.clientX - d.x) * k, Math.max(-85, Math.min(85, d.r[1] - (e.clientY - d.y) * k)), 0];
        schedule();
        callbacks.current.onHover(null);
        return;
      }
      pointer=at(e);if(!hoverFrame)hoverFrame=requestAnimationFrame(hoverAt);
    };
    const up = (e: PointerEvent) => {
      const d = drag.current; drag.current = null;
      schedule();
      if(cv.hasPointerCapture?.(e.pointerId))cv.releasePointerCapture(e.pointerId);
      if(d&&!d.moved){const p=at(e),exchange=exchangeAt(p);if(exchange){callbacks.current.onExchange?.(exchange.id);return;}const f=hit(p);if(f?.iso)callbacks.current.onSelect(f.iso);}
    };
    const wheel = (e: WheelEvent) => { if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault(); zoom.current = Math.max(0.8, Math.min(6, zoom.current * (e.deltaY < 0 ? 1.12 : 0.9)));schedule(); };
    cv.addEventListener('pointerdown', down); cv.addEventListener('pointermove', move); cv.addEventListener('pointerup', up);
    const leave = () => {pointer=null;cancelAnimationFrame(hoverFrame);hoverFrame=0;hovered='';callbacks.current.onHover(null);};
    const cancel=()=>{drag.current=null;schedule();leave();};
    cv.addEventListener('pointercancel',cancel);
    cv.addEventListener('pointerleave', leave); cv.addEventListener('wheel', wheel, { passive: false });
    return () => {
      cancelAnimationFrame(raf);
      cancelAnimationFrame(hoverFrame);invalidate.current=()=>{};observer?.disconnect();theme.disconnect();document.removeEventListener('visibilitychange',visibility);cv.removeEventListener('pointercancel',cancel);
      cv.removeEventListener('pointerdown', down); cv.removeEventListener('pointermove', move); cv.removeEventListener('pointerup', up);
      cv.removeEventListener('pointerleave', leave); cv.removeEventListener('wheel', wheel);
    };
  }, [W, height, feats]);

  const reset=()=>{anim.current=null;rot.current=[-10,-20,0];zoom.current=1;invalidate.current();onReset?.();};
  const zoomBy=(factor:number)=>{zoom.current=Math.max(.8,Math.min(6,zoom.current*factor));invalidate.current();};
  return (
    <div ref={wrap} className="relative w-full" style={{ height }}>

      <canvas ref={canvas} style={{ width: '100%', height, touchAction: 'pan-y' }} tabIndex={0} onKeyDown={e=>{
        if(['+','=','-','Home','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))e.preventDefault();
        if(e.key==='+'||e.key==='=')zoomBy(1.2);else if(e.key==='-')zoomBy(1/1.2);else if(e.key==='Home')reset();
        else if(e.key.startsWith('Arrow')){anim.current=null;rot.current=[rot.current[0]+(e.key==='ArrowLeft'?-10:e.key==='ArrowRight'?10:0),Math.max(-85,Math.min(85,rot.current[1]+(e.key==='ArrowUp'?-10:e.key==='ArrowDown'?10:0))),0];invalidate.current();}
      }} className="cursor-grab active:cursor-grabbing block" role="img" aria-label="3D globe with country borders and stock exchange locations" />
      <div className="atlas-globe-tools"><button aria-label="Zoom globe in" onClick={()=>zoomBy(1.3)}>+</button><button aria-label="Zoom globe out" onClick={()=>zoomBy(1/1.3)}>−</button><button onClick={reset}>Reset globe</button></div>
      <div className="absolute bottom-2 left-2 text-[10px] text-[#91aabd] pointer-events-none">drag to rotate · Ctrl/⌘ + scroll to zoom · click a country</div>
    </div>
  );
}

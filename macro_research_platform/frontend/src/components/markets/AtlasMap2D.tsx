import { forwardRef, memo, useEffect, useId, useImperativeHandle, useRef, useState } from 'react';
import { projectPoint } from '@/lib/topo';
import { EXCHANGES, exchangeById, exchangeLabels } from './exchanges';
import { ATLAS_WIDTH as W, ATLAS_HEIGHT as H, HOME, constrainCamera, zoomCamera, type AtlasGeometry, type Camera } from './atlasGeometry';
export type AtlasHover={iso:string;name:string;x:number;y:number}|null;
export type AtlasMapHandle={zoom:(factor:number)=>void;reset:()=>void;region:(bounds:[number,number,number,number])=>void};
type Props={showExchanges?:boolean;focusedExchange?:string|null;onExchange?:(id:string)=>void;geo:AtlasGeometry;numToIso:Record<string,string>;fills:Record<string,string>;selected:string|null;labels:Record<string,string>;showLabels:boolean;title:string;onSelect:(iso:string)=>void;onHover:(hover:AtlasHover)=>void};
const CountryPaths=memo(function CountryPaths({geo,numToIso,fills}:{geo:AtlasGeometry;numToIso:Record<string,string>;fills:Record<string,string>}){
  return <>{geo.shapes.map(s=><path key={s.id+s.name} d={s.path} data-iso={numToIso[s.id]??''} data-country={s.name} fill={fills[numToIso[s.id]]??'var(--atlas-no-data)'} stroke="var(--atlas-border)" strokeWidth=".55" vectorEffect="non-scaling-stroke"/>)}</>;
});
export const AtlasMap2D=memo(forwardRef<AtlasMapHandle,Props>(function AtlasMap2D({geo,numToIso,fills,selected,labels,showLabels,title,onSelect,onHover,showExchanges=true,focusedExchange=null,onExchange},ref){
  const svg=useRef<SVGSVGElement>(null),camera=useRef<Camera>(HOME),frame=useRef(0),pending=useRef<Camera>(HOME);
  const [view,setView]=useState(HOME),[hoverId,setHoverId]=useState<string|null>(null);
  const drag=useRef<{x:number;y:number;view:Camera;moved:boolean}|null>(null);
  const gradient=useId().replace(/:/g,'');
  const update=(v:Camera)=>{camera.current=constrainCamera(v);pending.current=camera.current;if(!frame.current)frame.current=requestAnimationFrame(()=>{frame.current=0;setView(pending.current);});};
  useEffect(()=>()=>cancelAnimationFrame(frame.current),[]);
  useImperativeHandle(ref,()=>({zoom:f=>update(zoomCamera(camera.current,f)),reset:()=>update(HOME),region:b=>{
    const [x0,y0]=projectPoint(b[0],b[3],W),[x1,y1]=projectPoint(b[2],b[1],W);
    const k=Math.min(8,Math.max(1,Math.min(W/Math.max(1,x1-x0),H/Math.max(1,y1-y0))*.92));
    update({k,x:W/2-(x0+x1)/2*k,y:H/2-(y0+y1)/2*k});
  }}),[]);
  useEffect(()=>{const e=exchangeById(focusedExchange);if(!e)return;const [x,y]=projectPoint(...e.point,W);update({k:3.5,x:W/2-x*3.5,y:H/2-y*3.5});},[focusedExchange]);
  useEffect(()=>{
    if(!selected||focusedExchange)return;const s=geo.shapes.find(s=>numToIso[s.id]===selected);if(!s||camera.current.k>=2.5)return;
    update({k:2.5,x:W/2-s.centroid[0]*2.5,y:H/2-s.centroid[1]*2.5});
  },[selected,geo,numToIso,focusedExchange]);
  useEffect(()=>{
    const el=svg.current;if(!el)return;
    const wheel=(e:WheelEvent)=>{
      // Plain scrolling keeps scrolling the page; intentional zoom does not hijack the document.
      if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault();const r=el.getBoundingClientRect();
      update(zoomCamera(camera.current,Math.exp(-Math.max(-120,Math.min(120,e.deltaY))*.006),(e.clientX-r.left)*W/r.width,(e.clientY-r.top)*H/r.height));
    };
    el.addEventListener('wheel',wheel,{passive:false});return()=>el.removeEventListener('wheel',wheel);
  },[]);
  const hit=(target:EventTarget|null)=>target instanceof Element?target.closest<SVGPathElement>('path[data-country]'):null;
  const highlighted=geo.shapes.find(s=>numToIso[s.id]===selected),hovered=geo.shapes.find(s=>s.id===hoverId);
  const exchangePoints=EXCHANGES.map(e=>{const [x,y]=projectPoint(...e.point,W);return {...e,x:x*view.k+view.x,y:y*view.k+view.y};}).filter(e=>e.x>4&&e.x<W-4&&e.y>4&&e.y<H-4);
  const visibleLabels=exchangeLabels(exchangePoints,focusedExchange);
  return <svg ref={svg} className="atlas-map-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title} tabIndex={0}
    onKeyDown={e=>{if(e.key==='+'||e.key==='='){e.preventDefault();update(zoomCamera(camera.current,1.3));}if(e.key==='-'){e.preventDefault();update(zoomCamera(camera.current,1/1.3));}if(e.key==='Home'){e.preventDefault();update(HOME);}}}
    onPointerDown={e=>{if(e.button!==0)return;drag.current={x:e.clientX,y:e.clientY,view:camera.current,moved:false};e.currentTarget.setPointerCapture(e.pointerId);}}
    onPointerMove={e=>{
      const d=drag.current;if(d){const r=e.currentTarget.getBoundingClientRect();if(Math.abs(e.clientX-d.x)+Math.abs(e.clientY-d.y)>4)d.moved=true;if(d.moved){onHover(null);setHoverId(null);update({...d.view,x:d.view.x+(e.clientX-d.x)*W/r.width,y:d.view.y+(e.clientY-d.y)*H/r.height});}return;}
      const path=hit(e.target),id=path?.getAttribute('data-country')??'';
      if(hovered?.name===id||(!path&&!hoverId))return;
      const shape=path?geo.shapes.find(s=>s.name===id):null;setHoverId(shape?.id??null);
      onHover(shape?{iso:numToIso[shape.id]??'',name:shape.name,x:0,y:0}:null);
    }}
    onPointerUp={e=>{const d=drag.current;drag.current=null;if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);if(!d?.moved){const path=hit(document.elementFromPoint(e.clientX,e.clientY));const iso=path?.getAttribute('data-iso');if(iso)onSelect(iso);}}}
    onPointerCancel={()=>{drag.current=null;onHover(null);setHoverId(null);}}
    onPointerLeave={()=>{if(!drag.current){onHover(null);setHoverId(null);}}}
    onDoubleClick={e=>{const r=e.currentTarget.getBoundingClientRect();update(zoomCamera(camera.current,1.5,(e.clientX-r.left)*W/r.width,(e.clientY-r.top)*H/r.height));}}>
    <defs><radialGradient id={gradient}><stop stopColor="var(--atlas-ocean-light)"/><stop offset="1" stopColor="var(--atlas-ocean)"/></radialGradient></defs>
    <rect width={W} height={H} fill={`url(#${gradient})`}/>
    <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
      <path d={geo.sphere} fill="none" stroke="var(--atlas-graticule)" vectorEffect="non-scaling-stroke"/>
      <path d={geo.graticule} fill="none" stroke="var(--atlas-graticule)" strokeWidth=".45" vectorEffect="non-scaling-stroke" pointerEvents="none"/>
      <CountryPaths geo={geo} numToIso={numToIso} fills={fills}/>
      {hovered&&<path d={hovered.path} fill="none" stroke="var(--atlas-highlight)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" pointerEvents="none"/>}
      {highlighted&&<path d={highlighted.path} fill="none" stroke="var(--atlas-selected)" strokeWidth="1.8" vectorEffect="non-scaling-stroke" pointerEvents="none"/>}
      {showLabels&&geo.shapes.filter(s=>s.area*view.k*view.k>1700&&labels[numToIso[s.id]]).map(s=><text key={s.id} x={s.centroid[0]} y={s.centroid[1]} fontSize={10/view.k} textAnchor="middle" dominantBaseline="middle" fill="var(--atlas-label)" stroke="var(--atlas-ocean)" strokeWidth={2.5/view.k} paintOrder="stroke" pointerEvents="none">{labels[numToIso[s.id]]}</text>)}
    </g>
    {showExchanges&&<g className="atlas-exchanges">{exchangePoints.map(e=><g key={e.id} transform={`translate(${e.x} ${e.y})`} role="button" tabIndex={0} aria-label={`${e.name}, ${e.city}`} onPointerDown={event=>event.stopPropagation()} onPointerUp={event=>{event.stopPropagation();onExchange?.(e.id);}} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();onExchange?.(e.id);}}}>
      <title>{e.name} · {e.city} · approximate city location</title><circle r="9" fill="transparent"/><circle r={e.id===focusedExchange?4.5:3} fill="#f3d596" stroke="#091623" strokeWidth="1.5"/>
      {visibleLabels.has(e.id)&&e.x+e.label.length*6+10<W&&<text x="7" y="-7" fontSize="10" fill="#f4e5c3" stroke="#091623" strokeWidth="3" paintOrder="stroke">{e.label}</text>}
    </g>)}</g>}
  </svg>;
}));

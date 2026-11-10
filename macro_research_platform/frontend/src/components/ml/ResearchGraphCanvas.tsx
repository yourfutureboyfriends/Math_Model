import {useMemo,useRef,useState} from 'react';
import {layoutGraph} from './researchGraph';
import type {ResearchNode,ResearchEdge} from './researchGraph';

/** Explicit SVG scene avoids graph-series merge/layout state corrupting filtered node identities. */
export function ResearchGraphCanvas({nodes,edges,selected,onSelect,colors}:{nodes:ResearchNode[];edges:ResearchEdge[];selected:string|null;onSelect:(id:string)=>void;colors:Record<string,string>}){
 const [zoom,setZoom]=useState(1),[pan,setPan]=useState({x:0,y:0});const drag=useRef<{x:number;y:number;px:number;py:number}|null>(null);
 const scene=useMemo(()=>{
  const count=Math.max(1,...Object.values(nodes.reduce<Record<string,number>>((a,n)=>{const k=['feature','factor','paper'].includes(n.kind)?'inputs':n.kind;a[k]=(a[k]??0)+1;return a;},{})));
  const height=Math.max(600,count*39+100);
  const laid=layoutGraph(nodes).map(n=>({...n,x:n.x+40,y:55+(n.y-40)*(height-140)/640}));
  return {height,dense:count>24,positions:new Map(laid.map(n=>[n.id,n]))};
 },[nodes]);
 const adjacent=new Set(edges.filter(e=>e.source===selected||e.target===selected).flatMap(e=>[e.source,e.target]));
 return <div>
  <div className="flex items-center gap-2 px-4 py-2 text-xs"><button aria-label="Zoom out research graph" onClick={()=>setZoom(v=>Math.max(.5,v/1.25))} className="rounded border px-2 py-1">−</button><span>{Math.round(zoom*100)}%</span><button aria-label="Zoom in research graph" onClick={()=>setZoom(v=>Math.min(3,v*1.25))} className="rounded border px-2 py-1">+</button><button onClick={()=>{setZoom(1);setPan({x:0,y:0});}} className="rounded border px-2 py-1">Fit graph</button><span className="text-[var(--text-secondary)]">Drag background to pan · Select a node or use the inspector</span></div>
  <div style={{maxHeight:640,overflow:'auto'}}><svg role="group" aria-label="Interactive research evidence graph" viewBox={`0 0 1240 ${scene.height}`} width={1240} height={scene.height} style={{display:'block',touchAction:'none',cursor:drag.current?'grabbing':'grab'}}
   onPointerDown={e=>{if((e.target as Element).closest('[data-node]'))return;e.currentTarget.setPointerCapture(e.pointerId);drag.current={x:e.clientX,y:e.clientY,px:pan.x,py:pan.y};}}
   onPointerMove={e=>{if(!drag.current)return;const rect=e.currentTarget.getBoundingClientRect(),ratio=Math.max(1240/rect.width,scene.height/rect.height);setPan({x:drag.current.px+(e.clientX-drag.current.x)*ratio,y:drag.current.py+(e.clientY-drag.current.y)*ratio});}}
   onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}>
   <g transform={`translate(${pan.x} ${pan.y}) translate(620 ${scene.height/2}) scale(${zoom}) translate(-620 ${-scene.height/2})`}>
    {['Sources','Factors','Specialists','Shared model','Forecasts','Saved outputs'].map((label,i)=><text key={label} x={80+i*200} y={23} fontSize={13} fontWeight={600} fill="currentColor" opacity={.7}>{label}</text>)}
    {edges.map(e=>{const a=scene.positions.get(e.source),b=scene.positions.get(e.target);if(!a||!b)return null;const related=!selected||adjacent.has(e.source)&&adjacent.has(e.target);return <path key={e.id} d={`M ${a.x} ${a.y} C ${a.x+90} ${a.y}, ${b.x-90} ${b.y}, ${b.x} ${b.y}`} fill="none" stroke={e.observed?'#d5b16e':'#4586ad'} strokeWidth={e.weight==null?1.5:1.2+4*e.weight} strokeDasharray={e.observed?undefined:'4 4'} opacity={related?(e.observed?.85:.5):.06}><title>{e.relation.replace(/_/g,' ')}: {e.detail}</title></path>;})}
    {[...scene.positions.values()].map(n=>{const active=n.id===selected,visible=!selected||active||adjacent.has(n.id);const label=n.kind==='observation'?'Raw '+((n.value??0)*100).toFixed(1)+'%':n.label;return <g key={n.id} data-node={n.id} role="button" tabIndex={0} aria-label={`Inspect ${n.label}`} onClick={()=>onSelect(n.id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(n.id);}}} style={{cursor:'pointer',opacity:visible?1:.3}}><title>{n.label}: {n.detail}</title><circle cx={n.x} cy={n.y} r={active?12:n.kind==='model'?12:7} fill={colors[n.kind]??'#5b9ec0'} stroke={active?'#fff':colors[n.kind]??'#5b9ec0'} strokeWidth={active?2:1}/><text x={n.x+13} y={n.y+5} fontSize={14} fill="currentColor" stroke="var(--surface-1)" strokeWidth={5} strokeLinejoin="round" paintOrder="stroke">{label.length>23?label.slice(0,21)+'…':label}</text></g>;})}
   </g>
  </svg></div>
 </div>;
}

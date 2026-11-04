/** The atlas's flat world map, on the shared ECharts GeoMap (Equal Earth): country shading by the chosen layer,
 *  exchanges as points, labels for countries big enough at the current zoom; same props and handle as before. */
import { forwardRef, memo, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react';
import { GeoMap, countryLabel, type GeoMapHandle, type GeoPoint } from '@/components/charts/GeoMap';
import { EXCHANGES, exchangeById } from './exchanges';
import type { AtlasGeometry } from './atlasGeometry';
export type AtlasHover={iso:string;name:string;x:number;y:number}|null;
export type AtlasMapHandle={zoom:(factor:number)=>void;reset:()=>void;region:(bounds:[number,number,number,number])=>void};
type Props={showExchanges?:boolean;focusedExchange?:string|null;onExchange?:(id:string)=>void;geo:AtlasGeometry;numToIso:Record<string,string>;fills:Record<string,string>;selected:string|null;labels:Record<string,string>;showLabels:boolean;title:string;onSelect:(iso:string)=>void;onHover:(hover:AtlasHover)=>void};

export const AtlasMap2D=memo(forwardRef<AtlasMapHandle,Props>(function AtlasMap2D({geo,numToIso,fills,selected,labels,showLabels,title,onSelect,onHover,showExchanges=true,focusedExchange=null,onExchange},ref){
  const map=useRef<GeoMapHandle>(null);
  const [zoom,setZoom]=useState(1);
  const isoToNum=useMemo(()=>{const m:Record<string,string>={};for(const s of geo.shapes){const iso=numToIso[s.id];if(iso&&(!m[iso]||s.area>(geo.shapes.find(x=>x.id===m[iso])?.area??0)))m[iso]=s.id;}return m;},[geo,numToIso]);
  const byId=useMemo(()=>{const f:Record<string,string>={};for(const s of geo.shapes){const iso=numToIso[s.id];if(iso&&fills[iso])f[s.id]=fills[iso];}return f;},[geo,numToIso,fills]);
  // a country is labelled once it is big enough on screen at this zoom
  const shown=useMemo(()=>{if(!showLabels)return undefined;const out:Record<string,string>={};for(const s of geo.shapes){const iso=numToIso[s.id];if(labels[iso]&&s.area*zoom*zoom>1700)out[s.id]=labels[iso];}return out;},[geo,numToIso,labels,showLabels,zoom]);
  const points=useMemo<GeoPoint[]>(()=>showExchanges?EXCHANGES.map(e=>({id:e.id,lon:e.point[0],lat:e.point[1],size:e.id===focusedExchange?10:6,color:'#f3d596',
    selected:e.id===focusedExchange,label:e.label,tip:`<b>${e.name}</b><br/>${e.city} · approximate city location`})):[],[showExchanges,focusedExchange]);
  useImperativeHandle(ref,()=>({zoom:f=>map.current?.zoom(f),reset:()=>map.current?.reset(),region:b=>map.current?.focusBounds(b)}),[]);
  useEffect(()=>{const e=exchangeById(focusedExchange);if(e)map.current?.focus(e.point[0],e.point[1],3.5);},[focusedExchange]);
  useEffect(()=>{if(!selected||focusedExchange)return;const id=isoToNum[selected];if(id)map.current?.focusRegion(id,2.5);},[selected,isoToNum,focusedExchange]);
  return <GeoMap ref={map} height={Math.round(1100*0.487)} className="atlas-map-svg" ariaLabel={title} controls={false} fills={byId} selected={selected?isoToNum[selected]??null:null}
    labels={shown} points={points} onZoom={setZoom}
    onRegionClick={id=>{const iso=numToIso[id];if(iso)onSelect(iso);}}
    onRegionHover={id=>onHover(id?{iso:numToIso[id]??'',name:countryLabel(id),x:0,y:0}:null)}
    onPointClick={id=>onExchange?.(id)}/>;
}));

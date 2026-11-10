import { useSyncExternalStore } from 'react';
export type ContentDensity='compact'|'comfortable';
const KEY='terminal.contentDensity',EVENT='terminal-content-density';let fallback:ContentDensity='comfortable';
export function getContentDensity():ContentDensity{
 try{const value=localStorage.getItem(KEY)??localStorage.getItem('mkt.density');return value==='compact'?'compact':'comfortable';}catch{return fallback;}
}
/** Mirrors the setting on <html data-content-density> so CSS can tighten page chrome (headers) in compact mode. */
export function applyContentDensity(value:ContentDensity=getContentDensity()){
 if(typeof document!=='undefined')document.documentElement.dataset.contentDensity=value;
}
export function setContentDensity(value:ContentDensity){
 fallback=value;try{localStorage.setItem(KEY,value);}catch{/* still works for this session */}
 applyContentDensity(value);
 window.dispatchEvent(new Event(EVENT));
}
function subscribe(listener:()=>void){const storage=(e:StorageEvent)=>{if(!e.key||e.key===KEY||e.key==='mkt.density'){applyContentDensity();listener();}};window.addEventListener(EVENT,listener);window.addEventListener('storage',storage);return()=>{window.removeEventListener(EVENT,listener);window.removeEventListener('storage',storage);};}
export function useContentDensity(){const density=useSyncExternalStore(subscribe,getContentDensity,()=> 'comfortable' as ContentDensity);return {density,setDensity:setContentDensity};}

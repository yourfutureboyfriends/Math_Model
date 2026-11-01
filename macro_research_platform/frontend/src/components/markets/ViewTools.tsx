import { useState } from 'react';
import { AlignJustify, Copy, Focus, Table2 } from 'lucide-react';
import { useContentDensity } from '@/lib/contentDensity';
import { TableExplorer } from '@/components/layout/TableExplorer';
export type MarketDensity='compact'|'comfortable';
export function useMarketDisplay(){
 const {density,setDensity}=useContentDensity();
 const [focused,setFocused]=useState(false);
 return {density,setDensity,focused,setFocused};
}
/** View-level actions apply to every market function, security page and launchpad. */
export function ViewTools({density,onDensity,focused,onFocus,code,onHelp}:{density:MarketDensity;onDensity:(v:MarketDensity)=>void;focused:boolean;onFocus:()=>void;code:string;onHelp:()=>void}){
 const [tables,setTables]=useState(false),[status,setStatus]=useState('');
 return <><div className="mkt-view-tools" aria-label="Markets view controls"><span className="mkt-view-code">{code}</span><span className="mkt-view-hint">Research workspace</span><div className="mkt-density" role="group" aria-label="Table density"><AlignJustify size={12}/>{(['compact','comfortable'] as const).map(v=><button key={v} aria-pressed={density===v} onClick={()=>onDensity(v)}>{v==='compact'?'Compact':'Comfortable'}</button>)}</div>
 <button onClick={onFocus} aria-pressed={focused} title="Hide side panels to give the page more room"><Focus size={12}/>{focused?'Restore panels':'Focus view'}</button>
 <button onClick={()=>setTables(true)} title="Search, copy and export loaded tables"><Table2 size={12}/>Tables</button>
 <button onClick={async()=>{try{await navigator.clipboard.writeText(window.location.href);setStatus('Page link copied.');}catch{setStatus('Copy the page address from your browser.');}}}><Copy size={12}/>Copy link</button>
 <button onClick={onHelp}>Help</button><span role="status" className="mkt-view-status">{status}</span></div>{tables&&<TableExplorer scopeId="mkt-fn-body" onClose={()=>setTables(false)}/>}</>;
}

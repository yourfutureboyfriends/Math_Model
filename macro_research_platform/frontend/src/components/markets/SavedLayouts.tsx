import { useState } from 'react';
import { findFunction } from './functions';
export type ResearchLayout = {layout:string;panes:{fn:string;symbol?:string;link?:'red'|'green'|'blue'|'yellow'|null}[]};
const KEY='mkt.savedResearchLayouts.v1';
type Saved={name:string;value:ResearchLayout};
export function validResearchLayout(value:any):value is ResearchLayout {
 return !!value && ['1x1','2x1','2x2','3x2'].includes(value.layout) && Array.isArray(value.panes) && value.panes.length>0 && value.panes.length<=6 && value.panes.every((p:any)=>p&&typeof p.fn==='string'&&!!findFunction(p.fn)&&p.fn!=='LP'&&(p.symbol===undefined||typeof p.symbol==='string'&&p.symbol.length<=128)&&[undefined,null,'red','green','blue','yellow'].includes(p.link));
}
export function readSavedLayouts():Saved[]{
 try {const rows=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(rows)?rows.filter((r:any)=>typeof r?.name==='string'&&r.name.trim().length>0&&r.name.length<=48&&validResearchLayout(r.value)).slice(0,12):[];}catch{return [];}
}
export function SavedLayouts({value,onRestore}:{value:ResearchLayout;onRestore:(value:ResearchLayout)=>void}){
 const [rows,setRows]=useState(readSavedLayouts),[name,setName]=useState(''),[selected,setSelected]=useState(''),[status,setStatus]=useState('');
 const [removed,setRemoved]=useState<Saved|null>(null);
 const persist=(next:Saved[])=>{try{localStorage.setItem(KEY,JSON.stringify(next));setRows(next);return true;}catch{setStatus('Browser storage is unavailable. This change was not saved.');return false;}};
 const save=()=>{const clean=name.trim();if(!clean){setStatus('Enter a layout name.');return;}if(rows.some(r=>r.name===clean)){setStatus('That name already exists. Choose another name to keep both layouts.');return;}if(rows.length>=12){setStatus('12 layouts saved. Remove one before adding another.');return;}if(persist([...rows,{name:clean,value:structuredClone(value)}])){setSelected(clean);setName('');setStatus(`Saved ${clean} on this browser.`);}};
 return <div className="flex flex-wrap items-center gap-2 p-3 border border-border rounded-lg bg-surface-1 text-xs" aria-label="Saved research layouts">
  <strong className="text-text-secondary">Saved layouts</strong>
  <input aria-label="New layout name" maxLength={48} value={name} onChange={e=>setName(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')save();}} placeholder="e.g. European earnings" className="bg-surface-2 border border-border rounded px-2 py-1"/>
  <button onClick={save} className="text-bloomberg">Save current</button>
  <select aria-label="Saved layout" value={selected} onChange={e=>setSelected(e.target.value)} className="bg-surface-2 border border-border rounded px-2 py-1"><option value="">Choose a layout</option>{rows.map(r=><option key={r.name}>{r.name}</option>)}</select>
  <button disabled={!selected} onClick={()=>{const row=rows.find(r=>r.name===selected);if(row){onRestore(structuredClone(row.value));setStatus(`Restored ${row.name}.`);}}}>Restore</button>
  <button disabled={!selected} onClick={()=>{const row=rows.find(r=>r.name===selected);if(row&&persist(rows.filter(r=>r.name!==selected))){setRemoved(row);setSelected('');setStatus(`Removed ${row.name}.`);}}}>Remove</button>
  {removed&&<button onClick={()=>{if(rows.some(r=>r.name===removed.name)||rows.length>=12){setStatus('Cannot undo: the name exists or storage is full.');return;}if(persist([...rows,removed])){setRemoved(null);setStatus('Removal undone.');}}}>Undo removal</button>}
  <span role="status" className="text-text-tertiary">{status||'Stored locally in this browser; no market data or model assumptions are saved.'}</span>
 </div>;
}

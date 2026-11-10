import { useEffect, useMemo, useRef, useState } from 'react';
import { Download, X } from 'lucide-react';
import { filteredRows, tableCSV, visibleTables, type TableSnapshot } from '@/lib/tableData';
export function TableExplorer({onClose,scopeId='terminal-content'}:{onClose:()=>void;scopeId?:string}) {
  const [tables,setTables]=useState<TableSnapshot[]>(()=>visibleTables(document.getElementById(scopeId)??document));
  const [index,setIndex]=useState(0),[query,setQuery]=useState(''),[status,setStatus]=useState('');
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close();},[]);
  const table=tables[index];
  const rows=useMemo(()=>table?filteredRows(table,query):[],[table,query]);
  const csv=()=>{
    if(!table)return;
    const url=URL.createObjectURL(new Blob(['\uFEFF'+tableCSV(table.headers,rows)],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=`${table.title.replace(/[^\w -]/g,'').slice(0,70)||'table'}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);setStatus(`Exported ${rows.length} rows.`);
  };
  return <dialog ref={dialog} onCancel={onClose} aria-labelledby="table-explorer-title" className="w-[min(1100px,95vw)] max-h-[85vh] rounded-xl border border-border bg-surface-1 text-text-primary p-4 backdrop:bg-black/60">
    <div className="flex items-start gap-3 mb-3"><div><h2 id="table-explorer-title" className="text-sm font-semibold">Table explorer</h2><p className="text-[11px] text-text-tertiary mt-1">Search, copy or export tables already loaded in this workspace. Refresh the snapshot after data changes.</p></div><button onClick={onClose} aria-label="Close table explorer" className="ml-auto p-1"><X className="w-4 h-4"/></button></div>
    <div className="flex flex-wrap gap-2 mb-3">
      <select aria-label="Choose workspace table" className="min-w-0 max-w-[420px] bg-bg border border-border rounded px-2 py-1.5 text-xs" value={index} onChange={e=>{setIndex(Number(e.target.value));setQuery('');setStatus('');}}>{tables.map((t,i)=><option key={i} value={i}>{t.title}</option>)}</select>
      <input aria-label="Search table rows" autoFocus placeholder="Search all columns…" value={query} onChange={e=>setQuery(e.target.value)} className="bg-bg border border-border rounded px-2 py-1.5 text-xs flex-1 min-w-[180px]"/>
      <button onClick={()=>{setTables(visibleTables(document.getElementById(scopeId)??document));setIndex(0);setStatus('Snapshot refreshed.');}} className="px-2 border border-border rounded text-xs">Refresh snapshot</button>
      <button disabled={!table} onClick={csv} className="inline-flex items-center gap-1 px-2 border border-border rounded text-xs disabled:opacity-40"><Download className="w-3.5 h-3.5"/>CSV</button>
      <button disabled={!table} onClick={async()=>{try{await navigator.clipboard.writeText(tableCSV(table.headers,rows));setStatus(`Copied ${rows.length} rows as CSV.`);}catch{setStatus('Clipboard unavailable. Use CSV download instead.');}}} className="px-2 border border-border rounded text-xs disabled:opacity-40">Copy CSV</button>
    </div>
    <p role="status" className="text-[11px] text-text-tertiary mb-2">{table?`${rows.length} of ${table.rows.length} rows · preview shows first 250${table.truncated?' · source capped at 5,000 rows':''}`:'No populated tables loaded here. Open a data panel, then refresh this snapshot.'} {status}</p>
    {table&&<div className="overflow-auto max-h-[55vh] border border-border rounded"><table className="w-full text-[11px] tabular-nums"><thead className="sticky top-0 bg-surface-2"><tr>{table.headers.map((v,i)=><th key={i} className="text-left p-2 whitespace-nowrap">{v}</th>)}</tr></thead><tbody>{rows.slice(0,250).map((row,i)=><tr key={i} className="border-t border-border-subtle">{row.map((v,j)=><td key={j} className="p-2 whitespace-nowrap">{v}</td>)}</tr>)}</tbody></table></div>}
  </dialog>;
}

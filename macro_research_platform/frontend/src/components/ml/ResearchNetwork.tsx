import {useMemo,useState} from 'react';
import {useChartTheme} from './ui/EChart';
import {ResearchGraphCanvas} from './ResearchGraphCanvas';
import {useResearchGraphQ} from './api';
import {KINDS,overviewGraph,safeResearchUrl,selectGraph} from './researchGraph';
import type {ResearchGraph,ResearchNode} from './researchGraph';

export function ResearchNetwork(){
 const q=useResearchGraphQ(),graph=q.data as ResearchGraph|undefined,t=useChartTheme();
 const [search,setSearch]=useState(''),[kind,setKind]=useState('all'),[selected,setSelected]=useState<string|null>(null),[focus,setFocus]=useState<string|null>(null),[detailed,setDetailed]=useState(false),[reset,setReset]=useState(0);
 const filtered=useMemo(()=>graph?selectGraph(detailed||search||kind!=='all'?graph:overviewGraph(graph),search,kind,focus):{nodes:[],edges:[]},[graph?.revision,search,kind,focus,detailed]);
 const node=filtered.nodes.find(n=>n.id===selected)??graph?.nodes.find(n=>n.id===selected);
 const connections=filtered.edges.filter(e=>e.source===selected||e.target===selected)??[];
 const colors=useMemo(()=>Object.fromEntries(KINDS.map((k,i)=>[k,t.series[i%t.series.length]])),[t]);
 if(q.isLoading)return <div role="status" className="p-6 text-sm">Loading research connections…</div>;
 if(q.error)return <div role="alert" className="p-6 text-sm">{String(q.error.message)} <button className="underline" onClick={()=>void q.refetch()}>Retry</button></div>;
 if(!graph)return null;
 const sourceLink=(n:ResearchNode,url:string|undefined,label:string)=>{const safe=safeResearchUrl(url);return safe?<a key={n.id+label} href={safe} target="_blank" rel="noreferrer" className="text-blue-400 underline">{label}</a>:null;};
 return <section className="overflow-hidden rounded-xl border border-[var(--border-primary)] bg-[var(--bg-secondary)]" aria-label="Research evidence map">
  <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border-primary)] p-4"><div><h2 className="font-semibold">Research evidence map</h2><p className="mt-1 text-xs text-[var(--text-secondary)]">Follow the evidence from data sources to research outputs. Sources, factors and forecasts in one view. Checks every 30 seconds.</p></div><button className="rounded border px-3 py-1 text-xs" onClick={()=>void q.refetch()} disabled={q.isFetching}>{q.isFetching?'Checking…':'Refresh evidence'}</button></header>
  <div className="flex flex-wrap gap-3 p-4"><input aria-label="Search research network" placeholder="Search indicators, forecasts or papers…" value={search} onChange={e=>setSearch(e.target.value)} className="min-w-0 flex-1 rounded border bg-transparent px-3 py-2 text-sm"/>
   <select aria-label="Filter research network" value={kind} onChange={e=>setKind(e.target.value)} className="rounded border bg-[var(--bg-secondary)] px-3 text-sm"><option value="all">All connections</option>{KINDS.map(k=><option key={k} value={k}>{k}</option>)}</select>
   <button className="rounded border px-3 text-xs" aria-pressed={detailed} onClick={()=>{setDetailed(v=>!v);setSelected(null);setFocus(null);}}>{detailed?'Group factors':'Show individual factors'}</button>
   <button className="rounded border px-3 text-xs" onClick={()=>{setSearch('');setKind('all');setFocus(null);setSelected(null);setDetailed(false);setReset(v=>v+1);}}>Reset view</button></div>
  <div className="flex flex-wrap gap-x-4 gap-y-2 px-4 text-[11px]">{KINDS.map(k=><span key={k}><span style={{color:colors[k]}}>●</span> {k}</span>)}<span>{filtered.nodes.length} nodes · {filtered.edges.length} links</span></div>
  <div className="grid xl:grid-cols-[minmax(0,1fr)_320px]">
   <div className="min-w-0 overflow-x-auto" style={{background:'radial-gradient(ellipse at 45% 45%, rgba(39,93,140,.12), transparent 70%)'}}><div className="mx-4 mt-3 text-[11px] text-[var(--text-secondary)]">Solid links: saved measurements · Dashed links: configured paths · Grouped factors by default</div>
    {filtered.nodes.length?<ResearchGraphCanvas key={reset+'|'+filtered.nodes.map(n=>n.id).join('|')} nodes={filtered.nodes} edges={filtered.edges} selected={selected} onSelect={setSelected} colors={colors}/>:<div role="status" className="p-12 text-sm">No matching connections. Try another search or reset the view.</div>}</div>
   <aside className="max-h-[670px] overflow-y-auto border-t border-[var(--border-primary)] p-4 xl:border-l xl:border-t-0" aria-label="Selected research evidence">
    <label className="mb-4 block text-xs">Inspect a node<select aria-label="Inspect a research node" className="mt-2 block w-full rounded border bg-[var(--bg-secondary)] p-2" value={selected??''} onChange={e=>setSelected(e.target.value||null)}><option value="">Select evidence…</option>{filtered.nodes.map(n=><option key={n.id} value={n.id}>{n.label}</option>)}</select></label>{!node?<><h3 className="font-medium">Inspect a connection</h3><p className="mt-3 text-xs leading-5">Select a node to inspect its provenance and linked evidence.</p><p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">{graph.scope}</p></>:<>
     <div className="text-xs uppercase text-[var(--text-secondary)]">{node.kind}</div><h3 className="mt-1 font-medium">{node.label}</h3><p className="mt-3 text-xs leading-5">{node.detail}</p>
     {node.value!=null&&<div className="mt-3 text-2xl">{(node.value*100).toFixed(1)}% <span className="text-xs">raw research</span></div>}
     <dl className="mt-4 space-y-2 break-words text-xs">{[['Status',node.status],['Cached observations',node.coverage_months],['Conservative lag',node.lag_months==null?null:node.lag_months+' months'],['Data month',node.as_of],['Observed',node.observed_at],['Weights trained',node.trained_at],['Outcome available after',node.known_after==null?null:node.known_after+' months'],['Input digest',node.digest],['Used for',node.used_for],['Source error',node.error]].filter(([,v])=>v!=null).map(([k,v])=><div key={String(k)}><dt className="text-[var(--text-secondary)]">{k}</dt><dd>{v}</dd></div>)}</dl>
     {node.limitation&&<p className="mt-3 text-xs leading-5 text-amber-400">{node.limitation}</p>}<div className="mt-3 flex gap-4 text-xs">{sourceLink(node,node.url,'Source / paper')}{sourceLink(node,node.code_url,'Released code')}</div>
     <button className="my-4 rounded border px-3 py-2 text-xs" onClick={()=>{setSearch('');setKind('all');setFocus(focus===node.id?null:node.id);}}>{focus===node.id?'Show full network':'Focus on this node'}</button>
     <h4 className="text-xs font-semibold">Connections ({connections.length})</h4><ul className="mt-2 space-y-2">{connections.map(e=>{const other=filtered.nodes.find(n=>n.id===(e.source===node.id?e.target:e.source));return <li key={e.id} className="rounded border border-[var(--border-primary)] p-2 text-xs"><button className="text-left text-blue-400 underline" onClick={()=>{setSelected(other?.id??null);if(focus)setFocus(other?.id??null);}}>{other?.label}</button><div className="mt-1">{e.relation.replace(/_/g,' ')}{e.weight!=null?' · '+(e.weight*100).toFixed(1)+'% routing':''}</div><p className="mt-1 leading-4 text-[var(--text-secondary)]">{e.detail}</p></li>;})}</ul>
    </>}
   </aside></div>
  <details className="border-t p-4 text-xs"><summary className="cursor-pointer font-medium">Factor coverage and remaining blind spots</summary><p className="my-3">Expanded factors are research inputs. Cached data does not establish predictive value or production approval.</p><div className="grid gap-2 sm:grid-cols-2">{graph.factor_coverage?.map(row=><div key={row.key} className="rounded border p-2"><b>{row.label}</b><div>{row.status} · {row.latest??'not loaded'} · lag {row.lag_months}m</div></div>)}</div><ul className="mt-3 list-inside list-disc">{graph.coverage_gaps?.map(g=><li key={g}>{g}</li>)}</ul></details><footer className="border-t border-[var(--border-primary)] p-4 text-[11px] leading-5 text-[var(--text-secondary)]">{graph.limitations.join(' ')}<br/>Revision {graph.revision} · checked {new Date(graph.generated_at).toLocaleTimeString()}</footer>
 </section>;
}

export type ResearchNode={id:string;label:string;kind:string;detail:string;url?:string;code_url?:string;status?:string;observed_at?:string;trained_at?:string;as_of?:string;digest?:string;value?:number;known_after?:number;used_for?:string;limitation?:string;quality?:unknown;error?:string;group?:string;coverage_months?:number;lag_months?:number;factor_family?:string;count?:number};
export type ResearchEdge={id:string;source:string;target:string;relation:string;detail:string;observed:boolean;weight?:number|null;observed_at?:string};
export type ResearchGraph={nodes:ResearchNode[];edges:ResearchEdge[];revision:string;generated_at:string;scope:string;limitations:string[];factor_coverage?:Array<{key:string;label:string;group:string;status:string;latest:string|null;lag_months:number}>;coverage_gaps?:string[]};
export const KINDS=['source','factor','feature','module','model','forecast','observation','method','paper'];
export function selectGraph(graph:ResearchGraph,search:string,kind:string,focus:string|null){
 const query=search.trim().toLowerCase();
 let nodes=graph.nodes;
 if(query||kind!=='all'){
  const matches=new Set(nodes.filter(n=>(kind==='all'||n.kind===kind)&&(!query||`${n.label} ${n.detail} ${n.id}`.toLowerCase().includes(query))).map(n=>n.id));
  const included=new Set(matches);
  graph.edges.forEach(e=>{if(matches.has(e.source)||matches.has(e.target)){included.add(e.source);included.add(e.target);}});
  nodes=nodes.filter(n=>included.has(n.id));
 }
 if(focus){const neighbors=new Set([focus]);graph.edges.forEach(e=>{if(e.source===focus||e.target===focus){neighbors.add(e.source);neighbors.add(e.target);}});nodes=nodes.filter(n=>neighbors.has(n.id));}
 const ids=new Set(nodes.map(n=>n.id));
 return {nodes,edges:graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))};
}
export function layoutGraph(nodes:ResearchNode[]){
 const columns:Record<string,number>={source:0,factor:1,feature:1,module:2,method:2,paper:1,model:3,forecast:4,observation:5};
 const buckets:Record<string,ResearchNode[]>={};
 nodes.forEach(n=>{const x=columns[n.kind]??0;(buckets[x]??=[]).push(n);});
 return Object.entries(buckets).flatMap(([column,rows])=>rows.map((n,i)=>({...n,x:40+Number(column)*200,y:40+i*640/Math.max(1,rows.length-1)})));
}
export function safeResearchUrl(url?:string){if(!url)return null;try{const u=new URL(url);return u.protocol==='https:'?u.href:null;}catch{return null;}}

/** Collapse feature-level paths into specialist groups; conventional task-input shortcuts are deliberately omitted. */
export function overviewGraph(graph:ResearchGraph):ResearchGraph{
 const all=new Map(graph.nodes.map(n=>[n.id,n]));
 const mapped=new Map<string,string>(),clusters=new Map<string,ResearchNode>();
 graph.nodes.filter(n=>n.kind==='feature').forEach(n=>{
  const module=graph.edges.find(e=>e.source===n.id&&e.relation==='encoded_by')?.target;
  const group=n.group??(module?all.get(module)?.label:'Other inputs')??'Other inputs';
  const id='cluster:'+group;mapped.set(n.id,id);
  const old=clusters.get(id);const count=(old?.count??0)+1;
  clusters.set(id,{id,label:group.replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase()),kind:'factor',detail:`${count} declared inputs. Expand individual factors to inspect source coverage and missing values.`,...{count}});
 });
 const nodes=[...graph.nodes.filter(n=>!['feature','paper','method'].includes(n.kind)),...clusters.values()];
 const ids=new Set(nodes.map(n=>n.id)),edges=new Map<string,ResearchEdge>();
 graph.edges.filter(e=>e.relation!=='task_input').forEach(e=>{
  const source=mapped.get(e.source)??e.source,target=mapped.get(e.target)??e.target;
  if(!ids.has(source)||!ids.has(target)||source===target)return;
  const id=source+'|'+e.relation+'|'+target;
  edges.set(id,{...e,id,source,target,detail:mapped.has(e.source)||mapped.has(e.target)?'Aggregated configured feature paths; expand individual factors for exact provenance.':e.detail});
 });
 return {...graph,nodes,edges:[...edges.values()]};
}

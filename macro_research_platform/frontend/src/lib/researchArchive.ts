export type Observation={id:string;symbol:string;kind:string;observedAt:string;payload:any};
export type Exposure={symbol:string;weight:number;fund:boolean};
export function readArchive(key:string):Observation[]{try{const a=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(a)?a.filter(r=>r&&typeof r.id==='string'&&typeof r.symbol==='string'&&typeof r.kind==='string'&&Number.isFinite(Date.parse(r.observedAt))&&r.payload).slice(-200):[];}catch{return [];}}
export function saveObservation(key:string,rows:Observation[],symbol:string,kind:string,payload:any){
 const next=[...rows,{id:crypto.randomUUID(),symbol,kind,observedAt:new Date().toISOString(),payload}].slice(-200);
 localStorage.setItem(key,JSON.stringify(next));return next;
}
export function compareNumbers(a:any,b:any,path='',out:{field:string;before:number;after:number;change:number}[]=[]){
 if(Array.isArray(a)&&Array.isArray(b)){
  const identity=['period','date','symbol','year'].find(k=>b.length>0&&b.every(r=>r&&typeof r==='object'&&r[k]!=null)&&a.every(r=>r&&typeof r==='object'&&r[k]!=null));
  if(identity){for(const row of b){const prior=a.find(r=>r[identity]===row[identity]);if(prior)compareNumbers(prior,row,`${path}[${row[identity]}]`,out);}return out;}
 }
 if(a&&b&&typeof a==='object'&&typeof b==='object')for(const k of Object.keys(b)){
 const p=path?`${path}.${k}`:k;if(typeof a[k]==='number'&&typeof b[k]==='number'&&Number.isFinite(a[k])&&Number.isFinite(b[k])&&a[k]!==b[k])out.push({field:p,before:a[k],after:b[k],change:b[k]-a[k]});
 else if(p.split('.').length<6)compareNumbers(a[k],b[k],p,out);
 }return out;
}
export function lookThrough(positions:Exposure[],funds:Record<string,{holdings?:{symbol:string;weight:number}[]}>) {
 const result=new Map<string,number>();let uncovered=0;
 for(const p of positions){if(!p.fund){result.set(p.symbol,(result.get(p.symbol)||0)+p.weight);continue;}
 let covered=0;for(const h of funds[p.symbol]?.holdings??[]){if(!h.symbol||!Number.isFinite(h.weight)||h.weight<0||h.weight>1)continue;const w=Math.min(h.weight,Math.max(0,1-covered));covered+=w;result.set(h.symbol,(result.get(h.symbol)||0)+p.weight*w);}
 uncovered+=p.weight*(1-covered);
 }return {rows:[...result].map(([symbol,weight])=>({symbol,weight})).sort((a,b)=>b.weight-a.weight),uncovered};
}
export function parseExposures(text:string):Exposure[]{const seen=new Set<string>();const rows=text.split('\n').filter(s=>s.trim()).map(line=>{const [s,w,t]=line.split(',').map(x=>x.trim());const weight=Number(w);if(!s||!w||!Number.isFinite(weight)||weight<=0||weight>100||seen.has(s.toUpperCase()))throw Error('Use unique SYMBOL, weight %, stock or fund rows; weights must be positive.');if(t&&!['stock','fund'].includes(t.toLowerCase()))throw Error('Position type must be stock or fund.');seen.add(s.toUpperCase());return {symbol:s.toUpperCase(),weight:weight/100,fund:t?.toLowerCase()==='fund'};});if(!rows.length||rows.length>30||rows.reduce((n,r)=>n+r.weight,0)>1.00001)throw Error('Enter 1–30 positions totaling at most 100%. Remaining weight is unallocated.');return rows;}

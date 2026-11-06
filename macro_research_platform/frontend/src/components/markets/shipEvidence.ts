import { recentFix, validPosition, shipPhase } from './trackerQuality';
export type VesselReport={mmsi:number;lat:number;lon:number;speed:number|null;heading:number|null;type:string;status:number|null;name:string;phase:ReturnType<typeof shipPhase>;sat:boolean;tag:string;t:number|null;timeBasis:string;source?:string;collectionType?:string};
const number=(x:unknown):number|null=>typeof x==='number'&&Number.isFinite(x)?x:null;
/** Compact feed schemas are provider data, not trusted application state. */
export function parseVessels(data:any, historical:boolean):VesselReport[]{
 if(!Array.isArray(data?.cols)||!Array.isArray(data?.rows))return [];
 const ix:Record<string,number>=Object.fromEntries(data.cols.map((c:string,i:number)=>[c,i]));
 return data.rows.flatMap((r:any)=>{
  if(!Array.isArray(r)||!validPosition(r[ix.lon],r[ix.lat])||number(r[ix.mmsi])==null||!Number.isInteger(r[ix.mmsi])||r[ix.mmsi]<=0)return [];
  const speed=number(r[ix.speed]),heading=number(r[ix.heading]),status=number(r[ix.status]);
  return [{mmsi:r[ix.mmsi],lat:r[ix.lat],lon:r[ix.lon],speed:speed!=null&&speed>=0&&speed<=60?speed:null,
   heading:heading!=null&&heading>=0&&heading<360?heading:null,type:Array.isArray(data.types)&&typeof data.types[r[ix.type]]==='string'?data.types[r[ix.type]]:'Unknown',status,
   name:typeof r[ix.name]==='string'?r[ix.name]:'',sat:historical,phase:shipPhase(status,speed,historical),
   tag:typeof r[ix.tag]==='string'?r[ix.tag]:'',t:number(r[ix.t]),timeBasis:r[ix.time_basis]??(historical?'historical_cell':'receiver_receipt'),source:r[ix.source]??(historical?'gfw':'community receivers'),collectionType:r[ix.collection_type]??(historical?'historical grid':'receiver observation')}];
 });
}
export function selectMaritimeLayer(rows:VesselReport[],now:number,historical:boolean,maxAge:number){
 const chosen=new Map<number,VesselReport>();
 for(const r of rows){
  if(r.sat!==historical||!recentFix(r.t,now,historical?7*86400:maxAge))continue;
  if(!chosen.has(r.mmsi)||(chosen.get(r.mmsi)!.t??0)<(r.t??0))chosen.set(r.mmsi,r);
 }
 return [...chosen.values()];
}
function distance(a:number[],b:number[]){const r=Math.PI/180,h=Math.sin((b[1]-a[1])*r/2)**2+Math.cos(a[1]*r)*Math.cos(b[1]*r)*Math.sin((b[2]-a[2])*r/2)**2;return 12742*Math.asin(Math.sqrt(Math.min(1,h)));}
/** Never bridge long gaps or impossible jumps into an apparently observed voyage. */
export function observedTrack(track:unknown,now:number){
 const points=(Array.isArray(track)?track:[]).filter((p:any)=>Array.isArray(p)&&recentFix(p[0],now,8*3600)&&validPosition(p[2],p[1])).sort((a,b)=>a[0]-b[0]);
 const segments:number[][][]=[];let km=0,seconds=0,breaks=0;
 for(const p of points){const last=segments[segments.length-1],prev=last?.[last.length-1];if(!prev){segments.push([p]);continue;}
  const dt=p[0]-prev[0];if(dt<=0)continue;
  const d=distance(prev,p);if(dt>1800||d/1.852/(dt/3600)>60){segments.push([p]);breaks++;continue;}
  last!.push(p);km+=d;seconds+=dt;
 }
 return {segments:segments.filter(s=>s.length>1),km,seconds,breaks};
}

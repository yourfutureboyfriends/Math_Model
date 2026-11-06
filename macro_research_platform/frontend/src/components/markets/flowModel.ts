export type FlowLayer='into_us'|'out_of_us'|'bis'|'etf'|'pressure';
export function countryFlowValues(layer:FlowLayer,tic:any,bis:any,etf:any,win:string,kind:string):Record<string,number>{
 const result:Record<string,number>={};
 const put=(iso:string,value:any)=>{if(iso&&typeof value==='number'&&Number.isFinite(value))result[iso]=value;};
 if(layer==='into_us'||layer==='out_of_us')for(const row of tic?.[layer]??[])put(row.iso2,row[win]?.[kind]);
 else if(layer==='bis')for(const row of bis?.countries??[])put(row.iso2,row.last_q);
 else for(const row of etf?.rows??[])if(row.iso2)put(row.iso2,layer==='etf'?row.flows?.week_usd:row.mf_1m);
 return result;
}
export function flowEndpoints(layer:'into_us'|'out_of_us',value:number,country:[number,number],us:[number,number]):[[number,number],[number,number]]{
 const endpoints:[[number,number],[number,number]]=layer==='into_us'?[country,us]:[us,country];
 return value>=0?endpoints:[endpoints[1],endpoints[0]];
}

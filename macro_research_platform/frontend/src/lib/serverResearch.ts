import {fetchJSONWithDeadline} from './fetchDeadline';
export async function workflowRequest(path:string,method='GET',body?:unknown,signal?:AbortSignal){
 const {response:r,json:j,invalid}=await fetchJSONWithDeadline(`/api/v1/workflows${path}`,signal??new AbortController().signal,60_000,{method,headers:body?{'Content-Type':'application/json'}:undefined,body:body?JSON.stringify(body):undefined});
 if(!r.ok||invalid||!j)throw Error(typeof j?.detail==='string'?j.detail:`Workflow request failed (${r.status})`);return j;
}
export function recordPayload(r:any){return {...r.payload,_serverVersion:r.version,_serverReceivedAt:r.updated_at};}
export async function loadServerResearch(signal?:AbortSignal){const j=await workflowRequest('/research','GET',undefined,signal);return {...j,observations:j.records.filter((r:any)=>r.kind==='observation').map(recordPayload),theses:j.records.filter((r:any)=>r.kind==='thesis').map(recordPayload)};}
export async function saveResearchRecord(kind:'observation'|'thesis'|'reconciliation',record:any){
 const {_serverVersion=0,_serverReceivedAt:_,...payload}=record;
 const r=await workflowRequest(`/research/${encodeURIComponent(record.id)}`,'PUT',{kind,payload,expected_version:_serverVersion});return recordPayload(r);
}
export async function saveServerObservation(symbol:string,kind:string,payload:any){return saveResearchRecord('observation',{id:crypto.randomUUID(),symbol,kind,observedAt:new Date().toISOString(),payload});}

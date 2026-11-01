import {it,expect,vi,afterEach} from 'vitest';import {saveResearchRecord,loadServerResearch} from './serverResearch';
afterEach(()=>vi.unstubAllGlobals());
it('sends optimistic versions and does not serialize server metadata into the record payload',async()=>{
 const fetcher=vi.fn(async(_url:any,init:any)=>({ok:true,status:200,json:async()=>({version:3,updated_at:'now',payload:JSON.parse(init.body).payload})}));vi.stubGlobal('fetch',fetcher);
 const saved=await saveResearchRecord('thesis',{id:'one',thesis:'Evidence',_serverVersion:2,_serverReceivedAt:'old'});
 const body=JSON.parse(fetcher.mock.calls[0][1].body);expect(body.expected_version).toBe(2);expect(body.payload._serverVersion).toBeUndefined();expect(saved._serverVersion).toBe(3);
});
it('surfaces conflict errors instead of overwriting another edit',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:409,json:async()=>({detail:'Record changed elsewhere'})})));
 await expect(saveResearchRecord('thesis',{id:'x'})).rejects.toThrow('Record changed elsewhere');
});
it('separates observations and theses when loading records',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,status:200,json:async()=>({records:[{kind:'thesis',version:1,payload:{id:'t'}},{kind:'observation',version:2,payload:{id:'o'}}]})})));
 const result=await loadServerResearch();expect(result.theses[0].id).toBe('t');expect(result.observations[0]._serverVersion).toBe(2);
});

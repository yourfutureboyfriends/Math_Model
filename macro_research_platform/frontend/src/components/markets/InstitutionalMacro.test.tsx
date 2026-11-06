import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {InstitutionalMacro} from './InstitutionalMacro';
const mocks=vi.hoisted(()=>({request:vi.fn(),save:vi.fn(),retry:vi.fn()}));
vi.mock('@/lib/serverResearch',()=>({workflowRequest:mocks.request,saveResearchRecord:mocks.save}));
vi.mock('./shared',async original=>({...await original<typeof import('./shared')>(),useJSON:()=>({data:{events:[],views:[]},error:null,retry:mocks.retry})}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);mocks.request.mockReset();host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});
const click=async(text:string)=>{await act(async()=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent===text)!.click());};
it('keeps data collection explicit and exposes official conditions with source basis',async()=>{
 await act(async()=>root.render(<InstitutionalMacro canWrite onRecordsChanged={async()=>{}}/>));
 expect(mocks.request).not.toHaveBeenCalled();await click('Open macro laboratory');
 expect(host.textContent).toContain('No release evidence');await click('Conditions');
 expect(mocks.request).not.toHaveBeenCalled();mocks.request.mockResolvedValue({latest:{date:'2026-09-30',value:-.7,contributions:{FFR:.1}},change:.2,change_contributions:{FFR:.01},source_url:'https://www.federalreserve.gov/data',note:'Published contributions',units:'percentage points',vintage_basis:'Revised history'});
 await click('Load official FCI-G');expect(mocks.request).toHaveBeenCalledWith('/macro/conditions','GET',undefined);
 expect(host.textContent).toContain('Revised history');expect(host.textContent).toContain('Official source file');
});
it('uses guided release fields and protects writes for read-only users',async()=>{
 await act(async()=>root.render(<InstitutionalMacro canWrite={false} onRecordsChanged={async()=>{}}/>));
 await click('Open macro laboratory');
 expect(host.querySelectorAll('select').length).toBeGreaterThan(0);
 expect(Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Append release evidence')?.disabled).toBe(true);
 await click('Challengers');expect(Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Run registered US challengers')?.disabled).toBe(true);
});
it('registers challenger requests only after an explicit run and presents missing data honestly',async()=>{
 await act(async()=>root.render(<InstitutionalMacro canWrite onRecordsChanged={async()=>{}}/>));
 await click('Open macro laboratory');await click('Challengers');mocks.request.mockResolvedValue({available:false,reason:'Vintage source unavailable'});
 await click('Run registered US challengers');expect(mocks.request).toHaveBeenCalledWith('/macro/challengers','POST',{start:'2024-01-01',end:'2026-01-01'});
 expect(host.textContent).toContain('Vintage source unavailable');
 await click('GDP bridge');expect(host.textContent).toContain('At least 20 released training targets');
});

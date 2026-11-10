import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {EvidenceWorkbench} from './EvidenceWorkbench';
const mocks=vi.hoisted(()=>({request:vi.fn(),save:vi.fn()}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:{username:'analyst',role:'analyst'}})}));
vi.mock('@/lib/serverResearch',()=>({workflowRequest:mocks.request,saveResearchRecord:mocks.save}));
vi.mock('./shared',async original=>({...await original<typeof import('./shared')>(),useJSON:()=>({data:null,error:null,loading:false,retry:vi.fn()})}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);mocks.request.mockReset();mocks.save.mockReset();host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});
const click=async(text:string)=>{await act(async()=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent===text)!.click());};
it('does not collect data while closed and labels replay and illustrative inputs honestly',async()=>{
 await act(async()=>root.render(<EvidenceWorkbench archive={[]} canWrite onRecordsChanged={async()=>{}}/>));
 expect(mocks.request).not.toHaveBeenCalled();await click('Open evidence tools');await click('Capture audit');
 expect(host.textContent).toContain('does not rerun the original forecasting code');
 await click('Execution evidence');expect(host.textContent).toContain('illustrative values');
 mocks.request.mockResolvedValue({vwap:10,note:'Sample only'});await click('Evaluate evidence');
 expect(mocks.request.mock.calls[0][0]).toBe('/execution-evidence');expect(host.textContent).toContain('Sample only');
});
it('prevents analyst writes to global identities and requires documented tracker links',async()=>{
 await act(async()=>root.render(<EvidenceWorkbench archive={[]} canWrite onRecordsChanged={async()=>{}}/>));
 await click('Open evidence tools');await click('Identity links');expect(Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Save dated identity link')?.disabled).toBe(true);
 await click('Tracker evidence');await click('Save linked evidence');expect(host.textContent).toContain('Document the event');expect(mocks.request).not.toHaveBeenCalled();
});
it('offers guided forms, preserves drafts across tabs and keeps an advanced editor',async()=>{
 await act(async()=>root.render(<EvidenceWorkbench archive={[]} canWrite onRecordsChanged={async()=>{}}/>));
 await click('Open evidence tools');await click('Compare sources');
 expect(host.querySelectorAll('input[type="number"]').length).toBeGreaterThan(0);
 await click('Advanced JSON');expect(host.textContent).toContain('Use guided form');
 const before=(host.querySelector('textarea') as HTMLTextAreaElement).value;
 await click('Tracker evidence');await click('Compare sources');
 expect((host.querySelector('textarea') as HTMLTextAreaElement).value).toBe(before);
 await click('Portfolio stress');await click('Use guided form');
 await click('Add European vanilla option terms');
 const json=JSON.parse((host.querySelector('textarea') as HTMLTextAreaElement).value);
 expect(json.positions[0].option_terms.style).toBe('european');
 expect(Array.from(host.querySelectorAll('select option')).some(o=>o.textContent==='call')).toBe(true);
});
it('shows research tools without automatically fetching their sources',async()=>{
 await act(async()=>root.render(<EvidenceWorkbench archive={[]} canWrite onRecordsChanged={async()=>{}}/>));
 await click('Open evidence tools');await click('Macro vintages');
 expect(mocks.request).not.toHaveBeenCalled();
 mocks.request.mockResolvedValue({available:false,note:'No revised-data fallback'});
 await click('Evaluate evidence');expect(mocks.request).toHaveBeenCalledWith('/macro-vintages','POST',{start:'2024-01-01',end:'2025-01-01'});
 expect(host.textContent).toContain('No revised-data fallback');
});

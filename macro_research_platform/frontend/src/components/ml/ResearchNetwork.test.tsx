import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {ResearchNetwork} from './ResearchNetwork';
import {type StreamFrame,useMlStreamStore} from '@/store/mlStreamStore';
const state=vi.hoisted(()=>({data:null as any,error:null as any,isLoading:false,live:null as boolean|null}));
vi.mock('./api',()=>({useResearchGraphQ:(live=false)=>{state.live=live;return {data:state.data,error:state.error,isLoading:state.isLoading,isFetching:false,refetch:vi.fn()};}}));
vi.mock('./ui/EChart',()=>({EChart:()=><div aria-label="Graph canvas"/>,useChartTheme:()=>({series:['#00f','#f90'],textStrong:'#fff'})}));
// research_graph.py:117 sets revision to a hash of the payload, so different content always means a
// different revision. The panel memoises on it; a fixture that reused one revision across two graphs
// would be asserting a state the backend cannot produce.
const graphOf=(label:string,kind='source')=>({nodes:[{id:`${kind}:a`,kind,label,detail:'Research only',url:'https://arxiv.org/abs/1'}],edges:[],revision:label,generated_at:'2026-11-05T00:00:00Z',scope:'Test evidence',limitations:['Not causality.']});
const frame=(ok:boolean,payload:unknown,error:string|null=null):StreamFrame=>
 ({v:1,topic:'system2_reasoning',channel:'research_graph',seq:1,ok,payload,error,computed_ms:40,sent_at:'2026-11-07T00:00:00.000Z'});
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);vi.stubGlobal('matchMedia',()=>({matches:false}));vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}});useMlStreamStore.getState().reset();host=document.createElement('div');document.body.append(host);root=createRoot(host);state.error=null;state.isLoading=false;state.live=null;state.data=graphOf('Paper A','paper');});
afterEach(()=>{act(()=>root.unmount());host.remove();useMlStreamStore.getState().reset();vi.unstubAllGlobals();});
it('makes graph evidence available through keyboard selection',async()=>{await act(async()=>root.render(<ResearchNetwork/>));await act(async()=>{(Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Show individual factors') as HTMLButtonElement).click();});const select=host.querySelector('[aria-label="Inspect a research node"]') as HTMLSelectElement;await act(async()=>{select.value='paper:a';select.dispatchEvent(new Event('change',{bubbles:true}));});expect(host.textContent).toContain('Research only');expect(host.querySelector('a')?.getAttribute('href')).toBe('https://arxiv.org/abs/1');});
it('shows a recoverable error instead of invented data',async()=>{state.error=new Error('Source unavailable');await act(async()=>root.render(<ResearchNetwork/>));expect(host.querySelector('[role="alert"]')?.textContent).toContain('Source unavailable');expect(host.querySelector('[aria-label="Graph canvas"]')).toBeNull();});
it('serves the pushed graph and stops polling, even while the poll is still pending',async()=>{
 // The poll mounts and fetches once even with its interval off. Without the precedence guard its
 // pending state would blank a map the stream has already delivered.
 act(()=>useMlStreamStore.getState().setStatus('open'));
 act(()=>useMlStreamStore.getState().accept(frame(true,graphOf('Pushed source'))));
 state.isLoading=true;state.data=null;
 await act(async()=>root.render(<ResearchNetwork/>));
 expect(state.live).toBe(true);
 expect(host.textContent).toContain('Pushed source');
 expect(host.textContent).not.toContain('Loading research connections');
});
it('reports a failed build through the poll rather than drawing an empty map',async()=>{
 act(()=>useMlStreamStore.getState().setStatus('open'));
 act(()=>useMlStreamStore.getState().accept(frame(false,null,'ValueError: no panel data')));
 state.error=new Error('Source unavailable');state.data=null;
 await act(async()=>root.render(<ResearchNetwork/>));
 expect(state.live).toBe(false);
 expect(host.querySelector('[role="alert"]')?.textContent).toContain('Source unavailable');
 expect(host.textContent).not.toContain('ValueError');
});
it('falls back to the polled graph when the socket drops',async()=>{
 act(()=>useMlStreamStore.getState().setStatus('open'));
 act(()=>useMlStreamStore.getState().accept(frame(true,graphOf('Pushed source'))));
 state.data=graphOf('Polled source');
 await act(async()=>root.render(<ResearchNetwork/>));
 expect(host.textContent).toContain('Pushed source');
 act(()=>useMlStreamStore.getState().setStatus('closed'));
 expect(state.live).toBe(false);
 expect(host.textContent).toContain('Polled source');
 expect(host.textContent).not.toContain('Pushed source');
});

import {act} from 'react';import {createRoot} from 'react-dom/client';import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {LiveModularFlow} from './LiveModularFlow';
import {type StreamFrame,useMlStreamStore} from '@/store/mlStreamStore';
const state=vi.hoisted(()=>({data:{} as any,isError:false,live:null as boolean|null,refresh:vi.fn().mockResolvedValue({})}));
vi.mock('./api',()=>({useLiveStateQ:(live=false)=>{state.live=live;return {data:state.data,isError:state.isError};},refreshLiveState:state.refresh}));
vi.mock('./ui/EChart',()=>({EChart:({ariaLabel}:any)=><div role="img" aria-label={ariaLabel}/>,axisStyle:()=>({}),chartTheme:()=>({series:['#00f','#f90'],textStrong:'#fff',muted:'#888',surface:'#000'})}));
const measured={job:{running:false},cadence:'Measured state is polled every two seconds.',trace:{purpose:'inspection_preview',trained_at:'2026-11-05',as_of:'2026-11',inferred_at:'2026-11-05T10:00:00Z',input_digest:'v1',inputs_changed:false,note:'Raw research-model states.',months:['2026-10','2026-11'],tasks:['oil_up_3m'],seeds:[{modules:['news'],routing:[[1],[1]],module_rms:[[.2],[.3]],memory_rms:[.1,.2],hidden:[[.1,.2],[.2,.3]],attention:[[1],[.4,.6]],probabilities:[[.4],[.5]]}]}};
const frame=(ok:boolean,payload:unknown,error:string|null=null):StreamFrame=>
 ({v:1,topic:'system1_inference',channel:'deep_live',seq:1,ok,payload,error,computed_ms:8,sent_at:'2026-11-07T00:00:00.000Z'});
const open=()=>act(()=>useMlStreamStore.getState().setStatus('open'));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}});useMlStreamStore.getState().reset();host=document.createElement('div');document.body.append(host);root=createRoot(host);state.refresh.mockClear();state.isError=false;state.live=null;state.data={};});
afterEach(()=>{act(()=>root.unmount());host.remove();useMlStreamStore.getState().reset();vi.unstubAllGlobals();});
it('waits for actual measured states and refreshes without inventing a graph',async()=>{
 state.data={job:{running:true}};await act(async()=>root.render(<LiveModularFlow/>));
 expect(host.textContent).toContain('Waiting for measured model states');
 expect(host.querySelector('[aria-label="Measured modular neural signal flow"]')).toBeNull();
 expect(state.refresh).toHaveBeenCalledTimes(1);
});
it('renders measured preview states and timestamps with explicit scope',async()=>{
 state.data={job:{running:false},trace:{purpose:'inspection_preview',trained_at:'2026-11-05',as_of:'2026-11',inferred_at:'2026-11-05T10:00:00Z',input_digest:'v1',inputs_changed:false,months:['2026-10','2026-11'],tasks:['oil_up_3m'],seeds:[{modules:['news'],routing:[[1],[1]],module_rms:[[.2],[.3]],memory_rms:[.1,.2],hidden:[[.1,.2],[.2,.3]],attention:[[1],[.4,.6]],probabilities:[[.4],[.5]]}]}};
 await act(async()=>root.render(<LiveModularFlow/>));
 expect(host.textContent).toContain('Bounded inspection preview');
 expect(host.textContent).toContain('input values unchanged');
 expect(host.querySelector('[aria-label="Measured modular neural signal flow"]')).toBeTruthy();
 expect(host.querySelector('[aria-label="Measured temporal attention"]')).toBeTruthy();
 expect(host.textContent).toContain('2026-11 · latest');
});
it('serves the pushed trace and leaves the once-a-minute kick to the broadcaster',async()=>{
 // The stream's deep_live channel kicks api.ml.live.request_refresh every 60s while a socket is
 // subscribed, which is the same request the panel's own timer made. The timer cleaned itself up on
 // unmount; the duplication was while both were live, and the lock coalesced it to one subprocess.
 open();act(()=>useMlStreamStore.getState().accept(frame(true,measured)));
 await act(async()=>root.render(<LiveModularFlow/>));
 expect(state.live).toBe(true);
 expect(state.refresh).not.toHaveBeenCalled();
 expect(host.querySelector('[aria-label="Measured modular neural signal flow"]')).toBeTruthy();
 expect(host.textContent).toContain('Bounded inspection preview');
});
it('does not call the stream unreachable while the stream is what is delivering',async()=>{
 // Turning the interval off does not stop the query's one mount fetch. If that fetch fails while
 // frames are arriving, the panel must not tell the reader the state is unreachable.
 open();act(()=>useMlStreamStore.getState().accept(frame(true,measured)));
 state.isError=true;
 await act(async()=>root.render(<LiveModularFlow/>));
 expect(host.querySelector('[role="alert"]')).toBeNull();
 expect(host.textContent).not.toContain('temporarily unreachable');
});
it('takes over the refresh itself when the socket drops',async()=>{
 open();act(()=>useMlStreamStore.getState().accept(frame(true,measured)));
 await act(async()=>root.render(<LiveModularFlow/>));
 expect(state.refresh).not.toHaveBeenCalled();
 // Nothing else would now ask for a new measurement, so the panel's own kick has to come back.
 act(()=>useMlStreamStore.getState().setStatus('closed'));
 expect(state.live).toBe(false);
 expect(state.refresh).toHaveBeenCalledTimes(1);
});

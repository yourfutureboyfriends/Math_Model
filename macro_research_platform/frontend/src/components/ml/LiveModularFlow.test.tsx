import {act} from 'react';import {createRoot} from 'react-dom/client';import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {LiveModularFlow} from './LiveModularFlow';
const state=vi.hoisted(()=>({data:{} as any,refresh:vi.fn().mockResolvedValue({})}));
vi.mock('./api',()=>({useLiveStateQ:()=>({data:state.data,isError:false}),refreshLiveState:state.refresh}));
vi.mock('./ui/EChart',()=>({EChart:({ariaLabel}:any)=><div role="img" aria-label={ariaLabel}/>,axisStyle:()=>({}),chartTheme:()=>({series:['#00f','#f90'],textStrong:'#fff',muted:'#888',surface:'#000'})}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}});host=document.createElement('div');document.body.append(host);root=createRoot(host);state.refresh.mockClear();});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});
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

import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {ModularNetwork} from './ModularNetwork';
const state=vi.hoisted(()=>({data:null as any}));
vi.mock('./api',()=>({useDeepStatusQ:()=>({data:state.data,isError:false,refetch:vi.fn()})}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});
it('shows configured modules during training without inventing measurements',()=>{
 state.data={configured:{architecture:'modular',profile:'expanded',hidden:64,layers:2,attention_heads:4},training:true,fingerprint:'test'};
 act(()=>root.render(<ModularNetwork/>));
 expect(host.textContent).toContain('Training in background');
 expect(host.textContent).toContain('Rates & credit');
 expect(host.textContent).toContain('No completed training report');
 expect(host.textContent).not.toContain('% routing');
});
it('shows measured feature counts and routing when available',()=>{
 state.data={configured:{architecture:'modular',profile:'expanded',hidden:64,layers:2,attention_heads:4},modules:{news:[0,1],macro_factors:[2,3,4]},routing:[{news:.2,macro_factors:.8}],training_reports:[{parameters:1234}],fingerprint:'test'};
 act(()=>root.render(<ModularNetwork/>));
 expect(host.textContent).toContain('2 transformed inputs · 20.0% routing');
 expect(host.textContent).toContain('3 transformed inputs · 80.0% routing');
 expect(host.textContent).toContain('not causal importance');
});

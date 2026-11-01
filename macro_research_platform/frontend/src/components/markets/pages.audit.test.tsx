import { act } from 'react';import { createRoot } from 'react-dom/client';import { beforeEach,afterEach,it,expect,vi } from 'vitest';
import { FUNCTIONS } from './functions';import { MarketBody,SecurityBody,MarketsPage } from '@/pages/MarketsPage';
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:{username:'audit',role:'viewer'}})}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.clear();sessionStorage.clear();
 vi.stubGlobal('fetch',vi.fn(()=>new Promise(()=>{})));vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
 vi.stubGlobal('IntersectionObserver',class{observe(){}disconnect(){}});vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener(){},removeEventListener(){}}));
 Object.defineProperty(Element.prototype,'scrollIntoView',{configurable:true,writable:true,value:vi.fn()});
 Object.defineProperty(window,'scrollTo',{configurable:true,writable:true,value:vi.fn()});
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.restoreAllMocks();vi.unstubAllGlobals();});
for(const phase of ['pending','unavailable'])for(const f of FUNCTIONS.filter(f=>f.code!=='LP'))it(`${f.code}: renders its page when feeds are ${phase}`,async()=>{
 if(phase==='unavailable')vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:404,json:async()=>({detail:'Not published for this instrument.'})})));
 await act(async()=>root.render(f.security?<SecurityBody code={f.code} symbol="AAPL" d={{symbol:'AAPL',name:'Apple',type:'Stock',price:100,currency:'USD',market_state:'REGULAR'}} isFund={false} onGo={()=>{}}/>:<MarketBody code={f.code} open={()=>{}} onGo={()=>{}} classic={false}/>));
 expect(host.childNodes.length).toBeGreaterThan(0);
});
it('LP: restores a malformed saved layout without crashing the workspace',async()=>{
 localStorage.setItem('mkt_lp_v2',JSON.stringify({layout:'2x2',panes:[null,{fn:12},{fn:'WEI',link:'invalid'}]}));window.location.hash='#mkt/lp';
 await act(async()=>root.render(<MarketsPage/>));expect(host.textContent).toContain('Layout');
});

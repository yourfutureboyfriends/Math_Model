import { act } from 'react';import { createRoot } from 'react-dom/client';import { it,expect,vi } from 'vitest';import { MarketsSidebar } from './MarketsSidebar';
const mocks=vi.hoisted(()=>({go:vi.fn()}));
vi.mock('@/lib/marketsRoute',()=>({useMarketsRoute:()=>({fn:'MAP'}),goMarkets:mocks.go}));
vi.mock('@/lib/region',()=>({useRegion:()=> 'europe',setRegion:vi.fn(),REGIONS:[{id:'global',label:'Global'},{id:'europe',label:'Europe'},{id:'americas',label:'Americas'},{id:'apac',label:'Asia Pacific'},{id:'mea',label:'Middle East & Africa'}]}));
it('handles malformed recent storage, searches countries across regions, and keeps codes in collapsed mode',()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.setItem('mkt_recent','{"unexpected":true}');const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 try{
  act(()=>root.render(<MarketsSidebar/>));expect(host.querySelector('[aria-current="page"]')?.textContent).toContain('MAP');
  const input=host.querySelector('input')!;act(()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'Japan');input.dispatchEvent(new Event('input',{bubbles:true}));});
  const japan=host.querySelector('[title="Japan"]') as HTMLButtonElement;expect(japan).not.toBeNull();act(()=>japan.click());expect(mocks.go).toHaveBeenCalledWith('CTRY','JP');
  act(()=>root.render(<MarketsSidebar collapsed/>));expect(host.querySelector('input')).toBeNull();expect(host.textContent).toContain('MAP');
 }finally{act(()=>root.unmount());host.remove();localStorage.clear();vi.unstubAllGlobals();}
});

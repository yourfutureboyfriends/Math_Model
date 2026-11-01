import {act}from'react';import{createRoot}from'react-dom/client';import{beforeEach,afterEach,it,expect,vi}from'vitest';import{ScreenerView}from'./ScreenerView';
const mock=vi.hoisted(()=>({urls:[] as string[]}));
vi.mock('./shared',async importOriginal=>({...await importOriginal<typeof import('./shared')>(),useJSON:(url:string|null)=>{if(url?.includes('/screen?'))mock.urls.push(url);return {data:url?.includes('/meta')?{regions:[{id:'us',name:'United States',currency:'USD'}],sectors:['Technology']}:url?.includes('/screen?')?{rows:[{symbol:'AAPL',name:'Apple',sector:'Technology',currency:'USD',price:200,change_pct:.01},{symbol:'MSFT',name:'Microsoft',sector:'Technology',currency:'USD',price:400,change_pct:-.02}],next_offset:null}:null,error:null,loading:false};}}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.clear();mock.urls=[];host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();localStorage.clear();vi.unstubAllGlobals();});
const enter=(input:HTMLInputElement,value:string)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));};
it('distinguishes edited filters from the last applied result set',async()=>{
 await act(async()=>root.render(<ScreenerView onOpen={()=>{}}/>));act(()=>enter(host.querySelectorAll<HTMLInputElement>('input[type="number"]')[0],'50'));expect(host.textContent).toContain('last applied screen');
 act(()=>{Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Apply changes →')!.click();});expect(host.textContent).not.toContain('last applied screen');expect(new URL(mock.urls.at(-1)!,'http://local').searchParams.get('market_cap_min')).toBe('50000000000');
});
it('rejects reversed ranges and filters only the visible page locally',async()=>{
 await act(async()=>root.render(<ScreenerView onOpen={()=>{}}/>));const numbers=host.querySelectorAll<HTMLInputElement>('input[type="number"]');act(()=>{enter(numbers[0],'100');enter(numbers[1],'20');});act(()=>{Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Screen')!.click();});expect(host.textContent).toContain('minimum cannot exceed');expect(new Set(mock.urls).size).toBe(1);
 act(()=>enter(host.querySelector('[aria-label="Filter companies on this page"]')!,'Microsoft'));expect(host.querySelector('tbody')?.textContent).toContain('MSFT');expect(host.querySelector('tbody')?.textContent).not.toContain('AAPL');
});

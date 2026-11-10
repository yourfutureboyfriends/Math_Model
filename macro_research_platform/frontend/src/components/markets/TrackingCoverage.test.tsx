import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {TrackingCoverage,MaritimeTrade} from './TrackingCoverage';
const fixture=vi.hoisted(()=>({feeds:{} as Record<string,any>,urls:[] as (string|null)[]}));
vi.mock('./shared',async original=>({...await original<typeof import('./shared')>(),useJSON:(url:string|null)=>{fixture.urls.push(url);return {data:fixture.feeds[url??'']??null,loading:false,error:null,retry:vi.fn()};}}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);fixture.feeds={};fixture.urls=[];host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});
it('coverage inspection never requests a licensed sample and shows unknown coverage',async()=>{
 fixture.feeds['/api/v1/mkt/tracking/coverage?kind=ship']={providers:[{id:'shipxy',name:'Shipxy',status:'disabled',active:false,configured:false,daily_request_limit:0}],regions:[{id:'shanghai',name:'Shanghai',radius_km:60,observed:0,median_age_s:null,p95_age_s:null,coverage:'coverage unknown'}]};
 await act(async()=>root.render(<TrackingCoverage kind="ship"/>));
 await act(async()=>{(Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Inspect regional coverage')!).click();});
 expect(host.textContent).toContain('No reports');expect(host.textContent).toContain('coverage unknown');
 const request=Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Request licensed sample')!;
 expect(request.disabled).toBe(true);expect(fixture.urls.some(u=>u?.includes('/tracking/region'))).toBe(false);
});
it('trade withholds missing values instead of displaying zero',async()=>{
 fixture.feeds['/api/v1/mkt/tracking/trade']={basis:'Estimated',comparison:'Dated',partial:true,ports:[{port:'Shanghai',as_of:'2026-11-01',imports_t_day:null,exports_t_day:null,calls_day:null,tonnes_yoy:null,complete_window:false}]};
 await act(async()=>root.render(<MaritimeTrade/>));
 await act(async()=>{(Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Load port-trade data')!).click();});
 expect(host.textContent).toContain('comparisons are withheld');expect(host.textContent).toContain('Incomplete / withheld');
 expect(Array.from(host.querySelectorAll('tbody td')).filter(td=>td.textContent==='—')).toHaveLength(4);
});

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { it,expect,vi } from 'vitest';
import topo from '../../../public/world-atlas/countries-50m.json';
import { WorldMap } from './WorldMap';
vi.mock('./shared',()=>({useJSON:(url:string)=>({data:url.includes('/map/world')?{countries:{US:{name:'United States',change_ytd:.1}},sources:{}}:{economies:[]},loading:false,error:null}),Loading:()=>null,ErrorBox:()=>null,Chg:()=>null,fmtPct:String,fmtPrice:String}));
vi.mock('./LiveTV',()=>({LiveTV:()=> <div data-testid="live-video">Live video</div>}));
// The map draws on a canvas (ECharts); this stand-in exposes the fills WorldMap computes, one path per country.
vi.mock('./AtlasMap2D',async()=>{const {forwardRef}=await import('react');return {AtlasMap2D:forwardRef((p:any,_r)=><svg className="atlas-map-svg" aria-label={p.title}>
  {['US',...Object.keys(p.fills).filter(k=>k!=='US')].map(iso=><path key={iso} data-iso={iso} fill={p.fills[iso]??'var(--atlas-no-data)'}/>)}</svg>)};});
it('renders data layers without autoplay video and opens coverage only on request',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>topo})));localStorage.setItem('mkt_map_mode','invalid');
 const host=document.createElement('div');document.body.append(host);const root=createRoot(host);
 try{
  await act(async()=>root.render(<WorldMap onOpen={()=>{}}/>));
  expect(host.querySelector('svg.atlas-map-svg')).not.toBeNull();expect(host.querySelector('[data-testid="live-video"]')).toBeNull();
  expect(host.querySelector('[data-iso="US"]')?.getAttribute('fill')).not.toBe('var(--atlas-no-data)');
  const layer=host.querySelector('[aria-label="Map data layer"]') as HTMLSelectElement;
  act(()=>{layer.value='m1';layer.dispatchEvent(new Event('change',{bubbles:true}));});
  expect(host.querySelector('[data-iso="US"]')?.getAttribute('fill')).toBe('var(--atlas-no-data)');
  const locator=host.querySelector('[aria-label="Locate stock exchange"]') as HTMLSelectElement;
  act(()=>{locator.value='tokyo';locator.dispatchEvent(new Event('change',{bubbles:true}));});
  expect(host.querySelector('.atlas-exchange-detail')?.textContent).toContain('Tokyo Stock Exchange');
  const coverage=host.querySelector('.atlas-coverage-toggle') as HTMLButtonElement;act(()=>coverage.click());expect(host.querySelector('[data-testid="live-video"]')).not.toBeNull();
  act(()=>coverage.click());expect(host.querySelector('[data-testid="live-video"]')).toBeNull();
 }finally{act(()=>root.unmount());host.remove();localStorage.clear();vi.unstubAllGlobals();}
});

it('colours by class with green for strength, shows the key, summary and the selected country\'s rank', async () => {
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true); vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => topo })));
 const host = document.createElement('div'); document.body.append(host); const root = createRoot(host);
 try {
  await act(async () => root.render(<WorldMap onOpen={() => {}} />));
  expect(host.querySelectorAll('.atlas-class').length).toBe(8);                      // seven classes plus "no data"
  expect(host.querySelector('.atlas-summary')?.textContent).toContain('United States');
  expect(host.querySelector('[data-iso="US"]')?.getAttribute('fill')).toBe('#3fd3a2');   // a positive YTD return: strongest green
  act(() => { (host.querySelector('.atlas-bar-row') as HTMLButtonElement).click(); });
  expect(host.querySelector('.atlas-focus')?.textContent).toContain('#1');
 } finally { act(() => root.unmount()); host.remove(); localStorage.clear(); vi.unstubAllGlobals(); }
});

import { act, forwardRef } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FlightTracker } from './FlightTracker';
import { ShipTracker } from './ShipTracker';
const fixtures=vi.hoisted(()=>({feeds:{} as Record<string,any>,now:1793620800}));
vi.mock('./shared',async original=>({...await original<typeof import('./shared')>(),useJSON:(url:string)=>({data:fixtures.feeds[url]??null,current:!!fixtures.feeds[url],loading:false,error:null,refreshError:null,retry:vi.fn()})}));
vi.mock('./LiveMap',async original=>({...await original<typeof import('./LiveMap')>(),LiveMap:forwardRef(({points,children}:any,_ref)=><div data-map>{points.map((p:any)=><span key={p.id} data-position={p.id}/>)}{children}</div>)}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);vi.spyOn(Date,'now').mockReturnValue(fixtures.now*1000);localStorage.clear();fixtures.feeds={};host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.restoreAllMocks();vi.unstubAllGlobals();});
it('flight map hides expired fixes and defaults to reported coordinates',async()=>{
 fixtures.feeds['/api/v1/mkt/fly/world']={cols:['hex','callsign','country','lon','lat','alt','ground','speed','track','vrate','squawk','fix','mil','type','tag'],rows:[['fresh','TEST1','US',1,2,30000,0,300,90,0,null,fixtures.now-20,0,'A320',''],['expired','OLD1','US',1,2,30000,0,300,90,0,null,fixtures.now-7200,0,'A320','']],time:fixtures.now,airborne:2,on_ground:0,military:0,emergencies:[]};
 await act(async()=>root.render(<FlightTracker/>));
 expect(host.querySelector('[data-position="fresh"]')).not.toBeNull();expect(host.querySelector('[data-position="expired"]')).toBeNull();
 const project=Array.from(host.querySelectorAll('label')).find(l=>l.textContent?.includes('estimate position'))!;
 expect(project.querySelector('input')?.checked).toBe(false);expect(host.textContent).toContain('Air traffic monitor');
});
it('ship map keeps historical cells separate from recent receiver fixes',async()=>{
 const cols=['mmsi','lat','lon','speed','heading','type','status','name','sat','tag','t'];
 fixtures.feeds['/api/v1/mkt/ship/world?layer=live']={cols,types:['Cargo'],rows:[[1,1,2,0,null,0,null,'Fresh',0,'',fixtures.now-30],[2,1,2,0,null,0,1,'Expired',0,'',fixtures.now-7200]],time:fixtures.now,status:'live',phase:{},live_count:2};
 fixtures.feeds['/api/v1/mkt/ship/world?layer=sat']={cols,types:['Cargo'],rows:[[3,1,2,null,null,0,null,'Historical',1,'',fixtures.now-86400]],satellite:{day:'2026-11-01'}};
 await act(async()=>root.render(<ShipTracker/>));
 expect(host.querySelector('[data-position="1"]')).not.toBeNull();expect(host.querySelector('[data-position="2"]')).toBeNull();expect(host.querySelector('[data-position="3"]')).toBeNull();
 await act(async()=>{(Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Historical AIS cells') as HTMLButtonElement).click();});
 expect(host.querySelector('[data-position="3"]')).not.toBeNull();expect(host.querySelector('[data-position="1"]')).toBeNull();
 expect(host.textContent).toContain('Maritime activity monitor');expect(host.textContent).toContain('Port presence');
});
it('does not require receiver data to display independently dated historical evidence',async()=>{
 localStorage.setItem('view.ship.history.v2','true');
 const cols=['mmsi','lat','lon','type','name','t'];
 fixtures.feeds['/api/v1/mkt/ship/world?layer=sat']={cols,types:['Cargo'],rows:[[123456789,1.2,103.4,0,'Historical only',fixtures.now-3*86400]],satellite:{day:'2026-10-30',status:'partial',boxes_failed:2}};
 fixtures.feeds['/api/v1/mkt/ship/ports']={as_of:fixtures.now-1000,ports:[{port:'Stale port',total:9,anchored:9}]};
 await act(async()=>root.render(<ShipTracker/>));
 expect(host.querySelector('[data-position="123456789"]')).not.toBeNull();
 expect(host.textContent).toContain('partial');expect(host.textContent).toContain('Counts are withheld');expect(host.textContent).not.toContain('Stale port');
});

import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {StreamBadge} from './StreamBadge';
import type {StreamStatus} from '@/store/mlStreamStore';

const render=(props:Partial<Parameters<typeof StreamBadge>[0]>)=>
 act(async()=>root.render(<StreamBadge status="idle" error={null} reconnects={0} gaps={{}} {...props}/>));
const pill=()=>host.querySelector('[role="status"]') as HTMLSpanElement;
const label=()=>pill()?.textContent;
const detail=()=>pill()?.getAttribute('title')??'';

let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);host=document.createElement('div');document.body.append(host);root=createRoot(host);});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});

it('claims a live push only while the socket is open',async()=>{
 await render({status:'open'});
 expect(label()).toBe('Live push');
 expect(pill().dataset.tone).toBe('ok');
 expect(detail()).toContain('their own polls are off');
});

it('says the panels are polling whenever the socket is not open',async()=>{
 // The failure this badge exists for: a dropped socket leaves the panels on their polls, and
 // without this nothing on the page distinguishes that from being pushed to.
 for(const status of ['connecting','closed','unauthorized','error','idle'] as StreamStatus[]){
  await render({status});
  expect(detail(),status).toContain('polling on their own timers');
  expect(label(),status).not.toBe('Live push');
 }
});

it('names the transport fault rather than reporting a generic slowdown',async()=>{
 await render({status:'closed'});
 expect(label()).toBe('Stream dropped · polling');
 expect(pill().dataset.tone).toBe('warn');
 await render({status:'unauthorized'});
 expect(label()).toBe('Stream refused · polling');
 await render({status:'error',error:'Unsupported stream schema v2'});
 expect(label()).toBe('Stream error · polling');
 expect(detail()).toContain('Unsupported stream schema v2');
});

it('shows a flapping link and coalesced frames instead of letting them self-heal silently',async()=>{
 await render({status:'open',reconnects:3,gaps:{deep_live:2,research_graph:5}});
 expect(detail()).toContain('Reconnected 3× since this page was opened.');
 expect(detail()).toContain('7 frames were coalesced away');
});

it('omits the counters while nothing has been dropped or reconnected',async()=>{
 await render({status:'open'});
 expect(detail()).not.toContain('Reconnected');
 expect(detail()).not.toContain('coalesced');
});

it('labels every status the stream can be in',async()=>{
 for(const status of ['open','connecting','closed','unauthorized','error','idle'] as StreamStatus[]){
  await render({status});
  expect(label(),status).toBeTruthy();
  expect(label(),status).not.toContain('undefined');
 }
});

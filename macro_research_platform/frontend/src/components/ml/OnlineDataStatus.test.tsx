import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {OnlineDataStatus} from './OnlineDataStatus';
import {type StreamFrame,useMlStreamStore} from '@/store/mlStreamStore';

// Records the `live` argument the panel passes, so "the poll stopped" is asserted rather than assumed.
const state=vi.hoisted(()=>({data:null as any,isError:false,live:null as boolean|null}));
vi.mock('./api',()=>({useOnlineStatusQ:(live=false)=>{state.live=live;return {data:state.data,isError:state.isError};}}));

const frame=(ok:boolean,payload:unknown,error:string|null=null):StreamFrame=>
 ({v:1,topic:'system1_inference',channel:'online_status',seq:1,ok,payload,error,computed_ms:1.5,sent_at:'2026-11-07T00:00:00.000Z'});
const polled={enabled:false,running:false,last_check:null,policy:'Polled policy',sources:[],learning:'Polled learning'};
const pushed={enabled:true,running:true,last_check:1762473600,policy:'Pushed policy',sources:[{id:'fred',title:'FRED',used_for:'inputs',status:'ok',last_success:1762473600,quality:{series:130,latest:'2026-10'}}],learning:'Pushed learning'};
const open=()=>act(()=>useMlStreamStore.getState().setStatus('open'));

let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);useMlStreamStore.getState().reset();host=document.createElement('div');document.body.append(host);root=createRoot(host);state.data=null;state.isError=false;state.live=null;});
afterEach(()=>{act(()=>root.unmount());host.remove();useMlStreamStore.getState().reset();vi.unstubAllGlobals();});

it('serves the pushed frame and stops polling for the same state',async()=>{
 open();act(()=>useMlStreamStore.getState().accept(frame(true,pushed)));
 state.data=polled;
 await act(async()=>root.render(<OnlineDataStatus/>));
 expect(state.live).toBe(true);
 expect(host.textContent).toContain('Online supervision enabled');
 expect(host.textContent).toContain('Pushed policy');
 expect(host.textContent).not.toContain('Polled policy');
 expect(host.textContent).toContain('130 series · through 2026-10');
});

it('resumes the poll when the producer failed instead of rendering the failure as a reading',async()=>{
 // ok:false means online.status() raised. Its payload is null, so serving it would blank the panel;
 // the guard must hand the panel back to the poll, which has its own error state.
 open();act(()=>useMlStreamStore.getState().accept(frame(false,null,'RuntimeError: provider refresh failed')));
 state.data=polled;
 await act(async()=>root.render(<OnlineDataStatus/>));
 expect(state.live).toBe(false);
 expect(host.textContent).toContain('Polled policy');
 expect(host.textContent).toContain('Online supervision disabled');
 expect(host.textContent).not.toContain('RuntimeError');
});

it('hands a good frame back to the poll once the socket drops rather than freezing on it',async()=>{
 // The store never expires a frame, so without the connection gate this panel would keep serving
 // the pre-drop reading forever with its poll switched off — a stale value that looks live.
 open();act(()=>useMlStreamStore.getState().accept(frame(true,pushed)));
 state.data=polled;
 await act(async()=>root.render(<OnlineDataStatus/>));
 expect(host.textContent).toContain('Pushed policy');
 act(()=>useMlStreamStore.getState().setStatus('closed'));
 expect(state.live).toBe(false);
 expect(host.textContent).toContain('Polled policy');
 expect(host.textContent).not.toContain('Pushed policy');
});

it('polls while no frame has arrived and says so rather than inventing a status',async()=>{
 open();
 await act(async()=>root.render(<OnlineDataStatus/>));
 expect(state.live).toBe(false);
 expect(host.textContent).toContain('Loading provider supervision…');
});

it('reports the source as unavailable when neither transport has a reading',async()=>{
 state.isError=true;
 await act(async()=>root.render(<OnlineDataStatus/>));
 expect(host.textContent).toContain('Provider supervision status is unavailable.');
});

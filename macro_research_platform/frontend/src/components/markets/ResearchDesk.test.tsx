import {act} from 'react';import {createRoot} from 'react-dom/client';import {it,expect,vi} from 'vitest';
import {ResearchDesk} from './ResearchDesk';
const server=vi.hoisted(()=>({rows:[] as any[]}));
vi.mock('@/lib/serverResearch',()=>({loadServerResearch:async()=>({observations:[],theses:server.rows}),saveResearchRecord:async(_kind:string,r:any)=>{const saved={...r,_serverVersion:(r._serverVersion??0)+1};server.rows=[...server.rows.filter(x=>x.id!==r.id),saved];return saved;},saveServerObservation:vi.fn()}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:{username:'tester'}})}));
vi.mock('./shared',()=>({Panel:({title,children}:any)=><section><h2>{title}</h2>{children}</section>,ErrorBox:({msg}:any)=>msg?<p>{msg}</p>:null,useJSON:()=>({data:{watchlists:[],alerts:[]}})}));
it('creates, edits and preserves a thesis across remounts',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.clear();server.rows=[];const host=document.createElement('div');document.body.append(host);let root=createRoot(host);
 const click=async(text:string)=>act(async()=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent===text)!.click());
 const fill=async(value:string,index:number)=>act(async()=>{const el=host.querySelectorAll('form input')[index];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(el,value);el.dispatchEvent(new Event('input',{bubbles:true}));});
 try{
  await act(async()=>root.render(<ResearchDesk/>));await click('Theses');
  await fill('MSFT',0);await fill('Margins improve',1);await fill('Next earnings',2);await fill('Margins fall',3);await fill('2027-01-01',4);
  await act(async()=>host.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  expect(host.textContent).toContain('Invalidated if: Margins fall');
  await click('Edit / reschedule');await fill('Revised thesis',1);await act(async()=>host.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  act(()=>root.unmount());root=createRoot(host);await act(async()=>root.render(<ResearchDesk/>));await click('Theses');expect(host.textContent).toContain('Revised thesis');expect(host.querySelectorAll('article')).toHaveLength(1);
 }finally{act(()=>root.unmount());host.remove();localStorage.clear();vi.unstubAllGlobals();}
});

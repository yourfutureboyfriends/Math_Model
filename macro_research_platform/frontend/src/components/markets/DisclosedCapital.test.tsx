import {act} from 'react';import {createRoot} from 'react-dom/client';import {it,expect,vi} from 'vitest';
import {DisclosedCapital} from './DisclosedCapital';
const calls=vi.hoisted(()=>[] as (string|null)[]);
vi.mock('./shared',async()=>{const actual=await vi.importActual<any>('./shared');return {...actual,useJSON:(url:string|null)=>{calls.push(url);return {data:null,loading:false,error:null,retry:vi.fn()};}};});
it('does not imply a live hidden-money feed or automatically fan out SEC requests',()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);calls.length=0;const host=document.createElement('div');const root=createRoot(host);
 try{act(()=>root.render(<DisclosedCapital onOpen={()=>{}}/>));expect(calls.every(x=>x===null)).toBe(true);expect(host.textContent).toContain('not identify undisclosed beneficial owners');expect(host.textContent).toContain('No market-wide insider scan');const buttons=host.querySelectorAll('[role=tab]');act(()=>(buttons[1] as HTMLButtonElement).click());expect(host.textContent).toContain('Missing history will not be labelled a new position');expect(calls.every(x=>x===null)).toBe(true);
 }finally{act(()=>root.unmount());vi.unstubAllGlobals();}
});

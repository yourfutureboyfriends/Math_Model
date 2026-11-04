import {act} from 'react';import {createRoot} from 'react-dom/client';import {expect,it,vi} from 'vitest';
import {ConnectedTools,parseCSV} from './ConnectedTools';
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:{username:'tester',role:'analyst'}})}));
vi.mock('./shared',()=>({Panel:({children,title,right}:any)=><section><h2>{title}</h2>{right}{children}</section>,ErrorBox:()=>null,useJSON:()=>({data:null,retry:vi.fn()})}));
it('reads quoted broker CSV and refuses missing or nonfinite quantities',()=>{
 expect(parseCSV('symbol,quantity,currency\n"BRK-B",2,USD')).toEqual([{symbol:'BRK-B',quantity:2,currency:'USD'}]);
 expect(()=>parseCSV('symbol,quantity,currency\nA,,USD')).toThrow('Missing numeric');
 expect(()=>parseCSV('symbol,quantity,currency\nA,Infinity,USD')).toThrow('Invalid number');
 expect(()=>parseCSV('symbol,quantity,currency\n"A,1,USD')).toThrow('Unclosed');
});
it('opens all eight connected workflows without automatically starting monitoring',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);const host=document.createElement('div'),root=createRoot(host);const fetcher=vi.fn();vi.stubGlobal('fetch',fetcher);
 try{await act(async()=>root.render(<ConnectedTools archive={[]} owner="main:tester" canWrite onRecordsChanged={async()=>{}}/>));
 await act(async()=>Array.from(host.querySelectorAll('button')).find(b=>b.textContent==='Open tools')!.click());
 expect(host.querySelectorAll('[role=tab]')).toHaveLength(8);expect((host.querySelector('input[type=checkbox]') as HTMLInputElement).checked).toBe(false);expect(fetcher).not.toHaveBeenCalled();
 }finally{act(()=>root.unmount());vi.unstubAllGlobals();}
});

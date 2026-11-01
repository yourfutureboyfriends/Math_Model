import {act} from 'react';import {createRoot} from 'react-dom/client';import {it,expect,vi} from 'vitest';
import {ValuationCapture} from './ValuationCapture';
const saved=vi.hoisted(()=>({rows:[] as any[]}));
vi.mock('@/lib/serverResearch',()=>({saveServerObservation:vi.fn(async(symbol:string,kind:string,payload:any)=>{saved.rows.push({symbol,kind,payload});return {};})}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({user:{username:'capture-test'}})}));
it('does not save pending inputs and captures the completed payload under the account/fund key',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);localStorage.clear();saved.rows=[];const host=document.createElement('div');const root=createRoot(host);const payload={currency:'GBP',assumptions:{growth:.04},fairValue:22};
 try{await act(async()=>root.render(<ValuationCapture symbol="VOD.L" payload={payload} disabled/>));act(()=>host.querySelector('button')!.click());expect(saved.rows).toEqual([]);
 await act(async()=>root.render(<ValuationCapture symbol="VOD.L" payload={payload} disabled={false}/>));await act(async()=>host.querySelector('button')!.click());const rows=saved.rows;expect(rows[0].payload.assumptions.growth).toBe(.04);expect(rows[0].payload.currency).toBe('GBP');expect(rows[0].symbol).toBe('VOD.L');expect(host.textContent).toContain('saved to server');
 }finally{act(()=>root.unmount());localStorage.clear();vi.unstubAllGlobals();}
});

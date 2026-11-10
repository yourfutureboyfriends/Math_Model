import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect,it,vi } from 'vitest';
import { CorrelationHeatmap } from './CorrelationHeatmap';
it('keeps missing and invalid coefficients distinct from zero and exposes paired samples',async()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);
 const host=document.createElement('div'),root=createRoot(host);
 try{
  await act(async()=>root.render(<CorrelationHeatmap labels={['A','B','C']} matrix={[[1,NaN,0],[Infinity,1],[0,0,1]]} observations={[[20,0,25]]}/>));
  expect(host.textContent).not.toContain('NaN');expect(host.textContent).not.toContain('Infinity');
  expect(host.querySelectorAll('button')).toHaveLength(9);
  expect(host.querySelector('button[title*="25 paired observations"]')?.textContent).toBe('0.00');
  expect(host.querySelector('button[title*="A vs B"]')?.textContent).toBe('·');
  expect(host.querySelector('button[title*="A vs C"]')?.getAttribute('title')).toContain('little linear co-movement');
 }finally{act(()=>root.unmount());vi.unstubAllGlobals();}
});

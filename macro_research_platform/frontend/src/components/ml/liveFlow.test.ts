import {it,expect} from 'vitest';
import {measuredFlowOption} from './liveFlow';
const theme={series:['blue','gold'],textStrong:'white',muted:'gray'};
const trace={months:Array.from({length:24},(_,i)=>String(i)),tasks:['oil_up_3m']};
const m={modules:['news'],routing:Array.from({length:24},()=>[1]),module_rms:Array.from({length:24},()=>[.5]),memory_rms:Array.from({length:24},()=>.25),attention:Array.from({length:24},(_,i)=>Array(i+1).fill(1/(i+1))),probabilities:Array.from({length:24},()=>[.7])};
it('animates measured lines and uses a bounded number of memory nodes',()=>{
 const option=measuredFlowOption(m,trace,23,theme,true);
 const lines=option.series.filter(s=>s.type==='lines');
 expect(lines.some((s:any)=>s.effect.show&&s.data.length)).toBe(true);
 const nodes=option.series.find(s=>s.type==='scatter') as any;
 expect(nodes.data.length).toBe(16); // module, fusion, 12 grouped states, attention, task
 expect(nodes.data.some((n:any)=>n.label?.formatter?.includes('70.0%'))).toBe(true);
});
it('disables particles without hiding measured nodes',()=>{
 const option=measuredFlowOption(m,trace,0,theme,false);
 expect(option.series.filter(s=>s.type==='lines').every((s:any)=>!s.effect.show)).toBe(true);
 expect((option.series.find(s=>s.type==='scatter') as any).data.length).toBe(5);
});

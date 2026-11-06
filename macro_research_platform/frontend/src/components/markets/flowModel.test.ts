import {it,expect} from 'vitest';
import {countryFlowValues,flowEndpoints} from './flowModel';
it('never mixes pressure scores into a dollar flow layer',()=>{
 const etf={rows:[{iso2:'US',flows:{week_usd:100},mf_1m:.7},{iso2:'JP',mf_1m:-.4}]};
 expect(countryFlowValues('etf',null,null,etf,'m3','total')).toEqual({US:100});
 expect(countryFlowValues('pressure',null,null,etf,'m3','total')).toEqual({US:.7,JP:-.4});
});
it('draws positive outbound flows away from the US and reverses negatives',()=>{
 const us:[number,number]=[1,2],country:[number,number]=[8,9];
 expect(flowEndpoints('out_of_us',10,country,us)).toEqual([us,country]);
 expect(flowEndpoints('out_of_us',-10,country,us)).toEqual([country,us]);
 expect(flowEndpoints('into_us',10,country,us)).toEqual([country,us]);
 expect(flowEndpoints('into_us',-10,country,us)).toEqual([us,country]);
});

import {it,expect,afterEach} from 'vitest';
import {compareNumbers,lookThrough,parseExposures,readArchive,saveObservation} from './researchArchive';
afterEach(()=>localStorage.clear());
it('combines direct and fund exposures without renormalizing missing holdings',()=>{
 const r=lookThrough([{symbol:'A',weight:.2,fund:false},{symbol:'ETF',weight:.8,fund:true}],{ETF:{holdings:[{symbol:'A',weight:.1},{symbol:'B',weight:.2}]}});
 expect(r.rows.find(r=>r.symbol==='A')?.weight).toBeCloseTo(.28);expect(r.uncovered).toBeCloseTo(.56);expect(r.rows.reduce((n,r)=>n+r.weight,0)+r.uncovered).toBeCloseTo(1);
});
it('does not drop unavailable funds or double-count overlapping published weights',()=>{
 expect(lookThrough([{symbol:'X',weight:1,fund:true}],{}).uncovered).toBe(1);
 const r=lookThrough([{symbol:'X',weight:1,fund:true}],{X:{holdings:[{symbol:'A',weight:.8},{symbol:'B',weight:.8}]}});expect(r.rows.reduce((n,r)=>n+r.weight,0)).toBeCloseTo(1);
});
it('validates unique positive long-only input weights',()=>{
 expect(parseExposures('MSFT,20,stock\nSPY,80,fund')).toHaveLength(2);
 for(const x of ['A,110,stock','A,-1,stock','A,50\nA,50','A,60\nB,60','A,0','A,,stock','A,20,typo'])expect(()=>parseExposures(x)).toThrow();
});
it('retains observation timestamps and isolates archive keys',()=>{
 const rows=saveObservation('one',[],'MSFT','earnings',{source:'Test',value:1});expect(readArchive('one')).toEqual(rows);expect(readArchive('two')).toEqual([]);expect(Date.parse(rows[0].observedAt)).toBeGreaterThan(0);
});
it('compares only shared finite numeric fields and reports absolute changes',()=>{
 expect(compareNumbers({a:{x:2},missing:null},{a:{x:3},missing:4})).toEqual([{field:'a.x',before:2,after:3,change:1}]);
});

it('aligns fiscal periods rather than comparing reordered array indices',()=>{
 expect(compareNumbers({eps:[{period:'0q',avg:1},{period:'+1q',avg:2}]},{eps:[{period:'+1q',avg:2},{period:'0q',avg:1}]})).toEqual([]);
});

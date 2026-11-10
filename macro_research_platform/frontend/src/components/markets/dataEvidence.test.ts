import { expect, it } from 'vitest';
import { sourceMeta } from './dataEvidence';
import { recentFix, shipPhase, validPosition, selectVesselReports } from './trackerQuality';
import { pageEvidence } from './PageEvidence';
import { FUNCTIONS } from './functions';
it('keeps missing provenance visible without inferring live or current observations',()=>{
 const m=sourceMeta({rows:[]})!;
 expect(m.supplied).toBe(false);expect(m.asOf).toBeNull();expect(m.delay).toBeNull();
 expect(sourceMeta({source:'Feed',time:1793620800})!.asOf).toMatch(/^2026-/);
 expect(sourceMeta({source:'Feed',as_of:'not a date',delay_minutes:-1})!.asOf).toBeNull();
 expect(sourceMeta({sources:['SEC','FRED']})!.source).toBe('SEC · FRED');
});
it('expires retained positions and preserves unknown maritime status',()=>{
 expect(recentFix(800,1000,120)).toBe(false);expect(recentFix(undefined,1000,120)).toBe(false);
 expect(recentFix(1100,1000,120)).toBe(false);expect(recentFix(990,1000,120)).toBe(true);
 expect(validPosition(NaN,0)).toBe(false);expect(validPosition(0,91)).toBe(false);
 expect(shipPhase(null,0,false)).toBe('unknown');expect(shipPhase(5,0,true)).toBe('unknown');
 expect(shipPhase(1,0,false)).toBe('anchored');
});
it('supplies interpretation guidance for every currently registered Markets page',()=>{
 for(const f of FUNCTIONS)expect(pageEvidence(f.code).length, f.code).toBeGreaterThan(70);
 expect(pageEvidence('COT')).toContain('Tuesday');expect(pageEvidence('SHIP')).toContain('not prove a berth queue');
});

it('falls back to historical AIS only after a recent report expires',()=>{
 const historical={mmsi:1,sat:true,t:100},live={mmsi:1,sat:false,t:990};
 expect(selectVesselReports([live,historical],1000)).toEqual([live]);
 expect(selectVesselReports([live,historical],5000)).toEqual([historical]);
 expect(selectVesselReports([historical,live],1000)).toEqual([live]);
});

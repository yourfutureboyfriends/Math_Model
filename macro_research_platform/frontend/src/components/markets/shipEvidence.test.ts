import { expect,it } from 'vitest';
import { parseVessels,selectMaritimeLayer,observedTrack } from './shipEvidence';
const now=1800000000;
it('separates clocks, expires missing times, and deduplicates by latest report',()=>{
 const data={cols:['mmsi','lat','lon','t','name'],rows:[[1,1,2,now-30,'Recent'],[1,1,2,now-60,'Older'],[2,1,2,now-1000,'Stale'],[3,1,2,null,'Undated']]};
 const rows=parseVessels(data,false);
 expect(selectMaritimeLayer(rows,now,false,900).map(r=>r.name)).toEqual(['Recent']);
 expect(selectMaritimeLayer(rows,now,true,900)).toEqual([]);
 const historic=parseVessels({...data,rows:[[4,1.2,103.4,now-3*86400,'History'],[5,1,2,now-8*86400,'Too old']]},true);
 expect(selectMaritimeLayer(historic,now,true,900).map(r=>[r.lat,r.lon,r.phase])).toEqual([[1.2,103.4,'unknown']]);
});
it('handles malformed compact schemas and missing kinematics',()=>{
 expect(parseVessels({},false)).toEqual([]);
 const rows=parseVessels({cols:['mmsi','lat','lon','speed','heading'],rows:[null,[1,91,2,10,90],[2,1,2,-1,511]]},false);
 expect(rows).toHaveLength(1);expect(rows[0].speed).toBeNull();expect(rows[0].heading).toBeNull();
});
it('breaks track lines at gaps and implausible jumps without inflating distance',()=>{
 const track=[[now-6000,1,2],[now-5700,1,2.01],[now-3000,1,3],[now-2700,40,80],[now-2400,40,80.01]];
 const result=observedTrack(track,now);
 expect(result.breaks).toBe(2);expect(result.segments).toHaveLength(2);expect(result.seconds).toBe(600);expect(result.km).toBeLessThan(3);
 expect(observedTrack([[now+300,1,2],['bad',1,2]],now).segments).toEqual([]);
});

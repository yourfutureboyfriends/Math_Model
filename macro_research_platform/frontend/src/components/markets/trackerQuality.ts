/** UI guards continue to age retained responses when a refresh fails. */
export function validPosition(lon: unknown, lat: unknown): boolean {
  return typeof lon === 'number' && Number.isFinite(lon) && Math.abs(lon) <= 180 && typeof lat === 'number' && Number.isFinite(lat) && Math.abs(lat) <= 90;
}
export function recentFix(fix: unknown, now: number, maxAge: number): fix is number {
  return typeof fix === 'number' && Number.isFinite(fix) && fix > 0 && fix <= now + 30 && now - fix <= maxAge;
}
export function shipPhase(status: number | null, speed: number | null, approximate: boolean): 'unknown' | 'moored' | 'anchored' | 'underway' {
  if (approximate) return 'unknown';
  if (status === 5) return 'moored';
  if (status === 1) return 'anchored';
  if ([0, 8, 11, 12].includes(status as number) || (status == null || status === 15) && speed != null && speed >= 0.5) return 'underway';
  return 'unknown';
}

/** Expire receiver fixes before deduplication so historical coverage can remain available. */
export function selectVesselReports<T extends {mmsi:number;sat:boolean;t:number|null}>(rows:T[],now:number,previous?:T[]):T[] {
  const selected=new Map<number,T>();
  for(const row of rows){
    if(!row.sat&&!recentFix(row.t,now,3600))continue;
    const prior=selected.get(row.mmsi);
    if(!prior || prior.sat&&!row.sat || prior.sat===row.sat&&(row.t??0)>(prior.t??0))selected.set(row.mmsi,row);
  }
  const next=[...selected.values()];
  return previous && previous.length===next.length && next.every((row,i)=>row===previous[i]) ? previous : next;
}

/** Changes use absolute prior EPS so negative estimates retain a meaningful direction. */
export function earningsInsights(estimates: any) {
  const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  return (estimates?.eps ?? []).map((row: any) => {
    const trend = estimates?.eps_trend?.find((r: any) => r.period === row.period);
    const revisions = estimates?.eps_revisions?.find((r: any) => r.period === row.period);
    const prior = trend?.['30daysAgo'], current = trend?.current;
    const up = revisions?.upLast30days, down = revisions?.downLast30days;
    return { period: row.period, analysts: finite(row.numberOfAnalysts) ? row.numberOfAnalysts : null,
      change: finite(prior) && prior !== 0 && finite(current) ? (current - prior) / Math.abs(prior) * 100 : null,
      dispersion: finite(row.avg) && row.avg !== 0 && finite(row.high) && finite(row.low) && row.high >= row.low ? (row.high - row.low) / Math.abs(row.avg) * 100 : null,
      breadth: finite(up) && finite(down) && up >= 0 && down >= 0 && up + down > 0 ? (up - down) / (up + down) * 100 : null };
  });
}

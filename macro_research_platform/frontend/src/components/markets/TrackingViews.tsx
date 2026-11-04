// Physical-economy trackers: SHIP (worldwide live vessels, port congestion, chokepoints), FLY (every aircraft worldwide), QUAK
// (earthquakes and the ports / chokepoints they threaten). One world basemap, zoomable.
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { GeoMap, type GeoPoint } from '@/components/charts/GeoMap';
import { ErrorBox, Loading, Panel, Spark, useJSON } from './shared';
import { LineChart } from '@/components/ui/LineChart';
import { FlightTracker } from './FlightTracker';
import { ShipTracker } from './ShipTracker';

/** World basemap (shared ECharts GeoMap, Equal Earth), opened on a lon/lat box when given; points carry tooltips. */
function Basemap({ box, height = 420, points, onPoint, ariaLabel }: { box?: [number, number, number, number]; height?: number;
  points: GeoPoint[]; onPoint?: (id: string) => void; ariaLabel: string }) {
  const initial = useMemo(() => (box ? { center: [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2] as [number, number],
    zoom: Math.min(8, Math.max(1, Math.min(300 / Math.max(1, box[2] - box[0]), 140 / Math.max(1, box[3] - box[1])) * 0.9)) } : null), [box]);
  return <GeoMap height={height} points={points} onPointClick={onPoint} initial={initial} ariaLabel={ariaLabel} className="border border-border" />;
}

const yoyColor = (v: number | null | undefined) => (v == null ? 'rgb(var(--c-text-tertiary))' : v <= -0.15 ? 'rgb(var(--c-red))' : v >= 0.15 ? 'rgb(var(--c-green))' : 'rgb(var(--c-amber))');
const pc = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%`);

// ── SHIP ────────────────────────────────────────────────────────────────────
export function ShipView() {
  const cp = useJSON<any>('/api/v1/mkt/ship/chokepoints', 3_600_000);
  const [sel, setSel] = useState<string | null>(null);
  const [sort, setSort] = useState<'transits_7d' | 'vs_last_year' | 'vs_1y_avg' | 'tankers_7d' | 'containers_7d'>('transits_7d');
  const chosen = cp.data?.chokepoints.find((c: any) => c.name === sel);
  const list = useMemo(() => [...(cp.data?.chokepoints ?? [])].sort((a: any, b: any) => (sort === 'vs_last_year' || sort === 'vs_1y_avg'
    ? (a[sort] ?? 9) - (b[sort] ?? 9) : (b[sort] ?? -1) - (a[sort] ?? -1))), [cp.data, sort]);
  // weeks behind: PortWatch publishes weekly with about a week's lag; much older means the feed is stuck
  const lagDays = cp.data?.as_of ? Math.round((Date.now() - new Date(cp.data.as_of).getTime()) / 86400000) : null;
  const falls = (cp.data?.chokepoints ?? []).filter((c: any) => c.vs_last_year != null && c.vs_last_year <= -0.15 && (c.transits_7d ?? 0) / (1 + c.vs_last_year) >= 5)   // judged on last year's traffic: a closed strait must show
    .sort((a: any, b: any) => a.vs_last_year - b.vs_last_year).slice(0, 6);
  const sh = (k: typeof sort, l: string) => <th onClick={() => setSort(k)} className={cn('text-right font-normal cursor-pointer select-none', sort === k && 'text-bloomberg')}
    aria-sort={sort === k ? 'descending' : 'none'}>{l}</th>;
  const maxN = Math.max(1, ...(cp.data?.chokepoints ?? []).map((c: any) => c.transits_7d ?? 0));
  return (
    <div className="space-y-3">
      <ShipTracker />
      <Panel title={`Maritime chokepoints — daily transits, 7-day average vs a year ago${cp.data ? ` · data to ${cp.data.as_of}` : ''}`}>
        {cp.loading && !cp.data && <Loading label="Loading IMF PortWatch…" />}
        {cp.error && <ErrorBox msg={cp.error} />}
        {cp.data && lagDays != null && lagDays > 21 && <div className="mb-2 px-2 py-1.5 border border-amber/60 bg-amber/[0.06] text-[11px] text-amber">
          Latest PortWatch data is {lagDays} days old (normally about a week) — the feed may be stuck; figures below are as of {cp.data.as_of}.</div>}
        {falls.length > 0 && <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
          <span className="text-[10px] uppercase tracking-wide text-text-tertiary">Disruption watch</span>
          {falls.map((c: any) => <button key={c.name} onClick={() => setSel(c.name)} className="px-1.5 py-0.5 border border-red/50 text-red hover:bg-red/[0.06]"
            title={`${c.transits_7d?.toFixed(0)} ships/day vs ${(c.transits_7d / (1 + c.vs_last_year)).toFixed(0)} a year ago`}>{c.name} {pc(c.vs_last_year)}</button>)}
          <span className="text-text-tertiary">— 7-day transits ≥ 15% below the same week last year</span></div>}
        {cp.data && (
          <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_520px] gap-3">
            <Basemap height={360} ariaLabel="Maritime chokepoints: traffic and change vs a year ago" onPoint={setSel}
              points={cp.data.chokepoints.filter((c: any) => c.lat != null).map((c: any) => ({ id: c.name, lon: c.lon, lat: c.lat,
                size: 6 + 22 * Math.sqrt((c.transits_7d ?? 0) / maxN), color: yoyColor(c.vs_last_year), selected: sel === c.name, pulse: c.vs_last_year != null && c.vs_last_year <= -0.15,
                label: sel === c.name ? c.name : undefined, tip: `<b>${c.name}</b><br/>${c.transits_7d?.toFixed(0)} ships/day · ${pc(c.vs_last_year)} y/y` }))} />
            <div className="max-h-[360px] overflow-y-auto">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Chokepoint</th>{sh('transits_7d', 'Ships/day')}
                  {sh('vs_last_year', 'vs y/y')}{sh('vs_1y_avg', 'vs 1y avg')}{sh('tankers_7d', 'Tankers')}{sh('containers_7d', 'Box ships')}<th className="font-normal">180d</th></tr></thead>
                <tbody>{list.map((c: any) => (
                  <tr key={c.name} onClick={() => setSel(c.name)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-3', sel === c.name && 'bg-surface-3')} tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}>
                    <td className="py-0.5 text-text-primary">{c.name}</td><td className="text-right font-mono">{c.transits_7d?.toFixed(0)}</td>
                    <td className="text-right font-mono" style={{ color: yoyColor(c.vs_last_year) }}>{pc(c.vs_last_year)}</td>
                    <td className="text-right font-mono" style={{ color: yoyColor(c.vs_1y_avg) }}>{pc(c.vs_1y_avg)}</td>
                    <td className="text-right font-mono text-text-secondary">{c.tankers_7d?.toFixed(0)}</td><td className="text-right font-mono text-text-secondary">{c.containers_7d?.toFixed(0)}</td>
                    <td className="pl-2"><Spark values={c.series.slice(-180).map((x: any) => x.n)} w={70} h={16} /></td></tr>))}</tbody>
              </table>
            </div>
          </div>)}
        {chosen && <div className="mt-2 text-xs text-text-secondary"><span className="text-text-primary font-semibold">{chosen.name}</span> — {chosen.why}. {chosen.transits_7d?.toFixed(0)} ships a day
          ({chosen.tankers_7d?.toFixed(0)} tankers, {chosen.containers_7d?.toFixed(0)} container ships, {chosen.dry_bulk_7d?.toFixed(0)} dry bulk), {pc(chosen.vs_last_year)} vs the same week last year, {pc(chosen.vs_1y_avg)} vs its 1-year average.</div>}
        {(chosen ?? cp.data?.chokepoints?.[0]) && (() => {
          const c = chosen ?? cp.data.chokepoints[0];
          // 7-day averages smooth the day-to-day noise of satellite transit counts
          const rows = c.series.map((x: any, i: number, a: any[]) => {
            const w = a.slice(Math.max(0, i - 6), i + 1);
            const avg = (k: string) => w.reduce((s2: number, y: any) => s2 + (y[k] ?? 0), 0) / w.length;
            return { date: x.date, total: avg('n'), tankers: avg('tankers'), containers: avg('containers'), dry_bulk: avg('dry_bulk') };
          });
          return (
            <div className="mt-3">
              <div className="text-[11px] text-text-tertiary mb-1">{c.name} — daily transits, 7-day average{!chosen ? ' (click a chokepoint to switch)' : ''}</div>
              <div className="mkt-chart-surface"><LineChart rows={rows} x="date" height={260} fmt={(v) => v.toFixed(0)}
                lines={[{ key: 'total', label: 'All ships', color: 'rgb(var(--c-text-primary))' }, { key: 'tankers', label: 'Tankers', color: 'rgb(var(--c-red))' },
                        { key: 'containers', label: 'Container ships', color: 'rgb(var(--c-blue))' }, { key: 'dry_bulk', label: 'Dry bulk', color: 'rgb(var(--c-amber))' }]} /></div>
            </div>);
        })()}
        {cp.data && <div className="text-[10px] text-text-tertiary mt-1">{cp.data.source}. Circle size = traffic; colour = change vs a year ago (red ≤ −15%, green ≥ +15%).
          Counts come from ships' AIS transponders: vessels sailing with AIS switched off — common in conflict zones, e.g. escorted convoys
          through Hormuz in 2026 — are not counted, so a war-zone figure can understate traffic.</div>}
      </Panel>
    </div>
  );
}

// ── FLY ─────────────────────────────────────────────────────────────────────
export function FlyView() {
  return <FlightTracker />;
}

// ── QUAK ────────────────────────────────────────────────────────────────────
export function QuakeView() {
  const { data, error, loading } = useJSON<any>('/api/v1/mkt/quakes', 900_000);
  if (loading && !data) return <Loading label="Loading USGS feed…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  const risky = data.quakes.filter((q: any) => q.trade_risk);
  return (
    <div className="space-y-3">
      {risky.length > 0 && <div className="px-3 py-2 border border-red/60 bg-red/5 text-xs text-red">
        Trade-relevant: {risky.map((q: any) => `M${q.mag} ${q.place} — ${q.chokepoint_km < q.port_km ? `${q.chokepoint_km} km from the ${q.nearest_chokepoint}` : `${q.port_km} km from ${q.nearest_port}`}`).join(' · ')}</div>}
      <Basemap height={400} ariaLabel="Recent earthquakes and trade exposure"
        points={data.quakes.map((q: any) => ({ id: q.time + q.place, lon: q.lon, lat: q.lat, size: 4 + Math.pow(Math.max(0, q.mag - 3.5), 1.6) * 3.2,
          color: q.trade_risk ? 'rgb(var(--c-red))' : 'rgb(var(--c-amber))', pulse: !!q.trade_risk, tip: `<b>M${q.mag}</b> ${q.place}<br/>${q.time.slice(0, 16).replace('T', ' ')} UTC` }))} />
      <div className="border border-border max-h-80 overflow-y-auto">
        <table className="w-full text-[11px]">
          <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left px-2 font-normal">Mag</th><th className="text-left font-normal">Where</th><th className="text-left font-normal">When (UTC)</th>
            <th className="text-left font-normal">Nearest port</th><th className="text-left font-normal">Nearest chokepoint</th><th className="px-2 font-normal">Tsunami</th></tr></thead>
          <tbody>{data.quakes.map((q: any) => (
            <tr key={q.time + q.place} className={cn('border-t border-border-subtle', q.trade_risk && 'text-red')}>
              <td className="px-2 font-mono font-semibold">{q.mag?.toFixed(1)}</td><td><a href={q.url} target="_blank" rel="noreferrer noopener" className="hover:underline">{q.place}</a></td>
              <td className="font-mono text-text-tertiary">{q.time.slice(0, 16).replace('T', ' ')}</td><td>{q.nearest_port} <span className="text-text-tertiary">{q.port_km.toLocaleString()} km</span></td>
              <td>{q.nearest_chokepoint} <span className="text-text-tertiary">{q.chokepoint_km.toLocaleString()} km</span></td><td className="px-2 text-center">{q.tsunami ? '⚠' : ''}</td></tr>))}</tbody>
        </table>
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source}. Red: magnitude 6.5+ within 300 km of a major port or shipping chokepoint.</div>
    </div>
  );
}

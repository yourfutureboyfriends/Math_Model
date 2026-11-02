// Physical-economy trackers: SHIP (worldwide live vessels, port congestion, chokepoints), FLY (every aircraft worldwide), QUAK
// (earthquakes and the ports / chokepoints they threaten). One world basemap, zoomable.
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { countryPaths, projectPoint } from '@/lib/topo';
import { ErrorBox, Loading, Panel, Spark, useJSON } from './shared';
import { LineChart } from '@/components/ui/LineChart';
import { FlightTracker } from './FlightTracker';
import { ShipTracker } from './ShipTracker';

const W = 1000;

/** World basemap in the Equal Earth projection, zoomed to a lon/lat box; children get the projector. */
function Basemap({ box, height = 420, children }: { box?: [number, number, number, number]; height?: number;
  children: (p: (lon: number, lat: number) => [number, number], k: number) => React.ReactNode }) {
  const map=useJSON<import('@/lib/topo').Topology>('/world-atlas/countries-50m.json');
  const topo=map.data;
  const geo = useMemo(() => (topo ? countryPaths(topo, W) : null), [topo]);
  const H = W * 0.487;
  // view box: the requested lon/lat box (with margin), else the whole world
  let vb = { x: 0, y: 0, w: W, h: H };
  if (box) {
    const [lonMin, latMin, lonMax, latMax] = box;
    const pts = [projectPoint(lonMin, latMin, W), projectPoint(lonMax, latMax, W), projectPoint(lonMin, latMax, W), projectPoint(lonMax, latMin, W)];
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const w = Math.max(x1 - x0, 4), h = Math.max(y1 - y0, 4);
    const aspect = W / height;
    const ww = Math.max(w, h * aspect) * 1.1, hh = ww / aspect;
    vb = { x: (x0 + x1) / 2 - ww / 2, y: (y0 + y1) / 2 - hh / 2, w: ww, h: hh };
  }
  const k = W / vb.w;
  const proj = (lon: number, lat: number) => projectPoint(lon, lat, W);
  if(map.error)return <ErrorBox msg={map.error} onRetry={map.retry}/>;
  return (
    <svg viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} width="100%" height={height} className="bg-surface-1 border border-border" role="img">
      <rect x={-W} y={-H} width={W * 3} height={H * 3} fill="rgb(var(--c-sea) / 0.08)" />
      {geo?.shapes.map((s) => <path key={s.id + s.name} d={s.path} fill="rgb(var(--c-surface-3))" stroke="rgb(var(--c-border))" strokeWidth={0.4 / k} />)}
      {children(proj, k)}
    </svg>
  );
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
            <Basemap height={360}>{(p, k) => cp.data.chokepoints.filter((c: any) => c.lat != null).map((c: any) => {
              const [x, y] = p(c.lon, c.lat);
              const r = (3 + 12 * Math.sqrt((c.transits_7d ?? 0) / maxN)) / k;
              return <g key={c.name} onClick={() => setSel(c.name)} className="cursor-pointer">
                <circle cx={x} cy={y} r={r} fill={yoyColor(c.vs_last_year)} fillOpacity={0.55} stroke={sel === c.name ? 'rgb(var(--c-text-primary))' : 'none'} strokeWidth={1.5 / k} />
                <title>{`${c.name}: ${c.transits_7d?.toFixed(0)} ships/day (${pc(c.vs_last_year)} y/y)`}</title></g>;
            })}</Basemap>
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
      <Basemap height={400}>{(p, k) => data.quakes.map((q: any) => {
        const [x, y] = p(q.lon, q.lat);
        return <circle key={q.time + q.place} cx={x} cy={y} r={(Math.pow(q.mag - 3.5, 1.6) * 1.6) / k} fill={q.trade_risk ? 'rgb(var(--c-red))' : 'rgb(var(--c-amber))'} fillOpacity={0.5}>
          <title>{`M${q.mag} ${q.place} · ${q.time}`}</title></circle>;
      })}</Basemap>
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

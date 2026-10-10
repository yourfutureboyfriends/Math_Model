// Physical-economy trackers: SHIP (chokepoints + live vessels), FLY (live aircraft), QUAK
// (earthquakes and the ports / chokepoints they threaten). One world basemap, zoomable.
import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { countryPaths, projectPoint, type Topology } from '@/lib/topo';
import { ErrorBox, Loading, Panel, Spark, useJSON } from './shared';
import { LineChart } from '@/components/ui/LineChart';

let topoCache: Topology | null = null;
const W = 1000;

/** World basemap in the Equal Earth projection, zoomed to a lon/lat box; children get the projector. */
function Basemap({ box, height = 420, children }: { box?: [number, number, number, number]; height?: number;
  children: (p: (lon: number, lat: number) => [number, number], k: number) => React.ReactNode }) {
  const [topo, setTopo] = useState<Topology | null>(topoCache);
  useEffect(() => { if (!topo) fetch('/world-atlas/countries-50m.json').then((r) => r.json()).then((t) => { topoCache = t; setTopo(t); }).catch(() => {}); }, [topo]);
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
  return (
    <svg viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} width="100%" height={height} className="bg-surface-1 border border-border" role="img">
      <rect x={-W} y={-H} width={W * 3} height={H * 3} fill="rgb(var(--c-blue) / 0.06)" />
      {geo?.shapes.map((s) => <path key={s.id + s.name} d={s.path} fill="rgb(var(--c-surface-3))" stroke="rgb(var(--c-border))" strokeWidth={0.4 / k} />)}
      {children(proj, k)}
    </svg>
  );
}

const yoyColor = (v: number | null | undefined) => (v == null ? 'rgb(var(--c-text-tertiary))' : v <= -0.15 ? 'rgb(var(--c-red))' : v >= 0.15 ? 'rgb(var(--c-green))' : 'rgb(var(--c-amber))');
const pc = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(0)}%`);

// ── SHIP ────────────────────────────────────────────────────────────────────
const SEAS: [string, [number, number, number, number]][] = [
  ['Singapore / Malacca', [100, 0, 106, 5]], ['Hong Kong / Pearl River', [112.5, 21.3, 115.5, 23.2]], ['Suez / Red Sea', [31, 26, 35, 32]],
  ['Strait of Hormuz', [54.5, 24.5, 58, 27.5]], ['English Channel', [-3, 49.5, 3, 52]], ['Rotterdam / North Sea', [2.5, 51.3, 5.5, 53]],
  ['LA / Long Beach', [-119, 33.3, -117.8, 34]], ['Shanghai', [121, 30.5, 123, 32]], ['Panama Canal', [-80.2, 8.6, -79.3, 9.6]], ['Baltic (open data)', [19, 59, 26, 61]],
];

export function ShipView() {
  const cp = useJSON<any>('/api/v1/mkt/ship/chokepoints', 3_600_000);
  const [sel, setSel] = useState<string | null>(null);
  const [sea, setSea] = useState(SEAS[0]);
  const box = sea[1];
  const live = useJSON<any>(`/api/v1/mkt/ship/vessels?lon_min=${box[0]}&lat_min=${box[1]}&lon_max=${box[2]}&lat_max=${box[3]}`, 120_000);
  const chosen = cp.data?.chokepoints.find((c: any) => c.name === sel);
  const maxN = Math.max(1, ...(cp.data?.chokepoints ?? []).map((c: any) => c.transits_7d ?? 0));
  const vessels = (live.data?.vessels ?? []).filter((v: any) => v.lon >= box[0] && v.lon <= box[2] && v.lat >= box[1] && v.lat <= box[3]);
  const TYPE_COL: Record<string, string> = { Tanker: 'rgb(var(--c-red))', Cargo: 'rgb(var(--c-blue))', Passenger: 'rgb(var(--c-green))', Fishing: 'rgb(var(--c-amber))' };
  return (
    <div className="space-y-3">
      <Panel title={`Maritime chokepoints — daily transits, 7-day average vs a year ago${cp.data ? ` · data to ${cp.data.as_of}` : ''}`}>
        {cp.loading && !cp.data && <Loading label="Loading IMF PortWatch…" />}
        {cp.error && <ErrorBox msg={cp.error} />}
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
                <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Chokepoint</th><th className="text-right font-normal">Ships/day</th>
                  <th className="text-right font-normal">vs y/y</th><th className="text-right font-normal">Tankers</th><th className="text-right font-normal">Box ships</th><th className="font-normal">180d</th></tr></thead>
                <tbody>{cp.data.chokepoints.map((c: any) => (
                  <tr key={c.name} onClick={() => setSel(c.name)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-3', sel === c.name && 'bg-surface-3')}>
                    <td className="py-0.5 text-text-primary">{c.name}</td><td className="text-right font-mono">{c.transits_7d?.toFixed(0)}</td>
                    <td className="text-right font-mono" style={{ color: yoyColor(c.vs_last_year) }}>{pc(c.vs_last_year)}</td>
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
              <LineChart rows={rows} x="date" height={260} fmt={(v) => v.toFixed(0)}
                lines={[{ key: 'total', label: 'All ships', color: 'rgb(var(--c-text-primary))' }, { key: 'tankers', label: 'Tankers', color: 'rgb(var(--c-red))' },
                        { key: 'containers', label: 'Container ships', color: 'rgb(var(--c-blue))' }, { key: 'dry_bulk', label: 'Dry bulk', color: 'rgb(var(--c-amber))' }]} />
            </div>);
        })()}
        {cp.data && <div className="text-[10px] text-text-tertiary mt-1">{cp.data.source}. Circle size = traffic; colour = change vs a year ago (red ≤ −15%, green ≥ +15%).</div>}
      </Panel>
      <Panel title="Live vessels">
        <div className="flex flex-wrap gap-1 text-xs mb-2">{SEAS.map((s) => (
          <button key={s[0]} onClick={() => setSea(s)} className={cn('px-2 py-0.5 border', sea[0] === s[0] ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{s[0]}</button>))}</div>
        {live.loading && !live.data && <Loading label="Listening to AIS…" />}
        {live.error && <ErrorBox msg={live.error} />}
        {live.data && (
          <>
            <Basemap box={box} height={380}>{(p, k) => vessels.map((v: any) => {
              const [x, y] = p(v.lon, v.lat);
              const moving = (v.speed ?? 0) > 0.5;
              const ang = ((v.course ?? v.heading ?? 0) - 90) * Math.PI / 180;
              const L = 6 / k;
              return <g key={v.mmsi}><circle cx={x} cy={y} r={2.2 / k} fill={TYPE_COL[v.type] ?? 'rgb(var(--c-text-tertiary))'} />
                {moving && <line x1={x} y1={y} x2={x + Math.cos(ang) * L} y2={y + Math.sin(ang) * L} stroke={TYPE_COL[v.type] ?? 'rgb(var(--c-text-tertiary))'} strokeWidth={0.8 / k} />}
                <title>{`${v.name || v.mmsi} · ${v.type}${v.destination ? ` → ${v.destination}` : ''} · ${v.speed ?? 0} kn`}</title></g>;
            })}</Basemap>
            <div className="flex flex-wrap gap-3 text-[11px] text-text-secondary mt-1">
              <span>{vessels.length} vessels in view</span>
              {Object.entries(TYPE_COL).map(([t, c]) => <span key={t}><span className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: c }} />{t} {vessels.filter((v: any) => v.type === t).length}</span>)}
            </div>
            <div className={cn('text-[11px] mt-1', vessels.length === 0 || /only/.test(live.data.coverage) ? 'text-amber' : 'text-text-tertiary')}>
              {live.data.source} — coverage: {live.data.coverage}. {vessels.length === 0 && /only/.test(live.data.coverage) ? 'Pick “Baltic (open data)” or add the key to see this area.' : ''}</div>
          </>)}
      </Panel>
    </div>
  );
}

// ── FLY ─────────────────────────────────────────────────────────────────────
export function FlyView() {
  const ap = useJSON<any>('/api/v1/mkt/fly/airports');
  const [code, setCode] = useState('HKG');
  const [radius, setRadius] = useState(80);
  const a = ap.data?.airports.find((x: any) => x.code === code);
  const { data, error, loading } = useJSON<any>(a ? `/api/v1/mkt/fly?lat=${a.lat}&lon=${a.lon}&radius_nm=${radius}` : null, 30_000);
  const deg = radius / 60;                          // nautical miles → degrees of latitude
  const box: [number, number, number, number] | undefined = a ? [a.lon - deg / Math.cos(a.lat * Math.PI / 180), a.lat - deg, a.lon + deg / Math.cos(a.lat * Math.PI / 180), a.lat + deg] : undefined;
  const altCol = (alt: number | null, ground: boolean) => ground ? 'rgb(var(--c-text-tertiary))' : alt == null ? 'rgb(var(--c-text-secondary))'
    : alt < 10000 ? 'rgb(var(--c-amber))' : alt < 25000 ? 'rgb(var(--c-green))' : 'rgb(var(--c-blue))';
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1 text-xs">
        {(ap.data?.airports ?? []).map((x: any) => <button key={x.code} onClick={() => setCode(x.code)} title={x.name}
          className={cn('px-2 py-0.5 border font-mono', code === x.code ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{x.code}</button>)}
        <span className="ml-2 text-text-tertiary">Radius</span>
        {[30, 80, 150, 250].map((r) => <button key={r} onClick={() => setRadius(r)} className={cn('px-2 py-0.5 border', radius === r ? 'border-bloomberg text-bloomberg' : 'border-border')}>{r} nm</button>)}
      </div>
      {loading && !data && <Loading label="Receiving ADS-B…" />}
      {error && <ErrorBox msg={error} />}
      {data && a && (
        <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_380px] gap-3">
          <div>
            <Basemap box={box} height={460}>{(p, k) => (
              <>
                {[radius / 3, (2 * radius) / 3, radius].map((r) => { const [cx, cy] = p(a.lon, a.lat); const [, ey] = p(a.lon, a.lat + r / 60);
                  return <circle key={r} cx={cx} cy={cy} r={Math.abs(cy - ey)} fill="none" stroke="rgb(var(--c-border-strong))" strokeDasharray={`${3 / k} ${3 / k}`} strokeWidth={0.6 / k} />; })}
                {data.aircraft.map((f: any) => {
                  const [x, y] = p(f.lon, f.lat);
                  const s = 5 / k, rot = f.track ?? 0;
                  return <g key={f.hex} transform={`translate(${x} ${y}) rotate(${rot})`}>
                    <path d={`M0 ${-s} L${s * 0.6} ${s * 0.7} L0 ${s * 0.35} L${-s * 0.6} ${s * 0.7} Z`} fill={f.emergency ? 'rgb(var(--c-red))' : altCol(f.alt, f.on_ground)} />
                    <title>{`${f.flight || f.reg || f.hex} · ${f.type ?? ''} · ${f.on_ground ? 'on ground' : `${f.alt ?? '?'} ft, ${Math.round(f.speed ?? 0)} kt`}${f.emergency ? ` · ${f.emergency}` : ''}`}</title></g>;
                })}
              </>)}</Basemap>
            <div className="flex flex-wrap gap-3 text-[11px] text-text-secondary mt-1">
              <span>{data.airborne} airborne · {data.on_ground} on the ground within {radius} nm of {a.name}</span>
              {[['< 10,000 ft', 'amber'], ['10–25,000 ft', 'green'], ['> 25,000 ft', 'blue']].map(([l, c]) => <span key={l}><span className="inline-block w-2 h-2 mr-1" style={{ background: `rgb(var(--c-${c}))` }} />{l}</span>)}
            </div>
            {data.emergencies.length > 0 && <div className="text-xs text-red mt-1">Emergency squawk: {data.emergencies.map((e: any) => `${e.flight || e.hex} (${e.emergency})`).join(', ')}</div>}
          </div>
          <div className="border border-border max-h-[500px] overflow-y-auto">
            <table className="w-full text-[11px] font-mono">
              <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left px-1.5 font-normal">Flight</th><th className="text-left font-normal">Type</th><th className="text-right font-normal">Alt ft</th><th className="text-right font-normal">Kt</th><th className="text-right px-1.5 font-normal">Hdg</th></tr></thead>
              <tbody>{[...data.aircraft].sort((x: any, y: any) => (y.alt ?? -1) - (x.alt ?? -1)).map((f: any) => (
                <tr key={f.hex} className={cn('border-t border-border-subtle', f.emergency && 'text-red')}><td className="px-1.5">{f.flight || f.reg || f.hex}</td><td className="text-text-secondary">{f.type ?? ''}</td>
                  <td className="text-right">{f.on_ground ? 'GND' : f.alt?.toLocaleString() ?? '—'}</td><td className="text-right">{f.speed != null ? Math.round(f.speed) : ''}</td><td className="text-right px-1.5">{f.track != null ? Math.round(f.track) : ''}</td></tr>))}</tbody>
            </table>
          </div>
        </div>)}
      {data && <div className="text-[10px] text-text-tertiary">{data.source}. Refreshes every 30 seconds.</div>}
    </div>
  );
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

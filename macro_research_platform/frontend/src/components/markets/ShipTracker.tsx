import { TrackingCoverage } from './TrackingCoverage';
import { VesselEvents } from './VesselEvents';
import { recentFix } from './trackerQuality';
import { parseVessels, selectMaritimeLayer, observedTrack, type VesselReport } from './shipEvidence';
// SHIP — every vessel the live AIS network hears, worldwide, on one map: colour by kind, filter
// by kind and by underway / at anchor / moored, click for identity, dimensions, destination, ETA,
// flag and the last 8 hours of track; registry owners and port calls from Global Fishing Watch.
// Below it: port congestion (ships waiting at anchor near 55 major ports).
import { useEffect, useMemo, useRef, useState } from 'react';
import { Anchor, ArrowDown, ArrowUp, Search, Star, X } from 'lucide-react';
import { useStickyState } from '@/lib/stickyState';
import { cn } from '@/lib/utils';
import { ErrorBox, Loading, Panel, useJSON } from './shared';
import { Photos } from './Photos';
import { LiveMap, type LiveMapHandle, type MapBounds, type MapLine, type MapMarker, type MapPoint } from './LiveMap';
import { useFollow } from './follow';

const TYPE_COL: Record<string, string> = {
  Cargo: 'rgb(var(--c-blue))', Tanker: 'rgb(var(--c-red))', Passenger: 'rgb(var(--c-green))', Fishing: 'rgb(var(--c-amber))',
  Tug: 'rgb(20 184 166)', Towing: 'rgb(20 184 166)', Military: 'rgb(236 72 153)', 'Sailing/pleasure': 'rgb(168 85 247)',
  Other: 'rgb(var(--c-text-secondary))', Unknown: 'rgb(var(--c-text-tertiary))',
};
const SEAS: [string, [number, number, number, number]][] = [
  ['Malacca / Singapore', [99, 0, 106, 6]], ['Hong Kong / PRD', [112.5, 21.3, 115.5, 23.2]], ['Shanghai / Ningbo', [120.5, 29.3, 123.5, 32]],
  ['Taiwan Strait', [117.5, 22, 122, 26]], ['Tokyo Bay', [139.4, 34.9, 140.3, 35.7]], ['Hormuz / Gulf', [50, 23.5, 58.5, 28.5]],
  ['Suez / Red Sea', [31, 26, 35, 32]], ['Bab el-Mandeb', [41.5, 11, 45, 14.5]], ['Bosporus', [28.5, 40.8, 29.5, 41.4]],
  ['Gibraltar', [-6.5, 35.5, -4.8, 36.4]], ['English Channel', [-3, 49.5, 3, 52]], ['Rotterdam / Antwerp', [2.5, 51, 5.5, 53]],
  ['Baltic', [10, 53.5, 30, 66]], ['New York', [-74.5, 40.3, -73.6, 40.9]], ['Gulf of Mexico', [-97.5, 26, -88, 30.5]],
  ['LA / Long Beach', [-119, 33.3, -117.8, 34]], ['Panama Canal', [-80.2, 8.6, -79.3, 9.6]], ['Santos', [-46.6, -24.3, -45.9, -23.8]],
];
const DENSITY_ZOOM = 5.5;                 // zoomed out: a density layer; closer in: one marker per ship
const PHASES = [['all', 'All'], ['underway', 'Under way'], ['anchored', 'At anchor'], ['moored', 'Moored'], ['unknown', 'Unknown']] as const;
type Phase = typeof PHASES[number][0];
const faded = (c: string) => c.replace(/\)$/, ' / 0.45)');          // historical AIS cells: days old, drawn fainter

type Sh = VesselReport;
const ageText = (s: number) => (s < 90 ? `${Math.max(0, Math.round(s))} s` : s < 5400 ? `${Math.round(s / 60)} min` : s < 172800 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} d`);
// notable reasons (backend tag letters), most important first, and their ring colours
const TAGS: [string, string, string][] = [['s', 'Sanctioned', 'rgb(239 68 68)'], ['m', 'Military', 'rgb(236 72 153)'], ['l', 'Gas carrier', 'rgb(6 182 212)'],
  ['g', 'Giant', 'rgb(245 158 11)'], ['h', 'Dangerous goods', 'rgb(249 115 22)'], ['z', 'Tanker in a hot zone', 'rgb(234 179 8)']];
const tagColor = (tag: string) => TAGS.find(([k]) => tag.includes(k))?.[2];

export function ShipTracker() {
  // live positions change by the second; historical AIS cells once a day — two requests, so the 30-second refresh stays small
  const world = useJSON<any>('/api/v1/mkt/ship/world?layer=live', 30_000);
  const ports = useJSON<any>('/api/v1/mkt/ship/ports', 120_000);
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [hiddenList, setHiddenList] = useStickyState<string[]>('ship.hidden', []);
  const hidden = useMemo(() => new Set(hiddenList), [hiddenList]);
  const [phase, setPhase] = useStickyState<Phase>('ship.phase', 'all');
  const [showPorts, setShowPorts] = useStickyState('ship.ports', true);
  const [showSat, setShowSat] = useStickyState('ship.history.v2', false);
  const [maxAge, setMaxAge] = useStickyState('ship.maxAge.v2', 900);
  const [region, setRegion] = useState('');
  const satW = useJSON<any>(showSat ? '/api/v1/mkt/ship/world?layer=sat' : null, 1_800_000);
  const [find, setFind] = useState('');
  const [registry, setRegistry] = useState<string | null>(null);
  const [notableOnly, setNotableOnly] = useStickyState('ship.notable', false);
  const [tab, setTab] = useStickyState<'view' | 'notable' | 'follow'>('ship.tab', 'view');
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => { const t = setInterval(() => document.visibilityState === 'visible' && setNow(Date.now() / 1000), 15000); return () => clearInterval(t); }, []);
  useEffect(() => {                                            // Esc closes the open ship / registry card
    const k = (e: KeyboardEvent) => { if (e.key !== 'Escape' || (e.target as HTMLElement)?.closest?.('input, textarea')) return; setSel(null); setRegistry(null); };
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k);
  }, []);
  const follow = useFollow('ship');
  const notable = useJSON<any>(tab==='notable' ? '/api/v1/mkt/ship/notable' : null, 120_000);
  const map = useRef<LiveMapHandle>(null);

  const parsedShips=useMemo(()=>[...parseVessels(world.data,false),...(showSat?parseVessels(satW.data,true):[])],[world.data,satW.data,showSat]);
  const ships=useMemo(()=>selectMaritimeLayer(parsedShips,now,showSat,maxAge),[parsedShips,now,showSat,maxAge]);
  const availableByType = useMemo(() => { const m: Record<string, number> = {}; for (const s of ships) m[s.type] = (m[s.type] ?? 0) + 1; return m; }, [ships]);
  const satInfo = satW.data?.satellite ?? world.data?.satellite;
  const byId = useMemo(() => new Map(ships.map((s) => [String(s.mmsi), s])), [ships]);
  const shown = useMemo(() => ships.filter((s) => !hidden.has(s.type) && (showSat || phase === 'all' || s.phase === phase) && (!notableOnly || s.tag)), [ships, hidden, phase, showSat, notableOnly]);
  const points: MapPoint[] = useMemo(() => shown.map((s) => ({
    id: String(s.mmsi), lon: s.lon, lat: s.lat, color: s.sat ? faded(TYPE_COL[s.type] ?? TYPE_COL.Other) : TYPE_COL[s.type] ?? TYPE_COL.Other, heading: s.heading, moving: (s.speed ?? 0) > 0.5,
    label: s.name || undefined, approx: s.sat, ring: s.tag ? tagColor(s.tag) : undefined, pin: follow.ids.has(String(s.mmsi)),
  })), [shown, follow.ids]);

  const live = useJSON<any>(sel && !showSat ? `/api/v1/mkt/ship/live/${sel}` : null, 30_000);
  const det = live.current && recentFix(live.data?.position_time,now,maxAge) ? live.data : null;
  const lines: MapLine[] = useMemo(() => {
    const out: MapLine[] = [];
    for(const segment of observedTrack(det?.track,now).segments)out.push({coords:segment.map(p=>[p[2],p[1]] as [number,number]),color:'rgb(var(--c-bloomberg))',width:2});
    return out;
  }, [det,now]);
  const markers: MapMarker[] = useMemo(() => {
    const out: MapMarker[] = showPorts && recentFix(ports.data?.as_of,now,300) ? (ports.data?.ports ?? []).filter((p:any)=>p.total>0).map((p: any) => ({
      lon: p.lon, lat: p.lat, id: p.port, color: 'rgb(var(--c-blue))',
      r: 4 + Math.min(14, Math.sqrt(p.anchored) * 1.6), fill: true, label: `${p.port}${p.anchored ? ` · ${p.anchored} at anchor` : ''}`,
    })) : [];
    const to = det?.voyage?.port;
    if (to?.lat != null) out.push({ lon: to.lon, lat: to.lat, color: 'rgb(var(--c-bloomberg))', r: 6, fill: true, label: `Declared destination: ${to.name}` });
    return out;
  }, [ports.data, showPorts, det,now]);

  const inView = useMemo(() => (bounds ? shown.filter((s) => s.lat >= bounds.south && s.lat <= bounds.north
    && (bounds.east - bounds.west >= 360 || ((s.lon - bounds.west + 360) % 360) <= ((bounds.east - bounds.west + 360) % 360))) : shown), [shown, bounds]);
  const viewStats = useMemo(() => {
    const t: Record<string, number> = {}, ph = { underway: 0, anchored: 0, moored: 0, unknown: 0 };
    for (const s of inView) { t[s.type] = (t[s.type] ?? 0) + 1; ph[s.phase]++; }
    return { t, ph };
  }, [inView]);

  const doFind = (e: React.FormEvent) => {
    e.preventDefault();
    const q = find.trim();
    if (!q) return;
    const up = q.toUpperCase();
    const hit = ships.find((s) => String(s.mmsi) === q) ?? ships.find((s) => s.name.toUpperCase() === up) ?? ships.find((s) => s.name.toUpperCase().includes(up));
    if (hit) { setSel(hit.mmsi); setRegistry(null); map.current?.flyTo({ lon: hit.lon, lat: hit.lat, zoom: Math.max(bounds?.zoom ?? 0, 9) }); }
    else { setSel(null); setRegistry(q); }                       // not in the live picture: look it up in the registry
  };
  const hoverText = (id: string) => {
    const s = byId.get(id);
    if (!s) return '';
    return `${s.name || `MMSI ${s.mmsi}`} · ${s.type}\n${s.sat ? 'historical AIS cell' : s.phase === 'underway' ? `${s.speed ?? '?'} kn · ${s.heading ?? '?'}°` : s.phase === 'anchored' ? 'at anchor' : s.phase === 'moored' ? 'moored' : 'status unknown'}`
      + ` · ${s.source??'source unavailable'} / ${s.collectionType??'collection type unavailable'}${s.t ? ` · reported ${ageText(now - s.t)} ago` : s.sat ? `, ${satInfo?.day ?? 'days old'}` : ''}`;
  };
  const toggleType = (t: string) => setHiddenList(hidden.has(t) ? hiddenList.filter((x) => x !== t) : [...hiddenList, t]);
  const isolateType = (t: string) => {                          // click a type in the panel: only that type; again: all
    const others = Object.keys(TYPE_COL).filter((x) => x !== t);
    setHiddenList(others.every((x) => hidden.has(x)) && !hidden.has(t) ? [] : others);
  };


  const w = world.data;
  return (
    <div className="space-y-3">
      <section className="maritime-brief" aria-label="Maritime observation basis">
        <div className="maritime-brief-heading"><div><span className="workspace-eyebrow">MARITIME INTELLIGENCE / OBSERVATION DESK</span><h2>Maritime activity monitor</h2><p>Receiver observations, historical presence and trade activity have different clocks. Select one map layer to keep them separate.</p></div><span className="maritime-source-badge">{showSat?'HISTORICAL CELLS':'RECENT REPORTS'}</span></div>
        <div className="maritime-metrics">
          <div><span>{showSat?'Historical vessels in selected snapshot':'Vessels reported within age limit'}</span><strong>{ships.length.toLocaleString()}</strong><small>{showSat?`Observation day ${satInfo?.day??'not supplied'} · 0.1° cell centres`:`${maxAge/60} minute window · receiver sample`}</small></div>
          <div><span>Filtered vessels in map view</span><strong>{inView.length.toLocaleString()}</strong><small>{shown.length.toLocaleString()} match active filters · no forced watchlist inclusions</small></div>
          <div><span>{showSat?'Historical coverage':'Report freshness'}</span><strong>{showSat?(satInfo?.status??'Unavailable'):`${ships.filter(s=>recentFix(s.t,now,300)).length.toLocaleString()} ≤5m`}</strong><small>{showSat?`${satInfo?.boxes_done??'—'}/${satInfo?.boxes??'—'} areas attempted · ${satInfo?.boxes_failed??'unknown'} failed`:ships.some(s=>s.timeBasis==='receiver_receipt')?'Some ages use receipt time; provider report time unavailable':'Provider report timestamps where supplied'}</small></div>
        </div>
        <div className="maritime-layer-controls"><div role="group" aria-label="Vessel observation layer"><button aria-pressed={!showSat} onClick={()=>{setShowSat(false);setSel(null);}}>Recent receiver reports</button><button aria-pressed={showSat} onClick={()=>{setShowSat(true);setSel(null);}}>Historical AIS cells</button></div>{!showSat&&<label>Maximum report age <select aria-label="Maximum vessel report age" value={maxAge} onChange={e=>setMaxAge(Number(e.target.value))}><option value={300}>5 minutes</option><option value={900}>15 minutes</option><option value={3600}>60 minutes</option></select></label>}</div>
        <p className="maritime-evidence-note">{showSat?'Historical presence is typically several days behind. Squares represent reported grid-cell centres, without artificial displacement; overlapping cells can contain multiple vessels. Speed, heading and current status are unavailable. Cells older than seven days or without a valid timestamp are excluded.':'AIS coverage depends on receivers and transmissions. No report does not establish no vessel, signal suppression, or a closed port. An active connection does not guarantee fresh positions.'} {showSat?'':`Feed: ${world.refreshError?'refresh failed; retained reports expire':w?.status??'loading'}.`}</p>
      </section>
      <TrackingCoverage kind="ship" onRegion={r=>map.current?.flyTo({lon:r.lon,lat:r.lat,zoom:9})}/>
      {!showSat&&world.loading&&!world.data&&<Loading label="Loading recent receiver observations…"/>}
      {!showSat&&world.error&&!world.data&&<ErrorBox msg={world.error} onRetry={world.retry}/>}
      {showSat&&satW.loading&&!satW.data&&<Loading label="Loading historical presence cells…"/>}
      {showSat&&satW.error&&<ErrorBox msg={satW.error} onRetry={satW.retry}/>}
      <div className="mkt-controls flex flex-wrap items-center gap-1 text-[11px]">
        <form onSubmit={doFind} className="flex">
          <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Ship name, MMSI or IMO" aria-label="Find a vessel"
            className="w-48 bg-surface-1 border border-border px-2 py-0.5 text-text-primary placeholder:text-text-tertiary" />
          <button className="px-1.5 border border-l-0 border-border text-text-secondary" aria-label="Find"><Search className="w-3 h-3" /></button>
        </form>
        <label className="inline-flex gap-2 items-center">Region<select aria-label="Maritime region" value={region} onChange={e=>{setRegion(e.target.value);const area=SEAS.find(([n])=>n===e.target.value);if(area)map.current?.fitBounds(area[1]);}}><option value="">Choose a port or sea…</option>{SEAS.map(([n])=><option key={n}>{n}</option>)}</select></label>
      </div>
          <div className="maritime-filter-bar mkt-controls flex flex-wrap gap-2 text-[10px]">
            <div className="mkt-controls flex flex-wrap gap-1 bg-surface-1/85 border border-border px-1.5 py-1">
              {Object.keys(TYPE_COL).map((t) => (
                <button key={t} onClick={() => toggleType(t)} title={hidden.has(t) ? `Show ${t}` : `Hide ${t}`}
                  className={cn('inline-flex items-center gap-1 px-1', hidden.has(t) && 'opacity-35 line-through')}>
                  <span className="w-2 h-2 rounded-full" style={{ background: TYPE_COL[t] }} />{t} <span className="font-mono text-text-tertiary">{(availableByType[t] ?? 0).toLocaleString()}</span></button>))}
            </div>
            <div className="flex gap-1 bg-surface-1/85 border border-border px-1.5 py-1">
              {!showSat&&PHASES.map(([k, l]) => <button key={k} onClick={() => setPhase(k)} className={cn('px-1', phase === k ? 'text-bloomberg' : 'text-text-secondary')}>{l}</button>)}
              <label className="inline-flex items-center gap-1 ml-1 cursor-pointer"><input type="checkbox" checked={showPorts} onChange={(e) => setShowPorts(e.target.checked)} />ports</label>
              <label className="inline-flex items-center gap-1 ml-1 cursor-pointer" title="Only sanctioned, military, gas carriers, giants, dangerous cargo and tankers in hot zones">
                <input type="checkbox" checked={notableOnly} onChange={(e) => setNotableOnly(e.target.checked)} />notable only</label>

            </div>
          </div>
      {ships.length>0||sel!=null||registry?<div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_360px] gap-3">
        <LiveMap ref={map} glyph="ship" points={points} lines={lines} markers={markers} selected={sel != null ? String(sel) : null}
          onSelect={(id) => { setSel(id ? Number(id) : null); setRegistry(null); }} onMarker={(port) => { const p = ports.data?.ports.find((x: any) => x.port === port); if (p) map.current?.flyTo({ lon: p.lon, lat: p.lat, zoom: 10 }); }}
          onView={setBounds} hoverText={hoverText} height={520} initial={{ lon: 60, lat: 25, zoom: 2.2 }} density={DENSITY_ZOOM}>
          {(bounds?.zoom ?? 0) < DENSITY_ZOOM && <div className="absolute top-2 left-2 text-[10px] bg-surface-1/85 border border-border px-2 py-1 flex items-center gap-2">
            <span>{showSat?'Historical cell concentration':'Observed report concentration'}</span><span className="w-20 h-2" style={{ background: 'linear-gradient(90deg, rgb(24 70 140), rgb(0 150 200), rgb(60 210 190), rgb(250 210 90), rgb(255 250 235))' }} />
            <span className="text-text-tertiary">zoom in for individual ships</span></div>}
        </LiveMap>
        <div className="space-y-2 min-w-0">
          {sel != null ? <ShipCard mmsi={sel} ship={byId.get(String(sel))} det={det} loading={live.loading && !det} error={live.error}
              onClose={() => setSel(null)} onRegistry={(q) => setRegistry(q)} follow={follow} />
            : registry ? null : <>
              <div className="flex gap-1 text-[11px]">{([['view', 'In view'], ['notable', 'Notable evidence'], ['follow', `Following ${follow.list.length}`]] as const).map(([k, l]) => (
                <button key={k} onClick={() => setTab(k)} className={cn('flex-1 px-2 py-1 border', tab === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>))}</div>
              {tab === 'view' && <ViewPanel stats={viewStats} inView={inView} now={now} hidden={hidden} onType={isolateType} onPick={(s) => setSel(s.mmsi)} />}
              {tab === 'notable' && <NotablePanel data={notable.data} loading={notable.loading} now={now} historical={showSat} maxAge={maxAge} follow={follow}
                onPick={(x) => { setSel(x.mmsi); map.current?.flyTo({ lon: x.lon, lat: x.lat, zoom: Math.max(bounds?.zoom ?? 0, 7) }); }} />}
              {tab === 'follow' && <FollowPanel follow={follow} byId={byId}
                onPick={(m) => { const s2 = byId.get(m); setSel(Number(m)); if (s2) map.current?.flyTo({ lon: s2.lon, lat: s2.lat, zoom: Math.max(bounds?.zoom ?? 0, 7) }); }} />}
            </>}
          {registry && <VesselCard query={registry} live={undefined} onClose={() => setRegistry(null)} />}
        </div>
      </div>
      :<div className="mkt-empty-state"><h3>No usable observations in this layer</h3><p>{showSat?'No dated historical cells within the seven-day limit. Check snapshot coverage or switch to receiver reports.':'No positions meet the report-age limit. Try a wider age window or check receiver availability; this does not mean the sea is empty.'}</p></div>}
      <div className="text-[10px] text-text-tertiary">{showSat?satInfo?.source:w?.source}. {showSat?'Historical provider cell centres, not current vessel fixes.':w?.coverage}</div>
      <PortCongestion data={ports.data} loading={ports.loading} error={ports.error} now={now} onPick={(p) => map.current?.flyTo({ lon: p.lon, lat: p.lat, zoom: 10 })} />
    </div>
  );
}

type SSort = 'name' | 'type' | 'speed' | 'age';

function ViewPanel({ stats, inView, now, hidden, onType, onPick }: { stats: { t: Record<string, number>; ph: Record<string, number> }; inView: Sh[]; now: number;
  hidden: Set<string>; onType: (t: string) => void; onPick: (s: Sh) => void }) {
  const total = Math.max(1, inView.length);
  const [sort, setSort] = useStickyState<SSort>('ship.sort', 'speed');
  const [desc, setDesc] = useStickyState('ship.desc', true);
  const [q, setQ] = useState('');
  const Q = q.trim().toUpperCase();
  const key = (s: Sh): number | string => (sort === 'name' ? s.name : sort === 'type' ? s.type : sort === 'age' ? (s.t ? now - s.t : 1e9) : s.speed ?? -1);
  const matches = inView.filter((s) => (!Q || s.name.toUpperCase().includes(Q) || String(s.mmsi).startsWith(Q) || s.type.toUpperCase().startsWith(Q)));
  const list=matches.sort((a, b) => { const x = key(a), y = key(b); const c = typeof x === 'string' ? x.localeCompare(String(y)) : x - (y as number); return desc ? -c : c; }).slice(0, 300);
  const th = (k: SSort, l: string, right = false) => (
    <th onClick={() => (sort === k ? setDesc(!desc) : (setSort(k), setDesc(k === 'speed')))} aria-sort={sort === k ? (desc ? 'descending' : 'ascending') : 'none'}
      className={cn('font-normal cursor-pointer select-none whitespace-nowrap px-1.5', right ? 'text-right' : 'text-left', sort === k && 'text-bloomberg')}>
      {l}{sort === k && (desc ? <ArrowDown className="inline w-2.5 h-2.5" /> : <ArrowUp className="inline w-2.5 h-2.5" />)}</th>);
  return (
    <>
      <div className="border border-border bg-surface-1 p-2 text-[11px] space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary">In view <span className="normal-case">— click a type to show only it</span></div>
        <div className="flex h-2 overflow-hidden rounded-sm gap-px">{Object.entries(stats.t).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
          <div key={t} title={`${t}: ${n}`} style={{ width: `${(n / total) * 100}%`, background: TYPE_COL[t] ?? TYPE_COL.Other }} />))}</div>
        <div className="grid grid-cols-2 gap-x-3">{Object.entries(stats.t).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
          <button key={t} onClick={() => onType(t)} className={cn('flex justify-between text-left hover:text-bloomberg', hidden.size > 0 && !hidden.has(t) && 'text-bloomberg')}>
            <span className="inline-flex items-center gap-1 text-text-secondary"><span className="w-2 h-2 rounded-full" style={{ background: TYPE_COL[t] }} />{t}</span><span className="font-mono">{n.toLocaleString()}</span></button>))}</div>
        <div className="flex justify-between border-t border-border-subtle pt-1 text-text-secondary">
          <span>Under way <b className="font-mono text-text-primary">{stats.ph.underway.toLocaleString()}</b></span><span>At anchor <b className="font-mono text-text-primary">{stats.ph.anchored.toLocaleString()}</b></span>
          <span>Moored <b className="font-mono text-text-primary">{stats.ph.moored.toLocaleString()}</b></span>{stats.ph.unknown > 0 && <span>Status unknown <b className="font-mono text-text-primary">{stats.ph.unknown.toLocaleString()}</b></span>}</div>
      </div>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter: name, MMSI or type" aria-label="Filter vessels in view"
        className="w-full bg-surface-1 border border-border px-2 py-0.5 text-[11px] text-text-primary placeholder:text-text-tertiary" />
      <div className="border border-border max-h-[380px] overflow-y-auto">
        <table className="w-full text-[11px]">
          <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary">{th('name', 'Vessel')}{th('type', 'Type')}{th('speed', 'Knots', true)}{th('age', 'Heard', true)}</tr></thead>
          <tbody>{list.map((s) => (
            <tr key={s.mmsi} onClick={() => onPick(s)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}>
              <td className="px-1.5 py-0.5 text-text-primary truncate max-w-[10rem]">{s.tag && <span className="inline-block w-1.5 h-1.5 rounded-full mr-1 align-middle" style={{ background: tagColor(s.tag) }} />}{s.name}</td>
              <td className="px-1.5" style={{ color: TYPE_COL[s.type] }}>{s.type}</td>
              <td className="text-right px-1.5 font-mono">{s.phase === 'underway' ? s.speed?.toFixed(1) ?? '' : s.phase === 'anchored' ? '⚓' : s.phase === 'moored' ? '·' : ''}</td>
              <td className={cn('text-right px-1.5 font-mono', s.sat ? 'text-text-tertiary' : s.t && now - s.t > 1200 ? 'text-amber' : 'text-text-secondary')}>{s.t ? ageText(now - s.t) : s.sat ? 'sat' : ''}</td></tr>))}</tbody>
        </table>
        <p className="p-2 text-[10px] text-text-tertiary">Showing {list.length} of {matches.length} matching reports · capped at 300 rows</p>
        {list.length === 0 && <p className="p-2 text-[11px] text-text-tertiary">{Q ? 'Nothing matches the filter in this view.' : 'No vessel reports match this view.'}</p>}
      </div>
    </>
  );
}

function ShipCard({ mmsi, ship, det, loading, error, onClose, onRegistry, follow }: { mmsi: number; ship?: Sh; det: any; loading: boolean; error: string | null;
  onClose: () => void; onRegistry: (q: string) => void; follow: ReturnType<typeof useFollow> }) {
  const d = det ?? {};
  const name = d.name || ship?.name || `MMSI ${mmsi}`;
  const historical=!!d.satellite||!!ship?.sat;
  const track=observedTrack(det?.track,Date.now()/1000);
  const hours=track.seconds/3600,trackKm=track.km;
  const v = (x: any, unit = '') => (x == null || x === '' ? '—' : `${x}${unit}`);
  const followed = follow.isFollowed(String(mmsi));
  const fNote = follow.list.find((f) => f.id === String(mmsi))?.note ?? '';
  const pf = d.profile ?? {}, voy = d.voyage, lp = d.last_port;
  return (
    <div className="border border-border bg-surface-1 p-2.5 text-xs space-y-2 max-h-[720px] overflow-y-auto">
      <div className="flex items-start justify-between gap-2">
        <div><div className="text-base font-semibold text-text-primary">{name}</div>
          <div className="text-[11px] text-text-secondary"><span style={{ color: TYPE_COL[d.type ?? ship?.type ?? 'Unknown'] }}>{d.type ?? ship?.type}</span>{d.flag ? ` · ${d.flag} flag` : ''}</div></div>
        <div className="flex items-center gap-1">
          <button onClick={() => follow.toggle(String(mmsi), name, d.notable?.[0])} title={followed ? 'Stop following' : 'Follow this ship'}
            className={cn('inline-flex items-center gap-1 px-2 py-0.5 border text-[11px]', followed ? 'border-[rgb(234_179_8)] text-[rgb(202_138_4)]' : 'border-border text-text-secondary')}>
            <Star className={cn('w-3 h-3', followed && 'fill-current')} />{followed ? 'Following' : 'Follow'}</button>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
      </div>
      {d.sanctions && <div className="px-2 py-1.5 border border-red/50 bg-red/[0.07] text-[11px] text-red rounded">
        <b>Sanctioned — US Treasury OFAC SDN list.</b> Programme: {d.sanctions.program}{d.sanctions.name && d.sanctions.name !== name ? ` · listed as ${d.sanctions.name}` : ''}
        {d.sanctions.flag ? ` · listed flag ${d.sanctions.flag}` : ''}. Matched by {d.sanctions.match}.</div>}
      {d.notable?.filter((r: string) => !r.startsWith('US sanctions')).length > 0 && <div className="flex flex-wrap gap-1">{d.notable.filter((r: string) => !r.startsWith('US sanctions')).map((r: string) => (
        <span key={r} className="px-1.5 py-0.5 rounded border border-amber/50 text-amber text-[10px]">{r}</span>))}</div>}
      {followed && <textarea value={fNote} onChange={(e) => follow.setNote(String(mmsi), e.target.value)} rows={2} placeholder="Your notes on this ship…"
        className="w-full bg-surface-2 border border-border px-2 py-1 text-[11px] text-text-primary" aria-label="Notes" />}
      {(det || !loading) && <Photos kind="ship" imo={d.imo} name={name} />}
      <p className="text-[11px] text-text-tertiary">Destination and ETA are crew-entered declarations. Cargo and load are hypotheses, not manifests. Position and registry information can have different dates.</p>
      {d.note && <p className="text-[11px] text-amber">{d.note}</p>}
      <VesselEvents query={String(mmsi)}/>
      {historical&&<p className="maritime-evidence-note">Historical cell only · {ship?.t?new Date(ship.t*1000).toISOString():d.position_time??'observation time unavailable'} · not a current location.</p>}
      {loading && <Loading label="Reading vessel evidence…" />}
      {error && !det && <p className="text-[11px] text-text-tertiary">{error}</p>}
      <div className={cn('px-2 py-1 border text-[11px] inline-flex items-center gap-1', d.phase === 'underway' ? 'border-green/50 text-green' : d.phase === 'anchored' ? 'border-amber/60 text-amber' : 'border-border text-text-secondary')}>
        {d.phase === 'anchored' && <Anchor className="w-3 h-3" />}{d.status_text ?? (d.phase ?? ship?.phase ?? '')}{d.seen_s != null ? ` · ${d.seen_s < 90 ? `${d.seen_s}s` : `${Math.round(d.seen_s / 60)} min`} ago` : ''}</div>
      <div className="grid grid-cols-3 gap-1.5 text-[11px]">
        {[['Reported speed', v(d.speed ?? ship?.speed, ' kn')], ['Course', v(d.course != null ? Math.round(d.course) : null, '°')], ['Heading', v(d.heading, '°')],
          ['Destination', v(d.destination)], ['Crew ETA (UTC, year unspecified)', v(d.eta)], ['Draught', v(d.draught, ' m')],
          ['Length', v(d.length_m, ' m')], ['Beam', v(d.beam_m, ' m')], ['Callsign', v(d.callsign)],
          ['MMSI', String(mmsi)], ['IMO', v(d.imo)], [historical?'Historical cell centre':'Reported position', d.lat != null ? `${d.lat.toFixed(d.satellite?1:3)}, ${d.lon.toFixed(d.satellite?1:3)}` : ship ? `${ship.lat.toFixed(ship.sat?1:3)}, ${ship.lon.toFixed(ship.sat?1:3)}` : '—']].map(([k, x]) => (
          <div key={k}><div className="text-text-tertiary">{k}</div><div className="font-mono text-text-primary truncate" title={String(x)}>{x}</div></div>))}
      </div>
      <div className="border-t border-border-subtle pt-2 space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Voyage declarations & recorded port calls</div>
        <div className="flex items-center gap-2 text-[11px]">
          <div className="flex-1 min-w-0"><div className="text-text-tertiary">From</div>
            <div className="text-text-primary truncate">{voy?.from ? `${voy.from.name} (${voy.from.country})` : lp ? `${lp.port ?? 'Anchorage'}${lp.country ? `, ${lp.country}` : ''}` : '—'}</div>
            {!voy?.from && lp && <div className="text-[10px] text-text-tertiary">last port call, left {String(lp.departed).slice(0, 10)}</div>}</div>
          <span className="text-bloomberg">→</span>
          <div className="flex-1 min-w-0 text-right"><div className="text-text-tertiary">Crew-declared destination</div>
            <div className="text-text-primary truncate" title={voy?.raw}>{voy?.port ? `${voy.port.name} (${voy.port.country})` : d.destination || '—'}</div>
            {d.eta && <div className="text-[10px] text-text-tertiary">ETA {d.eta} UTC</div>}</div>
        </div>
        {voy && !voy.port && d.destination && <div className="text-[10px] text-text-tertiary">Destination as typed by the crew: “{d.destination}” (not a port code)</div>}
      </div>
      <div className="border-t border-border-subtle pt-2 space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Registry & inferred vessel characteristics</div>
        <div className="grid grid-cols-2 gap-1.5 text-[11px]">
          {[['Class', pf.class ? `${pf.class}${pf.size_from === 'tonnage' ? ' (est. from tonnage)' : ''}` : null], ['Vessel-type cargo hypothesis', pf.cargo], ['Estimated load state', pf.laden ? pf.laden : null], ['Reported hazard class', pf.hazard ? pf.hazard.replace('Dangerous goods / pollutant, ', '') : 'Unknown / not supplied'],
            ['Owner', d.owners?.[0]?.name], ['Built', d.built], ['Gross tonnage', d.tonnage_gt ? Math.round(d.tonnage_gt).toLocaleString() : null], ['Flag', d.flag]].map(([k, x]) => (
            <div key={k as string}><div className="text-text-tertiary">{k}</div><div className={cn('text-text-primary truncate', k === 'Estimated load state' && x === 'laden' && 'text-amber')} title={String(x ?? '')}>{x ?? '—'}</div></div>))}
        </div>
        {d.cargo_inference && <div className={cn('px-2 py-1.5 rounded border text-[11px]', d.cargo_inference.confidence === 'likely' ? 'border-bloomberg/50 bg-bloomberg/[0.06] text-text-primary' : 'border-border text-text-secondary')}>
          <span className="text-[10px] uppercase tracking-wide text-text-tertiary mr-1">{d.cargo_inference.confidence === 'likely' ? 'Likely cargo' : 'Possible cargo'}</span>
          {d.cargo_inference.text}<div className="text-[10px] text-text-tertiary">Inferred from the {d.cargo_inference.basis} — manifests aren't public.</div></div>}
        {pf.laden_note && <div className="text-[10px] text-text-tertiary">{pf.laden_note}.</div>}
      </div>
      {hours > 0.2 && <div className="text-[11px] text-text-secondary border-t border-border-subtle pt-2">Connected track intervals {hours.toFixed(1)} h: {Math.round(trackKm).toLocaleString()} km
        {trackKm > 1 ? ` at ${(trackKm / 1.852 / hours).toFixed(1)} kn on average` : ' — stationary'} over connected observations only · {track.breaks} gap/jump breaks. Lines connect sampled fixes; the path between them is unknown.</div>}
      <button onClick={() => onRegistry(d.imo ? String(d.imo) : String(mmsi))} className="w-full py-1.5 border border-border text-[11px] text-text-secondary hover:text-bloomberg hover:border-bloomberg">
        Registry, owners & port calls (Global Fishing Watch)</button>
    </div>
  );
}

function NotablePanel({ data, loading, now, historical, maxAge, follow, onPick }: { data: any; loading: boolean; now:number; historical:boolean; maxAge:number; follow: ReturnType<typeof useFollow>; onPick: (x: any) => void }) {
  const [only, setOnly] = useState<string>('');
  if (loading && !data) return <Loading label="Checking ships against the sanctions list…" />;
  if (!data) return null;
  const eligible = (Array.isArray(data.ships)?data.ships:[]).filter((x:any)=>!!x.satellite===historical&&recentFix(x.position_time,now,historical?7*86400:maxAge));
  const list = eligible.filter((x:any) => !only || x.tags?.includes(only));
  return (
    <div className="border border-border bg-surface-1">
      <div className="mkt-controls flex flex-wrap gap-1 p-2 text-[10px]">
        <button onClick={() => setOnly('')} className={cn('px-1.5 border', !only ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>In this layer {eligible.length}</button>
        {TAGS.map(([k, l, col]) => (
          <button key={k} onClick={() => setOnly(k)} className={cn('px-1.5 border inline-flex items-center gap-1', only === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>
            <span className="w-2 h-2 rounded-full border-2" style={{ borderColor: col }} />{l} {eligible.filter((x:any)=>x.tags?.includes(k)).length}</button>))}
      </div>
      <ul className="max-h-[440px] overflow-y-auto divide-y divide-border-subtle">{list.slice(0, 300).map((x:any) => (
        <li key={x.mmsi}><button onClick={() => onPick(x)} className="w-full text-left px-2 py-1.5 hover:bg-surface-3 flex gap-2 items-start">
          <span className="mt-1 w-2 h-2 rounded-full border-2 shrink-0" style={{ borderColor: tagColor(x.tags) }} />
          <span className="min-w-0 flex-1"><span className="text-[11px] text-text-primary">{x.name}</span>
            <span className="text-[10px] text-text-tertiary"> · {x.type}{x.satellite ? ' · historical cell' : x.speed != null ? ` · ${x.speed} kn` : ''}{x.destination ? ` · → ${x.destination}` : ''}</span>
            <span className="block text-[10px] text-text-secondary truncate" title={x.reasons.join('; ')}>{x.reasons.join(' · ')}</span></span>
          {follow.isFollowed(String(x.mmsi)) && <Star className="w-3 h-3 text-[rgb(202_138_4)] fill-current shrink-0" />}
        </button></li>))}</ul>
      <p className="p-2 text-[10px] text-text-tertiary">{data.note} Counts above apply to the selected observation layer and age window; results are limited by the provider response.</p>
    </div>
  );
}

function FollowPanel({ follow, byId, onPick }: { follow: ReturnType<typeof useFollow>; byId: Map<string, Sh>; onPick: (mmsi: string) => void }) {
  if (!follow.list.length) return <p className="border border-border bg-surface-1 p-3 text-[11px] text-text-tertiary">Nothing followed yet — open a ship and press <b>Follow</b>. Followed ships get a gold ring and a label on the map, and your notes are kept here.</p>;
  return (
    <ul className="border border-border bg-surface-1 divide-y divide-border-subtle max-h-[520px] overflow-y-auto">{follow.list.map((f) => {
      const s = byId.get(f.id);
      return (
        <li key={f.id} className="px-2 py-1.5">
          <div className="flex items-center gap-2">
            <Star className="w-3 h-3 text-[rgb(202_138_4)] fill-current shrink-0" />
            <button onClick={() => onPick(f.id)} className="text-[11px] text-text-primary hover:text-bloomberg truncate">{f.label}</button>
            <span className="text-[10px] text-text-tertiary">{s ? (s.sat ? 'historical AIS cell' : s.phase === 'underway' ? `${s.speed ?? '?'} kn` : s.phase) : 'not heard now'}</span>
            <button onClick={() => follow.remove(f.id)} className="ml-auto text-text-tertiary hover:text-red" aria-label="Stop following"><X className="w-3 h-3" /></button>
          </div>
          {f.reason && <div className="text-[10px] text-amber">{f.reason}</div>}
          <textarea value={f.note} onChange={(e) => follow.setNote(f.id, e.target.value)} rows={1} placeholder="Notes…" aria-label={`Notes on ${f.label}`}
            className="mt-1 w-full bg-surface-2 border border-border-subtle px-1.5 py-0.5 text-[11px] text-text-primary" />
          <div className="text-[10px] text-text-tertiary">following since {f.added.replace('T', ' ')}</div>
        </li>);
    })}</ul>
  );
}

function PortCongestion({ data, loading, error, now, onPick }: { data: any; loading: boolean; error: string | null; now:number; onPick: (p: any) => void }) {
  const [sort, setSort] = useState<'anchored' | 'moored' | 'total' | 'cargo_waiting' | 'tankers_waiting'>('anchored');
  const fresh=recentFix(data?.as_of,now,300);
  const rows = [...(fresh?data?.ports??[]:[])].sort((a, b) => b[sort] - a[sort]);
  const max = Math.max(1, ...rows.map((r) => r.anchored));
  const th = (k: typeof sort, l: string) => <th onClick={() => setSort(k)} tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSort(k);}}} aria-sort={sort===k?'descending':'none'} className={cn('text-right font-normal px-1.5 cursor-pointer', sort === k ? 'text-bloomberg' : '')}>{l}</th>;
  return (
    <Panel title="Port presence — reported AIS near major ports">
      {loading && !data && <Loading />}
      {error && !data && <ErrorBox msg={error} />}
      {data && !fresh&&<p className="text-xs text-amber">Port snapshot is stale or undated. Counts are withheld until fresh observations arrive.</p>}
      {data && fresh&&<>
        <p className="maritime-evidence-note">15-minute receiver sample · one nearest port per vessel · zero means no observations, not zero activity. Port circles are geographic catchments, not terminal boundaries.</p>
        <div className="overflow-x-auto max-h-80 overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Port</th>
              {th('anchored', 'At anchor')}<th className="font-normal w-32" />{th('cargo_waiting', 'Cargo at anchor')}{th('tankers_waiting', 'Tankers at anchor')}{th('moored', 'Moored')}{th('total', 'All')}</tr></thead>
            <tbody>{rows.map((p) => (
              <tr key={p.port} onClick={() => onPick(p)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}>
                <td className="py-0.5 text-text-primary">{p.port}</td><td className="text-right font-mono px-1.5">{p.total?p.anchored:'—'}</td>
                <td><div className="h-1.5 bg-surface-3"><div className="h-full bg-amber" style={{ width: `${(p.anchored / max) * 100}%` }} /></div></td>
                <td className="text-right font-mono px-1.5 text-text-secondary">{p.total?p.cargo_waiting:'—'}</td><td className="text-right font-mono px-1.5 text-text-secondary">{p.total?p.tankers_waiting:'—'}</td>
                <td className="text-right font-mono px-1.5 text-text-secondary">{p.total?p.moored:'—'}</td><td className="text-right font-mono px-1.5 text-text-tertiary">{p.total||'No observations'}</td></tr>))}</tbody>
          </table>
        </div>
        <div className="text-[10px] text-text-tertiary mt-1">{data.note}{data.listening_s < 900 ? ' The collector started recently — counts are still filling in.' : ''} Click a port to zoom to it.</div>
      </>}
    </Panel>
  );
}

/** Registry identity, owners and port calls for a vessel (Global Fishing Watch). */
export function VesselCard({ query, live, onClose }: { query: string; live?: any; onClose: () => void }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/ship/vessel/${encodeURIComponent(query)}`);
  return (
    <div className="border border-border bg-surface-1 p-2.5 text-xs space-y-2 max-h-[372px] overflow-y-auto">
      <div className="flex items-start justify-between gap-2">
        <div><div className="text-sm font-semibold text-text-primary">{data?.name ?? live?.name ?? query}</div>
          <div className="text-[11px] text-text-tertiary">{[data?.flag && `Flag: ${data.flag}`, data?.imo && `IMO ${data.imo}`, (data?.mmsi ?? live?.mmsi) && `MMSI ${data?.mmsi ?? live?.mmsi}`, data?.callsign].filter(Boolean).join(' · ')}</div></div>
        <button onClick={onClose} className="text-text-tertiary hover:text-text-primary" aria-label="Close">×</button>
      </div>
      {live && <div className="grid grid-cols-3 gap-1.5 text-[11px]">
        <div><div className="text-text-tertiary">Speed</div><div className="font-mono">{live.speed ?? '—'} kn</div></div>
        <div><div className="text-text-tertiary">Course</div><div className="font-mono">{live.course != null ? Math.round(live.course) + '°' : '—'}</div></div>
        <div><div className="text-text-tertiary">Destination</div><div className="truncate">{live.destination || '—'}</div></div></div>}
      {loading && !data && <Loading label="Looking up identity and port calls…" />}
      {error && !data && <p className="text-[11px] text-text-tertiary">{error}</p>}
      {data && <>
        <div className="text-[11px] text-text-secondary">{[data.types?.join(', '), data.length_m && `${data.length_m} m`, data.tonnage_gt && `${Math.round(data.tonnage_gt).toLocaleString()} GT`, data.built && `built ${data.built}`].filter(Boolean).join(' · ')}</div>
        {data.owners?.length > 0 && <div><div className="text-[10px] uppercase tracking-wide text-text-tertiary">Owner</div>{data.owners.slice(0, 2).map((o: any, i: number) => <div key={i}>{o.name} <span className="text-text-tertiary">({o.flag})</span></div>)}</div>}
        {data.history?.length > 1 && <div><div className="text-[10px] uppercase tracking-wide text-text-tertiary">Identity history</div>
          {data.history.map((h: any, i: number) => <div key={i} className="font-mono text-[11px]">{h.from} → {h.to} · {h.name} · {h.flag_name}</div>)}</div>}
        <div><div className="text-[10px] uppercase tracking-wide text-text-tertiary">Port calls, last 6 months</div>
          {data.port_calls?.length ? <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-[11px]"><tbody>{data.port_calls.map((c: any, i: number) => (
            <tr key={i} className="border-t border-border-subtle"><td className="py-0.5 text-text-primary">{c.port ?? 'Anchorage'}</td><td className="text-text-secondary">{c.country}</td>
              <td className="font-mono text-text-tertiary">{c.arrived?.slice(0, 10)}</td><td className="text-right font-mono">{c.hours}h</td></tr>))}</tbody></table></div>
            : <p className="text-[11px] text-text-tertiary">None recorded.</p>}</div>
        <div className="text-[10px] text-text-tertiary">{data.source}</div>
      </>}
    </div>
  );
}

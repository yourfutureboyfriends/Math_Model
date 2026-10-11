// SHIP — every vessel the live AIS network hears, worldwide, on one map: colour by kind, filter
// by kind and by underway / at anchor / moored, click for identity, dimensions, destination, ETA,
// flag and the last 8 hours of track; registry owners and port calls from Global Fishing Watch.
// Below it: port congestion (ships waiting at anchor near 55 major ports).
import { useMemo, useRef, useState } from 'react';
import { Anchor, Search, Ship, Star, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ErrorBox, Loading, Panel, useJSON } from './shared';
import { Photos } from './Photos';
import { greatCircle, LiveMap, type LiveMapHandle, type MapBounds, type MapLine, type MapMarker, type MapPoint } from './LiveMap';
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
const PHASES = [['all', 'All'], ['underway', 'Under way'], ['anchored', 'At anchor'], ['moored', 'Moored']] as const;
type Phase = typeof PHASES[number][0];
type ShipPhase = Exclude<Phase, 'all'> | 'unknown';
const phaseOf = (status: number | null, speed: number | null, sat: boolean): ShipPhase =>
  sat ? 'unknown' : status === 5 ? 'moored' : status === 1 || ((status == null || status === 15) && speed != null && speed < 0.5) ? 'anchored' : 'underway';
const faded = (c: string) => c.replace(/\)$/, ' / 0.45)');          // satellite positions: days old, drawn fainter

type Sh = { mmsi: number; lat: number; lon: number; speed: number | null; heading: number | null; type: string; status: number | null; name: string; phase: ShipPhase; sat: boolean; tag: string };
// notable reasons (backend tag letters), most important first, and their ring colours
const TAGS: [string, string, string][] = [['s', 'Sanctioned', 'rgb(239 68 68)'], ['m', 'Military', 'rgb(236 72 153)'], ['l', 'Gas carrier', 'rgb(6 182 212)'],
  ['g', 'Giant', 'rgb(245 158 11)'], ['h', 'Dangerous goods', 'rgb(249 115 22)'], ['z', 'Tanker in a hot zone', 'rgb(234 179 8)']];
const tagColor = (tag: string) => TAGS.find(([k]) => tag.includes(k))?.[2];

export function ShipTracker() {
  const world = useJSON<any>('/api/v1/mkt/ship/world', 30_000);
  const ports = useJSON<any>('/api/v1/mkt/ship/ports', 120_000);
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [phase, setPhase] = useState<Phase>('all');
  const [showPorts, setShowPorts] = useState(true);
  const [showSat, setShowSat] = useState(true);
  const [find, setFind] = useState('');
  const [registry, setRegistry] = useState<string | null>(null);
  const [notableOnly, setNotableOnly] = useState(false);
  const [tab, setTab] = useState<'view' | 'notable' | 'follow'>('view');
  const follow = useFollow('ship');
  const notable = useJSON<any>('/api/v1/mkt/ship/notable', 120_000);
  const map = useRef<LiveMapHandle>(null);

  const ships: Sh[] = useMemo(() => {
    const d = world.data;
    if (!d) return [];
    const ix = Object.fromEntries((d.cols as string[]).map((c, i) => [c, i]));
    return (d.rows as any[]).map((r) => ({ mmsi: r[ix.mmsi], lat: r[ix.lat], lon: r[ix.lon], speed: r[ix.speed], heading: r[ix.heading],
      type: d.types[r[ix.type]] ?? 'Unknown', status: r[ix.status], name: r[ix.name], sat: !!r[ix.sat], phase: phaseOf(r[ix.status], r[ix.speed], !!r[ix.sat]),
      tag: r[ix.tag] ?? '' }));
  }, [world.data]);
  const byId = useMemo(() => new Map(ships.map((s) => [String(s.mmsi), s])), [ships]);
  const shown = useMemo(() => ships.filter((s) => (!hidden.has(s.type) && (phase === 'all' || s.phase === phase) && (showSat || !s.sat) && (!notableOnly || s.tag))
    || s.mmsi === sel || follow.ids.has(String(s.mmsi))), [ships, hidden, phase, sel, showSat, notableOnly, follow.ids]);
  const points: MapPoint[] = useMemo(() => shown.map((s) => ({
    id: String(s.mmsi), lon: s.lon, lat: s.lat, color: s.sat ? faded(TYPE_COL[s.type] ?? TYPE_COL.Other) : TYPE_COL[s.type] ?? TYPE_COL.Other, heading: s.heading, moving: (s.speed ?? 0) > 0.5,
    label: s.name || undefined, approx: s.sat, ring: s.tag ? tagColor(s.tag) : undefined, pin: follow.ids.has(String(s.mmsi)),
  })), [shown, follow.ids]);

  const live = useJSON<any>(sel ? `/api/v1/mkt/ship/live/${sel}` : null, 30_000);
  const det = live.current ? live.data : null;
  const lines: MapLine[] = useMemo(() => {
    const out: MapLine[] = [];
    if (det?.track?.length > 1) out.push({ coords: det.track.map((p: any) => [p[2], p[1]] as [number, number]), color: 'rgb(var(--c-bloomberg))', width: 2 });
    const to = det?.voyage?.port, from = det?.voyage?.from;
    if (det?.lat != null && to?.lat != null) out.push({ coords: greatCircle([det.lon, det.lat], [to.lon, to.lat]), color: 'rgb(var(--c-text-secondary))', width: 1.3, dash: [6, 4] });
    if (det?.lat != null && from?.lat != null) out.push({ coords: greatCircle([from.lon, from.lat], [det.lon, det.lat]), color: 'rgb(var(--c-text-tertiary))', width: 1, dash: [2, 4] });
    return out;
  }, [det]);
  const markers: MapMarker[] = useMemo(() => {
    const out: MapMarker[] = showPorts ? (ports.data?.ports ?? []).map((p: any) => ({
      lon: p.lon, lat: p.lat, id: p.port, color: p.anchored >= 20 ? 'rgb(var(--c-red))' : p.anchored >= 8 ? 'rgb(var(--c-amber))' : 'rgb(var(--c-text-tertiary))',
      r: 4 + Math.min(14, Math.sqrt(p.anchored) * 1.6), fill: true, label: `${p.port}${p.anchored ? ` · ${p.anchored} waiting` : ''}`,
    })) : [];
    const to = det?.voyage?.port;
    if (to?.lat != null) out.push({ lon: to.lon, lat: to.lat, color: 'rgb(var(--c-bloomberg))', r: 6, fill: true, label: `→ ${to.name}` });
    return out;
  }, [ports.data, showPorts, det]);

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
    return `${s.name || `MMSI ${s.mmsi}`} · ${s.type}\n${s.sat ? `satellite position, ${world.data?.satellite?.day ?? 'days old'}` : s.phase === 'underway' ? `${s.speed ?? '?'} kn · ${s.heading ?? '?'}°` : s.phase === 'anchored' ? 'at anchor' : 'moored'}`;
  };
  const toggleType = (t: string) => setHidden((h) => { const n = new Set(h); if (n.has(t)) n.delete(t); else n.add(t); return n; });

  if (world.loading && !world.data) return <Loading label="Loading every ship the AIS network can hear…" />;
  if (world.error && !world.data) return <ErrorBox msg={world.error} />;
  const w = world.data;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <span className="text-text-primary"><Ship className="inline w-3.5 h-3.5 mr-1 text-bloomberg" /><b className="font-mono">{w?.rows?.length?.toLocaleString()}</b> vessels worldwide</span>
        <span className="text-text-secondary"><b className="font-mono text-green">{w?.live_count?.toLocaleString()}</b> live ({w?.phase?.underway?.toLocaleString()} under way · {w?.phase?.anchored?.toLocaleString()} at anchor · {w?.phase?.moored?.toLocaleString()} moored)</span>
        <span className="text-text-secondary" title={w?.satellite?.source}><b className="font-mono">{w?.satellite_count?.toLocaleString()}</b> by satellite{w?.satellite?.day ? ` (as of ${w.satellite.day})` : ''}
          {w?.satellite?.status === 'building' ? ` — loading ${w.satellite.boxes_done}/${w.satellite.boxes} areas` : ''}</span>
        <span className="text-text-tertiary">in view <b className="font-mono text-text-secondary">{inView.length.toLocaleString()}</b></span>
        <span className={cn('ml-auto', w?.status === 'live' ? 'text-green' : 'text-amber')}>● {w?.status === 'live' ? 'live AIS stream' : w?.status}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
        <form onSubmit={doFind} className="flex">
          <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Ship name, MMSI or IMO" aria-label="Find a vessel"
            className="w-48 bg-surface-1 border border-border px-2 py-0.5 text-text-primary placeholder:text-text-tertiary" />
          <button className="px-1.5 border border-l-0 border-border text-text-secondary" aria-label="Find"><Search className="w-3 h-3" /></button>
        </form>
        {SEAS.map(([n, b]) => (
          <button key={n} onClick={() => map.current?.fitBounds(b)} className="px-1.5 py-0.5 border border-border text-text-secondary hover:text-bloomberg hover:border-bloomberg">{n}</button>))}
      </div>
      <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_360px] gap-2">
        <LiveMap ref={map} glyph="ship" points={points} lines={lines} markers={markers} selected={sel != null ? String(sel) : null}
          onSelect={(id) => { setSel(id ? Number(id) : null); setRegistry(null); }} onMarker={(port) => { const p = ports.data?.ports.find((x: any) => x.port === port); if (p) map.current?.flyTo({ lon: p.lon, lat: p.lat, zoom: 10 }); }}
          onView={setBounds} hoverText={hoverText} height={600} initial={{ lon: 60, lat: 25, zoom: 2.2 }} density={DENSITY_ZOOM} occludeLand>
          {(bounds?.zoom ?? 0) < DENSITY_ZOOM && <div className="absolute top-2 left-2 text-[10px] bg-surface-1/85 border border-border px-2 py-1 flex items-center gap-2">
            <span>Traffic density</span><span className="w-20 h-2" style={{ background: 'linear-gradient(90deg, rgb(24 70 140), rgb(0 150 200), rgb(60 210 190), rgb(250 210 90), rgb(255 250 235))' }} />
            <span className="text-text-tertiary">zoom in for individual ships</span></div>}
          <div className="absolute bottom-2 left-2 right-12 flex flex-wrap gap-1 text-[10px]">
            <div className="flex flex-wrap gap-1 bg-surface-1/85 border border-border px-1.5 py-1">
              {Object.keys(TYPE_COL).filter((t) => t !== 'Towing').map((t) => (
                <button key={t} onClick={() => toggleType(t)} title={hidden.has(t) ? `Show ${t}` : `Hide ${t}`}
                  className={cn('inline-flex items-center gap-1 px-1', hidden.has(t) && 'opacity-35 line-through')}>
                  <span className="w-2 h-2 rounded-full" style={{ background: TYPE_COL[t] }} />{t} <span className="font-mono text-text-tertiary">{((w?.by_type?.[t] ?? 0) + (w?.satellite_by_type?.[t] ?? 0)).toLocaleString()}</span></button>))}
            </div>
            <div className="flex gap-1 bg-surface-1/85 border border-border px-1.5 py-1">
              {PHASES.map(([k, l]) => <button key={k} onClick={() => setPhase(k)} className={cn('px-1', phase === k ? 'text-bloomberg' : 'text-text-secondary')}>{l}</button>)}
              <label className="inline-flex items-center gap-1 ml-1 cursor-pointer"><input type="checkbox" checked={showPorts} onChange={(e) => setShowPorts(e.target.checked)} />ports</label>
              <label className="inline-flex items-center gap-1 ml-1 cursor-pointer" title="Only sanctioned, military, gas carriers, giants, dangerous cargo and tankers in hot zones">
                <input type="checkbox" checked={notableOnly} onChange={(e) => setNotableOnly(e.target.checked)} />notable only</label>
              <label className="inline-flex items-center gap-1 ml-1 cursor-pointer" title="Vessels outside live receiver range, at their last satellite position (a few days old)">
                <input type="checkbox" checked={showSat} onChange={(e) => setShowSat(e.target.checked)} />satellite (faint)</label>
            </div>
          </div>
        </LiveMap>
        <div className="space-y-2 min-w-0">
          {sel != null ? <ShipCard mmsi={sel} ship={byId.get(String(sel))} det={det} loading={live.loading && !det} error={live.error}
              onClose={() => setSel(null)} onRegistry={(q) => setRegistry(q)} follow={follow} />
            : registry ? null : <>
              <div className="flex gap-1 text-[11px]">{([['view', 'In view'], ['notable', `Notable ${notable.data?.total ?? ''}`], ['follow', `Following ${follow.list.length}`]] as const).map(([k, l]) => (
                <button key={k} onClick={() => setTab(k)} className={cn('flex-1 px-2 py-1 border', tab === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>))}</div>
              {tab === 'view' && <ViewPanel stats={viewStats} inView={inView} onPick={(s) => setSel(s.mmsi)} />}
              {tab === 'notable' && <NotablePanel data={notable.data} loading={notable.loading} follow={follow}
                onPick={(x) => { setSel(x.mmsi); map.current?.flyTo({ lon: x.lon, lat: x.lat, zoom: Math.max(bounds?.zoom ?? 0, 7) }); }} />}
              {tab === 'follow' && <FollowPanel follow={follow} byId={byId}
                onPick={(m) => { const s2 = byId.get(m); setSel(Number(m)); if (s2) map.current?.flyTo({ lon: s2.lon, lat: s2.lat, zoom: Math.max(bounds?.zoom ?? 0, 7) }); }} />}
            </>}
          {registry && <VesselCard query={registry} live={undefined} onClose={() => setRegistry(null)} />}
        </div>
      </div>
      <div className="text-[10px] text-text-tertiary">{w?.source}. {w?.coverage}</div>
      <PortCongestion data={ports.data} loading={ports.loading} error={ports.error} onPick={(p) => map.current?.flyTo({ lon: p.lon, lat: p.lat, zoom: 10 })} />
    </div>
  );
}

function ViewPanel({ stats, inView, onPick }: { stats: { t: Record<string, number>; ph: Record<string, number> }; inView: Sh[]; onPick: (s: Sh) => void }) {
  const total = Math.max(1, inView.length);
  const list = [...inView].filter((s) => s.name).sort((a, b) => (b.speed ?? -1) - (a.speed ?? -1)).slice(0, 150);
  return (
    <>
      <div className="border border-border bg-surface-1 p-2 text-[11px] space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary">In view</div>
        <div className="flex h-2 overflow-hidden">{Object.entries(stats.t).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
          <div key={t} title={`${t}: ${n}`} style={{ width: `${(n / total) * 100}%`, background: TYPE_COL[t] ?? TYPE_COL.Other }} />))}</div>
        <div className="grid grid-cols-2 gap-x-3">{Object.entries(stats.t).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
          <div key={t} className="flex justify-between"><span className="inline-flex items-center gap-1 text-text-secondary"><span className="w-2 h-2 rounded-full" style={{ background: TYPE_COL[t] }} />{t}</span><span className="font-mono">{n.toLocaleString()}</span></div>))}</div>
        <div className="flex justify-between border-t border-border-subtle pt-1 text-text-secondary">
          <span>Under way <b className="font-mono text-text-primary">{stats.ph.underway}</b></span><span>At anchor <b className="font-mono text-text-primary">{stats.ph.anchored}</b></span>
          <span>Moored <b className="font-mono text-text-primary">{stats.ph.moored}</b></span></div>
      </div>
      <div className="border border-border max-h-[420px] overflow-y-auto">
        <table className="w-full text-[11px]">
          <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left px-1.5 font-normal">Vessel</th><th className="text-left font-normal">Type</th>
            <th className="text-right font-normal px-1.5">Knots</th></tr></thead>
          <tbody>{list.map((s) => (
            <tr key={s.mmsi} onClick={() => onPick(s)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3">
              <td className="px-1.5 py-0.5 text-text-primary truncate max-w-[11rem]">{s.name}</td>
              <td style={{ color: TYPE_COL[s.type] }}>{s.type}</td><td className="text-right px-1.5 font-mono">{s.phase === 'underway' ? s.speed?.toFixed(1) ?? '' : s.phase === 'anchored' ? '⚓' : '·'}</td></tr>))}</tbody>
        </table>
        {list.length === 0 && <p className="p-2 text-[11px] text-text-tertiary">No named vessels in this view.</p>}
      </div>
    </>
  );
}

function ShipCard({ mmsi, ship, det, loading, error, onClose, onRegistry, follow }: { mmsi: number; ship?: Sh; det: any; loading: boolean; error: string | null;
  onClose: () => void; onRegistry: (q: string) => void; follow: ReturnType<typeof useFollow> }) {
  const d = det ?? {};
  const name = d.name || ship?.name || `MMSI ${mmsi}`;
  // distance and average speed over the stored track
  const trackKm = (det?.track ?? []).reduce((acc: number, p: any, i: number, a: any[]) => {
    if (!i) return 0;
    const [, la1, lo1] = a[i - 1], [, la2, lo2] = p;
    const r = Math.PI / 180, h = Math.sin(((la2 - la1) * r) / 2) ** 2 + Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin(((lo2 - lo1) * r) / 2) ** 2;
    return acc + 12742 * Math.asin(Math.sqrt(h));
  }, 0);
  const hours = det?.track?.length > 1 ? (det.track[det.track.length - 1][0] - det.track[0][0]) / 3600 : 0;
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
      {d.note && <p className="text-[11px] text-amber">{d.note}</p>}
      {loading && <Loading label="Reading the live picture…" />}
      {error && !det && <p className="text-[11px] text-text-tertiary">{error}</p>}
      <div className={cn('px-2 py-1 border text-[11px] inline-flex items-center gap-1', d.phase === 'underway' ? 'border-green/50 text-green' : d.phase === 'anchored' ? 'border-amber/60 text-amber' : 'border-border text-text-secondary')}>
        {d.phase === 'anchored' && <Anchor className="w-3 h-3" />}{d.status_text ?? (d.phase ?? ship?.phase ?? '')}{d.seen_s != null ? ` · ${d.seen_s < 90 ? `${d.seen_s}s` : `${Math.round(d.seen_s / 60)} min`} ago` : ''}</div>
      <div className="grid grid-cols-3 gap-1.5 text-[11px]">
        {[['Speed', v(d.speed ?? ship?.speed, ' kn')], ['Course', v(d.course != null ? Math.round(d.course) : null, '°')], ['Heading', v(d.heading, '°')],
          ['Destination', v(d.destination)], ['ETA (UTC)', v(d.eta)], ['Draught', v(d.draught, ' m')],
          ['Length', v(d.length_m, ' m')], ['Beam', v(d.beam_m, ' m')], ['Callsign', v(d.callsign)],
          ['MMSI', String(mmsi)], ['IMO', v(d.imo)], ['Position', d.lat != null ? `${d.lat.toFixed(3)}, ${d.lon.toFixed(3)}` : '—']].map(([k, x]) => (
          <div key={k}><div className="text-text-tertiary">{k}</div><div className="font-mono text-text-primary truncate" title={String(x)}>{x}</div></div>))}
      </div>
      <div className="border-t border-border-subtle pt-2 space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Voyage</div>
        <div className="flex items-center gap-2 text-[11px]">
          <div className="flex-1 min-w-0"><div className="text-text-tertiary">From</div>
            <div className="text-text-primary truncate">{voy?.from ? `${voy.from.name} (${voy.from.country})` : lp ? `${lp.port ?? 'Anchorage'}${lp.country ? `, ${lp.country}` : ''}` : '—'}</div>
            {!voy?.from && lp && <div className="text-[10px] text-text-tertiary">last port call, left {String(lp.departed).slice(0, 10)}</div>}</div>
          <span className="text-bloomberg">→</span>
          <div className="flex-1 min-w-0 text-right"><div className="text-text-tertiary">To</div>
            <div className="text-text-primary truncate" title={voy?.raw}>{voy?.port ? `${voy.port.name} (${voy.port.country})` : d.destination || '—'}</div>
            {d.eta && <div className="text-[10px] text-text-tertiary">ETA {d.eta} UTC</div>}</div>
        </div>
        {voy && !voy.port && d.destination && <div className="text-[10px] text-text-tertiary">Destination as typed by the crew: “{d.destination}” (not a port code)</div>}
      </div>
      <div className="border-t border-border-subtle pt-2 space-y-1">
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Cargo & vessel</div>
        <div className="grid grid-cols-2 gap-1.5 text-[11px]">
          {[['Class', pf.class ? `${pf.class}${pf.size_from === 'tonnage' ? ' (est. from tonnage)' : ''}` : null], ['Likely cargo', pf.cargo], ['Load', pf.laden ? pf.laden : null], ['Dangerous goods', pf.hazard ? pf.hazard.replace('Dangerous goods / pollutant, ', '') : 'none declared'],
            ['Owner', d.owners?.[0]?.name], ['Built', d.built], ['Gross tonnage', d.tonnage_gt ? Math.round(d.tonnage_gt).toLocaleString() : null], ['Flag', d.flag]].map(([k, x]) => (
            <div key={k as string}><div className="text-text-tertiary">{k}</div><div className={cn('text-text-primary truncate', k === 'Load' && x === 'laden' && 'text-amber')} title={String(x ?? '')}>{x ?? '—'}</div></div>))}
        </div>
        {d.cargo_inference && <div className={cn('px-2 py-1.5 rounded border text-[11px]', d.cargo_inference.confidence === 'likely' ? 'border-bloomberg/50 bg-bloomberg/[0.06] text-text-primary' : 'border-border text-text-secondary')}>
          <span className="text-[10px] uppercase tracking-wide text-text-tertiary mr-1">{d.cargo_inference.confidence === 'likely' ? 'Likely cargo' : 'Possible cargo'}</span>
          {d.cargo_inference.text}<div className="text-[10px] text-text-tertiary">Inferred from the {d.cargo_inference.basis} — manifests aren't public.</div></div>}
        {pf.laden_note && <div className="text-[10px] text-text-tertiary">{pf.laden_note}.</div>}
      </div>
      {hours > 0.2 && <div className="text-[11px] text-text-secondary border-t border-border-subtle pt-2">Last {hours.toFixed(1)} h: {Math.round(trackKm).toLocaleString()} km
        {trackKm > 1 ? ` at ${(trackKm / 1.852 / hours).toFixed(1)} kn on average` : ' — stationary'} (orange track on the map).</div>}
      <button onClick={() => onRegistry(d.imo ? String(d.imo) : String(mmsi))} className="w-full py-1.5 border border-border text-[11px] text-text-secondary hover:text-bloomberg hover:border-bloomberg">
        Registry, owners & port calls (Global Fishing Watch)</button>
    </div>
  );
}

function NotablePanel({ data, loading, follow, onPick }: { data: any; loading: boolean; follow: ReturnType<typeof useFollow>; onPick: (x: any) => void }) {
  const [only, setOnly] = useState<string>('');
  if (loading && !data) return <Loading label="Checking ships against the sanctions list…" />;
  if (!data) return null;
  const list = (data.ships as any[]).filter((x) => !only || x.tags.includes(only));
  return (
    <div className="border border-border bg-surface-1">
      <div className="flex flex-wrap gap-1 p-2 text-[10px]">
        <button onClick={() => setOnly('')} className={cn('px-1.5 border', !only ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>All {data.total}</button>
        {TAGS.map(([k, l, col]) => (
          <button key={k} onClick={() => setOnly(k)} className={cn('px-1.5 border inline-flex items-center gap-1', only === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>
            <span className="w-2 h-2 rounded-full border-2" style={{ borderColor: col }} />{l} {data.counts?.[k] ?? 0}</button>))}
      </div>
      <ul className="max-h-[440px] overflow-y-auto divide-y divide-border-subtle">{list.slice(0, 300).map((x) => (
        <li key={x.mmsi}><button onClick={() => onPick(x)} className="w-full text-left px-2 py-1.5 hover:bg-surface-3 flex gap-2 items-start">
          <span className="mt-1 w-2 h-2 rounded-full border-2 shrink-0" style={{ borderColor: tagColor(x.tags) }} />
          <span className="min-w-0 flex-1"><span className="text-[11px] text-text-primary">{x.name}</span>
            <span className="text-[10px] text-text-tertiary"> · {x.type}{x.satellite ? ' · satellite' : x.speed != null ? ` · ${x.speed} kn` : ''}{x.destination ? ` · → ${x.destination}` : ''}</span>
            <span className="block text-[10px] text-text-secondary truncate" title={x.reasons.join('; ')}>{x.reasons.join(' · ')}</span></span>
          {follow.isFollowed(String(x.mmsi)) && <Star className="w-3 h-3 text-[rgb(202_138_4)] fill-current shrink-0" />}
        </button></li>))}</ul>
      <p className="p-2 text-[10px] text-text-tertiary">{data.note}</p>
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
            <span className="text-[10px] text-text-tertiary">{s ? (s.sat ? 'satellite position' : s.phase === 'underway' ? `${s.speed ?? '?'} kn` : s.phase) : 'not heard now'}</span>
            <button onClick={() => follow.remove(f.id)} className="ml-auto text-text-tertiary hover:text-red" aria-label="Stop following"><X className="w-3 h-3" /></button>
          </div>
          {f.reason && <div className="text-[10px] text-amber">{f.reason}</div>}
          <textarea value={f.note} onChange={(e) => follow.setNote(f.id, e.target.value)} rows={1} placeholder="Notes…" aria-label={`Notes on ${f.label}`}
            className="mt-1 w-full bg-surface-2 border border-border-subtle px-1.5 py-0.5 text-[11px] text-text-primary" />
          <div className="text-[9px] text-text-tertiary">following since {f.added.replace('T', ' ')}</div>
        </li>);
    })}</ul>
  );
}

function PortCongestion({ data, loading, error, onPick }: { data: any; loading: boolean; error: string | null; onPick: (p: any) => void }) {
  const [sort, setSort] = useState<'anchored' | 'moored' | 'total' | 'cargo_waiting' | 'tankers_waiting'>('anchored');
  const rows = [...(data?.ports ?? [])].sort((a, b) => b[sort] - a[sort]);
  const max = Math.max(1, ...rows.map((r) => r.anchored));
  const th = (k: typeof sort, l: string) => <th onClick={() => setSort(k)} className={cn('text-right font-normal px-1.5 cursor-pointer', sort === k ? 'text-bloomberg' : '')}>{l}</th>;
  return (
    <Panel title="Port congestion — ships near 55 major ports, live">
      {loading && !data && <Loading />}
      {error && !data && <ErrorBox msg={error} />}
      {data && <>
        <div className="overflow-x-auto max-h-80 overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Port</th>
              {th('anchored', 'At anchor')}<th className="font-normal w-32" />{th('cargo_waiting', 'Cargo waiting')}{th('tankers_waiting', 'Tankers waiting')}{th('moored', 'Moored')}{th('total', 'All')}</tr></thead>
            <tbody>{rows.map((p) => (
              <tr key={p.port} onClick={() => onPick(p)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3">
                <td className="py-0.5 text-text-primary">{p.port}</td><td className="text-right font-mono px-1.5">{p.anchored}</td>
                <td><div className="h-1.5 bg-surface-3"><div className="h-full bg-amber" style={{ width: `${(p.anchored / max) * 100}%` }} /></div></td>
                <td className="text-right font-mono px-1.5 text-text-secondary">{p.cargo_waiting}</td><td className="text-right font-mono px-1.5 text-text-secondary">{p.tankers_waiting}</td>
                <td className="text-right font-mono px-1.5 text-text-secondary">{p.moored}</td><td className="text-right font-mono px-1.5 text-text-tertiary">{p.total}</td></tr>))}</tbody>
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
          {data.port_calls?.length ? <table className="w-full text-[11px]"><tbody>{data.port_calls.map((c: any, i: number) => (
            <tr key={i} className="border-t border-border-subtle"><td className="py-0.5 text-text-primary">{c.port ?? 'Anchorage'}</td><td className="text-text-secondary">{c.country}</td>
              <td className="font-mono text-text-tertiary">{c.arrived?.slice(0, 10)}</td><td className="text-right font-mono">{c.hours}h</td></tr>))}</tbody></table>
            : <p className="text-[11px] text-text-tertiary">None recorded.</p>}</div>
        <div className="text-[10px] text-text-tertiary">{data.source}</div>
      </>}
    </div>
  );
}

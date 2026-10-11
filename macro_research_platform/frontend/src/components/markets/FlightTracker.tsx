// FLY — every aircraft in the world on one map. The world layer is OpenSky's snapshot (projected
// forward along each aircraft's track to now); zoomed in, the visible area switches to live,
// seconds-old adsb.fi data with model, operator, Mach, wind and temperature. Click an aircraft for
// its route, airframe, photo and the track it has flown.
import { useEffect, useMemo, useRef, useState } from 'react';
import { Plane, Search, Star, X } from 'lucide-react';
import { useFollow } from './follow';
import { cn } from '@/lib/utils';
import { ErrorBox, Loading, useJSON } from './shared';
import { Photos } from './Photos';
import { greatCircle, LiveMap, project, type LiveMapHandle, type MapBounds, type MapLine, type MapMarker, type MapPoint } from './LiveMap';

const AIRPORTS: [string, string, number, number][] = [
  ['HKG', 'Hong Kong', 22.308, 113.918], ['PEK', 'Beijing', 40.08, 116.584], ['PVG', 'Shanghai', 31.144, 121.808], ['HND', 'Tokyo Haneda', 35.549, 139.78],
  ['ICN', 'Seoul', 37.46, 126.44], ['SIN', 'Singapore', 1.364, 103.991], ['DXB', 'Dubai', 25.253, 55.364], ['DOH', 'Doha', 25.273, 51.608],
  ['IST', 'Istanbul', 41.275, 28.752], ['LHR', 'London', 51.47, -0.454], ['CDG', 'Paris', 49.01, 2.55], ['FRA', 'Frankfurt', 50.037, 8.562],
  ['AMS', 'Amsterdam', 52.31, 4.768], ['JFK', 'New York', 40.641, -73.778], ['ORD', 'Chicago', 41.974, -87.907], ['ATL', 'Atlanta', 33.64, -84.427],
  ['LAX', 'Los Angeles', 33.942, -118.408], ['MEM', 'Memphis (FedEx)', 35.042, -89.977], ['ANC', 'Anchorage (cargo)', 61.174, -149.996], ['SYD', 'Sydney', -33.94, 151.175],
];
// common airline ICAO prefixes (callsign = prefix + flight number)
const AIRLINES: Record<string, string> = {
  AAL: 'American', DAL: 'Delta', UAL: 'United', SWA: 'Southwest', JBU: 'JetBlue', ASA: 'Alaska', FDX: 'FedEx', UPS: 'UPS', BAW: 'British Airways',
  AFR: 'Air France', DLH: 'Lufthansa', KLM: 'KLM', RYR: 'Ryanair', EZY: 'easyJet', WZZ: 'Wizz Air', THY: 'Turkish', UAE: 'Emirates', QTR: 'Qatar',
  ETD: 'Etihad', SIA: 'Singapore', CPA: 'Cathay Pacific', HKE: 'HK Express', CRK: 'Hong Kong Airlines', CCA: 'Air China', CES: 'China Eastern',
  CSN: 'China Southern', CHH: 'Hainan', CSZ: 'Shenzhen', CXA: 'Xiamen', JAL: 'Japan Airlines', ANA: 'ANA', KAL: 'Korean Air', AAR: 'Asiana',
  QFA: 'Qantas', VOZ: 'Virgin Australia', ANZ: 'Air New Zealand', ACA: 'Air Canada', WJA: 'WestJet', AMX: 'Aeromexico', LAN: 'LATAM', TAM: 'LATAM Brasil',
  AIC: 'Air India', IGO: 'IndiGo', SVA: 'Saudia', ETH: 'Ethiopian', GTI: 'Atlas Air', CLX: 'Cargolux', ABW: 'AirBridgeCargo', CAO: 'Air China Cargo',
  EVA: 'EVA Air', CAL: 'China Airlines', VJC: 'VietJet', HVN: 'Vietnam Airlines', THA: 'Thai', MAS: 'Malaysia', GIA: 'Garuda', PAL: 'Philippine',
  SAS: 'SAS', FIN: 'Finnair', IBE: 'Iberia', VLG: 'Vueling', TAP: 'TAP', AZA: 'ITA', SWR: 'Swiss', AUA: 'Austrian', EIN: 'Aer Lingus', NKS: 'Spirit',
  FFT: 'Frontier', SKW: 'SkyWest', RPA: 'Republic', ENY: 'Envoy', EDV: 'Endeavor', VIR: 'Virgin Atlantic', ELY: 'El Al', MSR: 'EgyptAir', RAM: 'Royal Air Maroc',
};
const ALT_BANDS: [string, number, string][] = [['Ground', -1, 'rgb(var(--c-text-tertiary))'], ['< 10,000 ft', 10000, 'rgb(var(--c-amber))'],
  ['10–25,000 ft', 25000, 'rgb(var(--c-green))'], ['25–35,000 ft', 35000, 'rgb(var(--c-blue))'], ['> 35,000 ft', Infinity, 'rgb(168 85 247)']];
const altColor = (alt: number | null, ground: boolean) => (ground ? ALT_BANDS[0][2] : alt == null ? 'rgb(var(--c-text-secondary))'
  : (ALT_BANDS.slice(1).find(([, max]) => alt < max) ?? ALT_BANDS[4])[2]);
const airlineOf = (cs: string) => (/^[A-Z]{3}\d/.test(cs) ? cs.slice(0, 3) : null);

// notable reasons (backend tag letters) and their ring colours
const FTAGS: [string, string, string][] = [['e', 'Emergency', 'rgb(239 68 68)'], ['v', 'VIP / government', 'rgb(234 179 8)'], ['m', 'Military', 'rgb(236 72 153)'],
  ['n', 'Notable aircraft', 'rgb(168 85 247)'], ['c', 'Cargo', 'rgb(20 184 166)']];
const ftagColor = (t: string) => FTAGS.find(([k]) => t.includes(k))?.[2];

type Ac = { tag?: string; hex: string; callsign: string; country?: string | null; lon: number; lat: number; alt: number | null; ground: boolean; speed: number | null;
  track: number | null; vrate: number | null; squawk: string | null; fix: number; mil: boolean; type?: string | null; reg?: string | null; model?: string | null;
  operator?: string | null; live?: boolean; emergency?: string | null };

const EMERG: Record<string, string> = { '7500': 'Hijack', '7600': 'Radio failure', '7700': 'Emergency' };

export function FlightTracker() {
  const world = useJSON<any>('/api/v1/mkt/fly/world', 60_000);
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [projectOn, setProjectOn] = useState(true);
  const [showGround, setShowGround] = useState(false);
  const [only, setOnly] = useState<'all' | 'mil' | 'emerg' | 'notable'>('all');
  const [tab, setTab] = useState<'view' | 'notable' | 'follow'>('view');
  const follow = useFollow('plane');
  const notable = useJSON<any>('/api/v1/mkt/fly/notable', 60_000);
  const [find, setFind] = useState('');
  const [now, setNow] = useState(() => Date.now() / 1000);
  const map = useRef<LiveMapHandle>(null);
  useEffect(() => { const t = setInterval(() => document.visibilityState === 'visible' && setNow(Date.now() / 1000), 5000); return () => clearInterval(t); }, []);

  // live detail for the visible area once zoomed in (radius covers the view, 250 nm at most)
  const liveArea = bounds && bounds.zoom >= 6 ? (() => {
    const km = Math.hypot((bounds.east - bounds.west) * 111 * Math.cos((bounds.lat * Math.PI) / 180), (bounds.north - bounds.south) * 111) / 2;
    return { lat: bounds.lat, lon: bounds.lon, nm: Math.max(20, Math.min(250, Math.round(km / 1.852))) };
  })() : null;
  const area = useJSON<any>(liveArea ? `/api/v1/mkt/fly/area?lat=${liveArea.lat.toFixed(2)}&lon=${liveArea.lon.toFixed(2)}&radius_nm=${liveArea.nm}` : null, 10_000);

  const aircraft: Ac[] = useMemo(() => {
    const out = new Map<string, Ac>();
    const cols: string[] = world.data?.cols ?? [];
    const ix = Object.fromEntries(cols.map((c, i) => [c, i]));
    for (const r of world.data?.rows ?? []) {
      let lon = r[ix.lon], lat = r[ix.lat];
      const ground = !!r[ix.ground], speed = r[ix.speed], track = r[ix.track];
      const age = now - (r[ix.fix] ?? now);
      if (projectOn && !ground && speed > 60 && track != null && age > 0 && age < 1500) [lon, lat] = project(lon, lat, track, speed, age);
      out.set(r[ix.hex], { hex: r[ix.hex], callsign: r[ix.callsign] || '', country: r[ix.country], lon, lat, alt: r[ix.alt], ground, speed, track,
        vrate: r[ix.vrate], squawk: r[ix.squawk], fix: r[ix.fix], mil: !!r[ix.mil], type: r[ix.type], emergency: EMERG[String(r[ix.squawk] ?? '')] ?? null, tag: r[ix.tag] ?? '' });
    }
    if (area.data && liveArea) {
      const t = area.data.time ?? now;
      for (const a of area.data.aircraft ?? []) {
        const prev = out.get(a.hex);
        out.set(a.hex, { hex: a.hex, callsign: a.flight || prev?.callsign || '', country: prev?.country, lon: a.lon, lat: a.lat, alt: a.alt, ground: a.on_ground,
          speed: a.speed, track: a.track, vrate: a.vrate, squawk: a.squawk, fix: t - (a.seen_s ?? 0), mil: a.military || !!prev?.mil, type: a.type,
          reg: a.reg, model: a.model, operator: a.operator, live: true, emergency: a.emergency, tag: prev?.tag ?? (a.emergency ? 'e' : a.military ? 'm' : '') });
      }
    }
    return [...out.values()];
  }, [world.data, area.data, projectOn, now]);                 // eslint-disable-line react-hooks/exhaustive-deps

  const shown = aircraft.filter((a) => follow.ids.has(a.hex) || ((showGround || !a.ground || a.hex === sel)
    && (only === 'all' || (only === 'mil' ? a.mil : only === 'notable' ? !!a.tag : !!a.emergency) || a.hex === sel)));
  const points: MapPoint[] = useMemo(() => shown.map((a) => ({
    id: a.hex, lon: a.lon, lat: a.lat, color: a.emergency ? 'rgb(var(--c-red))' : altColor(a.alt, a.ground), heading: a.track, moving: !a.ground,
    big: !!a.emergency, ring: a.tag ? ftagColor(a.tag) : a.mil ? 'rgb(236 72 153)' : undefined, label: a.callsign || undefined, pin: follow.ids.has(a.hex),
  })), [shown, follow.ids]);
  const byHex = useMemo(() => new Map(aircraft.map((a) => [a.hex, a])), [aircraft]);
  const selAc = sel ? byHex.get(sel) : undefined;
  const detail = useJSON<any>(sel ? `/api/v1/mkt/fly/flight/${sel}${selAc?.callsign ? `?callsign=${encodeURIComponent(selAc.callsign)}` : ''}` : null, 20_000);
  const det = detail.current ? detail.data : null;

  const lines: MapLine[] = useMemo(() => {
    if (!det || !selAc) return [];
    const out: MapLine[] = [];
    if (det.track?.length > 1) out.push({ coords: [...det.track.map((p: any) => [p[0], p[1]] as [number, number]), [selAc.lon, selAc.lat]], color: 'rgb(var(--c-bloomberg))', width: 2 });
    const dst = det.route?.destination, org = det.route?.origin;
    if (det.route?.matches_position !== false && dst?.lat != null) out.push({ coords: greatCircle([selAc.lon, selAc.lat], [dst.lon, dst.lat]), color: 'rgb(var(--c-text-secondary))', width: 1.2, dash: [5, 4] });
    if (det.route?.matches_position !== false && org?.lat != null && !(det.track?.length > 1)) out.push({ coords: greatCircle([org.lon, org.lat], [selAc.lon, selAc.lat]), color: 'rgb(var(--c-bloomberg) / 0.6)', width: 1.2 });
    return out;
  }, [det, selAc?.lon, selAc?.lat]);                          // eslint-disable-line react-hooks/exhaustive-deps
  const markers: MapMarker[] = useMemo(() => {
    const out: MapMarker[] = [];
    const r = det?.route;
    if (r && r.matches_position !== false) for (const a of [r.origin, r.destination]) if (a?.lat != null) out.push({ lon: a.lon, lat: a.lat, label: a.iata ?? a.icao, color: 'rgb(var(--c-bloomberg))', r: 5, fill: true });
    const onRoute = new Set(out.map((m) => m.label));
    for (const [code, , lat, lon] of AIRPORTS) if (!onRoute.has(code)) out.push({ lon, lat, label: code, color: 'rgb(var(--c-text-secondary))', r: 3.5, id: code });
    return out;
  }, [det]);

  const inView = useMemo(() => (bounds ? shown.filter((a) => a.lat >= bounds.south && a.lat <= bounds.north
    && (bounds.east - bounds.west >= 360 || ((a.lon - bounds.west + 360) % 360) <= ((bounds.east - bounds.west + 360) % 360))) : shown), [shown, bounds]);
  const stats = useMemo(() => {
    const bands = ALT_BANDS.map(([l, , c]) => ({ l, c, n: 0 }));
    const lines: Record<string, number> = {};
    for (const a of inView) {
      const b = a.ground ? 0 : a.alt == null ? 2 : ALT_BANDS.findIndex(([, max], i) => i > 0 && a.alt! < max);
      bands[b < 0 ? 4 : b].n++;
      const al = airlineOf(a.callsign);
      if (al) lines[al] = (lines[al] ?? 0) + 1;
    }
    return { bands, airlines: Object.entries(lines).sort((a, b) => b[1] - a[1]).slice(0, 10) };
  }, [inView]);

  const doFind = (e: React.FormEvent) => {
    e.preventDefault();
    const q = find.trim().toUpperCase().replace(/\s/g, '');
    if (!q) return;
    const hit = aircraft.find((a) => a.callsign.toUpperCase() === q || a.hex.toUpperCase() === q || (a.reg ?? '').toUpperCase().replace('-', '') === q.replace('-', ''))
      ?? aircraft.find((a) => a.callsign.toUpperCase().startsWith(q));
    if (hit) { setSel(hit.hex); map.current?.flyTo({ lon: hit.lon, lat: hit.lat, zoom: Math.max(bounds?.zoom ?? 0, 6.5) }); }
  };

  const hoverText = (id: string) => {
    const a = byHex.get(id);
    if (!a) return '';
    const al = airlineOf(a.callsign);
    return `${a.callsign || a.hex}${al && AIRLINES[al] ? ` · ${AIRLINES[al]}` : ''}${a.mil ? ' · MILITARY' : ''}\n`
      + `${a.ground ? 'on ground' : `${a.alt?.toLocaleString() ?? '?'} ft · ${a.speed ?? '?'} kt · ${a.track ?? '?'}°`}${a.type ? ` · ${a.type}` : ''}`
      + `${a.emergency ? `\n⚠ squawk ${a.squawk} — ${a.emergency}` : ''}`;
  };

  if (world.loading && !world.data) return <Loading label="Loading every aircraft in the world…" />;
  if (world.error && !world.data) return <ErrorBox msg={world.error} />;
  const w = world.data;
  const fixAge = w?.time ? Math.round((now - w.time) / 60) : null;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        <span className="text-text-primary"><Plane className="inline w-3.5 h-3.5 mr-1 text-bloomberg" /><b className="font-mono">{w?.airborne?.toLocaleString()}</b> airborne worldwide</span>
        <span className="text-text-secondary"><b className="font-mono">{w?.on_ground?.toLocaleString()}</b> on the ground</span>
        <button onClick={() => setOnly(only === 'mil' ? 'all' : 'mil')} className={cn('px-1.5 border', only === 'mil' ? 'border-[rgb(236_72_153)] text-[rgb(236_72_153)]' : 'border-border text-text-secondary')}>
          {w?.military} military</button>
        <button onClick={() => setOnly(only === 'emerg' ? 'all' : 'emerg')} className={cn('px-1.5 border', only === 'emerg' ? 'border-red text-red' : w?.emergencies?.length ? 'border-red/60 text-red' : 'border-border text-text-tertiary')}>
          {w?.emergencies?.length ?? 0} emergency squawk{w?.emergencies?.length === 1 ? '' : 's'}</button>
        <button onClick={() => setOnly(only === 'notable' ? 'all' : 'notable')} title="VIP / government, military, notable aircraft, cargo flights, emergencies"
          className={cn('px-1.5 border', only === 'notable' ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{notable.data?.total ?? '…'} notable</button>
        <span className="text-text-tertiary">in view <b className="font-mono text-text-secondary">{inView.length.toLocaleString()}</b></span>
        {w?.sweep && <span className="text-text-tertiary" title="adsb.fi + adsb.lol queried continuously around 60 hubs in China, Asia, the Middle East, Africa and Latin America, where OpenSky has few receivers">
          <span className="text-green">●</span> {w.sweep.live_aircraft.toLocaleString()} live at {w.sweep.hubs} emerging-market hubs (+{w.sweep.added} not in OpenSky)</span>}
        <span className="ml-auto text-text-tertiary">{liveArea && area.data ? <span className="text-green">● live in this area ({area.data.aircraft.length} aircraft, 10 s refresh)</span>
          : `world snapshot ${fixAge != null ? `${fixAge} min old` : ''}${w?.stale ? ' (OpenSky limit reached — last snapshot)' : ''} · zoom in for live`}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
        <form onSubmit={doFind} className="flex">
          <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Callsign, hex or registration" aria-label="Find an aircraft"
            className="w-48 bg-surface-1 border border-border px-2 py-0.5 font-mono text-text-primary placeholder:text-text-tertiary" />
          <button className="px-1.5 border border-l-0 border-border text-text-secondary" aria-label="Find"><Search className="w-3 h-3" /></button>
        </form>
        {AIRPORTS.map(([code, name, lat, lon]) => (
          <button key={code} title={name} onClick={() => map.current?.flyTo({ lon, lat, zoom: 8 })} className="px-1.5 py-0.5 border border-border font-mono text-text-secondary hover:text-bloomberg hover:border-bloomberg">{code}</button>))}
      </div>
      <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_360px] gap-2">
        <LiveMap ref={map} glyph="plane" points={points} lines={lines} markers={markers} selected={sel} onSelect={setSel} onView={setBounds}
          onMarker={(code) => { const ap = AIRPORTS.find((x) => x[0] === code); if (ap) map.current?.flyTo({ lon: ap[3], lat: ap[2], zoom: Math.max(bounds?.zoom ?? 0, 8) }); }}
          hoverText={hoverText} height={600} initial={{ lon: 60, lat: 30, zoom: 2.2 }}>
          <div className="absolute bottom-2 left-2 flex flex-wrap gap-2 text-[10px] bg-surface-1/85 border border-border px-2 py-1">
            {ALT_BANDS.map(([l, , c]) => <span key={l} className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: c }} />{l}</span>)}
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full border-2 border-[rgb(236_72_153)]" />military</span>
            <label className="inline-flex items-center gap-1 cursor-pointer"><input type="checkbox" checked={showGround} onChange={(e) => setShowGround(e.target.checked)} />ground</label>
            <label className="inline-flex items-center gap-1 cursor-pointer" title="Move each aircraft along its track from its last reported position to now">
              <input type="checkbox" checked={projectOn} onChange={(e) => setProjectOn(e.target.checked)} />project to now</label>
          </div>
        </LiveMap>
        <div className="space-y-2 min-w-0">
          {sel ? <FlightCard hex={sel} ac={selAc} det={det} loading={detail.loading && !det} onClose={() => setSel(null)} follow={follow} />
            : <>
              <div className="flex gap-1 text-[11px]">{([['view', 'In view'], ['notable', `Notable ${notable.data?.total ?? ''}`], ['follow', `Following ${follow.list.length}`]] as const).map(([k, l]) => (
                <button key={k} onClick={() => setTab(k)} className={cn('flex-1 px-2 py-1 border', tab === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>))}</div>
              {tab === 'view' && <ViewPanel stats={stats} inView={inView} onPick={(a) => { setSel(a.hex); }} />}
              {tab === 'notable' && <NotableFlights data={notable.data} loading={notable.loading} follow={follow}
                onPick={(x) => { setSel(x.hex); map.current?.flyTo({ lon: x.lon, lat: x.lat, zoom: Math.max(bounds?.zoom ?? 0, 6.5) }); }} />}
              {tab === 'follow' && <FollowFlights follow={follow} byHex={byHex}
                onPick={(h) => { const a = byHex.get(h); setSel(h); if (a) map.current?.flyTo({ lon: a.lon, lat: a.lat, zoom: Math.max(bounds?.zoom ?? 0, 6.5) }); }} />}
            </>}
        </div>
      </div>
      <div className="text-[10px] text-text-tertiary">{w?.source}. {w?.note} Live areas: adsb.fi. Routes and airframes: adsbdb.com. Coverage depends on volunteer receivers
        (thin over oceans and Africa; mainland China restricts private receivers, so its domestic traffic is only partly visible on any free network); military flights often switch transponders off.{projectOn ? ' Snapshot positions are projected along each aircraft’s track to now.' : ''}</div>
    </div>
  );
}

function NotableFlights({ data, loading, follow, onPick }: { data: any; loading: boolean; follow: ReturnType<typeof useFollow>; onPick: (x: any) => void }) {
  const [only, setOnly] = useState('');
  if (loading && !data) return <Loading label="Finding flights worth watching…" />;
  if (!data) return null;
  const list = (data.flights as any[]).filter((x) => !only || x.tags.includes(only));
  return (
    <div className="border border-border bg-surface-1">
      <div className="flex flex-wrap gap-1 p-2 text-[10px]">
        <button onClick={() => setOnly('')} className={cn('px-1.5 border', !only ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>All {data.total}</button>
        {FTAGS.map(([k, l, col]) => (
          <button key={k} onClick={() => setOnly(k)} className={cn('px-1.5 border inline-flex items-center gap-1', only === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>
            <span className="w-2 h-2 rounded-full border-2" style={{ borderColor: col }} />{l} {data.counts?.[k] ?? 0}</button>))}
      </div>
      <ul className="max-h-[440px] overflow-y-auto divide-y divide-border-subtle">{list.map((x) => (
        <li key={x.hex}><button onClick={() => onPick(x)} className="w-full text-left px-2 py-1.5 hover:bg-surface-3 flex gap-2 items-start">
          <span className="mt-1 w-2 h-2 rounded-full border-2 shrink-0" style={{ borderColor: ftagColor(x.tags) }} />
          <span className="min-w-0 flex-1"><span className="text-[11px] font-mono text-text-primary">{x.callsign}</span>
            <span className="text-[10px] text-text-tertiary"> {x.type ?? ''}{x.alt != null ? ` · ${x.alt.toLocaleString()} ft` : ''}</span>
            <span className="block text-[10px] text-text-secondary truncate">{x.reasons.join(' · ')}</span></span>
          {follow.isFollowed(x.hex) && <Star className="w-3 h-3 text-[rgb(202_138_4)] fill-current shrink-0" />}
        </button></li>))}</ul>
      <p className="p-2 text-[10px] text-text-tertiary">{data.note}</p>
    </div>
  );
}

function FollowFlights({ follow, byHex, onPick }: { follow: ReturnType<typeof useFollow>; byHex: Map<string, Ac>; onPick: (hex: string) => void }) {
  if (!follow.list.length) return <p className="border border-border bg-surface-1 p-3 text-[11px] text-text-tertiary">Nothing followed yet — open an aircraft and press <b>Follow</b>. It keeps a gold ring and a label on the map wherever it flies, with your notes here.</p>;
  return (
    <ul className="border border-border bg-surface-1 divide-y divide-border-subtle max-h-[520px] overflow-y-auto">{follow.list.map((f) => {
      const a = byHex.get(f.id);
      return (
        <li key={f.id} className="px-2 py-1.5">
          <div className="flex items-center gap-2">
            <Star className="w-3 h-3 text-[rgb(202_138_4)] fill-current shrink-0" />
            <button onClick={() => onPick(f.id)} className="text-[11px] font-mono text-text-primary hover:text-bloomberg">{f.label}</button>
            <span className="text-[10px] text-text-tertiary">{a ? (a.ground ? 'on the ground' : `${a.alt?.toLocaleString() ?? '?'} ft · ${a.speed ?? '?'} kt`) : 'not in range now'}</span>
            <button onClick={() => follow.remove(f.id)} className="ml-auto text-text-tertiary hover:text-red" aria-label="Stop following"><X className="w-3 h-3" /></button>
          </div>
          {f.reason && <div className="text-[10px] text-amber">{f.reason}</div>}
          <textarea value={f.note} onChange={(e) => follow.setNote(f.id, e.target.value)} rows={1} placeholder="Notes…" aria-label={`Notes on ${f.label}`}
            className="mt-1 w-full bg-surface-2 border border-border-subtle px-1.5 py-0.5 text-[11px] text-text-primary" />
        </li>);
    })}</ul>
  );
}

function ViewPanel({ stats, inView, onPick }: { stats: { bands: { l: string; c: string; n: number }[]; airlines: [string, number][] }; inView: Ac[]; onPick: (a: Ac) => void }) {
  const max = Math.max(1, ...stats.bands.map((b) => b.n));
  const list = [...inView].filter((a) => !a.ground).sort((a, b) => (b.alt ?? -1) - (a.alt ?? -1)).slice(0, 150);
  return (
    <>
      <div className="border border-border bg-surface-1 p-2 text-[11px]">
        <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">In view by altitude</div>
        {stats.bands.map((b) => (
          <div key={b.l} className="flex items-center gap-2"><span className="w-24 text-text-secondary">{b.l}</span>
            <div className="flex-1 h-2 bg-surface-3"><div className="h-full" style={{ width: `${(b.n / max) * 100}%`, background: b.c }} /></div>
            <span className="w-12 text-right font-mono">{b.n.toLocaleString()}</span></div>))}
        {stats.airlines.length > 0 && <>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mt-2 mb-1">Busiest airlines in view</div>
          <div className="grid grid-cols-2 gap-x-3">{stats.airlines.map(([c, n]) => (
            <div key={c} className="flex justify-between"><span className="text-text-secondary truncate"><span className="font-mono text-text-tertiary mr-1">{c}</span>{AIRLINES[c] ?? ''}</span><span className="font-mono">{n}</span></div>))}</div></>}
      </div>
      <div className="border border-border max-h-[372px] overflow-y-auto">
        <table className="w-full text-[11px] font-mono">
          <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left px-1.5 font-normal">Flight</th><th className="text-left font-normal">Type</th>
            <th className="text-right font-normal">Alt ft</th><th className="text-right font-normal">Kt</th><th className="text-right px-1.5 font-normal">Hdg</th></tr></thead>
          <tbody>{list.map((a) => (
            <tr key={a.hex} onClick={() => onPick(a)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-3', a.emergency && 'text-red')}>
              <td className="px-1.5">{a.callsign || a.hex}{a.mil && <span className="ml-1 text-[9px] text-[rgb(236_72_153)]">MIL</span>}</td>
              <td className="text-text-secondary">{a.type ?? ''}</td><td className="text-right">{a.alt?.toLocaleString() ?? '—'}</td>
              <td className="text-right">{a.speed ?? ''}</td><td className="text-right px-1.5">{a.track ?? ''}</td></tr>))}</tbody>
        </table>
        {list.length === 0 && <p className="p-2 text-[11px] text-text-tertiary">No airborne aircraft in this view.</p>}
      </div>
    </>
  );
}

function FlightCard({ hex, ac, det, loading, onClose, follow }: { hex: string; ac?: Ac; det: any; loading: boolean; onClose: () => void; follow: ReturnType<typeof useFollow> }) {
  const followed = follow.isFollowed(hex);
  const fNote = follow.list.find((f) => f.id === hex)?.note ?? '';
  const live = det?.live, fr = det?.airframe, rt = det?.route, pg = det?.progress;
  const al = ac ? airlineOf(ac.callsign) : null;
  const v = (x: any, unit = '') => (x == null || x === '' ? '—' : `${typeof x === 'number' ? x.toLocaleString() : x}${unit}`);
  const alt = live?.alt ?? ac?.alt, spd = live?.speed ?? ac?.speed, trk = live?.track ?? ac?.track, vr = live?.vrate ?? ac?.vrate;
  return (
    <div className="border border-border bg-surface-1 p-2.5 text-xs space-y-2 max-h-[600px] overflow-y-auto">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-base font-semibold text-text-primary font-mono">{ac?.callsign || hex.toUpperCase()}
            {ac?.mil && <span className="ml-2 text-[10px] px-1 border border-[rgb(236_72_153)] text-[rgb(236_72_153)]">MILITARY</span>}
            {ac?.emergency && <span className="ml-2 text-[10px] px-1 border border-red text-red">{ac.emergency}</span>}</div>
          <div className="text-[11px] text-text-secondary">{rt?.airline ?? (al ? AIRLINES[al] : null) ?? ac?.operator ?? fr?.owner ?? ''}{rt?.iata ? ` · ${rt.iata}` : ''}</div>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => follow.toggle(hex, ac?.callsign || hex.toUpperCase(), det?.notable?.[0])} title={followed ? 'Stop following' : 'Follow this aircraft'}
            className={cn('inline-flex items-center gap-1 px-2 py-0.5 border text-[11px]', followed ? 'border-[rgb(234_179_8)] text-[rgb(202_138_4)]' : 'border-border text-text-secondary')}>
            <Star className={cn('w-3 h-3', followed && 'fill-current')} />{followed ? 'Following' : 'Follow'}</button>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary" aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
      </div>
      {det?.notable?.length > 0 && <div className="flex flex-wrap gap-1">{det.notable.map((r: string) => (
        <span key={r} className={cn('px-1.5 py-0.5 rounded border text-[10px]', r.startsWith('Squawking') ? 'border-red text-red' : 'border-amber/60 text-amber')}>{r}</span>))}</div>}
      {(det?.phase || det?.load) && <div className="grid grid-cols-2 gap-1.5 text-[11px]">
        <div><div className="text-text-tertiary">Phase of flight</div><div className="text-text-primary">{det?.phase ?? '—'}</div></div>
        <div><div className="text-text-tertiary">{det?.load?.kind === 'cargo' ? 'Carrying' : 'Capacity'}</div><div className="text-text-primary">{det?.load?.label ?? '—'}</div></div>
      </div>}
      {followed && <textarea value={fNote} onChange={(e) => follow.setNote(hex, e.target.value)} rows={2} placeholder="Your notes on this flight…"
        className="w-full bg-surface-2 border border-border px-2 py-1 text-[11px] text-text-primary" aria-label="Notes" />}
      {rt && rt.origin && rt.destination && (
        <div className={cn('border border-border-subtle p-2', rt.matches_position === false && 'opacity-60')}>
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0"><div className="text-lg font-semibold font-mono text-text-primary">{rt.origin.iata ?? rt.origin.icao}</div><div className="text-[10px] text-text-tertiary truncate">{rt.origin.city}</div></div>
            <Plane className="w-4 h-4 text-bloomberg shrink-0" />
            <div className="min-w-0 text-right"><div className="text-lg font-semibold font-mono text-text-primary">{rt.destination.iata ?? rt.destination.icao}</div><div className="text-[10px] text-text-tertiary truncate">{rt.destination.city}</div></div>
          </div>
          {pg && <>
            <div className="h-1.5 bg-surface-3 mt-2"><div className="h-full bg-bloomberg" style={{ width: `${pg.pct ?? 0}%` }} /></div>
            <div className="flex justify-between text-[10px] text-text-tertiary mt-1"><span>{pg.flown_km.toLocaleString()} km flown</span>
              <span>{pg.remaining_km.toLocaleString()} km to go{pg.eta_min != null ? ` · ~${pg.eta_min < 60 ? `${pg.eta_min} min` : `${Math.floor(pg.eta_min / 60)}h ${String(pg.eta_min % 60).padStart(2, '0')}m`}` : ''}</span></div></>}
          {rt.matches_position === false && <div className="text-[10px] text-amber mt-1">This callsign’s usual route — the aircraft is elsewhere, so it is flying a different route today.</div>}
        </div>)}
      <Photos kind="aircraft" hex={hex} registration={fr?.registration ?? live?.reg ?? ac?.reg} />
      <div className="grid grid-cols-3 gap-1.5 text-[11px]">
        {[['Altitude', ac?.ground ? 'Ground' : v(alt, ' ft')], ['Speed', v(spd != null ? Math.round(spd) : null, ' kt')], ['Heading', v(trk != null ? Math.round(trk) : null, '°')],
          ['Vertical', vr == null ? '—' : `${vr > 0 ? '+' : ''}${Math.round(vr).toLocaleString()} fpm`], ['Squawk', v(live?.squawk ?? ac?.squawk)], ['Mach', v(live?.mach)],
          ['Wind', live?.wind_kt != null ? `${live.wind_dir}° ${live.wind_kt} kt` : '—'], ['Outside air', live?.oat_c != null ? `${live.oat_c} °C` : '—'], ['Selected alt', v(live?.sel_alt, ' ft')]].map(([k, x]) => (
          <div key={k}><div className="text-text-tertiary">{k}</div><div className="font-mono text-text-primary">{x}</div></div>))}
      </div>
      <div className="border-t border-border-subtle pt-2 grid grid-cols-2 gap-1.5 text-[11px]">
        {[['Aircraft', fr ? [fr.manufacturer, fr.type].filter(Boolean).join(' ') : live?.model ?? ac?.model ?? ac?.type], ['Type code', fr?.icao_type ?? live?.type ?? ac?.type],
          ['Registration', fr?.registration ?? live?.reg ?? ac?.reg], ['Owner', fr?.owner ?? live?.operator], ['Registered in', fr?.owner_country ?? ac?.country],
          ['Built', live?.year], ['ICAO hex', hex.toUpperCase()], ['Data', ac?.live ? 'live (adsb.fi)' : 'world snapshot']].map(([k, x]) => (
          <div key={k as string}><div className="text-text-tertiary">{k}</div><div className="text-text-primary truncate" title={String(x ?? '')}>{x ?? '—'}</div></div>))}
      </div>
      {loading && <Loading label="Looking up route, airframe and track…" />}
      {det?.track?.length > 1 && <div className="text-[10px] text-text-tertiary">Orange line: track flown this flight ({det.track.length} points, OpenSky). Dashed: great-circle path to the destination.</div>}
      <div className="text-[10px] text-text-tertiary">{det?.source}</div>
    </div>
  );
}

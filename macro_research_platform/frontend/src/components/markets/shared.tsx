import { fetchJSONWithDeadline } from '@/lib/fetchDeadline';
// Shared bits for the Markets mode: data hook, number formats that respect the instrument
// (FX/crypto precision, currency), change colouring, compact market caps.
import { createContext, useCallback, useContext, useId, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

/** A readable message from a FastAPI error body (string detail, or a list of validation errors). */
export function apiError(j: any, status: number): string {
  const d = j?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) {
    return d.map((e: any) => {
      const field = Array.isArray(e?.loc) ? String(e.loc[e.loc.length - 1]).replace(/_/g, ' ') : 'input';
      return `${field}: ${String(e?.msg ?? 'invalid').replace(/^Input should be /, 'must be ')}`;
    }).join('; ');
  }
  return `Request failed (HTTP ${status}).`;
}

// Messages the API returned with 404 — "this doesn't apply / isn't published for this instrument",
// not a failure — so ErrorBox can show them as a neutral note instead of a red error.
const NOT_APPLICABLE = new Set<string>();

// ── Where each screen's numbers come from ──────────────────────────────────────────────────────────────────────────
// Every useJSON inside a <SourceScope> reports its response's source, delay, date and stale flag; <SourcesBar> lists
// them for that screen (each launchpad pane has its own scope).
type SourceMeta = { source: string; delay?: number | null; stale?: boolean; asOf?: string | null; fetchedAt?: number };
type RequestMeta={url:string;loading:boolean;refreshing:boolean;error:string|null;updatedAt:number|null;retry:()=>void};
type Registry = { request:(id:number,m:RequestMeta|null)=>void; requests:()=>RequestMeta[]; set: (id: number, m: SourceMeta | null) => void; subscribe: (fn: () => void) => () => void; all: () => SourceMeta[] };
const SourceCtx = createContext<Registry | null>(null);
let _metaId = 0;

function metaOf(j: any): SourceMeta | null {
  if (!j || typeof j !== 'object' || Array.isArray(j) || typeof j.source !== 'string' || !j.source) return null;
  const asOf = j.as_of ?? j.price_date ?? j.computed_at ?? j.last_updated ?? (typeof j.date === 'string' ? j.date : null);
  return { source: j.source, delay: typeof j.delay_minutes === 'number' ? j.delay_minutes : null, stale: !!j.stale,
           asOf: typeof asOf === 'string' ? asOf : null };
}

export function SourceScope({ children }: { children: ReactNode }) {
  const reg = useMemo<Registry>(() => {
    const m = new Map<number, SourceMeta>(), requests=new Map<number,RequestMeta>(), subs = new Set<() => void>();
    return { request:(id,meta)=>{if(meta)requests.set(id,meta);else requests.delete(id);subs.forEach(f=>f());},requests:()=>[...requests.values()],set: (id, meta) => { if (meta) m.set(id, meta); else m.delete(id); subs.forEach((f) => f()); },
             subscribe: (fn) => { subs.add(fn); return () => { subs.delete(fn); }; }, all: () => [...m.values()] };
  }, []);
  return <SourceCtx.Provider value={reg}>{children}</SourceCtx.Provider>;
}

/** A thin strip naming the data behind the screen: source, live / delayed, as-of date, refreshing. */
const ago = (t: number) => { const s = Math.max(0, Math.round((Date.now() - t) / 1000)); return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : `${Math.floor(s / 3600)}h ago`; };

export function SourcesBar({ className }: { className?: string }) {
  const reg = useContext(SourceCtx);
  const [, bump] = useState(0);
  const [online,setOnline]=useState(()=>navigator.onLine);
  useEffect(()=>{const update=()=>setOnline(navigator.onLine);window.addEventListener('online',update);window.addEventListener('offline',update);return()=>{window.removeEventListener('online',update);window.removeEventListener('offline',update);};},[]);
  useEffect(() => (reg ? reg.subscribe(() => bump((x) => x + 1)) : undefined), [reg]);
  useEffect(() => { const t = setInterval(() => {if(!document.hidden)bump((x) => x + 1);}, 10000); return () => clearInterval(t); }, []);   // "updated Ns ago" ticks
  if (!reg) return null;
  const seen = new Map<string, SourceMeta>();
  for (const m of reg.all()) {
    const k = m.source.split(/[(;—]/)[0].trim();
    const prev = seen.get(k);
    seen.set(k, prev ? { ...prev, stale: prev.stale || m.stale, delay: prev.delay ?? m.delay, asOf: prev.asOf ?? m.asOf,
                         fetchedAt: Math.max(prev.fetchedAt ?? 0, m.fetchedAt ?? 0) } : { ...m, source: k });
  }
  const items = [...seen.values()].slice(0, 6);
  const requests=reg.requests(),failed=requests.filter(r=>r.error),busy=requests.some(r=>r.loading||r.refreshing);
  if(!items.length&&!requests.length)return null;
  const retry=()=>{for(const r of failed.length?failed:requests)r.retry();};
  return (
    <div className={cn('flex flex-wrap items-center gap-1.5 text-[10px] text-text-tertiary', className)} aria-label="Data sources for this screen">
      <span className="uppercase tracking-wider">Data</span>
      {!online&&<span role="status" className="text-amber">Offline · displayed values may be saved; reconnect and retry feeds.</span>}
      {failed.length>0&&<span role="status" className="text-amber" title={failed.map(r=>r.error).join(' · ')}>{failed.length} source{failed.length===1?'':'s'} unavailable · displayed values may be older</span>}
      {busy&&<span className="text-text-secondary" role="status">Refreshing…</span>}
      {!busy&&!failed.length&&requests.length>0&&<span>{requests.filter(r=>r.updatedAt).length}/{requests.length} feeds loaded</span>}
      <button type="button" disabled={busy&&!failed.length} onClick={retry} className="mkt-data-refresh" title={failed.length?'Retry unavailable feeds':'Refresh data without resetting inputs'}>{failed.length?'Retry feeds':'Refresh data'}</button>
      <details className="basis-full rounded-lg border border-border bg-surface-1 px-3 py-2">
        <summary className="cursor-pointer text-text-secondary">Source details & freshness · {reg.all().length} datasets</summary>
        <div className="overflow-x-auto mt-2"><table className="w-full text-left text-[10px]">
          <thead><tr><th>Provider</th><th>Data date</th><th>Retrieved</th><th>Status</th></tr></thead>
          <tbody>{reg.all().map((m,i) => <tr key={i} className="border-t border-border-subtle">
            <td className="py-2 pr-3">{m.source}</td><td className="pr-3">{m.asOf ?? 'Not supplied'}</td>
            <td className="pr-3">{m.fetchedAt ? new Date(m.fetchedAt).toLocaleString() : 'Unknown'}</td>
            <td>{m.stale ? 'Saved / stale' : m.delay === 0 ? 'Provider reports live' : m.delay != null ? `${m.delay} min delayed` : 'Delay not supplied'}</td>
          </tr>)}</tbody></table></div>
        {!reg.all().length && <p>No provider metadata supplied yet.</p>}
        <p className="mt-2">Retrieval time is when this app received a response, not when the underlying figures changed. Missing dates or delay information do not imply live data. Currency and units follow individual field labels.</p>
        <div className="mt-2 flex flex-wrap gap-2">{[...new Map(requests.map(r => [r.url, r] as const)).values()].map(r => <a key={r.url} href={r.url} target="_blank" rel="noopener noreferrer" className="text-bloomberg underline">Inspect response: {r.url.split('?')[0]}</a>)}</div>
      </details>
      {items.map((m) => (
        <span key={m.source} className="inline-flex items-center gap-1 px-2 py-0.5 border border-border-subtle rounded-full bg-surface-1/60" title={m.source}>
          <span className={cn('w-1.5 h-1.5 rounded-full', m.stale ? 'bg-amber' : m.delay === 0 ? 'live-dot-tick' : 'bg-text-tertiary')} />
          <span className="truncate max-w-[16rem] text-text-secondary">{m.source}</span>
          {m.stale ? <span className="text-amber">· saved / stale copy</span>
            : m.delay === 0 ? <span className="text-green">· live</span>
            : m.delay ? <span>· {m.delay}-min delayed</span>
            : m.asOf ? <span>· as of {m.asOf}</span> : null}
          {m.fetchedAt ? <span className="tabular-nums text-text-tertiary">· updated {ago(m.fetchedAt)}</span> : null}
        </span>))}
    </div>
  );
}

export function useJSON<T = any>(url: string | null, refreshMs = 0) {
  const reg=useContext(SourceCtx),metaId=useRef(++_metaId);
  const [revision,reload]=useState(0);
  const retry=useCallback(()=>reload(n=>n+1),[]);
  type State={url:string|null;data:T|null;error:string|null;refreshError:string|null;loading:boolean;refreshing:boolean;updatedAt:number|null};
  const [state,setState]=useState<State>({url:null,data:null,error:null,refreshError:null,loading:false,refreshing:false,updatedAt:null});
  const snapshot=useRef(state);snapshot.current=state;
  useEffect(()=>{
    if(!url){setState({url:null,data:null,error:null,refreshError:null,loading:false,refreshing:false,updatedAt:null});return;}
    let live=true,inFlight=false,timer:ReturnType<typeof setTimeout>|undefined;
    const controller=new AbortController();
    const load=async(first:boolean,attempt=0)=>{
      if(!live||inFlight)return;inFlight=true;
      const previous=snapshot.current.url===url?snapshot.current.data:null;
      setState(s=>s.url===url?{...s,loading:s.data==null,refreshing:s.data!=null,error:null,refreshError:null}:{url,data:null,error:null,refreshError:null,loading:true,refreshing:false,updatedAt:null});
      try{
        const {response,json,invalid}=await fetchJSONWithDeadline(url,controller.signal);
        if(!response.ok)throw Object.assign(new Error(apiError(json,response.status)),{status:response.status,transient:response.status>=500||response.status===429});
        if(invalid)throw new Error(`Invalid response (HTTP ${response.status}).`);
        if(live)setState({url,data:json,error:null,refreshError:null,loading:false,refreshing:false,updatedAt:Date.now()});
      }catch(e:any){
        if(!live||e.name==='AbortError')return;
        if(first&&!previous&&(e.transient||e instanceof TypeError)&&attempt<3){timer=setTimeout(()=>load(true,attempt+1),[1500,4000,9000][attempt]);return;}
        if(e.status===404)NOT_APPLICABLE.add(e.message);
        setState(s=>({url,data:s.url===url?s.data:null,error:previous?null:e.message,refreshError:previous?e.message:null,loading:false,refreshing:false,updatedAt:s.url===url?s.updatedAt:null}));
      }finally{inFlight=false;}
    };
    load(true);
    const interval=refreshMs>0?setInterval(()=>{if(!document.hidden)load(false);},refreshMs):undefined;
    return()=>{live=false;controller.abort();clearInterval(interval);clearTimeout(timer);};
  },[url,refreshMs,revision]);
  const active=state.url===url?state:{url,data:null,error:null,refreshError:null,loading:!!url,refreshing:false,updatedAt:null};
  useEffect(()=>{
    if(!reg)return;
    const id=metaId.current,m=metaOf(active.data);
    reg.set(id,m?{...m,stale:m.stale||!!active.refreshError,fetchedAt:active.updatedAt??undefined}:null);
    reg.request(id,url?{url,loading:active.loading,refreshing:active.refreshing,error:active.error??active.refreshError,updatedAt:active.updatedAt,retry}:null);
    return()=>{reg.set(id,null);reg.request(id,null);};
  },[reg,url,active.data,active.error,active.refreshError,active.loading,active.refreshing,active.updatedAt,retry]);
  return {...active,current:active.data!=null&&state.url===url,retry};
}

export function decimalsFor(price: number | null | undefined, type?: string): number {
  if (price == null) return 2;
  const a = Math.abs(price);
  if (type === 'FX') return a >= 20 ? 3 : 5;
  if (a >= 1000) return 2;
  if (a >= 1) return 2;
  if (a >= 0.01) return 4;
  return 8;
}

export const fmtPrice = (v: number | null | undefined, type?: string) =>
  v == null || !Number.isFinite(v) ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: decimalsFor(v, type), maximumFractionDigits: decimalsFor(v, type) });

export const fmtPct = (v: number | null | undefined, d = 2) =>
  v == null || !Number.isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`;

export function fmtBig(v: number | null | undefined, ccy?: string | null): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const s = a >= 1e12 ? `${(v / 1e12).toFixed(2)}T` : a >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(v / 1e6).toFixed(1)}M`
    : a >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : v.toFixed(0);
  return ccy ? `${s} ${ccy}` : s;
}

export function Chg({ v, d = 2, className }: { v: number | null | undefined; d?: number; className?: string }) {
  return <span className={cn('font-mono tabular-nums', v == null ? 'text-text-tertiary' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : 'text-text-secondary', className)}>{fmtPct(v, d)}</span>;
}

export function Spark({ values, w = 72, h = 20 }: { values?: number[]; w?: number; h?: number }) {
  if (!values || values.length < 2) return <span className="inline-block" style={{ width: w }} />;
  const lo = Math.min(...values), hi = Math.max(...values);
  // a range under 0.2% of the level (stablecoins, pegs) is noise: don't stretch it to full height
  const flat = hi === lo || (hi - lo) / Math.max(Math.abs((hi + lo) / 2), 1e-12) < 0.002;
  const pad = 1.5, ih = h - 2 * pad;                    // keep the stroke and end dot inside the box
  const xy = values.map((v, i) => [(i / (values.length - 1)) * (w - 3), flat ? h / 2 : pad + ih - ((v - lo) / (hi - lo)) * ih]);
  const pts = xy.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(' ');
  const up = values[values.length - 1] >= values[0];
  if (flat) return <svg width={w} height={h} aria-hidden="true" className="inline-block align-middle"><polyline points={pts} fill="none" stroke="rgb(var(--c-text-tertiary))" strokeWidth={1.25} /></svg>;
  const col = up ? 'rgb(var(--c-green))' : 'rgb(var(--c-red))';
  const [lx, ly] = xy[xy.length - 1];
  return (
    <svg width={w} height={h} aria-hidden="true" className="inline-block align-middle overflow-visible">
      <polygon points={`0,${h} ${pts} ${lx.toFixed(1)},${h}`} fill={col} fillOpacity={0.12} />
      <polyline points={pts} fill="none" stroke={col} strokeWidth={1.3} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lx} cy={ly} r={1.8} fill={col} />
    </svg>
  );
}

export function Panel({ title, right, children, className }: { title?: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  const [collapsed,setCollapsed]=useState(false);const id=useId();
  return (
    <section data-panel-title={title} className={cn('mkt-panel bg-surface-1 border border-border', className)}>
      {(title || right) && (
        <div className="panel-hdr flex items-center justify-between gap-2 px-3 py-1.5 border-b border-border-subtle">
          {title&&<h2 className="text-[10px] uppercase tracking-wider text-text-tertiary">{title}</h2>}
          <div className="ml-auto flex items-center gap-2">{right}{title&&<button type="button" className="mkt-panel-collapse" aria-label={`${collapsed?'Expand':'Collapse'} ${title}`} aria-expanded={!collapsed} aria-controls={id} onClick={()=>setCollapsed(v=>!v)}>{collapsed?'+':'−'}</button>}</div>
        </div>
      )}
      <div id={id} hidden={collapsed} className="mkt-panel-body p-3">{children}</div>
    </section>
  );
}

/** Loading placeholder: a shimmering skeleton with the label, so a screen never looks blank. */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="p-3 space-y-2" role="status" aria-live="polite">
      <div className="flex items-center gap-2 text-2xs text-text-tertiary">
        <span className="inline-block w-3 h-3 rounded-full border-2 border-bloomberg/30 border-t-bloomberg animate-spin" />{label}
      </div>
      <div className="mkt-skeleton h-2.5 w-3/4" /><div className="mkt-skeleton h-2.5 w-1/2" /><div className="mkt-skeleton h-2.5 w-2/3" />
    </div>
  );
}

export function ErrorBox({ msg,onRetry }: { msg: string | null;onRetry?:()=>void }) {
  if (msg && NOT_APPLICABLE.has(msg)) {
    return (
      <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-border bg-surface-1 text-xs text-text-secondary" role="status">
        <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 mt-0.5 shrink-0 text-text-tertiary" fill="currentColor" aria-hidden="true"><path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm-.75 3h1.5V6h-1.5V4.5Zm0 3h1.5v4h-1.5v-4Z" /></svg>
        <span>{msg}</span>
      </div>);
  }
  return msg ? (
    <div className="flex items-start gap-2 px-3 py-2 rounded-md border border-red/35 bg-red/[0.06] text-xs text-red" role="alert">
      <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 mt-0.5 shrink-0" fill="currentColor" aria-hidden="true"><path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm-.75 3.5h1.5v4.5h-1.5V5Zm0 5.5h1.5V12h-1.5v-1.5Z" /></svg>
      <span className="flex-1">{msg}</span>{onRetry&&<button type="button" onClick={onRetry} className="underline shrink-0">Retry</button>}
    </div>) : null;
}

export const TYPE_COLOR: Record<string, string> = {
  Stock: 'text-blue', ETF: 'text-green', Fund: 'text-green', Index: 'text-amber', FX: 'text-purple',
  Crypto: 'text-bloomberg', Future: 'text-purple', Option: 'text-red',
};

/** A value that flashes green/red for a moment when it ticks up/down (terminal monitors). */
export function Flash({ value, children, className }: { value: number | null | undefined; children: React.ReactNode; className?: string }) {
  const prev = useRef<number | null | undefined>(value);
  const [cls, setCls] = useState('');
  const [n, setN] = useState(0);
  useEffect(() => {
    if (value != null && prev.current != null && value !== prev.current) {
      setCls(value > prev.current ? 'flash-up' : 'flash-down');
      setN((k) => k + 1);                       // restart the animation on every tick
    }
    prev.current = value;
  }, [value]);
  return <span key={n} className={cn(cls, className)}>{children}</span>;
}

/** Click-to-sort for any table: `useSort(rows)` returns the sorted rows and a header factory.
 *  First click sorts descending for numbers (biggest first) and ascending for text; again flips. */
export function useSort<T extends Record<string, any>>(rows: T[] | undefined, initial?: { key: string; dir: 1 | -1 }) {
  const [s, setS] = useState<{ key: string; dir: 1 | -1 } | null>(initial ?? null);
  const sorted = useMemo(() => {
    const r = [...(rows ?? [])];
    if (!s) return r;
    const val = (x: T) => {
      const v = s.key.split('.').reduce((o: any, k) => (o == null ? o : o[k]), x);
      return typeof v === 'string' ? v.toLowerCase() : v;
    };
    return r.sort((a, b) => {
      const va = val(a), vb = val(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;                              // blanks always last
      if (vb == null) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * s.dir;
    });
  }, [rows, s]);
  const toggleSort=(key:string,numeric:boolean)=>setS(p=>p?.key===key?{key,dir:(p.dir*-1) as 1|-1}:{key,dir:numeric?-1:1});
  const th = (key: string, label: React.ReactNode, className = '', numeric = true) => (
    <th className={cn('font-normal cursor-pointer select-none hover:text-text-primary whitespace-nowrap', className)} aria-sort={s?.key === key ? (s.dir > 0 ? 'ascending' : 'descending') : undefined}
      tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggleSort(key,numeric);}}} onClick={()=>toggleSort(key,numeric)} title="Sort · Enter or Space">
      {label}{s?.key === key ? <span className="text-bloomberg ml-0.5">{s.dir > 0 ? '▲' : '▼'}</span> : null}</th>
  );
  return { rows: sorted, th, sort: s };
}

/** Instrument type from a Yahoo symbol, for lists that only carry symbols (FX needs 4–5 decimals). */
export const symType = (s?: string | null) => (s && s.endsWith('=X') ? 'FX' : undefined);

/** A plain data summary; callers provide the unit and meaning rather than inferring an investment signal. */
export function MarketStatCard({label,value,note}:{label:string;value:ReactNode;note?:ReactNode}){
 return <div className="mkt-stat-card"><div className="mkt-stat-label">{label}</div><div className="mkt-stat-value">{value}</div>{note&&<div className="mkt-stat-note">{note}</div>}</div>;
}
export function EmptyState({title,detail}:{title:string;detail:string}){
 return <div className="mkt-empty-state" role="status"><span aria-hidden>⌕</span><h3>{title}</h3><p>{detail}</p></div>;
}

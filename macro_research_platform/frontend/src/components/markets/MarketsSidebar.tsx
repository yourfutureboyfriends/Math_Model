// Sidebar for the Markets mode: every market-wide function by group, the open instrument's
// functions, and recently opened instruments (per browser).
import { useEffect, useState } from 'react';
import { History, Search, ChevronDown, Globe2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FUNCTIONS, findFunction, type MktFunction } from './functions';
import { goMarkets, useMarketsRoute } from '@/lib/marketsRoute';
import { REGIONS, setRegion, useRegion } from '@/lib/region';

const RECENT_KEY = 'mkt_recent';
const GROUPS: MktFunction['group'][] = ['Markets', 'Rates & FX', 'Research', 'My tools'];
// Major economies per region for the sidebar's country shortcuts
const REGION_COUNTRIES: Record<string, [string, string][]> = {
  americas: [['US', 'United States'], ['CA', 'Canada'], ['BR', 'Brazil'], ['MX', 'Mexico'], ['AR', 'Argentina'], ['CL', 'Chile']],
  europe: [['GB', 'United Kingdom'], ['DE', 'Germany'], ['FR', 'France'], ['IT', 'Italy'], ['ES', 'Spain'], ['NL', 'Netherlands'], ['CH', 'Switzerland'], ['SE', 'Sweden'], ['PL', 'Poland'], ['TR', 'Turkey']],
  mea: [['SA', 'Saudi Arabia'], ['AE', 'UAE'], ['IL', 'Israel'], ['QA', 'Qatar'], ['ZA', 'South Africa'], ['EG', 'Egypt'], ['NG', 'Nigeria']],
  apac: [['CN', 'China'], ['JP', 'Japan'], ['IN', 'India'], ['HK', 'Hong Kong'], ['KR', 'South Korea'], ['TW', 'Taiwan'], ['AU', 'Australia'], ['SG', 'Singapore'], ['ID', 'Indonesia'], ['VN', 'Vietnam']],
};

export function MarketsSidebar({ collapsed }: { collapsed?: boolean }) {
  const route = useMarketsRoute();
  const cur = findFunction(route.fn);
  const sym = cur?.security ? route.symbol : undefined;
  const [recent, setRecent] = useState<string[]>(() => { try { const parsed=JSON.parse(localStorage.getItem(RECENT_KEY)||'[]');return Array.isArray(parsed)?parsed.filter((x:unknown):x is string=>typeof x==='string'&&x.length>0&&x.length<40).slice(0,12):[]; } catch { return []; } });
  useEffect(() => {
    if (!sym) return;
    setRecent((r) => {
      const next = [sym, ...r.filter((x) => x !== sym)].slice(0, 12);
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
      return next;
    });
  }, [sym]);
  const [query,setQuery]=useState('');
  const [closed,setClosed]=useState<string[]>(['Countries']);
  const needle=collapsed?'':query.trim().toLowerCase();
  const matches=(...text:string[])=>!needle||text.join(' ').toLowerCase().includes(needle);
  const toggle=(label:string)=>setClosed(s=>s.includes(label)?s.filter(x=>x!==label):[...s,label]);
  const item = (active: boolean) => cn('h-7 flex items-center gap-2 text-xs rounded-md transition-colors',
    collapsed ? 'justify-center px-0 mx-1 w-[calc(100%-0.5rem)]' : 'px-3 mx-2 w-[calc(100%-1rem)]',
    active ? 'bg-bloomberg/10 text-text-primary font-medium' : 'text-text-secondary hover:bg-text-primary/5 hover:text-text-primary');
  const head = (label:string,count?:number) => !collapsed&&<button type="button" className="markets-nav-heading" aria-expanded={!!needle||!closed.includes(label)} onClick={()=>toggle(label)}><span>{label}</span><span>{count!=null&&<b>{count}</b>}<ChevronDown className={cn('w-3 h-3',!needle&&closed.includes(label)&&'-rotate-90')}/></span></button>;
  const region = useRegion();
  const shown = region === 'global'||needle ? ['americas', 'europe', 'mea', 'apac'] : [region];
  return (
    <nav aria-label="Markets functions" className={cn("markets-navigation flex flex-col h-full overflow-y-auto pb-4",collapsed&&"is-collapsed")}>
      {!collapsed&&<div className="markets-nav-brand"><div><Globe2 className="w-4 h-4"/><span>MARKETS<span>RESEARCH DESK</span></span></div><button title="Open world atlas" onClick={()=>goMarkets('MAP')}>ATLAS ↗</button></div>}
      {!collapsed&&<div className="markets-nav-search"><Search className="w-3.5 h-3.5"/><input aria-label="Search Markets navigation" placeholder="Find a function or country…" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Escape')setQuery('');}}/>{query&&<button aria-label="Clear navigation search" onClick={()=>setQuery('')}><X className="w-3 h-3"/></button>}</div>}
      {!collapsed&&cur&&!needle&&<div className="markets-nav-current"><span>{cur.code}</span><div><small>CURRENT WORKSPACE</small><strong>{cur.name}</strong></div></div>}
      {head('Regions',REGIONS.length)}
      {(collapsed||needle||!closed.includes('Regions'))&&<>
      {matches('global','world','atlas')&&<button onClick={()=>{setRegion('global');goMarkets('MAP');}} className={item(cur?.code==='MAP'&&region==='global')} title="Global world atlas"><span className="w-10 shrink-0 font-mono text-[10px] font-semibold text-amber text-left">WORLD</span>{!collapsed&&<span>World atlas</span>}</button>}
      {REGIONS.filter((r) => r.id !== 'global'&&matches(r.id,r.label)).map((r) => (
        <button key={r.id} onClick={() => { setRegion(r.id); goMarkets('RMON'); }} className={item(cur?.code === 'RMON' && region === r.id)} title={`${r.label}: regional monitor`}>
          <span className="w-10 shrink-0 font-mono text-[10px] font-semibold text-amber text-left">{r.id === 'mea' ? 'MEA' : r.id === 'apac' ? 'APAC' : r.id === 'americas' ? 'AMER' : 'EUR'}</span>
          {!collapsed && <span className="truncate">{r.label}</span>}
        </button>))}
      </>}
      {!collapsed && <>
        {head('Countries',shown.flatMap(r=>REGION_COUNTRIES[r]).filter(([iso,name])=>matches(iso,name)).length)}
        {(needle||!closed.includes('Countries'))&&<>
        <div className="mkt-controls px-4 flex flex-wrap gap-1">{shown.flatMap((r) => REGION_COUNTRIES[r]).filter(([iso,name])=>matches(iso,name)).map(([iso, name]) => (
          <button key={iso} onClick={() => goMarkets('CTRY', iso)} title={name}
            className={cn('min-w-[30px] px-1.5 py-0.5 rounded-md text-[10px] font-medium tabular-nums transition-colors', cur?.code === 'CTRY' && route.symbol === iso ? 'bg-bloomberg/15 text-bloomberg ring-1 ring-bloomberg/40' : 'bg-text-primary/[0.04] text-text-secondary hover:bg-text-primary/[0.08] hover:text-text-primary')}>{iso}</button>))}</div>
        </>}
      </>}
      {GROUPS.filter(g=>FUNCTIONS.some(f=>f.group===g&&matches(f.code,f.name,f.desc))).map((g) => (
        <div key={g}>
          {head(g,FUNCTIONS.filter(f=>f.group===g&&matches(f.code,f.name,f.desc)).length)}
          {(collapsed||needle||!closed.includes(g))&&FUNCTIONS.filter((f) => f.group === g&&matches(f.code,f.name,f.desc)).map((f) => (
            <button key={f.code} onClick={() => goMarkets(f.code)} aria-current={cur?.code===f.code?'page':undefined} className={item(cur?.code === f.code)} title={`${f.code} — ${f.desc}`}>
              <span className="w-10 shrink-0 font-mono text-[10px] font-semibold text-bloomberg/90 text-left">{f.code}</span>
              {!collapsed && <span className="truncate">{f.name}</span>}
            </button>))}
        </div>))}
      {!collapsed&&needle&&!FUNCTIONS.some(f=>matches(f.code,f.name,f.desc))&&!shown.flatMap(r=>REGION_COUNTRIES[r]).some(([iso,name])=>matches(iso,name))&&!REGIONS.some(r=>matches(r.id,r.label))&&!matches('global','world','atlas')&&<p className="markets-nav-empty">No matching function or country.</p>}
      {!collapsed && !needle && recent.length > 0 && (
        <div>
          <div className="markets-nav-recent-heading"><History className="w-3 h-3" />Recent instruments</div>
          {recent.map((s) => (
            <button key={s} onClick={() => goMarkets('DES', s)} className={cn(item(sym === s), 'font-mono')}>{s}</button>))}
        </div>
      )}
    </nav>
  );
}

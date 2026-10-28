// Sidebar for the Markets mode: every market-wide function by group, the open instrument's
// functions, and recently opened instruments (per browser).
import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
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
  const [recent, setRecent] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; } });
  useEffect(() => {
    if (!sym) return;
    setRecent((r) => {
      const next = [sym, ...r.filter((x) => x !== sym)].slice(0, 12);
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
      return next;
    });
  }, [sym]);
  const item = (active: boolean) => cn('h-7 flex items-center gap-2 text-xs rounded-md transition-colors',
    collapsed ? 'justify-center px-0 mx-1 w-[calc(100%-0.5rem)]' : 'px-3 mx-2 w-[calc(100%-1rem)]',
    active ? 'bg-bloomberg/10 text-text-primary font-medium' : 'text-text-secondary hover:bg-text-primary/5 hover:text-text-primary');
  const head = (label: string) => !collapsed && <div className="px-5 pt-4 pb-1.5 text-[10px] uppercase tracking-[0.08em] font-semibold text-text-tertiary">{label}</div>;
  const region = useRegion();
  const shown = region === 'global' ? ['americas', 'europe', 'mea', 'apac'] : [region];
  return (
    <nav aria-label="Markets functions" className="flex flex-col h-full overflow-y-auto pb-4">
      {head('Regions')}
      {REGIONS.filter((r) => r.id !== 'global').map((r) => (
        <button key={r.id} onClick={() => { setRegion(r.id); goMarkets('RMON'); }} className={item(cur?.code === 'RMON' && region === r.id)} title={`${r.label}: regional monitor`}>
          <span className="w-10 shrink-0 font-mono text-[10px] font-semibold text-amber text-left">{r.id === 'mea' ? 'MEA' : r.id === 'apac' ? 'APAC' : r.id === 'americas' ? 'AMER' : 'EUR'}</span>
          {!collapsed && <span className="truncate">{r.label}</span>}
        </button>))}
      {!collapsed && <>
        {head(region === 'global' ? 'Countries' : `Countries — ${REGIONS.find((r) => r.id === region)?.label}`)}
        <div className="px-4 flex flex-wrap gap-1">{shown.flatMap((r) => REGION_COUNTRIES[r]).map(([iso, name]) => (
          <button key={iso} onClick={() => goMarkets('CTRY', iso)} title={name}
            className={cn('min-w-[30px] px-1.5 py-0.5 rounded-md text-[10px] font-medium tabular-nums transition-colors', cur?.code === 'CTRY' && route.symbol === iso ? 'bg-bloomberg/15 text-bloomberg ring-1 ring-bloomberg/40' : 'bg-text-primary/[0.04] text-text-secondary hover:bg-text-primary/[0.08] hover:text-text-primary')}>{iso}</button>))}</div>
      </>}
      {GROUPS.map((g) => (
        <div key={g}>
          {head(g)}
          {FUNCTIONS.filter((f) => f.group === g).map((f) => (
            <button key={f.code} onClick={() => goMarkets(f.code)} className={item(cur?.code === f.code)} title={`${f.code} — ${f.desc}`}>
              <span className="w-10 shrink-0 font-mono text-[10px] font-semibold text-bloomberg/90 text-left">{f.code}</span>
              {!collapsed && <span className="truncate">{f.name}</span>}
            </button>))}
        </div>))}
      {!collapsed && recent.length > 0 && (
        <div>
          <div className="px-5 pt-4 pb-1.5 text-[10px] uppercase tracking-[0.08em] font-semibold text-text-tertiary flex items-center gap-1"><History className="w-3 h-3" />Recent instruments</div>
          {recent.map((s) => (
            <button key={s} onClick={() => goMarkets('DES', s)} className={cn(item(sym === s), 'font-mono')}>{s}</button>))}
        </div>
      )}
    </nav>
  );
}

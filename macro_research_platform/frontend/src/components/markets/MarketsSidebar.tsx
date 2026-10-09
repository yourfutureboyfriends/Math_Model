// Sidebar for the Markets mode: every market-wide function by group, the open instrument's
// functions, and recently opened instruments (per browser).
import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FUNCTIONS, findFunction, type MktFunction } from './functions';
import { goMarkets, useMarketsRoute } from '@/pages/MarketsPage';

const RECENT_KEY = 'mkt_recent';
const GROUPS: MktFunction['group'][] = ['Markets', 'Rates & FX', 'Research', 'My tools'];

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
  const item = (active: boolean) => cn('w-full h-7 flex items-center gap-2 text-xs border-l-2 transition-colors',
    collapsed ? 'justify-center px-0' : 'px-4',
    active ? 'bg-bloomberg/10 text-bloomberg border-bloomberg' : 'text-text-secondary border-transparent hover:bg-surface-3 hover:text-text-primary');
  const head = (label: string) => !collapsed && <div className="px-4 pt-3 pb-1 text-[10px] uppercase tracking-wider text-text-tertiary">{label}</div>;
  return (
    <nav aria-label="Markets functions" className="flex flex-col h-full overflow-y-auto pb-4">
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
          <div className="px-4 pt-3 pb-1 text-[10px] uppercase tracking-wider text-text-tertiary flex items-center gap-1"><History className="w-3 h-3" />Recent instruments</div>
          {recent.map((s) => (
            <button key={s} onClick={() => goMarkets('DES', s)} className={cn(item(sym === s), 'font-mono')}>{s}</button>))}
        </div>
      )}
    </nav>
  );
}

// Sidebar for the Markets mode: views, plus instruments opened recently (per browser).
import { useEffect, useState } from 'react';
import { BarChart3, Filter, Globe2, History, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { goMarkets, useMarketsRoute } from '@/pages/MarketsPage';

const VIEWS = [
  { view: 'overview', label: 'World markets', Icon: Globe2 },
  { view: 'movers', label: 'Movers', Icon: TrendingUp },
  { view: 'screener', label: 'Screener', Icon: Filter },
] as const;
const RECENT_KEY = 'mkt_recent';

export function MarketsSidebar({ collapsed }: { collapsed?: boolean }) {
  const route = useMarketsRoute();
  const [recent, setRecent] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; } });
  useEffect(() => {
    if (route.view !== 'ticker' || !route.symbol) return;
    setRecent((r) => {
      const next = [route.symbol!, ...r.filter((x) => x !== route.symbol)].slice(0, 12);
      try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
      return next;
    });
  }, [route.view, route.symbol]);
  const item = (active: boolean) => cn('w-full h-7 flex items-center gap-2 text-xs border-l-2 transition-colors',
    collapsed ? 'justify-center px-0' : 'px-4',
    active ? 'bg-bloomberg-muted text-bloomberg border-bloomberg' : 'text-text-secondary border-transparent hover:bg-surface-3 hover:text-text-primary');
  return (
    <nav aria-label="Markets" className="flex flex-col h-full overflow-y-auto py-2">
      {!collapsed && <div className="px-4 pb-1 text-[10px] uppercase tracking-wider text-text-tertiary">Markets</div>}
      {VIEWS.map(({ view, label, Icon }) => (
        <button key={view} onClick={() => goMarkets({ view })} className={item(route.view === view)} title={label}>
          <Icon className="w-3.5 h-3.5 shrink-0" />{!collapsed && label}
        </button>
      ))}
      {route.view === 'ticker' && route.symbol && (
        <div className={item(true)}><BarChart3 className="w-3.5 h-3.5 shrink-0" />{!collapsed && <span className="font-mono truncate">{route.symbol}</span>}</div>
      )}
      {!collapsed && recent.length > 0 && (
        <>
          <div className="px-4 pt-4 pb-1 text-[10px] uppercase tracking-wider text-text-tertiary flex items-center gap-1"><History className="w-3 h-3" />Recent</div>
          {recent.map((s) => (
            <button key={s} onClick={() => goMarkets({ view: 'ticker', symbol: s })}
              className={cn(item(route.view === 'ticker' && route.symbol === s), 'font-mono')}>{s}</button>
          ))}
        </>
      )}
    </nav>
  );
}

// Markets mode — universal market workstation. Routes live in the URL hash so any view can
// be linked or bookmarked: #mkt/overview · #mkt/ticker/7203.T · #mkt/movers · #mkt/screener
import { useCallback, useEffect, useState } from 'react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { SymbolSearch } from '@/components/markets/SymbolSearch';
import { OverviewView } from '@/components/markets/OverviewView';
import { TickerView } from '@/components/markets/TickerView';
import { MoversView, ScreenerView } from '@/components/markets/ScreenerView';

export type MarketsRoute = { view: 'overview' | 'ticker' | 'movers' | 'screener'; symbol?: string };

export function parseMarketsHash(h = window.location.hash): MarketsRoute {
  const parts = h.replace(/^#mkt\/?/, '').split('/').filter(Boolean);
  const v = parts[0] as MarketsRoute['view'];
  if (v === 'ticker' && parts[1]) return { view: 'ticker', symbol: decodeURIComponent(parts[1]).toUpperCase() };
  if (v === 'movers' || v === 'screener') return { view: v };
  return { view: 'overview' };
}

export function goMarkets(r: MarketsRoute) {
  window.location.hash = r.view === 'ticker' && r.symbol ? `#mkt/ticker/${encodeURIComponent(r.symbol)}` : `#mkt/${r.view}`;
}

export function useMarketsRoute(): MarketsRoute {
  const [r, setR] = useState<MarketsRoute>(() => parseMarketsHash());
  useEffect(() => {
    const h = () => setR(parseMarketsHash());
    window.addEventListener('hashchange', h);
    return () => window.removeEventListener('hashchange', h);
  }, []);
  return r;
}

export function MarketsPage() {
  const route = useMarketsRoute();
  const open = useCallback((s: string) => { goMarkets({ view: 'ticker', symbol: s }); window.scrollTo({ top: 0 }); }, []);
  useEffect(() => {
    if (!window.location.hash.startsWith('#mkt')) goMarkets({ view: 'overview' });
  }, []);
  return (
    <div className="p-4 space-y-4 max-w-[1600px]">
      <SymbolSearch onPick={open} autoFocus={route.view !== 'ticker'} />
      <ErrorBoundary sectionName={`Markets · ${route.view}`} key={`${route.view}:${route.symbol ?? ''}`}>
        {route.view === 'overview' && <OverviewView onOpen={open} />}
        {route.view === 'ticker' && route.symbol && <TickerView symbol={route.symbol} />}
        {route.view === 'movers' && <MoversView onOpen={open} />}
        {route.view === 'screener' && <ScreenerView onOpen={open} />}
      </ErrorBoundary>
    </div>
  );
}

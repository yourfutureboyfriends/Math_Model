// Markets-mode routing (#mkt/<function>/<symbol>): small on purpose — the sidebar and links use it without loading
// the Markets page itself (which is code-split and loaded only when Markets mode opens).
import { useEffect, useState } from 'react';
import { findFunction } from '@/components/markets/functions';

export type MarketsRoute = { fn: string; symbol?: string };

export function parseMarketsHash(h = window.location.hash): MarketsRoute {
  const parts = h.replace(/^#mkt\/?/, '').split('/').filter(Boolean);
  // legacy routes from the first version
  const legacy: Record<string, string> = { overview: 'WEI', ticker: 'DES', movers: 'MOST', screener: 'EQS' };
  const raw = (parts[0] ?? 'wei').toUpperCase();
  const f = findFunction(legacy[raw.toLowerCase()] ?? raw);
  const code = f?.code ?? 'WEI';
  const symbol = parts[1] ? decodeURIComponent(parts[1]).toUpperCase() : undefined;
  if (f?.security && !symbol) return { fn: 'WEI' };
  return { fn: code, symbol };
}

export function goMarkets(fn: string, symbol?: string) {
  const f = findFunction(fn);
  const code = (f?.code ?? 'WEI').toLowerCase();
  window.location.hash = f?.security && symbol ? `#mkt/${code}/${encodeURIComponent(symbol)}` : `#mkt/${code}${symbol && !f?.security ? `/${encodeURIComponent(symbol)}` : ''}`;
  window.scrollTo({ top: 0 });
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


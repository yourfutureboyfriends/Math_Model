// Click-to-chart: any panel can open the full interactive PriceChart for an instrument by
// calling openChart(symbol, title). One modal for the whole terminal; Esc or the backdrop
// closes it. Symbols are Yahoo tickers (AAPL, EURUSD=X, GC=F, ^GSPC, 7203.T …).

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { PriceChart } from './PriceChart';

const EVENT = 'open-chart';

export function openChart(symbol: string, title?: string) {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { symbol, title } }));
}

/** Yahoo ticker for an FX pair written 'EUR/USD' or 'EURUSD'. */
export function fxTicker(pair: string): string {
  return `${pair.replace('/', '').toUpperCase()}=X`;
}

export function ChartModal() {
  const [open, setOpen] = useState<{ symbol: string; title?: string } | null>(null);
  useEffect(() => {
    const on = (e: Event) => setOpen((e as CustomEvent).detail);
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(null); };
    window.addEventListener(EVENT, on);
    window.addEventListener('keydown', key);
    return () => { window.removeEventListener(EVENT, on); window.removeEventListener('keydown', key); };
  }, []);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4" onClick={() => setOpen(null)}
      role="dialog" aria-modal="true" aria-label={`${open.title ?? open.symbol} chart`}>
      <div className="w-full max-w-5xl bg-surface-1 border border-border shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
          <span className="font-mono text-sm text-text-primary">{open.symbol}</span>
          {open.title && open.title !== open.symbol && <span className="text-xs text-text-secondary">{open.title}</span>}
          <button onClick={() => setOpen(null)} className="ml-auto p-1 text-text-tertiary hover:text-text-primary" aria-label="Close chart">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-3">
          <PriceChart key={open.symbol} symbol={open.symbol} height={420} />
        </div>
      </div>
    </div>
  );
}

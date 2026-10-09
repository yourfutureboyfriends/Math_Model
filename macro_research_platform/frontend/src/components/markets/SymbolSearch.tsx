// Universal instrument search: any stock (any exchange), ETF, fund, index, currency, future
// or crypto. Arrow keys + Enter; typing an exact symbol and pressing Enter opens it directly.
import { useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { TYPE_COLOR } from './shared';

interface Hit { symbol: string; name: string; type: string; exchange?: string; sector?: string }

export function SymbolSearch({ onPick, autoFocus, placeholder = 'Search any stock, ETF, index, FX pair, future or crypto — e.g. toyota, gold, EURUSD, bitcoin' }:
  { onPick: (symbol: string) => void; autoFocus?: boolean; placeholder?: string }) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = q.trim();
    if (!t) { setHits([]); return; }
    setBusy(true);
    const id = setTimeout(() => {
      fetch(`/api/v1/mkt/search?q=${encodeURIComponent(t)}&limit=12`).then((r) => (r.ok ? r.json() : { results: [] }))
        .then((j) => { setHits(j.results ?? []); setIdx(0); setOpen(true); }).catch(() => setHits([])).finally(() => setBusy(false));
    }, 250);
    return () => clearTimeout(id);
  }, [q]);

  useEffect(() => {
    const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const pick = (s: string) => { onPick(s); setQ(''); setHits([]); setOpen(false); };

  return (
    <div ref={box} className="relative w-full">
      <div className="flex items-center gap-2 px-3 h-9 bg-surface-1 border border-border focus-within:border-bloomberg">
        <Search className="w-3.5 h-3.5 text-text-tertiary shrink-0" />
        <input value={q} autoFocus={autoFocus} placeholder={placeholder} spellCheck={false}
          aria-label="Search instruments" role="combobox" aria-expanded={open} aria-controls="mkt-search-list"
          onChange={(e) => setQ(e.target.value)} onFocus={() => hits.length && setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, hits.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            else if (e.key === 'Escape') setOpen(false);
            else if (e.key === 'Enter') {
              const exact = hits.find((h) => h.symbol.toUpperCase() === q.trim().toUpperCase());
              if (exact || !hits.length) pick((exact?.symbol ?? q.trim()).toUpperCase());
              else pick(hits[idx].symbol);
            }
          }}
          className="flex-1 bg-transparent text-xs font-mono text-text-primary placeholder:text-text-tertiary outline-none" />
        {busy && <span className="text-[10px] text-text-tertiary">searching…</span>}
      </div>
      {open && hits.length > 0 && (
        <ul id="mkt-search-list" role="listbox" className="absolute z-40 left-0 right-0 mt-1 max-h-96 overflow-y-auto bg-surface-2 border border-border shadow-xl">
          {hits.map((h, i) => (
            <li key={h.symbol} role="option" aria-selected={i === idx}>
              <button type="button" onMouseEnter={() => setIdx(i)} onClick={() => pick(h.symbol)}
                className={cn('w-full grid grid-cols-[7rem_1fr_auto] gap-3 items-center px-3 py-1.5 text-left text-2xs', i === idx ? 'bg-surface-3' : '')}>
                <span className="font-mono text-text-primary truncate">{h.symbol}</span>
                <span className="text-text-secondary truncate">{h.name}{h.sector ? <span className="text-text-tertiary"> · {h.sector}</span> : null}</span>
                <span className="text-right whitespace-nowrap"><span className={cn('font-mono', TYPE_COLOR[h.type] ?? 'text-text-tertiary')}>{h.type}</span>
                  {h.exchange && <span className="text-text-tertiary"> · {h.exchange}</span>}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

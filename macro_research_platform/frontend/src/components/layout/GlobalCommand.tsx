// The Research-mode <GO> line in the topbar (Markets mode has its own, larger command line on the page; both use
// lib/commands). Press "/" anywhere to focus it, type a panel, a model ("EA MODEL"), a fund, an action or any
// security / Markets function ("AAPL DES", "ECO"), then Enter. Arrow keys move through the suggestions; company
// names are searched as you type.
import { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft } from 'lucide-react';
import { goMarkets } from '@/lib/marketsRoute';
import { resolveCommands, type Command, type FundRef } from '@/lib/commands';
import { loadFunds } from '@/lib/fundBrand';
import { cn } from '@/lib/utils';

const GROUP_TAG: Record<Command['group'], string> = { Model: 'MODEL', Panel: 'PANEL', Fund: 'FUND', Action: 'ACTION', Markets: 'FUNC', Security: 'SEC' };

export function GlobalCommand() {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [funds, setFunds] = useState<FundRef[]>([]);
  const [hits, setHits] = useState<{ symbol: string; name: string; type?: string; exchange?: string }[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => { loadFunds().then((fs) => setFunds(fs.map((f) => ({ id: f.id, name: f.name })))).catch(() => { /* optional */ }); }, []);

  // "/" focuses the command line (not while typing elsewhere)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
      if (e.key === '/' && !typing) { e.preventDefault(); input.current?.focus(); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  // company-name search for longer words (tickers resolve without it)
  useEffect(() => {
    const t = q.trim();
    if (t.length < 3 || /\s/.test(t) && t.split(/\s+/).length > 3) { setHits([]); return; }
    let stale = false;
    const id = setTimeout(() => {
      fetch(`/api/v1/mkt/search?q=${encodeURIComponent(t)}&limit=5`).then((r) => (r.ok ? r.json() : { results: [] }))
        .then((j) => { if (!stale) setHits(j.results ?? []); }).catch(() => { if (!stale) setHits([]); });
    }, 250);
    return () => { stale = true; clearTimeout(id); };
  }, [q]);

  const options: Command[] = useMemo(() => {
    const base = resolveCommands(q, funds);
    const have = new Set(base.map((c) => c.key));
    const extra = hits.filter((h) => !have.has(`sec:${h.symbol.toUpperCase()}:DES`)).map((h, i): Command => ({
      key: `hit:${h.symbol}`, group: 'Security', label: `${h.symbol} — ${h.name}`, hint: [h.type, h.exchange].filter(Boolean).join(' · '),
      score: 30 - i, run: () => goMarkets('DES', h.symbol) }));
    return [...base, ...extra].sort((a, b) => b.score - a.score).slice(0, 9);
  }, [q, funds, hits]);
  useEffect(() => { setIdx(0); }, [q]);

  const run = (c?: Command) => {
    if (!c) return;
    setQ(''); setOpen(false); setHits([]); input.current?.blur();
    c.run();
  };

  return (
    <div ref={box} className="relative hidden md:block shrink-0">
      <div className="gcmd">
        <span className="gcmd-go">GO</span>
        <input ref={input} value={q} spellCheck={false} autoComplete="off" role="combobox" aria-expanded={open && options.length > 0}
          aria-controls="gcmd-list" aria-label="Command: panel, model, fund, function or security"
          placeholder="Panel · EA MODEL · AAPL DES · ECO   /"
          onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, options.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            else if (e.key === 'Escape') { setOpen(false); input.current?.blur(); }
            else if (e.key === 'Enter') { e.preventDefault(); run(options[idx]); }
          }} />
        <CornerDownLeft className="w-3 h-3 text-text-tertiary shrink-0" aria-hidden />
      </div>
      {open && q.trim() && options.length > 0 && (
        <ul id="gcmd-list" role="listbox" className="gcmd-list">
          {options.map((c, i) => (
            <li key={c.key} role="option" aria-selected={i === idx}>
              <button type="button" onMouseEnter={() => setIdx(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => run(c)}
                className={cn('gcmd-item', i === idx && 'is-active')}>
                <span className="gcmd-tag">{GROUP_TAG[c.group]}</span>
                <span className="flex-1 min-w-0 truncate text-text-primary">{c.label}</span>
                {c.hint && <span className="text-[10px] text-text-tertiary truncate max-w-[45%]">{c.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Bloomberg-style command line with friendly autocomplete. Type a ticker, a company name, a
// function, or both: "AAPL DES", "toyota", "7203.T FA", "WEI", "EURUSD=X GP". Enter = <GO>.
import { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import { FUNCTIONS, MARKET_FUNCTIONS, parseCommand, SECURITY_FUNCTIONS, type MktFunction } from './functions';
import { TYPE_COLOR } from './shared';

interface Hit { symbol: string; name: string; type: string; exchange?: string; sector?: string }
type Option = { kind: 'fn'; fn: MktFunction; symbol?: string } | { kind: 'sym'; hit: Hit; fn?: MktFunction };

export function CommandLine({ current, onGo }: { current?: string; onGo: (fn: string, symbol?: string) => void }) {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  const [hint, setHint] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const parsed = useMemo(() => parseCommand(q), [q]);

  // "/" or Ctrl/Cmd+K focuses the command line from anywhere in Markets.
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
      if ((e.key === '/' && !typing) || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  // Instrument suggestions for the non-function part of what's typed.
  const symText = parsed.symbol ?? '';
  useEffect(() => {
    const t = q.trim().split(/\s+/).filter((w) => !parsed.fn || w.toUpperCase() !== parsed.fn.code).join(' ');
    if (!t || t.length < 1) { setHits([]); return; }
    const id = setTimeout(() => {
      fetch(`/api/v1/mkt/search?q=${encodeURIComponent(t)}&limit=8`).then((r) => (r.ok ? r.json() : { results: [] }))
        .then((j) => setHits(j.results ?? [])).catch(() => setHits([]));
    }, 220);
    return () => clearTimeout(id);
  }, [q, parsed.fn, symText]);

  const options: Option[] = useMemo(() => {
    const words = q.trim().toUpperCase().split(/\s+/).filter(Boolean);
    const last = words[words.length - 1] ?? '';
    const fnMatches = !q.trim() ? [] : FUNCTIONS.filter((f) =>
      (f.code.startsWith(last) || f.name.toUpperCase().includes(q.trim().toUpperCase()) || (f.aliases ?? []).some((a) => a === last)) &&
      (!f.security || parsed.symbol || current)).slice(0, 5);
    const symMatches = hits.map((h) => ({ kind: 'sym' as const, hit: h, fn: parsed.fn }));
    const fnOpts = fnMatches.map((f) => ({ kind: 'fn' as const, fn: f, symbol: f.security ? (parsed.symbol && parsed.fn ? parsed.symbol : current) : undefined }));
    return parsed.fn && !parsed.symbol ? [...fnOpts, ...symMatches] : [...symMatches, ...fnOpts];
  }, [q, hits, parsed, current]);

  useEffect(() => { setIdx(0); }, [options.length]);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  const done = () => { setQ(''); setHits([]); setOpen(false); setHint(null); input.current?.blur(); };
  const pick = (o: Option) => {
    if (o.kind === 'fn') {
      if (o.fn.security && !o.symbol) { setHint(`${o.fn.code} needs an instrument — type a ticker first, e.g. "AAPL ${o.fn.code}".`); return; }
      onGo(o.fn.code, o.symbol);
    } else {
      onGo(o.fn?.security ? o.fn.code : 'DES', o.hit.symbol);
    }
    done();
  };
  const go = () => {
    // a menu number picks from the numbered menu on screen (security functions, or the market menu)
    const num = /^\s*(\d{1,2})\s*$/.exec(q);
    if (num) {
      const menu = current ? SECURITY_FUNCTIONS : MARKET_FUNCTIONS;
      const f = menu[Number(num[1]) - 1];
      if (!f) { setHint(`No menu item ${num[1]} — the menu has 1–${menu.length}.`); return; }
      onGo(f.code, f.security ? current : undefined); return done();
    }
    if (parsed.terminal && parsed.symbol) { onGo(parsed.fn?.code ?? 'DES', parsed.symbol); return done(); }
    const opt = options[idx];
    const exactSym = hits.find((h) => h.symbol.toUpperCase() === parsed.symbol);
    if (parsed.fn && !parsed.fn.security) { onGo(parsed.fn.code); return done(); }
    if (parsed.fn && parsed.fn.security) {
      const sym = parsed.symbol ?? current;
      if (!sym) { setHint(`${parsed.fn.code} needs an instrument — e.g. "AAPL ${parsed.fn.code}".`); return; }
      onGo(parsed.fn.code, exactSym?.symbol ?? sym); return done();
    }
    if (exactSym) { onGo('DES', exactSym.symbol); return done(); }
    if (opt) return pick(opt);
    if (parsed.symbol) { onGo('DES', parsed.symbol); return done(); }
  };

  return (
    <div ref={box} className="relative w-full">
      <div className="flex items-center gap-2 px-3 h-10 bg-surface-1 border border-border focus-within:border-bloomberg shadow-sm">
        <Search className="w-4 h-4 text-text-tertiary shrink-0" />
        <input ref={input} value={q} spellCheck={false} autoComplete="off"
          placeholder={current ? `Function for ${current} (FA, OMON) or a menu number — or any security: VOD LN Equity, SPX Index, EURUSD Curncy`
            : 'Security + function <GO>: AAPL US Equity DES · SPX Index GP · EURUSD Curncy · CL1 Comdty · or a name, e.g. toyota'}
          aria-label="Command line: instrument or function" role="combobox" aria-expanded={open} aria-controls="mkt-cmd-list"
          onChange={(e) => { setQ(e.target.value); setOpen(true); setHint(null); }} onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, options.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
            else if (e.key === 'Escape') { setOpen(false); input.current?.blur(); }
            else if (e.key === 'Enter') { e.preventDefault(); go(); }
          }}
          className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary outline-none" />
        <kbd className="hidden sm:inline-flex items-center gap-1 text-[10px] font-mono text-text-tertiary border border-border px-1.5 py-0.5">
          <CornerDownLeft className="w-3 h-3" />GO</kbd>
        <kbd className="hidden md:inline text-[10px] font-mono text-text-tertiary border border-border px-1.5 py-0.5" title="Focus the command line">/</kbd>
      </div>
      {hint && <div className="mt-1 text-2xs text-amber">{hint}</div>}
      {open && q.trim() && options.length > 0 && (
        <ul id="mkt-cmd-list" role="listbox" className="absolute z-40 left-0 right-0 mt-1 max-h-[26rem] overflow-y-auto bg-surface-1 border border-border shadow-xl">
          {options.map((o, i) => (
            <li key={o.kind === 'fn' ? `f:${o.fn.code}` : `s:${o.hit.symbol}`} role="option" aria-selected={i === idx}>
              <button type="button" onMouseEnter={() => setIdx(i)} onClick={() => pick(o)}
                className={cn('w-full flex items-center gap-3 px-3 py-2 text-left', i === idx ? 'bg-surface-3' : '')}>
                {o.kind === 'fn' ? (
                  <>
                    <span className="w-14 shrink-0 text-center text-[11px] font-mono font-semibold text-bloomberg border border-bloomberg/40 py-0.5">{o.fn.code}</span>
                    <span className="min-w-0">
                      <span className="block text-xs text-text-primary">{o.fn.name}{o.symbol ? <span className="text-text-tertiary"> · {o.symbol}</span> : null}</span>
                      <span className="block text-2xs text-text-tertiary truncate">{o.fn.desc}</span>
                    </span>
                  </>
                ) : (
                  <>
                    <span className="w-24 shrink-0 font-mono text-xs text-text-primary truncate">{o.hit.symbol}</span>
                    <span className="flex-1 min-w-0 text-xs text-text-secondary truncate">{o.hit.name}{o.hit.sector ? <span className="text-text-tertiary"> · {o.hit.sector}</span> : null}</span>
                    <span className="shrink-0 text-2xs"><span className={cn('font-mono', TYPE_COLOR[o.hit.type] ?? 'text-text-tertiary')}>{o.hit.type}</span>
                      {o.hit.exchange && <span className="text-text-tertiary"> · {o.hit.exchange}</span>}
                      {o.fn && <span className="ml-2 font-mono text-bloomberg">{o.fn.code}</span>}</span>
                  </>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

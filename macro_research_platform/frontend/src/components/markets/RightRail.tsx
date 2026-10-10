// Brokerage-style right rail: a live watchlist and the AI research assistant, always at hand.
// Collapsible; the open tab and state are remembered per browser.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Bot, ChevronRight, List, Loader2, Send, Sparkles, Wrench } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fmtPrice, Spark, apiError } from './shared';

const KEY = 'mkt_rail';

export function RightRail({ symbol, onOpen }: { symbol?: string; onOpen: (s: string) => void }) {
  const [state, setState] = useState<{ open: boolean; tab: 'watch' | 'ai' }>(() => {
    try { return JSON.parse(localStorage.getItem(KEY) || '') ?? { open: true, tab: 'watch' }; } catch { return { open: true, tab: 'watch' }; }
  });
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* storage unavailable */ } }, [state]);
  if (!state.open) {
    return (
      <div className="hidden xl:flex flex-col gap-2 pt-1">
        <button onClick={() => setState({ open: true, tab: 'watch' })} title="Watchlist" className="p-2 rounded-md border border-border bg-surface-1 hover:border-bloomberg"><List className="w-4 h-4" /></button>
        <button onClick={() => setState({ open: true, tab: 'ai' })} title="AI assistant" className="p-2 rounded-md border border-border bg-surface-1 hover:border-bloomberg"><Sparkles className="w-4 h-4 text-bloomberg" /></button>
      </div>
    );
  }
  return (
    <aside className="hidden xl:flex flex-col w-[320px] shrink-0 bg-surface-1 border border-border rounded-md sticky top-[calc(var(--topbar-height)+12px)] h-[calc(100vh-var(--topbar-height)-24px)] overflow-hidden">
      <div className="flex items-center border-b border-border">
        {([['watch', 'Watchlist', List], ['ai', 'AI assistant', Sparkles]] as const).map(([k, l, Icon]) => (
          <button key={k} onClick={() => setState({ ...state, tab: k })} className={cn('flex-1 inline-flex items-center justify-center gap-1.5 py-2.5 text-xs border-b-2 -mb-px',
            state.tab === k ? 'border-bloomberg text-text-primary font-semibold' : 'border-transparent text-text-tertiary hover:text-text-primary')}>
            <Icon className={cn('w-3.5 h-3.5', k === 'ai' && 'text-bloomberg')} />{l}</button>))}
        <button onClick={() => setState({ ...state, open: false })} aria-label="Hide panel" className="px-2 text-text-tertiary hover:text-text-primary"><ChevronRight className="w-4 h-4" /></button>
      </div>
      <div className="flex-1 min-h-0">{state.tab === 'watch' ? <RailWatchlist current={symbol} onOpen={onOpen} /> : <AiChat context={symbol} compact />}</div>
    </aside>
  );
}

function RailWatchlist({ current, onOpen }: { current?: string; onOpen: (s: string) => void }) {
  const [lists, setLists] = useState<any[]>([]);
  const [idx, setIdx] = useState(0);
  const [quotes, setQuotes] = useState<Record<string, any>>({});
  const load = useCallback(() => fetch('/api/v1/mkt/watchlists').then((r) => r.json()).then((j) => setLists(j.watchlists ?? [])).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 120_000); return () => clearInterval(t); }, [load]);
  const list = lists[Math.min(idx, lists.length - 1)];
  useEffect(() => {
    if (!list?.symbols?.length) return;
    let live = true;
    const get = () => fetch(`/api/v1/mkt/quotes?symbols=${encodeURIComponent(list.symbols.join(','))}`).then((r) => r.json())
      .then((j) => live && setQuotes(Object.fromEntries((j.quotes ?? []).map((q: any) => [q.symbol, q])))).catch(() => {});
    get();
    const t = setInterval(() => document.visibilityState === 'visible' && get(), 60_000);
    return () => { live = false; clearInterval(t); };
  }, [list?.id, list?.symbols?.join(',')]);
  if (!list) return <div className="p-4 text-xs text-text-tertiary">Loading…</div>;
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 flex items-center gap-2">
        <select value={idx} onChange={(e) => setIdx(Number(e.target.value))} className="flex-1 bg-surface-2 border border-border rounded px-2 py-1 text-xs text-text-primary">
          {lists.map((l, i) => <option key={l.id} value={i}>{l.name} ({l.symbols.length})</option>)}</select>
        <button onClick={() => { window.location.hash = '#mkt/w'; }} className="text-[10px] text-bloomberg hover:underline">Edit</button>
      </div>
      <ul className="flex-1 overflow-y-auto">
        {list.symbols.map((s: string) => { const q = quotes[s]; return (
          <li key={s}><button onClick={() => onOpen(s)} className={cn('w-full grid grid-cols-[1fr_auto] gap-x-2 px-3 py-2 text-left border-l-2 hover:bg-surface-2',
            s === current ? 'border-bloomberg bg-surface-2' : 'border-transparent')}>
            <span className="font-mono text-xs font-semibold text-text-primary truncate">{s}</span>
            <span className="font-mono text-xs text-right text-text-primary">{q ? fmtPrice(q.price) : '…'}</span>
            <span className="opacity-80"><Spark values={q?.spark} w={70} h={16} /></span>
            <span className={cn('text-right text-[11px] font-mono px-1.5 rounded self-center', q?.change_1d == null ? 'text-text-tertiary' : q.change_1d >= 0 ? 'bg-green/15 text-green' : 'bg-red/15 text-red')}>
              {q?.change_1d == null ? '—' : `${q.change_1d >= 0 ? '+' : ''}${(q.change_1d * 100).toFixed(2)}%`}</span>
          </button></li>); })}
        {!list.symbols.length && <li className="p-4 text-xs text-text-tertiary">Empty — add symbols with “+ Watch” on any instrument.</li>}
      </ul>
    </div>
  );
}

type Turn = { role: 'user' | 'assistant'; content: string; tools?: { name: string; args: any; ok: boolean }[]; meta?: string };
const TOOL_LABEL: Record<string, string> = { search_instrument: 'Searched instruments', get_quote: 'Quote', get_profile: 'Profile', get_financials: 'Financials',
  get_earnings: 'Earnings', get_analyst_ratings: 'Analyst ratings', get_holders: 'Holders', get_news: 'News', run_dcf: 'DCF', get_peers: 'Peers',
  get_movers: 'Movers', screen_stocks: 'Screener', get_market_overview: 'World markets', get_macro_view: 'Macro model' };
const SUGGEST = (s?: string) => s ? [`Summarise ${s}: business, valuation vs peers and next earnings`, `What does the price of ${s} imply about growth? Run a DCF.`,
  `Any notable analyst or insider activity on ${s}?`] : ['What moved world markets today?', 'Which sectors does the macro model favour right now?', 'Screen for large-cap Japanese stocks with P/E under 12'];

/** Renders **bold** and line breaks safely (no HTML from the model). */
function Rich({ text }: { text: string }) {
  return <>{text.split('\n').map((line, i) => (
    <p key={i} className={cn(line.trim().startsWith('- ') || line.trim().startsWith('* ') ? 'pl-3 -indent-3' : '', 'min-h-[0.5em]')}>
      {line.replace(/^\s*[-*] /, '• ').split(/(\*\*[^*]+\*\*)/g).map((part, j) => part.startsWith('**') && part.endsWith('**')
        ? <strong key={j} className="text-text-primary">{part.slice(2, -2)}</strong> : <span key={j}>{part}</span>)}</p>))}</>;
}

export function AiChat({ context, compact }: { context?: string; compact?: boolean }) {
  const [status, setStatus] = useState<any>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [deep, setDeep] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { fetch('/api/v1/ai/status').then((r) => r.json()).then(setStatus).catch(() => setStatus({ available: false, note: 'Assistant unavailable.' })); }, []);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [turns, busy]);
  useEffect(() => { if (!busy) return; const t0 = Date.now(); const t = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000); return () => clearInterval(t); }, [busy]);
  // Deep mode = a larger *local* model. On Groq the default is already the strongest available model.
  const deepModel = status?.provider !== 'ollama' ? undefined
    : status?.models?.find((m: string) => m.startsWith('qwen3.5')) ?? status?.models?.find((m: string) => m !== status?.model);
  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    const next: Turn[] = [...turns, { role: 'user', content: q }];
    setTurns(next); setInput(''); setBusy(true); setElapsed(0);
    try {
      const r = await fetch('/api/v1/ai/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: next.map(({ role, content }) => ({ role, content })), context, model: deep ? deepModel : undefined }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(apiError(j, r.status));
      setTurns([...next, { role: 'assistant', content: j.reply, tools: j.tool_calls, meta: `${j.model} · ${j.seconds}s` }]);
    } catch (e: any) {
      setTurns([...next, { role: 'assistant', content: `⚠ ${e.message}` }]);
    } finally { setBusy(false); }
  };
  if (status && !status.available) {
    return (
      <div className="p-4 space-y-2 text-xs text-text-secondary">
        <div className="flex items-center gap-2 text-text-primary font-semibold"><Bot className="w-4 h-4" />AI assistant is not set up</div>
        <p>{status.note}</p>
        <p className="text-text-tertiary">Free options: open the <b>Ollama</b> app (local models, nothing leaves your Mac), or add a free <b>GROQ_API_KEY</b> to the server's .env.</p>
      </div>
    );
  }
  return (
    <div className="flex flex-col h-full">
      <div className={cn('flex-1 overflow-y-auto space-y-3', compact ? 'p-3' : 'p-4')}>
        {turns.length === 0 && (
          <div className="space-y-2">
            <div className="text-xs text-text-secondary">Ask about any company, market or the economy — answers come from the terminal’s data{context ? <>, focused on <b className="text-text-primary">{context}</b></> : ''}.</div>
            {SUGGEST(context).map((s) => <button key={s} onClick={() => send(s)} className="block w-full text-left text-xs px-3 py-2 rounded-md border border-border hover:border-bloomberg/60 hover:bg-surface-2 text-text-secondary">{s}</button>)}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={cn('text-xs leading-relaxed', t.role === 'user' ? 'ml-6 px-3 py-2 rounded-lg bg-bloomberg/10 text-text-primary' : 'text-text-secondary space-y-1')}>
            {t.role === 'assistant' && t.tools && t.tools.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-1">{t.tools.map((c, k) => (
                <span key={k} className={cn('inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] border', c.ok ? 'border-border text-text-tertiary' : 'border-red/40 text-red')}
                  title={JSON.stringify(c.args)}><Wrench className="w-2.5 h-2.5" />{TOOL_LABEL[c.name] ?? c.name}{c.args?.symbol ? ` ${c.args.symbol}` : ''}</span>))}</div>)}
            {t.role === 'assistant' ? <Rich text={t.content} /> : t.content}
            {t.meta && <div className="text-[10px] text-text-tertiary">{t.meta}</div>}
          </div>))}
        {busy && <div className="flex items-center gap-2 text-xs text-text-tertiary"><Loader2 className="w-3.5 h-3.5 animate-spin" />Researching… {elapsed}s
          {status?.provider === 'ollama' && <span>(local model — {deep ? 'deep mode can take a few minutes' : 'about 20–60 s'})</span>}</div>}
        <div ref={end} />
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="border-t border-border p-2 space-y-1.5">
        <div className="flex gap-2">
          <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={2} placeholder={context ? `Ask about ${context}…` : 'Ask about markets…'}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }}
            className="flex-1 resize-none bg-surface-2 border border-border rounded-md px-2 py-1.5 text-xs text-text-primary outline-none focus:border-bloomberg" />
          <button disabled={busy || !input.trim()} aria-label="Send" className="self-end p-2 rounded-md bg-bloomberg text-white disabled:opacity-40"><Send className="w-3.5 h-3.5" /></button>
        </div>
        <div className="flex items-center justify-between text-[10px] text-text-tertiary">
          <span>{status ? `${status.provider === 'ollama' ? 'Local' : status.provider} · ${deep && deepModel ? deepModel : status.model}` : '…'}</span>
          {deepModel && <label className="inline-flex items-center gap-1 cursor-pointer" title="A larger local model: better reasoning, much slower">
            <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} />Deep mode</label>}
          {turns.length > 0 && <button type="button" onClick={() => setTurns([])} className="hover:text-text-primary">Clear</button>}
        </div>
      </form>
    </div>
  );
}

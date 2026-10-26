// Live pop-ups: toasts in the bottom-right corner (above the ticker tape) that make the screen feel alive —
//   Headlines          new stories on the news wire (RSS: Bloomberg, FT, Nikkei Asia, …), every 2 minutes
//   Market moves       a world index, FX rate, commodity, yield or coin crossing a big-day threshold (shared feed)
//   Economic releases  high-impact releases worldwide: 15 minutes before, then the actual against consensus
//   Regime changes     the US / euro-area / rest-of-world macro model switching its most likely regime
// Each toast auto-dismisses after 12 s (hover pauses it); a click opens the story, chart or panel. Everything shown
// is also kept in the history (status bar → ALERTS), where pop-ups can be muted by kind. Nothing here is a trading
// signal: the thresholds only decide what is worth a glance.
import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { openChart } from '@/components/ui/ChartModal';
import { goMarkets } from '@/lib/marketsRoute';
import { getHubMode, setHubMode } from '@/lib/hubMode';
import { fmtPulseChange, SHORT, useMarketPulse, type PulseRow } from '@/lib/marketPulse';
import { dismissPopup, KIND_LABEL, pushPopup, seenBefore, setKindEnabled, setPopupsEnabled, togglePanel, usePopups,
  type Popup, type PopupKind } from '@/lib/popups';
import { cn } from '@/lib/utils';

const NEWS_MS = 120_000, ECO_MS = 300_000, REGIME_MS = 30 * 60_000, LIFE_MS = 12_000;

// ── Sources ────────────────────────────────────────────────────────────────────────────────────────────────────
/** Day-move threshold for an instrument (a "big day" for its asset class). */
function threshold(r: PulseRow): { v: number; unit: 'pct' | 'bp' } {
  const s = r.symbol;
  if (r.is_yield) return { v: 8, unit: 'bp' };
  if (s === '^VIX' || s === '^MOVE') return { v: 0.1, unit: 'pct' };
  if (s.endsWith('=X') || s === 'DX-Y.NYB') return { v: 0.008, unit: 'pct' };
  if (s.endsWith('-USD')) return { v: 0.05, unit: 'pct' };
  if (s.endsWith('=F')) return { v: 0.025, unit: 'pct' };
  return { v: 0.015, unit: 'pct' };
}

function revealResearch(id: string) {
  if (getHubMode() !== 'research') setHubMode('research');
  setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
}

function useNewsWire() {
  useEffect(() => {
    let first = true, alive = true;
    const poll = async () => {
      if (document.hidden && !first) return;
      try {
        const j = await (await fetch('/api/v1/mkt/news?limit=40')).json();
        const items: any[] = (j.items ?? []).filter((i: any) => i.title);
        if (!alive) return;                         // a discarded effect must not mark headlines as seen
        const fresh = items.filter((i) => !seenBefore(`news:${String(i.title).trim().toLowerCase().slice(0, 90)}`));
        const show = first ? fresh.slice(0, 2) : fresh.slice(0, 3);   // first look: the latest two, not the whole wire
        for (const i of show) {
          pushPopup({ id: `news:${i.title}`, kind: 'news', title: i.title, href: i.url,
            body: [i.source, i.countries?.length ? i.countries.join(' · ') : null].filter(Boolean).join(' · '),
            tone: i.sentiment > 0.2 ? 'up' : i.sentiment < -0.2 ? 'down' : 'neutral' });
        }
        if (!first && fresh.length > 3) {
          pushPopup({ id: `news-more:${Date.now()}`, kind: 'news', title: `${fresh.length - 3} more headlines on the wire`,
            action: { label: 'Open News', run: () => goMarkets('N') } });
        }
      } catch { /* the wire is optional */ }
      first = false;
    };
    poll();
    const t = setInterval(poll, NEWS_MS);
    return () => { alive = false; clearInterval(t); };
  }, []);
}

function useMarketMoves() {
  const { rows, status } = useMarketPulse();
  const primed = useRef(false);
  useEffect(() => {
    if (status !== 'ok') return;
    const hits: { r: PulseRow; size: number; key: string }[] = [];
    for (const r of Object.values(rows)) {
      if (r.price == null) continue;
      const th = threshold(r);
      const move = th.unit === 'bp' ? r.change_1d_bp : r.change_1d;
      if (move == null || Math.abs(move) < th.v) continue;
      const size = Math.abs(move) / th.v;
      hits.push({ r, size, key: `move:${r.symbol}:${r.date}:${move > 0 ? 'up' : 'down'}:${Math.floor(size)}` });
    }
    hits.sort((a, b) => b.size - a.size);
    const fresh = hits.filter((h) => !seenBefore(h.key));
    for (const h of fresh.slice(0, primed.current ? 3 : 2)) {
      const c = fmtPulseChange(h.r);
      pushPopup({ id: h.key, kind: 'move', tone: c.dir > 0 ? 'up' : 'down',
        title: `${SHORT[h.r.symbol] ?? h.r.symbol} ${c.dir > 0 ? '▲' : '▼'} ${c.text}`,
        body: `${h.r.name} — ${h.size >= 2 ? 'an outsized' : 'a big'} day (${h.r.date ?? 'latest session'})`,
        action: { label: 'Chart', run: () => openChart(h.r.symbol, h.r.name) } });
    }
    primed.current = true;
  }, [rows, status]);
}

function useEcoReleases() {
  const events = useRef<any[]>([]);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const j = await (await fetch('/api/v1/mkt/eco/global?days_back=1&min_impact=High')).json();
        if (alive) events.current = j.events ?? [];
      } catch { /* optional */ }
    };
    const check = () => {
      const now = Date.now();
      for (const e of events.current) {
        const t = new Date(e.date).getTime();
        if (!Number.isFinite(t) || String(e.date).length <= 10) continue;
        const name = `${e.country} ${e.title}`;
        const open = () => (getHubMode() === 'research' ? revealResearch('economic-calendar') : goMarkets('ECO'));
        const mins = Math.round((t - now) / 60_000);
        if (mins > 0 && mins <= 15 && !seenBefore(`eco-up:${name}:${e.date}`)) {
          pushPopup({ id: `eco-up:${name}:${e.date}`, kind: 'eco', title: `${name} in ${mins} min`,
            body: [e.forecast && `consensus ${e.forecast}`, e.previous && `previous ${e.previous}`].filter(Boolean).join(' · ') || 'High impact',
            action: { label: 'Calendar', run: open } });
        }
        if (e.actual != null && now - t < 3 * 3600_000 && now >= t && !seenBefore(`eco-act:${name}:${e.date}`)) {
          const unit = e.unit ?? '';
          const s = typeof e.surprise === 'number' ? e.surprise : null;
          pushPopup({ id: `eco-act:${name}:${e.date}`, kind: 'eco', tone: s == null || s === 0 ? 'neutral' : s > 0 ? 'up' : 'down',
            title: `${name}: ${e.actual}${unit}`,
            body: [e.forecast && `vs consensus ${e.forecast}`, e.previous && `previous ${e.previous}`,
              s != null && `surprise ${s > 0 ? '+' : ''}${+s.toFixed(3)}${unit}`].filter(Boolean).join(' · '),
            action: { label: 'Calendar', run: open } });
        }
      }
    };
    load().then(check);
    const a = setInterval(load, ECO_MS), b = setInterval(check, 30_000);
    return () => { alive = false; clearInterval(a); clearInterval(b); };
  }, []);
}

function useRegimeChanges() {
  useEffect(() => {
    const KEY = 'popup_regimes';
    const poll = async () => {
      try {
        const j = await (await fetch('/api/v1/model/world')).json();
        let last: Record<string, string> = {};
        try { last = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { /* none yet */ }
        const next = { ...last };
        for (const r of j.economies ?? []) {
          if (!r.available) continue;
          const id = r.economy.id, prev = last[id];
          next[id] = r.regime;
          if (prev && prev !== r.regime) {
            pushPopup({ id: `regime:${id}:${r.as_of}:${r.regime}`, kind: 'regime',
              title: `${r.economy.name}: ${prev} → ${r.regime}`,
              body: `Macro model, ${pct0(r.probabilities[r.regime])} probability · data to ${r.factor_as_of}`,
              action: { label: 'Model', run: () => revealResearch('macro-model') } });
          }
        }
        try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* storage unavailable */ }
      } catch { /* optional */ }
    };
    const first = setTimeout(poll, 20_000);           // after the page has loaded its own data
    const t = setInterval(poll, REGIME_MS);
    return () => { clearTimeout(first); clearInterval(t); };
  }, []);
}
const pct0 = (v?: number) => (v == null ? '—' : `${Math.round(v * 100)}%`);

// ── UI ─────────────────────────────────────────────────────────────────────────────────────────────────────────
const KIND_TAG: Record<PopupKind, string> = { news: 'NEWS', move: 'MOVE', eco: 'ECO', regime: 'REGIME' };

function ago(t: number): string {
  const s = Math.round((Date.now() - t) / 1000);
  return s < 60 ? 'now' : s < 3600 ? `${Math.floor(s / 60)}m` : `${Math.floor(s / 3600)}h`;
}

function open(p: Popup) {
  if (p.href) window.open(p.href, '_blank', 'noopener,noreferrer');
  else p.action?.run();
}

function Toast({ p }: { p: Popup }) {
  const [paused, setPaused] = useState(false);
  const left = useRef(LIFE_MS);
  useEffect(() => {
    if (paused) return;
    const started = Date.now();
    const t = setTimeout(() => dismissPopup(p.id), left.current);
    return () => { clearTimeout(t); left.current -= Date.now() - started; };
  }, [paused, p.id]);
  return (
    <div role="status" className={cn('popup-toast', `popup-${p.kind}`, p.tone && `popup-${p.tone}`)}
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div className="popup-head">
        <span className="popup-tag">{KIND_TAG[p.kind]}</span>
        <span className="popup-time">{ago(p.at)}</span>
        <button type="button" className="popup-close" aria-label="Dismiss" onClick={() => dismissPopup(p.id)}><X className="w-3 h-3" /></button>
      </div>
      <button type="button" className="popup-body" onClick={() => { open(p); dismissPopup(p.id); }}
        title={p.href ? 'Open the story' : p.action?.label}>
        <span className="popup-title">{p.title}</span>
        {p.body && <span className="popup-sub">{p.body}</span>}
        {(p.href || p.action) && <span className="popup-cta">{p.href ? 'Read ↗' : `${p.action!.label} →`}</span>}
      </button>
      <span className="popup-life" style={{ animationDuration: `${LIFE_MS}ms`, animationPlayState: paused ? 'paused' : 'running' }} />
    </div>
  );
}

function HistoryPanel() {
  const { history, enabled, kinds } = usePopups();
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') togglePanel(false); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, []);
  return (
    <div className="popup-panel" role="dialog" aria-label="Live alerts">
      <div className="popup-panel-head">
        <span className="text-xs font-semibold text-text-primary">Live alerts</span>
        <label className="ml-auto flex items-center gap-1.5 text-2xs text-text-secondary cursor-pointer">
          <input type="checkbox" checked={enabled} onChange={(e) => setPopupsEnabled(e.target.checked)} /> Pop-ups
        </label>
        <button type="button" className="popup-close" aria-label="Close" onClick={() => togglePanel(false)}><X className="w-3.5 h-3.5" /></button>
      </div>
      <div className="flex flex-wrap gap-1 px-3 pb-2">
        {(Object.keys(KIND_LABEL) as PopupKind[]).map((k) => (
          <button key={k} type="button" onClick={() => setKindEnabled(k, !kinds[k])} aria-pressed={kinds[k]}
            className={cn('px-1.5 py-0.5 text-[10px] font-mono border', kinds[k] ? 'border-bloomberg text-bloomberg' : 'border-border text-text-tertiary line-through')}>
            {KIND_LABEL[k]}</button>
        ))}
      </div>
      <div className="popup-panel-list">
        {history.length === 0 && <div className="p-3 text-2xs text-text-tertiary">Nothing yet — headlines, big moves, releases and regime changes will appear here.</div>}
        {history.map((p) => (
          <button key={p.id} type="button" className={cn('popup-row', `popup-${p.kind}`)} onClick={() => open(p)}>
            <span className="popup-tag">{KIND_TAG[p.kind]}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-2xs text-text-primary truncate">{p.title}</span>
              {p.body && <span className="block text-[10px] text-text-tertiary truncate">{p.body}</span>}
            </span>
            <span className="popup-time">{ago(p.at)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function LivePopups() {
  useNewsWire();
  useMarketMoves();
  useEcoReleases();
  useRegimeChanges();
  const { toasts, panel } = usePopups();
  return (
    <>
      <div className="popup-stack" aria-live="polite">
        {toasts.map((p) => <Toast key={p.id} p={p} />)}
      </div>
      {panel && <HistoryPanel />}
    </>
  );
}

/** Status-bar button: unread count, opens the history and settings. */
export function AlertsButton() {
  const { unread, enabled, panel } = usePopups();
  return (
    <button type="button" className={cn('status-btn', !enabled && 'opacity-60')} onClick={() => togglePanel()} aria-expanded={panel}
      title={enabled ? 'Live alerts — history and settings' : 'Pop-ups are muted — click for the history and settings'}>
      ALERTS{unread > 0 && <span className="popup-badge">{unread > 99 ? '99+' : unread}</span>}{!enabled && ' ⊘'}
    </button>
  );
}

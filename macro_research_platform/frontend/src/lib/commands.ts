// The command language shared by both modes' <GO> lines — one resolver, so the same words work everywhere:
//
//   panels      a Research panel by name, initials or a word in it: "VAR", "fund overview", "FO", "calendar"
//   models      the macro model for an economy: "US MODEL", "EA MODEL" / "EURO", "ROW" / "REST OF WORLD", "WORLD"
//   funds       switch fund: "BIFS", "MORIAH" (the funds you can open)
//   actions     "TAPE" (show / hide the ticker tape), "ALERTS" (live-alert history), "REFRESH", "KEYS" (shortcuts)
//   Markets     any Markets function or security: "WEI", "ECO", "AAPL DES", "SPX Index GP", "7203.T" (parseCommand)
//
// resolveCommands(q) returns ranked candidates; the first is what <GO> runs.
import { findFunction, parseCommand } from '@/components/markets/functions';
import { currentFund, switchFund } from './fund';
import { revealPanel } from './focusMode';
import { getHubMode, setHubMode } from './hubMode';
import { goMarkets } from './marketsRoute';
import { PANEL_LABELS } from './panels';
import { togglePanel } from './popups';

export type CommandGroup = 'Model' | 'Panel' | 'Fund' | 'Action' | 'Markets' | 'Security';
export type Command = { key: string; group: CommandGroup; label: string; hint?: string; score: number; run: () => void };
export type FundRef = { id: string; name: string };

const TICKER = /^(?=.*[A-Z])[A-Z0-9^][A-Z0-9.\-=^]{0,11}$/;

/** Open a Research panel from either mode (switching workspace or mode first when it is hidden). */
export function openPanel(id: string): void {
  const switchMode = getHubMode() !== 'research';
  if (switchMode) setHubMode('research');
  setTimeout(() => {                                   // after the Research page has mounted
    const switchedGroup = revealPanel(id);
    // Off-screen panels lay out at their real height only as they near the viewport (content-visibility), so the
    // target moves while we travel to it: jump, then re-aim until it stays put (at most ~2.5 s).
    const settle = (tries: number) => {
      const el = document.getElementById(id);
      if (!el) return;
      const off = el.getBoundingClientRect().top - 110;
      if (Math.abs(off) > 24) window.scrollTo({ top: window.scrollY + off, behavior: tries === 8 ? 'smooth' : 'auto' });
      if (tries > 0 && Math.abs(off) > 24) setTimeout(() => settle(tries - 1), 300);
    };
    setTimeout(() => settle(8), switchedGroup ? 260 : 0);
  }, switchMode ? 500 : 0);
}

/** Show an economy's macro model (US / euro area / rest of the world). */
export function openModel(economy: 'us' | 'ea' | 'row'): void {
  try { localStorage.setItem('model_economy', economy); } catch { /* storage unavailable */ }
  window.dispatchEvent(new CustomEvent('model-economy', { detail: economy }));
  openPanel('macro-model');
}

const MODEL_WORDS: [RegExp, 'us' | 'ea' | 'row', string][] = [
  [/^(US|USA|UNITED STATES|AMERICA)( MACRO)?( MODEL)?$/, 'us', 'United States'],
  [/^(EA|EZ|EURO|EUROZONE|EURO ?AREA|EUROPE)( MACRO)?( MODEL)?$/, 'ea', 'Euro area'],
  [/^(ROW|RW|REST( OF( THE)?)? WORLD|GLOBAL|EM|ASIA)( MACRO)?( MODEL)?$/, 'row', 'Rest of the world'],
];

const initials = (label: string) => label.split(/[\s&/—-]+/).filter(Boolean).map((w) => w[0]).join('').toUpperCase();

/** Ranked commands for what's typed. */
export function resolveCommands(input: string, funds: FundRef[] = []): Command[] {
  const raw = input.replace(/<go>/gi, '').trim();
  if (!raw) return [];
  const q = raw.toUpperCase().replace(/\s+/g, ' ');
  const words = q.split(' ');
  const out: Command[] = [];

  // Macro models
  for (const [re, eco, name] of MODEL_WORDS) {
    if (re.test(q)) out.push({ key: `model:${eco}`, group: 'Model', label: `${name} macro model`, hint: 'regime, portfolio, backtest', score: 100, run: () => openModel(eco) });
  }
  if (/^(WORLD|MACRO|MODEL|MACRO MODEL|REGIMES?)$/.test(q)) {
    out.push({ key: 'model:world', group: 'Model', label: 'Macro model — all three economies', hint: 'US · euro area · rest of world', score: 95, run: () => openPanel('macro-model') });
  }

  // Funds
  for (const f of funds) {
    const n = f.name.toUpperCase();
    if (q === f.id.toUpperCase() || q === n || (q.length >= 3 && n.startsWith(q))) {
      const here = f.id === currentFund();
      out.push({ key: `fund:${f.id}`, group: 'Fund', label: here ? `${f.name} (current fund)` : `Switch to ${f.name}`,
        hint: here ? undefined : 'reloads every panel for that fund', score: here ? 40 : 90, run: () => { if (!here) switchFund(f.id); } });
    }
  }

  // Actions
  const actions: [RegExp, string, string, () => void][] = [
    [/^TAPE$/, 'Show / hide the ticker tape', 'status bar', () => document.querySelector<HTMLButtonElement>('.status-btn[aria-pressed]')?.click()],
    [/^(ALERTS?|POP-?UPS?|NOTIFICATIONS?)$/, 'Live alerts — history and settings', 'status bar', () => togglePanel(true)],
    [/^(REFRESH|RELOAD)$/, 'Refresh the data', 'reload the page', () => window.location.reload()],
    [/^(KEYS|HELP|SHORTCUTS|\?)$/, 'Keyboard shortcuts', 'press ? anywhere', () => window.dispatchEvent(new KeyboardEvent('keydown', { key: '?' }))],
  ];
  for (const [re, label, hint, run] of actions) if (re.test(q)) out.push({ key: `act:${label}`, group: 'Action', label, hint, score: 85, run });

  // Research panels: exact name > initials > all words prefix a word of the name > contained
  for (const [id, label] of Object.entries(PANEL_LABELS)) {
    const L = label.toUpperCase();
    const lw = L.split(/[\s&/—-]+/).filter(Boolean);
    let score = 0;
    if (L === q || id.toUpperCase() === q.replace(/ /g, '-')) score = 80;
    else if (q.length >= 2 && initials(label) === q) score = 70;
    else if (words.every((w) => lw.some((x) => x.startsWith(w)))) score = 60 - Math.min(20, lw.length);
    else if (q.length >= 3 && L.includes(q)) score = 35;
    if (score) out.push({ key: `panel:${id}`, group: 'Panel', label, hint: 'Research', score, run: () => openPanel(id) });
  }

  // Markets functions and securities
  const p = parseCommand(raw);
  if (p.fn && !p.fn.security && !p.symbol) {
    out.push({ key: `fn:${p.fn.code}`, group: 'Markets', label: `${p.fn.code} — ${p.fn.name}`, hint: 'Markets', score: 75, run: () => goMarkets(p.fn!.code) });
  }
  const plainWord = !!p.symbol && /^[A-Z]+$/.test(p.symbol) && p.symbol.length > 5;   // MORIAH, CALENDAR: not tickers
  if (p.symbol && (p.terminal || p.fn || (TICKER.test(p.symbol) && !plainWord))) {
    const fn = p.fn && p.fn.security ? p.fn : findFunction('DES');
    // An explicit "AAPL DES" or terminal form ranks first; a ticker-shaped symbol (7203.T, ^N225, BTC-USD) just below
    // an exact panel name (so "what-if" opens the panel); a bare word below any panel or model it matches.
    const explicit = !!p.fn || !!p.terminal;
    const tickerShaped = /[.=^\d-]/.test(p.symbol);
    out.push({ key: `sec:${p.symbol}:${fn?.code}`, group: 'Security', label: `${p.symbol} — ${fn?.name ?? 'Description'}`,
      hint: 'Markets', score: explicit ? 98 : tickerShaped ? 78 : 50, run: () => goMarkets(fn?.code ?? 'DES', p.symbol) });
  }

  const seen = new Set<string>();
  return out.sort((a, b) => b.score - a.score).filter((c) => (seen.has(c.key) ? false : (seen.add(c.key), true))).slice(0, 8);
}

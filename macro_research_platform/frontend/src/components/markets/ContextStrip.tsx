// Context strip on a stock's page: what the rest of the platform knows about it, each item a link to where it
// comes from — your book (Trading), the two regime views of its sector (Macro), the DCF value vs the price (DCF),
// your alerts / journal / team notes, and PE deals on it (PE) or a one-click LBO. Reads /api/v1/mkt/context/{symbol}.
import { BookOpen, Bell, Briefcase, Compass, MessageSquare, Scale, Wallet } from 'lucide-react';
import { cn } from '@/lib/utils';
import { setHubMode } from '@/lib/hubMode';
import { openPanel } from '@/lib/commands';
import { openDeal, openLbo } from '@/components/pe/peShared';
import { useJSON } from './shared';

const TONE: Record<string, string> = { overweight: 'text-green', underweight: 'text-red', neutral: 'text-text-secondary' };
const pct = (v?: number | null) => (v == null || !isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(0)}%`);
const cap = (s?: string | null) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '—');

// One slim pill per item ("label · value") in a single scrolling row: the strip sits above every company screen,
// so it must not push the screen's own content halfway down the page.
function Chip({ icon: Icon, label, children, onClick, title }: { icon: any; label: string; children: React.ReactNode; onClick?: () => void; title?: string }) {
  return (
    <button type="button" onClick={onClick} title={title ?? label} disabled={!onClick}
      className="group inline-flex items-center gap-1.5 shrink-0 max-w-[22rem] pl-1.5 pr-2.5 py-1 rounded-full border border-border-subtle bg-surface-1/70 text-left hover:border-bloomberg/40 hover:bg-bloomberg/[0.04] transition-colors disabled:cursor-default">
      <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-bloomberg/10 text-bloomberg shrink-0"><Icon className="w-3 h-3" /></span>
      <span className="text-[10px] uppercase tracking-[0.06em] text-text-tertiary whitespace-nowrap">{label}</span>
      <span className="text-[11.5px] text-text-primary truncate min-w-0">{children}</span>
    </button>
  );
}

export function ContextStrip({ symbol, onGo, isEquity }: { symbol: string; onGo: (fn: string, s?: string) => void; isEquity: boolean }) {
  const { data: c } = useJSON<any>(isEquity ? `/api/v1/mkt/context/${encodeURIComponent(symbol)}` : null);
  if (!isEquity || !c) return null;
  const fund = c.book?.fund ?? [], futu = c.book?.futu ?? [];
  const held = fund.length + futu.length > 0;
  const qty = [...fund, ...futu].reduce((a: number, p: any) => a + (Number(p.quantity) || 0), 0);
  const m = c.macro ?? {}, sig = m.signal ?? {}, mod = m.model ?? {};
  const v = c.valuation ?? {}, y = c.yours ?? {}, deals = c.pe?.deals ?? [];
  const disagree = sig.stance && mod.stance && sig.stance !== mod.stance;
  const goPanel = (id: string) => openPanel(id);
  const earn = c.earnings_date ? new Date(c.earnings_date * 1000) : null;
  const earnSoon = earn && earn.getTime() > Date.now() && earn.getTime() - Date.now() < 30 * 864e5;
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-0.5 [scrollbar-width:thin]" aria-label="What the platform knows about this company">
      <Chip icon={Wallet} label="Your book" onClick={() => goPanel('position-manager')} title="Open the Position Manager (Trading)">
        {held ? <><span className="font-semibold">{qty.toLocaleString()}</span> held{futu.length ? ' · incl. Futu' : ''}</> : <span className="text-text-secondary">Not held</span>}
      </Chip>
      {m.sector_etf && (
        <Chip icon={Compass} label={`Macro · ${m.sector ?? 'sector'}`} onClick={() => goPanel('regime-playbook')}
          title={`${sig.rationale ?? ''}${disagree ? ' — the two regime views disagree on this sector' : ''}`}>
          <span className={TONE[sig.stance] ?? ''}>{cap(sig.stance)}</span><span className="text-text-tertiary"> in {cap(sig.regime)}</span>
          {mod.regime && <><span className="text-text-tertiary"> · model </span><span className={TONE[mod.stance] ?? ''}>{cap(mod.stance)}</span><span className="text-text-tertiary"> ({mod.regime})</span></>}
          {disagree && <span className="ml-1 text-amber" aria-label="views disagree">≠</span>}
        </Chip>)}
      {v.per_share != null && (
        <Chip icon={Scale} label="DCF value" onClick={() => onGo('DCF', symbol)} title="Open the DCF (three-stage FCFF)">
          <span className="font-semibold">{v.per_share.toFixed(2)}</span> <span className="text-text-tertiary">{v.currency}</span>{' '}
          <span className={cn((v.upside ?? 0) >= 0 ? 'text-green' : 'text-red')}>{pct(v.upside)}</span><span className="text-text-tertiary"> vs price</span>
        </Chip>)}
      {earnSoon && (
        <Chip icon={Bell} label="Earnings" onClick={() => onGo('ERN', symbol)}>{earn!.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</Chip>)}
      <Chip icon={Bell} label="Your alerts" onClick={() => onGo('ALRT', symbol)}>
        {y.alerts?.length ? `${y.alerts.filter((a: any) => a.active).length} active` : <span className="text-text-secondary">None · add one</span>}
      </Chip>
      <Chip icon={BookOpen} label="Journal & notes" onClick={() => onGo('JRNL', symbol)}>
        {(y.journal_count || y.notes_count) ? `${y.journal_count ?? 0} trades · ${y.notes_count ?? 0} notes` : <span className="text-text-secondary">Nothing yet</span>}
      </Chip>
      {deals.length > 0 ? (
        <Chip icon={Briefcase} label="PE pipeline" onClick={() => { setHubMode('pe'); openDeal(deals[0].id); }}>
          {deals[0].name} · {deals[0].stage}{deals.length > 1 ? ` +${deals.length - 1}` : ''}
        </Chip>
      ) : (
        <Chip icon={Briefcase} label="Private equity" onClick={() => { openLbo(symbol); setHubMode('pe'); }} title="Model a buyout in the LBO workbench">
          <span className="text-text-secondary">Model an LBO</span>
        </Chip>)}
      {y.notes?.[0] && (
        <Chip icon={MessageSquare} label={`Latest note · ${y.notes[0].author}`} onClick={() => onGo('JRNL', symbol)}>{y.notes[0].text}</Chip>)}
    </div>
  );
}

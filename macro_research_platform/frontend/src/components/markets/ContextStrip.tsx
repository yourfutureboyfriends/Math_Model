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

function Chip({ icon: Icon, label, children, onClick, title }: { icon: any; label: string; children: React.ReactNode; onClick?: () => void; title?: string }) {
  return (
    <button type="button" onClick={onClick} title={title} disabled={!onClick}
      className="group inline-flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-lg border border-border-subtle bg-surface-1/70 text-left hover:border-bloomberg/40 hover:bg-bloomberg/[0.04] transition-colors disabled:cursor-default min-w-0">
      <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-bloomberg/10 text-bloomberg shrink-0"><Icon className="w-3.5 h-3.5" /></span>
      <span className="min-w-0"><span className="block text-[10px] uppercase tracking-[0.07em] text-text-tertiary">{label}</span>
        <span className="block text-[11.5px] text-text-primary truncate">{children}</span></span>
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
    <div className="flex flex-wrap gap-2" aria-label="What the platform knows about this company">
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

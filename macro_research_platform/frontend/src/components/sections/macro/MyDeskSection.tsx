/**
 * MyDeskSection — the first thing each user sees, tailored to their job.
 *
 *  - Left: YOUR QUEUE — only what needs this user's action, routed by the four-eyes rules
 *    (risk approves others' orders, PM executes approved ones, analysts/quants own data
 *    problems). Each item jumps to the panel where it is handled.
 *  - Right: the numbers that job turns on — the book for a PM, limit utilisation for risk,
 *    the latest macro prints (graded against their release calendar) for analysts/quants.
 *
 * Data: /api/v1/desk (see api/routers/desk.py).
 */
import { ArrowRight, CheckCircle2, LayoutDashboard } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useDesk, type Desk, type DeskLimit, type DeskPrint } from '@/hooks/useDesk';
import { FREQ_LABEL } from '@/hooks/useFreshness';
import { fmtPct } from '@/utils/format';
import { panelLabel } from '@/lib/panels';

const PRIORITY_DOT: Record<string, string> = { high: 'bg-red', medium: 'bg-amber', info: 'bg-text-tertiary' };
const STATUS_TONE: Record<string, string> = { OK: 'text-green', WARN: 'text-amber', BREACH: 'text-red' };

const money = (v: number | null | undefined, ccy = 'USD') => {
  if (v == null || !Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  const s = abs >= 1e9 ? `${(abs / 1e9).toFixed(2)}B` : abs >= 1e6 ? `${(abs / 1e6).toFixed(2)}M`
    : abs >= 1e3 ? `${(abs / 1e3).toFixed(1)}K` : abs.toFixed(0);
  return `${v < 0 ? '-' : ''}${ccy === 'USD' ? '$' : `${ccy} `}${s}`;
};
const signedMoney = (v: number | null | undefined, ccy?: string) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${money(v, ccy)}`;
const tone = (v: number | null | undefined) => (v == null ? '' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : '');

function go(id: string | null) {
  if (!id) return;
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function Tile({ label, value, sub, className = '' }: { label: string; value: string; sub?: string; className?: string }) {
  return (
    <div className="p-2 bg-surface-1 border border-border min-w-0">
      <div className="text-2xs text-text-tertiary uppercase tracking-wider truncate">{label}</div>
      <div className={`text-sm font-mono font-bold text-text-primary truncate ${className}`}>{value}</div>
      {sub && <div className="text-2xs text-text-tertiary truncate">{sub}</div>}
    </div>
  );
}

function fmtLimit(v: number | null, unit: string) {
  if (v == null) return '—';
  return unit === 'days' ? `${v.toFixed(1)}d` : `${(v * 100).toFixed(1)}%`;
}

function LimitBars({ rows }: { rows: DeskLimit[] }) {
  if (!rows.length) return <div className="text-2xs text-text-tertiary">No limit data (empty book?)</div>;
  return (
    <div className="space-y-1.5">
      {rows.map((l) => {
        const u = Math.min(1, Math.max(0, l.utilization ?? 0));
        const bar = l.status === 'BREACH' ? 'bg-red' : l.status === 'WARN' ? 'bg-amber' : 'bg-green';
        return (
          <div key={l.metric}>
            <div className="flex justify-between text-2xs">
              <span className="text-text-secondary truncate">{l.label}</span>
              <span className={`font-mono ${STATUS_TONE[l.status] ?? ''}`}>
                {fmtLimit(l.value, l.unit)} / {fmtLimit(l.hard, l.unit)}
              </span>
            </div>
            <div className="h-1 bg-surface-3 mt-0.5">
              <div className={`h-1 ${bar}`} style={{ width: `${u * 100}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function fmtPrint(p: DeskPrint) {
  const v = p.latest_value;
  if (v == null) return '—';
  if (p.unit === 'claims') return `${(v / 1000).toFixed(0)}k`;
  if (p.unit === 'k jobs m/m') return `${v > 0 ? '+' : ''}${v.toFixed(0)}k`;
  return `${v.toFixed(2)}${p.unit?.startsWith('%') ? '%' : ''}`;
}

const STATE_LABEL: Record<string, [string, string]> = {
  CURRENT: ['current', 'text-green'], DUE: ['release window', 'text-amber'],
  LATE: ['late', 'text-amber'], MISSING_PERIODS: ['missing', 'text-red'], UNAVAILABLE: ['unavailable', 'text-text-tertiary'],
};

function PrintsTable({ prints, categories }: { prints: DeskPrint[]; categories?: string[] }) {
  const rows = categories ? prints.filter((p) => categories.includes(p.category)) : prints;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-2xs font-mono">
        <thead>
          <tr className="text-text-tertiary text-left">
            <th className="font-normal pb-1 pr-2">Indicator</th>
            <th className="font-normal pb-1 pr-2 text-right">Latest</th>
            <th className="font-normal pb-1 pr-2">Period</th>
            <th className="font-normal pb-1 pr-2">Status</th>
            <th className="font-normal pb-1">Next</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => {
            const [label, cls] = STATE_LABEL[p.state] ?? [p.state, ''];
            return (
              <tr key={p.series_id} className="border-t border-border-subtle">
                <td className="py-0.5 pr-2 text-text-secondary whitespace-nowrap" title={`${p.series_id} · ${FREQ_LABEL[p.frequency] ?? ''} · ${p.unit ?? ''}`}>{p.name}</td>
                <td className="pr-2 text-right text-text-primary whitespace-nowrap">{fmtPrint(p)}</td>
                <td className="pr-2 text-text-tertiary whitespace-nowrap">{p.last_observation_date?.slice(0, p.frequency === 'D' || p.frequency === 'W' ? 10 : 7) ?? '—'}</td>
                <td className={`pr-2 whitespace-nowrap ${cls}`}>{label}</td>
                <td className="text-text-tertiary whitespace-nowrap">{p.frequency === 'D' ? 'daily' : p.next_expected_release ? `~${p.next_expected_release.slice(5)}` : '—'}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MacroTiles({ d }: { d: Desk }) {
  const m = d.macro;
  if (!m.available) return null;
  return (
    <>
      <Tile label="Regime" value={(m.regime ?? '—').toUpperCase()}
        sub={m.regime_months != null ? `${m.regime_months} months · ${fmtPct(m.regime_confidence ?? null, 0)} conf.` : undefined} />
      <Tile label="Ensemble" value={m.ensemble_score != null ? m.ensemble_score.toFixed(2) : '—'}
        sub={m.conviction ? `${m.conviction} conviction · risk budget ${m.risk_budget?.toFixed(2) ?? '—'}` : undefined}
        className={tone(m.ensemble_score)} />
      <Tile label="Recession 12M" value={fmtPct(m.recession_probability ?? null, 1)}
        sub={m.sahm != null ? `Sahm ${m.sahm.toFixed(2)}pp` : undefined}
        className={(m.recession_probability ?? 0) > 0.3 ? 'text-red' : ''} />
    </>
  );
}

function BookTiles({ d }: { d: Desk }) {
  const f = d.fund;
  if (!f.available) return <Tile label="Book" value="unavailable" />;
  const ccy = f.base_currency ?? 'USD';
  const tr = f.track_record;
  return (
    <>
      <Tile label="NAV" value={money(f.nav, ccy)} sub={`${f.positions ?? 0} positions`} />
      <Tile label="Last day P&L" value={signedMoney(f.last_day_pnl, ccy)} className={tone(f.last_day_pnl)}
        sub={f.last_day_pnl == null ? 'needs 2 NAV snapshots' : 'NAV snapshot to snapshot'} />
      <Tile label="Unrealized P&L" value={signedMoney(f.unrealized_pnl, ccy)} className={tone(f.unrealized_pnl)} />
      <Tile label="Gross / Net" value={`${fmtPct(f.exposures?.gross ?? null, 0)} / ${fmtPct(f.exposures?.net ?? null, 0)}`} sub="% NAV" />
      <Tile label="VaR 95% 1d" value={money(f.var95_1d_usd, ccy)}
        sub={f.nav && f.var95_1d_usd != null ? `${fmtPct(f.var95_1d_usd / f.nav, 2)} NAV` : undefined} />
      <Tile label="Limits" value={f.limits?.overall ?? '—'} className={STATUS_TONE[f.limits?.overall ?? ''] ?? ''}
        sub={`${f.limits?.breaches.length ?? 0} breach · ${f.limits?.warnings.length ?? 0} warn`} />
      {tr?.available && (
        <Tile label="Track record" value={`Sharpe ${tr.sharpe?.toFixed(2) ?? '—'}`}
          sub={`${fmtPct(tr.total_return ?? null, 1)} total · max DD ${fmtPct(tr.max_drawdown ?? null, 1)}`} />
      )}
    </>
  );
}

function RoleBody({ d }: { d: Desk }) {
  const role = d.user.role;
  const pending = (d.orders.by_state['Proposed'] ?? 0) + (d.orders.by_state['Under Review'] ?? 0);
  const approved = d.orders.by_state['Approved'] ?? 0;
  const prints = d.data.prints ?? [];

  if (role === 'risk') {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
          <Tile label="Limits" value={d.fund.limits?.overall ?? '—'} className={STATUS_TONE[d.fund.limits?.overall ?? ''] ?? ''} />
          <Tile label="VaR 95% 1d" value={money(d.fund.var95_1d_usd, d.fund.base_currency)} />
          <Tile label="Gross / Net" value={`${fmtPct(d.fund.exposures?.gross ?? null, 0)} / ${fmtPct(d.fund.exposures?.net ?? null, 0)}`} />
          <Tile label="Orders to review" value={String(pending)} className={pending ? 'text-amber' : ''} />
        </div>
        <div>
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Highest limit utilisation</div>
          <LimitBars rows={d.fund.limits?.top_utilization ?? []} />
        </div>
        <div className="grid grid-cols-3 gap-1.5"><MacroTiles d={d} /></div>
      </div>
    );
  }
  if (role === 'analyst' || role === 'quant') {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-1.5"><MacroTiles d={d} /></div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">Latest prints · release calendar</span>
            {d.data.score_pct != null && (
              <span className={`text-2xs font-mono ${d.data.score_pct >= 90 ? 'text-green' : 'text-amber'}`}>
                {d.data.score_pct}% of inputs current
              </span>
            )}
          </div>
          <PrintsTable prints={prints}
            categories={role === 'analyst' ? ['Growth', 'Labour', 'Inflation', 'Policy & liquidity'] : undefined} />
        </div>
      </div>
    );
  }
  // pm / admin: the book first, then the macro backdrop.
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5"><BookTiles d={d} /></div>
      <div className="grid grid-cols-3 gap-1.5"><MacroTiles d={d} /></div>
      {(pending > 0 || approved > 0) && (
        <div className="text-2xs text-text-tertiary">Orders: {pending} awaiting approval · {approved} approved</div>
      )}
    </div>
  );
}

export const deskPanelLabel = (id: string) => panelLabel(id);

export function MyDeskSection() {
  const { user } = useAuth();
  const d = useDesk(user?.username);

  return (
    <section className="border border-bloomberg/40 bg-surface-1/60 p-3">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <LayoutDashboard className="w-4 h-4 text-bloomberg" />
        <h2 className="text-sm font-semibold text-text-primary tracking-wide">MY DESK</h2>
        <span className="text-2xs text-text-tertiary">
          {[d?.focus.title ?? user?.role?.toUpperCase(), user?.display_name]
            .filter((x, i, a) => x && a.indexOf(x) === i).join(' · ')}
        </span>
        {d && <span className="ml-auto text-2xs text-text-tertiary font-mono">as of {d.as_of.slice(11, 16)}</span>}
      </div>

      {!d ? (
        <div className="text-xs text-text-tertiary font-mono">Loading your desk…</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
          <div className="lg:col-span-2 min-w-0">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Your queue</div>
            {d.queue.length === 0 ? (
              <div className="flex items-center gap-1.5 text-xs text-green py-2">
                <CheckCircle2 className="w-3.5 h-3.5" /> Nothing needs your attention.
              </div>
            ) : (
              <ul className="space-y-1">
                {d.queue.slice(0, 8).map((i, n) => (
                  <li key={`${i.kind}-${n}`}>
                    <button onClick={() => go(i.target)} disabled={!i.target}
                      className="w-full text-left flex items-start gap-2 px-2 py-1.5 border border-border hover:border-bloomberg/60 disabled:hover:border-border">
                      <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${PRIORITY_DOT[i.priority]}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs text-text-primary">{i.title}</span>
                        {i.detail && <span className="block text-2xs text-text-tertiary truncate">{i.detail}</span>}
                      </span>
                      {i.target && <ArrowRight className="w-3 h-3 mt-1 text-text-tertiary shrink-0" />}
                    </button>
                  </li>
                ))}
                {d.queue.length > 8 && <li className="text-2xs text-text-tertiary">+{d.queue.length - 8} more</li>}
              </ul>
            )}
            <div className="flex flex-wrap gap-1 mt-3">
              {d.focus.panels.map((p) => (
                <button key={p} onClick={() => go(p)}
                  className="text-2xs px-1.5 py-0.5 border border-border text-text-secondary hover:text-bloomberg hover:border-bloomberg/60">
                  {deskPanelLabel(p)}
                </button>
              ))}
            </div>
          </div>
          <div className="lg:col-span-3 min-w-0"><RoleBody d={d} /></div>
        </div>
      )}
    </section>
  );
}

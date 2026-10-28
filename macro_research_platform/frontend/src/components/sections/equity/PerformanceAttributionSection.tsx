/**
 * PerformanceAttributionSection — Phase 5 multi-level attribution on real positions.
 *
 * Reads /api/v1/portfolio/attribution: contribution attribution (each position's / book's
 * dollar P&L, summing to total) and factor attribution (trailing portfolio return split
 * into systematic per-factor contributions + idiosyncratic selection). Renders a factor
 * waterfall and a by-book / by-position drill-down.
 */
import { useCallback, useEffect, useState } from 'react';
import { BarChart3, RefreshCw } from 'lucide-react';

const usd = (v: number | null | undefined) =>
  v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const pct = (v: number | null | undefined, dp = 1) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(dp)}%`);

export function PerformanceAttributionSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/v1/portfolio/attribution');
      setData(r.ok ? await r.json() : { available: false, reason: `HTTP ${r.status}` });
    } catch (e: any) {
      setData({ available: false, reason: e?.message || 'failed' });
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const c = data?.contribution;
  const f = data?.factor;
  const factorRows = f?.available
    ? [...Object.entries(f.by_factor as Record<string, number>).map(([k, v]) => ({ label: k, value: v })),
       { label: 'idiosyncratic', value: f.idiosyncratic_return }]
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    : [];
  const maxFactor = Math.max(0.001, ...factorRows.map((r) => Math.abs(r.value)));
  const maxBook = c ? Math.max(1, ...c.by_book.map((b: any) => Math.abs(b.pnl))) : 1;

  return (
    <section id="performance-attribution" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><BarChart3 className="w-3 h-3" /></span>
          <h2 className="section-title">Performance Attribution</h2>
          {c && <span className="section-meta">P&L {usd(c.total_unrealized_pnl)}</span>}
        </div>
        <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-6 text-center text-sm text-text-secondary">Computing attribution…</div>}
      {data && !data.available && (
        <div className="p-6 bg-surface-1 border border-border text-center text-sm text-text-secondary">{data.reason}</div>
      )}

      {data?.available && (
        <div className="space-y-3">
          {/* Factor attribution waterfall */}
          {f?.available && (
            <div className="p-3 bg-surface-1 border border-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-2xs text-text-tertiary uppercase tracking-wider">Return Attribution ({f.window})</span>
                <span className="text-xs font-mono">
                  Total <span className={f.portfolio_return >= 0 ? 'text-green' : 'text-red'}>{pct(f.portfolio_return)}</span>
                  <span className="text-text-tertiary"> = systematic </span><span className="text-text-secondary">{pct(f.systematic_return)}</span>
                  <span className="text-text-tertiary"> + selection </span><span className="text-text-secondary">{pct(f.idiosyncratic_return)}</span>
                </span>
              </div>
              <div className="space-y-1">
                {factorRows.map((r) => {
                  const w = (Math.abs(r.value) / maxFactor) * 50;
                  const posv = r.value >= 0;
                  return (
                    <div key={r.label} className="flex items-center gap-2 text-xs">
                      <span className={`w-28 shrink-0 capitalize ${r.label === 'idiosyncratic' ? 'text-bloomberg' : 'text-text-secondary'}`}>{r.label}</span>
                      <div className="flex-1 relative h-3 bg-surface-3">
                        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                        <div className={`absolute top-0 bottom-0 ${posv ? 'bg-green' : 'bg-red'}`} style={{ left: posv ? '50%' : `${50 - w}%`, width: `${w}%` }} />
                      </div>
                      <span className={`w-16 text-right font-mono ${posv ? 'text-green' : 'text-red'}`}>{pct(r.value)}</span>
                    </div>
                  );
                })}
              </div>
              <div className="text-2xs text-text-tertiary pt-1 mt-1 border-t border-border-subtle">
                Systematic = Σ factor loading × factor return; selection = residual (stock-specific).
              </div>
            </div>
          )}

          {/* Contribution by book */}
          {c?.by_book?.length > 0 && (
            <div className="p-3 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">P&L Contribution by Book</div>
              <div className="space-y-1">
                {c.by_book.map((b: any) => {
                  const w = (Math.abs(b.pnl) / maxBook) * 100;
                  return (
                    <div key={b.book} className="flex items-center gap-2 text-xs">
                      <span className="w-28 shrink-0 text-text-secondary">{b.book} <span className="text-text-tertiary">({b.positions})</span></span>
                      <div className="flex-1 h-3 bg-surface-3 relative">
                        <div className={`absolute top-0 bottom-0 left-0 ${b.pnl >= 0 ? 'bg-green' : 'bg-red'}`} style={{ width: `${w}%` }} />
                      </div>
                      <span className={`w-20 text-right font-mono ${b.pnl >= 0 ? 'text-green' : 'text-red'}`}>{usd(b.pnl)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Drill-down: by position */}
          <div className="border border-border bg-surface-1 overflow-x-auto">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 text-2xs text-text-tertiary uppercase tracking-wider">
              P&L Contribution by Position
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-subtle text-2xs text-text-tertiary uppercase">
                  <th className="text-left py-2 px-3 font-medium">Symbol</th>
                  <th className="text-left py-2 px-3 font-medium">Book</th>
                  <th className="text-right py-2 px-3 font-medium">P&L</th>
                  <th className="text-right py-2 px-3 font-medium">% of Total</th>
                </tr>
              </thead>
              <tbody>
                {(c?.by_position ?? []).map((p: any) => (
                  <tr key={p.symbol} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3 text-sm text-text-primary">{p.symbol}</td>
                    <td className="py-2 px-3 text-xs text-text-secondary">{p.book}</td>
                    <td className={`py-2 px-3 text-right font-mono text-sm ${p.pnl >= 0 ? 'text-green' : 'text-red'}`}>{usd(p.pnl)}</td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-text-secondary">{p.pct_of_pnl != null ? pct(p.pct_of_pnl, 0) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

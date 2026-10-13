// Phase 8 — Risk Parity Allocation Section (Redesigned)
// Risk-balanced allocation with terminal aesthetic

import { AlertTriangle, RefreshCw } from 'lucide-react';
import { Donut } from '@/components/ui/Donut';
import { BarList } from '@/components/ui/BarList';
import { useMacroStore } from '@/store/macroStore';

interface RiskParitySectionProps {
  data?: any;
}

export function RiskParitySection({ data: dataProp }: RiskParitySectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  let data = dataProp;
  if (!data) data = (_fullDash as any)?.riskParityAllocation as any;
  if (!data) return null;

  // Missing values render as '—' (no default vol / leverage is assumed).
  const formatPercent = (val: number | null | undefined) =>
    typeof val === 'number' && isFinite(val) ? `${(val * 100).toFixed(1)}%` : '—';

  // Handle both old and new data formats
  const holdings = data.holdings || data.assets || [];
  const targetVolatility: number | null = data.targetVolatility ?? null;
  const portfolioVolatility: number | null = data.portfolioVolatility ?? data.portfolioVol ?? null;
  const leverage: number | null = data.leverage ?? null;
  const rebalancingNeeded: boolean | null = data.rebalancingNeeded ?? null;
  const lastRebalanced = data.lastRebalanced || data.lastUpdated;

  return (
    <div id="risk-parity" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Risk Parity</h2>
          <span className="section-meta">
            {rebalancingNeeded == null ? '—' : rebalancingNeeded ? 'Rebalance' : 'Balanced'}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Portfolio Summary */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase mb-0.5">Target Vol</div>
            <div className="text-base font-mono font-bold text-text-primary">
              {formatPercent(targetVolatility)}
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase mb-0.5">Current Vol</div>
            <div className={`text-base font-mono font-bold ${portfolioVolatility == null || targetVolatility == null ? 'text-text-secondary' : portfolioVolatility > targetVolatility * 1.1 ? 'text-red' : 'text-green'}`}>
              {formatPercent(portfolioVolatility)}
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase mb-0.5">Leverage</div>
            <div className="text-base font-mono font-bold text-text-primary">
              {leverage != null ? `${leverage.toFixed(2)}x` : '—'}
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase mb-0.5">Status</div>
            <div className="flex items-center gap-1">
              {rebalancingNeeded == null ? (
                <span className="signal-tag neutral">—</span>
              ) : rebalancingNeeded ? (
                <>
                  <AlertTriangle className="w-3 h-3 text-red" />
                  <span className="signal-tag bearish">Rebalance</span>
                </>
              ) : (
                <>
                  <RefreshCw className="w-3 h-3 text-green" />
                  <span className="signal-tag bullish">Balanced</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Weight vs volatility: risk parity weights each asset ∝ 1 / volatility */}
        {holdings.length > 1 && (
          <div className="grid gap-2 md:grid-cols-2">
            <div className="p-3 bg-surface-1 border border-border">
              <Donut title="Target allocation" fmt={(v) => `${v.toFixed(1)}%`}
                centerValue={formatPercent(portfolioVolatility)} centerLabel="portfolio vol"
                data={holdings.map((h: any) => ({ label: h.ticker || h.asset, value: h.targetAllocationPct ?? (h.adjustedWeight ?? 0) * 100 }))} />
            </div>
            <div className="p-3 bg-surface-1 border border-border">
              <BarList title="Annualised volatility — the higher, the smaller the weight" color="#c98500" labelWidth="4.5rem"
                fmt={(v) => `${(v * 100).toFixed(1)}%`}
                data={[...holdings].sort((a: any, b: any) => (b.annualisedVol ?? b.volatility ?? 0) - (a.annualisedVol ?? a.volatility ?? 0))
                  .map((h: any) => ({ label: h.ticker || h.asset, value: h.annualisedVol ?? h.volatility ?? null }))} />
            </div>
          </div>
        )}

        {/* Holdings Table */}
        {holdings.length > 0 && (
          <div className="border border-border bg-surface-1 overflow-hidden">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">
                Holdings
              </span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Asset</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Vol</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Base Wgt</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium" title="3-month trend (t-stat ≥ 1); does not change the risk-parity weight">3M Trend</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Target %</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((item: any) => (
                  <tr key={item.ticker || item.asset} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3 text-sm font-medium text-text-primary">
                      <div>{item.ticker || item.asset}</div>
                      <div className="text-2xs text-text-tertiary">{item.sector}</div>
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-text-secondary">
                      {formatPercent(item.annualisedVol ?? item.volatility ?? null)}
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-text-secondary">
                      {formatPercent(item.baseWeight ?? null)}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className="signal-tag text-2xs neutral" title={`t-stat ${item.signalScore}`}>
                        {item.signal}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-bloomberg">
                      {item.targetAllocationPct != null ? `${item.targetAllocationPct.toFixed(1)}%` : item.adjustedWeight != null ? `${(item.adjustedWeight * 100).toFixed(1)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Diversification */}
        {data.diversificationRatio && (
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
              Diversification Ratio
            </div>
            <div className="text-lg font-mono font-bold text-text-primary">
              {data.diversificationRatio.toFixed(2)}
            </div>
            <p className="text-xs text-text-secondary mt-1">
              Higher ratio indicates better risk diversification
            </p>
          </div>
        )}

        {/* Last Rebalanced */}
        <div className="text-2xs text-text-tertiary text-right">
          {/* FIXED (BUG 8): Use ISO date format */}
          Last: {new Date(lastRebalanced).toISOString().split('T')[0]}
        </div>
      </div>
    </div>
  );
}

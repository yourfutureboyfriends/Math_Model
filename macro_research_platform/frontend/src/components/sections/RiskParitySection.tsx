// Phase 8 — Risk Parity Allocation Section (Redesigned)
// Risk-balanced allocation with terminal aesthetic

import { AlertTriangle, RefreshCw } from 'lucide-react';

interface RiskParitySectionProps {
  data?: any;
}

export function RiskParitySection({ data }: RiskParitySectionProps) {
  if (!data) return null;

  const formatPercent = (val: number) => `${((val || 0) * 100).toFixed(1)}%`;

  // Handle both old and new data formats
  const holdings = data.holdings || data.assets || [];
  const targetVolatility = data.targetVolatility || 0.15;
  const portfolioVolatility = data.portfolioVolatility || data.portfolioVol || 0.15;
  const leverage = data.leverage || 1.0;
  const rebalancingNeeded = data.rebalancingNeeded || false;
  const lastRebalanced = data.lastRebalanced || data.lastUpdated || new Date().toISOString();

  return (
    <div id="risk-parity" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">36</span>
          <h2 className="section-title">Risk Parity</h2>
          <span className="section-meta">
            {rebalancingNeeded ? 'Rebalance' : 'Balanced'}
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
            <div className={`text-base font-mono font-bold ${portfolioVolatility > targetVolatility * 1.1 ? 'text-red' : 'text-green'}`}>
              {formatPercent(portfolioVolatility)}
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase mb-0.5">Leverage</div>
            <div className="text-base font-mono font-bold text-text-primary">
              {(leverage || 1).toFixed(2)}x
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase mb-0.5">Status</div>
            <div className="flex items-center gap-1">
              {rebalancingNeeded ? (
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
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
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
                      {((item.annualisedVol || item.volatility || 0) * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-text-secondary">
                      {((item.baseWeight || 0) * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className={`signal-tag text-2xs ${item.conviction === 'High' ? 'bullish' : item.conviction === 'Medium' ? 'warning' : 'neutral'}`}>
                        {item.signal}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right font-mono text-xs text-accent">
                      {item.targetAllocationPct?.toFixed(1) || ((item.adjustedWeight || 0) * 100).toFixed(1)}%
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
          Last: {new Date(lastRebalanced).toLocaleDateString()}
        </div>
      </div>
    </div>
  );
}

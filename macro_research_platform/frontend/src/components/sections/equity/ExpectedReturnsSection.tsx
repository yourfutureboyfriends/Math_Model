// Phase 8 — Expected Returns Section (Redesigned)
// Forward-looking return projections with terminal aesthetic

import { Target } from 'lucide-react';
import { BarList } from '@/components/ui/BarList';
import type { ExpectedReturnsData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface ExpectedReturnsSectionProps {
  data?: ExpectedReturnsData;
}

export function ExpectedReturnsSection({ data }: ExpectedReturnsSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["expectedReturns"] as any;

  if (!data) return null;

  const next12Months = data.next12Months || [];
  const byAssetClass = data.byAssetClass || {};
  const riskAdjustedReturns = data.riskAdjustedReturns || {};

  // Backend provides expectedReturns.weightedPortfolioReturn (already a percent) but
  // not currentRegimeReturn (a fraction). Derive a single percent value and never
  // render NaN — show an explicit dash when no return is available.
  const anyData = data as any;
  const cregPct: number | null = typeof anyData.currentRegimeReturn === 'number'
    ? anyData.currentRegimeReturn * 100
    : typeof anyData.weightedPortfolioReturn === 'number'
      ? anyData.weightedPortfolioReturn
      : null;
  const cregAvailable = cregPct != null && isFinite(cregPct);

  return (
    <div id="expected-returns" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Expected Returns</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Current Regime Expected Return */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Target className="w-3 h-3 text-text-secondary" />
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider">
                  Current Regime Expected Return
                </div>
                <div className={`text-xl font-bold font-mono ${!cregAvailable ? 'text-text-tertiary' : cregPct! >= 0 ? 'text-green' : 'text-red'}`}>
                  {cregAvailable ? `${cregPct! >= 0 ? '+' : ''}${cregPct!.toFixed(1)}%` : '—'}
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-tertiary mb-0.5">Annualized</div>
              {cregAvailable ? (
                <span className={cregPct! >= 0 ? 'signal-tag bullish' : 'signal-tag bearish'}>
                  {cregPct! >= 0 ? 'Positive' : 'Negative'}
                </span>
              ) : (
                <span className="signal-tag neutral">N/A</span>
              )}
            </div>
          </div>
        </div>

        {/* Scenario Analysis */}
        <div className="border border-border bg-surface-1">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">Scenarios · next-month quadrant × historical annual 60/40 return</span>
          </div>
          <div className="p-2 space-y-3">
            {next12Months.length === 0 ? (
              <div className="text-xs text-text-secondary italic">No scenario data available</div>
            ) : (
              next12Months.map((scenario, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-text-primary">{scenario.scenario}</span>
                      <span className="signal-tag neutral text-2xs">
                        {(scenario.probability * 100).toFixed(0)}%
                      </span>
                    </div>
                    <span className={`font-mono text-sm font-medium ${scenario.expectedReturn >= 0 ? 'text-green' : 'text-red'}`}>
                      {scenario.expectedReturn >= 0 ? '+' : ''}{(scenario.expectedReturn * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="relative h-4 bg-surface-4">
                    {/* Probability bar */}
                    <div
                      className="absolute top-0 left-0 bottom-0 bg-bloomberg-muted border-r border-bloomberg"
                      style={{ width: `${scenario.probability * 100}%` }}
                    />
                    {/* Confidence interval markers */}
                    <div
                      className="absolute top-0 bottom-0 border-l border-dashed border-text-tertiary/50"
                      style={{ left: `${((scenario.confidenceInterval[0] + 0.5) / 1) * 100}%` }}
                    />
                    <div
                      className="absolute top-0 bottom-0 border-l border-dashed border-text-tertiary/50"
                      style={{ left: `${((scenario.confidenceInterval[1] + 0.5) / 1) * 100}%` }}
                    />
                    {/* Expected return marker */}
                    <div
                      className="absolute top-0 bottom-0 w-0.5 bg-bloomberg"
                      style={{ left: `${((scenario.expectedReturn + 0.5) / 1) * 100}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-2xs text-text-tertiary">
                    <span>CI: {(scenario.confidenceInterval[0] * 100).toFixed(1)}%</span>
                    <span>CI: {(scenario.confidenceInterval[1] * 100).toFixed(1)}%</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Returns by asset class (diverging around zero) and risk-adjusted */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="p-3 bg-surface-1 border border-border">
            {Object.keys(byAssetClass).length === 0 ? (
              <div className="text-xs text-text-secondary italic">No asset class data</div>
            ) : (
              <BarList title="Expected return by asset class" diverging labelWidth="7rem"
                fmt={(v) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`}
                data={Object.entries(byAssetClass).sort((a, b) => b[1] - a[1]).map(([asset, ret]) => ({ label: asset, value: ret }))} />
            )}
          </div>
          <div className="p-3 bg-surface-1 border border-border">
            {Object.keys(riskAdjustedReturns).length === 0 ? (
              <div className="text-xs text-text-secondary italic">No risk-adjusted data</div>
            ) : (
              <BarList title="Risk-adjusted (return per unit of volatility)" diverging labelWidth="7rem"
                fmt={(v) => v.toFixed(2)}
                data={Object.entries(riskAdjustedReturns).sort((a, b) => b[1] - a[1]).map(([asset, ret]) => ({ label: asset, value: ret }))} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

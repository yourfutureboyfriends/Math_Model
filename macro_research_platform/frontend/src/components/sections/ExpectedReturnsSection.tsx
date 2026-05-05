// Phase 8 — Expected Returns Section (Redesigned)
// Forward-looking return projections with terminal aesthetic

import { Target, AlertCircle } from 'lucide-react';
import type { ExpectedReturnsData } from '@/types';

interface ExpectedReturnsSectionProps {
  data?: ExpectedReturnsData;
}

export function ExpectedReturnsSection({ data }: ExpectedReturnsSectionProps) {
  if (!data) return null;

  const next12Months = data.next12Months || [];
  const byAssetClass = data.byAssetClass || {};
  const riskAdjustedReturns = data.riskAdjustedReturns || {};

  return (
    <div id="expected-returns" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">21</span>
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
                <div className={`text-xl font-bold font-mono ${data.currentRegimeReturn >= 0 ? 'text-green' : 'text-red'}`}>
                  {data.currentRegimeReturn >= 0 ? '+' : ''}{(data.currentRegimeReturn * 100).toFixed(1)}%
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-tertiary mb-0.5">Annualized</div>
              <span className={data.currentRegimeReturn >= 0 ? 'signal-tag bullish' : 'signal-tag bearish'}>
                {data.currentRegimeReturn >= 0 ? 'Positive' : 'Negative'}
              </span>
            </div>
          </div>
        </div>

        {/* Scenario Analysis */}
        <div className="border border-border bg-surface-1">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">Next 12 Months Scenarios</span>
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

        {/* Returns by Asset Class */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">
              By Asset Class
            </div>
            <div className="space-y-1.5">
              {Object.entries(byAssetClass).length === 0 ? (
                <div className="text-xs text-text-secondary italic">No asset class data</div>
              ) : (
                Object.entries(byAssetClass)
                  .sort((a, b) => b[1] - a[1])
                  .map(([asset, ret]) => (
                    <div key={asset} className="flex items-center justify-between">
                      <span className="text-xs text-text-secondary">{asset}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-surface-4 relative">
                          <div
                            className={`absolute top-0 bottom-0 ${ret >= 0 ? 'bg-green right-1/2' : 'bg-red left-1/2'}`}
                            style={{ width: `${Math.min(50, Math.abs(ret) * 100)}%` }}
                          />
                          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                        </div>
                        <span className={`font-mono text-xs w-12 text-right ${ret >= 0 ? 'text-green' : 'text-red'}`}>
                          {ret >= 0 ? '+' : ''}{(ret * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  ))
              )}
            </div>
          </div>

          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2 flex items-center gap-1">
              <AlertCircle className="w-3 h-3" />
              Risk-Adjusted
            </div>
            <div className="space-y-1.5">
              {Object.entries(riskAdjustedReturns).length === 0 ? (
                <div className="text-xs text-text-secondary italic">No risk-adjusted data</div>
              ) : (
                Object.entries(riskAdjustedReturns)
                  .sort((a, b) => b[1] - a[1])
                  .map(([asset, ret]) => (
                    <div key={asset} className="flex items-center justify-between">
                      <span className="text-xs text-text-secondary">{asset}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-surface-4">
                          <div
                            className="h-full bg-amber"
                            style={{ width: `${Math.min(100, Math.abs(ret) * 50)}%` }}
                          />
                        </div>
                        <span className={`font-mono text-xs w-10 text-right ${ret >= 0 ? 'text-amber' : 'text-red'}`}>
                          {ret.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

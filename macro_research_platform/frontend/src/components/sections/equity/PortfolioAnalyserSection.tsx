// Phase 10 — Model Portfolio Section (Macro Terminal Signal)
// Portfolio holdings analysis with terminal aesthetic

import { PieChart, TrendingUp, TrendingDown, Target, Scale, Calendar, Activity } from 'lucide-react';
import type { PortfolioAnalytics, PortfolioSimulationData } from '@/types';

interface PortfolioAnalyserSectionProps {
  data?: PortfolioAnalytics;
  simulationData?: PortfolioSimulationData;
}

export function PortfolioAnalyserSection({ data, simulationData }: PortfolioAnalyserSectionProps) {
  if (!data && !simulationData) {
    return (
      <div id="portfolio" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag"><PieChart className="w-3 h-3" /></span>
            <h2 className="section-title">Model Portfolio</h2>
          </div>
        </div>
        <div className="p-4 text-2xs text-text-tertiary">
          No model-portfolio data — add positions in the Positions panel to populate this view.
        </div>
      </div>
    );
  }

  const formatCurrency = (val: number) => {
    if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
    if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
    return `$${val.toFixed(0)}K`;
  };

  const getAlignmentTag = (alignment: string) => {
    switch (alignment) {
      case 'aligned':
        return 'signal-tag bullish';
      case 'contrarian':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const getSignalTag = (signal: string) => {
    switch (signal.toUpperCase()) {
      case 'OW':
      case 'OVERWEIGHT':
        return 'signal-tag bullish';
      case 'UW':
      case 'UNDERWEIGHT':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  // Model Portfolio View (Phase 10)
  if (simulationData) {
    const { metrics, holdings, inceptionDate, benchmark } = simulationData;
    const { terminal, benchmark6040, spy } = metrics || {};
    // Use null sentinels — display "—" when no portfolio history exists, not "0.0%"
    const safeTerminal = terminal || { totalReturn: null, annReturn: null, sharpe: null, maxDrawdown: null, winRate: null };
    const safeBenchmark6040 = benchmark6040 || { totalReturn: null, annReturn: null, sharpe: null, maxDrawdown: null, winRate: null };
    const safeSpy = spy || { totalReturn: null, annReturn: null, sharpe: null, maxDrawdown: null, winRate: null };
    const fmt = (v: number | null, decimals = 1, pct = true) =>
      v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}${pct ? '%' : ''}`;

    return (
      <div id="portfolio" className="terminal-section">
        {/* Section Header */}
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">◆</span>
            <h2 className="section-title">Model Portfolio</h2>
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="w-3 h-3 text-text-tertiary" />
            <span className="text-2xs text-text-tertiary">Inception: {inceptionDate}</span>
            <span className="text-2xs text-text-tertiary mx-1">|</span>
            <span className="text-2xs text-text-tertiary">Benchmark: {benchmark}</span>
          </div>
        </div>

        <div className="space-y-3">
          {/* Performance Metrics Table */}
          <div className="border border-border bg-surface-1 overflow-hidden">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Performance Metrics</span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Metric</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Terminal</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">60/40</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">SPY</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-border-subtle">
                  <td className="py-2 px-3 text-2xs text-text-secondary">Total Return</td>
                  <td className="py-2 px-3 text-right">
                    <span className={`font-mono text-sm font-bold ${safeTerminal.totalReturn === null ? 'text-text-tertiary' : safeTerminal.totalReturn >= 0 ? 'text-green' : 'text-red'}`}>
                      {fmt(safeTerminal.totalReturn)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className={`font-mono text-sm ${safeBenchmark6040.totalReturn === null ? 'text-text-tertiary' : safeBenchmark6040.totalReturn >= 0 ? 'text-green' : 'text-red'}`}>
                      {fmt(safeBenchmark6040.totalReturn)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className={`font-mono text-sm ${safeSpy.totalReturn === null ? 'text-text-tertiary' : safeSpy.totalReturn >= 0 ? 'text-green' : 'text-red'}`}>
                      {fmt(safeSpy.totalReturn)}
                    </span>
                  </td>
                </tr>
                <tr className="border-b border-border-subtle">
                  <td className="py-2 px-3 text-2xs text-text-secondary">Ann. Return</td>
                  <td className="py-2 px-3 text-right">
                    <span className={`font-mono text-sm ${safeTerminal.annReturn === null ? 'text-text-tertiary' : safeTerminal.annReturn >= 0 ? 'text-green' : 'text-red'}`}>
                      {fmt(safeTerminal.annReturn)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className={`font-mono text-sm ${safeBenchmark6040.annReturn === null ? 'text-text-tertiary' : safeBenchmark6040.annReturn >= 0 ? 'text-green' : 'text-red'}`}>
                      {fmt(safeBenchmark6040.annReturn)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className={`font-mono text-sm ${safeSpy.annReturn === null ? 'text-text-tertiary' : safeSpy.annReturn >= 0 ? 'text-green' : 'text-red'}`}>
                      {fmt(safeSpy.annReturn)}
                    </span>
                  </td>
                </tr>
                <tr className="border-b border-border-subtle">
                  <td className="py-2 px-3 text-2xs text-text-secondary">Sharpe</td>
                  <td className="py-2 px-3 text-right">
                    <span className={`font-mono text-sm ${safeTerminal.sharpe === null ? 'text-text-tertiary' : safeTerminal.sharpe > 1 ? 'text-green' : safeTerminal.sharpe > 0 ? 'text-amber' : 'text-red'}`}>
                      {safeTerminal.sharpe === null ? '—' : safeTerminal.sharpe.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="font-mono text-sm text-text-primary">
                      {safeBenchmark6040.sharpe === null ? '—' : safeBenchmark6040.sharpe.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="font-mono text-sm text-text-primary">
                      {safeSpy.sharpe === null ? '—' : safeSpy.sharpe.toFixed(2)}
                    </span>
                  </td>
                </tr>
                <tr className="border-b border-border-subtle">
                  <td className="py-2 px-3 text-2xs text-text-secondary">Max Drawdown</td>
                  <td className="py-2 px-3 text-right">
                    <span className="font-mono text-sm text-red">
                      {safeTerminal.maxDrawdown === null ? '—' : `${safeTerminal.maxDrawdown.toFixed(1)}%`}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="font-mono text-sm text-red">
                      {safeBenchmark6040.maxDrawdown === null ? '—' : `${safeBenchmark6040.maxDrawdown.toFixed(1)}%`}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="font-mono text-sm text-red">
                      {safeSpy.maxDrawdown === null ? '—' : `${safeSpy.maxDrawdown.toFixed(1)}%`}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td className="py-2 px-3 text-2xs text-text-secondary">Win Rate</td>
                  <td className="py-2 px-3 text-right">
                    <span className="font-mono text-sm text-text-primary">
                      {safeTerminal.winRate !== null ? `${safeTerminal.winRate.toFixed(0)}%` : '—'}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="font-mono text-sm text-text-secondary">—</span>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className="font-mono text-sm text-text-secondary">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Current Holdings */}
          <div className="border border-border bg-surface-1 overflow-hidden">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 flex items-center justify-between">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Current Holdings (from Signal Stack)</span>
              <Activity className="w-3 h-3 text-text-tertiary" />
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">ETF</th>
                  <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Weight</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">P&L</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Entry Date</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((item) => (
                  <tr key={item.etf} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3">
                      <span className="text-sm font-medium text-text-primary">{item.etf}</span>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className={getSignalTag(item.signal)}>
                        {item.signal}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className="font-mono text-sm text-text-primary">
                        {item.weight.toFixed(0)}%
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className={`font-mono text-sm ${item.pnlPct >= 0 ? 'text-green' : 'text-red'}`}>
                        {item.pnlPct >= 0 ? '+' : ''}{item.pnlPct.toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">
                      <span className="font-mono text-2xs text-text-secondary">
                        {item.entryDate}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Source Attribution */}
          <div className="flex items-center justify-end gap-2 text-2xs text-text-tertiary">
            <span>Source:</span>
            <span className="text-text-secondary">/api/backtest + SQLite positions table</span>
          </div>
        </div>
      </div>
    );
  }

  // Legacy Portfolio Analytics View (for backward compatibility)
  return (
    <div id="portfolio" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Portfolio Analyser</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Summary Cards Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <div className="p-2 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-1">
              <PieChart className="w-3 h-3 text-text-secondary" />
              <span className="text-2xs text-text-tertiary uppercase">Total Value</span>
            </div>
            <div className="text-base font-mono font-bold text-text-primary">{formatCurrency(data?.totalValue || 0)}</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-1">
              {data && data.dayPnl >= 0 ? <TrendingUp className="w-3 h-3 text-green" /> : <TrendingDown className="w-3 h-3 text-red" />}
              <span className="text-2xs text-text-tertiary uppercase">Day P&L</span>
            </div>
            <div className={`text-base font-mono font-bold ${data && data.dayPnl >= 0 ? 'text-green' : 'text-red'}`}>
              {data && data.dayPnl >= 0 ? '+' : ''}{(data?.dayPnl || 0).toFixed(2)}%
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-1">
              <Target className="w-3 h-3 text-text-secondary" />
              <span className="text-2xs text-text-tertiary uppercase">Total Return</span>
            </div>
            <div className={`text-base font-mono font-bold ${data && data.totalReturn >= 0 ? 'text-green' : 'text-red'}`}>
              {data && data.totalReturn >= 0 ? '+' : ''}{((data?.totalReturn || 0) * 100).toFixed(1)}%
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-1">
              <Scale className="w-3 h-3 text-text-secondary" />
              <span className="text-2xs text-text-tertiary uppercase">Sharpe</span>
            </div>
            <div className={`text-base font-mono font-bold ${data && data.sharpe > 1 ? 'text-green' : data && data.sharpe > 0 ? 'text-amber' : 'text-red'}`}>
              {(data?.sharpe || 0).toFixed(2)}
            </div>
          </div>
        </div>

        {/* Risk Metrics */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">
            Risk Metrics
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="text-center">
              <div className="text-2xs text-text-tertiary mb-0.5">Volatility</div>
              <div className="text-sm font-mono font-bold text-text-primary">{((data?.volatility || 0) * 100).toFixed(1)}%</div>
            </div>
            <div className="text-center">
              <div className="text-2xs text-text-tertiary mb-0.5">Max Drawdown</div>
              <div className="text-sm font-mono font-bold text-red">{((data?.maxDrawdown || 0) * 100).toFixed(1)}%</div>
            </div>
            <div className="text-center">
              <div className="text-2xs text-text-tertiary mb-0.5">Beta</div>
              <div className="text-sm font-mono font-bold text-text-primary">{(data?.beta || 0).toFixed(2)}</div>
            </div>
            <div className="text-center">
              <div className="text-2xs text-text-tertiary mb-0.5">Corr</div>
              <div className="text-sm font-mono font-bold text-text-primary">{((data?.correlationToBenchmark || 0) * 100).toFixed(0)}%</div>
            </div>
          </div>
        </div>

        {/* Holdings Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 flex items-center justify-between">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">Holdings</span>
            {data && data.holdings.some((h) => Math.abs(h.drift) > 0.05) && (
              <span className="signal-tag warning">Rebalance</span>
            )}
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Asset</th>
                <th className="text-right py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Current</th>
                <th className="text-right py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Target</th>
                <th className="text-right py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Drift</th>
                <th className="text-right py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">P&L</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Align</th>
              </tr>
            </thead>
            <tbody>
              {data?.holdings.map((item) => (
                <tr key={item.ticker} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 px-2">
                    <div>
                      <div className="text-sm font-medium text-text-primary">{item.asset}</div>
                      <div className="text-2xs text-text-tertiary">{item.ticker}</div>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span className="font-mono text-sm text-text-primary">
                      {(item.currentWeight * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span className="font-mono text-2xs text-text-secondary">
                      {(item.targetWeight * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-12 h-1 bg-surface-4 relative">
                        <div
                          className={`absolute top-0 bottom-0 ${Math.abs(item.drift) > 0.05 ? 'bg-amber' : 'bg-green'}`}
                          style={{
                            width: `${Math.min(50, Math.abs(item.drift) * 250)}%`,
                            [item.drift < 0 ? 'right' : 'left']: '50%'
                          }}
                        />
                        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                      </div>
                      <span className={`font-mono text-2xs ${Math.abs(item.drift) > 0.05 ? 'text-amber' : 'text-green'}`}>
                        {item.drift > 0 ? '+' : ''}{(item.drift * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span className={`font-mono text-sm ${item.pnl >= 0 ? 'text-green' : 'text-red'}`}>
                      {item.pnl >= 0 ? '+' : ''}{(item.pnl * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className={getAlignmentTag(item.regimeAlignment)}>
                      {item.regimeAlignment.charAt(0).toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Factor & Sector Exposure */}
        {(data?.factorExposure && Object.keys(data.factorExposure).length > 0) && (
          <div className="grid grid-cols-2 gap-2">
            <div className="p-3 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">
                Factor Exposure
              </div>
              <div className="space-y-2">
                {Object.entries(data.factorExposure).map(([factor, exposure]) => (
                  <div key={factor} className="flex items-center justify-between">
                    <span className="text-2xs text-text-secondary capitalize">{factor}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1 bg-surface-4 relative">
                        <div
                          className={`absolute top-0 bottom-0 ${exposure > 0 ? 'bg-green right-1/2' : 'bg-red left-1/2'}`}
                          style={{ width: `${Math.min(50, Math.abs(exposure) * 50)}%` }}
                        />
                        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                      </div>
                      <span className={`font-mono text-2xs ${exposure > 0.3 ? 'text-green' : exposure < -0.3 ? 'text-red' : 'text-text-secondary'}`}>
                        {exposure > 0 ? '+' : ''}{exposure.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {data.sectorExposure && Object.keys(data.sectorExposure).length > 0 && (
              <div className="p-3 bg-surface-1 border border-border">
                <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">
                  Sector Exposure
                </div>
                <div className="space-y-2">
                  {Object.entries(data.sectorExposure).map(([sector, exposure]) => (
                    <div key={sector} className="flex items-center justify-between">
                      <span className="text-2xs text-text-secondary">{sector}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-surface-4">
                          <div
                            className="h-full bg-bloomberg"
                            style={{ width: `${exposure * 100}%` }}
                          />
                        </div>
                        <span className="font-mono text-2xs text-text-primary">
                          {(exposure * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

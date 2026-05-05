// Phase 8 — GMO 7-Year Asset Class Forecasts Section (Redesigned)
// Long-term return expectations with terminal aesthetic

import { Clock, AlertTriangle } from 'lucide-react';
import type { GMOForecastsData } from '@/types';

interface GMOForecastsSectionProps {
  data?: GMOForecastsData;
}

export function GMOForecastsSection({ data }: GMOForecastsSectionProps) {
  if (!data) return null;

  const getSignalTag = (signal: string) => {
    switch (signal) {
      case 'STRONG BUY':
      case 'BUY':
        return 'signal-tag bullish';
      case 'AVOID':
      case 'STRONG AVOID':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  // Sort by expected return descending
  const sortedForecasts = [...(data.forecasts || [])].sort(
    (a, b) => (b.totalExpectedReturn || 0) - (a.totalExpectedReturn || 0)
  );

  const maxReturn = Math.max(...sortedForecasts.map(f => Math.abs(f.totalExpectedReturn || 0)), 1);

  return (
    <div id="gmo-forecasts" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">19</span>
          <h2 className="section-title">GMO 7-Year Forecasts</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Summary stats */}
        <div className="flex items-center justify-between p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2">
            <Clock className="w-3 h-3 text-text-secondary" />
            <span className="text-xs text-text-secondary">Average Expected Return</span>
          </div>
          <div className="font-mono text-sm text-text-primary">
            {data.summary?.avgExpectedReturn > 0 ? '+' : ''}{data.summary?.avgExpectedReturn?.toFixed(1) || '0.0'}%
          </div>
        </div>

        {/* Forecast table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-2">
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Asset</th>
                <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Return</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
              </tr>
            </thead>
            <tbody>
              {sortedForecasts.map((forecast) => {
                const return_pct = forecast.totalExpectedReturn || 0;
                const bar_width = Math.min(100, (Math.abs(return_pct) / Math.max(maxReturn, 8)) * 100);
                const is_positive = return_pct >= 0;

                return (
                  <tr key={forecast.ticker} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{forecast.assetClass}</div>
                        <div className="text-2xs text-text-tertiary">{forecast.ticker}</div>
                        {data.tensions?.some(t => t.assetClass === forecast.assetClass && t.divergence) && (
                          <div className="flex items-center gap-1 mt-1 text-amber">
                            <AlertTriangle className="w-3 h-3" />
                            <span className="text-2xs">Tactical tension</span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-surface-4 relative">
                          <div
                            className={`absolute top-0 bottom-0 ${is_positive ? 'bg-green right-1/2' : 'bg-red left-1/2'}`}
                            style={{
                              width: `${bar_width / 2}%`,
                              [is_positive ? 'right' : 'left']: '50%'
                            }}
                          />
                          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                        </div>
                        <span className={`font-mono text-sm ${is_positive ? 'text-green' : 'text-red'}`}>
                          {return_pct > 0 ? '+' : ''}{return_pct.toFixed(1)}%
                        </span>
                      </div>
                      <p className="text-2xs text-text-secondary mt-1">{forecast.gmoNote}</p>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className={getSignalTag(forecast.signal)}>
                        {forecast.signal.replace('STRONG ', 'S-')}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Methodology Disclaimer */}
        <div className="p-3 bg-surface-2 border border-border-subtle">
          <div className="text-2xs text-text-tertiary leading-relaxed">
            <strong>Methodology:</strong> Based on GMO&apos;s mean-reversion framework.
            Returns = Current Yield + Valuation Change. Equities use 7-year CAGR from
            normalized earnings yields minus mean reversion. Bonds use yield minus
            duration risk. Commodities use production cost vs spot deviation.
            <span className="text-amber ml-1">Not investment advice.</span>
          </div>
        </div>

        {/* Signal distribution */}
        <div className="grid grid-cols-5 gap-1 text-center">
          <div className="p-2 bg-surface-1 border border-green/30">
            <div className="text-sm font-mono font-bold text-green">{data.summary?.strongBuy || 0}</div>
            <div className="text-2xs text-text-tertiary">Strong Buy</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-sm font-mono font-bold text-green">{data.summary?.buy || 0}</div>
            <div className="text-2xs text-text-tertiary">Buy</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-sm font-mono font-bold text-text-primary">{data.summary?.neutral || 0}</div>
            <div className="text-2xs text-text-tertiary">Neutral</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-sm font-mono font-bold text-amber">{data.summary?.avoid || 0}</div>
            <div className="text-2xs text-text-tertiary">Avoid</div>
          </div>
          <div className="p-2 bg-surface-1 border border-red/30">
            <div className="text-sm font-mono font-bold text-red">{data.summary?.strongAvoid || 0}</div>
            <div className="text-2xs text-text-tertiary">Strong Avoid</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Phase 8 — CTA Trend Following Section (Redesigned)
// Multi-timeframe trend signals with terminal aesthetic

import { TrendingUp, TrendingDown, Minus, AlertTriangle, Activity, ArrowRightLeft } from 'lucide-react';
import type { TrendSignalsData } from '@/types';

interface CTATrendSectionProps {
  data?: TrendSignalsData;
}

export function CTATrendSection({ data }: CTATrendSectionProps) {
  if (!data) return null;

  const getTrendIcon = (direction: string | undefined) => {
    switch (direction) {
      case 'UPTREND':
        return <TrendingUp className="w-3 h-3 text-green" />;
      case 'DOWNTREND':
        return <TrendingDown className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getTrendColor = (direction: string | undefined) => {
    switch (direction) {
      case 'UPTREND':
        return 'text-green';
      case 'DOWNTREND':
        return 'text-red';
      default:
        return 'text-text-tertiary';
    }
  };

  const getSignalArrow = (signal: number | undefined | null) => {
    if (signal == null) return <Minus className="w-3 h-3 text-text-tertiary" />;
    if (signal > 0) return <TrendingUp className="w-3 h-3 text-green" />;
    if (signal < 0) return <TrendingDown className="w-3 h-3 text-red" />;
    return <Minus className="w-3 h-3 text-text-tertiary" />;
  };

  return (
    <div id="cta-trend" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">32</span>
          <h2 className="section-title">CTA Trend Following</h2>
          <span className={`section-meta ${data.ctaSignal === 'BULLISH' ? 'text-green' : data.ctaSignal === 'BEARISH' ? 'text-red' : 'text-text-secondary'}`}>
            {data.ctaSignal}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Summary Bar */}
        <div className="flex items-center justify-between p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2">
            <Activity className="w-3 h-3 text-text-secondary" />
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">CTA Signal</div>
              <div className={`text-base font-mono font-bold ${data.ctaSignal === 'BULLISH' ? 'text-green' : data.ctaSignal === 'BEARISH' ? 'text-red' : 'text-text-secondary'}`}>
                {data.ctaSignal}
              </div>
            </div>
          </div>
          <div className="flex gap-4 text-right">
            <div>
              <div className="text-2xs text-text-tertiary">Up</div>
              <div className="text-sm font-mono font-bold text-green">{data.summary.uptrends}</div>
            </div>
            <div>
              <div className="text-2xs text-text-tertiary">Down</div>
              <div className="text-sm font-mono font-bold text-red">{data.summary.downtrends}</div>
            </div>
            <div>
              <div className="text-2xs text-text-tertiary">Contra</div>
              <div className={`text-sm font-mono font-bold ${data.summary.contradictions > 0 ? 'text-amber' : 'text-text-secondary'}`}>
                {data.summary.contradictions}
              </div>
            </div>
          </div>
        </div>

        {/* Contradictions Alert */}
        {(data.contradictions?.length ?? 0) > 0 && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-3 h-3 text-amber" />
              <span className="text-xs font-medium text-amber">
                Regime Contractions
              </span>
            </div>
            <div className="space-y-1">
              {(data.contradictions ?? []).map((contradiction, idx) => (
                <div key={idx} className="flex items-center gap-2 text-xs">
                  <ArrowRightLeft className="w-3 h-3 text-amber" />
                  <span className="text-text-secondary">{contradiction.ticker}:</span>
                  <span className="text-text-tertiary">{contradiction.expected}</span>
                  <span className="text-amber">→</span>
                  <span className="text-red">{contradiction.actual}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Asset Trend Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-2">
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Asset</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">1M</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">3M</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">12M</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Trend</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {(data.assets ?? []).map((asset) => (
                <tr
                  key={asset.ticker}
                  className={`border-b border-border-subtle last:border-0 ${asset.contradiction ? 'bg-amber-dim' : ''}`}
                >
                  <td className="py-2 px-2">
                    <div>
                      <div className="text-sm font-medium text-text-primary">{asset.ticker}</div>
                      <div className="text-2xs text-text-tertiary">{asset.name}</div>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getSignalArrow(asset.signals.fast.signal)}
                      <span className={`font-mono text-2xs ${(asset.signals.fast.return ?? 0) >= 0 ? 'text-green' : 'text-red'}`}>
                        {asset.signals.fast.return != null && typeof asset.signals.fast.return === 'number' && isFinite(asset.signals.fast.return)
                          ? `${asset.signals.fast.return >= 0 ? '+' : ''}${asset.signals.fast.return.toFixed(1)}%`
                          : '—'}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getSignalArrow(asset.signals.medium.signal)}
                      <span className={`font-mono text-2xs ${(asset.signals.medium.return ?? 0) >= 0 ? 'text-green' : 'text-red'}`}>
                        {asset.signals.medium.return != null && typeof asset.signals.medium.return === 'number' && isFinite(asset.signals.medium.return)
                          ? `${asset.signals.medium.return >= 0 ? '+' : ''}${asset.signals.medium.return.toFixed(1)}%`
                          : '—'}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getSignalArrow(asset.signals.slow.signal)}
                      <span className={`font-mono text-2xs ${(asset.signals.slow.return ?? 0) >= 0 ? 'text-green' : 'text-red'}`}>
                        {asset.signals.slow.return != null && typeof asset.signals.slow.return === 'number' && isFinite(asset.signals.slow.return)
                          ? `${asset.signals.slow.return >= 0 ? '+' : ''}${asset.signals.slow.return.toFixed(1)}%`
                          : '—'}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getTrendIcon(asset.direction ?? 'NO TREND')}
                      <span className={`font-mono text-2xs ${getTrendColor(asset.direction ?? 'NO TREND')}`}>
                        {(asset.direction ?? 'N').charAt(0)}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    {asset.contradiction ? (
                      <span className="signal-tag warning">Divergence</span>
                    ) : (
                      <span className="signal-tag bullish">Confirmed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Interpretation */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Trend Regime</div>
          <p className="text-xs text-text-secondary">
            {data.summary.overallTrendRegime === 'Bullish' && 'Broad-based uptrends across asset classes suggest positive momentum regime.'}
            {data.summary.overallTrendRegime === 'Bearish' && 'Broad-based downtrends across asset classes suggest negative momentum regime.'}
            {data.summary.overallTrendRegime === 'Mixed' && 'Mixed trend signals with conflicting momentum across asset classes.'}
            {data.summary.contradictions > 0 && ` ${data.summary.contradictions} asset(s) contradict regime expectations.`}
          </p>
          {/* FIXED: BUG-C2 - Add divergence warning when CTA contradicts macro regime */}
          {(data.contradictions?.length ?? 0) > 0 && (
            <div className="text-amber text-xs mt-2">
              ⚠ {data.contradictions.length} asset(s) contradict Slowdown regime —
              momentum may be running ahead of macro fundamentals.
              Consider reducing CTA weight vs macro signal.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Phase 8 — Pure Alpha Signals Section (Redesigned)
// Factor-based alpha signals with terminal aesthetic

import { Sparkles, TrendingUp, TrendingDown, Minus, Zap } from 'lucide-react';
import type { PureAlphaData } from '@/types';

interface PureAlphaSectionProps {
  data?: PureAlphaData;
}

export function PureAlphaSection({ data }: PureAlphaSectionProps) {
  if (!data) return null;

  const getDirectionIcon = (direction: string) => {
    switch (direction) {
      case 'long':
        return <TrendingUp className="w-3 h-3 text-green" />;
      case 'short':
        return <TrendingDown className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };


  const getStrengthTag = (strength: string) => {
    switch (strength) {
      case 'strong':
        return 'signal-tag bullish';
      case 'moderate':
        return 'signal-tag warning';
      case 'weak':
        return 'signal-tag neutral';
      default:
        return 'signal-tag neutral';
    }
  };

  // Sort signals by strength and conviction
  const sortedSignals = [...data.signals].sort((a, b) => {
    const strengthOrder = { strong: 3, moderate: 2, weak: 1 };
    const strengthDiff =
      strengthOrder[b.strength as keyof typeof strengthOrder] -
      strengthOrder[a.strength as keyof typeof strengthOrder];
    return strengthDiff !== 0 ? strengthDiff : b.confidence - a.confidence;
  });

  return (
    <div id="pure-alpha" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">34</span>
          <h2 className="section-title">Pure Alpha</h2>
          <span className="section-meta">{data.regime.toUpperCase()}</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Composite Score Header */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-3 h-3 text-text-secondary" />
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider">
                  Composite Score
                </div>
                <div className="flex items-baseline gap-2">
                  <span className={`text-xl font-bold font-mono ${
                    data.compositeScore > 0.6 ? 'text-green' : data.compositeScore > 0.3 ? 'text-amber' : 'text-text-secondary'
                  }`}>
                    {data.compositeScore.toFixed(2)}
                  </span>
                  <span className={data.regime === 'expansion' ? 'signal-tag bullish' : 'signal-tag bearish'}>
                    {data.regime}
                  </span>
                </div>
              </div>
            </div>

            <div className="text-right">
              <div className="text-2xs text-text-tertiary mb-0.5">Top Ideas</div>
              <div className="flex flex-wrap gap-1 justify-end">
                {data.topIdeas.slice(0, 3).map((idea, idx) => (
                  <span key={idx} className="signal-tag neutral text-2xs">
                    {idea}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Composite Gauge */}
          <div className="mt-2">
            <div className="h-1 bg-surface-4">
              <div
                className="h-full bg-bloomberg"
                style={{ width: `${data.compositeScore * 100}%` }}
              />
            </div>
          </div>
        </div>

        {/* Signals Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">Factor Signals</span>
          </div>
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Factor</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Dir</th>
                <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Z</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">%</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Str</th>
              </tr>
            </thead>
            <tbody>
              {sortedSignals.map((signal) => (
                <tr key={signal.name} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 px-3">
                    <div>
                      <div className="text-xs font-medium text-text-primary">{signal.name}</div>
                      <div className="text-2xs text-text-tertiary capitalize">{signal.category}</div>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getDirectionIcon(signal.direction)}
                    </div>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <span className={`font-mono text-xs ${signal.zScore > 0 ? 'text-green' : 'text-red'}`}>
                      {signal.zScore > 0 ? '+' : ''}{signal.zScore.toFixed(2)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      <div className="w-8 h-1 bg-surface-4">
                        <div className="h-full bg-bloomberg" style={{ width: `${signal.percentile}%` }} />
                      </div>
                      <span className="text-2xs text-text-tertiary">{signal.percentile}</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={getStrengthTag(signal.strength)}>
                      {signal.strength.charAt(0).toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Regime Context */}
        <div className={`p-3 border ${data.regime === 'expansion' ? 'bg-green-dim border-green' : 'bg-red-dim border-red'}`}>
          <div className="flex items-center gap-2 mb-1">
            <Zap className={`w-3 h-3 ${data.regime === 'expansion' ? 'text-green' : 'text-red'}`} />
            <span className={`text-xs font-medium ${data.regime === 'expansion' ? 'text-green' : 'text-red'}`}>
              Alpha Regime: {data.regime}
            </span>
          </div>
          <p className="text-xs text-text-secondary">
            {data.regime === 'expansion'
              ? 'Factor-based alpha signals are strong. Value, momentum, and carry factors are exhibiting positive risk-adjusted returns.'
              : 'Factor-based alpha signals are weakening. Defensive positioning recommended. Consider reducing factor exposure.'}
          </p>
        </div>
      </div>
    </div>
  );
}

// Phase 8 — Liquidity Conditions Section (Redesigned)
// Liquidity conditions with terminal aesthetic

import { Droplets, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { ComputedTag } from '@/components/ui/ComputedTag';
import type { LiquidityConditionsData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface LiquiditySectionProps {
  data?: LiquidityConditionsData;
}

export function LiquiditySection({ data }: LiquiditySectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["liquidity"] as any;

  if (!data) return null;

  // Backend payload is {liquidityScore, regime, indicators:[{name,value,status,
  // contribution}]}; map it onto the shape this view renders (compositeScore,
  // indicators with trend/formatted/zScore) so real values show instead of crashing.
  const anyData = data as any;
  const compositeScore = anyData.compositeScore ?? anyData.liquidityScore ?? 0;
  const indicators = (anyData.indicators ?? []).map((i: any) => ({
    name: i.name,
    trend: i.trend ?? i.status ?? 'neutral',
    formatted: i.formatted ?? (i.value != null ? String(i.value) : '—'),
    zScore: typeof i.zScore === 'number' ? i.zScore : (typeof i.contribution === 'number' ? i.contribution : 0),
    interpretation: i.interpretation ?? i.status ?? '',
  }));
  const fedPolicyStance = anyData.fedPolicyStance;
  const creditAvailability = anyData.creditAvailability;

  const getTrendIcon = (trend: string) => {
    switch (trend.toLowerCase()) {
      case 'easing':
        return <TrendingUp className="w-3 h-3 text-green" />;
      case 'tightening':
        return <TrendingDown className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getStatusTag = (regime: string) => {
    switch (regime.toLowerCase()) {
      case 'easy':
        return 'signal-tag bullish';
      case 'tight':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  return (
    <div id="liquidity" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Liquidity Conditions</h2>
          <span className="section-meta">{data.regime.toUpperCase()}</span>
        </div>
        <ComputedTag section="liquidity" />
      </div>

      <div className="space-y-3">
        {/* Composite Score */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Droplets className="w-3 h-3 text-text-secondary" />
              <div>
                <div className="text-2xs text-text-tertiary">Composite Score</div>
                <div className={`text-xl font-mono font-bold ${compositeScore > 0 ? 'text-green' : compositeScore < 0 ? 'text-red' : 'text-text-secondary'}`}>
                  {compositeScore >= 0 ? '+' : ''}{Number(compositeScore).toFixed(2)}σ
                </div>
              </div>
            </div>
            <span className={getStatusTag(data.regime)}>
              {data.regime}
            </span>
          </div>
        </div>

        {/* Indicators Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {indicators.map((indicator: any) => (
            <div key={indicator.name} className="p-2 bg-surface-1 border border-border">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-text-primary">{indicator.name}</span>
                {getTrendIcon(indicator.trend)}
              </div>
              <div className="flex items-baseline gap-2 mb-1">
                <span className="text-base font-mono font-bold text-text-primary">{indicator.formatted}</span>
                <span className={`text-2xs font-mono ${indicator.zScore > 0 ? 'text-green' : indicator.zScore < 0 ? 'text-red' : 'text-text-tertiary'}`}>
                  ({indicator.zScore >= 0 ? '+' : ''}{indicator.zScore.toFixed(2)}σ)
                </span>
              </div>
              <p className="text-2xs text-text-secondary">{indicator.interpretation}</p>
            </div>
          ))}
        </div>

        {/* Policy Stance (only when the backend provides these fields) */}
        {(fedPolicyStance || creditAvailability) && (
          <div className="grid grid-cols-2 gap-2">
            {fedPolicyStance && (
              <div className="p-2 bg-surface-1 border border-border">
                <div className="text-2xs text-text-tertiary mb-1">Fed Policy</div>
                <div className={`text-sm font-medium ${fedPolicyStance === 'Restrictive' ? 'text-red' : fedPolicyStance === 'Accommodative' ? 'text-green' : 'text-text-primary'}`}>
                  {fedPolicyStance}
                </div>
              </div>
            )}
            {creditAvailability && (
              <div className="p-2 bg-surface-1 border border-border">
                <div className="text-2xs text-text-tertiary mb-1">Credit</div>
                <div className={`text-sm font-medium ${creditAvailability === 'Tight' ? 'text-red' : creditAvailability === 'Easy' ? 'text-green' : 'text-text-primary'}`}>
                  {creditAvailability}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

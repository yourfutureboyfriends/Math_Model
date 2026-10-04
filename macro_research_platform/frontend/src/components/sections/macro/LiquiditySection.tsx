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
    // A genuine z-score when provided; `contribution` is the component's WEIGHT in the
    // model score (it was rendered as "+0.60σ").
    zScore: typeof i.zScore === 'number' ? i.zScore : null,
    weight: typeof i.contribution === 'number' ? i.contribution : null,
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
          <h2 className="section-title">Financial Conditions</h2>
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
                <div className="text-2xs text-text-tertiary">Model score (0–1)</div>
                <div className={`text-xl font-mono font-bold ${compositeScore > 0 ? 'text-green' : compositeScore < 0 ? 'text-red' : 'text-text-secondary'}`}>
                  {Number(compositeScore).toFixed(2)}
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
                {indicator.zScore != null && (
                  <span className={`text-2xs font-mono ${indicator.zScore > 0 ? 'text-green' : indicator.zScore < 0 ? 'text-red' : 'text-text-tertiary'}`}>
                    ({indicator.zScore >= 0 ? '+' : ''}{indicator.zScore.toFixed(2)}σ)
                  </span>
                )}
                <span className="text-2xs font-mono text-text-tertiary">
                  {indicator.weight != null ? `${Math.round(indicator.weight * 100)}% of model score` : 'reference index'}
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
                <div className="text-2xs text-text-tertiary mb-1">Fed policy</div>
                <div className={`text-sm font-medium ${fedPolicyStance === 'Tightening' ? 'text-red' : fedPolicyStance === 'Easing' ? 'text-green' : 'text-text-primary'}`}>
                  {fedPolicyStance}
                </div>
                {anyData.fedLastMove && (
                  <div className="text-2xs text-text-tertiary font-mono">
                    Target upper {anyData.fedTargetUpper?.toFixed(2)}% · last move {anyData.fedLastMove.bp > 0 ? '+' : ''}{anyData.fedLastMove.bp}bp on {anyData.fedLastMove.date}
                  </div>
                )}
              </div>
            )}
            {creditAvailability && (
              <div className="p-2 bg-surface-1 border border-border">
                <div className="text-2xs text-text-tertiary mb-1">Credit availability</div>
                <div className={`text-sm font-medium ${creditAvailability === 'Tight' ? 'text-red' : creditAvailability === 'Ample' ? 'text-green' : 'text-text-primary'}`}>
                  {creditAvailability}
                </div>
                {anyData.hyOas != null && <div className="text-2xs text-text-tertiary font-mono">US HY OAS {anyData.hyOas.toFixed(2)}%</div>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

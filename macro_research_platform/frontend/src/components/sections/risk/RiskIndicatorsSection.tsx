// Phase 8 — Risk Indicators Section (Redesigned)
// Risk table with geopolitical integration

import { cn } from '@/lib/utils';
import { Shield, AlertTriangle, Globe } from 'lucide-react';
import { AnimatedValue, SkeletonCard } from '@/components/ui';
import type { RiskIndicatorsData, GeopoliticalRiskData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface RiskIndicatorsSectionProps {
  data?: RiskIndicatorsData;
  geopoliticalData?: GeopoliticalRiskData;
}

export function RiskIndicatorsSection({ data, geopoliticalData }: RiskIndicatorsSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["riskIndicators"] as any;

  if (!data) {
    return (
      <div id="risk-indicators" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">12</span>
            <h2 className="section-title">Risk Indicators</h2>
          </div>
        </div>
        <SkeletonCard />
      </div>
    );
  }

  const getRiskTag = (level: string) => {
    switch (level) {
      case 'low':
        return 'signal-tag bullish';
      case 'medium':
        return 'signal-tag warning';
      case 'high':
      case 'extreme':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const getCompositeColor = (score: number) => {
    if (score >= 7) return 'text-red';
    if (score >= 4) return 'text-amber';
    return 'text-green';
  };

  // The backend riskIndicators payload is {vix, vixState, yieldSpread, creditSpread,
  // riskScore, riskState}. Map it onto the shape this view renders (compositeScore,
  // regime label, indicators table) so it shows the real values instead of crashing.
  const anyData = data as any;
  const compositeScore = anyData.compositeScore ?? anyData.riskScore ?? 0;
  const regimeLabel = anyData.regime ?? anyData.riskState ?? 'Unknown';
  const indicators = (anyData.indicators?.length ? anyData.indicators : [
    anyData.vix != null && { name: 'VIX', value: Number(anyData.vix).toFixed(1),
      level: /extreme/i.test(anyData.vixState) ? 'extreme' : /high|elevated/i.test(anyData.vixState) ? 'high' : /low/i.test(anyData.vixState) ? 'low' : 'medium' },
    anyData.yieldSpread != null && { name: 'Yield Spread (10Y-2Y)', value: `${Number(anyData.yieldSpread).toFixed(2)}%`,
      level: anyData.yieldSpread < 0 ? 'high' : anyData.yieldSpread < 0.5 ? 'medium' : 'low' },
    anyData.creditSpread != null && { name: 'Credit Spread', value: `${Number(anyData.creditSpread).toFixed(2)}%`,
      level: anyData.creditSpread > 4 ? 'high' : anyData.creditSpread > 2.5 ? 'medium' : 'low' },
  ].filter(Boolean)) as Array<{ name: string; value: any; level: string }>;

  return (
    <div id="risk-indicators" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">12</span>
          <h2 className="section-title">Risk Indicators</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Geopolitical Risk Panel */}
        {geopoliticalData && (
          <div className={cn(
            'p-3 border',
            geopoliticalData.tailRiskLevel === 'Extreme' ? 'bg-red-dim border-red' :
            geopoliticalData.tailRiskLevel === 'Elevated' ? 'bg-amber-dim border-amber' :
            'bg-surface-2 border-border'
          )}>
            <div className="flex items-center gap-2 mb-2">
              <Globe className="w-3 h-3 text-text-secondary" />
              <span className="text-2xs text-text-secondary uppercase tracking-wider">Geopolitical Risk</span>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <div className="text-2xs text-text-tertiary">Tail Risk Score</div>
                <div className={cn(
                  'text-lg font-mono font-bold',
                  geopoliticalData.tailRiskLevel === 'Extreme' ? 'text-red' :
                  geopoliticalData.tailRiskLevel === 'Elevated' ? 'text-amber' : 'text-text-primary'
                )}>
                  <AnimatedValue value={geopoliticalData.tailRiskScore} decimals={2} suffix="σ" />
                </div>
              </div>
              <span className={getRiskTag(geopoliticalData.tailRiskLevel.toLowerCase())}>
                {geopoliticalData.tailRiskLevel.toUpperCase()}
              </span>
            </div>

            {geopoliticalData.confidenceAdjustment > 1.0 && (
              <div className="mt-2 text-2xs text-amber">
                Confidence widened by {((geopoliticalData.confidenceAdjustment - 1) * 100).toFixed(0)}%
              </div>
            )}
          </div>
        )}

        {/* Composite Score */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-text-secondary" />
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider">Composite Risk</div>
                <div className={cn('text-xl font-mono font-bold', getCompositeColor(compositeScore))}>
                  <AnimatedValue value={compositeScore} decimals={2} />
                </div>
              </div>
            </div>
            <span className={getRiskTag(String(regimeLabel).toLowerCase())}>
              {String(regimeLabel).toUpperCase()}
            </span>
          </div>
        </div>

        {/* Indicators Table */}
        {indicators?.length > 0 && (
          <div className="border border-border bg-surface-1 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-surface-2">
                  <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Indicator</th>
                  <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Value</th>
                  <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Level</th>
                </tr>
              </thead>
              <tbody>
                {(indicators ?? []).map((item) => (
                  <tr key={item.name} className="border-b border-border-subtle last:border-0 hover:bg-surface-3 transition-colors">
                    <td className="py-2 px-3 text-sm text-text-primary">{item.name}</td>
                    <td className="py-2 px-3 text-right font-mono text-sm text-text-primary">{item.value}</td>
                    <td className="py-2 px-3 text-center">
                      <span className={getRiskTag(item.level)}>
                        {String(item.level).charAt(0).toUpperCase() + String(item.level).slice(1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Warning */}
        <div className="flex items-start gap-2 p-2 bg-red-dim border border-red">
          <AlertTriangle className="w-3 h-3 text-red flex-shrink-0 mt-0.5" />
          <p className="text-2xs text-text-secondary">
            Risk indicators are based on current market conditions. Always consider multiple signals before making investment decisions.
          </p>
        </div>
      </div>
    </div>
  );
}

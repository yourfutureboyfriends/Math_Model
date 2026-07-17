// Phase 8 — Anomaly Detection Section (Redesigned)
// Isolation Forest results with terminal aesthetic

import { cn } from '@/lib/utils';
import { AlertTriangle, Activity, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { AnomalyDetectionData, AnomalousFeature } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface AnomalyDetectionSectionProps {
  data?: AnomalyDetectionData;
}

export function AnomalyDetectionSection({ data: dataProp }: AnomalyDetectionSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  let data = dataProp;
  if (!data) data = (_fullDash as any)?.anomalyDetection as any;
  if (!data) return null;

  const getSeverityTag = (severity: string) => {
    switch (severity) {
      case 'Critical':
      case 'High':
        return 'signal-tag bearish';
      case 'Moderate':
        return 'signal-tag warning';
      default:
        return 'signal-tag neutral';
    }
  };

  const FeatureRow = ({ feature }: { feature: AnomalousFeature }) => (
    <div className="flex items-center justify-between py-1.5 border-b border-border-subtle last:border-0">
      <div className="flex-1">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-text-primary capitalize">
            {feature.feature.replace(/_/g, ' ')}
          </span>
          {feature.zscore > 2 ? (
            <TrendingUp className="w-3 h-3 text-red" />
          ) : feature.zscore < -2 ? (
            <TrendingDown className="w-3 h-3 text-red" />
          ) : (
            <Minus className="w-3 h-3 text-text-tertiary" />
          )}
        </div>
        <div className="text-2xs text-text-tertiary">{feature.interpretation}</div>
      </div>
      <div className="text-right">
        <div className="text-xs font-mono text-text-primary">
          {feature.currentValue.toFixed(2)}
        </div>
        <div className="text-2xs font-mono text-text-secondary">
          z={feature.zscore > 0 ? '+' : ''}{feature.zscore.toFixed(2)}
        </div>
      </div>
    </div>
  );

  const anomalyPercent = Math.min(100, Math.max(0, data.anomalyScore * 100));
  const getBarColor = () => {
    if (data.anomalyScore >= 0.7) return 'bg-red';
    if (data.anomalyScore >= 0.5) return 'bg-amber';
    return 'bg-green';
  };

  return (
    <div id="anomaly-detection" className="terminal-section">
      {/* Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">ML</span>
          <h2 className="section-title">Anomaly Detection</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Anomaly Score */}
        <div className={cn(
          'p-3 border',
          data.isAnomaly ? 'bg-red-dim border-red' : 'bg-surface-1 border-border'
        )}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              {data.isAnomaly ? (
                <AlertTriangle className="w-4 h-4 text-red" />
              ) : (
                <Activity className="w-4 h-4 text-green" />
              )}
              <span className="text-xs font-medium text-text-primary">
                {data.isAnomaly ? 'ANOMALY DETECTED' : 'NORMAL'}
              </span>
            </div>
            <span className={getSeverityTag(data.severity)}>
              {data.severity.toUpperCase()}
            </span>
          </div>

          <div className="mb-2">
            <div className="flex items-center justify-between text-2xs text-text-tertiary mb-1">
              <span>Anomaly Score</span>
              <span className="font-mono">{(data.anomalyScore * 100).toFixed(1)}%</span>
            </div>
            <div className="h-1.5 bg-surface-4">
              <div
                className={cn('h-full transition-all duration-500', getBarColor())}
                style={{ width: `${anomalyPercent}%` }}
              />
            </div>
          </div>

          <p className="text-2xs text-text-secondary">{data.interpretation}</p>
        </div>

        {/* Anomalous Features */}
        {data.anomalousFeatures && data.anomalousFeatures.length > 0 && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-red uppercase tracking-wider">
                Anomalous ({(data.anomalousFeatures ?? []).length})
              </span>
            </div>
            <div className="p-2">
              {(data.anomalousFeatures ?? []).map((feature) => (
                <FeatureRow key={feature.feature} feature={feature} />
              ))}
            </div>
          </div>
        )}

        {/* Normal Features */}
        {data.normalFeatures && data.normalFeatures.length > 0 && (
          <div>
            <div className="text-2xs text-green uppercase tracking-wider mb-1">
              Normal Features ({data.normalFeatures.length})
            </div>
            <div className="flex flex-wrap gap-1">
              {data.normalFeatures.slice(0, 8).map((feature) => (
                <span
                  key={feature}
                  className="px-1.5 py-0.5 text-2xs bg-surface-2 border border-border text-text-secondary"
                >
                  {feature.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Regime Implication */}
        <div className="p-2 border border-border bg-surface-1">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
            Regime Implication
          </div>
          <p className="text-2xs text-text-secondary">{data.regimeImplication}</p>
        </div>
      </div>
    </div>
  );
}

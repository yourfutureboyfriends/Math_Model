// Phase 8 — Performance Tracking Section (Redesigned)
// Model accuracy metrics with terminal aesthetic

import { TrendingUp, RotateCcw, Target, Clock } from 'lucide-react';
import type { PerformanceTrackingData, WeightAdaptation } from '@/types';

interface PerformanceTrackingSectionProps {
  data?: PerformanceTrackingData;
}

export function PerformanceTrackingSection({ data }: PerformanceTrackingSectionProps) {
  if (!data) return null;

  const getAccuracyColor = (accuracy: number | null) => {
    if (accuracy === null) return 'text-text-secondary';
    if (accuracy >= 0.75) return 'text-green';
    if (accuracy >= 0.6) return 'text-amber';
    if (accuracy >= 0.45) return 'text-amber';
    return 'text-red';
  };

  const getAccuracyTag = (accuracy: number | null) => {
    if (accuracy === null) return 'signal-tag neutral';
    if (accuracy >= 0.75) return 'signal-tag bullish';
    if (accuracy >= 0.6) return 'signal-tag bullish';
    if (accuracy >= 0.45) return 'signal-tag warning';
    return 'signal-tag bearish';
  };

  const getAccuracyLabel = (accuracy: number | null) => {
    if (accuracy === null) return 'N/A';
    if (accuracy >= 0.75) return 'Exc';
    if (accuracy >= 0.6) return 'Good';
    if (accuracy >= 0.45) return 'Mod';
    return 'Poor';
  };

  // Prepare model accuracy data
  const accuracyData = Object.entries(data.modelAccuracies || {})
    .map(([model, accuracy]) => ({
      model,
      accuracy: (accuracy || 0) * 100,
      colorClass: getAccuracyColor(accuracy)
    }))
    .sort((a, b) => b.accuracy - a.accuracy);

  return (
    <div id="performance" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">14</span>
          <h2 className="section-title">Performance Tracking</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Header Stats */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="w-3 h-3 text-text-secondary" />
              <span className="text-2xs text-text-tertiary uppercase">Period</span>
            </div>
            <div className="text-sm font-mono text-text-primary">{data.trackingPeriod}</div>
            <div className="text-2xs text-text-tertiary">{data.totalPredictions} predictions</div>
          </div>

          <div className="p-2 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-1">
              <Target className="w-3 h-3 text-text-secondary" />
              <span className="text-2xs text-text-tertiary uppercase">Regime Accuracy</span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className={`text-sm font-mono ${data.regimeAccuracy !== null ? 'text-text-primary' : 'text-text-secondary'}`}>
                {data.regimeAccuracy !== null ? `${(data.regimeAccuracy * 100).toFixed(1)}%` : 'N/A'}
              </span>
              {data.regimeAccuracy !== null && (
                <span className={getAccuracyTag(data.regimeAccuracy)}>
                  {getAccuracyLabel(data.regimeAccuracy)}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Ensemble Calibration */}
        {data.ensembleCalibration && (
          <div className="grid grid-cols-2 gap-2">
            <div className={`p-2 border ${data.ensembleCalibration.riskOnAccuracy !== null && data.ensembleCalibration.riskOnAccuracy >= 0.6 ? 'bg-green-dim border-green' : 'bg-surface-1 border-border'}`}>
              <div className="text-2xs text-text-tertiary uppercase mb-1">Risk-On Acc</div>
              <div className="text-lg font-mono text-text-primary">
                {data.ensembleCalibration.riskOnAccuracy !== null
                  ? `${(data.ensembleCalibration.riskOnAccuracy * 100).toFixed(1)}%`
                  : 'N/A'}
              </div>
            </div>
            <div className={`p-2 border ${data.ensembleCalibration.riskOffAccuracy !== null && data.ensembleCalibration.riskOffAccuracy >= 0.6 ? 'bg-green-dim border-green' : 'bg-surface-1 border-border'}`}>
              <div className="text-2xs text-text-tertiary uppercase mb-1">Risk-Off Acc</div>
              <div className="text-lg font-mono text-text-primary">
                {data.ensembleCalibration.riskOffAccuracy !== null
                  ? `${(data.ensembleCalibration.riskOffAccuracy * 100).toFixed(1)}%`
                  : 'N/A'}
              </div>
            </div>
          </div>
        )}

        {/* Model Accuracies */}
        {accuracyData.length > 0 && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Model Accuracies</span>
            </div>
            <div className="p-2 space-y-1">
              {accuracyData.map((item) => (
                <div key={item.model} className="flex items-center justify-between">
                  <span className="text-xs text-text-primary">{item.model.slice(0, 12)}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1 bg-surface-4">
                      <div className={`h-full ${item.colorClass.replace('text-', 'bg-')}`} style={{ width: `${Math.min(100, item.accuracy)}%` }} />
                    </div>
                    <span className={`font-mono text-xs w-12 text-right ${item.colorClass}`}>
                      {item.accuracy.toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Weight Adaptations */}
        {data.weightAdaptations && data.weightAdaptations.length > 0 && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 flex items-center gap-2">
              <RotateCcw className="w-3 h-3 text-amber" />
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Weight Adaptations</span>
            </div>
            <div className="p-2 space-y-1">
              {data.weightAdaptations.map((adaptation: WeightAdaptation, idx: number) => (
                <div key={`${adaptation.model}-${idx}`} className="p-2 bg-surface-2 border border-border-subtle">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-medium text-text-primary">{adaptation.model}</span>
                    <div className="flex items-center gap-1 text-xs">
                      <span className="text-text-tertiary">{(adaptation.oldWeight * 100).toFixed(1)}%</span>
                      <TrendingUp className="w-3 h-3 text-text-tertiary" />
                      <span className={`font-mono ${adaptation.newWeight > adaptation.oldWeight ? 'text-green' : 'text-red'}`}>
                        {(adaptation.newWeight * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <div className="text-2xs text-text-secondary">{adaptation.reason}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Performance Note */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Note</div>
          <p className="text-xs text-text-secondary">{data.note}</p>
        </div>
      </div>
    </div>
  );
}

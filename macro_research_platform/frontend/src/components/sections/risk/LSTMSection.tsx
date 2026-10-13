// Phase 8 — LSTM Regime Prediction Section (Redesigned)
// LSTM-based regime transition probabilities

import { cn } from '@/lib/utils';
import { Brain, AlertCircle } from 'lucide-react';
import type { LSTMPredictionData, LSTMPrediction } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface LSTMSectionProps {
  data?: LSTMPredictionData;
}

export function LSTMSection({ data: dataProp }: LSTMSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  let data = dataProp;
  if (!data) data = (_fullDash as any)?.lstmPrediction as any;
  if (!data?.lstmPrediction) return null;

  const prediction: LSTMPrediction = data.lstmPrediction;

  const getConfidenceTag = (confidence: string) => {
    switch (confidence) {
      case 'High':
        return 'signal-tag bullish';
      case 'Medium':
        return 'signal-tag warning';
      default:
        return 'signal-tag neutral';
    }
  };

  const getRegimeColor = (regime: string) => {
    if (regime.includes('Risk-On') || regime.includes('Expansion')) return 'text-green';
    if (regime.includes('Risk-Off') || regime.includes('Contraction')) return 'text-red';
    return 'text-text-secondary';
  };

  const chartData = Object.entries(prediction.blendedProbabilities || {})
    .map(([regime, prob]) => ({
      regime: regime.replace(/_/g, ' '),
      probability: prob * 100,
    }))
    .sort((a, b) => b.probability - a.probability);

  return (
    <div id="lstm" className="terminal-section">
      {/* Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">ML</span>
          <h2 className="section-title">LSTM Prediction</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Prediction Header */}
        <div className={cn(
          'p-3 border',
          prediction.transitionWarning ? 'bg-amber-dim border-amber' : 'bg-surface-1 border-border'
        )}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-purple" />
              <span className="text-xs font-medium text-text-primary">LSTM Forecast</span>
            </div>
            <span className={getConfidenceTag(prediction.confidence)}>
              {prediction.confidence.toUpperCase()}
            </span>
          </div>

          {/* Predicted Regime */}
          <div className="mb-2">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
              Predicted Next Regime
            </div>
            <div className="flex items-center gap-2">
              <span className={cn('text-lg font-mono font-bold', getRegimeColor(prediction.predictedNextRegime))}>
                {prediction.predictedNextRegime.replace(/_/g, ' ')}
              </span>
              {prediction.transitionWarning && (
                <AlertCircle className="w-4 h-4 text-amber" />
              )}
            </div>
          </div>

          {/* Current Regime Probability */}
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">Current P</div>
              <div className="text-sm font-mono text-text-primary">
                {prediction.currentRegimeProb
                  ? `${(prediction.currentRegimeProb * 100).toFixed(1)}%`
                  : 'N/A'}
              </div>
            </div>
            {prediction.trainedSteps && (
              <div className="text-right">
                <div className="text-2xs text-text-tertiary uppercase tracking-wider">Steps</div>
                <div className="text-sm font-mono text-text-primary">{prediction.trainedSteps}</div>
              </div>
            )}
          </div>
        </div>

        {/* Transition Warning */}
        {prediction.transitionWarning && (
          <div className="p-2 bg-red-dim border border-red flex items-start gap-2">
            <AlertCircle className="w-3 h-3 text-red flex-shrink-0 mt-0.5" />
            <div>
              <div className="text-xs font-medium text-red">Transition Warning</div>
              <p className="text-2xs text-text-secondary">
                LSTM predicts potential regime change
              </p>
            </div>
          </div>
        )}

        {/* Probability Distribution */}
        {chartData.length > 0 && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">
                Probabilities
              </span>
            </div>
            <div className="p-2 space-y-1">
              {chartData.map((item) => (
                <div key={item.regime} className="flex items-center justify-between">
                  <span className="text-xs text-text-secondary truncate flex-1">
                    {item.regime}
                  </span>
                  <div className="flex items-center gap-2 w-24">
                    <div className="flex-1 h-1 bg-surface-4">
                      <div
                        className="h-full bg-bloomberg"
                        style={{ width: `${item.probability}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono text-text-primary w-10 text-right">
                      {item.probability.toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Model Note */}
        <div className="p-2 border border-border bg-surface-1">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Model Note</div>
          <p className="text-2xs text-text-secondary">{prediction.modelNote}</p>
        </div>
      </div>
    </div>
  );
}

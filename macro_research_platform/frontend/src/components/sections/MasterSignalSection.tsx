// Phase 8 — Master Signal Section (Redesigned)
// The centrepiece. Full-width, height 88px.

import { Activity } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { EnsembleSignalData } from '@/types';

interface MasterSignalSectionProps {
  data?: EnsembleSignalData;
}

export function MasterSignalSection({ data }: MasterSignalSectionProps) {
  if (!data) {
    return (
      <div className="h-22 bg-surface-2 border-b border-border p-4">
        <div className="flex items-center gap-2 text-text-tertiary">
          <Activity className="w-4 h-4 animate-pulse" />
          <span className="text-xs">Initializing ensemble models...</span>
        </div>
      </div>
    );
  }

  const getSignalColor = (signal: string) => {
    if (signal.includes('Strong Bullish') || signal.includes('Risk-On')) {
      return { color: 'text-green', bg: 'bg-green', border: 'border-green' };
    }
    if (signal.includes('Bullish')) {
      return { color: 'text-green', bg: 'bg-green', border: 'border-green' };
    }
    if (signal.includes('Strong Bearish') || signal.includes('Risk-Off')) {
      return { color: 'text-red', bg: 'bg-red', border: 'border-red' };
    }
    if (signal.includes('Bearish')) {
      return { color: 'text-red', bg: 'bg-red', border: 'border-red' };
    }
    return { color: 'text-text-secondary', bg: 'bg-text-tertiary', border: 'border-text-tertiary' };
  };

  const signalColors = getSignalColor(data.ensembleSignal);
  const score = data.ensembleScore;

  // Calculate position on -1 to +1 scale
  // Score is already normalized, we just need to map to percentage
  const scalePosition = ((score + 1) / 2) * 100;

  // Model agreement dots - 15 models
  const modelDots = data.modelBreakdown?.slice(0, 15).map((m: any) => ({
    signal: m.signal,
    color: m.signal.includes('Bullish') || m.signal.includes('Risk-On') ? 'green' :
           m.signal.includes('Bearish') || m.signal.includes('Risk-Off') ? 'red' : 'neutral'
  })) || [];

  return (
    <div className="h-22 bg-surface-2 border-b border-border">
      <div className="h-full flex items-center px-4 gap-6">
        {/* Left: Ensemble Signal */}
        <div className="w-44 flex-shrink-0">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
            ENSEMBLE SIGNAL
          </div>
          <div className={cn('text-xl font-mono font-bold', signalColors.color)}>
            {data.ensembleSignal}
          </div>
          <div className="text-xs text-text-secondary mt-0.5">
            {data.adaptiveWeightingActive ? '15 models · Adaptive' : '15 models · Static'}
          </div>
        </div>

        {/* Center: Score Scale Bar */}
        <div className="flex-1 max-w-md">
          <div className="flex items-center justify-between text-2xs text-text-tertiary mb-1">
            <span>STRONG RISK-OFF</span>
            <span>RISK-OFF</span>
            <span className="text-text-secondary">NEUTRAL</span>
            <span>RISK-ON</span>
            <span>STRONG RISK-ON</span>
          </div>

          {/* Scale track */}
          <div className="relative h-1 bg-surface-4">
            {/* Tick marks */}
            <div className="absolute inset-0 flex justify-between pointer-events-none">
              {[0, 25, 50, 75, 100].map((pos) => (
                <div
                  key={pos}
                  className="w-px h-2 -mt-0.5 bg-border-strong"
                  style={{ marginLeft: pos === 0 ? 0 : undefined, marginRight: pos === 100 ? 0 : undefined }}
                />
              ))}
            </div>

            {/* Position marker */}
            <div
              className={cn(
                'absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-surface-2 transition-all duration-500',
                score > 0 ? 'bg-green' : 'bg-red'
              )}
              style={{ left: `${scalePosition}%`, transform: `translate(-50%, -50%)` }}
            />
          </div>

          <div className="flex items-center justify-between text-xs mt-2">
            <span className={cn('font-mono font-bold', score < 0 ? signalColors.color : 'text-text-tertiary')}>
              {score < 0 ? `${score.toFixed(2)} score` : '—'}
            </span>
            <span className={cn('font-mono font-bold', score > 0 ? signalColors.color : 'text-text-tertiary')}>
              {score > 0 ? `+${score.toFixed(2)} score` : '—'}
            </span>
          </div>
        </div>

        {/* Right: Metrics */}
        <div className="flex items-center gap-6">
          {/* Conviction */}
          <div className="text-right">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
              CONVICTION
            </div>
            <div className="text-sm font-mono font-bold text-text-primary">
              {data.conviction.toUpperCase()}
            </div>
          </div>

          {/* Agreement */}
          <div className="text-right">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
              AGREEMENT
            </div>
            <div className={cn(
              'text-sm font-mono font-bold',
              data.agreementRatio >= 0.8 ? 'text-green' :
              data.agreementRatio >= 0.6 ? 'text-amber' : 'text-red'
            )}>
              {(data.agreementRatio * 100).toFixed(0)}%
            </div>
          </div>

          {/* Risk Budget */}
          <div className="text-right">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
              RISK BUDGET
            </div>
            <div className="text-sm font-mono font-bold text-text-primary">
              {data.riskBudgetFinal.toFixed(2)}x
            </div>
          </div>

          {/* Model Agreement Dots */}
          <div className="text-right">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
              MODEL ALIGNMENT
            </div>
            <div className="flex gap-1">
              {modelDots.map((dot, i) => (
                <div
                  key={i}
                  className={cn(
                    'w-2 h-2 rounded-full',
                    dot.color === 'green' ? 'bg-green' :
                    dot.color === 'red' ? 'bg-red' : 'bg-text-tertiary'
                  )}
                  title={dot.signal}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

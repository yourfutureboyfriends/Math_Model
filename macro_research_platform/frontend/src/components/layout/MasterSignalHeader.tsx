// Phase 8 Task 44 — Master Signal Dashboard Header
// Prominent display of ensemble signal with key metrics

import { Activity, Zap, TrendingUp, TrendingDown, Minus, Target, Users } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import type { EnsembleSignalData } from '@/types';

interface MasterSignalHeaderProps {
  data?: EnsembleSignalData;
}

export function MasterSignalHeader({ data }: MasterSignalHeaderProps) {
  if (!data) {
    return (
      <div className="bg-terminal-elevated border-y border-terminal-border px-6 py-3">
        <div className="flex items-center justify-center gap-2 text-text-muted">
          <Activity className="w-4 h-4 animate-pulse" />
          <span className="text-sm">Initializing ensemble models...</span>
        </div>
      </div>
    );
  }

  const getSignalStyles = (signal: string) => {
    if (signal.includes('Strong Bullish') || signal.includes('Risk-On')) {
      return {
        bg: 'bg-green-dim border-green',
        text: 'text-green',
        icon: TrendingUp,
        pulse: true,
      };
    }
    if (signal.includes('Bullish')) {
      return {
        bg: 'bg-green-dim border-green',
        text: 'text-green',
        icon: TrendingUp,
        pulse: false,
      };
    }
    if (signal.includes('Strong Bearish') || signal.includes('Risk-Off')) {
      return {
        bg: 'bg-red-dim border-red',
        text: 'text-red',
        icon: TrendingDown,
        pulse: true,
      };
    }
    if (signal.includes('Bearish')) {
      return {
        bg: 'bg-red-dim border-red',
        text: 'text-red',
        icon: TrendingDown,
        pulse: false,
      };
    }
    return {
      bg: 'bg-terminal-elevated border-terminal-border',
      text: 'text-text-muted',
      icon: Minus,
      pulse: false,
    };
  };

  const styles = getSignalStyles(data.ensembleSignal);
  const Icon = styles.icon;

  return (
    <div className={cn('border-y px-6 py-4', styles.bg)}>
      <div className="max-w-[1920px] mx-auto">
        <div className="flex items-center justify-between">
          {/* Left: Signal */}
          <div className="flex items-center gap-4">
            <div className={cn('flex items-center gap-2', styles.text)}>
              {styles.pulse && (
                <span className="relative flex h-3 w-3">
                  <span className={cn('animate-ping absolute inline-flex h-full w-full rounded-full opacity-75', styles.text.replace('text-', 'bg-'))} />
                  <span className={cn('relative inline-flex rounded-full h-3 w-3', styles.text.replace('text-', 'bg-'))} />
                </span>
              )}
              {!styles.pulse && <Icon className="w-5 h-5" />}
            </div>

            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-text-muted uppercase tracking-wider">Master Ensemble Signal</span>
                <Badge variant={data.ensembleSignal.includes('Bullish') ? 'success' : data.ensembleSignal.includes('Bearish') ? 'danger' : 'neutral'} className="text-xs">
                  {data.adaptiveWeightingActive ? 'ADAPTIVE' : 'STATIC'}
                </Badge>
              </div>
              <div className={cn('text-2xl font-bold', styles.text)}>
                {data.ensembleSignal}
              </div>
            </div>
          </div>

          {/* Center: Score Bar */}
          <div className="flex-1 max-w-md mx-6">
            <div className="flex items-center justify-between text-xs text-text-muted mb-1">
              <span>Ensemble Score</span>
              <span className="font-mono">{data.ensembleScore > 0 ? '+' : ''}{data.ensembleScore.toFixed(3)}</span>
            </div>
            <div className="h-2 bg-terminal-border rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full transition-all duration-500',
                  data.ensembleScore > 0 ? 'bg-green' : 'bg-red'
                )}
                style={{
                  width: `${Math.abs(data.ensembleScore) * 50}%`,
                  marginLeft: data.ensembleScore > 0 ? '50%' : `${50 - Math.abs(data.ensembleScore) * 50}%`,
                }}
              />
            </div>
            <div className="flex items-center justify-between text-xs text-text-muted mt-1">
              <span>Risk-Off</span>
              <span className="text-text-secondary">Neutral</span>
              <span>Risk-On</span>
            </div>
          </div>

          {/* Right: Key Metrics */}
          <div className="flex items-center gap-6">
            <div className="text-center">
              <div className="flex items-center gap-1 text-xs text-text-muted mb-0.5">
                <Users className="w-3 h-3" />
                <span>Agreement</span>
              </div>
              <div className={cn(
                'text-lg font-mono font-bold',
                data.agreementRatio >= 0.8 ? 'text-green' :
                data.agreementRatio >= 0.6 ? 'text-amber' : 'text-red'
              )}>
                {(data.agreementRatio * 100).toFixed(0)}%
              </div>
            </div>

            <div className="text-center">
              <div className="flex items-center gap-1 text-xs text-text-muted mb-0.5">
                <Target className="w-3 h-3" />
                <span>Conviction</span>
              </div>
              <div className="text-lg font-mono font-bold text-text-primary">
                {data.conviction}
              </div>
            </div>

            <div className="text-center">
              <div className="flex items-center gap-1 text-xs text-text-muted mb-0.5">
                <Zap className="w-3 h-3" />
                <span>Risk Budget</span>
              </div>
              <div className="text-lg font-mono font-bold text-text-primary">
                {data.riskBudgetFinal.toFixed(2)}x
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

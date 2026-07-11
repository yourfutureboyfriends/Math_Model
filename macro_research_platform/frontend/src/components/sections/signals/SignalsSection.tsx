// Phase 8 — Signal Interpretation Section (Redesigned) + Phase 1E Store Integration
// Signal interpretation with terminal aesthetic using macroStore

import { TrendingUp, TrendingDown, Minus, History } from 'lucide-react';
import { useMacroStore } from '@/store/macroStore';
import { fmtSignal, fmtChange } from '@/utils/format';
import type { SignalsData } from '@/types';

interface SignalsSectionProps {
  data?: SignalsData;
}

export function SignalsSection({ data }: SignalsSectionProps) {
  // Use macro store for live signal data
  const signals = useMacroStore((state) => state.signals);
  const isLoading = useMacroStore((state) => state.meta.dataStatus === 'loading');

  const getDirectionIcon = (direction: string) => {
    switch (direction) {
      case 'improving':
        return <TrendingUp className="w-3 h-3 text-green" />;
      case 'deteriorating':
        return <TrendingDown className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getDirectionColor = (direction: string) => {
    switch (direction) {
      case 'improving':
        return 'text-green';
      case 'deteriorating':
        return 'text-red';
      default:
        return 'text-text-tertiary';
    }
  };

  // Map store signals to display format
  const signalsData = [
    {
      name: 'Growth',
      latestScore: signals.growth.score ?? 0,
      threeMonthChange: signals.growth.threeMonth ?? 0,
      state: signals.growth.state ?? 'neutral',
      direction: (signals.growth.score ?? 0) > 0.3 ? 'improving' : (signals.growth.score ?? 0) < -0.3 ? 'deteriorating' : 'stable',
      interpretation: data?.growth?.interpretation ?? `${signals.growth.score && signals.growth.score > 0 ? 'Positive' : 'Negative'} growth momentum`,
      history: data?.growth?.history ?? [],
    },
    {
      name: 'Inflation',
      latestScore: signals.inflation.score ?? 0,
      threeMonthChange: signals.inflation.threeMonth ?? 0,
      state: signals.inflation.state ?? 'neutral',
      direction: (signals.inflation.score ?? 0) > 0.3 ? 'improving' : (signals.inflation.score ?? 0) < -0.3 ? 'deteriorating' : 'stable',
      interpretation: data?.inflation?.interpretation ?? `${signals.inflation.score && signals.inflation.score > 0 ? 'Rising' : 'Falling'} inflation pressure`,
      history: data?.inflation?.history ?? [],
    },
    {
      name: 'Liquidity',
      latestScore: signals.liquidity.score ?? 0,
      threeMonthChange: signals.liquidity.threeMonth ?? 0,
      state: signals.liquidity.state ?? 'neutral',
      direction: (signals.liquidity.score ?? 0) > 0.3 ? 'improving' : (signals.liquidity.score ?? 0) < -0.3 ? 'deteriorating' : 'stable',
      interpretation: data?.liquidity?.interpretation ?? `${signals.liquidity.score && signals.liquidity.score > 0 ? 'Accommodative' : 'Restrictive'} financial conditions`,
      history: data?.liquidity?.history ?? [],
    },
    {
      name: 'Risk',
      latestScore: signals.risk.score ?? 0,
      threeMonthChange: signals.risk.threeMonth ?? 0,
      state: signals.risk.state ?? 'neutral',
      direction: (signals.risk.score ?? 0) > 0.3 ? 'improving' : (signals.risk.score ?? 0) < -0.3 ? 'deteriorating' : 'stable',
      interpretation: data?.risk?.interpretation ?? `${signals.risk.score && signals.risk.score > 0 ? 'Elevated' : 'Muted'} risk appetite`,
      history: data?.risk?.history ?? [],
    },
  ];

  if (isLoading && !data) {
    return (
      <div id="signals" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">◆</span>
            <h2 className="section-title">Signal Interpretation</h2>
          </div>
        </div>
        <div className="p-8 bg-surface-1 border border-border text-center text-text-secondary">
          Loading signals...
        </div>
      </div>
    );
  }

  return (
    <div id="signals" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Signal Interpretation</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Signals Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-2">
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
                <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Latest</th>
                <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">3M</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">State</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Dir</th>
              </tr>
            </thead>
            <tbody>
              {signalsData.map((signal) => (
                <tr key={signal.name} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 px-3 text-sm font-medium text-text-primary">{signal.name}</td>
                  <td className="py-2 px-3 text-right font-mono text-xs text-text-primary">
                    {fmtSignal(signal.latestScore)}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-xs">
                    <span
                      className={
                        signal.threeMonthChange > 0
                          ? 'text-green'
                          : signal.threeMonthChange < 0
                            ? 'text-red'
                            : 'text-text-tertiary'
                      }
                    >
                      {fmtChange(signal.threeMonthChange)}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center text-xs text-text-secondary">{signal.state}</td>
                  <td className="py-2 px-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getDirectionIcon(signal.direction)}
                      <span className={`text-2xs ${getDirectionColor(signal.direction)}`}>
                        {signal.direction.charAt(0).toUpperCase()}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* History Data */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2 flex items-center gap-2">
            <History className="w-3 h-3" />
            Signal History (Last 6)
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {signalsData.map((signal) => (
              <div key={signal.name} className="bg-surface-2 p-2 border border-border-subtle">
                <div className="text-2xs text-text-tertiary mb-1">{signal.name}</div>
                <div className="flex gap-1 flex-wrap">
                  {signal.history?.slice(-6).map((val, idx) => (
                    <span
                      key={idx}
                      className={`font-mono text-2xs ${
                        val > 0 ? 'text-green' : val < 0 ? 'text-red' : 'text-text-tertiary'
                      }`}
                    >
                      {fmtSignal(val)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Interpretations */}
        <div className="space-y-1">
          {signalsData.map((signal) => (
            <div key={signal.name} className="p-2 bg-surface-1 border border-border-subtle">
              <span className="text-2xs text-text-tertiary">{signal.name}:</span>
              <span className="text-xs text-text-secondary ml-2">{signal.interpretation}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

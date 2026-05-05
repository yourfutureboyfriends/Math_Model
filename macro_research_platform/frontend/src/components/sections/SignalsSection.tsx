// Phase 8 — Signal Interpretation Section (Redesigned)
// Signal interpretation with terminal aesthetic

import { TrendingUp, TrendingDown, Minus, History } from 'lucide-react';
import type { SignalsData } from '@/types';

interface SignalsSectionProps {
  data?: SignalsData;
}

export function SignalsSection({ data }: SignalsSectionProps) {
  if (!data) return null;

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

  const signalsData = [
    { name: 'Growth', ...data.growth },
    { name: 'Inflation', ...data.inflation },
    { name: 'Liquidity', ...data.liquidity },
    { name: 'Risk', ...data.risk },
  ];

  return (
    <div id="signals" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">06</span>
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
                    {signal.latestScore >= 0 ? '+' : ''}{signal.latestScore.toFixed(2)}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-xs">
                    <span
                      className={
                        signal.threeMonthChange.startsWith('+')
                          ? 'text-green'
                          : signal.threeMonthChange.startsWith('-')
                            ? 'text-red'
                            : 'text-text-tertiary'
                      }
                    >
                      {signal.threeMonthChange}
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
                      {val >= 0 ? '+' : ''}{val.toFixed(1)}
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

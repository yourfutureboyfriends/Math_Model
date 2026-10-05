// Phase 8 — Signal Interpretation Section (Redesigned) + Phase 1E Store Integration
// Signal interpretation with terminal aesthetic using macroStore

import { TrendingUp, TrendingDown, Minus, History } from 'lucide-react';
import { useMacroStore } from '@/store/macroStore';
import { fmtSignal } from '@/utils/format';
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
      case 'rising':
        return <TrendingUp className="w-3 h-3 text-text-secondary" />;
      case 'falling':
        return <TrendingDown className="w-3 h-3 text-text-secondary" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getDirectionColor = (direction: string) => {
    switch (direction) {
      case 'rising':
      case 'falling':
        return 'text-text-secondary';
      default:
        return 'text-text-tertiary';
    }
  };

  // Server payload (interpretation, history, direction) from the dashboard response; the
  // store only keeps score/state. Never invent an interpretation when the server sent none.
  const full = useMacroStore((state) => (state.fullDashboard as any)?.signals) as Record<string, any> | undefined;
  const src = (data as any) ?? full ?? {};
  const signalsData = (['growth', 'inflation', 'liquidity', 'risk'] as const).map((k) => {
    const st = (signals as any)[k] ?? {};
    const sv = src[k] ?? {};
    const three = typeof sv.threeMonth === 'number' ? sv.threeMonth : (st.threeMonth ?? null);
    return {
      name: k.charAt(0).toUpperCase() + k.slice(1),
      latestScore: sv.latestScore ?? st.score ?? null,
      threeMonthChange: three,
      state: sv.state ?? st.state ?? '—',
      // Rising/falling only: whether a rise is good depends on the signal (rising
      // inflation is not "improving"), so no green/red judgement here.
      direction: three == null ? 'stable' : three > 0.05 ? 'rising' : three < -0.05 ? 'falling' : 'stable',
      label: sv.direction as string | undefined,
      interpretation: sv.interpretation as string | undefined,
      history: (sv.history ?? []) as number[],
    };
  });

  if (isLoading && !data) {
    return (
      <div id="signals" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">◆</span>
            <h2 className="section-title">Signal Detail</h2>
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
          <h2 className="section-title">Signal Detail</h2>
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
                    {signal.latestScore == null ? '—' : fmtSignal(signal.latestScore)}
                  </td>
                  <td className="py-2 px-3 text-right font-mono text-xs">
                    <span className="text-text-secondary">
                      {signal.threeMonthChange == null ? '—' : `${signal.threeMonthChange >= 0 ? '+' : ''}${signal.threeMonthChange.toFixed(2)}`}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center text-xs text-text-secondary">{signal.state}</td>
                  <td className="py-2 px-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getDirectionIcon(signal.direction)}
                      <span className={`text-2xs ${getDirectionColor(signal.direction)}`} title={signal.label}>
                        {signal.direction}
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
            Signal history (last 5 observations, oldest → latest)
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {signalsData.map((signal) => (
              <div key={signal.name} className="bg-surface-2 p-2 border border-border-subtle">
                <div className="text-2xs text-text-tertiary mb-1">{signal.name}</div>
                <div className="flex gap-1 flex-wrap">
                  {signal.history?.slice(-6).map((val, idx) => (
                    <span
                      key={idx}
                      className="font-mono text-2xs text-text-secondary"
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
          {signalsData.filter((signal) => signal.interpretation).map((signal) => (
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

// Phase 8 — Transmission Analysis Section (Redesigned)
// Policy transmission with terminal aesthetic

import { Zap } from 'lucide-react';
import type { TransmissionAnalysisData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface TransmissionSectionProps {
  data?: TransmissionAnalysisData;
}

export function TransmissionSection({ data }: TransmissionSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["transmissionAnalysis"] as any;

  // Explicit empty state instead of a blank panel when no channels are computed yet.
  if (!data?.channels?.length) {
    return (
      <div id="transmission" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag"><Zap className="w-3 h-3" /></span>
            <h2 className="section-title">Policy Transmission</h2>
          </div>
        </div>
        <div className="p-4 text-2xs text-text-tertiary">Transmission-channel data unavailable.</div>
      </div>
    );
  }

  const getStatusTag = (status: string) => {
    switch (status.toLowerCase()) {
      case 'active':
      case 'normal':
        return 'signal-tag bullish';
      case 'mixed':
      case 'neutral':
        return 'signal-tag neutral';
      case 'headwind':
      case 'restricted':
        return 'signal-tag warning';
      default:
        return 'signal-tag neutral';
    }
  };

  return (
    <div id="transmission" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">24</span>
          <h2 className="section-title">Transmission Analysis</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Channels Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-2">
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Channel</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Status</th>
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Description</th>
              </tr>
            </thead>
            <tbody>
              {data.channels.map((item) => (
                <tr key={item.channel} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-2">
                      <Zap className="w-3 h-3 text-amber" />
                      <span className="text-sm font-medium text-text-primary">{item.channel}</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span className={getStatusTag(item.status)}>{item.status}</span>
                  </td>
                  <td className="py-2 px-3 text-xs text-text-secondary">{item.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Summary */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
            Summary
          </div>
          <p className="text-xs text-text-primary">{data.summary}</p>
        </div>
      </div>
    </div>
  );
}

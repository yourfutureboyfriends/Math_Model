// Phase 8 — Data to Watch Section (Redesigned)
// Key upcoming releases with terminal aesthetic

import { Calendar, Eye } from 'lucide-react';
import type { DataToWatchItem } from '@/types';

interface DataToWatchSectionProps {
  data?: DataToWatchItem[];
}

export function DataToWatchSection({ data }: DataToWatchSectionProps) {
  if (!data?.length) return null;

  const getImportanceTag = (importance: string) => {
    switch (importance.toLowerCase()) {
      case 'high':
        return 'signal-tag bearish';
      case 'medium':
        return 'signal-tag warning';
      case 'low':
        return 'signal-tag neutral';
      default:
        return 'signal-tag neutral';
    }
  };

  return (
    <div id="data-to-watch" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">25</span>
          <h2 className="section-title">Data to Watch</h2>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs text-text-secondary">
          <Eye className="w-3 h-3" />
          <span>Upcoming releases that may impact regime classification</span>
        </div>

        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-2">
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Indicator</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Importance</th>
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Release</th>
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Impact</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.indicator} className="border-b border-border-subtle last:border-0">
                  <td className="py-2 px-3 text-sm font-medium text-text-primary">{item.indicator}</td>
                  <td className="py-2 px-3 text-center">
                    <span className={getImportanceTag(item.importance)}>
                      {item.importance.charAt(0).toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-2">
                      <Calendar className="w-3 h-3 text-text-tertiary" />
                      <span className="text-xs text-text-secondary">{item.nextRelease}</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-xs text-text-secondary">{item.expectedImpact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

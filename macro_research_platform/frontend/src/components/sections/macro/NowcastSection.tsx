// Phase 8 — GDP Nowcast Section (Redesigned)
// DFM/PCA nowcast with terminal aesthetic

import { cn } from '@/lib/utils';
import { ComputedTag } from '@/components/ui/ComputedTag';
import type { NowcastData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface NowcastSectionProps {
  data?: NowcastData;
}

// Format ISO timestamp to readable time
const fmtTimestamp = (iso: string | undefined): string => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      timeZone: 'UTC',
    }) + ' UTC';
  } catch {
    return iso;
  }
};

export function NowcastSection({ data }: NowcastSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["nowcast"] as any;

  if (!data) return null;

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'expanding':
        return 'text-green';
      case 'contracting':
        return 'text-red';
      default:
        return 'text-text-secondary';
    }
  };

  return (
    <div id="nowcast" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">16</span>
          <h2 className="section-title">GDP Nowcast</h2>
        </div>
        <ComputedTag section="nowcast" />
      </div>

      <div className="space-y-3">
        {/* Inline Data Row */}
        <div className="grid grid-cols-4 gap-3">
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">QoQ Ann</div>
            <div className={cn(
              'text-base font-mono font-bold',
              data.nowcastQoQ >= 0 ? 'text-green' : 'text-red'
            )}>
              {data.nowcastQoQ >= 0 ? '+' : ''}{data.nowcastQoQ.toFixed(2)}%
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">YoY</div>
            <div className={cn(
              'text-base font-mono font-bold',
              data.nowcastYoY >= 0 ? 'text-green' : 'text-red'
            )}>
              {data.nowcastYoY >= 0 ? '+' : ''}{data.nowcastYoY.toFixed(2)}%
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">95% CI</div>
            <div className="text-base font-mono text-text-primary">
              {data.confidenceInterval.lower.toFixed(1)} to {data.confidenceInterval.upper.toFixed(1)}%
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">RMSE</div>
            {/* FIXED: BUG-B8 - Handle null/undefined rmse properly */}
            <div className="text-base font-mono text-text-primary">
              {data.confidenceInterval.rmse !== null && data.confidenceInterval.rmse !== undefined && typeof data.confidenceInterval.rmse === 'number'
                ? `±${data.confidenceInterval.rmse.toFixed(2)}pp`
                : '±N/A'}
            </div>
          </div>
        </div>

        {/* Components */}
        <div className="border border-border bg-surface-1">
          <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">
              Components
            </span>
          </div>
          <div className="p-2 grid grid-cols-2 md:grid-cols-4 gap-2">
            {(data.components ?? []).map((comp) => (
              <div key={comp.name} className="p-2 bg-surface-2">
                <div className="text-xs text-text-secondary">{comp.name}</div>
                <div className="flex items-center justify-between">
                  <span className={cn('font-mono text-sm', getStatusColor(comp.status))}>
                    {comp.contribution >= 0 ? '+' : ''}{comp.contribution.toFixed(2)}%
                  </span>
                  {/* FIX: weight is a decimal (0.35); display as percentage for readability */}
                  <span className="text-2xs text-text-tertiary">w{(comp.weight * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Methodology */}
        <div className="p-2 border border-border bg-surface-1">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
            Methodology
          </div>
          <p className="text-xs text-text-secondary">{data.methodology}</p>
          {/* Format timestamp */}
          <p className="text-2xs text-text-tertiary font-mono mt-1">
            Updated: {fmtTimestamp(data?.lastUpdated)}
          </p>
        </div>
      </div>
    </div>
  );
}

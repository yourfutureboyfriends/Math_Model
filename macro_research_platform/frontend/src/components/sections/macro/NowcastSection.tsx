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

  const anyData = data as any;
  const ci: any = anyData.confidenceInterval;
  const isNum = (v: unknown): v is number => typeof v === 'number' && isFinite(v);
  const fmtSigned = (v: unknown) => (isNum(v) ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '—');
  const signColor = (v: unknown) => (isNum(v) ? (v >= 0 ? 'text-green' : 'text-red') : 'text-text-tertiary');

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
          <span className="section-tag">◆</span>
          <h2 className="section-title">GDP Nowcast</h2>
        </div>
        <ComputedTag section="nowcast" />
      </div>

      <div className="space-y-3">
        {/* Inline Data Row — fields the source doesn't publish render as '—'. */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">
              {(anyData.models ?? []).some((m: any) => m.model.startsWith('Atlanta')) ? 'Atlanta GDPNow' : 'QoQ Ann'}{anyData.quarter ? ` · ${anyData.quarter}` : ''}
            </div>
            <div className={cn('text-base font-mono font-bold', signColor(data.nowcastQoQ))}>
              {fmtSigned(data.nowcastQoQ)}
            </div>
          </div>
          {(anyData.models ?? []).filter((m: any) => m.model.startsWith('NY Fed')).map((m: any) => (
            <div key={m.model} className="p-2 bg-surface-1 border border-border" title={`${m.model}, as of ${m.asOf}`}>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">NY Fed Staff · {m.quarter?.replace(':', '')}</div>
              <div className={cn('text-base font-mono font-bold', signColor(m.value))}>{fmtSigned(m.value)}</div>
              <div className="text-2xs text-text-tertiary">{isNum(m.change4w) ? `${m.change4w >= 0 ? '+' : ''}${m.change4w.toFixed(2)}pp in 4 wks` : ''}</div>
            </div>
          ))}
          <div className="p-2 bg-surface-1 border border-border" title={anyData.bandType ?? 'Shown when both nowcasts cover the same quarter'}>
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">Model range</div>
            <div className="text-base font-mono text-text-primary">
              {Array.isArray(ci) && isNum(ci[0]) && isNum(ci[1]) ? `${ci[0].toFixed(2)} to ${ci[1].toFixed(2)}%`
                : isNum(ci?.lower) && isNum(ci?.upper) ? `${ci.lower.toFixed(1)} to ${ci.upper.toFixed(1)}%` : '—'}
            </div>
            <div className="text-2xs text-text-tertiary">GDPNow vs NY Fed</div>
          </div>
          {(anyData.models ?? []).filter((m: any) => isNum(m.nextQuarter)).map((m: any) => (
            <div key={`${m.model}-next`} className="p-2 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">Next quarter (NY Fed)</div>
              <div className={cn('text-base font-mono font-bold', signColor(m.nextQuarter))}>{fmtSigned(m.nextQuarter)}</div>
            </div>
          ))}
        </div>

        {/* Components */}
        {(data.components ?? []).length > 0 && (
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
        )}

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

// Phase 8 — Reflexivity Monitor Section (Redesigned)
// Soros feedback loops framework with terminal aesthetic

import { Activity, AlertCircle, Zap, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { ReflexivityData, ReflexivityLoop } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface ReflexivitySectionProps {
  data?: ReflexivityData;
}

export function ReflexivitySection({ data: dataProp }: ReflexivitySectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  let data = dataProp;
  if (!data) data = (_fullDash as any)?.reflexivity as any;
  if (!data) return null;

  const getStrengthIcon = (strength: number) => {
    if (strength >= 0.7) return <Zap className="w-3 h-3 text-red" />;
    if (strength >= 0.5) return <Activity className="w-3 h-3 text-amber" />;
    return <Minus className="w-3 h-3 text-text-tertiary" />;
  };

  const LoopCard = ({ loop, active }: { loop: ReflexivityLoop; active: boolean }) => (
    <div className={`p-2 border ${active ? 'bg-red-dim border-red' : 'bg-surface-1 border-border'}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {active ? (
            <div className="w-1.5 h-1.5 bg-red" />
          ) : (
            <div className="w-1.5 h-1.5 bg-text-tertiary" />
          )}
          <span className={`text-2xs font-medium uppercase ${active ? 'text-red' : 'text-text-secondary'}`}>
            {active ? 'Active' : 'Inactive'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {getStrengthIcon(loop.strength)}
          <span className="text-2xs text-text-tertiary">{loop.strength.toFixed(2)}</span>
        </div>
      </div>

      <div className="text-xs font-medium text-text-primary mb-2">{loop.loop}</div>

      {active && (
        <>
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div className="p-1.5 bg-surface-2">
              <div className="text-2xs text-text-tertiary">{loop.variables?.cause?.name}</div>
              <div className="flex items-center gap-1">
                {loop.variables?.cause?.trend === 'rising' ? (
                  <TrendingUp className="w-3 h-3 text-green" />
                ) : loop.variables?.cause?.trend === 'falling' ? (
                  <TrendingDown className="w-3 h-3 text-red" />
                ) : (
                  <Minus className="w-3 h-3 text-text-tertiary" />
                )}
                <span className="text-2xs text-text-secondary">{loop.variables?.cause?.trend}</span>
              </div>
            </div>
            <div className="p-1.5 bg-surface-2">
              <div className="text-2xs text-text-tertiary">{loop.variables?.effect?.name}</div>
              <div className="flex items-center gap-1">
                {loop.variables?.effect?.trend === 'rising' ? (
                  <TrendingUp className="w-3 h-3 text-green" />
                ) : loop.variables?.effect?.trend === 'falling' ? (
                  <TrendingDown className="w-3 h-3 text-red" />
                ) : (
                  <Minus className="w-3 h-3 text-text-tertiary" />
                )}
                <span className="text-2xs text-text-secondary">{loop.variables?.effect?.trend}</span>
              </div>
            </div>
          </div>

          <p className="text-2xs text-text-secondary mb-2">{loop.implication || loop.interpretation}</p>

          <div className="p-1.5 bg-surface-2 text-2xs text-text-tertiary">
            <span className="text-amber">Break:</span> {loop.breakCondition}
          </div>
        </>
      )}

      {!active && (
        <p className="text-2xs text-text-tertiary">{loop.interpretation}</p>
      )}
    </div>
  );

  return (
    <div id="reflexivity" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">23</span>
          <h2 className="section-title">Reflexivity Monitor</h2>
          {data.loopCount?.active > 0 && (
            <span className="section-meta text-red">{data.loopCount.active} ACTIVE</span>
          )}
        </div>
      </div>

      <div className="space-y-3">
        {/* Alert banner */}
        {data.reflexivityAlert ? (
          <div className="p-3 border border-red bg-red-dim">
            <div className="flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red flex-shrink-0" />
              <div>
                <div className="text-xs font-medium text-red mb-1">{data.alertMessage}</div>
                <p className="text-2xs text-text-secondary">{data.regimeImplication}</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="p-3 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 text-text-tertiary">
              <Minus className="w-3 h-3" />
              <span className="text-xs">No active reflexivity loops — regime transitions follow base probabilities</span>
            </div>
          </div>
        )}

        {/* Active loops */}
        {data.activeLoops && data.activeLoops.length > 0 && (
          <div>
            <div className="text-2xs text-red uppercase tracking-wider mb-2">
              Active Loops ({data.loopCount?.active || 0})
            </div>
            <div className="space-y-2">
              {(data.activeLoops ?? []).map((loop) => (
                <LoopCard key={loop.id} loop={loop} active={true} />
              ))}
            </div>
          </div>
        )}

        {/* Inactive loops */}
        {data.inactiveLoops && data.inactiveLoops.length > 0 && (
          <div>
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">
              Inactive Loops ({data.loopCount?.inactive || 0})
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {data.inactiveLoops.slice(0, 4).map((loop) => (
                <LoopCard key={loop.id} loop={loop} active={false} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

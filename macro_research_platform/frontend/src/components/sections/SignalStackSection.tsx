// Phase 8 — Signal Stack Section (Redesigned)
// Layered signal visualization with override tracking

import { cn } from '@/lib/utils';
import { Layers, Shield } from 'lucide-react';
import { AnimatedValue, SkeletonSignalStack } from '@/components/ui';
import type { SignalStackData } from '@/types';

interface SignalStackSectionProps {
  data?: SignalStackData;
}

export function SignalStackSection({ data }: SignalStackSectionProps) {
  if (!data) {
    return (
      <div id="signal-stack" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">08</span>
            <h2 className="section-title">Signal Stack</h2>
          </div>
        </div>
        <SkeletonSignalStack rows={8} />
      </div>
    );
  }

  // Handle both old format (layers array) and new format (layerOutputs object)
  const layerOutputs = (data as any).layerOutputs || {};
  const layers = (data as any).layers || [];
  const finalSignal = (data as any).finalSignal || (data as any).finalStance || 'NEUTRAL';
  const conviction = (data as any).conviction || (data as any).riskBudget || 0.5;
  const overridesApplied = (data as any).overridesApplied || [];
  const reasoning = (data as any).reasoning || (data as any).overrideReason || 'Signal stack active';
  const timestamp = (data as any).timestamp || (data as any).lastUpdated || '';

  const getSignalColor = (signal: string) => {
    if (!signal) return 'text-text-secondary';
    if (signal.includes('DEFENSIVE') || signal.includes('VETO') || signal.includes('UNDERWEIGHT'))
      return 'text-red';
    if (signal.includes('RISK_ON') || signal.includes('OVERWEIGHT') || signal.includes('BULLISH')) return 'text-green';
    if (signal.includes('CYCLICAL')) return 'text-blue';
    if (signal.includes('REAL_ASSETS')) return 'text-amber';
    return 'text-text-secondary';
  };

  const getFinalSignalBg = (signal: string) => {
    if (!signal) return 'bg-surface-2 border-border';
    if (signal.includes('DEFENSIVE') || signal.includes('VETO')) return 'bg-red-dim border-red';
    if (signal.includes('RISK_ON') || signal.includes('BULLISH')) return 'bg-green-dim border-green';
    if (signal.includes('CYCLICAL')) return 'bg-blue-dim border-blue';
    if (signal.includes('REAL_ASSETS')) return 'bg-amber-dim border-amber';
    return 'bg-surface-2 border-border';
  };

  // Convert layerOutputs object to array if needed
  const layerEntries = layers.length > 0
    ? layers
    : Object.entries(layerOutputs).map(([name, output]: [string, any], index) => ({
        layer: name,
        priority: index + 1,
        signal: output?.ctaSignal || output?.baseStance || output?.regime || name,
        conviction: output?.confidence || 0.5,
        override: output?.adjustment !== 0 ? `Adjustment: ${output?.adjustment}` : null
      }));

  const sortedLayers = [...layerEntries].sort((a, b) => a.priority - b.priority);

  return (
    <div id="signal-stack" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">08</span>
          <h2 className="section-title">Signal Stack</h2>
          <span className="section-meta">{sortedLayers.length} layers</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Final Signal Header */}
        <div className={cn('p-3 border', getFinalSignalBg(finalSignal))}>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
                Final Consensus
              </div>
              <div className={cn('text-lg font-mono font-bold', getSignalColor(finalSignal))}>
                {finalSignal.replace(/_/g, ' ')}
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
                Confidence
              </div>
              <div className="text-base font-mono font-bold text-text-primary">
                <AnimatedValue value={conviction * 100} decimals={0} suffix="%" />
              </div>
            </div>
          </div>

          {/* Confidence Bar */}
          <div className="mt-3">
            <div className="h-1 bg-surface-4">
              <div
                className="h-full bg-bloomberg transition-all duration-500"
                style={{ width: `${conviction * 100}%` }}
              />
            </div>
            <div className="flex justify-between text-2xs text-text-tertiary mt-1">
              <span>Low</span>
              <span>Medium</span>
              <span>High</span>
            </div>
          </div>
        </div>

        {/* Active Overrides */}
        {overridesApplied.length > 0 && (
          <div className="p-2 bg-amber-dim border border-amber">
            <div className="flex items-center gap-2 mb-1">
              <Shield className="w-3 h-3 text-amber" />
              <span className="text-xs font-medium text-amber">
                Overrides ({overridesApplied.length})
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              {overridesApplied.map((override: string, idx: number) => (
                <span key={idx} className="signal-tag warning text-2xs">
                  {override}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Signal Layers */}
        <div className="border border-border bg-surface-1">
          <div className="px-3 py-2 border-b border-border-subtle bg-surface-2">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider flex items-center gap-2">
              <Layers className="w-3 h-3" />
              Layers (Priority Order)
            </span>
          </div>
          <div className="p-2 space-y-1">
            {sortedLayers.map((layer: any, index: number) => (
              <div key={layer.layer || index}>
                <div
                  className={cn(
                    'flex items-center justify-between p-2 border',
                    layer.override
                      ? 'bg-amber-dim border-amber'
                      : 'bg-surface-2 border-border'
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 flex items-center justify-center text-2xs font-mono text-text-tertiary bg-surface-3">
                      {layer.priority}
                    </span>
                    <span className="text-sm text-text-primary">{layer.layer}</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className={cn('text-xs font-mono', getSignalColor(layer.signal))}>
                      {layer.signal?.replace(/_/g, ' ') || 'N/A'}
                    </span>

                    <div className="flex items-center gap-1.5">
                      <div className="w-12 h-1 bg-surface-4">
                        <div
                          className="h-full transition-all"
                          style={{
                            width: `${(layer.conviction || 0.5) * 100}%`,
                            backgroundColor:
                              layer.conviction >= 0.7 ? 'var(--green)' :
                              layer.conviction >= 0.4 ? 'var(--amber)' : 'var(--text-tertiary)',
                          }}
                        />
                      </div>
                      <span className="text-2xs font-mono text-text-secondary w-6 text-right">
                        <AnimatedValue value={(layer.conviction || 0.5) * 100} decimals={0} suffix="%" />
                      </span>
                    </div>
                  </div>
                </div>

                {/* Override note */}
                {layer.override && (
                  <div className="px-2 py-1 text-2xs text-amber">
                    Override: {layer.override}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Reasoning - FIXED: BUG-F7 - Human readable timestamp */}
        <div className="p-3 border border-border bg-surface-1">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
            Reasoning
          </div>
          <p className="text-xs text-text-secondary">{reasoning || 'Signal stack calculated from multi-layer analysis'}</p>
          {timestamp && (
            <div className="text-2xs text-text-tertiary font-mono mt-2">
              Updated: {new Date(timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

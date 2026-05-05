// Phase 8 — Horizon Tension Analysis Section (Redesigned)
// Tactical vs Strategic signal alignment with terminal aesthetic

import { Clock, AlertTriangle, ArrowRight } from 'lucide-react';
import type { HorizonAnalysisData, AssetHorizonAnalysis } from '@/types';

interface HorizonTensionSectionProps {
  data?: HorizonAnalysisData;
}

export function HorizonTensionSection({ data }: HorizonTensionSectionProps) {
  if (!data) return null;

  const getSignalTag = (signal: string) => {
    switch (signal) {
      case 'BULLISH':
        return 'signal-tag bullish';
      case 'BEARISH':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const getTensionTag = (tensionType: string) => {
    switch (tensionType) {
      case 'Fully Aligned':
        return 'signal-tag bullish';
      case 'Tactical vs Strategic':
      case 'High Tension':
        return 'signal-tag warning';
      case 'Fully Contradictory':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const SignalPill = ({ signal, horizon }: { signal: string; horizon: string }) => (
    <div className="flex flex-col items-center">
      <span className="text-2xs text-text-tertiary mb-0.5">{horizon}</span>
      <span className={getSignalTag(signal)}>
        {signal.charAt(0)}
      </span>
    </div>
  );

  const AssetRow = ({ asset }: { asset: AssetHorizonAnalysis }) => {
    return (
      <div className={`p-2 border ${
        asset.tensionScore === 0
          ? 'bg-green-dim border-green'
          : asset.tensionScore === 3
          ? 'bg-red-dim border-red'
          : 'bg-surface-1 border-border'
      }`}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-text-primary">{asset.assetClass}</span>
          <span className={getTensionTag(asset.tensionType)}>
            {asset.tensionType.replace('Fully ', 'F-').replace('Contradictory', 'Contra')}
          </span>
        </div>

        <div className="flex items-center justify-between">
          <SignalPill signal={asset.signals.shortTerm.signal} horizon="1-3M" />
          <ArrowRight className="w-3 h-3 text-text-tertiary" />
          <SignalPill signal={asset.signals.mediumTerm.signal} horizon="3-12M" />
          <ArrowRight className="w-3 h-3 text-text-tertiary" />
          <SignalPill signal={asset.signals.longTerm.signal} horizon="3-7Y" />
        </div>

        {asset.tensionScore > 0 && (
          <p className="text-2xs text-text-secondary mt-2">{asset.recommendation}</p>
        )}
      </div>
    );
  };

  return (
    <div id="horizon-tension" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">18</span>
          <h2 className="section-title">Horizon Tension</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Summary */}
        <div className="grid grid-cols-3 gap-2">
          <div className="p-2 bg-surface-1 border border-green/30 text-center">
            <div className="text-base font-mono font-bold text-green">{data.tensionSummary?.fullyAligned?.length || 0}</div>
            <div className="text-2xs text-text-tertiary">Aligned</div>
          </div>
          <div className="p-2 bg-surface-1 border border-amber/30 text-center">
            <div className="text-base font-mono font-bold text-amber">{data.tensionSummary?.partialTension?.length || 0}</div>
            <div className="text-2xs text-text-tertiary">Partial</div>
          </div>
          <div className="p-2 bg-surface-1 border border-red/30 text-center">
            <div className="text-base font-mono font-bold text-red">{data.tensionSummary?.fullyContradictory?.length || 0}</div>
            <div className="text-2xs text-text-tertiary">Contra</div>
          </div>
        </div>

        {/* Highest tension alert */}
        {data.tensionSummary?.tensionAlert && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber flex-shrink-0" />
              <span className="text-xs text-amber">{data.tensionSummary.tensionAlert}</span>
            </div>
          </div>
        )}

        {/* Asset analysis */}
        <div className="space-y-2">
          {data.assetAnalysis?.slice(0, 6).map((asset) => (
            <AssetRow key={asset.assetClass} asset={asset} />
          ))}
        </div>

        {/* Actionable summary */}
        {data.actionableSummary && (
          <div className="p-3 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-3 h-3 text-text-secondary" />
              <span className="text-xs font-medium text-text-primary">Recommendation</span>
            </div>

            <div className="space-y-1">
              {data.actionableSummary.fullyAlignedBuys?.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-2xs text-green">Buy:</span>
                  <span className="text-xs text-text-primary">{data.actionableSummary.fullyAlignedBuys.join(', ')}</span>
                </div>
              )}

              {data.actionableSummary.fullyAlignedAvoids?.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-2xs text-red">Avoid:</span>
                  <span className="text-xs text-text-primary">{data.actionableSummary.fullyAlignedAvoids.join(', ')}</span>
                </div>
              )}

              {data.actionableSummary.mixedSignals?.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-2xs text-amber">Mixed:</span>
                  <span className="text-xs text-text-primary">{data.actionableSummary.mixedSignals.join(', ')}</span>
                </div>
              )}
            </div>

            <p className="text-xs text-text-secondary mt-2">{data.actionableSummary.recommendation}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// Phase 8 — Cross-Asset Momentum Veto Section (Redesigned)
// Momentum veto with terminal aesthetic

import { Zap, TrendingDown, TrendingUp, CheckCircle } from 'lucide-react';
import type { MomentumVetoData } from '@/types';

interface MomentumVetoSectionProps {
  data?: MomentumVetoData;
}

export function MomentumVetoSection({ data }: MomentumVetoSectionProps) {
  if (!data) return null;

  const getSignalIcon = (signal: string) => {
    if (signal.includes('positive')) return <TrendingUp className="w-3 h-3 text-green" />;
    if (signal.includes('negative')) return <TrendingDown className="w-3 h-3 text-red" />;
    return <CheckCircle className="w-3 h-3 text-text-tertiary" />;
  };

  const getSignalTag = (signal: string) => {
    if (signal.includes('negative')) return 'signal-tag bearish';
    if (signal.includes('positive')) return 'signal-tag bullish';
    return 'signal-tag neutral';
  };

  return (
    <div id="momentum-veto" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">31</span>
          <h2 className="section-title">Momentum Veto</h2>
          <span className={`section-meta ${data.vetoActive ? 'text-red' : 'text-green'}`}>
            {data.vetoActive ? 'VETO' : 'PASS'}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Status Header */}
        <div className={`p-3 border ${data.vetoActive ? 'bg-red-dim border-red' : 'bg-green-dim border-green'}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className={`w-4 h-4 ${data.vetoActive ? 'text-red' : 'text-green'}`} />
              <div>
                <div className="text-2xs text-text-tertiary">Filter Status</div>
                <div className={`text-lg font-mono font-bold ${data.vetoActive ? 'text-red' : 'text-green'}`}>
                  {data.vetoActive ? 'VETO ACTIVE' : 'PASS'}
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-tertiary">Dampener</div>
              <div className="text-sm font-mono text-text-primary">{(data.dampenerApplied * 100).toFixed(0)}%</div>
            </div>
          </div>
        </div>

        {/* Portfolio Adjustment */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-text-primary">Portfolio Adjustment</span>
            <span className={data.portfolioAdjustment.action === 'reduce_risk' ? 'signal-tag bearish' : 'signal-tag bullish'}>
              {data.portfolioAdjustment.action.replace('_', ' ').toUpperCase()}
            </span>
          </div>
          {data.portfolioAdjustment.magnitude > 0 && (
            <div className="text-xs text-text-secondary mb-1">
              Magnitude: <span className="font-mono text-amber">{(data.portfolioAdjustment.magnitude * 100).toFixed(0)}%</span>
            </div>
          )}
          <p className="text-2xs text-text-tertiary">{data.portfolioAdjustment.rationale}</p>
        </div>

        {/* Asset Momentum Grid */}
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Asset Momentum (12-1 month)</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {data.assets.map((asset) => (
            <div key={asset.asset} className={`p-2 border ${asset.rawSignal.includes('negative') ? 'bg-red-dim border-red' : 'bg-surface-1 border-border'}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-text-primary">{asset.asset}</span>
                <div className="flex items-center gap-2">
                  {getSignalIcon(asset.rawSignal)}
                  <span className={getSignalTag(asset.rawSignal)}>
                    {asset.rawSignal.replace('_', ' ')}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs mb-1">
                <div>
                  <span className="text-2xs text-text-tertiary">12M:</span>
                  <span className={`font-mono ml-1 ${asset.return12m >= 0 ? 'text-green' : 'text-red'}`}>
                    {asset.return12m >= 0 ? '+' : ''}{asset.return12m.toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-2xs text-text-tertiary">12-1 Mo:</span>
                  <span className={`font-mono ml-1 ${asset.momentum12_1 >= 0 ? 'text-green' : 'text-red'}`}>
                    {asset.momentum12_1 >= 0 ? '+' : ''}{asset.momentum12_1.toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-2xs text-text-tertiary">Dampened: {asset.dampenedSignal >= 0 ? '+' : ''}{asset.dampenedSignal.toFixed(1)}%</span>
                <span className={`text-2xs font-medium ${asset.interpretation.includes('VETO') ? 'text-red' : 'text-green'}`}>
                  {asset.interpretation}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

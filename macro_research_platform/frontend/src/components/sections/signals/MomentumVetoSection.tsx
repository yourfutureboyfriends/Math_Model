// Phase 8 — Cross-Asset Momentum Veto Section (Redesigned) + Phase 4A Format Library
// Momentum veto using format library

import { Zap, TrendingDown, TrendingUp, CheckCircle } from 'lucide-react';
import { useMacroStore } from '@/store/macroStore';
import { fmtChange } from '@/utils/format';

export function MomentumVetoSection() {
  // Use macro store for data and regime context
  // P3: narrow selectors (avoid whole-store re-render on price ticks)
  const data = useMacroStore((s) => s.momentumVeto);
  const regime = useMacroStore((s) => s.regime);

  if (!data) {
    return (
      <div id="momentum-veto" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">29</span>
            <h2 className="section-title">Momentum Veto</h2>
            <span className="section-meta">Regime: {regime.current ? regime.current.toUpperCase() : '—'}</span>
          </div>
        </div>
        <div className="p-4 text-text-secondary text-sm">No momentum veto data available</div>
      </div>
    );
  }

  // Safe destructuring with defaults
  const vetoActive = data?.vetoActive ?? false;
  const dampenerApplied = data?.dampenerApplied ?? 0;
  const portfolioAction = data?.portfolioAdjustment?.action ?? 'MAINTAIN';
  const portfolioMagnitude = data?.portfolioAdjustment?.magnitude ?? 0;
  // Add fallback text for empty rationale
  const portfolioRationale = data?.portfolioAdjustment?.rationale
    ?? (data as any)?.reasoning
    ?? (vetoActive
        ? `Momentum dampener active at ${((typeof dampenerApplied === 'number' && isFinite(dampenerApplied)) ? Math.round(dampenerApplied * 100) : 0)}% — reduce position sizes accordingly.`
        : 'No momentum conflicts detected — maintain current allocation at full size.');
  // Get assets from either assetMomentum or assets field
  const assets = (data as any)?.assetMomentum ?? data?.assets ?? [];

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
          <span className="section-tag">29</span>
          <h2 className="section-title">Momentum Veto</h2>
          <span className={`section-meta ${vetoActive ? 'text-red' : 'text-green'}`}>
            {vetoActive ? 'VETO' : 'PASS'} | Regime: {regime.current ? regime.current.toUpperCase() : '—'}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Status Header */}
        <div className={`p-3 border ${vetoActive ? 'bg-red-dim border-red' : 'bg-green-dim border-green'}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className={`w-4 h-4 ${vetoActive ? 'text-red' : 'text-green'}`} />
              <div>
                <div className="text-2xs text-text-tertiary">Filter Status</div>
                <div className={`text-lg font-mono font-bold ${vetoActive ? 'text-red' : 'text-green'}`}>
                  {vetoActive ? 'VETO ACTIVE' : 'PASS'}
                </div>
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-tertiary">Dampener</div>
              <div className="text-sm font-mono text-text-primary">{(typeof dampenerApplied === 'number' && isFinite(dampenerApplied)) ? Math.round(dampenerApplied * 100) : 0}%</div>
            </div>
          </div>
        </div>

        {/* Portfolio Adjustment */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-text-primary">Portfolio Adjustment</span>
            <span className={portfolioAction === 'reduce_risk' ? 'signal-tag bearish' : 'signal-tag bullish'}>
              {(portfolioAction ?? '').replace(/_/g, ' ').toUpperCase()}
            </span>
          </div>
          {(typeof portfolioMagnitude === 'number' && isFinite(portfolioMagnitude) && portfolioMagnitude > 0) && (
            <div className="text-xs text-text-secondary mb-1">
              Magnitude: <span className="font-mono text-amber">{Math.round(portfolioMagnitude * 100)}%</span>
            </div>
          )}
          <p className="text-2xs text-text-tertiary">{portfolioRationale}</p>
        </div>

        {/* Asset Momentum Grid */}
        <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Asset Momentum (12-1 month)</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {/* FIXED: Show unavailable message when no assets (BUG 10) */}
          {assets.length === 0 ? (
            <div className="p-3 bg-surface-1 border border-border text-text-secondary text-xs">
              Asset momentum unavailable
            </div>
          ) : assets.map((asset: any) => (
            <div key={asset?.asset ?? 'unknown'} className={`p-2 border ${(asset?.rawSignal ?? '').includes('negative') ? 'bg-red-dim border-red' : 'bg-surface-1 border-border'}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-text-primary">{asset?.asset ?? 'Unknown'}</span>
                <div className="flex items-center gap-2">
                  {getSignalIcon(asset?.rawSignal ?? '')}
                  <span className={getSignalTag(asset?.rawSignal ?? '')}>
                    {(asset?.rawSignal ?? '').replace(/_/g, ' ')}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs mb-1">
                <div>
                  <span className="text-2xs text-text-tertiary">12M:</span>
                  <span className={`font-mono ml-1 ${(asset?.return12m ?? 0) >= 0 ? 'text-green' : 'text-red'}`}>
                    {fmtChange(asset?.return12m)}
                  </span>
                </div>
                <div>
                  <span className="text-2xs text-text-tertiary">12-1 Mo:</span>
                  <span className={`font-mono ml-1 ${(asset?.momentum12_1 ?? 0) >= 0 ? 'text-green' : 'text-red'}`}>
                    {fmtChange(asset?.momentum12_1)}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs">
                <span className="text-2xs text-text-tertiary">Dampened: {fmtChange(asset?.dampenedSignal)}</span>
                <span className={`text-2xs font-medium ${(asset?.interpretation ?? '').includes('VETO') ? 'text-red' : 'text-green'}`}>
                  {asset?.interpretation ?? ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

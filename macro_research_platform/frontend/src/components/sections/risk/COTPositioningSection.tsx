// COT Positioning Section — CFTC Commitments of Traders analysis + Phase 2 Format Library
// Shows speculative positioning extremes with contrarian signals

import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useMacroStore } from '@/store/macroStore';
import { useApiData } from '@/hooks/useApiData';
import { fmtPriceInt } from '@/utils/format';

interface COTContract {
  name?: string;
  contract?: string;
  asset_etf?: string;
  speculator_longs?: number;
  speculator_shorts?: number;
  net_position?: number;
  net_speculative_pct?: number;
  percentile_rank?: number;
  contrarian_signal?: 'FADE_LONG' | 'FADE_SHORT' | 'NEUTRAL';
  extreme_long?: boolean;
  extreme_short?: boolean;
  extreme?: boolean;
  net_change?: number;
  net_change_wk?: number;
  report_date?: string;
  interpretation?: string;
  positioning?: 'NET_LONG' | 'NET_SHORT';
}

interface COTData {
  contracts: COTContract[];
  extreme_positions?: number;
  contrarian_signals?: number;
  last_updated?: string;
  report_date?: string;
}

export function COTPositioningSection() {
  const { data, loading, error } = useApiData<COTData>('/api/cot');

  // Use macro store for regime context
  const regime = useMacroStore((state) => state.regime);

  if (loading) {
    return (
      <div id="cot-positioning" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">COT</span>
            <h2 className="section-title">CFTC Positioning</h2>
          </div>
        </div>
        <div className="p-4 bg-surface-1 border border-border text-center text-text-tertiary">
          Loading COT data...
        </div>
      </div>
    );
  }

  if (error || !data || !data.contracts || data.contracts.length === 0) {
    return (
      <div id="cot-positioning" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">COT</span>
            <h2 className="section-title">CFTC Positioning</h2>
          </div>
        </div>
        <div className="p-4 bg-surface-1 border border-border text-center text-text-tertiary">
          {error?.message || 'COT data unavailable'}
        </div>
      </div>
    );
  }

  const getSignalBadge = (signal: string) => {
    switch (signal) {
      case 'FADE_LONG':
        return (
          <span className="flex items-center gap-1 px-2 py-1 bg-red-dim border border-red text-red text-xs font-medium">
            <TrendingUp className="w-3 h-3" />
            FADE LONG
          </span>
        );
      case 'FADE_SHORT':
        return (
          <span className="flex items-center gap-1 px-2 py-1 bg-green-dim border border-green text-green text-xs font-medium">
            <TrendingDown className="w-3 h-3" />
            FADE SHORT
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1 px-2 py-1 bg-surface-2 border border-border text-text-tertiary text-xs">
            <Minus className="w-3 h-3" />
            NEUTRAL
          </span>
        );
    }
  };

  const getChangeIcon = (change: number) => {
    if (change > 0) return <TrendingUp className="w-3 h-3 text-green" />;
    if (change < 0) return <TrendingDown className="w-3 h-3 text-red" />;
    return <Minus className="w-3 h-3 text-text-tertiary" />;
  };

  // Normalize contract data to handle both API and expected formats
  const normalizedContracts = data.contracts.map((c) => ({
    contract: c.name || c.contract || 'Unknown',
    asset_etf: c.asset_etf || (c.name?.includes('S&P') ? 'SPY' : c.name?.includes('Treasury') ? 'IEF' : c.name?.includes('Gold') ? 'GLD' : c.name?.includes('Euro') ? 'FXE' : c.name?.includes('Oil') ? 'USO' : '—'),
    net_position: c.net_position ?? 0,
    net_change: c.net_change ?? c.net_change_wk ?? 0,
    extreme_long: c.extreme_long || (c.positioning === 'NET_LONG' && c.extreme) || false,
    extreme_short: c.extreme_short || (c.positioning === 'NET_SHORT' && c.extreme) || false,
    net_speculative_pct: c.net_speculative_pct ?? (c.net_position ? (c.net_position / 100000) * 100 : 0),
    percentile_rank: c.percentile_rank ?? 50,
    contrarian_signal: c.contrarian_signal || 'NEUTRAL',
  }));

  // Get contrarian signals summary
  const contrarianLongs = normalizedContracts.filter(c => c.contrarian_signal === 'FADE_SHORT');
  const contrarianShorts = normalizedContracts.filter(c => c.contrarian_signal === 'FADE_LONG');

  return (
    <div id="cot-positioning" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">COT</span>
          <h2 className="section-title">CFTC Positioning</h2>
          <span className="section-meta">
            Regime: {regime.current ? regime.current.toUpperCase() : '—'} | {data.extreme_positions ?? normalizedContracts.filter(c => c.extreme_long || c.extreme_short).length} extreme positions
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Contrarian Signals Alert Box */}
        {(contrarianLongs.length > 0 || contrarianShorts.length > 0) && (
          <div className="p-3 border border-bloomberg bg-bloomberg-muted">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-bloomberg flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="text-sm font-medium text-bloomberg mb-1">
                  CONTRARIAN SIGNALS DETECTED
                </div>
                <div className="text-xs text-text-secondary space-y-0.5">
                  {contrarianLongs.length > 0 && (
                    <div>Long {contrarianLongs.map(c => c.asset_etf).join(', ')}</div>
                  )}
                  {contrarianShorts.length > 0 && (
                    <div>Short {contrarianShorts.map(c => c.asset_etf).join(', ')}</div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* COT Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  Contract
                </th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  ETF
                </th>
                <th className="text-right py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  Net Position
                </th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  Positioning
                </th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  Signal
                </th>
                <th className="text-right py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  WoW Chg
                </th>
              </tr>
            </thead>
            <tbody>
              {(normalizedContracts ?? []).filter(c => c != null).map((contract) => (
                <tr
                  key={contract.contract}
                  className={cn(
                    "border-b border-border-subtle last:border-0 hover:bg-surface-3 transition-colors",
                    contract.extreme_long && "bg-red-dim/20",
                    contract.extreme_short && "bg-green-dim/20"
                  )}
                >
                  <td className="py-2 px-2">
                    <div className="text-sm text-text-primary">{contract.contract}</div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className="text-xs font-mono text-text-secondary">
                      {contract.asset_etf}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right">
                    <span className={cn(
                      'font-mono text-sm',
                      contract.net_position > 0 ? 'text-green' : 'text-red'
                    )}>
                      {contract.net_position > 0 ? '+' : ''}
                      {contract.net_position != null ? fmtPriceInt(contract.net_position) : '—'}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className={cn(
                      'text-xs font-medium',
                      contract.extreme_long ? 'text-red' :
                      contract.extreme_short ? 'text-green' :
                      'text-text-secondary'
                    )}>
                      {contract.extreme_long ? 'EXTREME LONG' :
                       contract.extreme_short ? 'EXTREME SHORT' :
                       contract.net_position > 0 ? 'NET LONG' : 'NET SHORT'}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-center">
                    {getSignalBadge(contract.contrarian_signal)}
                  </td>
                  <td className="py-2 px-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {getChangeIcon(contract.net_change)}
                      <span className={cn(
                        'text-xs font-mono',
                        contract.net_change > 0 ? 'text-green' :
                        contract.net_change < 0 ? 'text-red' :
                        'text-text-tertiary'
                      )}>
                        {contract.net_change > 0 ? '+' : ''}
                        {contract.net_change != null ? fmtPriceInt(contract.net_change) : '—'}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-4 text-2xs text-text-tertiary">
          <div className="flex items-center gap-1">
            <div className="w-3 h-1.5 bg-green" />
            <span>Speculative Short (&lt;15th percentile)</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-1.5 bg-red" />
            <span>Speculative Long (&gt;85th percentile)</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-3 h-1.5 bg-text-tertiary" />
            <span>Neutral range</span>
          </div>
        </div>
      </div>
    </div>
  );
}

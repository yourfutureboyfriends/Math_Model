// Phase 8 — CTA Trend Following Section (Redesigned)
// Multi-timeframe trend signals with terminal aesthetic

import { TrendingUp, TrendingDown, Minus, AlertTriangle, Activity, ArrowRightLeft } from 'lucide-react';
import { ComputedTag } from '@/components/ui/ComputedTag';
import type { TrendSignalsData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface CTATrendSectionProps {
  data?: TrendSignalsData;
}

export function CTATrendSection({ data: dataProp }: CTATrendSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  let data = dataProp;
  if (!data) data = (_fullDash as any)?.trendSignals as any;
  if (!data) return null;

  // The backend payload is a flat list ({signals:[{asset,direction,strength,timeframe,
  // confidence}]}). Group it by asset into the fast/medium/slow shape this view renders,
  // and derive the summary/ctaSignal so it shows real trend data instead of crashing.
  const anyData = data as any;
  let ctaSignal: string = anyData.ctaSignal;
  let summary: any = anyData.summary;
  let assets: any[] = anyData.assets;
  const contradictions: any[] = anyData.contradictions ?? [];

  if (!assets && Array.isArray(anyData.signals)) {
    const byAsset: Record<string, any> = {};
    for (const s of anyData.signals) {
      const key = s.asset ?? '—';
      byAsset[key] ??= { ticker: key, name: key, signals: {}, direction: 'NO TREND' };
      const tf = String(s.timeframe ?? '');
      const slot = /^(10d|1m|short|fast)/i.test(tf) ? 'fast' : /^(30d|3m|med)/i.test(tf) ? 'medium' : 'slow';
      const dir = String(s.direction ?? '').toUpperCase();
      const sign = dir === 'LONG' ? 1 : dir === 'SHORT' ? -1 : 0;
      byAsset[key].signals[slot] = { signal: sign, return: s.strength != null ? Number(s.strength) * 100 * (sign || 1) : null };
    }
    assets = Object.values(byAsset).map((a: any) => {
      for (const sl of ['fast', 'medium', 'slow']) a.signals[sl] ??= { signal: null, return: null };
      const net = ['fast', 'medium', 'slow'].reduce((x, sl) => x + (a.signals[sl].signal ?? 0), 0);
      a.direction = net > 0 ? 'UPTREND' : net < 0 ? 'DOWNTREND' : 'NO TREND';
      return a;
    });
    const up = assets.filter((a) => a.direction === 'UPTREND').length;
    const down = assets.filter((a) => a.direction === 'DOWNTREND').length;
    ctaSignal = up > down ? 'BULLISH' : down > up ? 'BEARISH' : 'NEUTRAL';
    summary = { uptrends: up, downtrends: down, contradictions: 0,
      overallTrendRegime: ctaSignal === 'BULLISH' ? 'Bullish' : ctaSignal === 'BEARISH' ? 'Bearish' : 'Mixed' };
  }
  ctaSignal ??= 'NEUTRAL';
  summary ??= { uptrends: 0, downtrends: 0, contradictions: 0, overallTrendRegime: 'Mixed' };
  assets ??= [];

  const getTrendIcon = (direction: string | undefined) => {
    switch (direction) {
      case 'UPTREND':
        return <TrendingUp className="w-3 h-3 text-green" />;
      case 'DOWNTREND':
        return <TrendingDown className="w-3 h-3 text-red" />;
      default:
        return <Minus className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getTrendColor = (direction: string | undefined) => {
    switch (direction) {
      case 'UPTREND':
        return 'text-green';
      case 'DOWNTREND':
        return 'text-red';
      default:
        return 'text-text-tertiary';
    }
  };

  const getSignalArrow = (signal: number | undefined | null) => {
    if (signal == null) return <Minus className="w-3 h-3 text-text-tertiary" />;
    if (signal > 0) return <TrendingUp className="w-3 h-3 text-green" />;
    if (signal < 0) return <TrendingDown className="w-3 h-3 text-red" />;
    return <Minus className="w-3 h-3 text-text-tertiary" />;
  };

  return (
    <div id="cta-trend" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">32</span>
          <h2 className="section-title">CTA Trend Following</h2>
          <span className={`section-meta ${ctaSignal === 'BULLISH' ? 'text-green' : ctaSignal === 'BEARISH' ? 'text-red' : 'text-text-secondary'}`}>
            {ctaSignal}
          </span>
        </div>
        <ComputedTag section="trendSignals" />
      </div>

      <div className="space-y-3">
        {/* Summary Bar */}
        <div className="flex items-center justify-between p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2">
            <Activity className="w-3 h-3 text-text-secondary" />
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider">CTA Signal</div>
              <div className={`text-base font-mono font-bold ${ctaSignal === 'BULLISH' ? 'text-green' : ctaSignal === 'BEARISH' ? 'text-red' : 'text-text-secondary'}`}>
                {ctaSignal}
              </div>
            </div>
          </div>
          <div className="flex gap-4 text-right">
            <div>
              <div className="text-2xs text-text-tertiary">Up</div>
              <div className="text-sm font-mono font-bold text-green">{summary.uptrends}</div>
            </div>
            <div>
              <div className="text-2xs text-text-tertiary">Down</div>
              <div className="text-sm font-mono font-bold text-red">{summary.downtrends}</div>
            </div>
            <div>
              <div className="text-2xs text-text-tertiary">Contra</div>
              <div className={`text-sm font-mono font-bold ${summary.contradictions > 0 ? 'text-amber' : 'text-text-secondary'}`}>
                {summary.contradictions}
              </div>
            </div>
          </div>
        </div>

        {/* Contradictions Alert */}
        {(contradictions?.length ?? 0) > 0 && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-3 h-3 text-amber" />
              <span className="text-xs font-medium text-amber">
                Regime Contractions
              </span>
            </div>
            <div className="space-y-1">
              {(contradictions ?? []).map((contradiction, idx) => (
                <div key={idx} className="flex items-center gap-2 text-xs">
                  <ArrowRightLeft className="w-3 h-3 text-amber" />
                  <span className="text-text-secondary">{contradiction.ticker}:</span>
                  <span className="text-text-tertiary">{contradiction.expected}</span>
                  <span className="text-amber">→</span>
                  <span className="text-red">{contradiction.actual}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Asset Trend Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-2">
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Asset</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">1M</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">3M</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">12M</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Trend</th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {(assets ?? []).map((asset) => (
                <tr
                  key={asset.ticker}
                  className={`border-b border-border-subtle last:border-0 ${asset.contradiction ? 'bg-amber-dim' : ''}`}
                >
                  <td className="py-2 px-2">
                    <div>
                      <div className="text-sm font-medium text-text-primary">{asset.ticker}</div>
                      <div className="text-2xs text-text-tertiary">{asset.name}</div>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getSignalArrow(asset.signals.fast.signal)}
                      <span className={`font-mono text-2xs ${(asset.signals.fast.return ?? 0) >= 0 ? 'text-green' : 'text-red'}`}>
                        {asset.signals.fast.return != null && typeof asset.signals.fast.return === 'number' && isFinite(asset.signals.fast.return)
                          ? `${asset.signals.fast.return >= 0 ? '+' : ''}${asset.signals.fast.return.toFixed(1)}%`
                          : '—'}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getSignalArrow(asset.signals.medium.signal)}
                      <span className={`font-mono text-2xs ${(asset.signals.medium.return ?? 0) >= 0 ? 'text-green' : 'text-red'}`}>
                        {asset.signals.medium.return != null && typeof asset.signals.medium.return === 'number' && isFinite(asset.signals.medium.return)
                          ? `${asset.signals.medium.return >= 0 ? '+' : ''}${asset.signals.medium.return.toFixed(1)}%`
                          : '—'}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getSignalArrow(asset.signals.slow.signal)}
                      <span className={`font-mono text-2xs ${(asset.signals.slow.return ?? 0) >= 0 ? 'text-green' : 'text-red'}`}>
                        {asset.signals.slow.return != null && typeof asset.signals.slow.return === 'number' && isFinite(asset.signals.slow.return)
                          ? `${asset.signals.slow.return >= 0 ? '+' : ''}${asset.signals.slow.return.toFixed(1)}%`
                          : '—'}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <div className="flex items-center justify-center gap-1">
                      {getTrendIcon(asset.direction ?? 'NO TREND')}
                      <span className={`font-mono text-2xs ${getTrendColor(asset.direction ?? 'NO TREND')}`}>
                        {(asset.direction ?? 'N').charAt(0)}
                      </span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    {asset.contradiction ? (
                      <span className="signal-tag warning">Divergence</span>
                    ) : (
                      <span className="signal-tag bullish">Confirmed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Interpretation */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Trend Regime</div>
          <p className="text-xs text-text-secondary">
            {summary.overallTrendRegime === 'Bullish' && 'Broad-based uptrends across asset classes suggest positive momentum regime.'}
            {summary.overallTrendRegime === 'Bearish' && 'Broad-based downtrends across asset classes suggest negative momentum regime.'}
            {summary.overallTrendRegime === 'Mixed' && 'Mixed trend signals with conflicting momentum across asset classes.'}
            {summary.contradictions > 0 && ` ${summary.contradictions} asset(s) contradict regime expectations.`}
          </p>
          {/* FIXED: BUG-C2 - Add divergence warning when CTA contradicts macro regime */}
          {(contradictions?.length ?? 0) > 0 && (
            <div className="text-amber text-xs mt-2">
              ⚠ {contradictions.length} asset(s) contradict Slowdown regime —
              momentum may be running ahead of macro fundamentals.
              Consider reducing CTA weight vs macro signal.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

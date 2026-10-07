// Long-Run Return Assumptions — building-block capital market assumptions by asset class
// Long-term return expectations with terminal aesthetic

import { Clock, AlertTriangle } from 'lucide-react';
import { ComputedTag } from '@/components/ui/ComputedTag';
import { CsvButton } from '@/components/ui/CsvButton';
import type { GMOForecastsData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface GMOForecastsSectionProps {
  data?: GMOForecastsData;
}

export function GMOForecastsSection({ data: dataProp }: GMOForecastsSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  let data = dataProp;
  if (!data) data = (_fullDash as any)?.gmoForecasts as any;
  if (!data) return null;

  const getSignalTag = (signal: string) => {
    switch (signal) {
      case 'STRONG BUY':
      case 'BUY':
        return 'signal-tag bullish';
      case 'AVOID':
      case 'STRONG AVOID':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  // Backend payload is {forecasts:[{assetClass, expectedReturn, volatility, sharpeRatio,
  // confidence}]}; normalize each to the {ticker, totalExpectedReturn, signal, gmoNote}
  // shape this view renders, and derive the summary so it shows real forecasts.
  const anyData = data as any;
  const signalFor = (r: number) =>
    r >= 8 ? 'STRONG BUY' : r >= 5 ? 'BUY' : r >= 2 ? 'NEUTRAL' : r >= 0 ? 'AVOID' : 'STRONG AVOID';
  const forecasts = (anyData.forecasts ?? []).map((f: any) => {
    const ret: number | null = f.totalExpectedReturn ?? f.expectedReturn ?? null;   // missing stays missing
    return {
      ticker: f.ticker ?? f.assetClass,
      assetClass: f.assetClass,
      totalExpectedReturn: ret,
      signal: f.signal ?? (ret == null ? 'N/A' : signalFor(ret)),
      components: (f.components ?? {}) as Record<string, number>,
      gmoNote: f.gmoNote ?? (f.volatility != null
        ? `Vol ${Number(f.volatility).toFixed(1)}%${f.sharpeRatio != null ? ` · Sharpe ${Number(f.sharpeRatio).toFixed(2)}` : ''}`
        : ''),
    };
  });
  const summary = anyData.summary ?? {
    avgExpectedReturn: (() => {
      const xs = forecasts.map((f: any) => f.totalExpectedReturn).filter((x: any) => typeof x === 'number');
      return xs.length ? xs.reduce((a: number, b: number) => a + b, 0) / xs.length : null;
    })(),
    strongBuy: forecasts.filter((f: any) => f.signal === 'STRONG BUY').length,
    buy: forecasts.filter((f: any) => f.signal === 'BUY').length,
    neutral: forecasts.filter((f: any) => f.signal === 'NEUTRAL').length,
    avoid: forecasts.filter((f: any) => f.signal === 'AVOID').length,
    strongAvoid: forecasts.filter((f: any) => f.signal === 'STRONG AVOID').length,
  };
  const tensions = anyData.tensions ?? [];

  // Sort by expected return descending
  const sortedForecasts = [...forecasts].sort(
    (a, b) => (b.totalExpectedReturn ?? -1e9) - (a.totalExpectedReturn ?? -1e9)
  );

  const maxReturn = Math.max(...sortedForecasts.map((f) => Math.abs(f.totalExpectedReturn ?? 0)), 1);
  const COMPONENT_COLORS: Record<string, string> = { earnings_yield: '#3987e5', inflation: '#c98500', yield: '#199e70', current_yield: '#199e70', growth: '#d55181', valuation: '#9085e9' };
  const componentLabel = (k: string) => k.replace(/_/g, ' ');
  const componentKeys = Array.from(new Set(forecasts.flatMap((f: any) => Object.keys(f.components ?? {})))) as string[];

  return (
    <div id="gmo-forecasts" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Long-Run Return Assumptions</h2>
        </div>
        <div className="flex items-center gap-2">
          <CsvButton
            filename="gmo-forecasts"
            getData={() => ({
              columns: ['Asset Class', 'Ticker', 'Expected Return %', 'Signal'],
              rows: sortedForecasts.map((f) => [f.assetClass, f.ticker, f.totalExpectedReturn, f.signal]),
            })}
          />
          <ComputedTag section="gmoForecasts" />
        </div>
      </div>

      <div className="space-y-3">
        {/* Summary stats */}
        <div className="flex items-center justify-between p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2">
            <Clock className="w-3 h-3 text-text-secondary" />
            <span className="text-xs text-text-secondary">Average Expected Return</span>
          </div>
          <div className="font-mono text-sm text-text-primary">
            {summary?.avgExpectedReturn == null ? '—' : `${summary.avgExpectedReturn > 0 ? '+' : ''}${summary.avgExpectedReturn.toFixed(1)}%`}
          </div>
        </div>

        {componentKeys.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 text-[10px] text-text-tertiary px-1">
            <span>Building blocks:</span>
            {componentKeys.map((k) => (
              <span key={k} className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm" style={{ background: COMPONENT_COLORS[k] ?? '#6b7280' }} />{componentLabel(k)}</span>
            ))}
          </div>
        )}

        {/* Forecast table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-2">
                <th className="text-left py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Asset</th>
                <th className="text-right py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Return</th>
                <th className="text-center py-2 px-3 text-2xs text-text-tertiary uppercase font-medium">Signal</th>
              </tr>
            </thead>
            <tbody>
              {sortedForecasts.map((forecast) => {
                const return_pct: number | null = forecast.totalExpectedReturn;
                const comps = Object.entries(forecast.components ?? {}).filter(([, v]) => typeof v === 'number' && (v as number) > 0) as [string, number][];
                return (
                  <tr key={forecast.ticker} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3">
                      <div>
                        <div className="text-sm font-medium text-text-primary">{forecast.assetClass}</div>
                        <div className="text-2xs text-text-tertiary">{forecast.ticker}</div>
                        {tensions?.some((t: any) => t.assetClass === forecast.assetClass && t.divergence) && (
                          <div className="flex items-center gap-1 mt-1 text-amber">
                            <AlertTriangle className="w-3 h-3" />
                            <span className="text-2xs">Tactical tension</span>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-2">
                        {/* Building blocks stacked to the total (scale shared across assets) */}
                        <div className="w-32 h-2 bg-surface-3 flex overflow-hidden rounded-sm" aria-hidden="true"
                          title={comps.map(([k, v]) => `${componentLabel(k)} ${v.toFixed(1)}%`).join(' + ')}>
                          {comps.length > 0
                            ? comps.map(([k, v]) => (
                                <div key={k} style={{ width: `${(v / Math.max(maxReturn, 8)) * 100}%`, background: COMPONENT_COLORS[k] ?? '#6b7280' }} />
                              ))
                            : return_pct != null && return_pct > 0 && <div style={{ width: `${(return_pct / Math.max(maxReturn, 8)) * 100}%`, background: '#199e70' }} />}
                        </div>
                        <span className={`font-mono text-sm ${return_pct == null ? 'text-text-tertiary' : return_pct >= 0 ? 'text-green' : 'text-red'}`}>
                          {return_pct == null ? '—' : `${return_pct > 0 ? '+' : ''}${return_pct.toFixed(1)}%`}
                        </span>
                      </div>
                      <p className="text-2xs text-text-secondary mt-1">{forecast.gmoNote}</p>
                    </td>
                    <td className="py-2 px-3 text-center">
                      <span className={getSignalTag(forecast.signal)}>
                        {String(forecast.signal).replace('STRONG ', 'S-')}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Methodology Disclaimer */}
        <div className="p-3 bg-surface-2 border border-border-subtle">
          <div className="text-2xs text-text-tertiary leading-relaxed">
            <strong>Methodology:</strong> Building-block capital market assumptions — equities: earnings yield + 10Y breakeven inflation; bonds: current yield. Not a valuation mean-reversion forecast.
            Volatility is the proxy ETF&apos;s realised 2-year volatility; Sharpe uses the 3M T-bill.
          </div>
        </div>

        {/* Signal distribution */}
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-1 text-center">
          <div className="p-2 bg-surface-1 border border-green/30">
            <div className="text-sm font-mono font-bold text-green">{summary?.strongBuy || 0}</div>
            <div className="text-2xs text-text-tertiary">Strong Buy</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-sm font-mono font-bold text-green">{summary?.buy || 0}</div>
            <div className="text-2xs text-text-tertiary">Buy</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-sm font-mono font-bold text-text-primary">{summary?.neutral || 0}</div>
            <div className="text-2xs text-text-tertiary">Neutral</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-sm font-mono font-bold text-amber">{summary?.avoid || 0}</div>
            <div className="text-2xs text-text-tertiary">Avoid</div>
          </div>
          <div className="p-2 bg-surface-1 border border-red/30">
            <div className="text-sm font-mono font-bold text-red">{summary?.strongAvoid || 0}</div>
            <div className="text-2xs text-text-tertiary">Strong Avoid</div>
          </div>
        </div>
      </div>
    </div>
  );
}

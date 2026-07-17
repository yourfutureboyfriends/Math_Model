/**
 * AltDataSection — Phase 7 alternative-data positioning signals.
 *
 * VIX term structure (contango/backwardation), cross-market correlation-breakdown alerts
 * (SPY vs duration/USD/gold/credit), and credit-spread stress — all from real yfinance/
 * FRED data via /api/v1/altdata/positioning. Surfaces positioning stress that often leads
 * price.
 */
import { useCallback, useEffect, useState } from 'react';
import { Radar, RefreshCw, AlertTriangle } from 'lucide-react';

export function AltDataSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/v1/altdata/positioning');
      setData(r.ok ? await r.json() : { available: false });
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const t = data?.vix_term_structure;
  const cr = data?.credit;
  const alerts = data?.correlation_alerts ?? [];
  const termStateTone = t?.state === 'backwardation' ? 'text-red' : t?.state === 'contango' ? 'text-green' : 'text-text-secondary';
  const creditTone = cr?.signal === 'stress' ? 'text-red' : cr?.signal === 'complacent' ? 'text-amber' : 'text-text-secondary';

  return (
    <div id="alt-data" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Radar className="w-3 h-3" /></span>
          <h2 className="section-title">Alt-Data Positioning</h2>
        </div>
        <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-6 text-center text-sm text-text-secondary">Loading positioning signals…</div>}

      {data?.available && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          {/* VIX term structure */}
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">VIX Term Structure</div>
            <div className="flex items-end justify-between gap-1 h-16 mb-2">
              {(['9d', 'spot', '3m', '6m'] as const).map((k) => {
                const v = t?.points?.[k];
                const maxv = Math.max(...Object.values(t?.points || {}).filter((x: any) => x) as number[], 1);
                return (
                  <div key={k} className="flex-1 flex flex-col items-center justify-end h-full">
                    <span className="text-2xs font-mono text-text-secondary mb-0.5">{v != null ? v.toFixed(1) : '—'}</span>
                    <div className="w-full bg-bloomberg" style={{ height: `${v ? (v / maxv) * 100 : 0}%` }} />
                    <span className="text-2xs text-text-tertiary mt-0.5">{k}</span>
                  </div>
                );
              })}
            </div>
            <div className={`text-sm font-mono font-bold ${termStateTone}`}>{(t?.state || 'unknown').toUpperCase()}</div>
            <div className="text-2xs text-text-secondary">{t?.interpretation}</div>
          </div>

          {/* Correlation breakdown alerts */}
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Cross-Market Correlations (63d)</div>
            <div className="space-y-1.5">
              {alerts.map((a: any) => (
                <div key={a.pair} className="flex items-center justify-between text-xs">
                  <span className="text-text-secondary flex items-center gap-1">
                    {a.breakdown && <AlertTriangle className="w-3 h-3 text-amber" />}{a.pair}
                  </span>
                  {a.available ? (
                    <span className="font-mono">
                      <span className={a.current_correlation >= 0 ? 'text-green' : 'text-red'}>{a.current_correlation >= 0 ? '+' : ''}{a.current_correlation.toFixed(2)}</span>
                      <span className="text-text-tertiary"> (z {a.zscore ?? '—'})</span>
                    </span>
                  ) : <span className="text-2xs text-text-tertiary">n/a</span>}
                </div>
              ))}
            </div>
            <div className="text-2xs text-text-tertiary pt-1.5 mt-1 border-t border-border-subtle">
              ⚠ = correlation &gt; 2σ from its history (potential regime-change tell).
            </div>
          </div>

          {/* Credit stress */}
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Credit Stress (ICE BofA OAS)</div>
            {cr?.available ? (
              <div className="space-y-1 text-xs">
                <div className="flex justify-between"><span className="text-text-secondary">HY OAS</span><span className="font-mono text-text-primary">{cr.hy_oas_bps} bps</span></div>
                <div className="flex justify-between"><span className="text-text-secondary">IG OAS</span><span className="font-mono text-text-primary">{cr.ig_oas_bps} bps</span></div>
                <div className="flex justify-between"><span className="text-text-secondary">HY − IG</span><span className="font-mono text-text-primary">{cr.hy_ig_spread_bps} bps</span></div>
                <div className="flex justify-between"><span className="text-text-secondary">HY z-score</span><span className="font-mono text-text-primary">{cr.hy_zscore ?? '—'}</span></div>
                <div className="flex justify-between"><span className="text-text-secondary">HY percentile</span><span className="font-mono text-text-primary">{cr.hy_percentile ?? '—'}%</span></div>
                <div className={`text-sm font-mono font-bold pt-1 ${creditTone}`}>{(cr.signal || '').toUpperCase()}</div>
                <div className="text-2xs text-text-tertiary">
                  {cr.signal === 'complacent' ? 'Spreads unusually tight — little cushion for shocks.'
                    : cr.signal === 'stress' ? 'Spreads unusually wide — credit stress building.'
                    : 'Credit spreads near normal range.'}
                </div>
              </div>
            ) : <div className="text-2xs text-text-tertiary">Credit data unavailable.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

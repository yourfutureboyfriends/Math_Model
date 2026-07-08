/**
 * SignalScorecardSection — Phase 4 signal backtesting track records.
 *
 * Shows a walk-forward backtest scorecard per price-reconstructable signal (momentum,
 * trend, VIX vol-regime) on the S&P 500: hit rate, forward return by state, the Sharpe/
 * max-drawdown of following the signal, and a confusion matrix. Reads
 * /api/v1/signals/backtest. Builds trust in signals by showing their real history.
 */
import { useCallback, useEffect, useState } from 'react';
import { Award, RefreshCw } from 'lucide-react';

interface StateStat { avg_forward_return: number; count: number; }
interface Scorecard {
  id: string; label: string; hit_rate: number; observations: number; horizon_days: number;
  strategy_sharpe: number; strategy_max_drawdown: number; strategy_total_return: number;
  forward_return_by_state: Record<string, StateStat>;
  confusion_matrix: Record<string, { Up: number; Down: number }>;
}
interface Resp { available: boolean; reason?: string; period_days?: number; methodology?: string; signals: Scorecard[]; }

const pct = (v: number, dp = 1) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(dp)}%`;
const hitTone = (h: number) => (h >= 0.6 ? 'text-green' : h >= 0.5 ? 'text-amber' : 'text-red');

export function SignalScorecardSection() {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/v1/signals/backtest');
      setData(r.ok ? await r.json() : { available: false, reason: `HTTP ${r.status}`, signals: [] });
    } catch (e: any) {
      setData({ available: false, reason: e?.message || 'failed', signals: [] });
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div id="signal-scorecard" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Award className="w-3 h-3" /></span>
          <h2 className="section-title">Signal Scorecard</h2>
          {data?.available && <span className="section-meta">{data.period_days}d · S&P 500</span>}
        </div>
        <button onClick={load} title="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-6 text-center text-sm text-text-secondary">Backtesting signals…</div>}
      {data && !data.available && (
        <div className="p-6 bg-surface-1 border border-border text-center text-sm text-text-secondary">{data.reason}</div>
      )}

      {data?.available && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            {data.signals.map((s) => (
              <div key={s.id} className="p-3 bg-surface-1 border border-border">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-text-primary">{s.label}</span>
                  <span className="text-2xs text-text-tertiary">{s.horizon_days}d fwd · {s.observations} obs</span>
                </div>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className={`text-2xl font-mono font-bold ${hitTone(s.hit_rate)}`}>{(s.hit_rate * 100).toFixed(0)}%</span>
                  <span className="text-2xs text-text-tertiary uppercase tracking-wider">hit rate</span>
                </div>
                <div className="grid grid-cols-3 gap-1 mb-2 text-center">
                  {[
                    ['Sharpe', s.strategy_sharpe.toFixed(2), s.strategy_sharpe >= 0.5 ? 'text-green' : 'text-text-primary'],
                    ['Max DD', pct(s.strategy_max_drawdown, 0), 'text-red'],
                    ['Total', pct(s.strategy_total_return, 0), s.strategy_total_return >= 0 ? 'text-green' : 'text-red'],
                  ].map(([l, v, tone]) => (
                    <div key={l as string} className="bg-surface-2 py-1">
                      <div className="text-2xs text-text-tertiary">{l}</div>
                      <div className={`text-xs font-mono font-bold ${tone}`}>{v}</div>
                    </div>
                  ))}
                </div>
                {/* Forward return by state */}
                <div className="space-y-0.5 text-2xs">
                  {(['BULLISH', 'BEARISH', 'NEUTRAL'] as const).map((st) => {
                    const d = s.forward_return_by_state[st];
                    if (!d) return null;
                    return (
                      <div key={st} className="flex items-center justify-between">
                        <span className={st === 'BULLISH' ? 'text-green' : st === 'BEARISH' ? 'text-red' : 'text-text-tertiary'}>{st}</span>
                        <span className="font-mono text-text-secondary">
                          {pct(d.avg_forward_return)} avg fwd <span className="text-text-tertiary">({d.count})</span>
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
          {data.methodology && (
            <div className="text-2xs text-text-tertiary p-2 border border-border-subtle bg-surface-1">
              <span className="uppercase tracking-wider text-text-secondary">Methodology: </span>{data.methodology}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

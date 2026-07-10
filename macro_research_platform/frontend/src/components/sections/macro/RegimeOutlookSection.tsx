/**
 * RegimeOutlookSection — Phase 6B regime-transition early-warning.
 *
 * Turns the static current-regime label into a forward-looking statement: the empirical
 * next-period probability of staying vs shifting, ranked, with implied persistence — e.g.
 * "20% probability of shifting to Slowdown next month". Probabilities come from an empirical
 * transition matrix over a monthly regime history classified from real macro data.
 * Reads /api/v1/regime-transition. 3-state bounded load (Phase 9).
 */
import { useCallback, useEffect, useState } from 'react';
import { GitBranch, RefreshCw, AlertTriangle } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

export function RegimeOutlookSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/v1/regime-transition').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (!res.available) { setReason(res.reason || 'Unavailable.'); setData(null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const o = data?.outlook;
  const change = o?.most_likely_change;
  const pctChange = change ? Math.round(change.prob * 100) : 0;
  const warn = pctChange >= 25; // early-warning threshold

  return (
    <div id="regime-outlook" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><GitBranch className="w-3 h-3" /></span>
          <h2 className="section-title">Regime Transition Outlook</h2>
          {data && <DataLineagePopover lineage={{ source: data.source, fetched_at: data.as_of, formula: `Empirical P(next|current) over ${data.months_analysed} monthly regime classifications`, notes: data.note }} />}
        </div>
        <button onClick={() => load()} title="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Computing transition probabilities…</div>}
      {!loading && reason && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {data && o && (
        <div className="space-y-3">
          {/* Early-warning headline */}
          <div className={`p-3 border ${warn ? 'border-amber/50 bg-amber-dim' : 'border-border bg-surface-1'}`}>
            <div className="flex items-center gap-2">
              {warn && <AlertTriangle className="w-4 h-4 text-amber" />}
              <span className="text-sm text-text-primary">
                {change
                  ? <>Currently <span className="font-bold text-bloomberg">{data.current_regime}</span> — <span className={`font-bold font-mono ${warn ? 'text-amber' : 'text-text-primary'}`}>{pctChange}%</span> probability of shifting to <span className="font-bold">{change.to}</span> next month</>
                  : <>Currently <span className="font-bold text-bloomberg">{data.current_regime}</span> — no recorded transitions</>}
              </span>
            </div>
            <div className="text-2xs text-text-tertiary mt-1">
              Stay probability {Math.round((o.stay_prob ?? 0) * 100)}% · expected persistence ≈ {o.expected_persistence_periods ?? '—'} months · {data.months_analysed} months analysed
            </div>
          </div>

          {/* Forward probability bars */}
          <div className="space-y-1.5">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider">Next-period probabilities (from {data.current_regime})</div>
            {o.ranked.map((r: any) => {
              const pct = Math.round(r.prob * 100);
              const isCurrent = r.regime === data.current_regime;
              return (
                <div key={r.regime} className="flex items-center gap-2 text-xs">
                  <span className={`w-24 truncate ${isCurrent ? 'text-bloomberg' : 'text-text-secondary'}`}>{r.regime}</span>
                  <div className="flex-1 h-2.5 bg-surface-3">
                    <div className={`h-2.5 ${isCurrent ? 'bg-bloomberg' : 'bg-blue'}`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="font-mono tabular-nums w-10 text-right text-text-primary">{pct}%</span>
                </div>
              );
            })}
          </div>
          <div className="text-2xs text-text-tertiary">{data.note}</div>
        </div>
      )}
    </div>
  );
}

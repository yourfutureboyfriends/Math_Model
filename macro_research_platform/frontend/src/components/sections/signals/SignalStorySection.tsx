/**
 * SignalStorySection — Phase 2 storytelling layer.
 *
 * For each core signal (Growth, Inflation, Liquidity, Risk): the headline score, a
 * one-line auto-generated explanation naming the largest driver, and — on click — a
 * change-attribution breakdown of every input contribution, ranked by magnitude.
 * Reads /api/v1/signal-attribution. 3-state bounded load (Phase 9).
 */
import { useCallback, useEffect, useState } from 'react';
import { BookOpen, RefreshCw, ChevronDown } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

const TREND_TONE: Record<string, string> = {
  improving: 'text-green', steepening: 'text-green', loose: 'text-green', complacent: 'text-green', normal: 'text-green',
  deteriorating: 'text-red', inverted: 'text-red', tight: 'text-red', stress: 'text-red', elevated: 'text-amber',
  flattening: 'text-amber', neutral: 'text-text-secondary', stable: 'text-text-secondary',
};

export function SignalStorySection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/v1/signal-attribution').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (!res.available) { setReason(res.reason || 'Unavailable.'); setData(null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const signals = data?.signals ?? [];
  const maxContrib = (s: any) => Math.max(...s.contributions.map((c: any) => Math.abs(c.contribution)), 0.0001);

  return (
    <div id="signal-story" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><BookOpen className="w-3 h-3" /></span>
          <h2 className="section-title">Signal Storytelling</h2>
          {data && <DataLineagePopover lineage={{ source: data.source, fetched_at: data.as_of, staleness_threshold_seconds: 900, formula: 'Each score decomposed into ranked input contributions; largest = driver' }} />}
        </div>
        <button onClick={() => load()} title="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Attributing signals…</div>}
      {!loading && reason && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {signals.map((s: any) => {
            const isOpen = open === s.signal;
            return (
              <div key={s.signal} className="border border-border bg-surface-1">
                <button onClick={() => setOpen(isOpen ? null : s.signal)} className="w-full text-left p-3 hover:bg-surface-2">
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xs text-text-tertiary uppercase tracking-wider">{s.signal}</span>
                    <span className={`text-2xs font-mono uppercase ${TREND_TONE[s.trend] || 'text-text-secondary'}`}>{s.trend}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-2xl font-mono font-bold text-text-primary tabular-nums">{s.score.toFixed(2)}</span>
                    <ChevronDown className={`w-3 h-3 text-text-tertiary ml-auto transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                  </div>
                  {/* explanation subtitle (Phase 2A) */}
                  <div className={`text-2xs text-text-secondary mt-1 ${isOpen ? '' : 'truncate'}`} title={s.explanation_text}>
                    {s.explanation_text}
                  </div>
                </button>
                {/* change attribution breakdown (Phase 2B) */}
                {isOpen && (
                  <div className="px-3 pb-3 pt-1 border-t border-border-subtle space-y-1.5">
                    <div className="text-2xs text-text-tertiary uppercase tracking-wider">Contributions · driver: <span className="text-bloomberg">{s.driver}</span></div>
                    {s.contributions.map((c: any) => (
                      <div key={c.input} className="flex items-center gap-2 text-2xs">
                        <span className="w-32 text-text-secondary truncate">{c.input}</span>
                        <span className="font-mono text-text-primary tabular-nums w-16 text-right">{c.value}{c.unit}</span>
                        <div className="flex-1 h-2 bg-surface-3 relative">
                          <div className={`h-2 ${c.direction === 'positive' ? 'bg-green' : 'bg-red'}`}
                            style={{ width: `${Math.min(100, (Math.abs(c.contribution) / maxContrib(s)) * 100)}%` }} />
                        </div>
                        <span className={`font-mono tabular-nums w-12 text-right ${c.direction === 'positive' ? 'text-green' : 'text-red'}`}>
                          {c.contribution >= 0 ? '+' : ''}{c.contribution}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

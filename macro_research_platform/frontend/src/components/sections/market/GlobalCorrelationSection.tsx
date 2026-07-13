/**
 * GlobalCorrelationSection — correlation matrix ACROSS world markets.
 *
 * Real pairwise Pearson correlations of daily returns for global equity indices (S&P 500,
 * Nasdaq, FTSE, DAX, Euro Stoxx, Nikkei, Hang Seng, Shanghai, ASX 200, Nifty), major FX
 * (EUR/USD, USD/JPY, DXY) and cross-asset (Gold, WTI, UST 10Y). Reads /api/global-correlation.
 * 3-state bounded load.
 */
import { useCallback, useEffect, useState } from 'react';
import { Globe2, RefreshCw } from 'lucide-react';
import { CorrelationHeatmap } from '@/components/ui/CorrelationHeatmap';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

const WINDOWS = [30, 90, 252];

export function GlobalCorrelationSection() {
  const [window, setWindow] = useState(90);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);
  const [sel, setSel] = useState<{ a: string; b: string; v: number | null } | null>(null);

  const load = useCallback(async (w: number, attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([
        fetch(`/api/global-correlation?window=${w}`).then((r) => r.json()),
        timeout,
      ]);
      if (!res) {
        if (attempt < 1) { setTimeout(() => load(w, attempt + 1), 1500); return; }
        setReason('Timed out — data feed slow.'); setData(null);
      } else if (!res.available) { setReason(res.reason || 'Unavailable.'); setData(null); }
      else setData(res);
    } catch (e: any) {
      setReason(e?.message || 'Failed to load.'); setData(null);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(window); }, [window, load]);

  return (
    <div id="global-correlation" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Globe2 className="w-3 h-3" /></span>
          <h2 className="section-title">Global Market Correlations</h2>
          {data && (
            <DataLineagePopover lineage={{
              source: data.source,
              fetched_at: data.as_of,
              staleness_threshold_seconds: 3600,
              formula: `Pearson correlation of aligned daily returns over the trailing ${data.window} sessions (${data.observations} obs)`,
              notes: 'World indices + FX + cross-asset',
            }} />
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex border border-border">
            {WINDOWS.map((w) => (
              <button key={w} onClick={() => setWindow(w)}
                className={`px-2 py-0.5 text-2xs font-mono ${window === w ? 'bg-bloomberg-muted text-bloomberg' : 'text-text-tertiary hover:text-text-secondary'}`}>
                {w}d
              </button>
            ))}
          </div>
          <button onClick={() => load(window)} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {data && (
        <div className="flex items-center gap-3 mb-2 text-2xs text-text-tertiary">
          <span>{data.observations} obs · {data.window}d rolling · {data.labels?.length} markets</span>
          <span className="ml-auto">source: {data.source}</span>
        </div>
      )}

      {loading && !data && <div className="p-4 text-2xs text-text-tertiary">Computing global correlations…</div>}
      {!loading && reason && (
        <div className="p-4 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>
      )}
      {data && (
        <>
          <CorrelationHeatmap
            labels={data.labels}
            matrix={data.matrix}
            selected={sel}
            onCellClick={(a, b, v) => setSel({ a, b, v })}
          />
          {sel && (
            <div className="mt-3 p-2 bg-surface-1 border border-border text-xs flex items-center gap-3">
              <span className="font-mono text-text-primary">{sel.a} · {sel.b}</span>
              <span className={`font-mono font-bold ${sel.v === null ? 'text-text-tertiary' : sel.v >= 0 ? 'text-green' : 'text-red'}`}>
                {sel.v === null ? 'n/a' : sel.v.toFixed(2)}
              </span>
              <span className="text-2xs text-text-tertiary">
                {sel.v === null ? '' : Math.abs(sel.v) > 0.7 ? 'strong' : Math.abs(sel.v) > 0.4 ? 'moderate' : 'weak'}
                {sel.v !== null && (sel.v >= 0 ? ' positive' : ' negative')} correlation over {data.window}d
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

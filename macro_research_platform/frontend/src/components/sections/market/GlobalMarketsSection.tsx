/**
 * GlobalMarketsSection — major WORLD equity indices (not just US).
 *
 * S&P 500, Nasdaq, FTSE 100, DAX, Euro Stoxx 50, Nikkei 225, Hang Seng, Shanghai, ASX 200,
 * Nifty 50 — real live levels + daily % change. Reads /api/global-markets. 3-state bounded load;
 * indices that fail to quote render an explicit "n/a" rather than a fabricated value.
 */
import { useCallback, useEffect, useState } from 'react';
import { Globe, RefreshCw } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

interface WorldIndex {
  name: string; region: string; ticker: string;
  level: number | null; change1d: number | null; available?: boolean;
}

export function GlobalMarketsSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/global-markets').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (res.available === false) { setReason(res.reason || 'Unavailable.'); setData(res.markets ? res : null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const markets: WorldIndex[] = data?.markets ?? [];

  return (
    <div id="global-markets" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Globe className="w-3 h-3" /></span>
          <h2 className="section-title">Global Equity Markets</h2>
          {data && <DataLineagePopover lineage={{ source: data.source, fetched_at: data.as_of, formula: 'Live index close + 1-day % change per world exchange' }} />}
          {data?.regions_covered && <span className="section-meta">{data.regions_covered.length} regions</span>}
        </div>
        <button onClick={() => load()} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Loading world indices…</div>}
      {!loading && reason && !markets.length && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {markets.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
          {markets.map((m) => {
            const up = (m.change1d ?? 0) >= 0;
            const na = !m.available || m.level == null;
            return (
              <div key={m.ticker} className="p-2 border border-border-subtle bg-surface-1">
                <div className="text-2xs text-text-tertiary uppercase tracking-wider truncate" title={`${m.name} · ${m.region}`}>{m.region}</div>
                <div className="text-xs text-text-secondary truncate">{m.name}</div>
                {na ? (
                  <div className="text-sm font-mono text-text-tertiary mt-0.5">n/a</div>
                ) : (
                  <>
                    <div className="text-sm font-mono font-bold text-text-primary tabular-nums mt-0.5">
                      {m.level!.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                    <div className={`text-2xs font-mono tabular-nums ${m.change1d == null ? 'text-text-tertiary' : up ? 'text-green' : 'text-red'}`}>
                      {m.change1d == null ? '—' : `${up ? '+' : ''}${m.change1d.toFixed(2)}%`}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

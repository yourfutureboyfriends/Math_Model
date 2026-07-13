/**
 * RegionalMacroSection — cross-country macro comparison (economics by region).
 *
 * Real per-economy indicators from FRED's OECD series — CPI YoY, harmonized unemployment,
 * 10Y government bond yield — for the US, Euro Area, UK, Japan, Canada, Australia. Any series
 * that doesn't resolve shows "—" (never a fabricated value). Reads /api/regional-macro.
 */
import { useCallback, useEffect, useState } from 'react';
import { Globe, RefreshCw } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

export function RegionalMacroSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/regional-macro').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (res.available === false) { setReason(res.reason || 'Unavailable.'); setData(res.regions ? res : null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const regions = data?.regions ?? [];
  const indicators = data?.indicators ?? [];
  const fmt = (v: any) => (typeof v === 'number' ? `${v.toFixed(1)}%` : '—');

  return (
    <div id="regional-macro" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Globe className="w-3 h-3" /></span>
          <h2 className="section-title">Regional Macro Comparison</h2>
          {data && <DataLineagePopover lineage={{ source: data.source, fetched_at: data.as_of, formula: 'Latest per-country FRED/OECD series: CPI YoY, harmonized unemployment, 10Y govt yield' }} />}
        </div>
        <button onClick={() => load()} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Loading regional macro…</div>}
      {!loading && reason && !regions.length && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {regions.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-2xs text-text-tertiary uppercase tracking-wider">
                <th className="text-left font-normal pb-1">Economy</th>
                {indicators.map((ind: any) => (
                  <th key={ind.key} className="text-right font-normal pb-1">{ind.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {regions.map((r: any) => (
                <tr key={r.code} className="border-t border-border-subtle">
                  <td className="py-1.5 pr-2 text-text-primary">{r.region}</td>
                  {indicators.map((ind: any) => (
                    <td key={ind.key} className={`py-1.5 text-right font-mono tabular-nums ${r[ind.key] == null ? 'text-text-tertiary' : 'text-text-primary'}`}>
                      {fmt(r[ind.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="text-2xs text-text-tertiary mt-2">Source: {data.source} · "—" = series not available for that economy.</div>
        </div>
      )}
    </div>
  );
}

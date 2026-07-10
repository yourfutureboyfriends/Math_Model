/**
 * VaRStressSection — Phase 3 Value-at-Risk & stress testing.
 *
 * Real VaR (historical / parametric / Monte Carlo, 95-99%, 1d-10d) on the ingested
 * positions, VaR contribution by position, predefined historical stress scenarios, a
 * custom factor-shock builder, and concentration. Reads /api/v1/risk/{var,stress-test,
 * concentration}. Shows explicit "no positions" state when the book is empty.
 */
import { useCallback, useEffect, useState } from 'react';
import { ShieldAlert, RefreshCw } from 'lucide-react';

const usd = (v: number | null | undefined) =>
  v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

const CUSTOM_FACTORS = [
  ['equity', 'Equity'], ['rates', 'Rates'], ['credit', 'Credit'],
  ['commodity', 'Commodity'], ['usd', 'USD'], ['volatility', 'Vol'],
] as const;

export function VaRStressSection() {
  const [varData, setVarData] = useState<any>(null);
  const [stress, setStress] = useState<any>(null);
  const [conc, setConc] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [shocks, setShocks] = useState<Record<string, string>>({});
  const [custom, setCustom] = useState<any>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [v, s, c] = await Promise.all([
        fetch('/api/v1/risk/var').then((r) => r.json()).catch(() => null),
        fetch('/api/v1/risk/stress-test').then((r) => r.json()).catch(() => null),
        fetch('/api/v1/risk/concentration').then((r) => r.json()).catch(() => null),
      ]);
      setVarData(v); setStress(s); setConc(c);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const runCustom = async () => {
    const parsed: Record<string, number> = {};
    Object.entries(shocks).forEach(([k, v]) => { const n = Number(v); if (v !== '' && !isNaN(n)) parsed[k] = n / 100; });
    if (!Object.keys(parsed).length) return;
    const r = await fetch('/api/v1/risk/stress-test', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ shocks: parsed }),
    });
    setCustom(await r.json());
  };

  const available = varData?.available;
  const worstStress = stress?.scenarios?.length ? Math.max(...stress.scenarios.map((s: any) => Math.abs(s.total_pnl)), 1) : 1;

  return (
    <div id="var-stress" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><ShieldAlert className="w-3 h-3" /></span>
          <h2 className="section-title">Value at Risk & Stress</h2>
          {available && <span className="section-meta">{varData.observations} obs · {varData.book}</span>}
        </div>
        <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !varData && <div className="p-6 text-center text-sm text-text-secondary">Computing VaR…</div>}

      {varData && !available && (
        <div className="p-6 bg-surface-1 border border-border text-center text-sm text-text-secondary">
          {varData.reason || 'VaR unavailable — add positions first.'}
        </div>
      )}

      {available && (
        <div className="space-y-3">
          {/* VaR table */}
          <div className="border border-border bg-surface-1 overflow-x-auto">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 text-2xs text-text-tertiary uppercase tracking-wider">
              Value at Risk (potential loss)
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-2xs text-text-tertiary uppercase">
                  <th className="text-left py-2 px-3 font-medium">Method</th>
                  <th className="text-right py-2 px-3 font-medium">95% · 1d</th>
                  <th className="text-right py-2 px-3 font-medium">95% · 10d</th>
                  <th className="text-right py-2 px-3 font-medium">99% · 1d</th>
                  <th className="text-right py-2 px-3 font-medium">99% · 10d</th>
                </tr>
              </thead>
              <tbody>
                {(['historical', 'parametric', 'monte_carlo'] as const).map((m) => (
                  <tr key={m} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3 capitalize text-text-primary">{m.replace('_', ' ')}</td>
                    <td className="py-2 px-3 text-right font-mono text-red">{usd(varData.var['95'][m]['1d'])}</td>
                    <td className="py-2 px-3 text-right font-mono text-red">{usd(varData.var['95'][m]['10d'])}</td>
                    <td className="py-2 px-3 text-right font-mono text-red">{usd(varData.var['99'][m]['1d'])}</td>
                    <td className="py-2 px-3 text-right font-mono text-red">{usd(varData.var['99'][m]['10d'])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {varData.component_var_95_1d?.length > 0 && (
              <div className="px-3 py-2 border-t border-border-subtle text-2xs">
                <span className="text-text-tertiary uppercase tracking-wider">VaR contribution (95% 1d): </span>
                {varData.component_var_95_1d.map((c: any) => (
                  <span key={c.symbol} className="ml-2 font-mono">
                    {c.symbol} <span className={c.component_var >= 0 ? 'text-red' : 'text-green'}>{usd(c.component_var)}</span>
                    <span className="text-text-tertiary"> ({(c.pct_of_var * 100).toFixed(0)}%)</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Predefined stress scenarios */}
          {stress?.available && (
            <div className="p-3 bg-surface-1 border border-border space-y-2">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Historical Stress Scenarios (est. P&L)</div>
              {stress.scenarios.map((s: any) => {
                const w = (Math.abs(s.total_pnl) / worstStress) * 100;
                return (
                  <div key={s.id} className="flex items-center gap-2 text-xs">
                    <span className="w-52 shrink-0 text-text-secondary truncate">{s.label}</span>
                    <div className="flex-1 h-3 bg-surface-3 relative">
                      <div className={`absolute top-0 bottom-0 left-0 ${s.total_pnl < 0 ? 'bg-red' : 'bg-green'}`} style={{ width: `${w}%` }} />
                    </div>
                    <span className={`w-24 text-right font-mono ${s.total_pnl < 0 ? 'text-red' : 'text-green'}`}>{usd(s.total_pnl)}</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Custom scenario builder */}
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Custom Scenario — shock factors (% return)</div>
            <div className="flex flex-wrap items-end gap-2">
              {CUSTOM_FACTORS.map(([key, label]) => (
                <div key={key} className="w-24">
                  <label className="text-2xs text-text-tertiary">{label} %</label>
                  <input value={shocks[key] ?? ''} onChange={(e) => setShocks({ ...shocks, [key]: e.target.value })}
                    placeholder="-20" className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm font-mono text-text-primary" />
                </div>
              ))}
              <button onClick={runCustom} className="px-3 py-1 border border-bloomberg-border bg-bloomberg-muted text-bloomberg text-xs hover:bg-bloomberg/20">Run</button>
              {custom?.available && (
                <div className="text-sm font-mono ml-2">
                  Est. P&L: <span className={custom.total_pnl < 0 ? 'text-red' : 'text-green'}>{usd(custom.total_pnl)}</span>
                </div>
              )}
            </div>
          </div>

          {/* Concentration */}
          {conc?.available && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {[
                ['Largest Name', `${conc.largest_name} ${(conc.largest_weight * 100).toFixed(0)}%`],
                ['Top-5 Concentration', `${(conc.top5_concentration * 100).toFixed(0)}%`],
                ['HHI', conc.hhi.toFixed(2)],
                ['Limit Breaches', `${conc.breaches.length}`, conc.breaches.length ? 'text-red' : 'text-green'],
              ].map(([label, val, tone]) => (
                <div key={label as string} className="p-2 bg-surface-1 border border-border">
                  <div className="text-2xs text-text-tertiary uppercase tracking-wider">{label}</div>
                  <div className={`text-sm font-mono font-bold ${(tone as string) || 'text-text-primary'}`}>{val}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Model Portfolio — the Macro Model's sleeve (book "Macro Model"): holdings vs the model's
// targets, drift and the orders that would close it. Read-only; staging is in Macro Model.

import { useCallback, useEffect, useState } from 'react';
import { PieChart, RefreshCw } from 'lucide-react';

interface Holding {
  symbol: string;
  quantity: number;
  price: number | null;
  market_value: number | null;
  weight: number | null;
  target_weight: number;
}

interface Sleeve {
  holdings: Holding[];
  order_count: number;
  turnover: number;
  est_total_cost: number;
  sleeve_capital: number;
  sleeve_capital_basis: string;
  clipped_by_limits: Record<string, { model_weight: number; capped_weight: number }>;
  single_name_limit: number;
  portfolio: string;
  as_of: string;
  regime: string;
  regime_probability: number;
  expected_vol: number;
}

const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
const usd = (v: number | null | undefined) =>
  v == null ? '—' : Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : `$${Math.round(v).toLocaleString()}`;

export function ModelSleeveSection() {
  const [which, setWhich] = useState<'strategic' | 'tactical'>('strategic');
  const [data, setData] = useState<Sleeve | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const r = await fetch(`/api/v1/model/sleeve?portfolio=${which}`);
      const j = await r.json().catch(() => null);
      if (!r.ok || !j?.holdings) throw new Error((typeof j?.detail === 'string' && j.detail) || `HTTP ${r.status}`);
      setData(j);
    } catch (e: any) {
      setError(e?.message || 'Unavailable');
    } finally { setBusy(false); }
  }, [which]);

  useEffect(() => { load(); }, [load]);

  const rows = (data?.holdings ?? []).filter((h) => h.target_weight > 0 || h.quantity !== 0);
  const invested = rows.reduce((a, h) => a + (h.market_value ?? 0), 0);
  const targetCash = 1 - rows.reduce((a, h) => a + h.target_weight, 0);
  const maxDrift = rows.reduce((a, h) => Math.max(a, Math.abs((h.weight ?? 0) - h.target_weight)), 0);

  return (
    <div>
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><PieChart className="w-3 h-3" /></span>
          <h2 className="section-title">Model Portfolio</h2>
          {data && <span className="text-2xs text-text-tertiary font-mono">book “Macro Model” · data to {data.as_of}</span>}
        </div>
        <div className="flex items-center gap-1">
          {(['strategic', 'tactical'] as const).map((w) => (
            <button key={w} onClick={() => setWhich(w)}
              className={`px-2 py-0.5 text-2xs border capitalize ${which === w ? 'border-bloomberg text-bloomberg' : 'border-border text-text-tertiary hover:text-text-secondary'}`}>
              {w}
            </button>
          ))}
          <button onClick={load} disabled={busy} className="p-1 text-text-tertiary hover:text-bloomberg disabled:opacity-50" aria-label="Refresh" title="Refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${busy ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && <div className="p-3 text-xs text-amber border border-amber/30">Model portfolio unavailable: {error}</div>}
      {!data && !error && <div className="h-32 animate-pulse bg-surface-2" />}

      {data && (
        <div className="border border-border bg-surface-1 p-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3 text-xs">
            <div><div className="text-2xs text-text-tertiary">Sleeve capital</div><div className="font-mono text-text-primary">{usd(data.sleeve_capital)}</div></div>
            <div><div className="text-2xs text-text-tertiary">Invested</div><div className="font-mono text-text-primary">{usd(invested)} <span className="text-text-tertiary">({pct(invested / (data.sleeve_capital || 1), 0)})</span></div></div>
            <div><div className="text-2xs text-text-tertiary">Largest drift</div><div className={`font-mono ${maxDrift > 0.02 ? 'text-amber' : 'text-text-primary'}`}>{pct(maxDrift)}</div></div>
            <div><div className="text-2xs text-text-tertiary">To rebalance</div><div className="font-mono text-text-primary">{data.order_count} orders · {usd(data.turnover)}</div></div>
          </div>
          {invested === 0 && (
            <div className="mb-2 text-2xs text-text-tertiary">
              The model sleeve holds no positions yet. Targets below are what the {which} portfolio would hold; stage the orders from the Macro Model panel.
            </div>
          )}
          <table className="w-full text-2xs font-mono">
            <thead>
              <tr className="text-text-tertiary text-left">
                <th className="font-normal pb-1">ETF</th>
                <th className="font-normal pb-1 text-right">Held</th>
                <th className="font-normal pb-1 text-right">Value</th>
                <th className="font-normal pb-1 text-right">Weight</th>
                <th className="font-normal pb-1 text-right">Target</th>
                <th className="font-normal pb-1 text-right">Drift</th>
              </tr>
            </thead>
            <tbody>
              {rows.sort((a, b) => b.target_weight - a.target_weight).map((h) => {
                const drift = (h.weight ?? 0) - h.target_weight;
                return (
                  <tr key={h.symbol} className="border-t border-border-subtle">
                    <td className="py-0.5 text-text-primary">{h.symbol}</td>
                    <td className="text-right">{h.quantity.toLocaleString()}</td>
                    <td className="text-right">{usd(h.market_value)}</td>
                    <td className="text-right">{pct(h.weight)}</td>
                    <td className="text-right text-text-primary">{pct(h.target_weight)}</td>
                    <td className={`text-right ${Math.abs(drift) > 0.02 ? 'text-amber' : 'text-text-tertiary'}`}>{drift >= 0 ? '+' : ''}{pct(drift)}</td>
                  </tr>
                );
              })}
              <tr className="border-t border-border-subtle text-text-tertiary">
                <td className="py-0.5">Cash</td><td /><td /><td />
                <td className="text-right">{pct(targetCash)}</td><td />
              </tr>
            </tbody>
          </table>
          <div className="mt-2 text-[10px] text-text-tertiary">
            {data.portfolio} portfolio · model regime {data.regime} ({pct(data.regime_probability, 0)}) · expected volatility {pct(data.expected_vol)} ·
            sleeve capital = {data.sleeve_capital_basis}.
            {Object.keys(data.clipped_by_limits ?? {}).length > 0 &&
              ` Capped at the ${pct(data.single_name_limit, 0)} single-name limit: ${Object.keys(data.clipped_by_limits).join(', ')}.`}
          </div>
        </div>
      )}
    </div>
  );
}

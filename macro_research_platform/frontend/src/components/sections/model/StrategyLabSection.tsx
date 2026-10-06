// Strategy Lab — research-backed systematic models (cross-asset trend, sector momentum, low
// volatility, residual momentum, the auto book) backtested on the same footing, their
// correlations, an equal-risk combination, and each model's positions today.

import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, FlaskConical, Layers, Loader2, MinusCircle, RefreshCw, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { Donut } from '@/components/ui/Donut';
import { CorrelationHeatmap } from '@/components/ui/CorrelationHeatmap';
import { CATEGORICAL } from '@/lib/chartPalette';

const PRIMARY = ['trend', 'sector_momentum', 'low_vol', 'residual_momentum', 'auto_book'];
const SHORT: Record<string, string> = {
  trend: 'Trend', sector_momentum: 'Sectors', low_vol: 'Low vol', residual_momentum: 'Resid. mom.', auto_book: 'Auto book', combined: 'Combined',
};
const COLOR: Record<string, string> = Object.fromEntries([...PRIMARY, 'combined'].map((k, i) => [k, i === 5 ? '#e8edf3' : CATEGORICAL[i]]));
const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
const spct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const num = (v: number | null | undefined, d = 2) => (v == null ? '—' : v.toFixed(d));
const TONE: Record<string, { cls: string; Icon: typeof CheckCircle2 }> = {
  good: { cls: 'border-green/40 text-green', Icon: CheckCircle2 },
  bad: { cls: 'border-red/40 text-red', Icon: XCircle },
  neutral: { cls: 'border-border text-text-tertiary', Icon: MinusCircle },
};

export function StrategyLabSection() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [model, setModel] = useState('trend');

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/strategies');
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : `HTTP ${r.status}`);
      setData(j); setErr(null);
    } catch (e: any) { setErr(e?.message || 'Unavailable'); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!data?.status?.running && data?.available !== false) return;
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [data?.status?.running, data?.available, load]);
  const rerun = async () => {
    const r = await fetch('/api/v1/strategies/run', { method: 'POST' }).catch(() => null);
    if (r && !r.ok) { const j = await r.json().catch(() => ({})); setErr(typeof j?.detail === 'string' ? j.detail : `HTTP ${r.status}`); return; }
    setData((d: any) => ({ ...(d ?? {}), status: { running: true } }));
    setTimeout(load, 1500);
  };

  const sp = data?.same_period ?? {};
  const strat: any[] = data?.strategies ?? [];
  const corr = data?.correlation;
  const positions: any[] = data?.positions?.[model] ?? [];

  return (
    <div className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Layers className="w-3 h-3" /></span>
          <h2 className="section-title">Strategy Lab</h2>
          {data?.available && (
            <span className="text-2xs text-text-tertiary font-mono">
              5 research models + combination · {data.window?.start?.slice(0, 4)}–{data.window?.end?.slice(0, 4)} · {data.trials} trials counted · run {new Date(data.as_of).toLocaleDateString(undefined, { dateStyle: 'medium' })}
            </span>
          )}
        </div>
        <button onClick={rerun} disabled={data?.status?.running} title="Re-run every model (PM / quant)"
          className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs border border-border text-text-secondary hover:text-bloomberg disabled:opacity-60">
          {data?.status?.running ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          {data?.status?.running ? `${data.status.stage ?? 'Running'}…` : 'Re-run'}
        </button>
      </div>

      {err && <div className="p-2 mb-2 text-xs text-amber border border-amber/30">{err}</div>}
      {data && !data.available && (
        <div className="p-4 text-xs text-text-secondary border border-border-subtle flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" />{data.reason}</div>
      )}

      {data?.available && (
        <div className="space-y-2">
          {/* KPI strip: one tile per stream, same period */}
          <div className="grid gap-2 grid-cols-2 md:grid-cols-3 xl:grid-cols-6">
            {[...PRIMARY, 'combined'].map((k) => {
              const p = sp[k] ?? {};
              return (
                <div key={k} className={cn('px-3 py-2 bg-surface-1 border', k === 'combined' ? 'border-bloomberg/50' : 'border-border')}>
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-text-tertiary">
                    <span className="inline-block w-2 h-2 rounded-sm" style={{ background: COLOR[k] }} />{SHORT[k]}
                  </div>
                  <div className="flex items-baseline gap-2 mt-0.5">
                    <span className="font-mono text-sm text-text-primary">{num(p.sharpe)}</span><span className="text-[10px] text-text-tertiary">Sharpe</span>
                  </div>
                  <div className="text-[10px] font-mono text-text-secondary">{spct(p.cagr)} /yr · DD {pct(p.max_drawdown, 0)}</div>
                </div>
              );
            })}
          </div>

          {/* Findings */}
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {(data.findings ?? []).map((f: any) => {
              const t = TONE[f.tone] ?? TONE.neutral;
              return (
                <div key={f.title} className={cn('px-3 py-2 border bg-surface-1', t.cls)}>
                  <div className="flex items-center gap-1.5 text-2xs uppercase tracking-wide"><t.Icon className="w-3 h-3" />{f.title}</div>
                  <div className="text-xs text-text-secondary mt-1 leading-snug">{f.text}</div>
                </div>
              );
            })}
          </div>

          <div className="grid gap-2 xl:grid-cols-3">
            <div className="px-3 py-2 bg-surface-1 border border-border xl:col-span-2">
              <div className="text-2xs text-text-tertiary mb-1">Growth of 1 on a common window — after costs, log scale</div>
              <LineChart rows={data.curve ?? []} x="date" height={250} log baseline={1} fmt={(x) => `${x.toFixed(2)}×`}
                axisFmt={(x) => `${x >= 1 ? x.toFixed(x >= 10 ? 0 : 1) : x.toFixed(2)}×`}
                lines={[...PRIMARY, 'combined'].map((k) => ({ key: k, label: SHORT[k], color: COLOR[k] }))} />
            </div>
            <div className="space-y-2">
              <div className="px-3 py-2 bg-surface-1 border border-border">
                <Donut title="Combined book — risk-balanced weights today" size={118}
                  colorFor={(l) => COLOR[Object.keys(SHORT).find((k) => SHORT[k] === l) ?? ''] ?? '#5b6270'}
                  fmt={(x) => pct(x, 1)} centerValue={num(sp.combined?.sharpe)} centerLabel="Sharpe"
                  data={Object.entries(data.combined_weights ?? {}).map(([k, w]) => ({ label: SHORT[k] ?? k, value: Number(w) }))} />
              </div>
              {corr && (
                <div className="px-3 py-2 bg-surface-1 border border-border">
                  <div className="text-2xs text-text-tertiary mb-1">Daily-return correlation (lower = more diversifying)</div>
                  <CorrelationHeatmap labels={PRIMARY.map((k) => SHORT[k])} matrix={PRIMARY.map((a) => PRIMARY.map((b) => corr[a]?.[b] ?? null))} />
                </div>
              )}
            </div>
          </div>

          {/* Full-history table */}
          <div className="overflow-x-auto border border-border">
            <table className="w-full text-2xs font-mono">
              <thead className="bg-surface-1"><tr className="text-text-tertiary text-left">
                <th className="font-normal font-sans px-2 py-1">Model (own full history)</th><th className="font-normal text-right px-2">Since</th>
                <th className="font-normal text-right px-2">CAGR</th><th className="font-normal text-right px-2">Sharpe</th><th className="font-normal text-right px-2">Sortino</th>
                <th className="font-normal text-right px-2">Max DD</th><th className="font-normal text-right px-2">Calmar</th><th className="font-normal text-right px-2">Turnover/yr</th>
                <th className="font-normal text-right px-2" title="Deflated Sharpe ratio after every trial (≥ 95% significant)">DSR</th>
                <th className="font-normal font-sans px-2">Research</th>
              </tr></thead>
              <tbody>{strat.map((s) => (
                <tr key={s.key} className={cn('border-t border-border-subtle', s.key === 'combined' && 'bg-bloomberg/5')}>
                  <td className="px-2 py-1 font-sans text-text-primary">{s.label}</td>
                  <td className="text-right px-2 text-text-tertiary">{Object.keys(s.performance.years ?? {})[0]}</td>
                  <td className={cn('text-right px-2', (s.performance.cagr ?? 0) >= 0 ? 'text-green' : 'text-red')}>{spct(s.performance.cagr)}</td>
                  <td className="text-right px-2">{num(s.performance.sharpe)}</td><td className="text-right px-2">{num(s.performance.sortino)}</td>
                  <td className="text-right px-2 text-red">{pct(s.performance.max_drawdown, 0)}</td><td className="text-right px-2">{num(s.performance.calmar)}</td>
                  <td className="text-right px-2 text-text-secondary">{s.turnover_annual == null ? '—' : `${num(s.turnover_annual, 1)}×`}</td>
                  <td className={cn('text-right px-2', (s.deflated_sharpe ?? 0) >= 0.95 ? 'text-green' : (s.deflated_sharpe ?? 0) >= 0.5 ? 'text-amber' : 'text-red')}>{pct(s.deflated_sharpe, 0)}</td>
                  <td className="px-2 font-sans text-[10px] text-text-tertiary">{s.citation}</td>
                </tr>))}</tbody>
            </table>
          </div>

          {/* Positions today */}
          <div className="border border-border">
            <div className="flex flex-wrap items-center gap-2 px-2 py-1.5 bg-surface-1 border-b border-border">
              <span className="text-2xs text-text-tertiary">Positions at the latest rebalance</span>
              <div className="flex border border-border" role="tablist" aria-label="Model">
                {['trend', 'sector_momentum', 'low_vol', 'residual_momentum'].map((k) => (
                  <button key={k} role="tab" aria-selected={model === k} onClick={() => setModel(k)}
                    className={cn('px-2 py-0.5 text-2xs', model === k ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>{SHORT[k]}</button>
                ))}
              </div>
              {positions[0]?.as_of && <span className="text-[10px] text-text-tertiary ml-auto">as of {positions[0].as_of}</span>}
            </div>
            <div className="grid gap-2 lg:grid-cols-3 p-2">
              <div className="lg:col-span-2 overflow-x-auto">
                <table className="w-full text-2xs font-mono">
                  <thead><tr className="text-text-tertiary text-left">
                    <th className="font-normal font-sans px-2 py-1">Holding</th><th className="font-normal font-sans px-2">Side</th><th className="font-normal text-right px-2">Weight</th>
                  </tr></thead>
                  <tbody>{positions.map((p) => (
                    <tr key={p.symbol} className="border-t border-border-subtle">
                      <td className="px-2 py-1"><span className="text-text-primary">{p.symbol}</span> <span className="font-sans text-text-tertiary">{p.name ?? ''}{p.country ? ` · ${p.country}` : ''}</span></td>
                      <td className={cn('px-2 font-sans', p.side === 'Long' ? 'text-green' : 'text-red')}>{p.side}</td>
                      <td className="text-right px-2">{pct(Math.abs(p.weight), 1)}</td>
                    </tr>))}
                    {positions.length === 0 && <tr><td colSpan={3} className="px-2 py-3 text-center font-sans text-text-tertiary">In cash at the latest rebalance (filter off or no signal).</td></tr>}
                  </tbody>
                </table>
              </div>
              {positions.length > 1 && (
                <Donut title="Gross weight" fmt={(x) => pct(x, 1)}
                  data={positions.map((p) => ({ label: `${p.symbol}${p.side === 'Short' ? ' (short)' : ''}`, value: Math.abs(p.weight) }))} />
              )}
            </div>
          </div>

          <div className="text-[10px] text-text-tertiary leading-relaxed">
            Monthly rebalance, weights set at the month-end close, costs on turnover (ETFs 5 bp/side; stocks half the market-class round trip). Trend positions are inverse-volatility sized to a 10% book target;
            no financing or cash yield is modelled (understates trend and cash-heavy models). Stock models use developed and emerging markets only, in local currency (FX-hedged); the stock sample is
            today's large caps, which flatters stock-model returns relative to the ETF models. The combination is re-estimated monthly on the trailing year (equal risk contribution, Ledoit-Wolf covariance).
            <span className="inline-flex items-center gap-1 ml-1"><FlaskConical className="w-3 h-3" />Research, not advice — size new models small until live results confirm them.</span>
          </div>
        </div>
      )}
    </div>
  );
}

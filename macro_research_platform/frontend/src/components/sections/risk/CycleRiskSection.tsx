/**
 * Cycle & Systemic Risk — indicators from published research, each with its source.
 *
 *  - Near-term forward spread (Engstrom & Sharpe, 2019) + fitted recession probability
 *  - Excess bond premium (Gilchrist & Zakrajšek, 2012) + the Fed's recession probability
 *  - Financial turbulence (Kritzman & Li, 2010)
 *  - Absorption ratio (Kritzman, Li, Page & Rigobon, 2011)
 *  - Environmental balance of the book across growth/inflation environments
 *
 * Reads /api/v1/risk/cycle.
 */
import { useCallback, useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';

type Point = { date: string; value: number };

function Sparkline({ points, unit = '', zero = false }: { points: Point[]; unit?: string; zero?: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return null;
  const W = 220, H = 44, P = 2;
  const vals = points.map((p) => p.value);
  const lo = Math.min(...vals, zero ? 0 : Infinity), hi = Math.max(...vals, zero ? 0 : -Infinity);
  const x = (i: number) => P + (i / (points.length - 1)) * (W - 2 * P);
  const y = (v: number) => H - P - ((v - lo) / (hi - lo || 1)) * (H - 2 * P);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join('');
  const h = hover != null ? points[hover] : null;
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-11" preserveAspectRatio="none"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          setHover(Math.max(0, Math.min(points.length - 1, Math.round(((e.clientX - r.left) / r.width) * (points.length - 1)))));
        }}>
        {zero && lo < 0 && hi > 0 && (
          <line x1={P} x2={W - P} y1={y(0)} y2={y(0)} stroke="var(--border-strong)" strokeWidth={1} strokeDasharray="2 3" />
        )}
        <path d={d} fill="none" stroke="var(--bloomberg)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        {h && <circle cx={x(hover!)} cy={y(h.value)} r={2.5} fill="var(--bloomberg)" />}
      </svg>
      <div className="text-[10px] font-mono text-text-tertiary h-3">
        {h ? `${h.date} · ${h.value.toFixed(2)}${unit}` : `${points[0].date} → ${points[points.length - 1].date}`}
      </div>
    </div>
  );
}

function Card({ title, source, children }: { title: string; source: string; children: React.ReactNode }) {
  return (
    <div className="p-3 bg-surface-1 border border-border min-w-0 flex flex-col gap-1.5">
      <div className="text-2xs text-text-tertiary uppercase tracking-wider">{title}</div>
      {children}
      <div className="text-[10px] text-text-tertiary mt-auto pt-1 border-t border-border-subtle">{source}</div>
    </div>
  );
}

const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);

export function CycleRiskSection() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch('/api/v1/risk/cycle');
      const j = await r.json();
      if (!r.ok) throw new Error(j?.detail || `HTTP ${r.status}`);
      setData(j);
    } catch (e: any) { setError(e?.message || 'Failed to load'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const n = data?.near_term_forward_spread, e = data?.excess_bond_premium;
  const t = data?.turbulence, a = data?.absorption_ratio, env = data?.environmental_balance;

  return (
    <div id="cycle-risk" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Activity className="w-3 h-3" /></span>
          <h2 className="section-title">Cycle &amp; Systemic Risk</h2>
          <span className="text-2xs text-text-tertiary">published indicators</span>
        </div>
        <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Loading indicators…</div>}
      {error && !data && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {error}</div>}

      {data && (
        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2">
            <Card title="Near-term forward spread" source="Engstrom & Sharpe (2019) · Fed zero-coupon curve">
              {n?.available ? <>
                <div className="flex items-baseline gap-2">
                  <span className={`text-lg font-mono font-bold ${n.value_pp < 0 ? 'text-red' : 'text-text-primary'}`}>
                    {n.value_pp > 0 ? '+' : ''}{n.value_pp.toFixed(2)}pp
                  </span>
                  <span className="text-2xs text-text-tertiary">{n.as_of}</span>
                </div>
                <div className="text-xs text-text-secondary">{n.signal}</div>
                <div className="text-2xs text-text-tertiary">
                  12M recession probability (probit, {n.model?.training_months} months): <span className="text-text-primary font-mono">{pct(n.recession_probability_12m)}</span>
                </div>
                <Sparkline points={n.history} unit="pp" zero />
              </> : <div className="text-2xs text-text-tertiary">{n?.reason ?? 'Unavailable'}</div>}
            </Card>

            <Card title="Excess bond premium" source="Gilchrist & Zakrajšek (2012) · Federal Reserve">
              {e?.available ? <>
                <div className="flex items-baseline gap-2">
                  <span className={`text-lg font-mono font-bold ${e.ebp_pp > 0.5 ? 'text-red' : 'text-text-primary'}`}>
                    {e.ebp_pp > 0 ? '+' : ''}{e.ebp_pp.toFixed(2)}pp
                  </span>
                  <span className="text-2xs text-text-tertiary">{e.as_of} · {e.ebp_percentile}th pct</span>
                </div>
                <div className="text-xs text-text-secondary">{e.signal}</div>
                <div className="text-2xs text-text-tertiary">
                  Fed 12M recession probability: <span className="text-text-primary font-mono">{pct(e.fed_recession_probability_12m)}</span>
                  {e.ebp_change_12m_pp != null && <> · 12M change {e.ebp_change_12m_pp > 0 ? '+' : ''}{e.ebp_change_12m_pp.toFixed(2)}pp</>}
                </div>
                <Sparkline points={(e.history ?? []).map((h: any) => ({ date: h.date, value: h.ebp }))} unit="pp" zero />
              </> : <div className="text-2xs text-text-tertiary">{e?.reason ?? 'Unavailable'}</div>}
            </Card>

            <Card title="Financial turbulence" source="Kritzman & Li (2010) · 10 cross-asset ETFs">
              {t?.available ? <>
                <div className="flex items-baseline gap-2">
                  <span className={`text-lg font-mono font-bold ${t.turbulent ? 'text-red' : 'text-text-primary'}`}>{t.avg_20d.toFixed(1)}</span>
                  <span className="text-2xs text-text-tertiary">20-day avg · {t.percentile_20d_avg}th pct</span>
                </div>
                <div className="text-xs text-text-secondary">
                  {t.turbulent ? 'Turbulent regime' : 'Not turbulent'} · {t.turbulent_days_last_20} of 20 days above the 75th percentile ({t.threshold_75th})
                </div>
                <Sparkline points={t.history} />
              </> : <div className="text-2xs text-text-tertiary">{t?.reason ?? 'Unavailable'}</div>}
            </Card>

            <Card title="Absorption ratio" source="Kritzman, Li, Page & Rigobon (2011) · US sectors">
              {a?.available ? <>
                <div className="flex items-baseline gap-2">
                  <span className="text-lg font-mono font-bold text-text-primary">{a.value.toFixed(3)}</span>
                  <span className="text-2xs text-text-tertiary">{a.percentile}th pct · shift {a.standardized_shift ?? '—'}σ</span>
                </div>
                <div className={`text-xs ${a.signal.startsWith('Fragile') ? 'text-red' : 'text-text-secondary'}`}>{a.signal}</div>
                <div className="text-2xs text-text-tertiary">Variance share of the top {a.eigenvectors} of {a.assets.length} eigenvectors</div>
                <Sparkline points={a.history} />
              </> : <div className="text-2xs text-text-tertiary">{a?.reason ?? 'Unavailable'}</div>}
            </Card>
          </div>

          {env?.available && (
            <div className="p-3 bg-surface-1 border border-border">
              <div className="flex flex-wrap items-baseline gap-2 mb-2">
                <span className="text-2xs text-text-tertiary uppercase tracking-wider">Environmental balance</span>
                {env.book?.balance_score != null && (
                  <span className="text-xs font-mono text-text-primary">book balance score {env.book.balance_score.toFixed(2)} (1 = equal risk in each environment)</span>
                )}
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  {env.environments.map((name: string) => {
                    const share = env.book?.risk_by_environment?.[name];
                    return (
                      <div key={name} title={share != null ? `${name}: ${(share * 100).toFixed(1)}% of book risk (target 25%)` : name}>
                        <div className="flex justify-between text-2xs">
                          <span className="text-text-secondary">{name}</span>
                          <span className="font-mono text-text-primary">{share != null ? `${(share * 100).toFixed(1)}%` : '—'}</span>
                        </div>
                        <div className="relative h-1.5 bg-surface-3 mt-0.5">
                          <div className="h-1.5 bg-bloomberg" style={{ width: `${Math.min(100, (share ?? 0) * 100 * 2)}%` }} />
                          <div className="absolute top-[-2px] h-2.5 w-px bg-text-tertiary" style={{ left: '50%' }} title="25% target" />
                        </div>
                      </div>
                    );
                  })}
                  {!env.book && <div className="text-2xs text-text-tertiary">No positions — showing the balanced reference only.</div>}
                  <div className="text-[10px] text-text-tertiary">Bar scale 0–50%; the tick marks the 25% equal-risk target.</div>
                </div>
                <div>
                  <div className="text-2xs text-text-tertiary mb-1">Environment-balanced reference weights</div>
                  <table className="w-full text-2xs font-mono">
                    <thead><tr className="text-text-tertiary text-left">
                      <th className="font-normal pb-1">Asset class</th><th className="font-normal pb-1">Proxy</th>
                      <th className="font-normal pb-1 text-right">Vol</th><th className="font-normal pb-1 text-right">Weight</th>
                      <th className="font-normal pb-1 pl-2">Environments</th></tr></thead>
                    <tbody>
                      {Object.entries(env.balanced_weights as Record<string, number>).sort((x, y) => y[1] - x[1]).map(([ac, w]) => (
                        <tr key={ac} className="border-t border-border-subtle">
                          <td className="py-0.5 text-text-secondary font-sans">{ac}</td>
                          <td className="text-text-tertiary">{env.proxies[ac]}</td>
                          <td className="text-right text-text-tertiary">{pct(env.proxy_volatility[ac], 0)}</td>
                          <td className="text-right text-text-primary">{pct(w)}</td>
                          <td className="pl-2 text-text-tertiary font-sans">{(env.asset_environments[ac] ?? []).join(' · ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="text-[10px] text-text-tertiary mt-2">{env.method}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

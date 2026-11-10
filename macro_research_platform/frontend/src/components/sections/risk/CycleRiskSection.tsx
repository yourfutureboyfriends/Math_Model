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
import { useCallback, useEffect, useMemo, useState } from 'react';
import { EChart, alpha, color, useChartTheme } from '@/components/charts/EChart';
import { Activity, RefreshCw } from 'lucide-react';
import { pct } from '@/lib/format';
import { setHubMode } from '@/lib/hubMode';
import { setMlTab, setMlTask } from '@/components/ml/mlShared';

type Point = { date: string; value: number };

function Sparkline({ points, unit = '', zero = false }: { points: Point[]; unit?: string; zero?: boolean }) {
  const t = useChartTheme();
  const option = useMemo(() => {
    const accent = color('rgb(var(--c-bloomberg))', t.accent);
    return {
      animation: false, legend: { show: false }, toolbox: { show: false },
      grid: { left: 2, right: 2, top: 4, bottom: 2 },
      tooltip: { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.mutedText, type: 'dashed' } }, position: (pt: number[]) => [pt[0] + 8, 0],
        formatter: (ps: any[]) => `${points[ps[0].dataIndex].date} · <b>${points[ps[0].dataIndex].value.toFixed(2)}${unit}</b>` },
      xAxis: { type: 'category', data: points.map((p) => p.date), show: false, boundaryGap: false },
      yAxis: { type: 'value', show: false, scale: !zero, min: zero ? (v: any) => Math.min(0, v.min) : undefined, max: zero ? (v: any) => Math.max(0, v.max) : undefined },
      series: [{ type: 'line', data: points.map((p) => p.value), showSymbol: false, symbol: 'circle', symbolSize: 5, lineStyle: { color: accent, width: 1.5 }, itemStyle: { color: accent },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: alpha(accent, 0.2) }, { offset: 1, color: alpha(accent, 0) }] }, origin: 'start' },
        markLine: zero ? { symbol: 'none', silent: true, data: [{ yAxis: 0 }], lineStyle: { color: t.borderStrong, type: [2, 3] }, label: { show: false } } : undefined }],
    };
  }, [points, unit, zero, t]);
  if (points.length < 2) return null;
  return (
    <div>
      <EChart option={option} height={44} ariaLabel={`History ${points[0].date} to ${points[points.length - 1].date}`} />
      <div className="text-[10px] font-mono text-text-tertiary h-3">{points[0].date} → {points[points.length - 1].date}</div>
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


/** The headline recession model (term spread + credit ensemble) with its out-of-sample record, so the number on the
 *  desk comes with the evidence for trusting it — and where it has been wrong. Data: /api/recession. */
function RecessionRecord() {
  const [r, setR] = useState<any>(null);
  useEffect(() => { fetch('/api/recession').then((x) => (x.ok ? x.json() : null)).then(setR).catch(() => setR(null)); }, []);
  const ev = r?.evaluation;
  if (!r || r.probability == null) return null;
  const rows: [string, any, any][] = ev ? [
    ['Headline (ensemble, recalibrated)', ev.models?.ensemble_calibrated ?? ev.models?.ensemble, ev.since_2005?.ensemble_calibrated ?? ev.since_2005?.ensemble],
    ...(ev.models?.ensemble_calibrated ? [['Ensemble before recalibration', ev.models?.ensemble, ev.since_2005?.ensemble] as [string, any, any]] : []),
    ...(ev.robustness ? [['Fully real-time variant (Baa spread instead of EBP)', ev.robustness, ev.robustness.since_2005] as [string, any, any]] : []),
    ['10Y–3M spread only', ev.models?.term_spread_only, ev.since_2005?.term_spread_only],
    ['Base rate (always the average)', ev.models?.base_rate, null],
  ] : [];
  const skill = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(0)}%`);
  return (
    <div className="p-3 bg-surface-1 border border-border space-y-2" aria-label="Recession model record">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-2xs uppercase tracking-wider text-text-tertiary">Headline recession probability</span>
        <span className="text-lg font-mono font-bold text-text-primary">{pct(r.probability)}</span>
        <span className="text-2xs text-text-secondary">{r.model ?? 'model'}</span>
        <span className="text-2xs text-text-tertiary">· target: {r.target ?? '12 months'}</span>
        {r.rawProbability != null && r.rawProbability !== r.probability && <span className="text-2xs text-text-tertiary" title="The ensemble's reading before the calibration learned from its past forecasts">· raw {pct(r.rawProbability)}</span>}
      </div>
      {ev ? <>
        <div className="overflow-x-auto"><table className="w-full text-2xs">
          <thead><tr className="text-text-tertiary text-left">
            <th className="font-normal py-1">Out of sample {ev.from}–{ev.to} ({ev.forecasts} monthly forecasts, {ev.recession_months} recession-ahead)</th>
            <th className="font-normal text-right" title="How well the model ranks months that led into recession above months that did not; 0.5 is a coin flip">AUROC</th>
            <th className="font-normal text-right" title="Brier-score improvement over always forecasting the training base rate; negative = worse than the base rate">Skill vs base rate</th>
            <th className="font-normal text-right">Since 2005: AUROC</th><th className="font-normal text-right">skill</th></tr></thead>
          <tbody>{rows.map(([name, all, s05]) => <tr key={name} className="border-t border-border-subtle">
            <td className="py-1 text-text-secondary">{name}</td>
            <td className="text-right font-mono">{all?.auroc ?? '—'}</td>
            <td className={`text-right font-mono ${all?.brier_skill_vs_base_rate < 0 ? 'text-red' : ''}`}>{skill(all?.brier_skill_vs_base_rate)}</td>
            <td className="text-right font-mono">{s05?.auroc ?? '—'}</td>
            <td className={`text-right font-mono ${s05?.brier_skill_vs_base_rate < 0 ? 'text-red' : ''}`}>{skill(s05?.brier_skill_vs_base_rate)}</td>
          </tr>)}</tbody></table></div>
        {ev.calibration?.length > 0 && <div className="text-2xs text-text-tertiary">
          Calibration — when the headline read… (how often a recession followed, 95% range):{' '}
          {ev.calibration.map((c: any) => <span key={c.range} className="mr-3 font-mono whitespace-nowrap" title={`${c.forecasts} monthly forecasts averaging ${pct(c.mean_probability)}`}>
            {c.range}: {pct(c.recession_frequency)}{c.frequency_95 && <span className="opacity-70"> ({pct(c.frequency_95[0])}–{pct(c.frequency_95[1])})</span>}</span>)}
        </div>}
        <div className="text-2xs text-text-tertiary">{ev.method} The headline is recalibrated on the model's own past forecasts; readings of 70%+ have still been over-confident (the 2022–24 inverted curve brought no recession). Payrolls are as first published (ALFRED vintages); the EBP has no vintages, so the fully real-time variant, which swaps it for the never-revised Baa spread, is the lower bound.</div>
      </> : <div className="text-2xs text-text-tertiary">Out-of-sample record unavailable for this model.</div>}
    </div>
  );
}

const FEATURE_LABEL: Record<string, string> = {
  ts: '10Y–3M spread', ntfs: 'Forward spread', ebp: 'Credit premium (EBP)', pay6: 'Payroll growth',
  ts_d6: 'Spread change (6m)', ebp_d3: 'EBP change (3m)', spx6: 'S&P 500 (6m)',
};

/** The machine-learning challenger in shadow mode: its forecast and what drove it, its record against the headline
 *  by era, and why it is (not) eligible for promotion. Data: /api/v1/models/recession/challenger. */
function ChallengerPanel() {
  const [c, setC] = useState<any>(undefined);
  useEffect(() => { fetch('/api/v1/models/recession/challenger').then((x) => (x.ok ? x.json() : null)).then(setC).catch(() => setC(null)); }, []);
  if (c === undefined) return <div className="p-3 bg-surface-1 border border-border text-2xs text-text-tertiary">ML challenger: retraining for this month (about a minute after a restart)…</div>;
  if (!c) return null;
  if (!c.available) return <div className="p-3 bg-surface-1 border border-border text-2xs text-text-tertiary">ML challenger unavailable — {c.reason}</div>;
  const contrib = Object.entries(c.contributions ?? {}).sort((a: any, b: any) => Math.abs(b[1]) - Math.abs(a[1])) as [string, number][];
  const maxAbs = Math.max(0.001, ...contrib.map(([, v]) => Math.abs(v)));
  const eras = Object.entries(c.backtest?.by_era ?? {}) as [string, any][];
  return (
    <div className="p-3 bg-surface-1 border border-border space-y-2" aria-label="Machine-learning challenger">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-2xs uppercase tracking-wider text-text-tertiary">ML challenger · shadow mode</span>
        <span className="text-lg font-mono font-bold text-text-primary">{pct(c.probability)}</span>
        <span className="text-2xs text-text-secondary">vs headline {pct(c.headline_probability)}</span>
        <span className="text-2xs text-text-tertiary" title={c.method}>· {c.model}</span>
        <button className="ml-auto text-2xs underline text-bloomberg" onClick={() => { setMlTask('recession_12m'); setMlTab('visualizer'); setHubMode('ml'); }}>Open in ML →</button>
      </div>
      <div className={`text-2xs px-2 py-1 border ${c.promotion?.eligible ? 'border-green/40 text-green' : 'border-amber/40 text-amber'}`}>
        {c.promotion?.status}{c.promotion?.requires_human_approval ? ' · promotion always needs a person to approve it' : ''}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <div className="text-2xs text-text-tertiary mb-1">What moved today's forecast (raw, percentage points)</div>
          {contrib.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[120px_1fr_48px] items-center gap-2 text-2xs">
              <span className="text-text-secondary truncate">{FEATURE_LABEL[k] ?? k}</span>
              <div className="h-1.5 bg-surface-3 relative">
                <div className={`absolute inset-y-0 ${v >= 0 ? 'left-1/2 bg-red/70' : 'right-1/2 bg-green/70'}`} style={{ width: `${(Math.abs(v) / maxAbs) * 50}%` }} />
              </div>
              <span className="font-mono text-right">{v > 0 ? '+' : ''}{(v * 100).toFixed(1)}</span>
            </div>))}
        </div>
        <div>
          <div className="text-2xs text-text-tertiary mb-1">Walk-forward record (Brier; lower is better)</div>
          <table className="w-full text-2xs">
            <thead><tr className="text-text-tertiary text-left"><th className="font-normal">Period</th><th className="font-normal text-right">Headline</th>
              <th className="font-normal text-right">Challenger</th><th className="font-normal text-right">Half-and-half</th></tr></thead>
            <tbody>{eras.map(([name, e]) => <tr key={name} className="border-t border-border-subtle">
              <td className="py-0.5 text-text-secondary">{name}</td><td className="text-right font-mono">{e.headline?.brier}</td>
              <td className="text-right font-mono">{e.challenger?.brier}</td>
              <td className={`text-right font-mono ${e.blend_brier_gain < 0 ? 'text-red' : 'text-green'}`}>{e.blend?.brier}</td></tr>)}</tbody>
          </table>
          <div className="text-2xs text-text-tertiary mt-1">
            Chance the gain is luck: {c.backtest?.p_no_gain != null ? pct(c.backtest.p_no_gain) : '—'} (bar: {pct(0.05 / (c.backtest?.variants_tried || 1))}, allowing for {c.backtest?.variants_tried} variants tried) ·
            live record {c.live?.scored ?? 0} scored of {c.live?.logged ?? 0} logged months.
          </div>
        </div>
      </div>
    </div>
  );
}

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
          <RecessionRecord />
          <ChallengerPanel />
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
                  <span title="This spread on its own, fitted on all history (in-sample). The headline above combines it with the 10Y–3M spread, credit (EBP) and payrolls and is scored out of sample.">
                    Spread-only probit (in-sample): <span className="text-text-primary font-mono">{pct(n.recession_probability_12m)}</span> · input to the headline</span>
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
                  <span title="The Federal Reserve's own EBP-based model, published with the series. The headline above is this platform's ensemble.">
                    Fed's EBP-only model: <span className="text-text-primary font-mono">{pct(e.fed_recession_probability_12m)}</span></span>
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
                  <div className="workspace-table-scroll" tabIndex={0} role="group" aria-label="Scrollable data table"><table className="w-full text-2xs font-mono">
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
                  </table></div>
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

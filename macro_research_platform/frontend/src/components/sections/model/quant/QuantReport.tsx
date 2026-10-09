// Backtest report: verdict, headline numbers, curves, monthly table, robustness evidence,
// today's target positions and the rebalance log.
import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, MinusCircle, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { KpiStrip } from '@/components/ui/KpiStrip';
import { HeatGrid } from '@/components/ui/HeatGrid';
import { CATEGORICAL } from '@/lib/chartPalette';
import { GRADE, num, pct, Pills, spct, tone } from './shared';

const MONTHS = ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12'];
const MLABEL = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function Card({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('p-3 bg-surface-1 border border-border', className)}>
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1.5">{title}</div>
      {children}
    </div>
  );
}

function Row({ k, v, cls }: { k: string; v: React.ReactNode; cls?: string }) {
  return <div className="flex justify-between gap-3 text-2xs"><span className="text-text-secondary">{k}</span><span className={cn('font-mono text-text-primary', cls)}>{v}</span></div>;
}

export function QuantReport({ r }: { r: any }) {
  const [chart, setChart] = useState<'growth' | 'drawdown' | 'sharpe' | 'exposure'>('growth');
  const m = r.metrics, b = r.benchmark.metrics, rb = r.robustness ?? {}, vb = r.vs_benchmark ?? {}, tr = r.trading ?? {};
  const g = GRADE[r.verdict?.grade] ?? GRADE.mixed;
  const heat = useMemo(() => Object.entries(r.monthly.months as Record<string, Record<string, number>>).sort(([a], [b2]) => b2.localeCompare(a))
    .map(([y, mm]) => ({ label: y, sub: spct(r.monthly.years[y], 0), values: [...MONTHS.map((k) => (mm[k] != null ? mm[k] * 100 : null)), r.monthly.years[y] * 100] })), [r]);
  const sym = r.benchmark.symbol;

  return (
    <div className="space-y-3">
      {r.verdict && (
        <div className={cn('p-3 border bg-surface-1', g.cls)}>
          <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {r.verdict.grade === 'promising' ? <CheckCircle2 className="w-4 h-4" /> : r.verdict.grade === 'weak' ? <XCircle className="w-4 h-4" /> : <MinusCircle className="w-4 h-4" />}
            {r.verdict.label}
            <span className="text-2xs font-normal text-text-tertiary">{r.period.start} → {r.period.end} · {num(r.period.years, 1)} years</span>
          </div>
          <ul className="mt-1.5 space-y-0.5 text-2xs text-text-secondary list-disc pl-4">
            {r.verdict.reasons.map((x: string) => <li key={x}>{x}</li>)}
          </ul>
          {r.trials_note && <div className="mt-1 text-[10px] text-text-tertiary">{r.trials_note}</div>}
        </div>
      )}

      <KpiStrip items={[
        { label: 'Annual return', value: spct(m.cagr), sub: `${sym} ${spct(b.cagr)}`, tone: tone(m.cagr), accent: true },
        { label: 'Sharpe', value: num(m.sharpe), sub: `${sym} ${num(b.sharpe)}` },
        { label: 'Volatility', value: pct(m.vol), sub: `${sym} ${pct(b.vol)}` },
        { label: 'Max drawdown', value: pct(m.max_drawdown), sub: `${sym} ${pct(b.max_drawdown)}`, tone: 'down' },
        { label: 'Calmar', value: num(m.calmar), sub: `${m.longest_underwater_days} days longest underwater` },
        { label: 't-stat', value: num(m.t_stat, 1), sub: 'need > 3 for a new idea', tone: m.t_stat >= 3 ? 'up' : m.t_stat < 2 ? 'warn' : null },
      ]} />

      <div className="p-3 bg-surface-1 border border-border">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <Pills label="Chart" value={chart} onChange={setChart} options={[['growth', 'Growth of $1'], ['drawdown', 'Drawdown'], ['sharpe', 'Rolling 1-yr Sharpe'], ['exposure', 'Gross exposure']] as const} />
          <span className="text-[10px] text-text-tertiary">net of costs · trades at the next {r.spec.execution === 'next_close' ? 'close' : 'open'}</span>
        </div>
        {chart === 'growth' && <LineChart rows={r.curve} x="date" height={260} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
          lines={[{ key: 'strategy', label: r.spec.name, color: CATEGORICAL[0] }, { key: 'benchmark', label: sym, color: '#6b7280' }]} />}
        {chart === 'drawdown' && <LineChart rows={r.curve} x="date" height={220} baseline={0} fmt={(v) => pct(v, 0)}
          lines={[{ key: 'drawdown', label: 'Drawdown', color: '#e66767' }]} />}
        {chart === 'sharpe' && <LineChart rows={r.curve.filter((c: any) => c.rolling_sharpe != null)} x="date" height={220} baseline={0} fmt={(v) => v.toFixed(2)}
          lines={[{ key: 'rolling_sharpe', label: 'Rolling Sharpe', color: CATEGORICAL[2] }]} />}
        {chart === 'exposure' && <LineChart rows={r.curve} x="date" height={220} baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
          lines={[{ key: 'exposure', label: 'Gross exposure', color: CATEGORICAL[3] }]} />}
      </div>

      {r.warnings?.length > 0 && (
        <div className="p-2 border border-amber/40 bg-amber/5 space-y-1">
          {r.warnings.map((w: string) => <div key={w} className="flex gap-1.5 text-2xs text-amber"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}</div>)}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
        <Card title="Is it real? — significance">
          <Row k="Deflated Sharpe (prob. real)" v={pct(rb.deflated_sharpe?.dsr, 0)} cls={rb.deflated_sharpe?.dsr >= 0.95 ? 'text-green' : rb.deflated_sharpe?.dsr < 0.5 ? 'text-red' : 'text-amber'} />
          <Row k="Variants tried (counted)" v={rb.deflated_sharpe?.trials ?? '—'} />
          <Row k="Prob. Sharpe > 0 (PSR)" v={pct(rb.psr, 0)} />
          <Row k="t-stat of returns" v={num(m.t_stat, 2)} />
          <Row k="Skew / worst day" v={`${num(m.skew)} / ${pct(m.worst_day)}`} />
        </Card>
        <Card title="Does it last? — out of sample">
          {rb.is_oos?.split_date ? <>
            <Row k={`Sharpe before ${rb.is_oos.split_date}`} v={num(rb.is_oos.is_sharpe)} />
            <Row k="Sharpe after (out of sample)" v={num(rb.is_oos.oos_sharpe)} cls={rb.is_oos.oos_sharpe > 0 ? 'text-green' : 'text-red'} />
            <Row k="Decay" v={pct(rb.is_oos.decay, 0)} />
          </> : <div className="text-2xs text-text-tertiary">Too short to split.</div>}
          <Row k="Positive years" v={pct(r.monthly.pct_positive_years, 0)} />
          <Row k="Positive months" v={pct(r.monthly.pct_positive_months, 0)} />
        </Card>
        <Card title="How sure? — 90% bootstrap range">
          {rb.bootstrap?.sharpe_p05 != null ? <>
            <Row k="Sharpe" v={`${num(rb.bootstrap.sharpe_p05)} to ${num(rb.bootstrap.sharpe_p95)}`} />
            <Row k="Annual return" v={`${spct(rb.bootstrap.cagr_p05)} to ${spct(rb.bootstrap.cagr_p95)}`} />
            <Row k="Chance Sharpe < 0" v={pct(rb.bootstrap.prob_sharpe_negative, 1)} />
          </> : <div className="text-2xs text-text-tertiary">Too short.</div>}
          <div className="text-[10px] text-text-tertiary mt-1">Resampled 1-month blocks of the strategy's own returns.</div>
        </Card>
        <Card title="Can it be traded? — costs & delays">
          <table className="w-full text-2xs font-mono">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Costs</th><th className="text-right font-normal">Sharpe</th><th className="text-right font-normal">Return</th></tr></thead>
            <tbody>{(rb.cost_sensitivity ?? []).map((c: any) => (
              <tr key={c.multiple} className={c.multiple === 1 ? 'text-text-primary' : 'text-text-secondary'}>
                <td>{c.multiple}× ({c.bps} bp)</td><td className="text-right">{num(c.sharpe)}</td><td className="text-right">{spct(c.cagr)}</td>
              </tr>))}</tbody>
          </table>
          {rb.one_day_delay && <Row k="Trading one day later" v={`Sharpe ${num(rb.one_day_delay.sharpe)}`} />}
          <Row k="Turnover / year" v={`${num(tr.turnover_annual, 1)}×`} />
          <Row k="Cost drag / year" v={pct(tr.cost_drag_annual, 2)} />
        </Card>
        <Card title={`Versus ${sym}`}>
          <Row k="Beta" v={num(vb.beta)} />
          <Row k="Alpha / year" v={spct(vb.alpha_annual)} cls={vb.alpha_annual > 0 ? 'text-green' : 'text-red'} />
          <Row k="Correlation" v={num(vb.correlation)} />
          <Row k="Information ratio" v={num(vb.information_ratio)} />
          <Row k="Up / down capture" v={`${pct(vb.up_capture, 0)} / ${pct(vb.down_capture, 0)}`} />
          <Row k={`Avg month when ${sym} falls`} v={spct(vb.return_in_benchmark_down_months)} />
        </Card>
        <Card title="How it trades">
          <Row k="Average holdings" v={num(tr.avg_holdings, 1)} />
          <Row k="Gross / net exposure" v={`${num(tr.avg_gross_exposure)}× / ${num(tr.avg_net_exposure)}×`} />
          <Row k="Time invested" v={pct(tr.time_in_market, 0)} />
          {rb.without_vol_target && <Row k="Without the vol target" v={`Sharpe ${num(rb.without_vol_target.sharpe)} · DD ${pct(rb.without_vol_target.max_drawdown, 0)}`} />}
          <Row k="Gross return (before costs)" v={spct(r.metrics_gross?.cagr)} />
          <Row k="Best / worst month" v={`${spct(r.monthly.best_month)} / ${spct(r.monthly.worst_month)}`} />
        </Card>
      </div>

      <div className="p-3 bg-surface-1 border border-border">
        <HeatGrid title="Monthly returns (%) — net of costs" columns={[...MLABEL, 'Year']} rows={heat} labelWidth="4.5rem"
          fmt={(v) => v.toFixed(1)} scale={8} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        <Card title={`Target positions if rebalanced at the ${r.period.last_close} close`}>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-2xs font-mono">
              <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary">
                <th className="text-left font-normal">Asset</th><th className="text-right font-normal">Signal</th>
                {r.spec.filter && <th className="text-center font-normal">Filter</th>}
                <th className="text-right font-normal">Weight</th><th className="text-right font-normal">Vol</th></tr></thead>
              <tbody>{r.positions.map((p: any) => (
                <tr key={p.symbol} className={cn('border-t border-border-subtle', p.target_weight ? 'text-text-primary' : 'text-text-tertiary')}>
                  <td>{p.symbol}{p.fallback && <span className="text-text-tertiary"> (fallback)</span>}</td>
                  <td className="text-right">{p.signal == null ? '—' : num(p.signal, 3)}</td>
                  {r.spec.filter && <td className="text-center">{p.passes_filter == null ? '—' : p.passes_filter ? '✓' : '✗'}</td>}
                  <td className={cn('text-right', p.target_weight > 0 ? 'text-green' : p.target_weight < 0 ? 'text-red' : '')}>{p.target_weight ? spct(p.target_weight) : '—'}</td>
                  <td className="text-right">{pct(p.vol, 0)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </Card>
        <Card title="Recent rebalances">
          <div className="max-h-72 overflow-y-auto space-y-1">
            {r.rebalance_log.map((l: any) => (
              <div key={l.date} className="text-2xs border-b border-border-subtle pb-1">
                <span className="font-mono text-text-secondary">{l.date}</span>
                <span className="text-text-tertiary"> · {l.holdings} holdings · {num(l.gross)}× gross</span>
                {l.in.length > 0 && <div className="text-green">+ {l.in.join(', ')}</div>}
                {l.out.length > 0 && <div className="text-red">− {l.out.join(', ')}</div>}
              </div>
            ))}
          </div>
        </Card>
      </div>
      {r.missing_symbols?.length > 0 && <div className="text-[10px] text-text-tertiary">No data for: {r.missing_symbols.join(', ')}</div>}
    </div>
  );
}

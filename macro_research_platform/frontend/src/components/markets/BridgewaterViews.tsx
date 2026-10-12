// Bridgewater research frameworks — used in Markets mode (ENVR, AWP, DCYC, HGRL, WPWR) and embedded in the macro
// dashboard (Four Quadrants, Risk Parity, Debt Cycle, Pure Alpha, Regional Macro).
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, Loading, Panel, useJSON } from './shared';

const pc = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);
const sp = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(d)}%`);
const tone = (x: number | null | undefined) => (x == null ? 'text-text-tertiary' : x >= 0 ? 'text-green' : 'text-red');
const COLORS = ['rgb(var(--c-blue))', 'rgb(var(--c-amber))', 'rgb(var(--c-text-tertiary))', 'rgb(var(--c-green))', 'rgb(168 85 247)'];
const QCLS: Record<string, string> = { 'Reflation / overheating': 'text-amber', Goldilocks: 'text-green', Stagflation: 'text-red', 'Deflationary bust': 'text-blue' };

function Tile({ label, value, sub, cls }: { label: string; value: React.ReactNode; sub?: React.ReactNode; cls?: string }) {
  return (
    <div className="border border-border bg-surface-1 rounded-md px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className={cn('font-mono text-text-primary', cls)}>{value}</div>
      {sub != null && <div className="text-[10px] text-text-tertiary leading-tight">{sub}</div>}
    </div>
  );
}
function Frame<T>({ url, label, children }: { url: string; label: string; children: (d: T) => React.ReactNode }) {
  const { data, error, loading } = useJSON<T>(url, 3_600_000);
  if (loading && !data) return <Loading label={label} />;
  if (error && !data) return <ErrorBox msg={error} />;
  return data ? <>{children(data)}</> : null;
}
const Ref = ({ text }: { text: string }) => <div className="text-[10px] text-text-tertiary italic">Framework: {text}</div>;

// ── ENVR ────────────────────────────────────────────────────────────────────
export function EnvironmentsPanel({ compact = false }: { compact?: boolean }) {
  return (
    <Frame<any> url="/api/v1/mkt/bw/envr" label="Classifying 75 years of growth and inflation…">{(d) => {
      const max = Math.max(...d.table.flatMap((r: any) => d.assets.map((a: string) => Math.abs(r.assets[a]?.excess_annual ?? 0))));
      const cell = (v: number | null | undefined) => (v == null ? 'transparent' : v >= 0 ? `rgb(var(--c-green) / ${0.08 + 0.5 * v / max})` : `rgb(var(--c-red) / ${0.08 + 0.5 * -v / max})`);
      return (
        <div className="space-y-3">
          {!compact && <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Tile label="Environment now" value={<span className={QCLS[d.current.nickname]}>{d.current.nickname}</span>} sub={`${d.current.quadrant} · ${d.current.as_of}`} />
            <Tile label="Growth (industrial production y/y)" value={`${d.current.growth_yoy.toFixed(1)}%`} sub={`${d.current.growth_chg >= 0 ? '+' : ''}${d.current.growth_chg.toFixed(1)} pts vs 6 months ago`} />
            <Tile label="Inflation (CPI y/y)" value={`${d.current.inflation_yoy.toFixed(1)}%`} sub={`${d.current.inflation_chg >= 0 ? '+' : ''}${d.current.inflation_chg.toFixed(1)} pts vs 6 months ago`} />
            <Tile label="Sample" value={`${d.months} months`} sub={`since ${d.start}`} />
          </div>}
          <Panel title={`What each asset class has earned in each environment — annualised excess return over cash, ${d.start} to today`}>
            <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Environment</th><th className="text-right font-normal">Months</th>
                {d.assets.map((a: string) => <th key={a} className="text-right font-normal px-1.5">{a}</th>)}</tr></thead>
              <tbody>{d.table.map((r: any) => (
                <tr key={r.quadrant} className={cn('border-t border-border-subtle', r.nickname === d.current.nickname && 'outline outline-1 outline-bloomberg')}>
                  <td className="py-1 font-sans"><span className={cn('font-semibold', QCLS[r.nickname])}>{r.nickname}</span><div className="text-[10px] text-text-tertiary">{r.quadrant}</div></td>
                  <td className="text-right text-text-tertiary">{r.months}</td>
                  {d.assets.map((a: string) => { const x = r.assets[a]; return (
                    <td key={a} className="text-right px-1.5" style={{ background: cell(x?.excess_annual) }} title={x ? `${x.months} months · up ${pc(x.hit, 0)} of months · t = ${x.t?.toFixed(1)}` : 'not enough history'}>
                      {x ? sp(x.excess_annual) : '—'}</td>); })}</tr>))}
                <tr className="border-t-2 border-border"><td className="py-1 font-sans text-text-secondary">All months</td><td />
                  {d.assets.map((a: string) => <td key={a} className="text-right px-1.5 text-text-secondary">{sp(d.baseline[a])}</td>)}</tr>
              </tbody></table></div>
            <div className="text-[10px] text-text-tertiary mt-1">Hover a cell for the hit rate and t-statistic. The highlighted row is today’s environment.</div>
          </Panel>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <Panel title="Sensitivity — return when rising minus when falling (a year)">
              <table className="w-full text-2xs font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Asset</th><th className="text-right font-normal">To growth</th><th className="text-right font-normal">To inflation</th><th className="text-left font-normal pl-3">Best in</th></tr></thead>
                <tbody>{d.assets.map((a: string) => { const s = d.sensitivity[a]; return (
                  <tr key={a} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-primary">{a}</td>
                    <td className={cn('text-right', tone(s.growth))}>{sp(s.growth)}</td><td className={cn('text-right', tone(s.inflation))}>{sp(s.inflation)}</td>
                    <td className="pl-3 font-sans text-text-tertiary">{[s.growth > 0.01 ? 'rising growth' : s.growth < -0.01 ? 'falling growth' : null, s.inflation > 0.01 ? 'rising inflation' : s.inflation < -0.01 ? 'falling inflation' : null].filter(Boolean).join(', ') || '—'}</td></tr>); })}</tbody></table>
              <div className="text-[10px] text-text-tertiary mt-1">This is the core of All Weather: each asset is a bet on growth and inflation. Combine assets with opposite biases and the portfolio stops depending on the economy.</div>
            </Panel>
            <Panel title="The last 20 years of environments">
              <LineChart rows={d.history} x="date" height={200} fmt={(v) => `${v.toFixed(1)}%`} baseline={0}
                lines={[{ key: 'growth_yoy', label: 'Growth (IP y/y)', color: COLORS[0] }, { key: 'inflation_yoy', label: 'Inflation (CPI y/y)', color: COLORS[1] }]} />
              <div className="flex flex-wrap gap-1 mt-1 text-[10px]">{d.spells.slice(-8).map((s: any) => <span key={s.start} className="border border-border-subtle rounded-sm px-1"><span className="text-text-tertiary">{s.start}</span> <span className={QCLS[s.q]}>{s.q}</span></span>)}</div>
            </Panel>
          </div>
          <div className="text-[10px] text-text-tertiary">{d.method}</div>
          <Ref text={d.reference} />
        </div>);
    }}</Frame>
  );
}

// ── AWP ─────────────────────────────────────────────────────────────────────
export function AllWeatherPanel() {
  const [tv, setTv] = useState(0.10);
  return (
    <Frame<any> url={`/api/v1/mkt/bw/awp?target_vol=${tv}`} label="Building and backtesting All Weather…">{(d) => (
      <div className="space-y-3">
        <div className="flex items-center gap-1 text-[11px]"><span className="text-text-tertiary">Target volatility</span>
          {[0.06, 0.08, 0.10, 0.12].map((v) => <button key={v} onClick={() => setTv(v)} className={cn('px-2 py-0.5 border rounded-sm', tv === v ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{v * 100}%</button>)}
          <span className="ml-2 text-text-tertiary">Unlevered mix runs at {pc(d.vol_unlevered)} vol → leverage now {d.leverage_now?.toFixed(2)}×</span></div>
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-3">
          <Panel title="Today’s All Weather weights">
            <table className="w-full text-2xs font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Asset</th><th className="text-right font-normal">Weight</th><th className="text-right font-normal">Risk share</th><th className="text-left font-normal pl-2">Environments</th></tr></thead>
              <tbody>{[...d.weights].sort((a: any, b: any) => b.weight - a.weight).map((w: any) => (
                <tr key={w.symbol} className="border-t border-border-subtle"><td className="py-0.5 font-sans"><span className="font-mono text-text-primary">{w.symbol}</span> <span className="text-text-tertiary">{w.name}</span></td>
                  <td className="text-right">{pc(w.weight)}</td><td className="text-right text-text-secondary">{pc(w.risk_share)}</td><td className="pl-2 font-sans text-[10px] text-text-tertiary">{w.environments.join(' · ')}</td></tr>))}</tbody></table>
            <div className="grid grid-cols-2 gap-1.5 mt-2">{Object.entries<number>(d.environment_risk).map(([k, v]) => <Tile key={k} label={k} value={pc(v, 0)} sub="share of risk" />)}</div>
          </Panel>
          <Panel title={`Backtest since ${d.start} (rebased to 100)`}>
            <LineChart rows={d.curves} x="date" height={260} log fmt={(v) => v.toFixed(0)} lines={Object.keys(d.labels).map((k, i) => ({ key: k, label: d.labels[k], color: COLORS[i % COLORS.length] }))} />
          </Panel>
        </div>
        <Panel title="Results — and the point of All Weather: similar returns whatever the environment">
          <table className="w-full text-2xs font-mono tabular-nums"><thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Portfolio</th><th className="text-right font-normal">CAGR</th><th className="text-right font-normal">Vol</th><th className="text-right font-normal">Sharpe</th><th className="text-right font-normal">Max DD</th><th className="text-right font-normal">Worst year</th>
            {d.by_quadrant.map((q: any) => <th key={q.quadrant} className={cn('text-right font-normal', QCLS[q.quadrant])}>{q.quadrant}</th>)}</tr></thead>
            <tbody>{d.performance.map((p: any) => (
              <tr key={p.key} className={cn('border-t border-border-subtle', p.key === 'aw_lev' && 'font-semibold')}><td className="py-1 font-sans text-text-primary">{p.label}</td>
                <td className={cn('text-right', tone(p.cagr))}>{sp(p.cagr)}</td><td className="text-right">{pc(p.vol)}</td><td className="text-right">{p.sharpe?.toFixed(2)}</td>
                <td className="text-right text-red">{pc(p.max_drawdown)}</td><td className="text-right">{sp(p.worst_year)} <span className="text-text-tertiary">{p.worst_year_label}</span></td>
                {d.by_quadrant.map((q: any) => <td key={q.quadrant} className={cn('text-right', tone(q[p.key]))}>{sp(q[p.key])}</td>)}</tr>))}</tbody></table>
          <div className="text-[10px] text-text-tertiary mt-1">Environment columns: annualised return in months of each environment. A balanced portfolio shows a narrower spread across them than stocks or 60/40. {d.method}</div>
        </Panel>
        <Ref text={d.reference} />
      </div>)}</Frame>
  );
}

// ── DCYC ────────────────────────────────────────────────────────────────────
const PHASE_CLS: Record<string, string> = { 'Bubble / top': 'text-red', 'Late upswing': 'text-amber', 'Deleveraging': 'text-blue', 'Early / recovery': 'text-green', 'Mid-cycle': 'text-text-secondary' };
export function DebtCyclesPanel({ compact = false }: { compact?: boolean }) {
  const [sort, setSort] = useState<'total' | 'credit_gap' | 'dsr_vs_avg'>('total');
  return (
    <Frame<any> url="/api/v1/mkt/bw/dcyc" label="Loading BIS credit data for ~40 economies…">{(d) => {
      const u = d.us;
      const rows = [...d.countries].sort((a: any, b: any) => (b[sort] ?? -1e9) - (a[sort] ?? -1e9));
      return (
        <div className="space-y-3">
          {u?.available && <Panel title={`US monetary-policy stage: ${u.stage}`}>
            <div className="text-2xs text-text-secondary mb-2">{u.explanation} {u.debt_dynamics ? `${u.debt_dynamics}.` : ''}</div>
            <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
              <Tile label="Fed funds" value={`${u.fed_funds.toFixed(2)}%`} sub="MP1 lever" /><Tile label="Fed balance sheet" value={sp(u.fed_balance_sheet_yoy)} sub="y/y — MP2 (QE) lever" />
              <Tile label="Federal deficit" value={`${u.deficit_pct_gdp.toFixed(1)}%`} sub="of GDP — MP3 needs big deficits" /><Tile label="Federal debt" value={`${u.federal_debt_pct_gdp.toFixed(0)}%`} sub="of GDP" />
              <Tile label="Interest / receipts" value={pc(u.interest_share_of_receipts, 0)} sub="share of tax revenue spent on interest" cls={(u.interest_share_of_receipts ?? 0) > 0.25 ? 'text-amber' : ''} />
              <Tile label="10y yield − nominal growth" value={u.r_minus_g != null ? `${u.r_minus_g >= 0 ? '+' : ''}${u.r_minus_g.toFixed(1)} pts` : '—'} cls={tone(u.r_minus_g != null ? -u.r_minus_g : null)} sub={`nominal GDP ${u.nominal_gdp_growth?.toFixed(1)}%`} />
              <Tile label="Stage" value={u.stage} sub="MP1 rates → MP2 QE → MP3 fiscal + monetary" />
            </div>
          </Panel>}
          <Panel title={`Debt cycles — ${d.countries.length} economies (BIS)`} right={<div className="flex gap-1 text-[11px]">{([['total', 'Total debt'], ['credit_gap', 'Credit gap'], ['dsr_vs_avg', 'Debt service']] as const).map(([k, l]) => (
            <button key={k} onClick={() => setSort(k)} className={cn('px-2 py-0.5 border rounded-sm', sort === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>))}</div>}>
            <div className={cn('overflow-auto', compact ? 'max-h-80' : 'max-h-[560px]')}><table className="w-full text-2xs font-mono tabular-nums">
              <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Economy</th><th className="text-right font-normal">Total</th><th className="text-right font-normal">Private</th><th className="text-right font-normal">Govt</th>
                <th className="text-right font-normal" title="Private credit/GDP vs its long-run trend; above +10 has preceded most banking crises">Credit gap</th><th className="text-right font-normal">Debt service</th><th className="text-right font-normal">vs avg</th><th className="text-right font-normal">Policy rate</th>
                <th className="text-left font-normal pl-2">Short-term cycle</th><th className="text-left font-normal">Long-term cycle</th></tr></thead>
              <tbody>{rows.map((r: any) => (
                <tr key={r.code} className="border-t border-border-subtle" title={`${r.why}. ${r.long_term_why}. Data ${r.as_of}.`}>
                  <td className="py-0.5 font-sans text-text-primary">{r.country}</td><td className="text-right">{r.total?.toFixed(0) ?? '—'}%</td><td className="text-right text-text-secondary">{r.private_debt?.toFixed(0)}%</td><td className="text-right text-text-secondary">{r.government?.toFixed(0) ?? '—'}%</td>
                  <td className={cn('text-right', r.credit_gap > 10 ? 'text-red font-semibold' : r.credit_gap > 4 ? 'text-amber' : '')}>{r.credit_gap != null ? `${r.credit_gap >= 0 ? '+' : ''}${r.credit_gap.toFixed(1)}` : '—'}</td>
                  <td className="text-right">{r.dsr != null ? `${r.dsr.toFixed(1)}%` : '—'}</td><td className={cn('text-right', (r.dsr_vs_avg ?? 0) > 1 ? 'text-amber' : '')}>{r.dsr_vs_avg != null ? `${r.dsr_vs_avg >= 0 ? '+' : ''}${r.dsr_vs_avg.toFixed(1)}` : '—'}</td>
                  <td className="text-right">{r.policy_rate != null ? `${r.policy_rate.toFixed(2)}%` : '—'}</td>
                  <td className={cn('pl-2 font-sans', PHASE_CLS[r.phase])}>{r.phase}</td><td className={cn('font-sans', r.long_term === 'Late' ? 'text-red' : r.long_term === 'Mature' ? 'text-amber' : 'text-text-secondary')}>{r.long_term}</td></tr>))}</tbody></table></div>
            <div className="text-[10px] text-text-tertiary mt-1">Debt as % of GDP. Hover a row for the reasoning. {d.method}</div>
          </Panel>
          {!compact && <Panel title="Total debt (private + government), % of GDP">
            <LineChart rows={d.history} x="date" height={220} fmt={(v) => `${v.toFixed(0)}%`}
              lines={[['US', 'United States'], ['CN', 'China'], ['JP', 'Japan'], ['XM', 'Euro area'], ['GB', 'United Kingdom']].map(([k, l], i) => ({ key: k, label: l, color: COLORS[i % COLORS.length] }))} />
          </Panel>}
          <Ref text={d.reference} />
        </div>);
    }}</Frame>
  );
}

// ── HGRL ────────────────────────────────────────────────────────────────────
export function HolyGrailPanel({ defaultSymbols = 'SPY,EFA,EEM,TLT,IEF,TIP,LQD,HYG,GLD,DBC' }: { defaultSymbols?: string }) {
  const [draft, setDraft] = useState(defaultSymbols);
  const [syms, setSyms] = useState(defaultSymbols);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 text-[11px]"><input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && setSyms(draft)}
        className="flex-1 bg-surface-1 border border-border px-2 py-1 font-mono" /><button onClick={() => setSyms(draft)} className="px-3 py-1 bg-bloomberg text-text-inverse">Analyse</button></div>
      <Frame<any> url={`/api/v1/mkt/bw/hgrl?symbols=${encodeURIComponent(syms.replace(/\s+/g, ''))}`} label="Measuring how many independent bets these are…">{(d) => (
        <div className="space-y-3">
          {d.effective_bets != null && <>
            <div className={cn('px-3 py-2 border rounded-md text-xs', d.effective_bets >= 0.6 * d.n ? 'border-green/50 bg-green/5 text-green' : 'border-amber/50 bg-amber/5 text-amber')}>{d.verdict}</div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              <Tile label="Holdings" value={d.n} /><Tile label="Independent bets" value={d.effective_bets.toFixed(1)} sub={`entropy measure ${d.effective_bets_entropy.toFixed(1)}`} />
              <Tile label="Average correlation" value={d.average_correlation.toFixed(2)} /><Tile label="Risk cut by mixing" value={pc(d.risk_reduction, 0)} sub="risk-balanced mix vs average holding" />
              <Tile label="Portfolio vol" value={pc(d.portfolio_vol)} sub={`average holding ${pc(d.average_vol)}`} />
            </div>
          </>}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <Panel title="The Holy Grail curve — risk vs number of streams, by correlation">
              <LineChart rows={d.curve.map((r: any) => ({ date: String(r.n), ...Object.fromEntries(Object.entries(r).filter(([k]) => k !== 'n').map(([k, v]) => [k, (v as number) * 100])) }))} x="date" height={230} controls={false} fmt={(v) => `${v.toFixed(0)}%`}
                lines={[['rho0', 'ρ = 0'], ['rho10', 'ρ = 0.1'], ['rho20', 'ρ = 0.2'], ['rho40', 'ρ = 0.4'], ['rho60', 'ρ = 0.6']].map(([k, l], i) => ({ key: k, label: l, color: COLORS[i % COLORS.length] }))} />
              <div className="text-[10px] text-text-tertiary mt-1">x = number of return streams, y = portfolio risk as % of one stream’s. {d.note}</div>
            </Panel>
            {d.most_correlated && <Panel title="Pairs that are really the same bet / genuine diversifiers">
              <table className="w-full text-2xs font-mono"><tbody>
                {d.most_correlated.map((p: any) => <tr key={p.a + p.b} className="border-t border-border-subtle first:border-0"><td className="py-0.5">{p.a} – {p.b}</td><td className="text-right text-red">{p.rho.toFixed(2)}</td></tr>)}
                <tr><td colSpan={2} className="pt-2 text-[10px] text-text-tertiary font-sans">Least correlated</td></tr>
                {d.least_correlated.map((p: any) => <tr key={p.a + p.b + 'l'} className="border-t border-border-subtle"><td className="py-0.5">{p.a} – {p.b}</td><td className="text-right text-green">{p.rho.toFixed(2)}</td></tr>)}
              </tbody></table>
            </Panel>}
          </div>
          <Ref text={d.reference} />
        </div>)}</Frame>
    </div>
  );
}

// ── WPWR ────────────────────────────────────────────────────────────────────
export function WorldOrderPanel() {
  return (
    <Frame<any> url="/api/v1/mkt/bw/wpwr" label="Scoring the major powers (World Bank, IMF)…">{(d) => (
      <div className="space-y-3">
        <Panel title="Power index — the measures Dalio uses to track rising and declining empires">
          <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Country</th><th className="text-left font-normal pl-2">Index</th>
              {d.measures.map((m: string) => <th key={m} className="text-right font-normal px-1" title={d.detail[m]?.label}>{m}</th>)}</tr></thead>
            <tbody>{d.countries.map((c: any) => (
              <tr key={c.code} className="border-t border-border-subtle"><td className="py-1 font-sans text-text-primary">{c.country}</td>
                <td className="pl-2"><div className="flex items-center gap-1.5"><div className="w-24 h-1.5 bg-surface-3 rounded-full overflow-hidden"><div className="h-full bg-bloomberg" style={{ width: `${(c.index ?? 0) * 100}%` }} /></div><span>{c.index?.toFixed(2) ?? '—'}</span></div></td>
                {d.measures.map((m: string) => { const v = c.scores[m]; return <td key={m} className="text-right px-1" style={{ background: v != null ? `rgb(var(--c-blue) / ${0.05 + 0.45 * v})` : undefined }}>{v != null ? v.toFixed(2) : '—'}</td>; })}</tr>))}</tbody></table></div>
          <div className="text-[10px] text-text-tertiary mt-1">1.00 = the leader on that measure. {d.note}</div>
        </Panel>
        <div className="text-[10px] text-text-tertiary">Source: {d.source}.</div>
        <Ref text={d.reference} />
      </div>)}</Frame>
  );
}

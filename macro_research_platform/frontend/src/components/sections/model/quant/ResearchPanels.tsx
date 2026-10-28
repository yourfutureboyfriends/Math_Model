/**
 * Research-grade result panels for a Code Lab run (api/quant/codelab.py evaluate()):
 * validation (look-ahead check, probability of backtest overfitting), capacity, P&L attribution, ex-ante risk with
 * stress tests, and signal information coefficients (Alphalens-style).
 */
import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { BarList } from '@/components/ui/BarList';
import { LineChart } from '@/components/ui/LineChart';
import { CATEGORICAL } from '@/lib/chartPalette';
import { num, pct, spct, usd } from './shared';

const Card = ({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) => (
  <div className="p-3 bg-surface-1 border border-border text-[11px] space-y-2">
    <div className="flex flex-wrap items-baseline gap-2">
      <div className="text-xs font-semibold text-text-primary">{title}</div>
      {sub && <div className="text-[10px] text-text-tertiary">{sub}</div>}
    </div>
    {children}
  </div>
);

const bars = (o: Record<string, number> | undefined, n = 8) =>
  Object.entries(o ?? {}).slice(0, n).map(([label, value]) => ({ label, value }));

export function Validation({ v }: { v: any }) {
  const c = v?.causality, p = v?.pbo;
  if (!c && !p) return null;
  const first = c?.cuts?.find((x: any) => x.first)?.first;
  return (
    <Card title="Validation" sub="does any decision use the future · how likely is the parameter choice overfit">
      {c && (
        <div className={cn('flex items-start gap-1.5', c.passed === false ? 'text-red' : c.passed ? 'text-green' : 'text-text-tertiary')}>
          {c.passed === false ? <ShieldAlert className="w-3.5 h-3.5 shrink-0" /> : <ShieldCheck className="w-3.5 h-3.5 shrink-0" />}
          <div>
            <b>{c.passed === false ? 'Look-ahead detected.' : c.passed ? 'No look-ahead found.' : 'Look-ahead not checked.'}</b> {c.note}
            {first && <> First difference: {first.date} {first.ticker} — full history {first.full_history ?? 'blank'}, data to date {first.data_to_date ?? 'blank'}.</>}
            {c.cuts?.length > 0 && <span className="text-text-tertiary"> Checked as of {c.cuts.map((x: any) => x.as_of).join(', ')}.</span>}
          </div>
        </div>)}
      {p && (p.pbo == null ? <div className="text-text-tertiary">{p.note}</div> : (
        <div className={cn(p.pbo >= 0.5 ? 'text-red' : p.pbo >= 0.2 ? 'text-amber' : 'text-text-secondary')}>
          <b>Probability of backtest overfitting {pct(p.pbo, 0)}</b> ({p.candidates} parameter sets, {p.splits} half/half splits of the history).
          The in-sample winner's median out-of-sample percentile: {pct(p.median_oos_percentile, 0)}; it lost money out of sample in {pct(p.prob_oos_loss, 0)} of splits. {p.note}.
          <span className="text-text-tertiary"> (Bailey, Borwein, López de Prado & Zhu 2017.)</span>
        </div>))}
      {v?.cpcv && (
        <div className="text-text-secondary">
          <b>Combinatorial purged cross-validation:</b> {v.cpcv.paths} out-of-sample paths ({v.cpcv.groups} blocks, {v.cpcv.test_groups} held out at a time, {v.cpcv.embargo_days}-day embargo) —
          Sharpe {num(v.cpcv.sharpe_mean)} on average (min {num(v.cpcv.sharpe_min)}, max {num(v.cpcv.sharpe_max)}), positive on {pct(v.cpcv.share_positive, 0)} of paths.
          <span className="text-text-tertiary"> (López de Prado 2018.)</span>
        </div>)}
    </Card>
  );
}

export function Capacity({ c }: { c: any }) {
  if (!c?.levels?.length) return null;
  return (
    <Card title="Capacity" sub="the same decisions at larger account sizes — impact, volume limits and lots grow with size">
      <table className="w-full font-mono">
        <thead className="text-text-tertiary"><tr>{['Capital', 'CAGR', 'Sharpe', 'Trading costs /yr', 'of which impact', 'Volume-capped days', 'Lot shortfall'].map((h) => <th key={h} className="text-right first:text-left font-normal px-1.5">{h}</th>)}</tr></thead>
        <tbody>{c.levels.map((x: any) => (
          <tr key={x.capital} className="border-t border-border-subtle">
            <td className="px-1.5">{usd(x.capital)}</td><td className="text-right px-1.5">{spct(x.cagr)}</td><td className="text-right px-1.5">{num(x.sharpe)}</td>
            <td className="text-right px-1.5">{pct(x.trading_costs, 2)}</td><td className="text-right px-1.5">{pct(x.impact, 2)}</td>
            <td className="text-right px-1.5">{x.capped_days}</td><td className="text-right px-1.5">{pct(x.lot_residual, 3)}</td></tr>))}</tbody>
      </table>
      <div className="text-text-tertiary">{c.capacity ? `Capacity ≈ ${usd(c.capacity)}${c.capacity === c.levels[c.levels.length - 1].capital ? ' or more' : ''}` : 'Below the smallest tested size'} (account currency). {c.note}</div>
    </Card>
  );
}

export function Attribution({ a }: { a: any }) {
  if (!a?.per_year) return null;
  const y = a.per_year;
  const rows = [['Securities', y.securities], ['  of which currency moves', y.of_which_currency], ['Trading costs', y.trading_costs], ['Stock borrow', y.borrow],
    ['Cash interest (net)', y.cash_interest], ['Dividend withholding', y.dividend_tax], ['FX hedge', y.fx_hedge]].filter(([, v]) => v);
  return (
    <Card title="Where the return came from" sub="per year, fraction of NAV">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <BarList title="Sources" diverging fmt={(v) => spct(v, 2)} data={rows.map(([label, value]) => ({ label: label as string, value: value as number }))} />
        <BarList title="Best contributors" diverging fmt={(v) => spct(v, 2)}
          data={[...(a.top ?? []).slice(0, 6), ...(a.bottom ?? []).slice(0, 4)].map((x: any) => ({ label: x.ticker, value: x.per_year, sub: x.currency_part ? `currency ${spct(x.currency_part, 2)}` : x.name ?? undefined }))} />
        <BarList title="By sector" diverging fmt={(v) => spct(v, 2)} data={bars(a.by?.sector)} />
      </div>
      {(Object.keys(a.by?.country ?? {}).length > 1 || Object.keys(a.by?.currency ?? {}).length > 1) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <BarList title="By listing country" diverging fmt={(v) => spct(v, 2)} data={bars(a.by?.country)} />
          <BarList title="By currency" diverging fmt={(v) => spct(v, 2)} data={bars(a.by?.currency)} />
        </div>)}
      {a.brinson && (
        <div>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Brinson–Fachler vs the equal-weight universe, by {a.brinson.by} (per year, before costs)</div>
          <table className="w-full font-mono">
            <thead className="text-text-tertiary"><tr>{['', 'Allocation', 'Selection', 'Interaction', 'Total'].map((h) => <th key={h} className="text-right first:text-left font-normal px-1.5">{h}</th>)}</tr></thead>
            <tbody>
              {a.brinson.rows.map((r: any) => (
                <tr key={r.group} className="border-t border-border-subtle"><td className="font-sans px-1.5">{r.group}</td>
                  <td className="text-right px-1.5">{spct(r.allocation, 2)}</td><td className="text-right px-1.5">{spct(r.selection, 2)}</td>
                  <td className="text-right px-1.5">{spct(r.interaction, 2)}</td><td className="text-right px-1.5">{spct(r.allocation + r.selection + r.interaction, 2)}</td></tr>))}
              <tr className="border-t border-border font-semibold"><td className="font-sans px-1.5">Total (+ cash {spct(a.brinson.total.cash, 2)})</td>
                <td className="text-right px-1.5">{spct(a.brinson.total.allocation, 2)}</td><td className="text-right px-1.5">{spct(a.brinson.total.selection, 2)}</td>
                <td className="text-right px-1.5">{spct(a.brinson.total.interaction, 2)}</td>
                <td className="text-right px-1.5">{spct(a.brinson.total.allocation + a.brinson.total.selection + a.brinson.total.interaction + a.brinson.total.cash, 2)}</td></tr>
            </tbody>
          </table>
          <div className="text-text-tertiary mt-1">{a.brinson.note}</div>
        </div>)}
      <div className="text-text-tertiary">{a.note}</div>
    </Card>
  );
}

export function Risk({ r }: { r: any }) {
  if (!r) return null;
  return (
    <Card title="Risk of today's book (ex-ante)" sub={`${r.lookback_days} days of returns, shrinkage covariance`}>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2 font-mono">
        {[['Volatility', pct(r.vol)], ['Beta', num(r.beta)], ['VaR 99% 1d', pct(r.var99_1d, 2)], ['ES 99% 1d', pct(r.es99_1d, 2)],
          ['Hist. VaR 99%', pct(r.hist_var99_1d, 2)], ['Hist. ES 99%', pct(r.hist_es99_1d, 2)], ['Gross / net', `${num(r.gross)} / ${num(r.net)}`],
          ['Effective positions', num(r.effective_positions, 1)]].map(([l, v]) => (
          <div key={l}><div className="text-[10px] font-sans text-text-tertiary">{l}</div><div>{v}</div></div>))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <BarList title="Largest risk contributors (share of risk)" diverging fmt={(v) => pct(v, 1)}
          data={(r.positions ?? []).slice(0, 10).map((p: any) => ({ label: p.ticker, value: p.risk_share, sub: `weight ${pct(p.weight, 1)}` }))} />
        <BarList title="Risk by sector" diverging fmt={(v) => pct(v, 1)} data={bars(r.risk_by?.sector)} />
        <div>
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Today's book through past crises</div>
          <table className="w-full font-mono"><tbody>{(r.stress ?? []).map((s: any) => (
            <tr key={s.scenario} className="border-t border-border-subtle">
              <td className="font-sans pr-2">{s.scenario}</td>
              <td className={cn('text-right', s.book < 0 && 'text-red')}>{spct(s.book)}</td>
              <td className="text-right text-text-tertiary">{s.benchmark != null ? `bench ${spct(s.benchmark)}` : ''}</td>
              <td className="text-right text-text-tertiary" title="share of the book with its own history in the episode">{pct(s.coverage, 0)}</td></tr>))}</tbody></table>
        </div>
      </div>
      {r.factor_model && !r.factor_model.error && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Factor model ({r.factor_model.estimation_universe} names, {r.factor_model.days} days)</div>
            <div className="font-mono">vol {pct(r.factor_model.vol)} · factor {pct(r.factor_model.factor_share, 0)} / specific {pct(r.factor_model.specific_share, 0)} of variance</div>
            <BarList title="Style exposures (z-score of the book)" diverging fmt={(v) => num(v)} data={bars(r.factor_model.style_exposures, 6)} />
          </div>
          <BarList title="Share of risk by factor" diverging fmt={(v) => pct(v, 1)} data={bars(r.factor_model.risk_share, 8)} />
        </div>)}
      {r.factor_model?.note && <div className="text-text-tertiary">{r.factor_model.note}</div>}
      <div className="text-text-tertiary">{r.note}</div>
    </Card>
  );
}

export function Signal({ s }: { s: any }) {
  if (!s) return null;
  if (s.error) return <Card title="Signal research"><div className="text-amber">signal() failed: {s.error}</div></Card>;
  const q = s.quantiles;
  return (
    <Card title="Signal research (information coefficient)" sub={`your signal() scores · ${num(s.coverage, 0)} names scored a day on average`}>
      <table className="w-full font-mono">
        <thead className="text-text-tertiary"><tr>{['Horizon', 'Mean IC', 'IC IR (annual)', 't-stat', 'IC > 0', 'Days'].map((h) => <th key={h} className="text-right first:text-left font-normal px-1.5">{h}</th>)}</tr></thead>
        <tbody>{(s.ic ?? []).map((x: any) => (
          <tr key={x.horizon} className="border-t border-border-subtle">
            <td className="px-1.5">{x.horizon}d</td><td className={cn('text-right px-1.5', x.mean_ic > 0 ? 'text-green' : 'text-red')}>{num(x.mean_ic, 4)}</td>
            <td className="text-right px-1.5">{num(x.ic_ir)}</td><td className={cn('text-right px-1.5', Math.abs(x.t_stat ?? 0) >= 2 && 'font-semibold')}>{num(x.t_stat)}</td>
            <td className="text-right px-1.5">{pct(x.positive, 0)}</td><td className="text-right px-1.5">{x.days}</td></tr>))}</tbody>
      </table>
      {(s.ic_sector_neutral ?? []).length > 0 && (
        <div>
          <div className="text-text-tertiary mb-0.5">Sector-neutral IC — stock selection within {s.sectors} sectors (a signal that only picks sectors scores ~0 here)</div>
          <table className="w-full font-mono">
            <tbody>{s.ic_sector_neutral.map((x: any) => {
              const raw = (s.ic ?? []).find((r: any) => r.horizon === x.horizon);
              return (
                <tr key={x.horizon} className="border-t border-border-subtle">
                  <td className="px-1.5">{x.horizon}d</td>
                  <td className={cn('text-right px-1.5', x.mean_ic > 0 ? 'text-green' : 'text-red')}>{num(x.mean_ic, 4)}</td>
                  <td className="text-right px-1.5 text-text-tertiary">{raw ? `${raw.mean_ic ? Math.round((x.mean_ic / raw.mean_ic) * 100) : 0}% of the raw IC` : ''}</td>
                  <td className={cn('text-right px-1.5', Math.abs(x.t_stat ?? 0) >= 2 && 'font-semibold')}>t {num(x.t_stat)}</td>
                  <td className="text-right px-1.5">{pct(x.positive, 0)} &gt; 0</td></tr>);
            })}</tbody>
          </table>
        </div>)}
      {q && (
        <BarList title={`Quintile excess return, ${q.horizon}-day horizon (annualised, before costs) — Q1 lowest score`} diverging fmt={(v) => spct(v, 1)}
          data={q.annualised_excess.map((v: number, i: number) => ({ label: `Q${i + 1}`, value: v }))} />)}
      <div className="text-text-tertiary">
        {q && <>Top minus bottom {spct(q.spread, 1)} a year{q.monotonic ? ', monotonic across quintiles' : ''}. </>}
        {s.top_quantile_turnover != null && <>Top quintile turnover {pct(s.top_quantile_turnover, 1)} a day. </>}
        Rank autocorrelation 1/5/21 days: {['1', '5', '21'].map((k) => num(s.rank_autocorrelation?.[k])).join(' / ')}. {s.note} |t| ≥ 2 is the usual bar; with many signals tried, ask for more (Harvey, Liu & Zhu 2016: t ≥ 3).
      </div>
    </Card>
  );
}

/** Order log and round-trip trade statistics, with a CSV download of the orders. */
export function Trades({ t }: { t: any }) {
  if (!t) return null;
  const s = t.stats ?? {};
  const csv = () => {
    const head = ['date', 'ticker', 'side', 'quantity', 'price', 'value', 'costs', 'type'];
    const rows = [head.join(','), ...(t.orders ?? []).map((o: any) => head.map((k) => o[k]).join(','))];
    const url = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = 'orders.csv'; a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <Card title="Trades and orders" sub={`${s.orders ?? 0} orders · ${s.closed_trades ?? 0} closed round trips · ${s.open_trades ?? 0} open`}>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 font-mono">
        {[['Win rate', pct(s.win_rate, 1)], ['Profit/loss ratio', num(s.profit_loss_ratio)], ['Profit factor', num(s.profit_factor)],
          ['Expectancy / trade', usd(s.expectancy)], ['Avg win', usd(s.avg_win)], ['Avg loss', usd(s.avg_loss)],
          ['Largest win', usd(s.largest_win)], ['Largest loss', usd(s.largest_loss)], ['Avg days held', num(s.avg_days_held, 1)],
          ['Long / short', `${s.long_trades ?? 0} / ${s.short_trades ?? 0}`], ['Total costs', usd(s.total_costs)], ['Orders', String(s.orders ?? 0)]].map(([l, v]) => (
          <div key={l}><div className="text-[10px] font-sans text-text-tertiary">{l}</div><div>{v}</div></div>))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <div className="overflow-auto max-h-72">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Latest closed trades</div>
          <table className="w-full font-mono"><thead className="text-text-tertiary"><tr>{['Ticker', 'Side', 'Entry', 'Exit', 'Days', 'P&L', 'Return'].map((h) => <th key={h} className="text-left font-normal px-1">{h}</th>)}</tr></thead>
            <tbody>{(t.closed ?? []).slice().reverse().slice(0, 100).map((x: any, i: number) => (
              <tr key={i} className="border-t border-border-subtle"><td className="px-1">{x.ticker}</td><td className="px-1">{x.side}</td><td className="px-1">{x.entry}</td>
                <td className="px-1">{x.exit}</td><td className="px-1">{x.days}</td>
                <td className={cn('px-1', x.pnl < 0 ? 'text-red' : 'text-green')}>{usd(x.pnl)}</td><td className="px-1">{spct(x.return, 1)}</td></tr>))}</tbody></table>
        </div>
        <div className="overflow-auto max-h-72">
          <div className="flex items-baseline gap-2 mb-1">
            <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Order log (latest {(t.orders ?? []).length} of {t.orders_total})</div>
            <button onClick={csv} className="ml-auto text-[10px] underline text-text-tertiary">download CSV</button>
          </div>
          <table className="w-full font-mono"><thead className="text-text-tertiary"><tr>{['Date', 'Ticker', 'Side', 'Qty', 'Price', 'Value', 'Costs', 'Type'].map((h) => <th key={h} className="text-left font-normal px-1">{h}</th>)}</tr></thead>
            <tbody>{(t.orders ?? []).slice().reverse().slice(0, 150).map((o: any, i: number) => (
              <tr key={i} className="border-t border-border-subtle"><td className="px-1">{o.date}</td><td className="px-1">{o.ticker}</td>
                <td className={cn('px-1', o.side === 'buy' ? 'text-green' : 'text-red')}>{o.side}</td><td className="px-1">{num(o.quantity, 2)}</td>
                <td className="px-1">{num(o.price, 4)}</td><td className="px-1">{usd(o.value)}</td><td className="px-1">{usd(o.costs, 2)}</td><td className="px-1">{o.type}</td></tr>))}</tbody></table>
        </div>
      </div>
      {t.open?.length > 0 && <div className="text-text-secondary">Open: {t.open.slice(0, 12).map((x: any) => `${x.ticker} (${x.side}, since ${x.entry}, ${usd(x.unrealised)})`).join(' · ')}{t.open.length > 12 ? ` · +${t.open.length - 12} more` : ''}</div>}
      <div className="text-text-tertiary">{t.note}</div>
    </Card>
  );
}

/** Custom charts from plot() / ctx.plot(). */
export function Charts({ c }: { c: any }) {
  const charts = Object.entries(c ?? {}) as [string, Record<string, [string, number][]>][];
  if (!charts.length) return <div className="text-2xs text-text-tertiary">No custom charts — call plot("Chart", "series", values) in your code (or ctx.plot in on_bar).</div>;
  return (
    <div className="space-y-3">
      {charts.map(([name, series]) => {
        const keys = Object.keys(series);
        const map = new Map<string, any>();
        keys.forEach((k, i) => series[k].forEach(([d, v]) => { const row = map.get(d) ?? { date: d }; row[`s${i}`] = v; map.set(d, row); }));
        const rows = Array.from(map.values()).sort((a, b) => (a.date < b.date ? -1 : 1));
        return (
          <Card key={name} title={name}>
            <LineChart rows={rows} x="date" height={200} fmt={(v) => num(v, 3)} lines={keys.map((k, i) => ({ key: `s${i}`, label: k, color: CATEGORICAL[i % CATEGORICAL.length] }))} />
          </Card>);
      })}
    </div>
  );
}

/** Parameter sensitivity: every PARAMS combination's out-of-sample result, as a heatmap for two parameters. */
export function Heatmap({ opt }: { opt: any }) {
  const grid = opt?.grid as any[] | undefined;
  if (!grid || grid.length < 2) return null;
  const keys = Object.keys(grid[0].params ?? {});
  const metric = (g: any) => g.sharpe as number | null;
  const vals = grid.map(metric).filter((v): v is number => v != null && Number.isFinite(v));
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const color = (v: number | null) => {
    if (v == null) return 'transparent';
    const x = hi > lo ? (v - lo) / (hi - lo) : 0.5;
    return `rgba(57, 135, 229, ${0.15 + 0.75 * x})`;
  };
  const chosen = JSON.stringify(opt.in_sample_best?.params ?? {});
  if (keys.length === 2) {
    const xs = Array.from(new Set(grid.map((g) => JSON.stringify(g.params[keys[0]])))).map((x) => JSON.parse(x));
    const ys = Array.from(new Set(grid.map((g) => JSON.stringify(g.params[keys[1]])))).map((x) => JSON.parse(x));
    const at = (a: any, b: any) => grid.find((g) => g.params[keys[0]] === a && g.params[keys[1]] === b);
    return (
      <Card title="Parameter sensitivity" sub={`Sharpe of each ${keys[0]} × ${keys[1]} combination over the out-of-sample years · outlined = best in hindsight`}>
        <table className="font-mono">
          <thead><tr><th className="px-2 text-left font-normal text-text-tertiary">{keys[1]} ↓ / {keys[0]} →</th>{xs.map((x) => <th key={String(x)} className="px-2 font-normal text-text-tertiary">{String(x)}</th>)}</tr></thead>
          <tbody>{ys.map((y) => (
            <tr key={String(y)}><td className="px-2 text-text-tertiary">{String(y)}</td>
              {xs.map((x) => { const g = at(x, y); const v = g ? metric(g) : null; return (
                <td key={String(x)} className={cn('px-3 py-1 text-center', g && JSON.stringify(g.params) === chosen && 'outline outline-2 outline-bloomberg')} style={{ background: color(v) }}
                  title={g ? `CAGR ${spct(g.cagr)} · max DD ${pct(g.max_drawdown)}` : ''}>{num(v)}</td>); })}</tr>))}</tbody>
        </table>
        <div className="text-text-tertiary">A good parameter sits in a broad region of similar results; an isolated bright cell is usually overfit.</div>
      </Card>);
  }
  return (
    <Card title="Parameter sensitivity" sub="Sharpe of each PARAMS combination over the out-of-sample years">
      <BarList title="" fmt={(v) => num(v)} data={grid.map((g) => ({ label: Object.entries(g.params).map(([k, v]) => `${k}=${v}`).join(', '), value: metric(g) ?? 0 }))} />
    </Card>);
}

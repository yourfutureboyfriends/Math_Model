// ALPHA — Stock Signal Lab (backend: api/quant/alphalab.py): which stock-level signals predicted S&P 500 returns,
// an out-of-sample composite of the ones that work, and today's ranked long and short ideas with sizes.
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, Loading, Panel, useJSON } from './shared';
import { Chip, pct, sign, Source, Tile } from './StandardViews';
import { useStickyState } from '@/lib/stickyState';

const SHORT: Record<string, string> = { momentum: 'Mom', reversal: 'Rev', low_vol: 'LowVol', value: 'Value', profitability: 'Prof', investment: 'Inv',
  earnings: 'EPS surp', high52: '52w hi', resid_mom: 'ResMom', industry_mom: 'IndMom' };
const COMP_SHORT: Record<string, string> = { fixed: 'Pre-reg.', adaptive: 'Adaptive' };
const num = (v: number | null | undefined, d = 3) => (v == null ? '—' : v.toFixed(d));

function IcCell({ v }: { v: number | null | undefined }) {
  if (v == null) return <span className="text-text-tertiary">—</span>;
  const a = Math.min(1, Math.abs(v) / 0.06);
  return <span className="inline-block w-full text-center rounded-sm font-mono" style={{ background: v >= 0 ? `rgba(63,211,162,${0.12 + a * 0.5})` : `rgba(217,83,74,${0.12 + a * 0.5})` }}>{(v * 100).toFixed(1)}</span>;
}

export function AlphaLabView({ onOpen }: { onOpen: (s: string) => void }) {
  const [refresh, setRefresh] = useState(false);
  const [universe, setUniverse] = useStickyState('alpha.universe', 'sp500');
  const { data: d, error, loading } = useJSON<any>(`/api/v1/quant/alphalab?universe=${universe}${refresh ? '&refresh=true' : ''}`, 20_000);
  const uniChips = (
    <div className="flex flex-wrap gap-1">
      {Object.entries<string>(d?.universes ?? { sp500: 'S&P 500', sp1000: 'S&P MidCap 400 + SmallCap 600' }).map(([k, l]) =>
        <Chip key={k} on={universe === k} onClick={() => { setUniverse(k); setRefresh(false); }}>{l}</Chip>)}
    </div>
  );
  const [side, setSide] = useState<'long' | 'short'>('long');
  if (loading && !d) return <Loading label="Loading the Stock Signal Lab…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  if (d.status) {
    return (
      <div className="space-y-2">
        {uniChips}
        {d.status === 'computing' ? <Loading label={`Building — scoring seven signals over the S&P 500 since 2014 (${d.started_seconds_ago ?? 0}s so far)…`} /> : <ErrorBox msg={d.error ?? 'The build failed.'} />}
        <p className="text-[11px] text-text-tertiary">{d.note}</p>
      </div>
    );
  }
  const c = d.composite;
  const comps: any[] = d.composites ?? [c];
  const weights = d.current_weights ?? {};
  const book = side === 'long' ? d.longs : d.shorts;
  const years: number[] = Array.from(new Set(d.signals.flatMap((s: any) => Object.keys(s.ic_by_year).map(Number)))).sort() as number[];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-text-tertiary">
        {uniChips}
        <span>{d.universe} stocks ({d.universe_source ?? 'point-in-time S&P 500 members'}) · monthly since {d.start} · signals as of {d.as_of}{d.age_hours != null ? ` · built ${d.age_hours}h ago` : ''}</span>
        <button onClick={() => setRefresh(true)} disabled={d.refreshing} className="text-bloomberg hover:underline disabled:opacity-50">{d.refreshing ? 'Rebuilding in the background…' : 'Rebuild now'}</button>
      </div>
      {d.edge && <div className={cn('alpha-verdict', d.edge.level)} role="status"><b>{d.edge.level === 'significant' ? 'Edge found' : d.edge.level === 'weak' ? 'Weak evidence' : 'No reliable edge'}</b> {d.edge.text}
        <span className="block text-[10px] opacity-80 mt-0.5">Ideas below come from the {c.name.toLowerCase()} — the composite with the stronger out-of-sample record.</span></div>}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label="Composite rank IC" value={c.ic_mean != null ? (c.ic_mean * 100).toFixed(2) : '—'} sub={`t = ${num(c.ic_t, 1)} · positive in ${c.ic_hit_rate != null ? Math.round(c.ic_hit_rate * 100) : '—'}% of months`} />
        <Tile label="Top fifth vs index (net)" value={pct(c.excess_vs_universe_ann, 1)} cls={sign(c.excess_vs_universe_ann)} sub="a year, after 10bp per turnover" />
        <Tile label="Top fifth return" value={pct(c.top_quintile_net.ann_return, 1)} sub={`Sharpe ${num(c.top_quintile_net.sharpe, 2)} · max DD ${pct(c.top_quintile_net.max_drawdown, 0)}`} />
        <Tile label="Long-short (top − bottom fifth)" value={pct(c.long_short.ann_return, 1)} cls={sign(c.long_short.ann_return)} sub={`Sharpe ${num(c.long_short.sharpe, 2)} · before borrow`} />
        <Tile label="Turnover" value={c.turnover_monthly != null ? `${Math.round(c.turnover_monthly * 100)}%` : '—'} sub="of the top fifth replaced a month" />
      </div>

      <Panel title="Which signals predicted next month's return" right={<span className="text-[11px] text-text-tertiary">rank IC ×100 · |t| ≥ 2 is significant</span>}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Signal</th><th className="text-right font-normal px-1">IC</th><th className="text-right font-normal px-1">t</th>
            <th className="text-right font-normal px-1">Hit</th><th className="text-right font-normal px-1">Last 3y</th><th className="text-right font-normal px-1">IC 3m</th><th className="text-right font-normal px-1">IC 12m</th>
            <th className="text-right font-normal px-1">L/S a yr</th><th className="text-right font-normal px-1">L/S Sharpe</th><th className="text-right font-normal px-1">Top 5th vs index</th>
            <th className="text-right font-normal px-1">Turnover</th><th className="text-right font-normal px-1">Adaptive wt now</th></tr></thead>
          <tbody>{[...d.signals, ...comps].map((s: any) => (
            <tr key={s.id} className={cn(COMP_SHORT[s.id] && 'font-semibold border-t border-border')}>
              <td className="py-1 font-sans text-text-primary whitespace-nowrap">{s.name}</td>
              <td className={cn('text-right px-1', sign(s.ic_mean))}>{s.ic_mean != null ? (s.ic_mean * 100).toFixed(2) : '—'}</td>
              <td className={cn('text-right px-1', s.ic_t != null && Math.abs(s.ic_t) >= 2 ? (s.ic_t > 0 ? 'text-green' : 'text-red') : 'text-text-secondary')}>{num(s.ic_t, 1)}</td>
              <td className="text-right px-1">{s.ic_hit_rate != null ? `${Math.round(s.ic_hit_rate * 100)}%` : '—'}</td>
              <td className={cn('text-right px-1', sign(s.ic_last_36m))}>{s.ic_last_36m != null ? (s.ic_last_36m * 100).toFixed(2) : '—'}</td>
              <td className="text-right px-1 text-text-secondary">{s.decay?.['3m'] != null ? (s.decay['3m'] * 100).toFixed(1) : '—'}</td>
              <td className="text-right px-1 text-text-secondary">{s.decay?.['12m'] != null ? (s.decay['12m'] * 100).toFixed(1) : '—'}</td>
              <td className={cn('text-right px-1', sign(s.long_short.ann_return))}>{pct(s.long_short.ann_return, 1)}</td>
              <td className="text-right px-1">{num(s.long_short.sharpe, 2)}</td>
              <td className={cn('text-right px-1', sign(s.excess_vs_universe_ann))}>{pct(s.excess_vs_universe_ann, 1)}</td>
              <td className="text-right px-1 text-text-secondary">{s.turnover_monthly != null ? `${Math.round(s.turnover_monthly * 100)}%` : '—'}</td>
              <td className="text-right px-1">{COMP_SHORT[s.id] ? '' : weights[s.id] != null ? `${Math.round(weights[s.id] * 100)}%` : '—'}</td>
            </tr>))}</tbody>
        </table></div>
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title="Growth of $1 — composite top fifth vs the index, equal weight (net of costs)">
          <div className="mkt-chart-surface"><LineChart rows={d.curve} x="month" height={250} controls={false} fmt={(v) => `$${v.toFixed(2)}`} log
            lines={[{ key: 'composite_top_quintile', label: 'Composite top fifth', color: 'rgb(var(--c-bloomberg))' },
              { key: 'universe_equal_weight', label: 'S&P 500 members, equal weight', color: 'rgb(var(--c-text-tertiary))' },
              { key: 'composite_long_short', label: 'Long-short', color: 'rgb(var(--c-blue))' }]} /></div>
        </Panel>
        <Panel title="Rank IC by year (×100) — is the edge still there?">
          <div className="overflow-x-auto"><table className="w-full text-2xs tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Signal</th>{years.map((y) => <th key={y} className="font-normal px-0.5 text-center">{String(y).slice(2)}</th>)}</tr></thead>
            <tbody>{[...d.signals, ...comps].map((s: any) => (
              <tr key={s.id}><td className="py-0.5 pr-2 whitespace-nowrap text-text-secondary">{SHORT[s.id] ?? COMP_SHORT[s.id] ?? 'Composite'}</td>
                {years.map((y) => <td key={y} className="px-0.5"><IcCell v={s.ic_by_year[y]} /></td>)}</tr>))}</tbody>
          </table></div>
        </Panel>
      </div>

      <Panel title={`Today's ideas — ${side === 'long' ? 'highest' : 'lowest'} composite scores`} right={
        <div className="flex gap-1"><Chip on={side === 'long'} onClick={() => setSide('long')}>Long book</Chip><Chip on={side === 'short'} onClick={() => setSide('short')}>Short book</Chip></div>}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Stock</th><th className="text-left font-normal">Sector</th><th className="text-right font-normal px-1">Score</th>
            <th className="text-right font-normal px-1">Size</th><th className="text-right font-normal px-1">Vol</th>
            {side === 'short' && <th className="text-right font-normal px-1">Borrow</th>}
            {Object.keys(SHORT).map((k) => <th key={k} className="text-center font-normal px-1">{SHORT[k]}</th>)}</tr></thead>
          <tbody>{book.map((x: any) => (
            <tr key={x.symbol} onClick={() => onOpen(x.symbol)} className="cursor-pointer hover:bg-surface-2">
              <td className="py-1 font-sans whitespace-nowrap"><span className="text-text-primary">{x.symbol}</span> <span className="text-text-tertiary">{(x.name ?? '').slice(0, 22)}</span></td>
              <td className="font-sans text-text-tertiary whitespace-nowrap max-w-[9rem] truncate">{x.sector ?? ''}</td>
              <td className={cn('text-right px-1 font-semibold', sign(x.score))}>{x.score.toFixed(2)}</td>
              <td className="text-right px-1">{(x.weight * 100).toFixed(1)}%</td>
              <td className="text-right px-1 text-text-secondary">{x.vol != null ? `${Math.round(x.vol * 100)}%` : '—'}</td>
              {side === 'short' && <td className={cn('text-right px-1', (x.borrow_fee ?? 0) >= 5 && 'text-red')}>{x.borrow_fee != null ? `${x.borrow_fee.toFixed(2)}%` : '—'}</td>}
              {Object.keys(SHORT).map((k) => <td key={k} className="px-0.5"><IcCell v={x.signals[k] != null ? x.signals[k] / 30 : null} /></td>)}
            </tr>))}</tbody>
        </table></div>
        <p className="text-[10px] text-text-tertiary mt-2">Size: inverse-volatility weights within the book, capped at 8%. Signal cells show each stock's standardised score (green = favourable for a long). Click a stock to open it.</p>
      </Panel>
      <SignalHealth />
      <Source>{d.method}</Source>
      <ul className="list-disc pl-4 space-y-0.5">{d.caveats.map((t: string) => <li key={t} className="text-[10px] text-text-tertiary">{t}</li>)}</ul>
    </div>
  );
}

const HEALTH: Record<string, { cls: string; tip: string }> = {
  gone: { cls: 'border-red/50 text-red', tip: 'Worked early on, not any more — retire' },
  'fading fast': { cls: 'border-red/50 text-red', tip: 'Falling sharply with a significant downward trend — retire' },
  'never worked': { cls: 'border-border text-text-tertiary', tip: 'Not positive in either half of its history — retire' },
  fading: { cls: 'border-amber/60 text-amber', tip: 'Still positive but well below its early strength — watch' },
  emerging: { cls: 'border-blue/50 text-blue', tip: 'Positive only lately — watch before trusting it' },
  'holding up': { cls: 'border-green/50 text-green', tip: 'Recent strength close to or above its early level' },
};

/** Signal health: decay of each signal's information coefficient, early history against the last three years. */
function SignalHealth() {
  const { data: h, error } = useJSON<any>('/api/v1/quant/decay', 3_600_000);
  if (error && !h) return <ErrorBox msg={error} />;
  if (!h?.signals?.length) return null;
  const ic = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(3)}`);
  return (
    <Panel title="Signal health — is each signal's edge holding up?"
      right={<span className="text-2xs text-text-tertiary">{Object.entries(h.counts??{}).filter(([, n]) => (n as number) > 0).map(([k, n]) => `${n} ${k}`).join(' · ')}</span>}>
      <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Signal health table"><table className="w-full text-2xs tabular-nums">
        <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Signal</th><th className="text-left font-normal">Universe</th>
          <th className="text-left font-normal">Status</th><th className="text-right font-normal">IC early</th><th className="text-right font-normal">IC last 3y</th>
          <th className="text-right font-normal">Trend / yr</th><th className="text-right font-normal">Half-life</th></tr></thead>
        <tbody>{h.signals.map((r: any) => (
          <tr key={r.universe + r.id} className="border-t border-border-subtle">
            <td className="py-1 text-text-primary">{r.name}</td>
            <td className="text-text-secondary">{r.universe === 'sp500' ? 'S&P 500' : 'Mid/small'}</td>
            <td><span title={HEALTH[r.status]?.tip ?? r.status} className={cn('px-1.5 py-px rounded border', HEALTH[r.status]?.cls ?? 'border-border text-text-tertiary')}>
              {r.status}{r.retire ? ' · retire' : ''}</span></td>
            <td className="text-right font-mono">{ic(r.ic_early)}</td>
            <td className={cn('text-right font-mono', sign(r.ic_recent))}>{ic(r.ic_recent)}</td>
            <td className="text-right font-mono text-text-secondary" title={r.trend_t != null ? `t = ${r.trend_t}` : ''}>{r.trend_per_year != null ? ic(r.trend_per_year) : '—'}</td>
            <td className="text-right font-mono text-text-secondary">{r.half_life_years != null ? `${r.half_life_years}y` : '—'}</td></tr>))}</tbody>
      </table></div>
      <p className="text-[10px] text-text-tertiary mt-2">{h.rule} {h.method} Basis: {h.signals[0]?.basis}.</p>
    </Panel>
  );
}

// ── PROOF: what actually works — every tested strategy and signal judged by alpha, not return ──
const VERDICT_LABEL: Record<string, string> = { alpha: 'Proven alpha', promising: 'Promising', beta: 'Mostly beta', 'no edge': 'No edge' };
export function ProofView({ onGo }: { onGo: (fn: string, s?: string) => void }) {
  const { data: d, error, loading } = useJSON<any>('/api/v1/quant/proof', 600_000);
  const [filter, setFilter] = useState<string>('all');
  if (loading && !d) return <Loading label="Scoring every tested strategy…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const rows = d.rows.filter((r: any) => filter === 'all' || r.verdict === filter);
  return (
    <div className="space-y-3">
      <div className="alpha-verdict none" style={d.counts.alpha ? { borderColor: 'rgb(var(--c-green) / .45)', background: 'rgb(var(--c-green) / .07)' } : undefined}>
        <b>{d.headline}</b>
        <ul className="list-disc pl-4 mt-1.5 space-y-1">{d.takeaways.map((t: string) => <li key={t}>{t}</li>)}</ul>
      </div>
      {d.forward?.length > 0 && (
        <Panel title="Forward tracking — out-of-sample from the day each was frozen" right={<span className="text-[11px] text-text-tertiary">updates when the library re-runs</span>}>
          <table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Strategy</th><th className="text-left font-normal">Frozen</th>
              <th className="text-right font-normal px-1">Days</th><th className="text-right font-normal px-1">Return</th><th className="text-right font-normal px-1">Benchmark</th>
              <th className="text-right font-normal px-1">Excess</th><th className="text-left font-normal pl-3">Mandate / governance</th></tr></thead>
            <tbody>{d.forward.map((f: any) => (
              <tr key={f.id} title={f.reason}>
                <td className="py-1 font-sans text-text-primary">{f.name ?? f.id}</td><td>{f.since}</td><td className="text-right px-1">{f.days}</td>
                <td className={cn('text-right px-1', sign(f.return))}>{f.days ? pct(f.return, 2) : 'from next session'}</td>
                <td className="text-right px-1 text-text-secondary">{f.days ? pct(f.benchmark, 2) : '—'}</td>
                <td className={cn('text-right px-1 font-semibold', sign(f.excess))}>{f.days ? pct(f.excess, 2) : '—'}</td>
                <td className="pl-3 font-sans text-text-secondary">{f.mandate}</td>
              </tr>))}</tbody>
          </table>
          <p className="text-[10px] text-text-tertiary mt-2">A strategy earns a larger allocation only if this live record confirms the backtest. A record of a few weeks is noise; judge after at least a year.</p>
        </Panel>
      )}
      <div className="flex flex-wrap gap-1">
        <Chip on={filter === 'all'} onClick={() => setFilter('all')}>All ({d.rows.length})</Chip>
        {Object.keys(VERDICT_LABEL).map((k) => <Chip key={k} on={filter === k} onClick={() => setFilter(k)}>{VERDICT_LABEL[k]} ({d.counts[k]})</Chip>)}
      </div>
      <Panel title="Every tested strategy and signal, judged by alpha" right={<span className="text-[11px] text-text-tertiary">{d.n_trials} trials allowed for in the deflated Sharpe</span>}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Verdict</th><th className="text-left font-normal">Strategy / signal</th>
            <th className="text-right font-normal px-1">Return a yr</th><th className="text-right font-normal px-1">Sharpe</th><th className="text-right font-normal px-1">Alpha a yr</th>
            <th className="text-right font-normal px-1">t</th><th className="text-right font-normal px-1">Equity β</th><th className="text-right font-normal px-1">Deflated SR</th>
            <th className="text-right font-normal px-1">PBO</th><th className="text-right font-normal px-1">Max DD</th>
            <th className="text-right font-normal px-1" title="Average monthly return in the worst tenth of S&P 500 months (index return in brackets)">In crises</th></tr></thead>
          <tbody>{rows.map((r: any) => (
            <tr key={r.id} title={[r.verdict_text, r.note, r.alpha_basis].filter(Boolean).join(' · ')}>
              <td className="py-1"><span className={cn('proof-pill', r.verdict.replace(' ', '-'))}>{VERDICT_LABEL[r.verdict]}</span></td>
              <td className="font-sans text-text-primary">{r.name}<span className="block text-[10px] text-text-tertiary">{r.family}{r.note ? ' · CAPM-only alpha (carry)' : ''}</span></td>
              <td className="text-right px-1">{pct(r.cagr, 1)}</td>
              <td className="text-right px-1">{num(r.sharpe, 2)}</td>
              <td className={cn('text-right px-1 font-semibold', sign(r.alpha))}>{pct(r.alpha, 1)}</td>
              <td className={cn('text-right px-1', (r.alpha_t ?? 0) >= 2 ? 'text-green' : (r.alpha_t ?? 0) <= -2 ? 'text-red' : 'text-text-secondary')}>{num(r.alpha_t, 1)}</td>
              <td className="text-right px-1 text-text-secondary">{num(r.equity_beta, 2)}</td>
              <td className={cn('text-right px-1', (r.deflated_sharpe ?? 0) >= 0.9 ? 'text-green' : 'text-text-secondary')}>{r.deflated_sharpe != null ? `${Math.round(r.deflated_sharpe * 100)}%` : '—'}</td>
              <td className={cn('text-right px-1', (r.pbo ?? 0) > 0.5 ? 'text-red' : 'text-text-secondary')}>{r.pbo != null ? `${Math.round(r.pbo * 100)}%` : '—'}</td>
              <td className="text-right px-1 text-text-secondary">{pct(r.max_drawdown, 0)}</td>
              <td className="text-right px-1" title={r.downside_capture != null ? `Downside capture ${Math.round(r.downside_capture * 100)}% of the index's down months` : ''}>
                {r.crisis_return != null ? <><span className={sign(r.crisis_return)}>{pct(r.crisis_return, 1)}</span>
                  <span className="text-text-tertiary"> ({pct(r.crisis_benchmark, 0)})</span>
                  {r.role && <span className={cn('block text-[10px]', r.role === 'crisis diversifier' ? 'text-green' : 'text-text-tertiary')}>{r.role}</span>}</> : '—'}</td>
            </tr>))}</tbody>
        </table></div>
        <p className="text-[10px] text-text-tertiary mt-2">Alpha: multi-factor (equity, credit, rates, EM, dollar, size, low risk, inflation) for strategies; top fifth vs the index for stock signals; tactical vs strategic for the macro model. Deflated SR: the chance the Sharpe ratio is real after {d.n_trials} trials. In crises: a diversifier (trend, defensive) can earn little alpha yet pay when equities fall — judge those on this column, not on alpha alone. PBO: probability the backtest's chosen settings were overfitted. Hover a row for the verdict. <button className="text-bloomberg hover:underline" onClick={() => onGo('ALPHA')}>Open the Stock Signal Lab →</button></p>
      </Panel>
      <Source>{d.method} {d.stale_note}</Source>
    </div>
  );
}

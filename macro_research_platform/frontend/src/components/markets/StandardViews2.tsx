// More standard Bloomberg screens (backend: api/marketdata/bbgstd.py):
//   FWCV forward curves · ECFC economic forecasts · FOMC Fed portal · EM earnings matrix · EA earnings analysis
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { BarList } from '@/components/ui/BarList';
import { useStickyState } from '@/lib/stickyState';
import { SpfPanel } from './GapViews';
import { ErrorBox, Loading, Panel, useJSON } from './shared';
import { Chip, pct, sign, Source, Tile } from './StandardViews';

const rate = (v: number | null | undefined, d = 2) => (v == null ? '—' : `${v.toFixed(d)}%`);
const bp = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : ''}${Math.round(v)}`);
const num = (v: number | null | undefined, d = 1) => (v == null ? '—' : v.toFixed(d));
const REGION: Record<string, string> = { americas: 'Americas', europe: 'Europe', mea: 'Middle East & Africa', apac: 'Asia-Pacific' };

// ── FWCV ─────────────────────────────────────────────────────────────────────
export function FwcvView() {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/fwcv', 3 * 3_600_000);
  const [code, setCode] = useStickyState('fwcv.code', 'US');
  if (loading && !d) return <Loading label="Building forward curves…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const c = d.curves.find((x: any) => x.code === code) ?? d.curves[0];
  const labels: string[] = Array.from(new Set(d.curves.flatMap((x: any) => x.pairs.map((p: any) => p.label))));
  return (
    <div className="space-y-3">
      <Panel title="Key forward rates by market" right={<span className="text-[11px] text-text-tertiary">change over a month in bp</span>}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Market</th><th className="text-right font-normal px-1">Priced 1y move</th>
            {labels.map((l) => <th key={l} className="text-right font-normal px-1">{l}</th>)}</tr></thead>
          <tbody>{d.curves.map((x: any) => {
            const by = Object.fromEntries(x.pairs.map((p: any) => [p.label, p]));
            return (
              <tr key={x.code} onClick={() => setCode(x.code)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-2', x.code === c.code && 'bg-surface-2')}>
                <td className="py-1 font-sans text-text-primary whitespace-nowrap">{x.name} <span className="text-text-tertiary">{x.date}</span></td>
                <td className={cn('text-right px-1', sign(x.priced_1y_change_bp))} title="1y1y minus today's 1-year: the move in 1-year rates the curve prices over the next year">{bp(x.priced_1y_change_bp)}</td>
                {labels.map((l) => <td key={l} className="text-right px-1">{by[l] ? <>{rate(by[l].rate)} <span className={cn('text-[10px]', sign(by[l].change_1m_bp))}>{bp(by[l].change_1m_bp)}</span></> : '—'}</td>)}
              </tr>
            );
          })}</tbody>
        </table></div>
      </Panel>
      <Panel title={`${c.name}: the 1-year rate the curve implies in each future year`}>
        <div className="mkt-chart-surface"><LineChart rows={c.one_year.map((p: any) => ({ x: `${p.start}y`, fwd: p.rate, spot: p.spot }))} x="x" height={240} controls={false}
          fmt={(v) => `${v.toFixed(2)}%`} lines={[{ key: 'fwd', label: '1-year forward', color: 'rgb(var(--c-bloomberg))' }, { key: 'spot', label: 'Spot curve', color: 'rgb(var(--c-text-tertiary))' }]} /></div>
      </Panel>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── ECFC ─────────────────────────────────────────────────────────────────────
export function EcfcView({ onGo }: { onGo: (fn: string, s?: string) => void }) {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/ecfc', 6 * 3_600_000);
  const [region, setRegion] = useStickyState<string | null>('ecfc.region', null);
  const [all, setAll] = useState(false);
  if (loading && !d) return <Loading label="Loading IMF forecasts…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const rows = d.rows.filter((r: any) => !region || r.region === region);
  const shown = all ? rows : rows.slice(0, 40);
  const y = d.year;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label={`World growth ${y}`} value={rate(d.world_growth_usd_weighted, 1)} sub="GDP-weighted, in US dollars" />
        {d.regions.map((r: any) => <Tile key={r.region} label={REGION[r.region]} value={`${num(r.gdp_growth)}% → ${num(r.gdp_growth_next)}%`}
          sub={`median growth ${y} → ${y + 1}; inflation ${num(r.inflation)}% → ${num(r.inflation_next)}%`} />)}
      </div>
      <SpfPanel />
      <div className="flex flex-wrap gap-1">
        <Chip on={!region} onClick={() => setRegion(null)}>All</Chip>
        {Object.entries(REGION).map(([k, l]) => <Chip key={k} on={region === k} onClick={() => setRegion(k)}>{l}</Chip>)}
      </div>
      <Panel title={`IMF forecasts, largest economies first (${rows.length})`}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Country</th>
            <th className="text-right font-normal px-1">GDP {y}</th><th className="text-right font-normal px-1">GDP {y + 1}</th>
            <th className="text-right font-normal px-1">CPI {y}</th><th className="text-right font-normal px-1">CPI {y + 1}</th>
            <th className="text-right font-normal px-1">Latest CPI</th><th className="text-right font-normal px-1">vs forecast</th>
            <th className="text-right font-normal px-1">Jobless</th><th className="text-right font-normal px-1">Current acct</th>
            <th className="text-right font-normal px-1">Gov. debt</th><th className="text-right font-normal px-1">Policy</th><th className="text-right font-normal px-1">Real policy</th></tr></thead>
          <tbody>{shown.map((r: any) => {
            const gap = r.cpi_latest != null && r.inflation != null ? r.cpi_latest - r.inflation : null;
            return (
              <tr key={r.iso} onClick={() => onGo('CTRY', r.iso)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2">
                <td className="py-1 font-sans text-text-primary whitespace-nowrap">{r.name}</td>
                <td className={cn('text-right px-1', sign(r.gdp_growth))}>{rate(r.gdp_growth, 1)}</td>
                <td className={cn('text-right px-1', sign(r.gdp_growth_next))}>{rate(r.gdp_growth_next, 1)}</td>
                <td className="text-right px-1">{rate(r.inflation, 1)}</td><td className="text-right px-1">{rate(r.inflation_next, 1)}</td>
                <td className="text-right px-1" title={r.cpi_month ?? ''}>{rate(r.cpi_latest, 1)}</td>
                <td className={cn('text-right px-1', gap == null ? '' : gap > 0.5 ? 'text-red' : gap < -0.5 ? 'text-green' : '')}>{gap == null ? '—' : `${gap > 0 ? '+' : ''}${gap.toFixed(1)}`}</td>
                <td className="text-right px-1 text-text-secondary">{rate(r.unemployment, 1)}</td>
                <td className={cn('text-right px-1', sign(r.current_account))}>{rate(r.current_account, 1)}</td>
                <td className="text-right px-1 text-text-secondary">{r.gov_debt != null ? `${Math.round(r.gov_debt)}%` : '—'}</td>
                <td className="text-right px-1">{rate(r.policy_rate)}</td>
                <td className={cn('text-right px-1', sign(r.real_policy_rate))}>{rate(r.real_policy_rate)}</td>
              </tr>
            );
          })}</tbody>
        </table></div>
        {rows.length > 40 && <button onClick={() => setAll(!all)} className="mt-2 text-[11px] text-bloomberg hover:underline">{all ? 'Show the largest 40' : `Show all ${rows.length}`}</button>}
      </Panel>
      <Source>{d.note} Current account and debt in % of GDP. {d.source}</Source>
    </div>
  );
}

// ── FOMC ─────────────────────────────────────────────────────────────────────
export function FomcView() {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/fomc', 900_000);
  if (loading && !d) return <Loading label="Loading the Fed…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const next = d.market?.next_meeting;
  const ff = d.sep.fed_funds;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label="Target range" value={`${rate(d.target_lower)} – ${rate(d.target_upper)}`} sub={`effective ${rate(d.effective)}`} />
        <Tile label="Last decision" value={d.last_move ? `${d.last_move.change_bp > 0 ? '+' : ''}${d.last_move.change_bp}bp` : '—'} cls={sign(d.last_move?.change_bp)} sub={d.last_move?.date} />
        <Tile label="Last two years" value={<><span className="text-red">{d.hikes_2y} hikes</span> · <span className="text-green">{d.cuts_2y} cuts</span></>} />
        <Tile label="Next meeting" value={next ? next.meeting : '—'}
          sub={next ? Object.entries(next.probabilities).map(([k, v]) => `${k} ${Math.round((v as number) * 100)}%`).join(' · ') : 'futures unavailable'} />
        <Tile label="Long-run neutral (dots)" value={rate(ff?.longer_run, 2)} sub="the FOMC's median longer-run rate" />
      </div>
      {d.dots_vs_market && (
        <Panel title="Fed dots vs market pricing (year-end fed funds)">
          <table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Year end</th><th className="text-right font-normal">FOMC median dot</th>
              <th className="text-right font-normal">Futures imply</th><th className="text-right font-normal">Market − Fed</th><th className="text-left font-normal pl-3">Reading</th></tr></thead>
            <tbody>{d.dots_vs_market.map((g: any) => (
              <tr key={g.year} className="border-t border-border-subtle"><td className="py-1">{g.year}</td><td className="text-right">{rate(g.dots)}</td><td className="text-right">{rate(g.market)}</td>
                <td className={cn('text-right', sign(g.gap_bp))}>{bp(g.gap_bp)} bp</td>
                <td className="pl-3 font-sans text-text-secondary">{g.gap_bp == null ? '—' : Math.abs(g.gap_bp) < 15 ? 'market agrees with the Fed' : g.gap_bp > 0 ? 'market prices a higher rate than the Fed projects' : 'market prices a lower rate than the Fed projects'}</td></tr>))}</tbody>
          </table>
        </Panel>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title="Summary of Economic Projections (median, with the range of participants)">
          <table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Measure</th>
              {(ff?.years ?? []).map((y: any) => <th key={y.year} className="text-right font-normal px-1">{y.year}</th>)}<th className="text-right font-normal px-1">Longer run</th></tr></thead>
            <tbody>{Object.entries(d.sep).map(([k, v]: [string, any]) => (
              <tr key={k} className="border-t border-border-subtle"><td className="py-1 font-sans text-text-secondary">{v.label}</td>
                {(ff?.years ?? []).map((y: any) => {
                  const c = v.years.find((x: any) => x.year === y.year);
                  return <td key={y.year} className="text-right px-1" title={c && c.low != null ? `range ${c.low}–${c.high}` : ''}>{c ? c.median.toFixed(1) : '—'}
                    {c && c.low != null && <span className="block text-[9px] text-text-tertiary">{c.low}–{c.high}</span>}</td>;
                })}
                <td className="text-right px-1">{v.longer_run != null ? v.longer_run.toFixed(1) : '—'}</td></tr>))}</tbody>
          </table>
        </Panel>
        <Panel title="Market-implied rate after each meeting">
          {d.market?.path?.length ? (
            <div className="mkt-chart-surface"><LineChart rows={d.market.path.map((m: any) => ({ meeting: m.meeting, implied: m.implied_rate }))} x="meeting" height={220} controls={false}
              fmt={(v) => `${v.toFixed(2)}%`} refs={(ff?.years ?? []).slice(0, 2).map((y: any) => ({ value: y.median, label: `${y.year} dot` }))}
              lines={[{ key: 'implied', label: 'Futures-implied', color: 'rgb(var(--c-bloomberg))' }]} /></div>
          ) : <p className="text-xs text-text-tertiary">Fed funds futures unavailable right now.</p>}
        </Panel>
      </div>
      <Panel title="Rate decisions since 2008">
        <div className="max-h-64 overflow-y-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Date</th><th className="text-right font-normal">Move</th><th className="text-right font-normal">New range</th></tr></thead>
          <tbody>{d.decisions.map((x: any) => (
            <tr key={x.date} className="border-t border-border-subtle"><td className="py-1">{x.date}</td><td className={cn('text-right', sign(x.change_bp))}>{x.change_bp > 0 ? '+' : ''}{x.change_bp}bp</td>
              <td className="text-right">{rate(x.lower)} – {rate(x.upper)}</td></tr>))}</tbody>
        </table></div>
      </Panel>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── EM ───────────────────────────────────────────────────────────────────────
export function EmView({ symbol }: { symbol: string }) {
  const [field, setField] = useStickyState<'eps' | 'revenue'>('em.field', 'eps');
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/em/${encodeURIComponent(symbol)}?years=8`, 6 * 3_600_000);
  if (loading && !d) return <Loading label="Reading quarterly results from SEC filings…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const fmt = (v: number | null | undefined) => (v == null ? '—' : field === 'eps' ? v.toFixed(2) : v >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : `${(v / 1e6).toFixed(0)}M`);
  const cell = (v: number | null | undefined, g: number | null | undefined) => (
    <><div className={cn(v != null && v < 0 && 'text-red')}>{fmt(v)}</div><div className={cn('text-[10px]', sign(g))}>{g == null ? '' : pct(g, 0)}</div></>
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1">
        <Chip on={field === 'eps'} onClick={() => setField('eps')}>Diluted EPS</Chip>
        <Chip on={field === 'revenue'} onClick={() => setField('revenue')}>Revenue</Chip>
        <span className="ml-auto text-[11px] text-text-tertiary">last 4 quarters: EPS {d.ttm_eps != null ? d.ttm_eps.toFixed(2) : '—'} · revenue {d.ttm_revenue != null ? `${(d.ttm_revenue / 1e9).toFixed(1)}B` : '—'}</span>
      </div>
      <Panel title={`${d.name ?? symbol} — ${field === 'eps' ? 'diluted EPS' : 'revenue'} by fiscal quarter (growth on a year earlier below)`}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Fiscal year</th>
            {[1, 2, 3, 4].map((q) => <th key={q} className="text-right font-normal px-2">Q{q}</th>)}<th className="text-right font-normal px-2">Year</th></tr></thead>
          <tbody>{[...d.rows].reverse().map((r: any) => (
            <tr key={r.year_end} className="border-t border-border-subtle align-top">
              <td className="py-1 font-sans text-text-primary">FY{r.fiscal_year} <span className="text-text-tertiary">to {r.year_end}{r.complete ? '' : ' (in progress)'}</span></td>
              {[1, 2, 3, 4].map((q) => {
                const x = r.quarters.find((c: any) => c.q === q);
                return <td key={q} className="text-right px-2 py-1" title={x ? `quarter ended ${x.end}` : ''}>{x ? cell(x[field], x[`${field}_yoy`]) : <span className="text-text-tertiary">—</span>}</td>;
              })}
              <td className="text-right px-2 py-1 font-semibold">{cell(r[field], r[`${field}_yoy`])}</td>
            </tr>))}</tbody>
        </table></div>
      </Panel>
      <Source>{d.source}</Source>
    </div>
  );
}

// ── EA ───────────────────────────────────────────────────────────────────────
export function EaView({ onOpen }: { onOpen: (s: string) => void }) {
  const [code, setCode] = useStickyState('earn.code', 'SPX');
  const [days, setDays] = useStickyState('earn.days', 45);
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/ea/${code}?days=${days}`, 1_800_000);
  const controls = (
    <div className="flex flex-wrap gap-1">
      {['SPX', 'NDX', 'INDU'].map((c) => <Chip key={c} on={code === c} onClick={() => setCode(c)}>{c}</Chip>)}
      <span className="w-3" />
      {[30, 45, 92].map((n) => <Chip key={n} on={days === n} onClick={() => setDays(n)}>{n === 92 ? 'Last quarter' : `${n} days`}</Chip>)}
    </div>
  );
  if (loading && !d) return <div className="space-y-2">{controls}<Loading label="Collecting this season's reports…" /></div>;
  if (error && !d) return <div className="space-y-2">{controls}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  const List = ({ title, rows, metric }: { title: string; rows: any[]; metric: 'surprise' | 'reaction' }) => (
    <Panel title={title}>
      <table className="w-full text-2xs font-mono tabular-nums">
        <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Company</th><th className="text-right font-normal">EPS vs est.</th>
          <th className="text-right font-normal">Surprise</th><th className="text-right font-normal">Reaction</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.symbol + r.datetime} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2" title={r.name}>
            <td className="py-1 font-sans whitespace-nowrap"><span className="text-text-primary">{r.symbol}</span> <span className="text-text-tertiary">{r.datetime.slice(5, 10)}</span></td>
            <td className="text-right text-text-secondary">{r.eps_reported?.toFixed(2)} / {r.eps_estimate?.toFixed(2)}</td>
            <td className={cn('text-right', sign(r.surprise_pct), metric === 'surprise' && 'font-semibold')}>{r.surprise_pct != null ? `${r.surprise_pct > 0 ? '+' : ''}${r.surprise_pct.toFixed(1)}%` : '—'}</td>
            <td className={cn('text-right', sign(r.reaction), metric === 'reaction' && 'font-semibold')}>{pct(r.reaction)}</td></tr>))}</tbody>
      </table>
    </Panel>
  );
  return (
    <div className="space-y-3">
      {controls}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label="Reported" value={`${d.reported} of ${d.members}`} sub={d.reported_weight != null ? `${Math.round(d.reported_weight * 100)}% of index weight` : `last ${d.window_days} days`} />
        <Tile label="Beat estimates" value={`${Math.round(d.beat_rate * 100)}%`} sub={`${Math.round(d.miss_rate * 100)}% missed · ${Math.round(d.in_line_rate * 100)}% in line`} />
        <Tile label="Median surprise" value={d.median_surprise != null ? `${d.median_surprise > 0 ? '+' : ''}${d.median_surprise.toFixed(1)}%` : '—'} cls={sign(d.median_surprise)} />
        <Tile label="Reaction to beats / misses" value={<><span className={sign(d.avg_reaction_beat)}>{pct(d.avg_reaction_beat)}</span> / <span className={sign(d.avg_reaction_miss)}>{pct(d.avg_reaction_miss)}</span></>} sub="average next-session move" />
        <Tile label="Beat but fell" value={d.beat_and_fell} sub={`${d.missed_and_rose} missed but rose`} />
      </div>
      <Panel title="By sector (beat rate)">
        <BarList data={d.sectors.map((s: any) => ({ label: `${s.sector} (${s.reported}/${s.members})`, value: s.beat_rate * 100 }))} fmt={(v) => `${v.toFixed(0)}%`} labelWidth="16rem" />
      </Panel>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <List title="Biggest beats" rows={d.biggest_beats} metric="surprise" />
        <List title="Biggest misses" rows={d.biggest_misses} metric="surprise" />
        <List title="Biggest share reactions" rows={d.biggest_reactions} metric="reaction" />
      </div>
      {d.upcoming.length > 0 && (
        <Panel title="Still to report (next two weeks)">
          <div className="flex flex-wrap gap-1">{d.upcoming.map((u: any) => (
            <button key={u.symbol + u.datetime} onClick={() => onOpen(u.symbol)} title={u.name} className="px-2 py-0.5 border border-border rounded-sm text-[11px] text-text-secondary hover:text-text-primary">
              {u.symbol} <span className="text-text-tertiary">{u.datetime.slice(5, 10)}</span></button>))}</div>
        </Panel>
      )}
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

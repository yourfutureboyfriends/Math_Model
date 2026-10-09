// Instrument workstation — works for ANY instrument: quote header, interactive chart,
// profile (company / fund / instrument facts, valuation, analyst targets), financial
// statements (SEC as-filed for US filers, company reports otherwise) and news + filings.
import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PriceChart } from '@/components/ui/PriceChart';
import { Chg, ErrorBox, fmtBig, fmtPct, fmtPrice, Loading, Panel, TYPE_COLOR, useJSON } from './shared';

const TABS = [['overview', 'Overview'], ['financials', 'Financials'], ['news', 'News & filings']] as const;

export function TickerView({ symbol }: { symbol: string }) {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('overview');
  const q = useJSON<any>(`/api/v1/mkt/quote/${encodeURIComponent(symbol)}`, 60_000);
  if (q.loading && !q.data) return <Loading label={`Loading ${symbol}…`} />;
  if (q.error && !q.data) return <ErrorBox msg={q.error} />;
  const d = q.data;
  if (!d) return null;
  const isEquity = d.type === 'Stock';
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-text-primary truncate">{d.name}</h1>
            <span className={cn('text-2xs font-mono px-1.5 border border-border', TYPE_COLOR[d.type])}>{d.type}</span>
          </div>
          <div className="text-2xs text-text-tertiary font-mono">{d.symbol} · {d.exchange}{d.currency ? ` · ${d.currency}` : ''}
            {d.market_state && <> · {d.market_state === 'REGULAR' ? <span className="text-green">market open</span> : d.market_state.toLowerCase()}</>}
            {d.delay_minutes ? ` · ${d.delay_minutes}-min delayed` : ''}</div>
        </div>
        <div>
          <div className="text-2xl font-mono text-text-primary tabular-nums">{fmtPrice(d.price, d.type)}</div>
          <div className="text-xs font-mono">{d.change == null ? '—' : <span className={d.change >= 0 ? 'text-green' : 'text-red'}>{d.change >= 0 ? '+' : ''}{fmtPrice(d.change, d.type)}</span>} <Chg v={d.change_pct} /></div>
        </div>
        <dl className="grid grid-cols-3 sm:grid-cols-6 gap-x-4 gap-y-1 text-2xs">
          {[['Open', fmtPrice(d.open, d.type)], ['Day range', d.day_low != null ? `${fmtPrice(d.day_low, d.type)}–${fmtPrice(d.day_high, d.type)}` : '—'],
            ['52-wk range', d.week52_low != null ? `${fmtPrice(d.week52_low, d.type)}–${fmtPrice(d.week52_high, d.type)}` : '—'],
            ['Volume', fmtBig(d.volume)], ['Avg volume', fmtBig(d.avg_volume)], ['Market cap', fmtBig(d.market_cap, d.currency)]].map(([k, v]) => (
            <div key={k}><dt className="text-text-tertiary">{k}</dt><dd className="font-mono text-text-primary">{v}</dd></div>
          ))}
        </dl>
      </div>

      <div className="bg-surface-1 border border-border p-2">
        <PriceChart key={symbol} symbol={symbol} height={360} />
      </div>

      <div className="flex border border-border w-fit" role="tablist" aria-label="Workstation">
        {TABS.filter(([k]) => k !== 'financials' || isEquity).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={cn('px-3 py-1 text-2xs', tab === k ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>{l}</button>
        ))}
      </div>
      {tab === 'overview' && <Profile symbol={symbol} />}
      {tab === 'financials' && isEquity && <Financials symbol={symbol} />}
      {tab === 'news' && <News symbol={symbol} />}
    </div>
  );
}

function Profile({ symbol }: { symbol: string }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/profile/${encodeURIComponent(symbol)}`);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  const v = data.valuation, a = data.analysts;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-3">
      <Panel title="About">
        {data.description ? <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-line">{data.description}</p>
          : <p className="text-2xs text-text-tertiary">No description provided for this instrument.</p>}
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3 text-2xs">
          {[['Sector', data.sector], ['Industry', data.industry], ['Country', data.country], ['Employees', data.employees?.toLocaleString()],
            ['Category', data.category], ['Fund family', data.fund_family], ['Expense ratio', data.expense_ratio != null ? fmtPct(data.expense_ratio / (data.expense_ratio > 0.2 ? 100 : 1)) : null],
            ['Fund assets', data.total_assets != null ? fmtBig(data.total_assets, data.currency) : null], ['Underlying', data.underlying]]
            .filter(([, x]) => x != null && x !== '').map(([k, x]) => (
              <div key={k as string}><dt className="text-text-tertiary">{k}</dt><dd className="text-text-primary">{x as string}</dd></div>))}
          {data.website && <div><dt className="text-text-tertiary">Website</dt><dd><a href={data.website} target="_blank" rel="noreferrer noopener" className="text-bloomberg underline">{data.website.replace(/^https?:\/\//, '')}</a></dd></div>}
        </dl>
      </Panel>
      {v && (
        <div className="space-y-3">
          <Panel title="Valuation (Yahoo)">
            <dl className="grid grid-cols-2 gap-1.5 text-2xs">
              {[['P/E (trailing)', v.trailing_pe?.toFixed(1)], ['P/E (forward)', v.forward_pe?.toFixed(1)], ['Price / book', v.price_to_book?.toFixed(2)],
                ['Price / sales', v.price_to_sales?.toFixed(2)], ['EV / EBITDA', v.ev_to_ebitda?.toFixed(1)], ['PEG', v.peg?.toFixed(2)],
                ['Dividend yield', v.dividend_yield != null ? fmtPct(v.dividend_yield) : null], ['Beta', v.beta?.toFixed(2)]].map(([k, x]) => (
                <div key={k as string} className="flex justify-between gap-2"><dt className="text-text-tertiary">{k}</dt><dd className="font-mono text-text-primary">{x ?? '—'}</dd></div>))}
            </dl>
          </Panel>
          {a?.target_mean != null && (
            <Panel title={`Analysts (${a.analysts ?? '?'})`}>
              <div className="text-2xs text-text-secondary">Target <span className="font-mono text-text-primary">{fmtPrice(a.target_mean)}</span> (range {fmtPrice(a.target_low)}–{fmtPrice(a.target_high)}) · consensus <span className="text-text-primary">{a.recommendation?.replace('_', ' ') ?? '—'}</span></div>
            </Panel>
          )}
        </div>
      )}
    </div>
  );
}

const ROWS: [string, string][] = [['revenue', 'Revenue'], ['gross_profit', 'Gross profit'], ['operating_income', 'Operating income'],
  ['net_income', 'Net income'], ['eps_diluted', 'EPS (diluted)'], ['operating_cash_flow', 'Operating cash flow'], ['capex', 'Capex'],
  ['free_cash_flow', 'Free cash flow'], ['total_assets', 'Total assets'], ['total_liabilities', 'Total liabilities'], ['equity', 'Equity'],
  ['cash', 'Cash'], ['long_term_debt', 'Long-term debt']];

function Financials({ symbol }: { symbol: string }) {
  const [period, setPeriod] = useState<'annual' | 'quarterly'>('annual');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/statements/${encodeURIComponent(symbol)}`);
  if (loading && !data) return <Loading label="Loading statements…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  if (data.provider === 'yahoo') {
    return (
      <div className="space-y-3">
        {Object.entries(data.tables).map(([k, t]: [string, any]) => (
          <Panel key={k} title={`${{ income: 'Income statement (annual)', balance: 'Balance sheet', cashflow: 'Cash flow', income_q: 'Income statement (quarterly)' }[k] ?? k} · ${data.currency ?? ''}`}>
            <div className="overflow-x-auto"><table className="w-full text-2xs font-mono">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Item</th>{t.periods.map((p: string) => <th key={p} className="text-right font-normal px-2">{p.slice(0, 7)}</th>)}</tr></thead>
              <tbody>{t.rows.slice(0, 40).map((r: any, i: number) => (
                <tr key={r.item} className={cn('border-t', i === t.key_lines ? 'border-border' : 'border-border-subtle')}>
                  <td className={cn('font-sans pr-2 whitespace-nowrap', i < t.key_lines ? 'text-text-primary' : 'text-text-tertiary')}>{r.item}</td>
                  {r.values.map((x: number | null, i: number) => <td key={i} className="text-right px-2">{fmtBig(x)}</td>)}</tr>))}</tbody>
            </table></div>
          </Panel>
        ))}
        <div className="text-[10px] text-text-tertiary">{data.source}</div>
      </div>
    );
  }
  const rows = (period === 'annual' ? data.annual : data.quarterly) as any[];
  const r = data.ratios ?? {};
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        {[['Gross margin', r.gross_margin], ['Operating margin', r.operating_margin], ['Net margin', r.net_margin], ['FCF margin', r.fcf_margin],
          ['ROE', r.roe], ['ROA', r.roa], ['Debt / equity', r.debt_to_equity, 'x'], ['Current ratio', r.current_ratio, 'x']].map(([k, x, u]) => (
          <div key={k as string} className="px-2 py-1.5 bg-surface-1 border border-border">
            <div className="text-[10px] uppercase text-text-tertiary">{k}</div>
            <div className="font-mono text-xs text-text-primary">{x == null ? '—' : u === 'x' ? `${(x as number).toFixed(2)}×` : fmtPct(x as number, 1)}</div>
          </div>))}
      </div>
      <Panel title={`SEC filings, as filed · TTM to ${data.ttm?.as_of ?? '—'}`} right={
        <div className="flex border border-border">{(['annual', 'quarterly'] as const).map((p) => (
          <button key={p} onClick={() => setPeriod(p)} className={cn('px-2 py-0.5 text-[10px]', period === p ? 'bg-surface-3 text-text-primary' : 'text-text-tertiary')}>{p}</button>))}</div>}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal">USD</th>
            {rows.map((x) => <th key={x.period_end} className="text-right font-normal px-2">{x.period_end.slice(0, 7)}</th>)}
            {period === 'annual' && <th className="text-right font-normal px-2 text-bloomberg">TTM</th>}</tr></thead>
          <tbody>{ROWS.filter(([k]) => rows.some((x) => x[k] != null)).map(([k, label]) => (
            <tr key={k} className="border-t border-border-subtle"><td className="text-text-secondary font-sans pr-2 whitespace-nowrap">{label}</td>
              {rows.map((x) => <td key={x.period_end} className="text-right px-2">{k === 'eps_diluted' ? (x[k]?.toFixed(2) ?? '—') : fmtBig(x[k])}</td>)}
              {period === 'annual' && <td className="text-right px-2 text-text-primary">{k === 'eps_diluted' ? (data.ttm?.[k]?.toFixed(2) ?? '') : fmtBig(data.ttm?.[k])}</td>}
            </tr>))}</tbody>
        </table></div>
      </Panel>
      <div className="flex flex-wrap gap-2 text-[10px]">
        {data.filings.map((f: any) => <a key={f.accession} href={f.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 px-2 py-0.5 border border-border text-text-secondary hover:border-bloomberg">
          {f.form} · {f.filed}<ExternalLink className="w-2.5 h-2.5" /></a>)}
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source} — {data.name}, CIK {data.cik}. Q4 and quarterly cash-flow figures are derived from the 10-K and year-to-date filings.</div>
    </div>
  );
}

function News({ symbol }: { symbol: string }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/news/${encodeURIComponent(symbol)}`, 900_000);
  if (loading && !data) return <Loading label="Loading news…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-3">
      <Panel title="Headlines">
        {data.news.length === 0 ? <div className="text-2xs text-text-tertiary">No recent headlines from the news provider.</div> : (
          <ul className="space-y-2">{data.news.map((n: any, i: number) => (
            <li key={i} className="text-xs">
              <a href={n.url} target="_blank" rel="noreferrer noopener" className="text-text-primary hover:text-bloomberg">{n.title}</a>
              <div className="text-[10px] text-text-tertiary">{n.publisher}{n.time ? ` · ${String(n.time).slice(0, 16).replace('T', ' ')}` : ''}</div>
            </li>))}</ul>)}
      </Panel>
      <Panel title="SEC filings (official)">
        {data.filings.length === 0 ? <div className="text-2xs text-text-tertiary">Not an SEC filer (non-US company, ETF or other instrument).</div> : (
          <ul className="space-y-1">{data.filings.map((f: any, i: number) => (
            <li key={i} className="text-2xs flex gap-2"><span className="font-mono text-text-tertiary w-20 shrink-0">{f.date}</span>
              <a href={f.url} target="_blank" rel="noreferrer noopener" className="text-text-secondary hover:text-bloomberg truncate" title={f.description}>
                <span className="font-mono text-text-primary">{f.form}</span> {f.description !== f.form ? f.description : ''}</a></li>))}</ul>)}
      </Panel>
    </div>
  );
}

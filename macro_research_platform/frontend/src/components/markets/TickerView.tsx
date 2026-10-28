// Instrument workstation — works for ANY instrument: quote header, interactive chart,
// profile (company / fund / instrument facts, valuation, analyst targets), financial
// statements (SEC as-filed for US filers, company reports otherwise) and news + filings.
import { LiveNumber } from '@/components/ui/LiveNumber';
import { useLiveQuote } from '@/lib/cryptoStream';
import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PriceChart } from '@/components/ui/PriceChart';
import { Chg, ErrorBox, fmtBig, fmtPct, fmtPrice, Loading, Panel, TYPE_COLOR, useJSON } from './shared';


export function useQuote(symbol: string) {
  return useJSON<any>(`/api/v1/mkt/quote/${encodeURIComponent(symbol)}`, 60_000);
}

export function QuoteHeader({ d: polled }: { d: any }) {
  const d = useLiveQuote(polled);
  return (
    <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold text-text-primary truncate">{d.name}</h1>
          <span className={cn('text-2xs font-mono px-1.5 py-0.5 border border-border', TYPE_COLOR[d.type])}>{d.type}</span>
        </div>
        <div className="text-2xs text-text-tertiary font-mono mt-0.5">{d.symbol} · {d.exchange}{d.currency ? ` · ${d.currency}` : ''}
          {d.market_state && <> · {d.market_state === 'REGULAR' ? <span className="text-green">market open</span> : d.market_state.toLowerCase()}</>}
          {d.delay_minutes ? ` · ${d.delay_minutes}-min delayed` : ''}</div>
      </div>
      <div>
        <LiveNumber value={d.price} format={(v) => fmtPrice(v, d.type)} className="block text-3xl font-mono text-text-primary tabular-nums leading-none" />
        <div className="text-sm font-mono mt-1">{d.change == null ? '—' : <span className={d.change >= 0 ? 'text-green' : 'text-red'}>{d.change >= 0 ? '+' : ''}{fmtPrice(d.change, d.type)}</span>} <Chg v={d.change_pct} /></div>
      </div>
      <dl className="grid grid-cols-3 sm:grid-cols-6 gap-x-5 gap-y-1 text-2xs">
        {[['Open', fmtPrice(d.open, d.type)], ['Day range', d.day_low != null ? `${fmtPrice(d.day_low, d.type)} – ${fmtPrice(d.day_high, d.type)}` : '—'],
          ['52-week range', d.week52_low != null ? `${fmtPrice(d.week52_low, d.type)} – ${fmtPrice(d.week52_high, d.type)}` : '—'],
          ['Volume', fmtBig(d.volume)], ['Avg volume', fmtBig(d.avg_volume)], ['Market cap', fmtBig(d.market_cap, d.currency)]].map(([k, v]) => (
          <div key={k}><dt className="text-text-tertiary">{k}</dt><dd className="font-mono text-text-primary">{v}</dd></div>
        ))}
      </dl>
    </div>
  );
}

export function Chart({ symbol, height = 380 }: { symbol: string; height?: number }) {
  return (
    <div className="bg-surface-1 border border-border p-2">
      <PriceChart key={symbol} symbol={symbol} height={height} />
    </div>
  );
}

export function Profile({ symbol }: { symbol: string }) {
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

// per-share lines keep two decimals; everything else in K / M / B
const fmtCell = (item: string, v: number | null | undefined) => (v == null ? '—' : /EPS|per share/i.test(item) ? v.toFixed(2) : fmtBig(v));

const ROWS: [string, string][] = [['revenue', 'Revenue'], ['gross_profit', 'Gross profit'], ['operating_income', 'Operating income'],
  ['net_income', 'Net income'], ['eps_diluted', 'EPS (diluted)'], ['operating_cash_flow', 'Operating cash flow'], ['capex', 'Capex'],
  ['free_cash_flow', 'Free cash flow'], ['total_assets', 'Total assets'], ['total_liabilities', 'Total liabilities'], ['equity', 'Equity'],
  ['cash', 'Cash'], ['long_term_debt', 'Long-term debt']];

function RatioTiles({ r }: { r: Record<string, number | null> }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
      {[['Gross margin', r.gross_margin], ['Operating margin', r.operating_margin], ['Net margin', r.net_margin], ['FCF margin', r.fcf_margin],
        ['ROE', r.roe], ['ROA', r.roa], ['Debt / equity', r.debt_to_equity, 'x'], ['Current ratio', r.current_ratio, 'x']].map(([k, x, u]) => (
        <div key={k as string} className="px-2 py-1.5 bg-surface-1 border border-border">
          <div className="text-[10px] uppercase text-text-tertiary">{k}</div>
          <div className="font-mono text-xs text-text-primary">{x == null ? '—' : u === 'x' ? `${(x as number).toFixed(2)}×` : fmtPct(x as number, 1)}</div>
        </div>))}
    </div>
  );
}

const FA_PERIOD_KEY = 'mkt_fa_period';
type FaPeriod = 'annual' | 'quarterly';

function PeriodToggle({ period, setPeriod }: { period: FaPeriod; setPeriod: (p: FaPeriod) => void }) {
  return (
    <div className="inline-flex border border-border" role="group" aria-label="Statement period">
      {(['annual', 'quarterly'] as const).map((p) => (
        <button key={p} onClick={() => setPeriod(p)} aria-pressed={period === p}
          className={cn('px-2.5 py-0.5 text-[11px] capitalize', period === p ? 'bg-bloomberg text-black font-semibold' : 'text-text-secondary hover:text-text-primary')}>{p}</button>))}
    </div>
  );
}

const YAHOO_TABLES: Record<FaPeriod, [string, string][]> = {
  annual: [['income', 'Income statement'], ['balance', 'Balance sheet'], ['cashflow', 'Cash flow']],
  quarterly: [['income_q', 'Income statement'], ['balance_q', 'Balance sheet'], ['cashflow_q', 'Cash flow']],
};
// lines that are not flows, so the last four quarters can't be summed into a trailing-twelve-month figure
const NOT_SUMMABLE = /shares|average|rate|per share/i;

export function Financials({ symbol }: { symbol: string }) {
  const [period, setPeriodState] = useState<FaPeriod>(() => {
    try { return localStorage.getItem(FA_PERIOD_KEY) === 'quarterly' ? 'quarterly' : 'annual'; } catch { return 'annual'; }
  });
  const setPeriod = (p: FaPeriod) => { setPeriodState(p); try { localStorage.setItem(FA_PERIOD_KEY, p); } catch { /* storage unavailable */ } };
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/statements/${encodeURIComponent(symbol)}`);
  if (loading && !data) return <Loading label="Loading statements…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  if (data.provider === 'yahoo') {
    // trailing twelve months for the annual flow statements, from the last four reported quarters
    const ttmOf = (qKey: string) => {
      const q = data.tables[qKey];
      if (!q || q.periods.length < 4) return null;
      const span = (Date.parse(q.periods[0]) - Date.parse(q.periods[3])) / 86400000;
      if (span < 250 || span > 300) return null;                       // not four consecutive quarters (e.g. half-yearly reporters)
      const m: Record<string, number> = {};
      for (const r of q.rows) {
        const v = r.values.slice(0, 4);
        if (!NOT_SUMMABLE.test(r.item) && v.every((x: number | null) => x != null)) m[r.item] = v.reduce((a: number, b: number) => a + b, 0);
      }
      return { as_of: q.periods[0], values: m };
    };
    const shown = YAHOO_TABLES[period].filter(([k]) => data.tables[k]);
    const missing = YAHOO_TABLES[period].filter(([k]) => !data.tables[k]).map(([, l]) => l.toLowerCase());
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <PeriodToggle period={period} setPeriod={setPeriod} />
          <span className="text-[10px] text-text-tertiary">Ratios: latest fiscal year{data.currency ? ` · figures in ${data.currency}` : ''}</span>
        </div>
        {data.ratios && <RatioTiles r={data.ratios} />}
        {shown.map(([k, label]) => {
          const t = data.tables[k];
          const ttm = period === 'annual' && k !== 'balance' ? ttmOf(`${k}_q`) : null;
          const hasTtm = ttm && t.periods[0] < ttm.as_of;
          return (
            <Panel key={k} title={`${label} (${period})${data.currency ? ` · ${data.currency}` : ''}`}>
              <div className="overflow-x-auto"><table className="w-full text-2xs font-mono">
                <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Item</th>
                  {hasTtm && <th className="text-right font-normal px-2 text-bloomberg" title={`Last four quarters to ${ttm!.as_of}`}>TTM</th>}
                  {t.periods.map((p: string) => <th key={p} className="text-right font-normal px-2">{period === 'annual' ? `FY ${p.slice(0, 7)}` : p.slice(0, 7)}</th>)}</tr></thead>
                <tbody>{t.rows.slice(0, 40).map((r: any, i: number) => (
                  <tr key={r.item} className={cn('border-t', i === t.key_lines ? 'border-border' : 'border-border-subtle')}>
                    <td className={cn('font-sans pr-2 whitespace-nowrap', i < t.key_lines ? 'text-text-primary' : 'text-text-tertiary')}>{r.item}</td>
                    {hasTtm && <td className="text-right px-2 text-text-primary">{ttm!.values[r.item] != null ? fmtCell(r.item, ttm!.values[r.item]) : ''}</td>}
                    {r.values.map((x: number | null, j: number) => <td key={j} className="text-right px-2">{fmtCell(r.item, x)}</td>)}</tr>))}</tbody>
              </table></div>
            </Panel>);
        })}
        {missing.length > 0 && <p className="text-[11px] text-text-tertiary">
          {period === 'quarterly' ? `This company doesn't publish a quarterly ${missing.join(' or ')} (many Hong Kong, UK and European companies report half-yearly).` : `No annual ${missing.join(' or ')} available.`}</p>}
        <div className="text-[10px] text-text-tertiary">{data.source}{period === 'annual' ? '. TTM = sum of the last four reported quarters, where the company reports quarterly.' : ''}</div>
      </div>
    );
  }
  const rows = [...((period === 'annual' ? data.annual : data.quarterly) as any[])].reverse();      // newest first
  const r = data.ratios ?? {};
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <PeriodToggle period={period} setPeriod={setPeriod} />
        <span className="text-[10px] text-text-tertiary">Ratios: trailing twelve months</span>
      </div>
      <RatioTiles r={r} />
      <Panel title={`SEC filings, as filed (${period}) · TTM to ${data.ttm?.as_of ?? '—'}`}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal">USD</th>
            {period === 'annual' && <th className="text-right font-normal px-2 text-bloomberg" title={`Last four quarters to ${data.ttm?.as_of ?? '—'}`}>TTM</th>}
            {rows.map((x) => <th key={x.period_end} className="text-right font-normal px-2">{period === 'annual' ? `FY ${x.period_end.slice(0, 7)}` : x.period_end.slice(0, 7)}</th>)}</tr></thead>
          <tbody>{ROWS.filter(([k]) => rows.some((x) => x[k] != null)).map(([k, label]) => (
            <tr key={k} className="border-t border-border-subtle"><td className="text-text-secondary font-sans pr-2 whitespace-nowrap">{label}</td>
              {period === 'annual' && <td className="text-right px-2 text-text-primary" title={data.ttm?.[k] == null && data.balance?.[k] != null ? `Latest balance sheet, ${data.balance_as_of}` : undefined}>
                {k === 'eps_diluted' ? (data.ttm?.[k]?.toFixed(2) ?? '') : fmtBig(data.ttm?.[k] ?? data.balance?.[k])}</td>}
              {rows.map((x) => <td key={x.period_end} className="text-right px-2">{k === 'eps_diluted' ? (x[k]?.toFixed(2) ?? '—') : fmtBig(x[k])}</td>)}
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

export function News({ symbol }: { symbol: string }) {
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
              <div className="text-[10px] text-text-tertiary">{n.publisher}{n.time ? ` · ${new Date(n.time).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}` : ''}</div>
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

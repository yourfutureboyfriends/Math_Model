// CHART (formula charts), DATA (BDP / BDH grids), OVDV (vol surface), CDR (exchange hours), ILBE (breakevens),
// YAS (Treasuries + bond calculator), FXCA (FX carry), CACS / DVDC (corporate actions), MGMT (management),
// PGEO (segments), DDIS (debt maturities), MRGR (merger arbitrage), MEMB (index members), FSRC (ETF screener).
import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, fmtBig, fmtPrice, Loading, Panel, useJSON } from './shared';

const enc = encodeURIComponent;
const pc = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);
const sp = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(d)}%`);
const bp = (x: number | null | undefined) => (x == null ? '—' : `${x > 0 ? '+' : ''}${Math.round(x)}bp`);
const tone = (x: number | null | undefined) => (x == null ? 'text-text-tertiary' : x >= 0 ? 'text-green' : 'text-red');
const num = (x: number | null | undefined, d = 2) => (x == null ? '—' : Math.abs(x) >= 1e5 ? fmtBig(x) : x.toLocaleString(undefined, { maximumFractionDigits: d }));
const COLORS = ['rgb(var(--c-blue))', 'rgb(var(--c-amber))', 'rgb(var(--c-red))', 'rgb(var(--c-green))', 'rgb(168 85 247)', 'rgb(20 184 166)'];

function Tile({ label, value, sub, cls }: { label: string; value: React.ReactNode; sub?: React.ReactNode; cls?: string }) {
  return (
    <div className="border border-border bg-surface-1 rounded-md px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className={cn('font-mono text-text-primary', cls)}>{value}</div>
      {sub != null && <div className="text-[10px] text-text-tertiary leading-tight">{sub}</div>}
    </div>
  );
}
function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button onClick={onClick} className={cn('px-2 py-0.5 border rounded-sm text-[11px]', on ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{children}</button>;
}
function Frame<T>({ url, label, children, refresh }: { url: string | null; label: string; refresh?: number; children: (d: T) => React.ReactNode }) {
  const { data, error, loading } = useJSON<T>(url, refresh);
  if (!url) return null;
  if (loading && !data) return <Loading label={label} />;
  if (error && !data) return <ErrorBox msg={error} />;
  return data ? <>{children(data)}</> : null;
}
function download(name: string, text: string, type = 'text/csv') {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  a.click();
}
const csvCell = (v: any) => (v == null ? '' : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));

// ── CHART ───────────────────────────────────────────────────────────────────
const G_EXAMPLES = ['AAPL/SPY', '{^TNX}-FRED:DGS2', 'log(XOM)-log(CVX)', 'ma(SPY,200)', 'yoy(FRED:CPIAUCSL)', 'GLD/SLV', 'z(HYG/IEF,252)', 'vol(SPY,21)', 'rebase(QQQ)', '{BTC-USD}/{ETH-USD}'];
const GKEY = 'mkt_chart_v1';

export function ChartView({ seed }: { seed?: string }) {
  const [rows, setRows] = useState<string[]>(() => {
    if (seed) return [seed];
    try { const v = JSON.parse(localStorage.getItem(GKEY) || '[]'); return Array.isArray(v) && v.length ? v : ['AAPL/SPY']; } catch { return ['AAPL/SPY']; }
  });
  const [draft, setDraft] = useState(rows);
  const [period, setPeriod] = useState('5y');
  useEffect(() => { try { localStorage.setItem(GKEY, JSON.stringify(rows)); } catch { /* storage unavailable */ } }, [rows]);
  const url = rows.filter(Boolean).length ? `/api/v1/mkt/g?${rows.filter(Boolean).map((e) => `e=${enc(e)}`).join('&')}&period=${period}` : null;
  const apply = () => setRows(draft.map((x) => x.trim()).filter(Boolean));
  return (
    <div className="space-y-3">
      <Panel title="Formulas — instruments, FRED series (FRED:ID), numbers, + − × ÷ ^ and functions">
        <div className="space-y-1">{draft.map((e, i) => (
          <div key={i} className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: COLORS[i % COLORS.length] }} />
            <input value={e} onChange={(ev) => { const d = [...draft]; d[i] = ev.target.value; setDraft(d); }} onKeyDown={(ev) => ev.key === 'Enter' && apply()}
              className="flex-1 bg-surface-1 border border-border px-2 py-1 text-xs font-mono" placeholder="e.g. AAPL/SPY" />
            {draft.length > 1 && <button onClick={() => setDraft(draft.filter((_, j) => j !== i))} className="px-1.5 text-text-tertiary hover:text-red">✕</button>}
          </div>))}</div>
        <div className="flex flex-wrap items-center gap-1 mt-2 text-[11px]">
          {draft.length < 6 && <button onClick={() => setDraft([...draft, ''])} className="px-2 py-0.5 border border-border text-text-secondary">+ Add line</button>}
          <button onClick={apply} className="px-3 py-0.5 bg-bloomberg text-text-inverse">Chart</button>
          <span className="ml-2 text-text-tertiary">Period</span>{['1y', '2y', '5y', '10y', '20y', 'max'].map((p) => <Chip key={p} on={period === p} onClick={() => setPeriod(p)}>{p}</Chip>)}
        </div>
        <div className="flex flex-wrap gap-1 mt-2 text-[10px]"><span className="text-text-tertiary">Try:</span>{G_EXAMPLES.map((x) => (
          <button key={x} onClick={() => { setDraft([x]); setRows([x]); }} className="font-mono px-1.5 border border-border-subtle rounded-sm text-text-secondary hover:text-bloomberg">{x}</button>))}</div>
        <div className="text-[10px] text-text-tertiary mt-1">Functions: log, exp, abs, sqrt, ma(x,n), ema(x,n), pct(x,n), diff(x,n), lag(x,n), yoy(x), rebase(x), z(x,n), vol(x,n). Put symbols with - or = in braces: {'{BTC-USD}'}, {'{EURUSD=X}'}.</div>
      </Panel>
      <Frame<any> url={url} label="Fetching series and evaluating…">{(d) => (
        <>
          <Panel title="Chart">
            <LineChart rows={d.rows} x="date" height={360} fmt={(v) => num(v, 4)} lines={d.lines.map((l: any, i: number) => ({ key: l.key, label: l.expr, color: COLORS[i % COLORS.length] }))} />
          </Panel>
          <Panel title="Statistics">
            <table className="w-full text-2xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Formula</th><th className="text-right font-normal">Last</th><th className="text-right font-normal">1 month</th>
                <th className="text-right font-normal">1 year</th><th className="text-right font-normal">Range</th><th className="text-right font-normal">Percentile</th><th className="text-right font-normal">As of</th></tr></thead>
              <tbody>{d.lines.map((l: any, i: number) => (
                <tr key={l.key} className="border-t border-border-subtle"><td className="py-1"><span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ background: COLORS[i % COLORS.length] }} />{l.expr}</td>
                  <td className="text-right text-text-primary">{num(l.last, 4)}</td>
                  <td className={cn('text-right', tone(l.m1 != null ? l.last - l.m1 : null))}>{l.m1 != null ? num(l.last - l.m1, 4) : '—'}</td>
                  <td className={cn('text-right', tone(l.y1 != null ? l.last - l.y1 : null))}>{l.y1 != null ? num(l.last - l.y1, 4) : '—'}</td>
                  <td className="text-right text-text-secondary">{num(l.min, 3)} – {num(l.max, 3)}</td><td className="text-right">{Math.round(l.percentile * 100)}th</td>
                  <td className="text-right text-text-tertiary">{l.date}</td></tr>))}</tbody>
            </table>
            <div className="text-[10px] text-text-tertiary mt-1">Changes are in the formula’s own units. {d.note}</div>
          </Panel>
        </>)}</Frame>
    </div>
  );
}

// ── DATA (BDP / BDH) ────────────────────────────────────────────────────────
const DKEY = 'mkt_data_v1';
export function DataView({ seed }: { seed?: string }) {
  const saved = (() => { try { return JSON.parse(localStorage.getItem(DKEY) || 'null'); } catch { return null; } })();
  const [syms, setSyms] = useState<string>(seed ?? saved?.syms ?? 'AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, XOM, 7203.T, SAP.DE, 0700.HK');
  const [fields, setFields] = useState<string[]>(saved?.fields ?? ['name', 'price', 'change_pct', 'market_cap', 'pe', 'forward_pe', 'div_yield', 'beta', 'sector']);
  const [tab, setTab] = useState<'bdp' | 'bdh'>('bdp');
  const [period, setPeriod] = useState('1y'), [interval, setInterval_] = useState('1d'), [field, setField] = useState('close');
  const [go, setGo] = useState(0);
  useEffect(() => { try { localStorage.setItem(DKEY, JSON.stringify({ syms, fields })); } catch { /* storage unavailable */ } }, [syms, fields]);
  const list = syms.split(/[\s,;]+/).map((s) => s.trim().toUpperCase()).filter(Boolean);
  const bdp = useJSON<any>(tab === 'bdp' && list.length ? `/api/v1/mkt/bdp?symbols=${enc(list.join(','))}&fields=${enc(fields.join(','))}&_=${go}` : null);
  const bdh = useJSON<any>(tab === 'bdh' && list.length ? `/api/v1/mkt/bdh?symbols=${enc(list.slice(0, 50).join(','))}&period=${period}&interval=${interval}&field=${field}&_=${go}` : null);
  const catalogue: { key: string; label: string }[] = bdp.data?.catalogue ?? [];
  const exportBdp = (sep: string) => {
    const d = bdp.data; if (!d) return '';
    return [['Symbol', ...d.fields.map((f: any) => f.label)].join(sep), ...d.rows.map((r: any) => [r.symbol, ...d.fields.map((f: any) => r[f.key])].map(csvCell).join(sep))].join('\n');
  };
  const exportBdh = () => {
    const d = bdh.data; if (!d) return '';
    return [['Date', ...d.symbols].join(','), ...d.rows.map((r: any) => [r.date, ...d.symbols.map((s: string) => r[s])].map(csvCell).join(','))].join('\n');
  };
  return (
    <div className="space-y-3">
      <Panel title="Instruments (up to 100 — any market)" right={<div className="flex gap-1"><Chip on={tab === 'bdp'} onClick={() => setTab('bdp')}>Current data (BDP)</Chip><Chip on={tab === 'bdh'} onClick={() => setTab('bdh')}>History (BDH)</Chip></div>}>
        <textarea value={syms} onChange={(e) => setSyms(e.target.value)} rows={2} className="w-full bg-surface-1 border border-border px-2 py-1 text-xs font-mono" />
        {tab === 'bdp' && catalogue.length > 0 && <div className="flex flex-wrap gap-1 mt-1">{catalogue.map((f) => (
          <Chip key={f.key} on={fields.includes(f.key)} onClick={() => setFields(fields.includes(f.key) ? fields.filter((x) => x !== f.key) : [...fields, f.key])}>{f.label}</Chip>))}</div>}
        {tab === 'bdh' && <div className="flex flex-wrap items-center gap-1 mt-1 text-[11px]">
          <span className="text-text-tertiary">Period</span>{['1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max'].map((p) => <Chip key={p} on={period === p} onClick={() => setPeriod(p)}>{p}</Chip>)}
          <span className="ml-2 text-text-tertiary">Interval</span>{[['1d', 'Daily'], ['1wk', 'Weekly'], ['1mo', 'Monthly']].map(([k, l]) => <Chip key={k} on={interval === k} onClick={() => setInterval_(k)}>{l}</Chip>)}
          <span className="ml-2 text-text-tertiary">Field</span>{[['close', 'Adjusted close'], ['return', 'Daily return %'], ['volume', 'Volume']].map(([k, l]) => <Chip key={k} on={field === k} onClick={() => setField(k)}>{l}</Chip>)}</div>}
        <div className="flex gap-2 mt-2 text-[11px]"><button onClick={() => setGo(go + 1)} className="px-3 py-0.5 bg-bloomberg text-text-inverse">Refresh</button>
          {tab === 'bdp' && bdp.data && <><button onClick={() => download('data.csv', exportBdp(','))} className="px-2 border border-border">Download CSV</button>
            <button onClick={() => navigator.clipboard.writeText(exportBdp('\t'))} className="px-2 border border-border" title="Paste straight into Excel or Sheets">Copy for Excel</button></>}
          {tab === 'bdh' && bdh.data && <button onClick={() => download(`history_${period}_${interval}.csv`, exportBdh())} className="px-2 border border-border">Download CSV</button>}</div>
      </Panel>
      {tab === 'bdp' && (bdp.loading && !bdp.data ? <Loading label="Pulling fields…" /> : bdp.error && !bdp.data ? <ErrorBox msg={bdp.error} /> : bdp.data && (
        <Panel title={`${bdp.data.rows.length} instruments × ${bdp.data.fields.length} fields`}>
          <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Symbol</th>{bdp.data.fields.map((f: any) => <th key={f.key} className="text-right font-normal px-1.5">{f.label}</th>)}</tr></thead>
            <tbody>{bdp.data.rows.map((r: any) => (
              <tr key={r.symbol} className="border-t border-border-subtle"><td className="py-1 text-text-primary">{r.symbol}</td>
                {r.error ? <td colSpan={bdp.data.fields.length} className="text-red font-sans">{r.error}</td> : bdp.data.fields.map((f: any) => (
                  <td key={f.key} className={cn('text-right px-1.5', typeof r[f.key] === 'string' && 'font-sans text-text-secondary', f.key === 'change_pct' && tone(r[f.key]))}>
                    {typeof r[f.key] === 'number' ? num(r[f.key]) : r[f.key] ?? '—'}</td>))}</tr>))}</tbody>
          </table></div>
        </Panel>))}
      {tab === 'bdh' && (bdh.loading && !bdh.data ? <Loading label="Downloading history…" /> : bdh.error && !bdh.data ? <ErrorBox msg={bdh.error} /> : bdh.data && (
        <Panel title={`${bdh.data.rows.length} rows — newest first`}>
          {bdh.data.missing.length > 0 && <div className="text-2xs text-amber mb-1">No data: {bdh.data.missing.join(', ')}</div>}
          <div className="overflow-auto max-h-[60vh]"><table className="w-full text-2xs font-mono tabular-nums">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Date</th>{bdh.data.symbols.map((s: string) => <th key={s} className="text-right font-normal px-1.5">{s}</th>)}</tr></thead>
            <tbody>{bdh.data.rows.slice(0, 600).map((r: any) => (
              <tr key={r.date} className="border-t border-border-subtle"><td className="py-0.5 text-text-secondary">{r.date}</td>
                {bdh.data.symbols.map((s: string) => <td key={s} className={cn('text-right px-1.5', field === 'return' && tone(r[s]))}>{num(r[s], field === 'volume' ? 0 : 4)}</td>)}</tr>))}</tbody>
          </table></div>
          <div className="text-[10px] text-text-tertiary mt-1">{bdh.data.note} The download has every row.</div>
        </Panel>))}
    </div>
  );
}

// ── OVDV ────────────────────────────────────────────────────────────────────
export function OvdvView({ symbol }: { symbol: string }) {
  return (
    <Frame<any> url={`/api/v1/mkt/ovdv/${enc(symbol)}`} label="Solving implied vols across the option chain…" refresh={900_000}>{(d) => {
      const vols = d.surface.flatMap((r: any) => d.moneyness.map((m: string) => r[m])).filter((x: any) => x != null);
      const lo = Math.min(...vols), hi = Math.max(...vols);
      const heat = (v: number | null) => (v == null ? 'transparent' : `rgb(var(--c-red) / ${0.08 + 0.6 * ((v - lo) / (hi - lo || 1))})`);
      const smileRows = (() => {
        const ms = [...new Set(d.smiles.flatMap((s: any) => s.points.map((p: any) => p.m.toFixed(3))))].sort();
        return ms.map((m: any) => ({ m, ...Object.fromEntries(d.smiles.map((s: any, i: number) => [`s${i}`, s.points.find((p: any) => p.m.toFixed(3) === m)?.iv ?? null])) }));
      })();
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
            <Tile label="30-day implied vol" value={pc(d.iv30)} sub={d.option_root !== d.symbol ? `options on ${d.option_root}` : 'at the money'} />
            <Tile label="Realised vol (20d)" value={pc(d.rv20)} sub={`60-day ${pc(d.rv60)}`} />
            <Tile label="Vol risk premium" value={d.vrp != null ? `${d.vrp >= 0 ? '+' : ''}${(d.vrp * 100).toFixed(1)} pts` : '—'} cls={tone(d.vrp)} sub="implied − realised" />
            <Tile label="Skew (90% − 110%)" value={d.skew30 != null ? `${(d.skew30 * 100).toFixed(1)} pts` : '—'} sub="downside protection premium" />
            <Tile label="Term structure" value={d.contango != null ? (d.contango > 0.005 ? 'Upward' : d.contango < -0.005 ? 'Inverted' : 'Flat') : '—'} cls={d.contango != null && d.contango < -0.005 ? 'text-red' : ''} sub="inverted = stress now" />
            <Tile label="IV rank" value={d.iv_rank != null ? `${Math.round(d.iv_rank * 100)}` : '—'} sub={d.iv_rank != null ? `percentile ${Math.round(d.iv_percentile * 100)}` : `building history (${d.history_days} days)`} />
            <Tile label="Spot" value={fmtPrice(d.spot)} />
          </div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <Panel title="Term structure — at-the-money vol and skew by expiry">
              <LineChart rows={d.term.map((t: any) => ({ date: t.expiry, atm: t.atm != null ? t.atm * 100 : null, skew: t.skew != null ? t.skew * 100 : null }))} x="date" height={220} controls={false} fmt={(v) => v.toFixed(1)}
                lines={[{ key: 'atm', label: 'ATM vol %', color: 'rgb(var(--c-blue))' }, { key: 'skew', label: 'Skew (pts)', color: 'rgb(var(--c-amber))' }]} />
            </Panel>
            <Panel title="Smile — vol by moneyness (strike ÷ spot)">
              <LineChart rows={smileRows} x="m" height={220} controls={false} fmt={(v) => `${(v * 100).toFixed(1)}%`}
                lines={d.smiles.map((s: any, i: number) => ({ key: `s${i}`, label: `${s.expiry} (${s.dte}d)`, color: COLORS[i % COLORS.length] }))} />
            </Panel>
          </div>
          <Panel title="Volatility surface — implied vol by expiry (rows) and moneyness (columns)">
            <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Expiry</th><th className="text-right font-normal pr-2">Days</th>
                {d.moneyness.map((m: string) => <th key={m} className={cn('text-right font-normal px-1', m === '1.000' && 'text-bloomberg')}>{Math.round(Number(m) * 100)}%</th>)}</tr></thead>
              <tbody>{d.surface.map((r: any) => (
                <tr key={r.expiry} className="border-t border-border-subtle"><td className="py-0.5">{r.expiry}</td><td className="text-right pr-2 text-text-tertiary">{r.dte}</td>
                  {d.moneyness.map((m: string) => <td key={m} className="text-right px-1 text-text-primary" style={{ background: heat(r[m]) }}>{r[m] != null ? (r[m] * 100).toFixed(1) : ''}</td>)}</tr>))}</tbody>
            </table></div>
            <div className="text-[10px] text-text-tertiary mt-1">Darker = higher implied vol. {d.note}</div>
          </Panel>
          {d.history.length > 1 && <Panel title="Recorded 30-day implied vs realised vol">
            <LineChart rows={d.history.map((h: any) => ({ date: h.date, iv: h.iv30 * 100, rv: h.rv20 * 100 }))} x="date" height={180} controls={false} fmt={(v) => v.toFixed(1)}
              lines={[{ key: 'iv', label: 'Implied 30d', color: 'rgb(var(--c-blue))' }, { key: 'rv', label: 'Realised 20d', color: 'rgb(var(--c-amber))' }]} /></Panel>}
          <div className="text-[10px] text-text-tertiary">Source: {d.source}.</div>
        </div>);
    }}</Frame>
  );
}

// ── CDR ─────────────────────────────────────────────────────────────────────
export function CdrView() {
  const [tick, setTick] = useState(0);
  useEffect(() => { const t = setInterval(() => setTick((x) => x + 1), 60_000); return () => clearInterval(t); }, []);
  const hm = (m: number | null) => (m == null ? '—' : m >= 1440 ? `${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h` : `${Math.floor(m / 60)}h ${m % 60}m`);
  return (
    <Frame<any> url={`/api/v1/mkt/cdr?_=${tick}`} label="Checking exchange calendars…">{(d) => (
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Tile label="Open now" value={d.exchanges.filter((x: any) => x.status === 'open').length} cls="text-green" sub={`of ${d.exchanges.length} exchanges`} />
          <Tile label="Lunch break" value={d.exchanges.filter((x: any) => x.status === 'lunch break').length} />
          <Tile label="Holiday today" value={d.exchanges.filter((x: any) => x.holidays[0]?.date === d.now_utc.slice(0, 10)).map((x: any) => x.code).join(', ') || 'none'} />
          <Tile label="UTC" value={d.now_utc.slice(11, 16)} sub={d.now_utc.slice(0, 10)} />
        </div>
        <Panel title="Exchanges — regular trading sessions in local time">
          <table className="w-full text-2xs"><thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Exchange</th><th className="text-left font-normal">Local time</th>
            <th className="text-left font-normal">Sessions</th><th className="text-left font-normal">Status</th><th className="text-right font-normal">Closes / opens in</th><th className="text-left font-normal pl-3">Next holidays</th></tr></thead>
            <tbody>{d.exchanges.map((x: any) => (
              <tr key={x.code} className="border-t border-border-subtle"><td className="py-1"><span className="text-text-primary">{x.name}</span> <span className="text-text-tertiary">{x.city}</span></td>
                <td className="font-mono">{x.local_time} <span className="text-text-tertiary">UTC{x.utc_offset_h >= 0 ? '+' : ''}{x.utc_offset_h}</span></td>
                <td className="font-mono text-text-secondary">{x.sessions.join(', ')}</td>
                <td><span className={cn('px-1.5 rounded-sm text-[10px] font-semibold', x.status === 'open' ? 'bg-green/15 text-green' : x.status === 'lunch break' ? 'bg-amber/15 text-amber' : 'bg-surface-3 text-text-tertiary')}>{x.status}</span></td>
                <td className="text-right font-mono">{x.status === 'open' ? `closes ${hm(x.closes_in_min)}` : `opens ${hm(x.opens_in_min)}`}</td>
                <td className="pl-3 text-text-tertiary">{x.holidays.slice(0, 2).map((h: any) => `${h.date.slice(5)} ${h.name}`).join(' · ') || (x.holiday_calendar ? 'none in 60 days' : 'calendar not covered')}</td></tr>))}</tbody></table>
          <div className="text-[10px] text-text-tertiary mt-1">{d.note}</div>
        </Panel>
      </div>)}</Frame>
  );
}

// ── ILBE ────────────────────────────────────────────────────────────────────
export function IlbeView() {
  const [view, setView] = useState<'exp' | 'real'>('exp');
  return (
    <Frame<any> url="/api/v1/mkt/ilbe" label="Loading breakevens and real yields…" refresh={3_600_000}>{(d) => {
      const g = (id: string) => d.series.find((s: any) => s.id === id);
      return (
        <div className="space-y-3">
          {d.signals.length > 0 && <div className="px-3 py-2 border border-border bg-surface-1 rounded-md space-y-1">{d.signals.map((s: string) => <div key={s} className="text-2xs text-text-secondary">• {s}</div>)}</div>}
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-2">
            {['T5YIE', 'T10YIE', 'T5YIFR', 'DFII10', 'EXPINF1YR', 'MICH', 'CPI_YOY'].map((id) => { const s = g(id); return s && (
              <Tile key={id} label={s.name} value={`${s.last.toFixed(2)}%`} sub={<span>{bp(s.chg_1m_bp)} 1m · {bp(s.chg_1y_bp)} 1y · {Math.round(s.percentile_10y * 100)}th pct (10y)</span>} />); })}
          </div>
          <Panel title="History (weekly, %)" right={<div className="flex gap-1"><Chip on={view === 'exp'} onClick={() => setView('exp')}>Inflation expectations</Chip><Chip on={view === 'real'} onClick={() => setView('real')}>Real vs nominal yields</Chip></div>}>
            <LineChart rows={d.history} x="date" height={320} fmt={(v) => `${v.toFixed(2)}%`} defaultRange="5y"
              lines={view === 'exp'
                ? [{ key: 'T5YIE', label: '5y breakeven', color: COLORS[0] }, { key: 'T10YIE', label: '10y breakeven', color: COLORS[1] }, { key: 'T5YIFR', label: '5y5y forward', color: COLORS[4] },
                  { key: 'EXPINF1YR', label: '1y expected (Cleveland Fed)', color: COLORS[5] }, { key: 'CPI_YOY', label: 'CPI actual y/y', color: COLORS[2] }]
                : [{ key: 'DGS10', label: '10y nominal', color: COLORS[0] }, { key: 'DFII10', label: '10y real (TIPS)', color: COLORS[3] }, { key: 'DFII5', label: '5y real', color: COLORS[5] }, { key: 'DFII30', label: '30y real', color: COLORS[4] }]} />
          </Panel>
          <div className="text-[10px] text-text-tertiary">{d.note} Source: {d.source}.</div>
        </div>);
    }}</Frame>
  );
}

// ── YAS: Treasuries and the bond calculator ─────────────────────────────────
function CurveSvg({ curve }: { curve: any }) {
  const pts = [...curve.nominal.map((p: any) => ({ ...p, k: 'n' })), ...curve.real.map((p: any) => ({ ...p, k: 'r' }))];
  if (!pts.length) return null;
  const W = 620, H = 200, P = 30;
  const xs = pts.map((p: any) => p.years), ys = pts.map((p: any) => p.ytm * 100);
  const x0 = 0, x1 = Math.max(...xs), y0 = Math.min(0, Math.min(...ys)), y1 = Math.max(...ys) * 1.08;
  const sx = (v: number) => P + ((v - x0) / (x1 - x0)) * (W - 2 * P), sy = (v: number) => H - P - ((v - y0) / (y1 - y0)) * (H - 2 * P);
  const path = (k: string) => pts.filter((p: any) => p.k === k).map((p: any, i: number) => `${i ? 'L' : 'M'}${sx(p.years)},${sy(p.ytm * 100)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 230 }} role="img" aria-label="Treasury yield curve">
      <line x1={P} x2={W - P} y1={H - P} y2={H - P} stroke="var(--border)" />
      {[0, 5, 10, 20, 30].filter((v) => v <= x1).map((v) => <text key={v} x={sx(v)} y={H - P + 12} fontSize="9" textAnchor="middle" fill="var(--text-tertiary)">{v}y</text>)}
      {[y0, (y0 + y1) / 2, y1].map((v) => <text key={v} x={P - 4} y={sy(v) + 3} fontSize="9" textAnchor="end" fill="var(--text-tertiary)">{v.toFixed(1)}%</text>)}
      <path d={path('n')} fill="none" stroke="rgb(var(--c-blue))" strokeWidth="2" /><path d={path('r')} fill="none" stroke="rgb(var(--c-green))" strokeWidth="2" />
      <text x={W - P} y={sy(curve.nominal[curve.nominal.length - 1]?.ytm * 100 || 0) - 6} fontSize="10" textAnchor="end" fill="rgb(var(--c-blue))">nominal</text>
      <text x={W - P} y={sy(curve.real[curve.real.length - 1]?.ytm * 100 || 0) + 12} fontSize="10" textAnchor="end" fill="rgb(var(--c-green))">real (TIPS)</text>
    </svg>
  );
}

export function YasView() {
  const [kind, setKind] = useState('Note');
  const [form, setForm] = useState({ coupon: '4.25', maturity: '2036-08-15', price: '98.5', ytm: '', settle: '' });
  const [calcUrl, setCalcUrl] = useState<string | null>(null);
  const calc = useJSON<any>(calcUrl);
  const run = (f = form) => {
    const p = new URLSearchParams({ coupon: String(Number(f.coupon) / 100), maturity: f.maturity });
    if (f.ytm) p.set('ytm', String(Number(f.ytm) / 100)); else if (f.price) p.set('price', f.price);
    if (f.settle) p.set('settle', f.settle);
    setCalcUrl(`/api/v1/mkt/yas?${p}`);
  };
  useEffect(() => { run(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-3">
        <Panel title="Bond calculator (YAS) — fixed coupon, street convention">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[10px] uppercase tracking-wide text-text-tertiary">
            {([['coupon', 'Coupon %'], ['maturity', 'Maturity'], ['price', 'Clean price'], ['ytm', 'or yield %'], ['settle', 'Settlement']] as const).map(([k, l]) => (
              <label key={k}>{l}<input value={(form as any)[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value, ...(k === 'ytm' && e.target.value ? { price: '' } : {}), ...(k === 'price' && e.target.value ? { ytm: '' } : {}) })}
                onKeyDown={(e) => e.key === 'Enter' && run()} placeholder={k === 'settle' ? 'today' : ''} type={k === 'maturity' || k === 'settle' ? 'date' : 'text'}
                className="mt-0.5 w-full bg-surface-1 border border-border px-1.5 py-1 text-xs font-mono normal-case text-text-primary" /></label>))}
          </div>
          <button onClick={() => run()} className="mt-2 px-3 py-0.5 text-[11px] bg-bloomberg text-text-inverse">Calculate</button>
          {calc.error && <div className="mt-2"><ErrorBox msg={calc.error} /></div>}
          {calc.data && <>
            <div className="grid grid-cols-3 md:grid-cols-4 gap-2 mt-3">
              <Tile label="Yield to maturity" value={`${(calc.data.ytm * 100).toFixed(3)}%`} /><Tile label="Clean price" value={calc.data.clean.toFixed(4)} sub={`dirty ${calc.data.dirty.toFixed(4)}`} />
              <Tile label="Accrued" value={calc.data.accrued.toFixed(4)} sub={`since ${calc.data.previous_coupon}`} /><Tile label="Current yield" value={pc(calc.data.current_yield, 3)} />
              <Tile label="Modified duration" value={calc.data.modified.toFixed(3)} sub={`Macaulay ${calc.data.macaulay.toFixed(3)}`} /><Tile label="Convexity" value={calc.data.convexity.toFixed(2)} />
              <Tile label="DV01 (per 100)" value={calc.data.dv01.toFixed(4)} sub="price change for 1bp" /><Tile label="Next coupon" value={calc.data.next_coupon} sub={`${calc.data.coupons_left} left`} />
            </div>
            <table className="w-full text-2xs font-mono mt-2"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Yield shift</th><th className="text-right font-normal">Yield</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">Change</th><th className="text-right font-normal">Duration+convexity estimate</th></tr></thead>
              <tbody>{calc.data.grid.map((g: any) => (
                <tr key={g.shift_bp} className={cn('border-t border-border-subtle', g.shift_bp === 0 && 'font-semibold')}><td>{bp(g.shift_bp)}</td><td className="text-right">{(g.yield * 100).toFixed(3)}%</td>
                  <td className="text-right">{g.price.toFixed(3)}</td><td className={cn('text-right', tone(g.change))}>{sp(g.change, 2)}</td><td className="text-right text-text-tertiary">{g.duration_convexity_estimate.toFixed(3)}</td></tr>))}</tbody></table>
          </>}
        </Panel>
        <Frame<any> url="/api/v1/mkt/tsy" label="Pricing every Treasury from TreasuryDirect…">{(d) => (
          <Panel title={`US Treasuries — end-of-day prices ${d.price_date}`} right={<div className="flex gap-1">{['Bill', 'Note', 'Bond', 'Tips', 'Frn'].map((k) => <Chip key={k} on={kind === k} onClick={() => setKind(k)}>{k === 'Tips' ? 'TIPS' : k === 'Frn' ? 'FRN' : `${k}s`} ({d.counts[k]})</Chip>)}</div>}>
            <CurveSvg curve={d.curve} />
            <div className="max-h-[360px] overflow-auto mt-2"><table className="w-full text-2xs font-mono tabular-nums">
              <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal py-1">CUSIP</th><th className="text-right font-normal">Coupon</th><th className="text-right font-normal">Maturity</th>
                <th className="text-right font-normal">Price</th><th className="text-right font-normal">Yield</th><th className="text-right font-normal">Mod. dur.</th><th className="text-right font-normal">DV01</th></tr></thead>
              <tbody>{d.securities.filter((s: any) => s.type === kind).map((s: any) => (
                <tr key={s.cusip} onClick={() => { if (s.type === 'Bill' || s.type === 'Frn') return; const f = { coupon: (s.coupon * 100).toFixed(3), maturity: s.maturity, price: String(s.price), ytm: '', settle: '' }; setForm(f); run(f); }}
                  className={cn('border-t border-border-subtle', s.type !== 'Bill' && s.type !== 'Frn' && 'cursor-pointer hover:bg-surface-2')}>
                  <td className="py-0.5 text-text-secondary">{s.cusip}</td><td className="text-right">{(s.coupon * 100).toFixed(3)}%</td><td className="text-right">{s.maturity}</td>
                  <td className="text-right">{s.price.toFixed(4)}</td><td className="text-right text-text-primary">{s.ytm != null ? `${(s.ytm * 100).toFixed(3)}%` : '—'}</td>
                  <td className="text-right">{s.modified?.toFixed(2) ?? '—'}</td><td className="text-right">{s.dv01?.toFixed(4) ?? '—'}</td></tr>))}</tbody></table></div>
            <div className="text-[10px] text-text-tertiary mt-1">Click a note or bond to load it into the calculator. {d.note}</div>
          </Panel>)}</Frame>
      </div>
    </div>
  );
}

// ── FXCA ────────────────────────────────────────────────────────────────────
export function FxcaView() {
  return (
    <Frame<any> url="/api/v1/mkt/fxca" label="Ranking carry trades…" refresh={3_600_000}>{(d) => {
      const max = Math.max(...d.rows.map((r: any) => Math.abs(r.carry)));
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Tile label="US policy rate (funding)" value={`${d.usd_rate.toFixed(2)}%`} />
            {d.basket && <><Tile label="Carry basket — long" value={d.basket.long.join(' · ')} sub="highest carry" /><Tile label="… funded by" value={d.basket.short.join(' · ')} sub="lowest rates" />
              <Tile label="Basket carry / last year's spot" value={`${pc(d.basket.carry)} / ${sp(d.basket.spot_1y)}`} sub="interest earned / currency move" /></>}
          </div>
          <Panel title="Carry vs the dollar — ranked by carry-to-volatility">
            <table className="w-full text-2xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Currency</th><th className="text-right font-normal">Policy rate</th><th className="text-left font-normal pl-3">Carry vs USD (a year)</th>
                <th className="text-right font-normal">3m vol</th><th className="text-right font-normal">Carry ÷ vol</th><th className="text-right font-normal">Spot 3m</th><th className="text-right font-normal">Spot 1y</th><th className="text-right font-normal">Carry trade 1y</th><th className="text-right font-normal">3m fwd pts</th></tr></thead>
              <tbody>{d.rows.map((r: any) => (
                <tr key={r.ccy} className="border-t border-border-subtle"><td className="py-1 font-sans"><span className="font-mono text-text-primary">{r.ccy}</span> <span className="text-text-tertiary">{r.country}</span></td>
                  <td className="text-right">{r.policy_rate.toFixed(2)}%</td>
                  <td className="pl-3"><div className="flex items-center gap-2"><div className="relative w-28 h-1.5 bg-surface-3 rounded-full"><div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary" />
                    <div className={cn('absolute top-0 bottom-0', r.carry >= 0 ? 'bg-green left-1/2' : 'bg-red')} style={{ width: `${(Math.abs(r.carry) / max) * 50}%`, ...(r.carry < 0 ? { right: '50%' } : {}) }} /></div>
                    <span className={tone(r.carry)}>{sp(r.carry, 2)}</span></div></td>
                  <td className="text-right">{pc(r.vol_3m)}</td><td className={cn('text-right font-semibold', tone(r.carry_to_vol))}>{r.carry_to_vol?.toFixed(2)}</td>
                  <td className={cn('text-right', tone(r.spot_3m))}>{sp(r.spot_3m)}</td><td className={cn('text-right', tone(r.spot_1y))}>{sp(r.spot_1y)}</td>
                  <td className={cn('text-right', tone(r.carry_trade_1y))}>{sp(r.carry_trade_1y)}</td><td className="text-right text-text-tertiary">{r.forward_points_3m.toFixed(1)}</td></tr>))}</tbody></table>
            <div className="text-[10px] text-text-tertiary mt-1">Carry trade 1y = last year’s spot move + carry (approximate total return of holding the currency against the dollar). Managed currencies (low vol, e.g. TRY) can look attractive until a devaluation. {d.note}</div>
          </Panel>
        </div>);
    }}</Frame>
  );
}

// ── CACS / DVDC ─────────────────────────────────────────────────────────────
export function CacsView({ symbol }: { symbol: string }) {
  return (
    <Frame<any> url={`/api/v1/mkt/cacs/${enc(symbol)}`} label="Loading corporate actions…">{(d) => (
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
          <Tile label="Dividend (annual)" value={d.dividend_rate != null ? num(d.dividend_rate, 4) : '—'} sub={d.currency} /><Tile label="Yield" value={pc(d.yield, 2)} />
          <Tile label="Frequency" value={d.frequency ?? '—'} /><Tile label="5-year growth" value={sp(d.growth_5y)} cls={tone(d.growth_5y)} />
          <Tile label="Years of increases" value={d.raise_streak_years} sub="consecutive calendar years" /><Tile label="Payout ratio" value={pc(d.payout_ratio, 0)} />
        </div>
        {d.upcoming.length > 0 && <Panel title="Upcoming / latest">
          <div className="flex flex-wrap gap-2">{d.upcoming.map((u: any) => (
            <div key={u.event + u.date} className={cn('border rounded-md px-3 py-1.5 text-xs', u.past ? 'border-border-subtle text-text-tertiary' : 'border-bloomberg/50 text-text-primary')}>
              <div className="text-[10px] uppercase tracking-wide">{u.event}{u.past ? ' (past)' : ''}</div><div className="font-mono">{u.date}</div>{u.detail && <div className="text-[10px] text-text-tertiary">{u.detail}</div>}</div>))}</div></Panel>}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
          <Panel title="Dividends per year">
            {d.annual.length ? <div className="flex items-end gap-1 h-36">{(() => { const mx = Math.max(...d.annual.map((a: any) => a.total)); return d.annual.map((a: any) => (
              <div key={a.year} className="flex-1 flex flex-col items-center justify-end h-full" title={`${a.year}: ${num(a.total, 4)}`}>
                <div className="w-full bg-blue/70 rounded-t-sm" style={{ height: `${(a.total / mx) * 100}%` }} /><span className="text-[8px] text-text-tertiary mt-0.5">{String(a.year).slice(2)}</span></div>)); })()}</div>
              : <div className="text-2xs text-text-tertiary">No dividends paid.</div>}
          </Panel>
          <Panel title="Payments (ex-date)"><div className="max-h-48 overflow-auto"><table className="w-full text-2xs font-mono"><tbody>{d.dividends.map((p: any) => (
            <tr key={p.ex_date} className="border-t border-border-subtle first:border-0"><td className="py-0.5 text-text-secondary">{p.ex_date}</td><td className="text-right">{num(p.amount, 4)}</td></tr>))}</tbody></table></div></Panel>
          <Panel title="Splits">{d.splits.length ? <table className="w-full text-2xs font-mono"><tbody>{d.splits.map((s: any) => (
            <tr key={s.date} className="border-t border-border-subtle first:border-0"><td className="py-0.5 text-text-secondary">{s.date}</td><td className={cn('text-right', s.ratio < 1 && 'text-red')}>{s.label}</td></tr>))}</tbody></table>
            : <div className="text-2xs text-text-tertiary">No splits on record.</div>}</Panel>
        </div>
        <div className="text-[10px] text-text-tertiary">Source: {d.source}.</div>
      </div>)}</Frame>
  );
}

export function DvdcView({ onOpen }: { onOpen: (s: string) => void }) {
  const [q, setQ] = useState('');
  return (
    <Frame<any> url="/api/v1/mkt/cacs" label="Loading the dividend and split calendars…" refresh={3_600_000}>{(d) => {
      const divs = d.dividends.filter((x: any) => !q || `${x.symbol} ${x.name}`.toLowerCase().includes(q.toLowerCase()));
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] gap-3">
            <Panel title={`Ex-dividend dates ${d.from} → ${d.to} (${d.dividends.length})`} right={<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter…" className="w-40 bg-surface-1 border border-border px-2 py-0.5 text-[11px]" />}>
              <div className="max-h-[560px] overflow-auto"><table className="w-full text-2xs font-mono tabular-nums">
                <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Ex-date</th><th className="text-left font-normal">Company</th><th className="text-right font-normal">Dividend</th><th className="text-right font-normal">Annual</th><th className="text-right font-normal">Pays</th></tr></thead>
                <tbody>{divs.map((x: any, i: number) => (
                  <tr key={i} onClick={() => onOpen(x.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2"><td className="py-0.5">{x.date}</td>
                    <td className="font-sans truncate max-w-[280px]"><span className="font-mono text-text-primary">{x.symbol}</span> <span className="text-text-tertiary">{x.name}</span></td>
                    <td className="text-right">{num(x.amount, 4)}</td><td className="text-right text-text-secondary">{num(x.annual, 2)}</td><td className="text-right text-text-tertiary">{x.pay_date}</td></tr>))}</tbody></table></div>
            </Panel>
            <Panel title="Upcoming splits">{d.splits.length ? <table className="w-full text-2xs font-mono"><tbody>{d.splits.map((s: any, i: number) => (
              <tr key={i} onClick={() => onOpen(s.symbol)} className="border-t border-border-subtle first:border-0 cursor-pointer hover:bg-surface-2"><td className="py-1">{s.date}</td>
                <td className="font-sans"><span className="font-mono text-text-primary">{s.symbol}</span> <span className="text-text-tertiary">{s.name}</span></td><td className="text-right">{s.ratio}</td></tr>))}</tbody></table>
              : <div className="text-2xs text-text-tertiary">None scheduled.</div>}
              <div className="text-[10px] text-text-tertiary mt-2">A ratio like 1 : 10 is a reverse split (ten shares become one).</div></Panel>
          </div>
          <div className="text-[10px] text-text-tertiary">Source: {d.source}. Buy before the ex-date to receive the dividend.</div>
        </div>);
    }}</Frame>
  );
}

// ── MGMT ────────────────────────────────────────────────────────────────────
const RISK_LABEL: Record<string, string> = { overallRisk: 'Overall', boardRisk: 'Board', compensationRisk: 'Pay', shareHolderRightsRisk: 'Shareholder rights', auditRisk: 'Audit' };
export function MgmtView({ symbol }: { symbol: string }) {
  return (
    <Frame<any> url={`/api/v1/mkt/mgmt/${enc(symbol)}`} label="Loading management…">{(d) => (
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
          <Tile label="Employees" value={d.employees ? d.employees.toLocaleString() : '—'} /><Tile label="Held by insiders" value={pc(d.held_by_insiders)} /><Tile label="Held by institutions" value={pc(d.held_by_institutions)} />
          {Object.entries<any>(d.risk).filter(([, v]) => v != null).map(([k, v]) => (
            <Tile key={k} label={`${RISK_LABEL[k] ?? k} risk`} value={`${v}/10`} cls={v >= 7 ? 'text-red' : v <= 3 ? 'text-green' : ''} sub={v >= 7 ? 'high' : v <= 3 ? 'low' : 'medium'} />))}
        </div>
        <Panel title={`Officers — total disclosed pay ${d.total_disclosed_pay ? `${fmtBig(d.total_disclosed_pay)} ${d.pay_currency ?? 'USD'}` : '—'}`}>
          <table className="w-full text-2xs"><thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Name</th><th className="text-left font-normal">Title</th><th className="text-right font-normal">Age</th><th className="text-right font-normal">Pay</th><th className="text-right font-normal">Options exercised</th></tr></thead>
            <tbody>{d.people.map((p: any) => (
              <tr key={p.name + p.title} className="border-t border-border-subtle"><td className="py-1 text-text-primary">{p.name}</td><td className="text-text-secondary">{p.title}</td>
                <td className="text-right font-mono">{p.age ?? '—'}</td><td className="text-right font-mono">{p.pay ? `${fmtBig(p.pay)} ${d.pay_currency ?? 'USD'}` : '—'}</td><td className="text-right font-mono text-text-tertiary">{p.exercised ? `${fmtBig(p.exercised)} ${d.pay_currency ?? 'USD'}` : '—'}</td></tr>))}</tbody></table>
          <div className="text-[10px] text-text-tertiary mt-1">{d.note}</div>
        </Panel>
        {d.insiders?.rows?.length > 0 && <Panel title="Insider trades (Form 4)">
          <table className="w-full text-2xs"><tbody>{d.insiders.rows.map((r: any, i: number) => (
            <tr key={i} className="border-t border-border-subtle first:border-0"><td className="py-0.5 font-mono text-text-secondary">{r.date ?? r.filed}</td><td className="text-text-primary">{r.owner ?? r.insider}</td>
              <td className="text-text-tertiary">{r.role}</td><td className={cn('text-right', r.direction === 'buy' ? 'text-green' : r.direction === 'sell' ? 'text-red' : 'text-text-tertiary')}>{r.type ?? r.code}{r.plan_10b5_1 ? ' (10b5-1 plan)' : ''}</td>
              <td className="text-right font-mono">{r.shares ? num(r.shares, 0) : ''}</td><td className="text-right font-mono">{r.value ? `$${fmtBig(r.value)}` : ''}</td></tr>))}</tbody></table>
        </Panel>}
        <div className="text-[10px] text-text-tertiary">Source: {d.source}.</div>
      </div>)}</Frame>
  );
}

// ── PGEO ────────────────────────────────────────────────────────────────────
export function PgeoView({ symbol }: { symbol: string }) {
  return (
    <Frame<any> url={`/api/v1/mkt/pgeo/${enc(symbol)}`} label="Reading segment data from the annual report…">{(d) => {
      const ly = d.years[d.years.length - 1];
      return (
        <div className="space-y-3">
          <div className="text-2xs text-text-secondary">From the {d.form} filed {d.filed} (fiscal year to {ly}). Total revenue <span className="font-mono text-text-primary">${fmtBig(d.total_revenue[ly])}</span>.</div>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
            {Object.entries<any[]>(d.breakdowns).map(([name, rows]) => (
              <Panel key={name} title={name}>
                <table className="w-full text-2xs font-mono tabular-nums">
                  <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Line</th><th className="text-left font-normal pl-2">Share of revenue</th>
                    {d.years.map((y: string) => <th key={y} className="text-right font-normal">FY{y.slice(0, 4)}</th>)}<th className="text-right font-normal">Growth</th><th className="text-right font-normal">Op. margin</th></tr></thead>
                  <tbody>{rows.map((r: any) => (
                    <tr key={r.member} className="border-t border-border-subtle"><td className="py-1 font-sans text-text-primary">{r.name}</td>
                      <td className="pl-2"><div className="flex items-center gap-1.5"><div className="w-20 h-1.5 bg-surface-3 rounded-full overflow-hidden"><div className="h-full bg-blue" style={{ width: `${Math.min(100, (r.share ?? 0) * 100)}%` }} /></div><span>{pc(r.share, 0)}</span></div></td>
                      {d.years.map((y: string) => <td key={y} className="text-right">{r.revenue[y] != null ? fmtBig(r.revenue[y]) : '—'}</td>)}
                      <td className={cn('text-right', tone(r.growth))}>{sp(r.growth)}</td><td className="text-right">{pc(r.margin)}</td></tr>))}</tbody></table>
              </Panel>))}
          </div>
          <div className="text-[10px] text-text-tertiary">{d.note} Source: {d.source}.</div>
        </div>);
    }}</Frame>
  );
}

// ── DDIS ────────────────────────────────────────────────────────────────────
export function DdisView({ symbol }: { symbol: string }) {
  return (
    <Frame<any> url={`/api/v1/mkt/ddis/${enc(symbol)}`} label="Reading the debt maturity schedule…">{(d) => {
      const mx = Math.max(...d.ladder.map((x: any) => x.amount));
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
            <Tile label="Scheduled principal" value={`$${fmtBig(d.total_scheduled)}`} sub={`as of ${d.as_of}`} /><Tile label="Due within 2 years" value={`$${fmtBig(d.due_2y)}`} />
            <Tile label="Cash covers 2 years" value={d.cash_covers_2y != null ? `${d.cash_covers_2y.toFixed(2)}×` : '—'} cls={d.cash_covers_2y != null && d.cash_covers_2y < 1 ? 'text-amber' : ''} />
            <Tile label="Cash" value={d.cash ? `$${fmtBig(d.cash)}` : '—'} /><Tile label="Interest cover" value={d.interest_cover != null ? `${d.interest_cover.toFixed(1)}×` : '—'} sub="EBITDA ÷ interest" />
            <Tile label="Net debt / EBITDA" value={d.net_debt_to_ebitda != null ? `${d.net_debt_to_ebitda.toFixed(2)}×` : '—'} />
          </div>
          <Panel title="Maturity ladder">
            <div className="flex items-end gap-3 h-48 px-2">{d.ladder.map((x: any) => (
              <div key={x.bucket} className="flex-1 flex flex-col items-center justify-end h-full">
                <span className="text-[10px] font-mono text-text-secondary mb-0.5">${fmtBig(x.amount)}</span>
                <div className={cn('w-full rounded-t-sm', x.bucket === 'Year 1' || x.bucket === 'Year 2' ? 'bg-amber/80' : 'bg-blue/70')} style={{ height: `${(x.amount / mx) * 85}%` }} />
                <span className="text-[10px] text-text-tertiary mt-1">{x.bucket}</span></div>))}</div>
            <div className="text-[10px] text-text-tertiary mt-1">{d.note} Source: {d.source}.</div>
          </Panel>
        </div>);
    }}</Frame>
  );
}

// ── MRGR ────────────────────────────────────────────────────────────────────
export function MrgrView({ onOpen }: { onOpen: (s: string) => void }) {
  const [all, setAll] = useState(false);
  return (
    <Frame<any> url="/api/v1/mkt/ma" label="Searching EDGAR for merger agreements…" refresh={3_600_000}>{(d) => {
      const rows = d.deals.filter((x: any) => all || x.status === 'pending');
      return (
        <div className="space-y-3">
          <Panel title={`Announced US mergers since ${d.from} — ${rows.length} ${all ? '' : 'pending'}`} right={<label className="text-[11px] text-text-secondary"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> include completed</label>}>
            <table className="w-full text-2xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Target</th><th className="text-left font-normal">Buyer</th><th className="text-right font-normal">Announced</th>
                <th className="text-right font-normal">Offer</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">Spread</th><th className="text-right font-normal">Expected close</th><th className="text-right font-normal">Annualised</th><th className="text-right font-normal">Status</th><th /></tr></thead>
              <tbody>{rows.map((x: any) => (
                <tr key={x.ticker + x.filed} className="border-t border-border-subtle">
                  <td className="py-1 font-sans"><button onClick={() => onOpen(x.ticker)} className="hover:underline"><span className="font-mono text-text-primary">{x.ticker}</span> <span className="text-text-secondary">{x.name}</span></button></td>
                  <td className="font-sans text-text-secondary truncate max-w-[220px]">{x.counterparty ?? '—'}</td><td className="text-right text-text-tertiary">{x.filed}</td>
                  <td className="text-right text-text-primary">{x.cash_per_share != null ? `$${x.cash_per_share.toFixed(2)}` : x.stock_ratio ? `${x.stock_ratio} sh` : '—'}{x.cvr && <span className="text-amber font-sans" title="Plus a contingent value right — extra payment if a milestone is met"> +CVR</span>}</td>
                  <td className="text-right">{x.price != null ? `$${x.price.toFixed(2)}` : '—'}</td>
                  <td className={cn('text-right font-semibold', x.spread == null ? '' : x.spread > 0.05 ? 'text-amber' : x.spread < 0 ? 'text-text-secondary' : 'text-green')}>{x.spread != null ? sp(x.spread, 2) : '—'}</td>
                  <td className="text-right text-text-tertiary">{x.expected_close ?? '—'}</td><td className="text-right">{x.annualized != null ? sp(x.annualized) : '—'}</td>
                  <td className="text-right font-sans text-text-tertiary">{x.status}</td><td className="pl-2"><a href={x.url} target="_blank" rel="noreferrer" className="text-bloomberg font-sans hover:underline">filing</a></td></tr>))}</tbody></table>
            <div className="text-[10px] text-text-tertiary mt-1">{d.note} Scanned {d.scanned} filings. Source: {d.source}.</div>
          </Panel>
        </div>);
    }}</Frame>
  );
}

// ── MEMB ────────────────────────────────────────────────────────────────────
export function MembView({ seed, onOpen }: { seed?: string; onOpen: (s: string) => void }) {
  const [code, setCode] = useState((seed ?? 'SPX').toUpperCase());
  const [q, setQ] = useState('');
  return (
    <Frame<any> url={`/api/v1/mkt/memb/${enc(code)}`} label="Loading constituents…">{(d) => {
      const rows = d.members.filter((m: any) => !q || `${m.symbol} ${m.name} ${m.sector ?? ''}`.toLowerCase().includes(q.toLowerCase()));
      const mx = Math.max(0.0001, ...d.members.map((m: any) => m.weight ?? 0));
      return (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-1">{d.indices.map((i: any) => <Chip key={i.code} on={code === i.code} onClick={() => setCode(i.code)}>{i.name}</Chip>)}
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter…" className="ml-auto w-48 bg-surface-1 border border-border px-2 py-0.5 text-[11px]" /></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Tile label="Members" value={d.count} /><Tile label="Top 10 weight" value={pc(d.top10_weight)} /><Tile label="Effective number of stocks" value={d.effective_n?.toFixed(0) ?? '—'} sub="1 ÷ Σ weight²" />
            <Tile label="Largest" value={d.members[0]?.symbol} sub={d.members[0]?.weight != null ? pc(d.members[0].weight, 2) : ''} />
          </div>
          {d.note && <div className="text-2xs text-text-tertiary">{d.note}</div>}
          <Panel title={`${d.name} constituents`}>
            <div className="max-h-[600px] overflow-auto"><table className="w-full text-2xs"><thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-right font-normal pr-2">#</th><th className="text-left font-normal py-1">Company</th><th className="text-left font-normal">Sector</th><th className="text-left font-normal pl-2">Weight</th></tr></thead>
              <tbody>{rows.map((m: any, i: number) => (
                <tr key={m.symbol + i} onClick={() => onOpen(m.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2">
                  <td className="text-right pr-2 text-text-tertiary font-mono">{i + 1}</td><td className="py-0.5"><span className="font-mono text-text-primary">{m.symbol}</span> <span className="text-text-secondary">{m.name}</span></td>
                  <td className="text-text-tertiary">{m.sector ?? ''}</td>
                  <td className="pl-2">{m.weight != null ? <div className="flex items-center gap-1.5"><div className="w-32 h-1.5 bg-surface-3 rounded-full overflow-hidden"><div className="h-full bg-blue" style={{ width: `${(m.weight / mx) * 100}%` }} /></div><span className="font-mono">{pc(m.weight, 2)}</span></div> : <span className="text-text-tertiary">—</span>}</td></tr>))}</tbody></table></div>
            <div className="text-[10px] text-text-tertiary mt-1">Source: {d.source}.</div>
          </Panel>
        </div>);
    }}</Frame>
  );
}

// ── FSRC ────────────────────────────────────────────────────────────────────
export function FsrcView({ onOpen }: { onOpen: (s: string) => void }) {
  const [group, setGroup] = useState('All');
  const [sort, setSort] = useState<string>('aum');
  const [maxEr, setMaxEr] = useState<number | null>(null);
  const [a, setA] = useState('SPY'), [b, setB] = useState('XLK');
  const [cmp, setCmp] = useState<[string, string] | null>(null);
  const screen = useJSON<any>('/api/v1/mkt/fsrc', 3_600_000);
  const comp = useJSON<any>(cmp ? `/api/v1/mkt/fsrc/compare?a=${enc(cmp[0])}&b=${enc(cmp[1])}` : null);
  const rows = useMemo(() => (screen.data?.funds ?? []).filter((f: any) => (group === 'All' || f.group === group) && (maxEr == null || (f.expense ?? 1) <= maxEr))
    .sort((x: any, y: any) => (sort === 'expense' ? (x.expense ?? 9) - (y.expense ?? 9) : (y[sort] ?? -1e18) - (x[sort] ?? -1e18))), [screen.data, group, sort, maxEr]);
  const cols: [string, string, (v: any) => string][] = [['aum', 'Assets', (v) => (v ? `$${fmtBig(v)}` : '—')], ['expense', 'Expense', (v) => pc(v, 2)], ['yield', 'Yield', (v) => pc(v, 2)],
    ['ytd', 'YTD', (v) => sp(v)], ['r3y', '3y avg', (v) => sp(v)], ['r5y', '5y avg', (v) => sp(v)], ['beta3y', 'Beta', (v) => (v != null ? v.toFixed(2) : '—')], ['volume', 'Avg volume', (v) => (v ? fmtBig(v) : '—')]];
  return (
    <div className="space-y-3">
      {screen.loading && !screen.data ? <Loading label="Loading ~200 ETFs (first load ~30 s)…" /> : screen.error && !screen.data ? <ErrorBox msg={screen.error} /> : screen.data && (
        <Panel title={`ETF screener — ${rows.length} funds`} right={<div className="flex flex-wrap gap-1">
          <Chip on={maxEr === null} onClick={() => setMaxEr(null)}>Any cost</Chip><Chip on={maxEr === 0.001} onClick={() => setMaxEr(0.001)}>≤ 0.10%</Chip><Chip on={maxEr === 0.0035} onClick={() => setMaxEr(0.0035)}>≤ 0.35%</Chip></div>}>
          <div className="flex flex-wrap gap-1 mb-2">{['All', ...screen.data.groups].map((g: string) => <Chip key={g} on={group === g} onClick={() => setGroup(g)}>{g}</Chip>)}</div>
          <div className="overflow-x-auto max-h-[520px]"><table className="w-full text-2xs font-mono tabular-nums">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Fund</th>
              {cols.map(([k, l]) => <th key={k} onClick={() => setSort(k)} className={cn('text-right font-normal cursor-pointer px-1.5', sort === k && 'text-bloomberg')}>{l}</th>)}<th /></tr></thead>
            <tbody>{rows.map((f: any) => (
              <tr key={f.symbol} className="border-t border-border-subtle hover:bg-surface-2">
                <td className="py-1 font-sans"><button onClick={() => onOpen(f.symbol)} className="text-left"><span className="font-mono text-text-primary">{f.symbol}</span> <span className="text-text-secondary">{f.name}</span></button>
                  <div className="text-[10px] text-text-tertiary">{f.category ?? f.group}{f.family ? ` · ${f.family}` : ''}</div></td>
                {cols.map(([k, , fmt]) => <td key={k} className={cn('text-right px-1.5', ['ytd', 'r3y', 'r5y'].includes(k) && tone(f[k]))}>{fmt(f[k])}</td>)}
                <td className="pl-2 font-sans"><button onClick={() => setA(f.symbol)} className="text-[10px] text-bloomberg hover:underline">A</button> <button onClick={() => setB(f.symbol)} className="text-[10px] text-bloomberg hover:underline">B</button></td></tr>))}</tbody></table></div>
          <div className="text-[10px] text-text-tertiary mt-1">Click A / B to pick two funds to compare below. {screen.data.note}</div>
        </Panel>)}
      <Panel title="Compare two funds — overlap and costs">
        <div className="flex items-center gap-1 text-[11px]"><input value={a} onChange={(e) => setA(e.target.value.toUpperCase())} className="w-20 bg-surface-1 border border-border px-2 py-0.5 font-mono" />
          <span className="text-text-tertiary">vs</span><input value={b} onChange={(e) => setB(e.target.value.toUpperCase())} className="w-20 bg-surface-1 border border-border px-2 py-0.5 font-mono" />
          <button onClick={() => setCmp([a, b])} className="px-3 py-0.5 bg-bloomberg text-text-inverse">Compare</button></div>
        {comp.loading && !comp.data ? <Loading /> : comp.error ? <div className="mt-2"><ErrorBox msg={comp.error} /></div> : comp.data && (
          <div className="mt-2 space-y-2">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Tile label="Holdings overlap" value={pc(comp.data.overlap_weight)} cls={comp.data.overlap_weight > 0.5 ? 'text-amber' : ''} sub={`${comp.data.common_count} shared names`} />
              <Tile label="Sector overlap" value={pc(comp.data.sector_overlap)} />
              <Tile label={`${comp.data.a} coverage`} value={comp.data.count_a} sub={comp.data.coverage_a} /><Tile label={`${comp.data.b} coverage`} value={comp.data.count_b} sub={comp.data.coverage_b} />
            </div>
            <table className="w-full text-2xs font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal" /><th className="text-right font-normal">{comp.data.a}</th><th className="text-right font-normal">{comp.data.b}</th></tr></thead>
              <tbody>{[['Expense', 'expense', (v: any) => pc(v, 2)], ['Assets', 'aum', (v: any) => (v ? `$${fmtBig(v)}` : '—')], ['Yield', 'yield', (v: any) => pc(v, 2)], ['YTD', 'ytd', (v: any) => sp(v)], ['5y avg', 'r5y', (v: any) => sp(v)]].map(([l, k, f]: any) => (
                <tr key={k} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-secondary">{l}</td><td className="text-right">{f(comp.data.fa[k])}</td><td className="text-right">{f(comp.data.fb[k])}</td></tr>))}</tbody></table>
            {comp.data.common.length > 0 && <div className="text-2xs"><span className="text-text-tertiary">Largest shared: </span>{comp.data.common.slice(0, 12).map((c: any) => `${c.symbol} (${pc(c.weight_a)} / ${pc(c.weight_b)})`).join(' · ')}</div>}
            <div className="text-[10px] text-text-tertiary">{comp.data.note}</div>
          </div>)}
      </Panel>
    </div>
  );
}

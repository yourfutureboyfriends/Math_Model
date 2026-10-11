// CF (company filings), CRED (credit spreads), FAC (factor exposures) and PORT (portfolio risk).
import { useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { apiError, ErrorBox, fmtBig, Loading, Panel, useJSON } from './shared';

const enc = encodeURIComponent;
const pc = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`);
const sp = (x: number | null | undefined, d = 1) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(d)}%`);
const bp = (x: number | null | undefined) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${x.toFixed(0)}bp`);
const tone = (x: number | null | undefined) => (x == null ? 'text-text-tertiary' : x >= 0 ? 'text-green' : 'text-red');
const usd = (x: number | null | undefined) => (x == null ? '—' : `${x < 0 ? '−' : ''}$${fmtBig(Math.abs(x))}`);

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

// ── CF ──────────────────────────────────────────────────────────────────────
const CF_FILTERS: [string, string, (f: any) => boolean][] = [
  ['material', 'Material', (f) => f.material], ['8k', '8-K events', (f) => f.form.startsWith('8-K') || f.form === '6-K'],
  ['periodic', '10-K / 10-Q', (f) => /^(10-K|10-Q|20-F|40-F)/.test(f.form)], ['owners', 'Big holders (13D/G)', (f) => /^SC 13/.test(f.form)],
  ['insider', 'Insiders (4, 144)', (f) => ['4', '4/A', '144'].includes(f.form)], ['all', 'All', () => true],
];

export function CfView({ symbol }: { symbol: string }) {
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/cf/${enc(symbol)}`, 900_000);
  const [flt, setFlt] = useState('material');
  const [open, setOpen] = useState<any>(null);
  useEffect(() => setOpen(null), [symbol]);
  if (loading && !d) return <Loading label="Reading the SEC filing index…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const rows = d.filings.filter((CF_FILTERS.find((f) => f[0] === flt) ?? CF_FILTERS[0])[2]);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Filer" value={<span className="text-sm">{d.name}</span>} sub={`CIK ${d.cik}${d.sic ? ` · ${d.sic}` : ''}`} />
        <Tile label="Typical earnings-day move" value={pc(d.typical_earnings_move)} sub={`median |move vs S&P 500| over ${d.earnings_events} results 8-Ks`} />
        <Tile label="Red-flag events" value={d.red_flags} cls={d.red_flags ? 'text-red' : ''} sub="restatements, auditor changes, impairments, defaults…" />
        <Tile label="Fiscal year ends" value={d.fiscal_year_end ? `${d.fiscal_year_end.slice(0, 2)}/${d.fiscal_year_end.slice(2)}` : '—'} sub="month / day" />
      </div>
      <div className="flex flex-wrap gap-1">{CF_FILTERS.map(([k, l]) => <Chip key={k} on={flt === k} onClick={() => setFlt(k)}>{l}</Chip>)}</div>
      <div className={cn('grid gap-3', open ? 'grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_620px]' : 'grid-cols-1')}>
        <Panel title={`${rows.length} filings — newest first; click one to read it here`}>
          <div className="overflow-x-auto"><table className="w-full text-2xs">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Accepted</th><th className="text-left font-normal">Form</th>
              <th className="text-left font-normal">What happened</th><th className="text-right font-normal" title="Close-to-close on the first session after the filing">Day move</th>
              <th className="text-right font-normal" title="Minus the S&P 500">vs market</th><th className="text-right font-normal">5 days</th></tr></thead>
            <tbody>{rows.map((f: any) => (
              <tr key={f.url} onClick={() => setOpen(f)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-2', open?.url === f.url && 'bg-bloomberg/10')}>
                <td className="py-1 pr-2 font-mono text-text-secondary whitespace-nowrap">{f.accepted ?? f.filed}</td>
                <td className="pr-2 whitespace-nowrap"><span className="font-mono text-text-primary">{f.form}</span> <span className="text-text-tertiary">{f.label}</span></td>
                <td className="pr-2">{f.items.length ? <span className="flex flex-wrap gap-1">{f.items.filter((i: any) => i.code !== '9.01').map((i: any) => (
                  <span key={i.code} className={cn('px-1 rounded-sm border text-[10px]', i.severity === 'red' ? 'border-red/50 text-red bg-red/5' : i.severity === 'amber' ? 'border-amber/50 text-amber bg-amber/5' : 'border-border text-text-secondary')}>{i.label}</span>))}</span>
                  : f.period ? <span className="text-text-tertiary">period {f.period}</span> : null}</td>
                <td className={cn('text-right font-mono', tone(f.reaction))}>{f.reaction != null ? sp(f.reaction) : ''}</td>
                <td className={cn('text-right font-mono', tone(f.abnormal), f.abnormal != null && Math.abs(f.abnormal) >= 0.05 && 'font-semibold')}>{f.abnormal != null ? sp(f.abnormal) : ''}</td>
                <td className={cn('text-right font-mono', tone(f.reaction_5d))}>{f.reaction_5d != null ? sp(f.reaction_5d) : ''}</td></tr>))}</tbody>
          </table></div>
          <div className="text-[10px] text-text-tertiary mt-1">{d.source} A filing accepted after 4pm New York time is matched to the next session.</div>
        </Panel>
        {open && <FilingReader f={open} onClose={() => setOpen(null)} />}
      </div>
    </div>
  );
}

function FilingReader({ f, onClose }: { f: any; onClose: () => void }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/cf/text?url=${enc(f.url)}`);
  const [q, setQ] = useState('');
  const [tab, setTab] = useState(0);
  const docs: { name: string; text: string }[] = data ? [...(data.exhibits ?? []).map((e: any) => ({ name: /99/.test(e.name) ? 'Press release' : e.name, text: e.text })), { name: `${f.form} document`, text: data.text }] : [];
  const cur = docs[Math.min(tab, docs.length - 1)];
  const parts = useMemo(() => {
    if (!cur) return [];
    if (!q || q.length < 3) return [cur.text];
    return cur.text.split(new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
  }, [cur, q]);
  const hits = q.length >= 3 ? Math.floor(parts.length / 2) : 0;
  return (
    <Panel title={`${f.form} · ${f.accepted ?? f.filed}`} className="self-start 2xl:sticky 2xl:top-2" right={<button onClick={onClose} className="px-2 border border-border text-text-secondary text-[11px]">✕</button>}>
      {loading && !data ? <Loading label="Fetching the document from EDGAR…" /> : error && !data ? <ErrorBox msg={error} /> : cur && (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-1">{docs.map((x, i) => <Chip key={i} on={tab === i} onClick={() => setTab(i)}>{x.name}</Chip>)}
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find in document (guidance, impairment…)" className="ml-auto w-56 bg-surface-1 border border-border px-2 py-0.5 text-[11px]" />
            {q.length >= 3 && <span className="text-[10px] text-text-tertiary">{hits} found</span>}</div>
          <div className="max-h-[70vh] overflow-auto border border-border-subtle bg-surface-2/40 p-2 text-[11px] leading-relaxed whitespace-pre-wrap text-text-secondary">
            {parts.map((p, i) => (i % 2 ? <mark key={i} className="bg-amber/30 text-text-primary">{p}</mark> : <span key={i}>{p}</span>))}
          </div>
          {data.truncated && <div className="text-[10px] text-text-tertiary">Long document — the first 200,000 characters are shown.</div>}
        </div>)}
    </Panel>
  );
}

// ── CRED ────────────────────────────────────────────────────────────────────
const CRED_COLORS: Record<string, string> = {
  BAMLC0A0CM: 'rgb(var(--c-blue))', BAMLC0A4CBBB: 'rgb(14 165 233)', BAMLH0A0HYM2: 'rgb(var(--c-red))', BAMLH0A1HYBB: 'rgb(var(--c-amber))',
  BAMLH0A2HYB: 'rgb(234 88 12)', BAMLH0A3HYC: 'rgb(127 29 29)', BAMLHE00EHYIOAS: 'rgb(168 85 247)', BAMLEMCBPIOAS: 'rgb(var(--c-green))',
  BAMLEMHBHYCRPIOAS: 'rgb(20 184 166)', BAMLH0A0HYM2EY: 'rgb(var(--c-text-secondary))',
};

export function CredView() {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/cred', 3_600_000);
  const [sel, setSel] = useState<string[]>(['BAMLC0A0CM', 'BAMLC0A4CBBB', 'BAMLH0A0HYM2', 'BAMLH0A1HYBB']);
  if (loading && !d) return <Loading label="Loading ICE BofA spreads…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const groups = ['IG', 'HY', 'Regions', 'Yield'];
  const toggle = (id: string) => setSel(sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]);
  return (
    <div className="space-y-3">
      {d.signals.length > 0 && <div className="px-3 py-2 border border-amber/50 bg-amber/5 space-y-1">{d.signals.map((s: string) => <div key={s} className="text-2xs text-amber">• {s}</div>)}</div>}
      <Panel title="Spreads over Treasuries — click to chart">
        <table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Index</th><th className="text-right font-normal">Level</th><th className="text-right font-normal">1w</th>
            <th className="text-right font-normal">1m</th><th className="text-right font-normal">3m</th><th className="text-right font-normal">1y</th><th className="font-normal text-left pl-3">Where in its 3-year range (tight → wide)</th></tr></thead>
          <tbody>{groups.flatMap((g) => d.series.filter((x: any) => x.group === g).map((x: any) => (
            <tr key={x.id} onClick={() => toggle(x.id)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-2', sel.includes(x.id) && 'bg-bloomberg/5')}>
              <td className="py-1 font-sans"><span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ background: CRED_COLORS[x.id] }} /><span className="text-text-primary">{x.name}</span></td>
              <td className="text-right text-text-primary">{x.last.toFixed(2)}%</td>
              {[x.chg_1w_bp, x.chg_1m_bp, x.chg_3m_bp, x.chg_1y_bp].map((v: number, i: number) => <td key={i} className={cn('text-right', v == null ? '' : v > 0 ? 'text-red' : 'text-green')}>{bp(v)}</td>)}
              <td className="pl-3"><div className="flex items-center gap-2"><div className="relative w-40 h-1.5 bg-gradient-to-r from-green/40 via-surface-3 to-red/40 rounded-full">
                <span className="absolute -top-0.5 w-1 h-2.5 bg-text-primary rounded-sm" style={{ left: `calc(${x.percentile * 100}% - 2px)` }} /></div>
                <span className="text-text-tertiary">{Math.round(x.percentile * 100)}th · {x.min.toFixed(2)}–{x.max.toFixed(2)}</span></div></td></tr>)))}</tbody>
        </table>
        <div className="text-[10px] text-text-tertiary mt-1">Widening (red) means investors demand more to lend to companies — usually alongside falling stocks. {d.note}</div>
      </Panel>
      <Panel title="History (weekly, %)">
        <LineChart rows={d.history} x="date" height={300} fmt={(v) => `${v.toFixed(2)}%`}
          lines={sel.map((id) => ({ key: id, label: d.series.find((x: any) => x.id === id)?.name ?? id, color: CRED_COLORS[id] ?? 'rgb(var(--c-blue))' }))} />
      </Panel>
      {Object.keys(d.derived).length > 0 && <div className="grid grid-cols-1 md:grid-cols-2 gap-2">{Object.entries<any>(d.derived).map(([k, x]) => (
        <Tile key={k} label={x.label} value={k === 'hy_ig_ratio' ? `${x.last.toFixed(2)}×` : `${x.last.toFixed(2)} pts`} sub={`${Math.round(x.percentile * 100)}th percentile of three years`} />))}</div>}
      <div className="text-[10px] text-text-tertiary">Source: {d.source}.</div>
    </div>
  );
}

// ── FAC ─────────────────────────────────────────────────────────────────────
const FAC_COLORS: Record<string, string> = { 'Mkt-RF': 'rgb(var(--c-blue))', SMB: 'rgb(var(--c-amber))', HML: 'rgb(168 85 247)', RMW: 'rgb(var(--c-green))', CMA: 'rgb(20 184 166)', Mom: 'rgb(var(--c-red))' };
const FAC_SHORT: Record<string, [string, string]> = {
  'Mkt-RF': ['more market-sensitive than average', 'less market-sensitive than average'], SMB: ['small-company-like', 'large-company-like'],
  HML: ['value-like (cheap on book)', 'growth-like (expensive on book)'], RMW: ['high-profitability (quality)', 'low-profitability'],
  CMA: ['a conservative investor', 'an aggressive investor (fast asset growth)'], Mom: ['a recent winner (momentum)', 'a recent loser (anti-momentum)'],
};

export function FacView({ symbol }: { symbol: string }) {
  const [yrs, setYrs] = useState(5);
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/fac/${enc(symbol)}?years=${yrs}`);
  if (loading && !d) return <Loading label="Regressing on the Fama–French factors…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const sig = d.loadings.filter((l: any) => Math.abs(l.t) >= 2 && l.factor !== 'Mkt-RF');
  const mkt = d.loadings.find((l: any) => l.factor === 'Mkt-RF');
  const story = [mkt && `${mkt.beta > 1.1 ? FAC_SHORT['Mkt-RF'][0] : mkt.beta < 0.9 ? FAC_SHORT['Mkt-RF'][1] : 'about as market-sensitive as average'} (β ${mkt.beta.toFixed(2)})`,
    ...sig.map((l: any) => FAC_SHORT[l.factor]?.[l.beta > 0 ? 0 : 1])].filter(Boolean);
  const maxB = Math.max(0.5, ...d.loadings.map((l: any) => Math.abs(l.beta)));
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 text-[11px]"><span className="text-text-tertiary mr-1">Window</span>{[3, 5, 10].map((y) => <Chip key={y} on={yrs === y} onClick={() => setYrs(y)}>{y} years</Chip>)}</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Alpha (annual)" value={sp(d.alpha_annual)} cls={tone(d.alpha_annual)} sub={`t = ${d.alpha_t} ${Math.abs(d.alpha_t) >= 2 ? '(significant)' : '(not significant)'}`} />
        <Tile label="Explained by factors (R²)" value={pc(d.r2, 0)} sub={`${pc(d.idiosyncratic_share, 0)} of the variance is company-specific`} />
        <Tile label="Market beta" value={mkt?.beta.toFixed(2)} sub={`t = ${mkt?.t}`} />
        <Tile label="Sample" value={`${d.days} days`} sub={`${d.start} → ${d.end}`} />
      </div>
      <div className="px-3 py-2 border border-border bg-surface-1 rounded-md text-xs text-text-secondary">In factor terms, {symbol} is {story.length ? story.join('; ') : 'free of strong style tilts'}.</div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-3">
        <Panel title="Loadings (bars) — faded = not statistically significant">
          <div className="space-y-2">{d.loadings.map((l: any) => (
            <div key={l.factor} className={cn('text-2xs', Math.abs(l.t) < 2 && 'opacity-50')}>
              <div className="flex justify-between"><span className="text-text-primary">{l.name}</span><span className="font-mono text-text-secondary">β {l.beta.toFixed(2)} · t {l.t} · {sp(l.return_contribution)} a year</span></div>
              <div className="relative h-2 bg-surface-3 rounded-full mt-0.5"><div className="absolute top-0 bottom-0 w-px bg-text-tertiary left-1/2" />
                <div className="absolute top-0 bottom-0 rounded-full" style={{ background: FAC_COLORS[l.factor], left: l.beta >= 0 ? '50%' : `${50 - (Math.abs(l.beta) / maxB) * 50}%`, width: `${(Math.abs(l.beta) / maxB) * 50}%` }} /></div>
            </div>))}</div>
          <div className="text-[10px] text-text-tertiary mt-2">Return contribution = loading × the factor’s average return over the window. {d.note}</div>
        </Panel>
        <Panel title="Rolling one-year loadings">
          <LineChart rows={d.rolling} x="date" height={260} controls={false} fmt={(v) => v.toFixed(2)} baseline={0}
            lines={Object.keys(FAC_COLORS).map((k) => ({ key: k, label: d.factor_names?.[k] ?? k, color: FAC_COLORS[k] }))} />
        </Panel>
      </div>
      {d.us_factors_note && <div className="text-[10px] text-amber">{d.us_factors_note}</div>}
      <div className="text-[10px] text-text-tertiary">Source: {d.source}.</div>
    </div>
  );
}

// ── PORT ────────────────────────────────────────────────────────────────────
type Holding = { symbol: string; quantity: number };
const PKEY = 'mkt_port_v1';
const readCustom = (): Holding[] => { try { const v = JSON.parse(localStorage.getItem(PKEY) || '[]'); return Array.isArray(v) ? v : []; } catch { return []; } };
const saveCustom = (h: Holding[]) => { try { localStorage.setItem(PKEY, JSON.stringify(h)); } catch { /* storage unavailable */ } };

export function PortView({ onOpen }: { onOpen: (s: string) => void }) {
  const paper = useJSON<any>('/api/v1/portfolio/positions');
  const paperRows: Holding[] = useMemo(() => (paper.data?.positions ?? []).map((p: any) => ({ symbol: p.symbol, quantity: Number(p.quantity) })).filter((h: Holding) => h.symbol && h.quantity), [paper.data]);
  const [src, setSrc] = useState<'paper' | 'custom'>('custom');
  const [custom, setCustom] = useState<Holding[]>(readCustom);
  const [paste, setPaste] = useState('');
  useEffect(() => { if (paperRows.length && !readCustom().length) setSrc('paper'); }, [paperRows.length]);
  const holdings = src === 'paper' ? paperRows : custom;
  const key = JSON.stringify(holdings);
  const [res, setRes] = useState<{ data: any; error: string | null; loading: boolean }>({ data: null, error: null, loading: false });
  useEffect(() => {
    if (!holdings.length) { setRes({ data: null, error: null, loading: false }); return; }
    let live = true;
    const t = setTimeout(async () => {
      setRes((r) => ({ ...r, loading: true, error: null }));
      try {
        const r = await fetch('/api/v1/mkt/port/risk', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ holdings }) });
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(apiError(j, r.status));
        if (live) setRes({ data: j, error: null, loading: false });
      } catch (e: any) { if (live) setRes((r) => ({ ...r, error: e.message, loading: false })); }
    }, 600);
    return () => { live = false; clearTimeout(t); };
  }, [key]);   // eslint-disable-line react-hooks/exhaustive-deps
  const setC = (h: Holding[]) => { setCustom(h); saveCustom(h); };
  const addPaste = () => {
    const add: Holding[] = [];
    for (const m of paste.matchAll(/([A-Za-z0-9.^=\-]+)[\s,:x×]+(-?[\d.]+)/g)) add.push({ symbol: m[1].toUpperCase(), quantity: Number(m[2]) });
    if (add.length) { const map = new Map(custom.map((h) => [h.symbol, h.quantity])); add.forEach((h) => map.set(h.symbol, h.quantity)); setC([...map].map(([symbol, quantity]) => ({ symbol, quantity }))); setPaste(''); }
  };
  const d = res.data, s = d?.summary;
  return (
    <div className="space-y-3">
      <Panel title="Holdings" right={<div className="flex gap-1">
        <Chip on={src === 'custom'} onClick={() => setSrc('custom')}>My list ({custom.length})</Chip>
        <Chip on={src === 'paper'} onClick={() => setSrc('paper')}>Paper portfolio ({paperRows.length})</Chip></div>}>
        {src === 'custom' ? (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-1">{custom.map((h, i) => (
              <span key={h.symbol} className="inline-flex items-center gap-1 border border-border rounded-sm px-1.5 py-0.5 text-[11px]">
                <button onClick={() => onOpen(h.symbol)} className="font-mono text-text-primary hover:text-bloomberg">{h.symbol}</button>
                <input type="number" value={h.quantity} onChange={(e) => { const c = [...custom]; c[i] = { ...h, quantity: Number(e.target.value) }; setC(c); }}
                  className="w-20 bg-surface-1 border border-border-subtle px-1 font-mono text-right" />
                <button onClick={() => setC(custom.filter((_, j) => j !== i))} className="text-text-tertiary hover:text-red">✕</button></span>))}</div>
            <div className="flex gap-1"><input value={paste} onChange={(e) => setPaste(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addPaste()}
              placeholder="Add holdings: AAPL 100, MSFT 50, 7203.T 1000, BTC-USD 0.5, TLT 200 (negative = short)" className="flex-1 bg-surface-1 border border-border px-2 py-1 text-xs font-mono" />
              <button onClick={addPaste} className="px-3 text-xs bg-bloomberg text-text-inverse">Add</button>
              {custom.length > 0 && <button onClick={() => setC([])} className="px-2 text-xs text-text-tertiary hover:text-red">Clear</button>}</div>
            <div className="text-[10px] text-text-tertiary">Saved in this browser. Any instrument works: stocks anywhere, ETFs, crypto, futures.</div>
          </div>
        ) : paper.error ? <div className="text-2xs text-text-tertiary">The paper portfolio needs you to be signed in ({paper.error}). Use “My list” instead.</div>
          : !paperRows.length ? <div className="text-2xs text-text-tertiary">No paper positions yet — buy something from a quote’s Trade box, or use “My list”.</div>
          : <div className="text-2xs text-text-secondary">{paperRows.length} positions from your paper portfolio.</div>}
      </Panel>
      {!holdings.length ? null : res.loading && !d ? <Loading label="Pricing holdings, three years of returns, FX and stress tests…" /> : res.error && !d ? <ErrorBox msg={res.error} /> : d && <>
        {res.loading && <div className="text-[10px] text-text-tertiary">Recalculating…</div>}
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2">
          <Tile label="Gross value" value={usd(s.gross_usd)} sub={`net ${usd(s.net_usd)} (${pc(s.net_exposure, 0)})`} />
          <Tile label="Today" value={usd(s.day_pnl)} cls={tone(s.day_pnl)} sub="P&L since yesterday’s close" />
          <Tile label="Volatility" value={pc(s.vol)} sub="annualised, daily returns" />
          <Tile label="Beta to S&P 500" value={s.beta?.toFixed(2) ?? '—'} sub="weekly" />
          <Tile label="1-day VaR 95%" value={usd(s.var95_1d)} sub={`99%: ${usd(s.var99_1d)}`} />
          <Tile label="Expected shortfall" value={usd(s.es95_1d)} sub="average loss on the worst 5% of days" />
          <Tile label="Max drawdown" value={pc(s.max_drawdown)} cls="text-red" sub={`since ${s.history_from}`} />
          <Tile label="Diversification" value={`${s.effective_n?.toFixed(1)} bets`} sub={`top 5 = ${pc(s.top5_weight, 0)} of gross`} />
        </div>
        {d.missing_history.length > 0 && <div className="text-2xs text-amber">No usable price history for {d.missing_history.join(', ')} — left out of the risk numbers.</div>}
        <Panel title="Positions — where the risk actually comes from">
          <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Holding</th><th className="text-right font-normal">Value</th><th className="text-right font-normal">Weight</th>
              <th className="text-right font-normal">Today</th><th className="text-right font-normal">1 year</th><th className="text-right font-normal">Vol</th><th className="text-right font-normal">Beta</th>
              <th className="text-left font-normal pl-3">Share of portfolio risk</th></tr></thead>
            <tbody>{d.positions.map((r: any) => (
              <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2">
                <td className="py-1 font-sans"><span className="font-mono text-text-primary">{r.symbol}</span> <span className="text-text-tertiary">{r.name} · {r.sector}</span></td>
                <td className="text-right">{usd(r.value_usd)}</td><td className="text-right">{pc(r.weight)}</td>
                <td className={cn('text-right', tone(r.day_change))}>{sp(r.day_change)}</td><td className={cn('text-right', tone(r.return_1y))}>{sp(r.return_1y, 0)}</td>
                <td className="text-right">{pc(r.vol, 0)}</td><td className="text-right">{r.beta?.toFixed(2) ?? '—'}</td>
                <td className="pl-3"><div className="flex items-center gap-2"><div className="w-32 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                  <div className={cn('h-full', r.risk_share > Math.abs(r.weight) * 1.5 ? 'bg-red' : 'bg-blue')} style={{ width: `${Math.min(100, Math.max(0, r.risk_share) * 100)}%` }} /></div>
                  <span className={cn(r.risk_share > Math.abs(r.weight) * 1.5 && 'text-red')}>{pc(r.risk_share, 0)}</span></div></td></tr>))}</tbody>
          </table></div>
          <div className="text-[10px] text-text-tertiary mt-1">Red = the position’s share of risk is far above its share of capital. Negative risk share = it hedges the rest.</div>
        </Panel>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          <Panel title="Stress tests — if this happens, the portfolio moves…">
            <table className="w-full text-2xs font-mono tabular-nums"><tbody>{d.scenarios.map((x: any) => (
              <tr key={x.scenario} className="border-t border-border-subtle first:border-0"><td className="py-1 font-sans text-text-primary">{x.scenario}</td>
                <td className={cn('text-right', tone(x.pnl))}>{usd(x.pnl)}</td><td className={cn('text-right w-16', tone(x.return))}>{sp(x.return)}</td>
                <td className="pl-3 font-sans text-[10px] text-text-tertiary">{x.pnl < 0 ? 'hit hardest: ' : 'helped most: '}{(x.pnl < 0 ? x.worst : x.best).map((w: any) => w.symbol).join(', ')}</td></tr>))}</tbody></table>
            <div className="text-[10px] text-text-tertiary mt-1">Each holding’s weekly beta to the driver over three years, times the shock.</div>
          </Panel>
          <Panel title="History replays — today’s portfolio through past crises">
            <table className="w-full text-2xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Episode</th><th className="text-right font-normal">S&P 500</th><th className="text-right font-normal">Portfolio</th><th className="text-right font-normal">P&L</th></tr></thead>
              <tbody>{d.replays.map((x: any) => (
                <tr key={x.episode} className="border-t border-border-subtle" title={`${x.start} → ${x.end}. Worst: ${x.worst.map((w: any) => `${w.symbol} ${sp(w.return, 0)}`).join(', ')}${x.proxied.length ? `. Proxied by beta: ${x.proxied.join(', ')}` : ''}`}>
                  <td className="py-1 font-sans text-text-primary">{x.episode}<span className="text-text-tertiary"> · {x.start.slice(0, 7)}</span>{x.proxied.length ? <span className="text-amber"> *</span> : null}</td>
                  <td className={cn('text-right', tone(x.spx))}>{sp(x.spx, 0)}</td><td className={cn('text-right font-semibold', tone(x.return))}>{sp(x.return, 0)}</td><td className={cn('text-right', tone(x.pnl))}>{usd(x.pnl)}</td></tr>))}</tbody></table>
            <div className="text-[10px] text-text-tertiary mt-1">Actual returns of each holding over the episode, in local currency. * a holding that didn’t trade yet is proxied by its S&P 500 beta. Hover a row for details.</div>
          </Panel>
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
          {(['sector', 'country', 'currency'] as const).map((k) => (
            <Panel key={k} title={`Exposure by ${k}`}>
              <div className="space-y-1">{d.exposure[k].slice(0, 10).map((e: any) => (
                <div key={e.name} className="flex items-center gap-2 text-2xs"><span className="w-28 truncate text-text-secondary">{e.name}</span>
                  <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden"><div className={cn('h-full', e.weight >= 0 ? 'bg-blue' : 'bg-red')} style={{ width: `${Math.min(100, Math.abs(e.weight) * 100)}%` }} /></div>
                  <span className="w-12 text-right font-mono">{pc(e.weight, 0)}</span></div>))}</div>
            </Panel>))}
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] gap-3">
          <Panel title="Today’s portfolio over the last three years (rebased to 100)">
            <LineChart rows={d.curve} x="date" height={230} fmt={(v) => v.toFixed(1)} baseline={100} lines={[{ key: 'value', label: 'Portfolio', color: 'rgb(var(--c-blue))' }]} />
            <div className="text-[10px] text-text-tertiary mt-1">Worst days: {d.worst_days.map((w: any) => `${w.date} ${sp(w.return)}`).join(' · ')}</div>
          </Panel>
          <Panel title="Factor loadings (Fama–French 5 + momentum)">
            {d.factors?.available ? <div className="space-y-1.5">{d.factors.loadings.map((l: any) => (
              <div key={l.factor} className={cn('flex items-center gap-2 text-2xs', Math.abs(l.t) < 2 && 'opacity-50')}>
                <span className="w-40 truncate text-text-secondary">{l.name}</span><span className="font-mono w-12 text-right">{l.beta.toFixed(2)}</span><span className="text-text-tertiary">t {l.t}</span></div>))}
              <div className="text-[10px] text-text-tertiary">Alpha {sp(d.factors.alpha_annual)} a year (t {d.factors.alpha_t}), R² {pc(d.factors.r2, 0)}.</div></div>
              : <div className="text-2xs text-text-tertiary">{d.factors?.reason ?? 'Factor data unavailable.'}</div>}
          </Panel>
        </div>
        <CorrGrid c={d.correlation} />
        <div className="text-[10px] text-text-tertiary">{d.note} Source: {d.source}.</div>
      </>}
    </div>
  );
}

function CorrGrid({ c }: { c: { symbols: string[]; matrix: number[][] } }) {
  if (!c || c.symbols.length < 2) return null;
  const col = (v: number) => (v >= 0 ? `rgb(var(--c-red) / ${Math.min(0.85, v * 0.85)})` : `rgb(var(--c-blue) / ${Math.min(0.85, -v * 0.85)})`);
  return (
    <Panel title="Correlation (weekly returns) — red = move together, blue = offset">
      <div className="overflow-x-auto"><table className="text-[10px] font-mono">
        <thead><tr><th />{c.symbols.map((s) => <th key={s} className="px-1 font-normal text-text-tertiary">{s.split('.')[0].slice(0, 6)}</th>)}</tr></thead>
        <tbody>{c.symbols.map((s, i) => (
          <tr key={s}><td className="pr-2 text-text-secondary">{s}</td>
            {c.matrix[i].map((v, j) => <td key={j} className="w-11 h-6 text-center text-text-primary" style={{ background: i === j ? 'transparent' : col(v) }}>{i === j ? '' : v.toFixed(2)}</td>)}</tr>))}</tbody>
      </table></div>
    </Panel>
  );
}


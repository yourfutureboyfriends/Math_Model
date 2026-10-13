// Stock Entry Signals — buy / wait / avoid for any stock, with the evidence behind it,
// an entry zone, stop, target and size, sell-side rating changes, a historical test of the
// rules on that stock, and a ranked scan of a watchlist. Method: api/calculations/stock_timing.py.

import { useCallback, useEffect, useState } from 'react';
import { Crosshair, Loader2, Search, Star } from 'lucide-react';
import { PriceChart } from '@/components/ui/PriceChart';
import { cn } from '@/lib/utils';
import { revealPanel } from '@/lib/focusMode';
import { marketTag, marketTitle } from '@/lib/marketTag';


const COMPONENTS: { key: string; label: string; source: string }[] = [
  { key: 'trend', label: 'Trend', source: 'Faber (2007); Hurst, Ooi & Pedersen — AQR (2017)' },
  { key: 'momentum', label: 'Time-series momentum', source: 'Moskowitz, Ooi & Pedersen (2012); vol-scaled per Barroso & Santa-Clara (2015)' },
  { key: 'high_52w', label: '52-week high', source: 'George & Hwang (2004)' },
  { key: 'earnings', label: 'Earnings drift', source: 'Bernard & Thomas (1989)' },
  { key: 'analysts', label: 'Sell-side view', source: 'Brokerage consensus, targets and rating changes' },
  { key: 'quality', label: 'Quality', source: 'Asness, Frazzini & Pedersen — Quality Minus Junk' },
];

const VERDICT_TONE: Record<string, string> = {
  BUY: 'border-green text-green', WAIT: 'border-amber text-amber', BUY_SMALL: 'border-amber text-amber',
  WATCH: 'border-border text-text-secondary', AVOID: 'border-red text-red', 'N/A': 'border-border text-text-tertiary',
};

const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
const spct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const px = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 }));

function Meter({ value, threshold, label, right }: { value: number | null; threshold?: number; label: string; right?: string }) {
  const pos = value == null ? 50 : ((value + 1) / 2) * 100;
  return (
    <div>
      <div className="flex justify-between text-2xs mb-1">
        <span className="text-text-tertiary uppercase tracking-wider">{label}</span>
        <span className="font-mono text-text-primary">{value == null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}`}{right ? ` · ${right}` : ''}</span>
      </div>
      <div className="relative h-2 bg-surface-3">
        <div className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
        {threshold != null && <div className="absolute -inset-y-0.5 w-0.5 bg-text-tertiary" style={{ left: `${((threshold + 1) / 2) * 100}%` }} title={`Buy threshold ${threshold}`} />}
        {value != null && (
          <div className={cn('absolute inset-y-0', value >= 0 ? 'bg-green/70' : 'bg-red/70')}
            style={value >= 0 ? { left: '50%', width: `${pos - 50}%` } : { left: `${pos}%`, width: `${50 - pos}%` }} />
        )}
      </div>
      <div className="flex justify-between text-[10px] text-text-tertiary mt-0.5"><span>−1</span><span>0</span><span>+1</span></div>
    </div>
  );
}

export function StockTimingSection() {
  const [symbol, setSymbol] = useState('');
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [held, setHeld] = useState<string[]>([]);
  const [scan, setScan] = useState<any>(null);
  const [scanning, setScanning] = useState(false);
  const [suggest, setSuggest] = useState<any[]>([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const [watch, setWatch] = useState<string[]>([]);

  useEffect(() => {
    fetch('/api/v1/stock/watchlist').then((r) => r.json())
      .then((j) => setWatch((j.symbols ?? []).map((x: any) => x.symbol))).catch(() => {});
  }, []);

  // Search any listed stock worldwide by name or ticker (debounced).
  useEffect(() => {
    const q = symbol.trim();
    if (q.length < 2 || !showSuggest) { setSuggest([]); return; }
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/v1/stock/search?q=${encodeURIComponent(q)}`);
        const j = await r.json();
        setSuggest(j.results ?? []);
      } catch { setSuggest([]); }
    }, 350);
    return () => clearTimeout(t);
  }, [symbol, showSuggest]);

  const toggleWatch = async (sym: string) => {
    const next = watch.includes(sym) ? watch.filter((s) => s !== sym) : [...watch, sym];
    setWatch(next);
    await fetch('/api/v1/stock/watchlist', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols: next }) }).catch(() => {});
  };

  useEffect(() => {
    fetch('/api/v1/portfolio/positions').then((r) => r.json())
      .then((j) => setHeld(((j.positions ?? j) as any[]).map((p) => String(p.symbol).toUpperCase()).slice(0, 8)))
      .catch(() => {});
  }, []);

  const analyze = useCallback(async (sym: string) => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setSymbol(s); setBusy(true); setError(null); setShowSuggest(false); setSuggest([]);
    try {
      const r = await fetch(`/api/v1/stock/timing?symbol=${encodeURIComponent(s)}`);
      const j = await r.json().catch(() => null);
      if (!r.ok || !j) throw new Error((typeof j?.detail === 'string' && j.detail) || `HTTP ${r.status}`);
      if (j.available === false) throw new Error(j.reason || 'No data');
      setData(j);
    } catch (e: any) {
      setError(e?.message || 'Unavailable'); setData(null);
    } finally { setBusy(false); }
  }, []);

  // Opened from Stock Ideas (or anywhere) via a 'stock-analyse' event.
  useEffect(() => {
    const h = (e: Event) => {
      const sym = String((e as CustomEvent).detail || '');
      if (!sym) return;
      const reveal = revealPanel('stock-timing');
      setTimeout(() => document.getElementById('stock-timing')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), reveal ? 300 : 50);
      analyze(sym);
    };
    window.addEventListener('stock-analyse', h);
    return () => window.removeEventListener('stock-analyse', h);
  }, [analyze]);

  const runScan = async () => {
    setScanning(true);
    try {
      const r = await fetch('/api/v1/stock/screen');
      setScan(await r.json());
    } catch { setScan({ available: false }); } finally { setScanning(false); }
  };

  const v = data?.verdict;
  const lv = data?.levels;
  const an = data?.components?.analysts;
  const bt = data?.backtest;
  const refs = lv ? [
    { value: lv.target, label: 'Target', color: 'var(--green)' },
    { value: lv.entry, label: 'Entry', color: 'var(--text-secondary)' },
    { value: lv.stop, label: 'Stop', color: 'var(--red)' },
  ] : [];

  return (
    <div className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Crosshair className="w-3 h-3" /></span>
          <h2 className="section-title">Stock Entry Signals</h2>
          <span className="text-2xs text-text-tertiary">when the evidence says buy — and where</span>
        </div>
      </div>

      <form onSubmit={(e) => {
        e.preventDefault();
        // A name ("toyota") resolves to the top search match; a ticker is used as typed.
        const exact = suggest.find((x) => x.symbol === symbol.trim().toUpperCase());
        analyze(exact ? exact.symbol : (/\s|[a-z]{4,}/.test(symbol.trim()) && suggest[0] ? suggest[0].symbol : symbol));
      }} className="flex flex-wrap items-center gap-2 mb-3">
        <div className="relative">
          <div className="flex items-center border border-border bg-bg">
            <Search className="w-3.5 h-3.5 ml-2 text-text-tertiary" />
            <input value={symbol} onChange={(e) => { setSymbol(e.target.value); setShowSuggest(true); }}
              onBlur={() => setTimeout(() => setShowSuggest(false), 200)} onFocus={() => setShowSuggest(true)}
              placeholder="Ticker or name — any market" aria-label="Ticker or company name"
              className="w-56 bg-transparent px-2 py-1 font-mono text-xs text-text-primary outline-none" />
          </div>
          {showSuggest && suggest.length > 0 && (
            <div className="absolute z-20 mt-0.5 w-[26rem] max-h-72 overflow-y-auto bg-surface-2 border border-border shadow-lg">
              {suggest.map((x) => (
                <button type="button" key={x.symbol} onMouseDown={(e) => { e.preventDefault(); analyze(x.symbol); }}
                  className="w-full text-left px-2 py-1 hover:bg-surface-3 flex items-baseline gap-2">
                  <span className="font-mono text-xs text-text-primary w-24 shrink-0">{x.symbol}</span>
                  <span className="text-2xs text-text-secondary truncate flex-1">{x.name}</span>
                  <span className="text-[10px] text-text-tertiary whitespace-nowrap">{x.exchange} · {marketTag({ ...x, asset_type: x.type === 'ETF' ? 'ETF' : x.asset_type })}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button type="submit" disabled={busy || !symbol.trim()} className="px-3 py-1 text-xs bg-bloomberg text-bg disabled:opacity-50 inline-flex items-center gap-1">
          {busy && <Loader2 className="w-3 h-3 animate-spin" />}Analyse
        </button>
        {held.length > 0 && <span className="text-2xs text-text-tertiary ml-2">Holdings:</span>}
        {held.map((h) => (
          <button type="button" key={h} onClick={() => analyze(h)}
            className="px-1.5 py-0.5 text-2xs font-mono border border-border-subtle text-text-secondary hover:text-bloomberg hover:border-bloomberg">{h}</button>
        ))}
        <button type="button" onClick={runScan} disabled={scanning}
          className="ml-auto px-2 py-1 text-2xs border border-border text-text-secondary hover:text-bloomberg disabled:opacity-50 inline-flex items-center gap-1">
          {scanning && <Loader2 className="w-3 h-3 animate-spin" />}Scan watchlist
        </button>
      </form>

      {error && <div className="mb-2 p-2 text-xs text-amber border border-amber/30">{error}</div>}
      {!data && !error && !scan && (
        <div className="p-4 text-2xs text-text-tertiary border border-border-subtle">
          Search any listed stock (any exchange, by name or ticker) to see whether trend, momentum, earnings, the sell-side and quality support buying it, whether the
          entry is stretched, and the entry zone, stop, target and size — or scan a watchlist of large caps and your holdings.
        </div>
      )}

      {data && (
        <div className="space-y-2">
          {/* Verdict */}
          <div className={cn('p-3 border-l-4 bg-surface-1 border border-border', VERDICT_TONE[v?.code] ?? '')}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-lg font-mono font-bold">{v?.label}</span>
              <span className="text-xs text-text-secondary">{data.name} · {data.symbol}{data.sector ? ` · ${data.sector}` : ''}</span>
              <button type="button" onClick={() => toggleWatch(data.symbol)} title={watch.includes(data.symbol) ? 'Remove from watchlist' : 'Add to watchlist (always analysed in Stock Ideas)'}
                className={watch.includes(data.symbol) ? 'text-amber' : 'text-text-tertiary hover:text-amber'} aria-label="Toggle watchlist">
                <Star className="w-3.5 h-3.5" fill={watch.includes(data.symbol) ? 'currentColor' : 'none'} />
              </button>
              <span className="ml-auto font-mono text-sm text-text-primary">{px(data.price)} <span className="text-2xs text-text-tertiary">{data.currency} · close {data.as_of}</span></span>
            </div>
            <div className="text-2xs text-text-secondary mt-1">{v?.detail}</div>
            <div className="text-[10px] text-text-tertiary mt-1 font-mono">
              {marketTitle(data)}{data.listing_country && data.listing_country !== data.country ? ` (listed in ${data.listing_country})` : ''} · quoted in {data.currency}
              {data.market?.index ? ` · regime vs ${data.market.index}` : ''}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
            {/* Scores */}
            <div className="p-3 bg-surface-1 border border-border space-y-3">
              <Meter label="Set-up (should I own it?)" value={data.setup_score} threshold={0.35} />
              <Meter label="Entry timing (is now good?)" value={data.timing?.score ?? null} right={data.timing?.state} />
              <div className="text-2xs text-text-tertiary">
                {data.timing?.evidence}
                <div className={cn('mt-1', data.market?.ok ? 'text-green' : 'text-amber')}>
                  Market regime: {data.market ? (data.market.ok ? 'supportive' : 'unfavourable') : 'n/a'} — {data.market?.evidence}
                </div>
              </div>
            </div>

            {/* Levels */}
            <div className="p-3 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Trade plan</div>
              {lv ? (
                <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
                  <span className="text-text-tertiary">Entry zone</span><span className="font-mono text-right text-text-primary">{px(lv.entry_low)} – {px(lv.entry_high)}</span>
                  <span className="text-text-tertiary">Stop</span><span className="font-mono text-right text-red">{px(lv.stop)}</span>
                  <span className="text-text-tertiary">Target</span><span className="font-mono text-right text-green" title={lv.target_basis}>{px(lv.target)}</span>
                  <span className="text-text-tertiary">Reward : risk</span><span className={cn('font-mono text-right', (lv.reward_risk ?? 0) >= 1.5 ? 'text-text-primary' : 'text-amber')}>{lv.reward_risk ?? '—'}</span>
                  {lv.shares != null && <>
                    <span className="text-text-tertiary">Size</span><span className="font-mono text-right text-text-primary">{lv.shares.toLocaleString()} sh</span>
                    <span className="text-text-tertiary">Notional</span><span className="font-mono text-right text-text-primary">${Math.round(lv.notional).toLocaleString()} ({pct(lv.pct_nav)} NAV)</span>
                    {data.currency && data.currency !== 'USD' && lv.notional_local != null && <>
                      <span className="text-text-tertiary">Local</span><span className="font-mono text-right text-text-secondary">{Math.round(lv.notional_local).toLocaleString()} {data.currency}</span>
                    </>}
                    <span className="text-text-tertiary">Risk to stop</span><span className="font-mono text-right text-text-primary">${Math.round(lv.risk_usd).toLocaleString()}</span>
                  </>}
                  <span className="col-span-2 text-[10px] text-text-tertiary mt-1">Stop: {lv.stop_basis}. Target: {lv.target_basis}. {lv.sizing_basis}.</span>
                </div>
              ) : <div className="text-2xs text-text-tertiary">Not enough history for levels.</div>}
            </div>

            {/* Sell-side */}
            <div className="p-3 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Sell-side</div>
              {an ? (
                <div className="text-xs space-y-1">
                  <div className="flex justify-between"><span className="text-text-tertiary" title="1 = strong buy … 5 = sell">Consensus</span><span className="font-mono whitespace-nowrap">{an.recommendation_mean?.toFixed(2) ?? '—'} · {an.analysts ?? '—'} analysts</span></div>
                  <div className="flex justify-between"><span className="text-text-tertiary" title="Low / mean / high price target">Targets</span><span className="font-mono whitespace-nowrap">{px(an.target_low)} / {px(an.target_mean)} / {px(an.target_high)}</span></div>
                  <div className="flex justify-between"><span className="text-text-tertiary">Upside to mean</span><span className="font-mono">{spct(an.upside, 0)}</span></div>
                  <div className="flex justify-between"><span className="text-text-tertiary">90 days</span><span className="font-mono">{an.upgrades}↑ {an.downgrades}↓ · targets {an.target_raises}↑ {an.target_cuts}↓</span></div>
                </div>
              ) : <div className="text-2xs text-text-tertiary">No analyst coverage.</div>}
              {(data.revisions ?? []).length > 0 && (
                <table className="w-full mt-2 text-[10px] font-mono">
                  <tbody>
                    {data.revisions.slice(0, 6).map((r: any, i: number) => (
                      <tr key={i} className="border-t border-border-subtle">
                        <td className="py-0.5 text-text-tertiary whitespace-nowrap">{r.date.slice(5)}</td>
                        <td className="font-sans text-text-secondary truncate max-w-[110px]">{r.firm}</td>
                        <td className={cn('whitespace-nowrap', r.action === 'up' ? 'text-green' : r.action === 'down' ? 'text-red' : 'text-text-tertiary')}>
                          {r.action === 'up' ? 'upgrade' : r.action === 'down' ? 'downgrade' : r.action === 'init' ? 'initiate' : 'maintain'} {r.to_grade}
                        </td>
                        <td className="text-right text-text-secondary">{r.target ? `${px(r.target)}${r.target_change ? ` (${r.target_change > 0 ? '+' : ''}${px(r.target_change)})` : ''}` : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Chart */}
          {data.chart && (
            <div className="p-3 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Price, moving averages, plan levels{data.chart.some((r: any) => r.buy) ? ' and past BUY signal starts (▲, daily bars)' : ''}</div>
              <PriceChart symbol={data.symbol} refs={refs}
                markers={Object.fromEntries(data.chart.filter((r: any, i: number) => r.buy && !data.chart[i - 1]?.buy).map((r: any) => [r.date, true]))} />
            </div>
          )}

          {/* Evidence */}
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Evidence</div>
            <table className="w-full text-xs">
              <thead><tr className="text-2xs text-text-tertiary text-left"><th className="font-normal pb-1">Signal</th><th className="font-normal pb-1 w-28">Score</th><th className="font-normal pb-1 text-right w-12">Weight</th><th className="font-normal pb-1 pl-3">Reading</th></tr></thead>
              <tbody>
                {COMPONENTS.map((c) => {
                  const comp = data.components?.[c.key];
                  const sc = comp?.score as number | undefined;
                  return (
                    <tr key={c.key} className="border-t border-border-subtle align-top">
                      <td className="py-1.5 pr-2"><div className="text-text-primary">{c.label}</div><div className="text-[10px] text-text-tertiary">{c.source}</div></td>
                      <td className="py-1.5">
                        {sc == null ? <span className="text-text-tertiary text-2xs">no data</span> : (
                          <div className="flex items-center gap-1.5">
                            <div className="relative w-16 h-1.5 bg-surface-3"><div className="absolute inset-y-0 left-1/2 w-px bg-border-strong" />
                              <div className={cn('absolute inset-y-0', sc >= 0 ? 'bg-green/70' : 'bg-red/70')} style={sc >= 0 ? { left: '50%', width: `${sc * 50}%` } : { left: `${50 + sc * 50}%`, width: `${-sc * 50}%` }} /></div>
                            <span className="font-mono text-2xs">{sc >= 0 ? '+' : ''}{sc.toFixed(2)}</span>
                          </div>
                        )}
                      </td>
                      <td className="py-1.5 text-right font-mono text-2xs text-text-tertiary">{Math.round((data.weights?.[c.key] ?? 0) * 100)}%</td>
                      <td className="py-1.5 pl-3 text-2xs text-text-secondary">{comp?.evidence ?? '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Historical test */}
          {bt && (
            <div className="p-3 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Historical test on {data.symbol} · {bt.period}</div>
              <table className="w-full text-xs font-mono">
                <thead><tr className="text-2xs text-text-tertiary text-left font-sans"><th className="font-normal">Horizon</th><th className="font-normal text-right">Signals</th><th className="font-normal text-right">Avg return after signal</th><th className="font-normal text-right">Any day</th><th className="font-normal text-right">Hit rate</th><th className="font-normal text-right">Any day</th></tr></thead>
                <tbody>
                  {['21d', '63d'].map((h) => bt[h] && (
                    <tr key={h} className="border-t border-border-subtle">
                      <td className="py-0.5 font-sans text-text-secondary">{h === '21d' ? '1 month' : '3 months'}</td>
                      <td className="text-right">{bt[h].signals}</td>
                      <td className={cn('text-right', (bt[h].avg_return ?? 0) > (bt[h].base_avg_return ?? 0) ? 'text-green' : 'text-amber')}>{spct(bt[h].avg_return)}</td>
                      <td className="text-right text-text-tertiary">{spct(bt[h].base_avg_return)}</td>
                      <td className="text-right">{pct(bt[h].hit_rate, 0)}</td>
                      <td className="text-right text-text-tertiary">{pct(bt[h].base_hit_rate, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="text-[10px] text-text-tertiary mt-1">
                Rules tested: {bt.rules}. Signals thinned to one per horizon (independent windows); &ldquo;any day&rdquo; = buying on every day of the period.
                A single stock&apos;s history is a small sample — treat this as a sanity check, not proof.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Watchlist scan */}
      {scan && (
        <div className="mt-2 p-3 bg-surface-1 border border-border">
          <div className="flex items-baseline gap-2 mb-1">
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">Watchlist scan</span>
            {scan.counts && <span className="text-2xs text-text-tertiary font-mono">{scan.counts.BUY} buy · {scan.counts.WAIT} wait · {scan.counts.WATCH} watch · {scan.counts.AVOID} avoid</span>}
          </div>
          {scan.available === false ? <div className="text-2xs text-amber">Scan unavailable.</div> : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead><tr className="text-2xs text-text-tertiary text-left font-sans">
                  <th className="font-normal pb-1">Stock</th><th className="font-normal">Verdict</th><th className="font-normal text-right">Set-up</th>
                  <th className="font-normal text-right">Entry</th><th className="font-normal text-right">12-1M</th><th className="font-normal text-right">Target upside</th><th className="font-normal text-right">R:R</th></tr></thead>
                <tbody>
                  {(scan.rows ?? []).map((r: any) => (
                    <tr key={r.symbol} onClick={() => analyze(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2">
                      <td className="py-1"><span className="text-text-primary">{r.symbol}</span> <span className="font-sans text-2xs text-text-tertiary">{r.name}</span></td>
                      <td className={cn('font-sans text-2xs', (VERDICT_TONE[r.verdict] ?? '').split(' ').find((c: string) => c.startsWith('text-')))}>{r.verdict_label}</td>
                      <td className="text-right">{r.setup_score?.toFixed(2) ?? '—'}</td>
                      <td className="text-right text-text-secondary">{r.timing_state ?? '—'}</td>
                      <td className="text-right">{spct(r.momentum, 0)}</td>
                      <td className="text-right">{spct(r.upside, 0)}</td>
                      <td className="text-right">{r.reward_risk ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="mt-2 text-[10px] text-text-tertiary">
        Research basis: trend and time-series momentum (Faber 2007; Moskowitz, Ooi &amp; Pedersen 2012; Hurst, Ooi &amp; Pedersen, AQR 2017),
        volatility scaling (Barroso &amp; Santa-Clara 2015), 52-week high (George &amp; Hwang 2004), post-earnings drift (Bernard &amp; Thomas 1989),
        quality (Asness, Frazzini &amp; Pedersen), and trend-plus-mean-reversion entry filters (Kolanovic &amp; Wei, J.P. Morgan 2015).
        Not investment advice; signals are probabilistic.
      </div>
    </div>
  );
}

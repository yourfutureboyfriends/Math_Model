/**
 * Pre-Trade Desk — the Head of Trading's feasibility assessment for implementing a PMC-approved order:
 * price and timestamp, size and weights, liquidity, estimated costs (each labelled observed / estimate /
 * assumption / statutory), technicals for entry timing, events in the execution window, mandate checks and the
 * pitch's valuation → flags and an execution suggestion. Decision support only: approves nothing, places no order.
 * Backend: POST /api/v1/trading/pretrade-assessment (api/handlers/pretrade_feasibility.py).
 */
import { useState } from 'react';
import { Loader2, ShieldAlert, ShieldCheck, AlertTriangle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { num } from '@/lib/format';

const pct = (v?: number | null, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`);
const spct = (v?: number | null, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const bp = (v?: number | null) => (v == null || !Number.isFinite(v) ? '—' : `${v.toFixed(1)} bp`);

const inputCls = 'bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary focus:border-bloomberg outline-none';

function Card({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('border border-border bg-surface-1 p-3', className)}>
      <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">{title}</div>
      {children}
    </div>
  );
}

function Row({ k, v, sub }: { k: string; v: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2 text-2xs py-0.5 border-b border-border-subtle last:border-0">
      <span className="text-text-tertiary">{k}</span>
      <span className="font-mono text-text-primary text-right">{v}{sub ? <span className="text-text-tertiary font-sans"> {sub}</span> : null}</span>
    </div>
  );
}

export function PreTradeDeskSection() {
  const [symbol, setSymbol] = useState('');
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY');
  const [mode, setMode] = useState<'amount' | 'quantity'>('amount');
  const [size, setSize] = useState('');
  const [cap, setCap] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [r, setR] = useState<any>(null);

  const run = async () => {
    setBusy(true); setErr(null); setR(null);
    try {
      const body: any = { symbol: symbol.trim().toUpperCase(), side };
      const n = Number(size);
      if (!(n > 0)) throw new Error('Enter a positive size.');
      if (mode === 'amount') body.amount_base = n; else body.quantity = n;
      if (cap) body.participation = Number(cap) / 100;
      const res = await fetch('/api/v1/trading/pretrade-assessment', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const j = await res.json();
      if (!res.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${res.status}`);
      setR(j);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const verdictTone = r?.assessment?.verdict === 'feasible' ? 'border-green text-green' : r?.assessment?.blocking ? 'border-red text-red' : 'border-amber text-amber';
  const ccy = r?.price?.currency ?? '';
  const base = r?.base_currency ?? '';

  return (
    <section id="pretrade-desk" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Pre-Trade Desk</h2>
          <span className="text-2xs text-text-tertiary ml-2">feasibility of implementing an approved order — decision support, no orders placed</span>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2 mb-3">
        <label className="text-2xs text-text-tertiary">Security<br />
          <input className={cn(inputCls, 'w-28')} value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="AZN.L" /></label>
        <label className="text-2xs text-text-tertiary">Side<br />
          <select className={inputCls} value={side} onChange={(e) => setSide(e.target.value as any)}><option>BUY</option><option>SELL</option></select></label>
        <label className="text-2xs text-text-tertiary">Size by<br />
          <select className={inputCls} value={mode} onChange={(e) => setMode(e.target.value as any)}><option value="amount">amount (fund currency)</option><option value="quantity">shares</option></select></label>
        <label className="text-2xs text-text-tertiary">{mode === 'amount' ? 'Amount' : 'Shares'}<br />
          <input className={cn(inputCls, 'w-32')} value={size} onChange={(e) => setSize(e.target.value)} placeholder={mode === 'amount' ? '30000' : '200'} /></label>
        <label className="text-2xs text-text-tertiary">Max participation %<br />
          <input className={cn(inputCls, 'w-20')} value={cap} onChange={(e) => setCap(e.target.value)} placeholder="mandate" /></label>
        <button onClick={run} disabled={busy || !symbol.trim() || !size} className="inline-flex items-center gap-1 px-3 py-1 text-2xs bg-bloomberg text-bg disabled:opacity-50">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <ShieldCheck className="w-3 h-3" />}Assess
        </button>
      </div>
      {err && <div className="text-xs text-red mb-2">{err}</div>}

      {r && (
        <div className="space-y-2">
          <div className={cn('border p-2 flex flex-wrap items-center gap-3', verdictTone)}>
            {r.assessment.blocking ? <ShieldAlert className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
            <span className="text-sm font-semibold uppercase">{r.assessment.verdict}</span>
            <span className="text-xs text-text-secondary">{r.side} {num(r.size.quantity, 0)} {r.symbol} · {r.security.name} · {r.security.exchange} · ≈ {num(r.size.notional_base, 0)} {base}</span>
            <span className="text-2xs text-text-tertiary ml-auto">{r.disclaimer}</span>
          </div>
          {r.flags?.length > 0 && (
            <div className="border border-border bg-surface-1 p-2 space-y-0.5">
              {r.flags.map((f: any, i: number) => (
                <div key={i} className={cn('text-xs flex gap-1.5', f.level === 'block' ? 'text-red' : f.level === 'warn' ? 'text-amber' : 'text-text-secondary')}>
                  {f.level === 'block' ? <ShieldAlert className="w-3 h-3 mt-0.5 shrink-0" /> : f.level === 'warn' ? <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /> : <Info className="w-3 h-3 mt-0.5 shrink-0" />}
                  <span><b className="uppercase text-2xs">{f.area}</b> {f.message}</span>
                </div>))}
            </div>)}
          {r.assessment.suggested_execution?.length > 0 && (
            <div className="text-xs text-text-secondary"><b className="text-text-primary">Suggested execution:</b> {r.assessment.suggested_execution.join(' · ')}</div>)}

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
            <Card title="Price & size">
              <Row k="Last" v={`${num(r.price.last, 4)} ${ccy}`} sub={r.price.market_state?.toLowerCase()} />
              <Row k="Bid / ask" v={r.price.bid && r.price.ask ? `${num(r.price.bid, 4)} / ${num(r.price.ask, 4)}` : '—'} />
              <Row k="Quote time" v={r.price.quote_time ? r.price.quote_time.replace('T', ' ').slice(0, 16) + ' UTC' : '—'} sub={r.price.delay_minutes ? `(${r.price.delay_minutes} min delayed source)` : undefined} />
              <Row k="Quantity" v={num(r.size.quantity, 0)} />
              <Row k={`Amount (${base})`} v={num(r.size.notional_base, 0)} sub={`${num(r.size.notional_local, 0)} ${ccy}`} />
              <Row k="Weight before → after" v={`${pct(r.size.weight_before, 2)} → ${pct(r.size.weight_after, 2)}`} />
              <Row k="Cash after" v={pct(r.size.cash_weight_after, 1)} />
              {r.size.sector && <Row k={`${r.size.sector} after`} v={pct(r.size.sector_weight_after, 1)} />}
            </Card>
            <Card title="Liquidity (observed)">
              {r.liquidity.available ? <>
                <Row k="ADV 20d / 30d (shares)" v={`${num(r.liquidity.adv20_shares, 0)} / ${num(r.liquidity.adv30_shares, 0)}`} />
                <Row k={`ADTV 20d / 30d (${base})`} v={`${num(r.liquidity.adtv20_base, 0)} / ${num(r.liquidity.adtv30_base, 0)}`} />
                <Row k="Order vs ADV20" v={pct(r.liquidity.order_pct_adv20, 2)} />
                <Row k="Participation cap" v={pct(r.liquidity.participation_cap, 0)} />
                <Row k="Sessions at the cap" v={num(r.liquidity.sessions_at_cap, 0)} />
                <Row k="Market cap" v={r.security.market_cap ? num(r.security.market_cap / 1e9, 1) + 'bn ' + ccy.replace('GBp', 'GBP') : '—'} />
              </> : <div className="text-2xs text-text-tertiary">Not enough volume history.</div>}
            </Card>
            <Card title="Estimated costs (one way)">
              <Row k="Half-spread" v={bp(r.costs.half_spread_bps?.value)} sub={r.costs.half_spread_bps?.basis} />
              {r.costs.impact_bps && <Row k="Market impact (staged)" v={bp(r.costs.impact_bps.staged_at_cap)} sub={`single session ${bp(r.costs.impact_bps.single_session)} · model estimate`} />}
              <Row k="Commission" v={bp(r.costs.commission_bps?.value)} sub="fund assumption" />
              <Row k="Transfer taxes" v={bp(r.costs.taxes_bps?.value)} sub={r.costs.taxes_bps?.basis} />
              <Row k="FX conversion" v={bp(r.costs.fx_conversion_bps?.value)} sub={r.costs.fx_conversion_bps?.basis} />
              <Row k="Total" v={<b>{bp(r.costs.total_bps)}</b>} sub={`≈ ${num(r.costs.total_base, 0)} ${base}`} />
            </Card>
            <Card title={`Technicals (vs ${r.technicals?.benchmark ?? 'benchmark'})`}>
              {r.technicals?.available ? <>
                <Row k="RSI(14)" v={num(r.technicals.rsi14, 0)} />
                <Row k="vs SMA 20 / 50 / 200" v={`${spct(r.technicals.vs_sma20)} / ${spct(r.technicals.vs_sma50)} / ${spct(r.technicals.vs_sma200)}`} />
                <Row k="Trend" v={r.technicals.trend ?? '—'} />
                <Row k="MACD" v={r.technicals.macd?.state ?? '—'} />
                <Row k="Bollinger %B" v={num(r.technicals.bollinger?.pct_b, 2)} />
                <Row k="ATR(14)" v={pct(r.technicals.atr14_pct, 2)} sub="of price" />
                <Row k="Volatility 20d / 60d" v={`${pct(r.technicals.vol20, 0)} / ${pct(r.technicals.vol60, 0)}`} />
                <Row k="Volume vs 60d / today z" v={`${spct(r.technicals.volume_trend, 0)} / ${num(r.technicals.volume_z, 1)}`} />
                <Row k="52-week range" v={`${num(r.technicals.levels?.low52w, 2)} – ${num(r.technicals.levels?.high52w, 2)}`} sub={`(${spct(r.technicals.from_52w_high)} from high)`} />
                <Row k="Relative strength 3/6/12m" v={['3m', '6m', '12m'].map((k) => spct(r.technicals.relative_strength_vs_benchmark?.[k])).join(' / ')} />
                <Row k="Max drawdown 1y / 5y" v={`${pct(r.technicals.max_drawdown_1y, 0)} / ${pct(r.technicals.max_drawdown_5y, 0)}`} />
              </> : <div className="text-2xs text-text-tertiary">{r.technicals?.reason ?? 'Unavailable.'}</div>}
            </Card>
            <Card title={`Events to ${r.events.window_end}`}>
              <Row k="Next earnings" v={r.events.next_earnings?.date ?? '—'} sub={r.events.next_earnings?.date ? 'listed date (confirm with IR)' : undefined} />
              <Row k="Ex-dividend" v={r.events.ex_dividend?.upcoming ? r.events.ex_dividend.date : '—'} />
              {(r.events.central_banks ?? []).map((b: any) => <Row key={b.bank} k={b.bank} v={b.date ?? '—'} sub={b.date ? (b.consensus ? `cons. ${b.consensus}` : undefined) : 'date not in the free feed'} />)}
              {(r.events.macro_releases ?? []).slice(0, 6).map((m: any, i: number) => <Row key={i} k={`${m.currency} ${m.title}`} v={m.date?.slice(0, 10)} sub={m.impact} />)}
              <Row k="Exchange" v={r.events.exchange?.mic ?? '—'} sub={r.events.exchange?.status ? `${r.events.exchange.status}${r.events.exchange.holidays_in_window?.length ? ` · holidays: ${r.events.exchange.holidays_in_window.map((h: any) => h.date).join(', ')}` : ''}` : r.events.exchange?.note} />
            </Card>
            <Card title="Mandate">
              {(r.mandate?.checks ?? []).map((c: any) => (
                <div key={c.rule} className={cn('text-2xs py-0.5 flex justify-between gap-2', c.passed ? 'text-text-secondary' : 'text-red')}>
                  <span>{c.passed ? '✓' : '✗'} {c.rule}</span><span className="font-mono text-right">{c.detail}</span>
                </div>))}
              <div className="text-2xs text-text-tertiary mt-1">Developed-market listing checked; MSCI World membership itself is licensed data ({r.security.msci_world_membership}).</div>
            </Card>
          </div>

          {r.pitch && (
            <Card title={`Pitch #${r.pitch.id} · ${r.pitch.status} · v${r.pitch.version} · ${r.pitch.analyst}`}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4">
                <Row k="Bear / base / bull" v={`${num(r.pitch.valuation.bear)} / ${num(r.pitch.valuation.base)} / ${num(r.pitch.valuation.bull)}`} />
                <Row k="Probability-weighted value" v={num(r.pitch.valuation.expected_value)} />
                <Row k="Expected return" v={spct(r.pitch.valuation.expected_return)} sub={`${spct(r.pitch.valuation.annualised_expected_return)} a year over ${r.pitch.horizon_years}y`} />
                <Row k="Reward / risk" v={num(r.pitch.valuation.reward_to_risk, 2)} />
                <Row k="Entry range" v={r.pitch.entry_range ? `${num(r.pitch.entry_range.low)} – ${num(r.pitch.entry_range.high)}` : '—'} sub={r.pitch.valuation.in_entry_range == null ? undefined : r.pitch.valuation.in_entry_range ? 'price inside' : 'price outside'} />
                <Row k="Target weight" v={pct(r.pitch.target_weight, 1)} />
                <Row k="PMC decision" v={r.pitch.decided_by ? `${r.pitch.decided_by} ${String(r.pitch.decided_at).slice(0, 10)}` : '—'} />
              </div>
              <div className="mt-1 text-2xs">
                {(r.pitch.kill_criteria ?? []).map((k: any, i: number) => (
                  <span key={i} className={cn('mr-3', k.status === 'triggered' ? 'text-red' : k.status === 'ok' ? 'text-green' : 'text-text-tertiary')}>
                    {k.status === 'triggered' ? '✗' : k.status === 'ok' ? '✓' : '·'} {k.description || k.type}{k.observed != null ? ` (${typeof k.observed === 'number' ? num(k.observed, 3) : k.observed})` : ''}
                  </span>))}
              </div>
            </Card>)}
          <div className="text-2xs text-text-tertiary">{r.costs.note} Generated {String(r.generated_at).replace('T', ' ').slice(0, 19)} UTC.</div>
        </div>)}
    </section>
  );
}

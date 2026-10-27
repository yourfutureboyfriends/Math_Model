/**
 * Position Manager — "I'm in: hold, tighten, trim, add or exit?" for every stock in the book, or any position you
 * enter, from technicals, fundamentals and news. Each call shows the stop in force, the R-multiple and the signals
 * behind it, each with its evidence and source. The exit-rule evidence table shows how the rules compare on the
 * same entries over ten years — the reason the defaults are what they are.
 * Reads /api/v1/stock/positions/manage, POST /api/v1/stock/manage, /api/v1/stock/exit-evidence
 * (rules: api/calculations/trade_management.py).
 */
import { Fragment, useCallback, useEffect, useState } from 'react';
import { Loader2, LogOut } from 'lucide-react';
import { cn } from '@/lib/utils';

const ACTION_TONE: Record<string, string> = {
  EXIT: 'bg-red text-white', TRIM: 'bg-amber text-bg', TIGHTEN: 'border border-amber text-amber',
  HOLD: 'border border-border text-text-secondary', ADD: 'bg-green text-white',
};
const px = (v?: number | null) => (v == null ? '—' : v.toLocaleString('en-US', { maximumFractionDigits: v >= 1000 ? 0 : 2 }));
const pc = (v?: number | null, d = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);

function Badge({ a }: { a?: string }) {
  return <span className={cn('inline-block px-1.5 py-0.5 text-[10px] font-mono font-bold tracking-wider', ACTION_TONE[a ?? ''] ?? 'border border-border text-text-tertiary')}>{a ?? '—'}</span>;
}

function Signals({ r }: { r: any }) {
  return (
    <div className="space-y-1">
      {(r.signals ?? []).map((s: any, i: number) => (
        <div key={i} className="flex items-start gap-2 text-[11px]">
          <Badge a={s.action} />
          <span className="flex-1 text-text-secondary">{s.evidence}</span>
          <span className="text-[10px] text-text-tertiary whitespace-nowrap">{s.source}</span>
        </div>
      ))}
      {!(r.signals ?? []).length && <div className="text-[11px] text-text-tertiary">No warnings: the trend is intact and nothing argues against holding.</div>}
    </div>
  );
}

function Detail({ r }: { r: any }) {
  const tones = r.news?.items ?? [];
  return (
    <div className="p-3 bg-surface-1 border border-border space-y-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <Badge a={r.action} />
        <span className="text-sm font-semibold text-text-primary">{r.label}</span>
        <span className="text-xs text-text-secondary">{r.name} · {r.symbol} · {r.side} from {px(r.entry_price)} on {r.entry_date}{r.entry_date_assumed ? ' (date assumed)' : ''}</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-[11px]">
        <span className="text-text-tertiary">Price <span className="block font-mono text-text-primary">{px(r.price)} {r.currency}</span></span>
        <span className="text-text-tertiary">Stop in force <span className="block font-mono text-red">{px(r.stop)}</span><span className="text-[10px]">{r.stop_basis}</span></span>
        <span className="text-text-tertiary">Distance <span className="block font-mono text-text-primary">{pc(r.stop_distance_pct)}</span></span>
        <span className="text-text-tertiary">R-multiple <span className={cn('block font-mono', (r.r_multiple ?? 0) >= 0 ? 'text-green' : 'text-red')}>{r.r_multiple != null ? `${r.r_multiple > 0 ? '+' : ''}${r.r_multiple}R` : '—'}</span></span>
        <span className="text-text-tertiary">200-day avg <span className="block font-mono text-text-primary">{px(r.stops?.sma200)}</span>{r.money_at_risk != null && <span className="text-[10px]">at risk {px(r.money_at_risk)}</span>}</span>
      </div>
      <Signals r={r} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1 border-t border-border-subtle">
        <div>
          <div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">News, last {r.news?.window_days ?? 14} days {r.news?.avg_tone != null && <span className={cn('normal-case font-mono', r.news.avg_tone > 0.1 ? 'text-green' : r.news.avg_tone < -0.1 ? 'text-red' : '')}>· tone {r.news.avg_tone > 0 ? '+' : ''}{r.news.avg_tone}</span>}</div>
          {r.news?.available === false ? <div className="text-[11px] text-text-tertiary">{r.news.reason}</div> : (
            <ul className="space-y-0.5 max-h-36 overflow-y-auto">
              {tones.slice(0, 8).map((n: any, i: number) => (
                <li key={i} className="text-[11px] flex gap-1.5">
                  <span className={cn('font-mono w-9 shrink-0 text-right', n.sentiment > 0 ? 'text-green' : n.sentiment < 0 ? 'text-red' : 'text-text-tertiary')}>{n.sentiment > 0 ? '+' : ''}{n.sentiment}</span>
                  <a href={n.url} target="_blank" rel="noreferrer noopener" className="text-text-secondary hover:text-bloomberg truncate">{n.title}</a>
                </li>
              ))}
              {!tones.length && <li className="text-[11px] text-text-tertiary">No headlines in the window.</li>}
            </ul>
          )}
        </div>
        <div>
          <div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">Insiders (open market, 6 months)</div>
          {r.insiders?.available ? (
            <div className="text-[11px] text-text-secondary">
              {r.insiders.buyers_6m ?? 0} buyer(s), {r.insiders.open_market_buys_6m ? px(r.insiders.open_market_buys_6m) : 0} bought ·
              sales {r.insiders.open_market_sales_6m ? px(r.insiders.open_market_sales_6m) : 0}
              <div className="text-[10px] text-text-tertiary mt-0.5">Buying by two or more insiders is informative (Cohen, Malloy &amp; Pomorski, 2012); sales are mostly for liquidity and carry little signal (Lakonishok &amp; Lee, 2001).</div>
            </div>
          ) : <div className="text-[11px] text-text-tertiary">{r.insiders?.reason ?? 'n/a'}</div>}
          {r.entry_model?.verdict && <div className="text-[11px] text-text-tertiary mt-2">Entry model today: <span className="text-text-secondary">{r.entry_model.verdict.label}</span></div>}
        </div>
      </div>
    </div>
  );
}

const GRADE_TONE: Record<string, string> = { good: 'border-green/60 bg-green/5 text-green', fair: 'border-amber/60 bg-amber/5 text-amber', poor: 'border-red/60 bg-red/5 text-red' };

/** The model's recommended entry, and the grade of the price you chose (planned, or paid on a date). */
function EntryCheck({ e }: { e: any }) {
  const r = e.recommended ?? {}, y = e.your_price, t = e.at_entry_date;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
      <div className="p-3 bg-surface-1 border border-border">
        <div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">Where the model would get in — {e.symbol} {e.side}</div>
        <div className="text-xs font-semibold text-text-primary">{r.verdict?.label ?? '—'}</div>
        <div className="text-[11px] text-text-secondary mb-2">{r.verdict?.detail}</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          <span className="text-text-tertiary">Buy zone</span><span className="font-mono text-right text-text-primary">{px(r.entry_low)} – {px(r.entry_high)}</span>
          <span className="text-text-tertiary">Price now</span><span className="font-mono text-right">{px(r.price)} {r.currency}</span>
          <span className="text-text-tertiary">Stop</span><span className="font-mono text-right text-red">{px(r.stop)}</span>
          <span className="text-text-tertiary" title={r.target_basis}>Objective</span><span className="font-mono text-right text-green">{px(r.target)}</span>
          <span className="text-text-tertiary">Reward : risk</span><span className="font-mono text-right">{r.reward_risk ?? '—'}</span>
          {r.shares != null && <><span className="text-text-tertiary">Size (0.5% NAV at risk)</span><span className="font-mono text-right">{r.shares.toLocaleString()} sh</span></>}
          {r.fill_probability_at_zone_top != null && <><span className="text-text-tertiary">Chance the zone is reached (20 sessions)</span><span className="font-mono text-right">{Math.round(r.fill_probability_at_zone_top * 100)}%</span></>}
        </div>
        {r.note && <div className="text-[10px] text-text-tertiary mt-1">{r.note}</div>}
      </div>
      {y ? (
        <div className={cn('p-3 border', GRADE_TONE[y.grade] ?? 'border-border')}>
          <div className="text-[10px] uppercase tracking-wider mb-1 opacity-80">Your price {px(y.price)}</div>
          <div className="text-sm font-semibold">{y.label}</div>
          <ul className="mt-1 space-y-0.5 text-[11px] text-text-secondary list-disc pl-4">{y.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
          <div className="grid grid-cols-3 gap-2 mt-2 text-[11px] text-text-tertiary">
            <span>Stop <span className="block font-mono text-red">{px(y.stop)}</span></span>
            <span>Objective <span className="block font-mono text-green">{px(y.target)}</span></span>
            <span>Reward:risk <span className="block font-mono text-text-primary">{y.reward_risk ?? '—'}</span></span>
          </div>
          {t?.verdict && <div className="text-[10px] text-text-tertiary mt-2">{t.verdict}</div>}
        </div>
      ) : (
        <div className="p-3 bg-surface-1 border border-border text-[11px] text-text-tertiary">Enter a price to have it graded — inside or outside the zone, reward:risk at your price, and the chance a limit order there fills.</div>
      )}
    </div>
  );
}

function Evidence() {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    let alive = true, t: ReturnType<typeof setTimeout>;
    const load = () => fetch('/api/v1/stock/exit-evidence').then((r) => r.json()).then((j) => {
      if (!alive) return;
      setD(j);
      if (j.running) t = setTimeout(load, 8000);
    }).catch(() => { /* optional */ });
    load();
    return () => { alive = false; clearTimeout(t); };
  }, []);
  const res = d?.result;
  if (!res) return <div className="text-[11px] text-text-tertiary">{d?.running ? 'Running the exit-rule comparison (about a minute)…' : d?.error ? `Comparison failed: ${d.error}` : 'Loading…'}</div>;
  const best = Math.max(...res.rules.map((r: any) => r.return_per_year_held ?? -1));
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead><tr className="text-[10px] text-text-tertiary text-left">
            <th className="font-normal pb-1">Exit rule (same entries)</th><th className="font-normal text-right">Trades</th><th className="font-normal text-right">Win rate</th>
            <th className="font-normal text-right">Avg / trade</th><th className="font-normal text-right">Profit factor</th><th className="font-normal text-right">Worst</th>
            <th className="font-normal text-right" title="Sum of trade returns per year of capital in trades">Return / yr held</th>
            <th className="font-normal text-right" title="Profit factor in the first / second half of the period">PF halves</th></tr></thead>
          <tbody>
            {res.rules.map((r: any) => (
              <tr key={r.rule} className={cn('border-t border-border-subtle', r.rule === 'trend' && 'bg-bloomberg/5')}>
                <td className="py-1 text-text-secondary">{r.label}{r.rule === 'trend' && <span className="ml-1 text-[9px] text-bloomberg font-mono">DEFAULT</span>}</td>
                <td className="text-right font-mono">{r.trades}</td>
                <td className="text-right font-mono">{r.win_rate != null ? `${Math.round(r.win_rate * 100)}%` : '—'}</td>
                <td className="text-right font-mono">{pc(r.avg_return)}</td>
                <td className="text-right font-mono text-text-primary">{r.profit_factor ?? '—'}</td>
                <td className="text-right font-mono text-red">{pc(r.worst, 0)}</td>
                <td className={cn('text-right font-mono', r.return_per_year_held === best ? 'text-green' : 'text-text-primary')}>{pc(r.return_per_year_held)}</td>
                <td className="text-right font-mono text-text-tertiary">{r.first_half?.profit_factor ?? '—'} / {r.second_half?.profit_factor ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-[10px] text-text-tertiary mt-1">{res.universe?.length} large caps, {res.period}, {(res.cost_round_trip * 100).toFixed(1)}% round-trip cost, computed {String(res.computed_at).slice(0, 10)}. {res.caveat}</div>
    </div>
  );
}

export function PositionManagerSection() {
  const [book, setBook] = useState<any>(null);
  const [bookBusy, setBookBusy] = useState(false);
  const [src, setSrc] = useState<'fund' | 'futu'>('fund');      // the fund's book, or the Futu account (read-only)
  const [bookErr, setBookErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [form, setForm] = useState({ symbol: '', entry_price: '', entry_date: '', side: 'long', quantity: '' });
  const [mode, setMode] = useState<'plan' | 'held'>('plan');
  const [check, setCheck] = useState<any>(null);
  const [entry, setEntry] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const loadBook = useCallback(async () => {
    setBookBusy(true); setBookErr(null);
    try {
      const r = await fetch(src === 'futu' ? '/api/v1/futu/positions/manage' : '/api/v1/stock/positions/manage');
      const j = await r.json();
      if (!r.ok) { setBookErr(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`); setBook({ positions: [] }); }
      else setBook(j);
    } catch { setBook({ positions: [] }); }
    finally { setBookBusy(false); }
  }, [src]);
  useEffect(() => { loadBook(); }, [loadBook]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null); setCheck(null); setEntry(null);
    const post = async (url: string, body: any) => {
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`);
      return j;
    };
    try {
      const price = form.entry_price ? Number(form.entry_price) : null;
      if (mode === 'plan') {
        setEntry(await post('/api/v1/stock/entry-check', { symbol: form.symbol.trim(), price, side: form.side }));
      } else {
        if (!price) throw new Error('Enter the price you paid.');
        const [ec, mg] = await Promise.all([
          post('/api/v1/stock/entry-check', { symbol: form.symbol.trim(), price, side: form.side, date: form.entry_date || null, held: true }),
          post('/api/v1/stock/manage', { symbol: form.symbol.trim(), entry_price: price, entry_date: form.entry_date || null, side: form.side,
            quantity: form.quantity ? Number(form.quantity) : null })]);
        if (mg.available === false) throw new Error(mg.reason);
        setEntry(ec); setCheck(mg);
      }
    } catch (e2: any) { setErr(e2?.message || 'Could not analyse the position'); } finally { setBusy(false); }
  };

  const rows: any[] = book?.positions ?? [];
  return (
    <section id="position-manager" className="terminal-section">
      <div className="section-header !justify-start gap-2">
        <span className="section-tag"><LogOut className="w-3 h-3" /></span>
        <h2 className="section-title">Position Manager</h2>
        <span className="text-2xs text-text-tertiary hidden md:inline">hold, tighten, trim, add or exit — from technicals, fundamentals and news</span>
        {book?.summary && rows.length > 0 && <span className="ml-auto text-2xs font-mono text-text-tertiary">{book.summary.EXIT} exit · {book.summary.TRIM} trim · {book.summary.TIGHTEN} tighten · {book.summary.ADD} add · {book.summary.HOLD} hold</span>}
      </div>

      <div className="p-2 space-y-2">
        {/* Book */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-primary">The book</span>
            <div className="flex border border-border" role="tablist" aria-label="Positions source">
              {([['fund', 'Fund book'], ['futu', 'Futu account']] as const).map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={src === k} onClick={() => { setSrc(k); setOpen(null); }}
                  className={cn('px-2 py-0.5 text-[10.5px]', src === k ? 'bg-bloomberg text-bg' : 'text-text-secondary')}>{label}</button>))}
            </div>
            {bookBusy && <Loader2 className="w-3 h-3 animate-spin text-text-tertiary" />}
            <button type="button" onClick={loadBook} className="ml-auto text-[10px] text-text-tertiary hover:text-bloomberg">Refresh</button>
          </div>
          {src === 'futu' && book?.source && <div className="text-[10px] text-text-tertiary mb-1">{book.source} · read-only — nothing here can trade. Futu does not report purchase dates, so each is taken as 90 days ago.</div>}
          {bookErr && <div className="text-[11px] text-amber">{bookErr}</div>}
          {!bookBusy && !bookErr && rows.length === 0 && <div className="text-[11px] text-text-tertiary">{src === 'futu' ? 'No positions in the Futu account.' : "No positions in this fund's book yet — check any position below."}</div>}
          {rows.length > 0 && (
            <table className="w-full text-[11px]">
              <thead><tr className="text-[10px] text-text-tertiary text-left"><th className="font-normal pb-1">Stock</th><th className="font-normal">Action</th>
                <th className="font-normal text-right">Price</th><th className="font-normal text-right">Stop</th><th className="font-normal text-right">Distance</th>
                <th className="font-normal text-right">R</th><th className="font-normal pl-3">Why</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <Fragment key={r.symbol}>
                    <tr onClick={() => setOpen(open === r.symbol ? null : r.symbol)} className="border-t border-border-subtle cursor-pointer">
                      <td className="py-1 font-mono text-text-primary" data-symbol={r.symbol}>{r.symbol}</td>
                      <td>{r.available === false ? <span className="text-text-tertiary">{r.reason}</span> : <Badge a={r.action} />}</td>
                      <td className="text-right font-mono">{px(r.price)}</td>
                      <td className="text-right font-mono text-red">{px(r.stop)}</td>
                      <td className="text-right font-mono">{pc(r.stop_distance_pct)}</td>
                      <td className={cn('text-right font-mono', (r.r_multiple ?? 0) >= 0 ? 'text-green' : 'text-red')}>{r.r_multiple ?? '—'}</td>
                      <td className="pl-3 text-text-secondary truncate max-w-[22rem]">{r.signals?.[0]?.evidence ?? 'Trend intact'}</td>
                    </tr>
                    {open === r.symbol && r.available !== false && <tr><td colSpan={7} className="pb-2"><Detail r={r} /></td></tr>}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Check a position */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-primary">Check an entry or a position</span>
            <div className="flex border border-border" role="tablist" aria-label="Mode">
              {([['plan', "I'm planning to buy"], ['held', 'I already hold it']] as const).map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={mode === k} onClick={() => { setMode(k); setCheck(null); setEntry(null); }}
                  className={cn('px-2 py-0.5 text-[10.5px]', mode === k ? 'bg-bloomberg text-bg' : 'text-text-secondary')}>{label}</button>
              ))}
            </div>
          </div>
          <form onSubmit={submit} className="flex flex-wrap items-end gap-2 text-[11px]">
            <label className="flex flex-col gap-0.5"><span className="text-text-tertiary">Ticker</span>
              <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} required placeholder="NVDA"
                className="w-24 bg-bg border border-border px-1.5 py-1 font-mono uppercase text-text-primary" /></label>
            <label className="flex flex-col gap-0.5"><span className="text-text-tertiary">{mode === 'plan' ? 'Your price (optional)' : 'Price you paid'}</span>
              <input value={form.entry_price} onChange={(e) => setForm({ ...form, entry_price: e.target.value })} required={mode === 'held'} inputMode="decimal"
                className="w-24 bg-bg border border-border px-1.5 py-1 font-mono text-text-primary" /></label>
            {mode === 'held' && <label className="flex flex-col gap-0.5"><span className="text-text-tertiary">Date bought</span>
              <input type="date" value={form.entry_date} onChange={(e) => setForm({ ...form, entry_date: e.target.value })}
                className="bg-bg border border-border px-1.5 py-0.5 font-mono text-text-primary" /></label>}
            <label className="flex flex-col gap-0.5"><span className="text-text-tertiary">Side</span>
              <select value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })} className="bg-bg border border-border px-1 py-1 text-text-primary">
                <option value="long">Long</option><option value="short">Short</option></select></label>
            {mode === 'held' && <label className="flex flex-col gap-0.5"><span className="text-text-tertiary">Shares (optional)</span>
              <input value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} inputMode="decimal"
                className="w-24 bg-bg border border-border px-1.5 py-1 font-mono text-text-primary" /></label>}
            <button type="submit" disabled={busy} className="px-3 py-1 bg-bloomberg text-bg disabled:opacity-50 inline-flex items-center gap-1">
              {busy && <Loader2 className="w-3 h-3 animate-spin" />}Analyse</button>
          </form>
          {err && <div className="mt-2 text-[11px] text-amber">{err}</div>}
          {entry && <div className="mt-2"><EntryCheck e={entry} /></div>}
          {check && <div className="mt-2"><div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">What to do now</div><Detail r={check} /></div>}
        </div>

        {/* Evidence */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-xs font-semibold uppercase tracking-wider text-text-primary mb-2">Why these exit rules — the evidence</div>
          <Evidence />
        </div>
        <div className="text-[10px] text-text-tertiary">
          Exits: 200-day trend break with a 2.5×ATR initial stop (Faber 2007; Kaminski &amp; Lo 2014); warnings tighten the stop to the chandelier level
          (LeBeau): analyst cuts (Chan, Jegadeesh &amp; Lakonishok 1996), an earnings miss (Bernard &amp; Thomas 1989), negative news tone (Tetlock 2007),
          a volatility spike (Moreira &amp; Muir 2017), a risk-off market (Daniel &amp; Moskowitz 2016). Not investment advice; signals are probabilistic.
        </div>
      </div>
    </section>
  );
}

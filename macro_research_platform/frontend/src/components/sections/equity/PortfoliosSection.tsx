// Portfolios — two books side by side plus an optimiser:
//   * My Portfolio: the stocks you choose, each reviewed by the entry model (action, trailing
//     stop, trend) — you decide what to do;
//   * Auto Portfolio: a systematic PAPER book that trades the model's BUY signals by itself
//     (next-open fills, 2.5×ATR stop, 2R target, 63-day time stop, drawdown control and
//     volatility targeting) — simulated, never routes real orders;
//   * Optimiser: six weighting methods on either book or any tickers, ranked walk-forward.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, Briefcase, Loader2, Play, Plus, RefreshCw, Scale, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { openStockAnalysis } from './StockIdeasSection';

const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#8a63d2', '#d0457a', '#6b7280'];
const usd = (v: number | null | undefined, d = 0) =>
  v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d })}`;
const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
const spct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const num = (v: number | null | undefined, d = 2) => (v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: d }));
const TONE: Record<string, string> = { good: 'text-green border-green/40', bad: 'text-red border-red/40', neutral: 'text-text-secondary border-border' };

async function getJSON(url: string, init?: RequestInit) {
  const r = await fetch(url, init);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : j?.detail?.message || `HTTP ${r.status}`);
  return j;
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="px-3 py-2 bg-surface-1 border border-border min-w-[7.5rem]">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className={cn('font-mono text-sm', tone)}>{value}</div>
      {sub && <div className="text-[10px] text-text-tertiary">{sub}</div>}
    </div>
  );
}

// ── My Portfolio ──────────────────────────────────────────────────────────────
function MyPortfolio() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ symbol: '', quantity: '', avg_cost: '' });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await getJSON('/api/v1/portfolio/model-review')); setErr(null); }
    catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = async () => {
    const q = Number(form.quantity), c = Number(form.avg_cost);
    if (!form.symbol.trim() || !Number.isFinite(q) || q === 0 || !Number.isFinite(c) || c <= 0) {
      setErr('Enter a ticker, a non-zero quantity and an average cost.'); return;
    }
    setSaving(true);
    try {
      await getJSON('/api/v1/portfolio/positions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: form.symbol.trim().toUpperCase(), quantity: q, avg_cost: c, asset_class: 'Equity', book: 'Discretionary' }),
      });
      setForm({ symbol: '', quantity: '', avg_cost: '' });
      await load();
    } catch (e: any) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const rows: any[] = data?.holdings ?? [];
  const counts = data?.counts ?? {};
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-2 px-3 py-2 bg-surface-1 border border-border">
        <span className="text-2xs text-text-tertiary mr-1">Add a stock you hold</span>
        {(['symbol', 'quantity', 'avg_cost'] as const).map((k) => (
          <input key={k} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })}
            placeholder={k === 'symbol' ? 'Ticker (e.g. AAPL, 7203.T)' : k === 'quantity' ? 'Shares' : 'Avg cost'}
            aria-label={k} className="bg-bg border border-border px-1.5 py-0.5 text-2xs font-mono w-36" />
        ))}
        <button onClick={add} disabled={saving} className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs border border-bloomberg text-bloomberg disabled:opacity-60">
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />} Add
        </button>
        <button onClick={load} className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 text-2xs border border-border text-text-secondary hover:text-bloomberg">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Re-review
        </button>
      </div>
      {err && <div className="p-2 text-xs text-amber border border-amber/30">{err}</div>}
      {data && rows.length === 0 && <div className="p-3 text-xs text-text-secondary border border-border-subtle">{data.reason ?? 'No holdings.'}</div>}
      {rows.length > 0 && (
        <>
          <div className="flex flex-wrap gap-2">
            <Tile label="Holdings" value={String(rows.length)} sub={`net ${usd(data.total_usd)} · gross ${usd(data.gross_usd)}`} />
            <Tile label="Exit / cover" value={String((counts.exit ?? 0) + (counts.cover ?? 0))} tone={(counts.exit ?? 0) + (counts.cover ?? 0) > 0 ? 'text-red' : undefined} />
            <Tile label="Hold / add" value={String(counts.add ?? 0)} tone="text-green" />
            <Tile label="Hold" value={String(['hold_extended', 'hold_riskoff', 'watch', 'hold_short', 'watch_short'].reduce((n, k) => n + (counts[k] ?? 0), 0))} />
          </div>
          <div className="overflow-x-auto border border-border">
            <table className="w-full text-2xs font-mono">
              <thead className="bg-surface-1"><tr className="text-text-tertiary text-left">
                <th className="font-normal font-sans px-2 py-1">Holding</th><th className="font-normal text-right px-2">Weight</th>
                <th className="font-normal text-right px-2">Value</th><th className="font-normal text-right px-2">P&amp;L</th>
                <th className="font-normal font-sans px-2">Model action</th><th className="font-normal text-right px-2">Set-up</th>
                <th className="font-normal text-right px-2" title="2.5 × ATR(14) below the last price (above it for a short)">Trailing stop</th>
                <th className="font-normal font-sans px-2">Trend</th>
              </tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol} className="border-t border-border-subtle align-top">
                    <td className="px-2 py-1 font-sans">
                      <button onClick={() => openStockAnalysis(r.symbol)} className="text-text-primary hover:text-bloomberg font-mono">{r.symbol}</button>
                      {r.side === 'Short' && <span className="ml-1 px-1 border border-amber/50 text-amber text-[10px]">Short</span>}
                      <div className="text-[10px] text-text-tertiary truncate max-w-[12rem]">{r.name ?? r.reason ?? ''}</div>
                    </td>
                    <td className="text-right px-2">{pct(r.weight)}</td>
                    <td className="text-right px-2">{usd(r.market_value_usd)}</td>
                    <td className={cn('text-right px-2', (r.pnl_pct ?? 0) >= 0 ? 'text-green' : 'text-red')}>{spct(r.pnl_pct)}</td>
                    <td className="px-2 font-sans">
                      <span className={cn('px-1 border whitespace-nowrap', TONE[r.tone] ?? TONE.neutral)}>{r.action_label}</span>
                      {r.verdict_label && <div className="text-[10px] text-text-tertiary mt-0.5 max-w-[16rem]">{r.verdict_label}</div>}
                    </td>
                    <td className="text-right px-2">{num(r.setup_score)}</td>
                    <td className="text-right px-2">{num(r.trailing_stop)}<div className="text-[10px] text-text-tertiary">{r.stop_distance_pct != null ? `${r.side === 'Short' ? '+' : '-'}${pct(r.stop_distance_pct)}` : ''}</div></td>
                    <td className="px-2 font-sans text-[10px] text-text-secondary max-w-[16rem]">{r.trend ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="text-[10px] text-text-tertiary">The model times entries; for holdings it flags exits when the evidence turns negative or the long-term trend breaks (price below the 200-day with the 50-day below it, Faber 2007). Shorts are mirrored — a strong up-trend says cover. Trailing stop: 2.5 × ATR(14). Weights are shares of gross exposure. Decisions stay yours.</div>
        </>
      )}
    </div>
  );
}

// ── Auto Portfolio ────────────────────────────────────────────────────────────
function AutoPortfolio() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [edit, setEdit] = useState<any>(null);

  const load = useCallback(async () => {
    try { setData(await getJSON('/api/v1/auto/status')); setErr(null); } catch (e: any) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);

  const act = async (label: string, url: string, init: RequestInit) => {
    setBusy(label);
    try { await getJSON(url, init); await load(); setEdit(null); } catch (e: any) { setErr(e.message); }
    finally { setBusy(null); }
  };
  const s = data?.settings;
  const navRows = useMemo(() => (data?.nav ?? []).map((n: any) => ({ date: n.date, equity: n.equity / (s?.capital || 1) })), [data, s]);

  if (!data) return err ? <div className="p-2 text-xs text-amber border border-amber/30">{err}</div>
    : <div className="p-3 text-xs text-text-secondary flex items-center gap-2"><Loader2 className="w-3.5 h-3.5 animate-spin" />Loading the auto book…</div>;

  const st = data.stats ?? {};
  const risk = data.risk ?? {};
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-surface-1 border border-border text-2xs">
        <span className="px-1.5 py-0.5 border border-amber/50 text-amber uppercase tracking-wide">Paper — simulated, no real orders</span>
        <span className={cn('px-1.5 py-0.5 border', s?.enabled ? 'border-green/50 text-green' : 'border-border text-text-tertiary')}>
          {s?.enabled ? 'Auto-trading on' : 'Auto-trading off'}
        </span>
        {data.paused && <span className="px-1.5 py-0.5 border border-red/50 text-red">Paused — drawdown limit</span>}
        <span className="text-text-tertiary">Runs after each US close (22:20 UTC) · last run {data.last_run ? new Date(data.last_run).toLocaleString() : 'never'}</span>
        <span className="text-text-tertiary">· ideas {data.ideas?.fresh ? 'fresh' : 'stale'}</span>
        <div className="ml-auto flex gap-1.5">
          <button onClick={() => act('toggle', '/api/v1/auto/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: !s?.enabled }) })}
            disabled={!!busy} className="px-2 py-0.5 border border-border text-text-secondary hover:text-bloomberg disabled:opacity-60">{s?.enabled ? 'Turn off' : 'Turn on'}</button>
          <button onClick={() => act('run', '/api/v1/auto/run', { method: 'POST' })} disabled={!!busy}
            className="inline-flex items-center gap-1 px-2 py-0.5 border border-bloomberg text-bloomberg disabled:opacity-60">
            {busy === 'run' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />} Run now
          </button>
          <button onClick={() => setEdit(edit ? null : { ...s })} className="px-2 py-0.5 border border-border text-text-secondary hover:text-bloomberg">Settings</button>
        </div>
      </div>
      {err && <div className="p-2 text-xs text-amber border border-amber/30">{err}</div>}

      {edit && (
        <div className="px-3 py-2 bg-surface-1 border border-border grid gap-2 sm:grid-cols-3 lg:grid-cols-5 text-2xs">
          {([['risk_per_trade', 'Risk per trade', 0.001], ['max_positions', 'Max positions', 1], ['max_position', 'Max per name', 0.01],
             ['max_gross', 'Max gross', 0.05], ['max_drawdown', 'Drawdown limit', 0.01], ['vol_target', 'Volatility target', 0.01],
             ['max_per_sector', 'Max per sector', 1]] as const).map(([k, label, step]) => (
            <label key={k} className="flex flex-col gap-0.5"><span className="text-text-tertiary">{label}</span>
              <input type="number" step={step} value={edit[k] ?? ''} onChange={(e) => setEdit({ ...edit, [k]: e.target.value === '' ? null : Number(e.target.value) })}
                className="bg-bg border border-border px-1.5 py-0.5 font-mono" /></label>
          ))}
          <label className="flex items-center gap-1.5 mt-3"><input type="checkbox" checked={!!edit.exclude_frontier} onChange={(e) => setEdit({ ...edit, exclude_frontier: e.target.checked })} />Exclude frontier</label>
          <div className="flex items-end gap-1.5">
            <button onClick={() => {
              const keys = ['risk_per_trade', 'max_positions', 'max_position', 'max_gross', 'max_drawdown', 'vol_target', 'max_per_sector', 'exclude_frontier'];
              const body = Object.fromEntries(keys.map((k) => [k, edit[k]]));
              act('save', '/api/v1/auto/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            }}
              disabled={!!busy} className="px-2 py-0.5 border border-bloomberg text-bloomberg">Save</button>
            <button onClick={() => {
              const cap = window.prompt('Reset the paper book and start with how much virtual capital (USD)?', String(s?.capital ?? 1000000));
              if (cap && Number(cap) > 0) act('reset', '/api/v1/auto/reset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ capital: Number(cap) }) });
            }} className="px-2 py-0.5 border border-red/50 text-red">Reset book…</button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Tile label="Equity" value={usd(data.equity)} sub={`capital ${usd(s?.capital)}`} />
        <Tile label="Return" value={spct(st.total_return, 2)} tone={(st.total_return ?? 0) >= 0 ? 'text-green' : 'text-red'} />
        <Tile label="Cash" value={usd(data.cash)} sub={`gross ${pct(data.gross, 0)}`} />
        <Tile label="Drawdown" value={pct(st.drawdown, 1)} sub={`limit ${pct(s?.max_drawdown, 0)}`} tone={(st.drawdown ?? 0) < -0.05 ? 'text-red' : undefined} />
        <Tile label="Risk scale" value={pct(risk.scale, 0)} sub={`per trade ${pct(risk.effective_risk_per_trade, 2)}`} />
        <Tile label="Closed trades" value={String(st.closed_trades ?? 0)} sub={`hit ${pct(st.hit_rate, 0)} · avg ${st.avg_r == null ? '—' : `${st.avg_r >= 0 ? '+' : ''}${st.avg_r.toFixed(2)}R`}`} />
      </div>

      {navRows.length > 1 && (
        <div className="px-3 py-2 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary mb-1">Equity / starting capital</div>
          <LineChart rows={navRows} x="date" height={160} baseline={1} fmt={(v) => `${v.toFixed(3)}×`}
            lines={[{ key: 'equity', label: 'Auto book', color: SERIES[0] }]} />
        </div>
      )}

      <div className="grid gap-2 xl:grid-cols-2">
        <div className="border border-border">
          <div className="px-2 py-1 bg-surface-1 text-2xs text-text-tertiary border-b border-border">Open positions ({data.positions.length}) · pending orders ({data.pending.length})</div>
          <div className="overflow-x-auto"><table className="w-full text-2xs font-mono">
            <thead><tr className="text-text-tertiary text-left">
              <th className="font-normal font-sans px-2 py-1">Stock</th><th className="font-normal text-right px-2">Shares</th><th className="font-normal text-right px-2">Entry</th>
              <th className="font-normal text-right px-2">Last</th><th className="font-normal text-right px-2">Stop / target</th><th className="font-normal text-right px-2">P&amp;L</th><th></th>
            </tr></thead>
            <tbody>
              {data.positions.map((p: any) => (
                <tr key={p.id} className="border-t border-border-subtle">
                  <td className="px-2 py-1"><button onClick={() => openStockAnalysis(p.symbol)} className="hover:text-bloomberg">{p.symbol}</button>
                    <div className="text-[10px] text-text-tertiary font-sans">{p.country} · {p.sector ?? '—'} · {p.days_held}d</div></td>
                  <td className="text-right px-2">{num(p.shares, 0)}</td>
                  <td className="text-right px-2">{num(p.entry_price)}</td>
                  <td className="text-right px-2">{num(p.last)}</td>
                  <td className="text-right px-2"><span className="text-red">{num(p.stop)}</span> / <span className="text-green">{num(p.target)}</span></td>
                  <td className={cn('text-right px-2', (p.unrealized_usd ?? 0) >= 0 ? 'text-green' : 'text-red')}>{usd(p.unrealized_usd)}<div className="text-[10px]">{p.open_r == null ? '' : `${p.open_r >= 0 ? '+' : ''}${p.open_r.toFixed(2)}R`}</div></td>
                  <td className="px-1"><button title="Close at the latest close" disabled={!!busy}
                    onClick={() => window.confirm(`Close ${p.symbol} in the paper book at the latest close?`) && act('close', `/api/v1/auto/positions/${p.id}/close`, { method: 'POST' })}
                    className="text-text-tertiary hover:text-red"><X className="w-3 h-3" /></button></td>
                </tr>
              ))}
              {data.pending.map((o: any) => (
                <tr key={`o${o.id}`} className="border-t border-border-subtle text-text-tertiary">
                  <td className="px-2 py-1">{o.symbol}<div className="text-[10px] font-sans">order — fills at the next open</div></td>
                  <td className="text-right px-2">—</td><td className="text-right px-2">~{num(o.signal_price)}</td><td className="text-right px-2">—</td>
                  <td className="text-right px-2">{num(o.signal_stop)}</td><td colSpan={2} className="px-2 font-sans">set-up {num(o.setup)}</td>
                </tr>
              ))}
              {data.positions.length + data.pending.length === 0 && (
                <tr><td colSpan={7} className="px-2 py-3 text-center font-sans text-text-tertiary">No positions yet — the book buys the next fresh BUY signals in risk-on markets.</td></tr>
              )}
            </tbody>
          </table></div>
        </div>
        <div className="border border-border">
          <div className="px-2 py-1 bg-surface-1 text-2xs text-text-tertiary border-b border-border">Activity log</div>
          <div className="max-h-64 overflow-y-auto text-[10px] font-mono">
            {(data.log ?? []).map((l: any, i: number) => (
              <div key={i} className={cn('px-2 py-0.5 border-t border-border-subtle', l.level === 'warn' ? 'text-amber' : 'text-text-secondary')}>
                <span className="text-text-tertiary">{l.ts.replace('T', ' ').slice(5, 16)}</span> {l.message}
              </div>
            ))}
            {(data.log ?? []).length === 0 && <div className="px-2 py-3 text-text-tertiary font-sans">No activity yet.</div>}
          </div>
        </div>
      </div>

      {data.closed.length > 0 && (
        <div className="overflow-x-auto border border-border max-h-64">
          <table className="w-full text-2xs font-mono">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary text-left">
              <th className="font-normal font-sans px-2 py-1">Closed</th><th className="font-normal px-2">In → out</th><th className="font-normal text-right px-2">Entry / exit</th>
              <th className="font-normal font-sans px-2">Reason</th><th className="font-normal text-right px-2">P&amp;L</th><th className="font-normal text-right px-2">R</th>
            </tr></thead>
            <tbody>{data.closed.map((p: any) => (
              <tr key={p.id} className="border-t border-border-subtle">
                <td className="px-2 py-1">{p.symbol}</td><td className="px-2 text-text-tertiary">{p.entry_date} → {p.exit_date}</td>
                <td className="text-right px-2">{num(p.entry_price)} / {num(p.exit_price)}</td><td className="px-2 font-sans">{p.exit_reason}</td>
                <td className={cn('text-right px-2', (p.pnl_usd ?? 0) >= 0 ? 'text-green' : 'text-red')}>{usd(p.pnl_usd)}</td>
                <td className="text-right px-2">{p.r_multiple == null ? '—' : p.r_multiple.toFixed(2)}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      <div className="text-[10px] text-text-tertiary leading-relaxed">
        Rules: BUY signals in risk-on markets only, frontier excluded{s?.exclude_frontier ? '' : ' (currently included)'}; fill at the next session's open; {pct(s?.risk_per_trade, 2)} of equity at risk per trade,
        ≤ {pct(s?.max_position, 0)} per name, ≤ {pct(s?.max_gross, 0)} gross, ≤ {s?.max_per_sector} per sector; exits at the stop, the {s?.target_r}R target or after {s?.max_hold} sessions.
        Risk scales with the drawdown surplus (Grossman &amp; Zhou 1993) and to a {pct(s?.vol_target, 0)} volatility target (Moreira &amp; Muir 2017; Harvey et al. 2018).
        Virtual capital, separate from the fund's positions and NAV.
      </div>
    </div>
  );
}

// ── Optimiser ─────────────────────────────────────────────────────────────────
function Optimiser() {
  const [source, setSource] = useState<'my' | 'auto' | 'custom'>('my');
  const [symbols, setSymbols] = useState('');
  const [maxW, setMaxW] = useState(0.25);
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true); setErr(null);
    try {
      const q = new URLSearchParams({ source, max_weight: String(maxW) });
      if (source === 'custom') q.set('symbols', symbols);
      setData(await getJSON(`/api/v1/portfolio/optimize?${q}`));
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  };

  const methods: any[] = data?.methods ?? [];
  const best = data?.best_out_of_sample;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-surface-1 border border-border text-2xs">
        <div className="flex border border-border" role="tablist" aria-label="Optimise which holdings">
          {([['my', 'My portfolio'], ['auto', 'Auto book'], ['custom', 'Tickers']] as const).map(([k, l]) => (
            <button key={k} role="tab" aria-selected={source === k} onClick={() => setSource(k)}
              className={cn('px-2 py-0.5', source === k ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>{l}</button>
          ))}
        </div>
        {source === 'custom' && (
          <input value={symbols} onChange={(e) => setSymbols(e.target.value)} placeholder="AAPL, MSFT, XOM, 7203.T, SHEL.L"
            className="bg-bg border border-border px-1.5 py-0.5 font-mono w-72" aria-label="Tickers" />
        )}
        <label className="flex items-center gap-1 text-text-tertiary">Max per name
          <input type="number" step={0.05} min={0.05} max={1} value={maxW} onChange={(e) => setMaxW(Number(e.target.value))}
            className="bg-bg border border-border px-1.5 py-0.5 font-mono w-16" /></label>
        <button onClick={run} disabled={loading} className="inline-flex items-center gap-1 px-2 py-0.5 border border-bloomberg text-bloomberg disabled:opacity-60">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Scale className="w-3 h-3" />} {loading ? 'Optimising…' : 'Optimise'}
        </button>
        <span className="text-text-tertiary">~3 years of daily USD returns · Ledoit-Wolf covariance · walk-forward ranking</span>
      </div>
      {err && <div className="p-2 text-xs text-amber border border-amber/30">{err}</div>}
      {data && !data.available && <div className="p-3 text-xs text-text-secondary border border-border-subtle">{data.reason}</div>}
      {data?.available && (
        <>
          <div className="px-3 py-2 bg-surface-1 border border-border text-xs text-text-secondary">
            Best out of sample: <span className="text-bloomberg">{methods.find((m) => m.method === best)?.label ?? '—'}</span>.{' '}
            {data.beats_equal_weight?.length ? `${data.beats_equal_weight.length} of ${methods.length - 1} methods beat equal weight after costs.` : 'No method beat equal weight after costs — keep it simple.'}
            {data.dropped?.length ? <span className="text-amber"> Not enough history: {data.dropped.join(', ')}.</span> : null}
            {data.cap_note ? <span className="text-amber"> {data.cap_note}</span> : null}
          </div>
          <div className="overflow-x-auto border border-border">
            <table className="w-full text-2xs font-mono">
              <thead className="bg-surface-1"><tr className="text-text-tertiary text-left">
                <th className="font-normal font-sans px-2 py-1">Method</th>
                <th className="font-normal text-right px-2" title="Ex-ante annual volatility">Vol</th>
                <th className="font-normal text-right px-2" title="Weighted average volatility / portfolio volatility">Div. ratio</th>
                <th className="font-normal text-right px-2" title="1 / Σw²">Eff. N</th>
                <th className="font-normal text-right px-2 border-l border-border">OOS CAGR</th><th className="font-normal text-right px-2">OOS Sharpe</th>
                <th className="font-normal text-right px-2">OOS max DD</th><th className="font-normal text-right px-2">Turnover/yr</th>
              </tr></thead>
              <tbody>
                {data.current && (
                  <tr className="border-t border-border-subtle text-text-secondary"><td className="px-2 py-1 font-sans">Current weights</td>
                    <td className="text-right px-2">{pct(data.current.vol)}</td><td className="text-right px-2">{num(data.current.diversification_ratio)}</td>
                    <td className="text-right px-2">{num(data.current.effective_n, 1)}</td><td colSpan={4} className="border-l border-border" /></tr>
                )}
                {methods.map((m) => (
                  <tr key={m.method} className={cn('border-t border-border-subtle', m.method === best && 'bg-bloomberg/5')}>
                    <td className="px-2 py-1 font-sans text-text-primary" title={m.citation}>{m.label}{m.method === best && <span className="ml-1 text-bloomberg">★</span>}</td>
                    <td className="text-right px-2">{pct(m.vol)}</td><td className="text-right px-2">{num(m.diversification_ratio)}</td>
                    <td className="text-right px-2">{num(m.effective_n, 1)}</td>
                    <td className={cn('text-right px-2 border-l border-border', (m.walk_forward?.cagr ?? 0) >= 0 ? 'text-green' : 'text-red')}>{spct(m.walk_forward?.cagr)}</td>
                    <td className="text-right px-2">{num(m.walk_forward?.sharpe)}</td>
                    <td className="text-right px-2 text-red">{pct(m.walk_forward?.max_drawdown, 0)}</td>
                    <td className="text-right px-2 text-text-secondary">{num(m.walk_forward?.turnover_annual, 1)}×</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.curve?.length > 1 && (
            <div className="px-3 py-2 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary mb-1">Walk-forward growth of 1 (out of sample, after costs, USD)</div>
              <LineChart rows={data.curve} x="date" height={200} baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
                lines={methods.slice(0, 7).map((m, i) => ({ key: m.method, label: m.label.split(' (')[0], color: SERIES[i % SERIES.length] }))} />
            </div>
          )}
          <div className="overflow-x-auto border border-border">
            <table className="w-full text-2xs font-mono">
              <thead className="bg-surface-1"><tr className="text-text-tertiary text-left">
                <th className="font-normal font-sans px-2 py-1">Weights</th>
                {data.current && <th className="font-normal text-right px-2">Now</th>}
                {methods.map((m) => <th key={m.method} className={cn('font-normal text-right px-2', m.method === best && 'text-bloomberg')} title={m.label}>{m.label.split(' ')[0]}</th>)}
                <th className="font-normal text-right px-2" title="Entry-model set-up score (Black-Litterman view)">Set-up</th>
              </tr></thead>
              <tbody>{data.symbols.map((sym: string) => (
                <tr key={sym} className="border-t border-border-subtle">
                  <td className="px-2 py-1"><button onClick={() => openStockAnalysis(sym)} className="hover:text-bloomberg">{sym}</button></td>
                  {data.current && <td className="text-right px-2 text-text-secondary">{pct(data.current.weights[sym])}</td>}
                  {methods.map((m) => <td key={m.method} className="text-right px-2">{pct(m.weights[sym])}</td>)}
                  <td className="text-right px-2 text-text-secondary">{num(data.setup_scores?.[sym])}</td>
                </tr>))}</tbody>
            </table>
          </div>
          {data.rebalance_to_best && (
            <div className="border border-border">
              <div className="px-2 py-1 bg-surface-1 text-2xs text-text-tertiary border-b border-border">Trades to move to {methods.find((m) => m.method === best)?.label} (suggestions — nothing is executed)</div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 px-2 py-1.5 text-2xs font-mono">
                {data.rebalance_to_best.filter((t: any) => Math.abs(t.trade_usd) >= 1).map((t: any) => (
                  <span key={t.symbol}><span className="text-text-primary">{t.symbol}</span>{' '}
                    <span className={t.trade_usd >= 0 ? 'text-green' : 'text-red'}>{t.trade_usd >= 0 ? 'buy' : 'sell'} {usd(Math.abs(t.trade_usd))}</span></span>
                ))}
              </div>
            </div>
          )}
          <div className="text-[10px] text-text-tertiary leading-relaxed">
            {(data.notes ?? []).join(' ')} Methods: equal weight (DeMiguel, Garlappi &amp; Uppal 2009) · minimum variance with Ledoit-Wolf shrinkage · equal risk contribution (Maillard, Roncalli &amp; Teiletche 2010) ·
            hierarchical risk parity (López de Prado 2016) · maximum diversification (Choueifaty &amp; Coignard 2008) · Black-Litterman (Black &amp; Litterman 1992; Idzorek 2005). Long-only, fully invested, capped per name.
          </div>
        </>
      )}
    </div>
  );
}

const TABS = [
  { key: 'my', label: 'My Portfolio', Icon: Briefcase },
  { key: 'auto', label: 'Auto Portfolio (paper)', Icon: Bot },
  { key: 'opt', label: 'Optimiser', Icon: Scale },
] as const;

export function PortfoliosSection() {
  const [tab, setTab] = useState<(typeof TABS)[number]['key']>(() => {
    try { return (localStorage.getItem('portfolios.tab') as any) || 'my'; } catch { return 'my'; }
  });
  useEffect(() => { try { localStorage.setItem('portfolios.tab', tab); } catch { /* storage unavailable */ } }, [tab]);
  return (
    <div className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Briefcase className="w-3 h-3" /></span>
          <h2 className="section-title">Portfolios</h2>
          <span className="text-2xs text-text-tertiary">your picks reviewed by the model · a systematic paper book · optimisation</span>
        </div>
      </div>
      <div className="flex border border-border mb-2 w-fit" role="tablist" aria-label="Portfolio">
        {TABS.map(({ key, label, Icon }) => (
          <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
            className={cn('inline-flex items-center gap-1 px-3 py-1 text-2xs', tab === key ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>
            <Icon className="w-3 h-3" />{label}
          </button>
        ))}
      </div>
      {tab === 'my' && <MyPortfolio />}
      {tab === 'auto' && <AutoPortfolio />}
      {tab === 'opt' && <Optimiser />}
    </div>
  );
}

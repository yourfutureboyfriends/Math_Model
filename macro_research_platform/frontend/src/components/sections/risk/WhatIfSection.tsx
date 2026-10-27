/**
 * What-if scenarios — drag market moves and watch the fund's book and the US / euro-area / rest-of-world macro
 * models' portfolios respond. Sliders: equities, the 10-year yield, high-yield spreads, commodities, the dollar and
 * the VIX; presets replay approximate crisis moves. Linear factor-model estimates (POST /api/v1/risk/what-if,
 * api/what_if.py): a sense of size and direction, not a forecast.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { cn } from '@/lib/utils';

type Sliders = { equity_pct: number; rates_bp: number; credit_bp: number; commodities_pct: number; usd_pct: number; vix_pts: number };
const ZERO: Sliders = { equity_pct: 0, rates_bp: 0, credit_bp: 0, commodities_pct: 0, usd_pct: 0, vix_pts: 0 };

const SLIDERS: { key: keyof Sliders; label: string; min: number; max: number; step: number; fmt: (v: number) => string }[] = [
  { key: 'equity_pct', label: 'Equities (S&P 500)', min: -0.5, max: 0.3, step: 0.01, fmt: (v) => `${v > 0 ? '+' : ''}${Math.round(v * 100)}%` },
  { key: 'rates_bp', label: '10-year yield', min: -250, max: 250, step: 5, fmt: (v) => `${v > 0 ? '+' : ''}${v}bp` },
  { key: 'credit_bp', label: 'High-yield spread', min: -200, max: 700, step: 10, fmt: (v) => `${v > 0 ? '+' : ''}${v}bp` },
  { key: 'commodities_pct', label: 'Commodities', min: -0.5, max: 0.5, step: 0.01, fmt: (v) => `${v > 0 ? '+' : ''}${Math.round(v * 100)}%` },
  { key: 'usd_pct', label: 'US dollar', min: -0.15, max: 0.15, step: 0.005, fmt: (v) => `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%` },
  { key: 'vix_pts', label: 'VIX', min: -15, max: 50, step: 1, fmt: (v) => `${v > 0 ? '+' : ''}${v} pts` },
];

// Approximate peak-to-trough market moves (rounded) — for orientation, not exact replays
const PRESETS: { label: string; s: Sliders; note: string }[] = [
  { label: '2008 crisis', note: 'Sep 2008 – Mar 2009, rounded', s: { equity_pct: -0.4, rates_bp: -150, credit_bp: 600, commodities_pct: -0.5, usd_pct: 0.12, vix_pts: 45 } },
  { label: '2020 crash', note: 'Feb – Mar 2020, rounded', s: { equity_pct: -0.34, rates_bp: -120, credit_bp: 500, commodities_pct: -0.4, usd_pct: 0.06, vix_pts: 50 } },
  { label: '2022 rate shock', note: 'Jan – Oct 2022, rounded', s: { equity_pct: -0.25, rates_bp: 250, credit_bp: 250, commodities_pct: 0.2, usd_pct: 0.15, vix_pts: 15 } },
  { label: 'Soft landing', note: 'a benign illustration', s: { equity_pct: 0.1, rates_bp: -50, credit_bp: -50, commodities_pct: 0, usd_pct: -0.03, vix_pts: -5 } },
];

const pctS = (v?: number | null, d = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const money = (v?: number | null) => (v == null ? '—' : `${v < 0 ? '−' : '+'}${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`);
const tone = (v?: number | null) => (v == null ? 'text-text-tertiary' : v > 0.0005 ? 'text-green' : v < -0.0005 ? 'text-red' : 'text-text-secondary');

function Bars({ rows, scale }: { rows: { label: string; value: number; sub?: string }[]; scale: number }) {
  return (
    <div className="space-y-0.5">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[minmax(0,1fr)_120px_52px] items-center gap-2 text-[10.5px]" title={r.sub}>
          <span className="truncate text-text-secondary">{r.label}</span>
          <span className="relative h-2 bg-surface-3">
            <span className="absolute top-0 bottom-0 left-1/2 w-px bg-border-strong" />
            <span className={cn('absolute top-0 bottom-0', r.value < 0 ? 'bg-red/70' : 'bg-green/70')}
              style={r.value < 0 ? { right: '50%', width: `${Math.min(50, (Math.abs(r.value) / scale) * 50)}%` } : { left: '50%', width: `${Math.min(50, (r.value / scale) * 50)}%` }} />
          </span>
          <span className={cn('text-right font-mono', tone(r.value))}>{pctS(r.value)}</span>
        </div>
      ))}
    </div>
  );
}

export function WhatIfSection() {
  const [s, setS] = useState<Sliders>(ZERO);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [port, setPort] = useState<'tactical' | 'strategic'>('tactical');
  const [preset, setPreset] = useState<string | null>(null);
  const seq = useRef(0);
  const isZero = useMemo(() => Object.values(s).every((v) => v === 0), [s]);

  useEffect(() => {
    if (isZero) { setRes(null); setErr(null); return; }
    const n = ++seq.current;
    const t = setTimeout(async () => {
      setBusy(true); setErr(null);
      try {
        const r = await fetch('/api/v1/risk/what-if', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(s) });
        const j = await r.json();
        if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `HTTP ${r.status}`);
        if (n === seq.current) setRes(j);               // a newer drag supersedes an older answer
      } catch (e: any) { if (n === seq.current) setErr(e?.message || 'Scenario failed'); }
      finally { if (n === seq.current) setBusy(false); }
    }, 450);
    return () => clearTimeout(t);
  }, [s, isZero]);

  const book = res?.book;
  const models: any[] = res?.models ?? [];
  const scale = Math.max(0.05, ...models.flatMap((m) => (m[port]?.by_asset ?? []).map((a: any) => Math.abs(a.move))));

  return (
    <section id="what-if" className="terminal-section">
      <div className="section-header !justify-start gap-2">
        <span className="section-tag"><SlidersHorizontal className="w-3 h-3" /></span>
        <h2 className="section-title">What-if Scenarios</h2>
        <span className="text-2xs text-text-tertiary hidden md:inline">drag a market move — the book and the three macro models respond</span>
        {busy && <span className="ml-auto text-2xs text-bloomberg animate-pulse">computing…</span>}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)] gap-2 p-2">
        {/* Controls */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex flex-wrap gap-1 mb-3">
            {PRESETS.map((p) => (
              <button key={p.label} type="button" title={p.note} onClick={() => { setS(p.s); setPreset(p.label); }}
                className={cn('px-2 py-0.5 text-[10.5px] border', preset === p.label ? 'border-bloomberg text-bloomberg bg-bloomberg/10' : 'border-border text-text-secondary hover:text-text-primary')}>
                {p.label}</button>
            ))}
            <button type="button" onClick={() => { setS(ZERO); setPreset(null); }} className="px-2 py-0.5 text-[10.5px] border border-border text-text-tertiary hover:text-text-primary">Reset</button>
          </div>
          <div className="space-y-3">
            {SLIDERS.map((d) => (
              <label key={d.key} className="block">
                <span className="flex justify-between text-[11px]">
                  <span className="text-text-secondary">{d.label}</span>
                  <span className={cn('font-mono', s[d.key] === 0 ? 'text-text-tertiary' : 'text-text-primary')}>{d.fmt(s[d.key])}</span>
                </span>
                <input type="range" min={d.min} max={d.max} step={d.step} value={s[d.key]} aria-label={d.label}
                  onChange={(e) => { setS({ ...s, [d.key]: Number(e.target.value) }); setPreset(null); }}
                  onDoubleClick={() => setS({ ...s, [d.key]: 0 })} className="whatif-range w-full" />
              </label>
            ))}
          </div>
          <div className="mt-3 text-[10px] text-text-tertiary">Double-click a slider to reset it. {res?.method}</div>
        </div>

        {/* Results */}
        <div className="space-y-2 min-w-0">
          {isZero && <div className="p-4 bg-surface-1 border border-border text-xs text-text-tertiary">
            Pick a preset or drag a slider. The first scenario estimates each instrument's factor betas (up to a minute and a
            half); after that, results follow the sliders.</div>}
          {err && <div className="p-2 text-xs text-amber border border-amber/30 bg-amber-dim">{err}</div>}
          {res && (
            <>
              <div className={cn('p-3 bg-surface-1 border border-border', busy && 'opacity-60')}>
                <div className="flex items-baseline gap-3">
                  <span className="text-xs font-semibold uppercase tracking-wider text-text-primary">Fund book</span>
                  {book?.available ? (
                    <>
                      <span className={cn('font-mono text-lg font-semibold', tone(book.pnl))}>{money(book.pnl)}</span>
                      {book.pnl_pct_capital != null && <span className={cn('font-mono text-xs', tone(book.pnl_pct_capital))}>{pctS(book.pnl_pct_capital, 2)} of capital</span>}
                    </>
                  ) : <span className="text-2xs text-text-tertiary">{book?.reason ?? 'unavailable'} — the macro models below still respond.</span>}
                </div>
                {book?.available && book.by_factor?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 text-[10.5px]">
                    {book.by_factor.map((f: any) => <span key={f.factor} className="text-text-tertiary">{f.label} <span className={cn('font-mono', tone(f.pnl))}>{money(f.pnl)}</span></span>)}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2">
                <span className="text-2xs text-text-tertiary">Macro model portfolios</span>
                <div className="ml-auto flex border border-border">
                  {(['tactical', 'strategic'] as const).map((k) => (
                    <button key={k} type="button" onClick={() => setPort(k)} aria-pressed={port === k}
                      className={cn('px-2 py-0.5 text-[10px] uppercase', port === k ? 'bg-bloomberg text-bg' : 'text-text-secondary')}>{k}</button>
                  ))}
                </div>
              </div>
              <div className={cn('grid grid-cols-1 lg:grid-cols-3 gap-2', busy && 'opacity-60')}>
                {models.map((m) => (
                  <div key={m.economy} className="p-3 bg-surface-1 border border-border min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="text-xs font-semibold text-text-primary">{m.name}</span>
                      {m.currency && <span className="text-[10px] font-mono text-text-tertiary">{m.currency}</span>}
                      {m.available && <span className={cn('ml-auto font-mono text-base font-semibold', tone(m[port].return))}>{pctS(m[port].return)}</span>}
                    </div>
                    {!m.available ? <div className="text-2xs text-text-tertiary mt-1">Model not available yet.</div> : (
                      <div className="mt-2">
                        <Bars scale={scale} rows={m[port].by_asset.map((a: any) => ({ label: a.asset, value: a.move,
                          sub: `${a.instrument}: ${pctS(a.move)} × weight ${(a.weight * 100).toFixed(0)}% = ${pctS(a.contribution, 2)} of the portfolio` }))} />
                        <div className="mt-1 text-[10px] text-text-tertiary">Bars: each asset's move; hover for its contribution at the {port} weight.</div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

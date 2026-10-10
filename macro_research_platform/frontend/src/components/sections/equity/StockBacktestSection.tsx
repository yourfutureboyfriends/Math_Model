// Entry Model Backtest — does the stock entry signal actually work? A walk-forward replay of
// the live price rules (set-up, pullback entry, regime gate, 2.5×ATR stop, 2R target, 63-day
// time stop) on ~20 years of the global universe, against a control that enters without a
// signal but uses the same exits. Trade statistics, portfolio curve, and breakdowns by market
// class, region, score bucket, year and regime.

import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, FlaskConical, Loader2, MinusCircle, RefreshCw, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';

const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500'];
const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
const spct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const r2 = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}R`);
const num = (v: number | null | undefined, d = 2) => (v == null ? '—' : v.toFixed(d));

const VARIANTS: { key: string; label: string; hint: string }[] = [
  { key: 'model', label: 'Model (live rules)', hint: 'BUY at full risk, BUY_SMALL (risk-off market) at half risk' },
  { key: 'regime_gate', label: 'Model, risk-on only', hint: 'Skips BUY_SMALL — trades only when the home market is risk-on' },
  { key: 'setup_only', label: 'Set-up, no entry filter', hint: 'Buys every strong set-up, even when extended' },
  { key: 'control', label: 'Control (no signal)', hint: 'Enters whenever flat, same stop / target / time exits' },
];
const BREAKDOWNS: { key: string; label: string }[] = [
  { key: 'market_class', label: 'Market class' }, { key: 'region', label: 'Region' }, { key: 'setup', label: 'Set-up score' },
  { key: 'label', label: 'Regime' }, { key: 'year', label: 'Year' }, { key: 'half', label: 'Sub-period' },
];
const TONE: Record<string, { cls: string; Icon: typeof CheckCircle2; word: string }> = {
  good: { cls: 'border-green/40 text-green', Icon: CheckCircle2, word: 'Supports' },
  bad: { cls: 'border-red/40 text-red', Icon: XCircle, word: 'Against' },
  neutral: { cls: 'border-border text-text-tertiary', Icon: MinusCircle, word: 'Inconclusive' },
};

function rColor(v: number | null | undefined) {
  return v == null ? 'text-text-tertiary' : v > 0.05 ? 'text-green' : v < -0.05 ? 'text-red' : 'text-text-secondary';
}

export function StockBacktestSection() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState('market_class');

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/v1/stock/backtest');
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : `HTTP ${r.status}`);
      setData(j); setError(null);
    } catch (e: any) { setError(e?.message || 'Unavailable'); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!data?.status?.running) return;
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [data?.status?.running, load]);

  const rerun = async () => {
    await fetch('/api/v1/stock/backtest/run', { method: 'POST' }).catch(() => {});
    setData((d: any) => ({ ...(d ?? {}), status: { running: true, stage: 'starting' } }));
    setTimeout(load, 1500);
  };

  const running = data?.status?.running;
  const s = data?.sample;
  const rows: any[] = data?.breakdown?.[tab] ?? [];
  const maxTrades = Math.max(1, ...rows.map((g) => g.trades));

  return (
    <div className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><FlaskConical className="w-3 h-3" /></span>
          <h2 className="section-title">Entry Model Backtest</h2>
          {data?.available && s && (
            <span className="text-2xs text-text-tertiary font-mono">
              {s.stocks} stocks · {s.markets} markets · {s.start.slice(0, 4)}–{s.end.slice(0, 4)} ({s.years}y) ·
              run {new Date(data.as_of).toLocaleDateString(undefined, { dateStyle: 'medium' })}
            </span>
          )}
        </div>
        <button onClick={rerun} disabled={running} title="Re-run the backtest (prices cached for a month)"
          className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs border border-border text-text-secondary hover:text-bloomberg disabled:opacity-60">
          {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          {running ? `${data?.status?.stage ?? 'Running'}…` : 'Re-run'}
        </button>
      </div>

      {error && <div className="p-2 text-xs text-amber border border-amber/30">{error}</div>}
      {data?.status?.error && <div className="p-2 mb-2 text-xs text-amber border border-amber/30">Last run failed: {data.status.error}</div>}
      {data && !data.available && (
        <div className="p-4 text-xs text-text-secondary border border-border-subtle flex items-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />{data.reason} {data.status?.stage ? `(${data.status.stage})` : ''}
        </div>
      )}

      {data?.available && (
        <div className="space-y-3">
          {/* Findings */}
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {(data.findings ?? []).map((f: any) => {
              const t = TONE[f.tone] ?? TONE.neutral;
              return (
                <div key={f.title} className={cn('px-3 py-2 border bg-surface-1', t.cls)}>
                  <div className="flex items-center gap-1.5 text-2xs uppercase tracking-wide">
                    <t.Icon className="w-3 h-3" />{f.title}<span className="ml-auto normal-case tracking-normal opacity-80">{t.word}</span>
                  </div>
                  <div className="text-xs text-text-secondary mt-1 leading-snug">{f.text}</div>
                </div>
              );
            })}
          </div>

          {/* Equity curves */}
          <div className="px-3 py-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary mb-1">Growth of 1 — trading every signal at 0.5% NAV risk per trade (local currency, after costs, log scale)</div>
            <LineChart rows={data.curve ?? []} x="date" height={240} log baseline={1}
              fmt={(v) => `${v.toFixed(2)}×`} axisFmt={(v) => `${v >= 1 ? v.toFixed(v >= 10 ? 0 : 1) : v.toFixed(2)}×`}
              lines={[{ key: 'model', label: 'Model', color: SERIES[0] }, { key: 'regime_gate', label: 'Risk-on only', color: SERIES[2] },
                      { key: 'control', label: 'Control', color: SERIES[1] }, { key: 'equal_weight', label: 'Equal-weight hold', color: SERIES[3] }]} />
          </div>

          {/* Variant comparison */}
          <div className="overflow-x-auto border border-border">
            <table className="w-full text-2xs font-mono">
              <thead className="bg-surface-1">
                <tr className="text-text-tertiary text-left">
                  <th className="font-normal font-sans px-2 py-1">Variant</th>
                  <th className="font-normal text-right px-2">Trades</th><th className="font-normal text-right px-2">Hit</th>
                  <th className="font-normal text-right px-2">Avg R</th><th className="font-normal text-right px-2" title="t-statistic of the mean R">t</th>
                  <th className="font-normal text-right px-2">PF</th><th className="font-normal text-right px-2">Days</th>
                  <th className="font-normal text-right px-2" title="Share of exits: target / stop / time">T / S / Time</th>
                  <th className="font-normal text-right px-2 border-l border-border">CAGR</th><th className="font-normal text-right px-2">Sharpe</th>
                  <th className="font-normal text-right px-2">Max DD</th><th className="font-normal text-right px-2" title="Average gross exposure">Expo.</th>
                </tr>
              </thead>
              <tbody>
                {VARIANTS.map(({ key, label, hint }) => {
                  const v = data.variants?.[key];
                  if (!v) return null;
                  const t = v.trades, p = v.portfolio ?? {};
                  const mix = t.exit_mix ?? {};
                  return (
                    <tr key={key} className={cn('border-t border-border-subtle', key === 'model' && 'bg-bloomberg/5')}>
                      <td className="px-2 py-1 font-sans text-text-primary" title={hint}>{label}</td>
                      <td className="text-right px-2">{t.trades?.toLocaleString()}</td>
                      <td className="text-right px-2">{pct(t.hit_rate, 0)}</td>
                      <td className={cn('text-right px-2', rColor(t.avg_r))}>{r2(t.avg_r)}</td>
                      <td className="text-right px-2 text-text-secondary">{num(t.t_stat, 1)}</td>
                      <td className="text-right px-2">{num(t.profit_factor)}</td>
                      <td className="text-right px-2 text-text-secondary">{num(t.avg_days, 0)}</td>
                      <td className="text-right px-2 text-text-secondary">{pct(mix.target, 0)} / {pct(mix.stop, 0)} / {pct(mix.time, 0)}</td>
                      <td className={cn('text-right px-2 border-l border-border', (p.cagr ?? 0) >= 0 ? 'text-green' : 'text-red')}>{spct(p.cagr)}</td>
                      <td className="text-right px-2">{num(p.sharpe)}</td>
                      <td className="text-right px-2 text-red">{pct(p.max_drawdown, 0)}</td>
                      <td className="text-right px-2 text-text-secondary">{pct(p.avg_gross, 0)}</td>
                    </tr>
                  );
                })}
                {data.equal_weight && (
                  <tr className="border-t border-border-subtle text-text-secondary">
                    <td className="px-2 py-1 font-sans" title="Daily-rebalanced equal weight of the same stocks">Equal-weight buy &amp; hold</td>
                    <td colSpan={7} className="text-right px-2 text-text-tertiary font-sans">same stocks, always invested</td>
                    <td className="text-right px-2 border-l border-border">{spct(data.equal_weight.cagr)}</td>
                    <td className="text-right px-2">{num(data.equal_weight.sharpe)}</td>
                    <td className="text-right px-2 text-red">{pct(data.equal_weight.max_drawdown, 0)}</td>
                    <td className="text-right px-2">100%</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Breakdown */}
          <div className="border border-border">
            <div className="flex flex-wrap items-center gap-1.5 px-2 py-1.5 bg-surface-1 border-b border-border">
              <span className="text-2xs text-text-tertiary mr-1">Model trades by</span>
              <div className="flex border border-border" role="tablist" aria-label="Breakdown">
                {BREAKDOWNS.map((b) => (
                  <button key={b.key} role="tab" aria-selected={tab === b.key} onClick={() => setTab(b.key)}
                    className={cn('px-2 py-0.5 text-2xs', tab === b.key ? 'bg-bloomberg text-bg' : 'text-text-secondary hover:text-text-primary')}>{b.label}</button>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto max-h-80">
              <table className="w-full text-2xs font-mono">
                <thead className="sticky top-0 bg-surface-1">
                  <tr className="text-text-tertiary text-left">
                    <th className="font-normal font-sans px-2 py-1">Group</th><th className="font-normal px-2">Trades</th>
                    <th className="font-normal text-right px-2">Hit</th><th className="font-normal text-right px-2">Avg R</th>
                    <th className="font-normal text-right px-2">t</th><th className="font-normal text-right px-2">Avg return</th>
                    <th className="font-normal text-right px-2">PF</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((g) => (
                    <tr key={g.group} className="border-t border-border-subtle">
                      <td className="px-2 py-1 font-sans text-text-primary whitespace-nowrap">{g.group === 'BUY_SMALL' ? 'Risk-off (BUY_SMALL)' : g.group === 'BUY' ? 'Risk-on (BUY)' : g.group}</td>
                      <td className="px-2">
                        <div className="flex items-center gap-1.5">
                          <span className="w-10 text-right">{g.trades.toLocaleString()}</span>
                          <span className="h-1.5 bg-bloomberg/40 rounded-sm" style={{ width: `${Math.max(2, (g.trades / maxTrades) * 80)}px` }} />
                        </div>
                      </td>
                      <td className="text-right px-2">{pct(g.hit_rate, 0)}</td>
                      <td className={cn('text-right px-2', rColor(g.avg_r))}>{r2(g.avg_r)}</td>
                      <td className="text-right px-2 text-text-secondary">{num(g.t_stat, 1)}</td>
                      <td className={cn('text-right px-2', (g.avg_return ?? 0) >= 0 ? 'text-green' : 'text-red')}>{spct(g.avg_return, 2)}</td>
                      <td className="text-right px-2">{num(g.profit_factor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="text-[10px] text-text-tertiary leading-relaxed">
            Walk-forward, no look-ahead: signal at the close, entry at the next open, stop {data.rules?.stop_atr}×ATR(14), target {data.rules?.target_r}R,
            {' '}{data.rules?.max_hold}-day time stop; stop assumed first when both are hit in one day; round-trip costs DM {pct(data.rules?.costs?.Developed, 2)},
            {' '}EM {pct(data.rules?.costs?.Emerging, 2)}, frontier {pct(data.rules?.costs?.Frontier, 2)}. Tests the price evidence only (trend, momentum,
            {' '}52-week high, pullback entry, regime) — no point-in-time history exists for analyst ratings, earnings surprises or quality.
            {' '}<span className="text-amber">Survivorship:</span> the sample is today’s largest stocks, which flatters absolute returns for every line;
            {' '}judge the model by its margin over the control on the same stocks and dates. Returns in local currency.
          </div>
        </div>
      )}
    </div>
  );
}

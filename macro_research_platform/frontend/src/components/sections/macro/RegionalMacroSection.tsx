/**
 * Developed Markets monitor — Americas, Europe and Asia-Pacific side by side.
 *
 * Reads /api/v1/global-macro: BIS policy rates (and every central-bank move in the last
 * 120 days), OECD/Eurostat CPI, unemployment, GDP and yields, Yahoo equity indices and FX.
 * Every number carries its reporting period and source on hover, and a dot when it is
 * behind its release calendar. Replaces the old regional table, whose FRED/OECD series had
 * stopped updating in early 2025.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Globe, RefreshCw } from 'lucide-react';

type Cell = { value: number | null; period: string | null; source: string; state: string; status: string;
              next_expected_release?: string | null; qoq?: number | null };
interface Economy {
  code: string; name: string; region: string; cb: string; target: number | null; ccy: string; note?: string;
  policy: { available: boolean; rate?: number; as_of?: string; change_12m_bp?: number | null; stance?: string;
            last_move?: { date: string; from: number; to: number; bp: number } | null; state?: string; reason?: string };
  cpi: Cell; unemployment: Cell; gdp: Cell; ten_year: Cell; three_month: Cell;
  ten_year_live?: { value: number; date: string };
  real_policy_rate: number | null; policy_vs_fed_bp: number | null; inflation_gap: number | null;
  ten_year_vs_us_bp: number | null; curve_bp: number | null; quadrant: string | null; trend_growth: number | null;
  equity: { index: string; level: number | null; as_of: string | null; change_1d: number | null;
            return_1m: number | null; return_ytd: number | null; return_ytd_usd: number | null };
  fx: { pair: string; spot: number | null; as_of: string | null; ccy_vs_usd_1m: number | null; ccy_vs_usd_ytd: number | null } | null;
}
interface GlobalMacro {
  available: boolean; as_of: string; regions: string[]; economies: Economy[];
  recent_policy_moves: { economy: string; date: string; from: number; to: number; bp: number }[];
  sources: Record<string, { source_status: string }>; notes: string[];
}

type Tab = 'macro' | 'rates' | 'markets';
const QUAD_TONE: Record<string, string> = {
  goldilocks: 'text-green', reflation: 'text-amber', stagflation: 'text-red', slowdown: 'text-blue',
};
const STALE_DOT: Record<string, string> = { LATE: 'bg-amber', MISSING_PERIODS: 'bg-red' };

const num = (v: number | null | undefined, d = 2, suffix = '') =>
  v == null || !Number.isFinite(v) ? '—' : `${v.toFixed(d)}${suffix}`;
const signed = (v: number | null | undefined, d = 1, suffix = '%') =>
  v == null || !Number.isFinite(v) ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(d)}${suffix}`;
const tone = (v: number | null | undefined) => (v == null ? 'text-text-tertiary' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : '');

function V({ c, d = 1, suffix = '%' }: { c: Cell; d?: number; suffix?: string }) {
  const title = c.value == null ? 'Not available for this economy'
    : `${c.source} · period ${c.period}${c.state !== 'CURRENT' ? ` · ${c.state.toLowerCase().replace('_', ' ')}` : ''}`
      + (c.next_expected_release ? ` · next ~${c.next_expected_release}` : '');
  return (
    <span title={title} className="inline-flex items-center justify-end gap-1">
      {STALE_DOT[c.state] && <span className={`w-1.5 h-1.5 rounded-full ${STALE_DOT[c.state]}`} />}
      <span className={c.value == null ? 'text-text-tertiary' : ''}>{num(c.value, d, c.value == null ? '' : suffix)}</span>
      {c.period && c.value != null && <span className="text-text-tertiary text-[9px]">{shortPeriod(c.period)}</span>}
    </span>
  );
}

function shortPeriod(p: string) {
  if (p.includes('-Q')) return p.slice(2).replace('-', '');      // 26Q2
  const [y, m] = p.split('-');
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m) - 1] ?? m}${y.slice(2)}`;
}

export function RegionalMacroSection() {
  const [data, setData] = useState<GlobalMacro | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('macro');
  const [region, setRegion] = useState<string>('All');

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await fetch('/api/v1/global-macro');
      const j = await r.json();
      if (!r.ok) throw new Error(j?.detail || `HTTP ${r.status}`);
      setData(j);
    } catch (e: any) { setError(e?.message || 'Failed to load'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const rows = useMemo(() => (data?.economies ?? []).filter((e) => region === 'All' || e.region === region), [data, region]);
  const degraded = data ? Object.entries(data.sources).filter(([, s]) => s.source_status !== 'ok') : [];

  return (
    <div id="regional-macro" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><Globe className="w-3 h-3" /></span>
          <h2 className="section-title">Developed Markets</h2>
          <span className="text-2xs text-text-tertiary">Americas · Europe · Asia-Pacific</span>
        </div>
        <button onClick={load} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Loading developed-markets data…</div>}
      {error && !data && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {error}</div>}

      {data && (
        <div className="space-y-3">
          {/* Central-bank moves */}
          {data.recent_policy_moves.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider mr-1">CB moves · 120d</span>
              {data.recent_policy_moves.slice(0, 10).map((m) => (
                <span key={`${m.economy}-${m.date}`} title={`${m.economy}: ${m.from}% → ${m.to}% on ${m.date}`}
                  className={`text-2xs font-mono px-1.5 py-0.5 border ${m.bp > 0 ? 'border-red/40 text-red' : 'border-green/40 text-green'}`}>
                  {m.economy} {m.bp > 0 ? '+' : ''}{m.bp}bp <span className="text-text-tertiary">{m.date.slice(5)}</span>
                </span>
              ))}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1">
              {(['macro', 'rates', 'markets'] as Tab[]).map((t) => (
                <button key={t} onClick={() => setTab(t)}
                  className={`px-2.5 py-1 text-2xs uppercase border ${tab === t ? 'bg-bloomberg text-bg border-bloomberg' : 'bg-surface-2 text-text-secondary border-border-subtle'}`}>
                  {t}
                </button>
              ))}
            </div>
            <div className="flex gap-1 ml-auto">
              {['All', ...data.regions].map((r) => (
                <button key={r} onClick={() => setRegion(r)}
                  className={`px-2 py-0.5 text-2xs border ${region === r ? 'border-bloomberg text-bloomberg' : 'border-border-subtle text-text-tertiary hover:text-text-primary'}`}>
                  {r}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono tabular-nums">
              <thead>
                <tr className="text-2xs text-text-tertiary uppercase tracking-wider">
                  <th className="text-left font-normal pb-1 pr-2 font-sans">Economy</th>
                  {tab === 'macro' && <>
                    <th className="text-right font-normal pb-1 px-1.5">Policy</th>
                    <th className="text-left font-normal pb-1 px-1.5">Stance</th>
                    <th className="text-right font-normal pb-1 px-1.5">CPI y/y</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="CPI minus the central bank's target">vs tgt</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="Policy rate minus CPI y/y">Real rate</th>
                    <th className="text-right font-normal pb-1 px-1.5">Unemp.</th>
                    <th className="text-right font-normal pb-1 px-1.5">GDP y/y</th>
                    <th className="text-left font-normal pb-1 px-1.5" title="GDP vs assumed trend, CPI vs target">Quadrant</th>
                  </>}
                  {tab === 'rates' && <>
                    <th className="text-right font-normal pb-1 px-1.5">Policy</th>
                    <th className="text-right font-normal pb-1 px-1.5">12m Δ</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="Policy rate minus the Fed's">vs Fed</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="OECD monthly average">3M</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="OECD monthly average (US latest daily close shown below the table)">10Y</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="Same-month 10Y spread to US Treasuries">vs UST</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="10Y minus 3M, same month">Curve</th>
                  </>}
                  {tab === 'markets' && <>
                    <th className="text-left font-normal pb-1 px-1.5 font-sans">Index</th>
                    <th className="text-right font-normal pb-1 px-1.5">Level</th>
                    <th className="text-right font-normal pb-1 px-1.5">1D</th>
                    <th className="text-right font-normal pb-1 px-1.5">1M</th>
                    <th className="text-right font-normal pb-1 px-1.5">YTD</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="Index return translated into USD">YTD $</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="Local currency vs USD, 1 month">Ccy 1M</th>
                    <th className="text-right font-normal pb-1 px-1.5" title="Local currency vs USD, year to date">Ccy YTD</th>
                  </>}
                </tr>
              </thead>
              <tbody>
                {data.regions.filter((r) => region === 'All' || r === region).map((reg) => (
                  <RegionRows key={reg} region={reg} rows={rows.filter((e) => e.region === reg)} tab={tab} />
                ))}
              </tbody>
            </table>
          </div>

          <div className="text-2xs text-text-tertiary space-y-0.5">
            {data.economies.find((e) => e.code === 'US')?.ten_year_live && (
              <div>US 10Y latest daily close (FRED DGS10): {num(data.economies.find((e) => e.code === 'US')!.ten_year_live!.value)}%
                ({data.economies.find((e) => e.code === 'US')!.ten_year_live!.date}).</div>
            )}
            {data.notes.map((n) => <div key={n}>{n}</div>)}
            <div>Sources: BIS (policy rates), OECD &amp; Eurostat (macro, yields), FRED (US), Yahoo (indices, FX). Hover any value for its period and source.</div>
            {degraded.length > 0 && (
              <div className="text-amber">Using cached data for: {degraded.map(([k, s]) => `${k} (${s.source_status})`).join(', ')}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function RegionRows({ region, rows, tab }: { region: string; rows: Economy[]; tab: Tab }) {
  if (!rows.length) return null;
  const span = tab === 'macro' ? 9 : 8;
  return (
    <>
      <tr><td colSpan={span} className="pt-2 pb-0.5 text-2xs text-bloomberg uppercase tracking-wider font-sans">{region}</td></tr>
      {rows.map((e) => (
        <tr key={e.code} className="border-t border-border-subtle">
          <td className="py-1 pr-2 font-sans text-text-primary whitespace-nowrap" title={e.note ?? `${e.cb} · ${e.ccy}`}>
            {e.name} <span className="text-text-tertiary text-2xs">{e.cb}</span>
          </td>
          {tab === 'macro' && e.note && e.cpi?.value == null && e.unemployment?.value == null && (
            // No macro coverage (HK peg, SG FX-based policy): say so instead of a row of dashes.
            <>
              <td className="text-right px-1.5">{num(e.policy.rate, 2, e.policy.rate != null ? '%' : '')}</td>
              <td colSpan={7} className="px-1.5 font-sans text-2xs text-text-tertiary">{e.note}</td>
            </>
          )}
          {tab === 'macro' && !(e.note && e.cpi?.value == null && e.unemployment?.value == null) && <>
            <td className="text-right px-1.5" title={e.policy.as_of ? `BIS · ${e.policy.as_of}` : e.policy.reason}>{num(e.policy.rate, 2, e.policy.rate != null ? '%' : '')}</td>
            <td className={`px-1.5 font-sans text-2xs whitespace-nowrap ${e.policy.stance === 'hiking' ? 'text-red' : e.policy.stance === 'cutting' ? 'text-green' : 'text-text-tertiary'}`}
              title={e.policy.last_move ? `Last move ${e.policy.last_move.date}: ${e.policy.last_move.from}% → ${e.policy.last_move.to}%` : undefined}>
              {e.policy.available ? `${e.policy.stance}${e.policy.last_move ? ` ${e.policy.last_move.date.slice(2, 7)}` : ''}` : '—'}
            </td>
            <td className="text-right px-1.5"><V c={e.cpi} /></td>
            <td className={`text-right px-1.5 ${e.inflation_gap == null ? 'text-text-tertiary' : e.inflation_gap > 0.5 ? 'text-red' : e.inflation_gap < -0.5 ? 'text-blue' : ''}`}>{signed(e.inflation_gap, 1, 'pp')}</td>
            <td className={`text-right px-1.5 ${tone(e.real_policy_rate)}`}>{signed(e.real_policy_rate, 2, '%')}</td>
            <td className="text-right px-1.5"><V c={e.unemployment} /></td>
            <td className="text-right px-1.5"><V c={e.gdp} /></td>
            <td className={`px-1.5 font-sans text-2xs ${QUAD_TONE[e.quadrant ?? ''] ?? 'text-text-tertiary'}`}
              title={e.trend_growth != null ? `trend growth assumed ${e.trend_growth}%` : undefined}>{e.quadrant ?? '—'}</td>
          </>}
          {tab === 'rates' && <>
            <td className="text-right px-1.5">{num(e.policy.rate, 2, e.policy.rate != null ? '%' : '')}</td>
            <td className={`text-right px-1.5 ${tone(e.policy.change_12m_bp ?? null)}`}>{signed(e.policy.change_12m_bp ?? null, 0, 'bp')}</td>
            <td className="text-right px-1.5">{e.code === 'US' ? '·' : signed(e.policy_vs_fed_bp, 0, 'bp')}</td>
            <td className="text-right px-1.5"><V c={e.three_month} d={2} /></td>
            <td className="text-right px-1.5"><V c={e.ten_year} d={2} /></td>
            <td className="text-right px-1.5">{e.code === 'US' ? '·' : signed(e.ten_year_vs_us_bp, 0, 'bp')}</td>
            <td className={`text-right px-1.5 ${e.curve_bp != null && e.curve_bp < 0 ? 'text-red' : ''}`}>{signed(e.curve_bp, 0, 'bp')}</td>
          </>}
          {tab === 'markets' && <>
            <td className="px-1.5 font-sans text-text-secondary whitespace-nowrap" title={e.equity.as_of ? `close ${e.equity.as_of}` : undefined}>{e.equity.index}</td>
            <td className="text-right px-1.5">{e.equity.level != null ? e.equity.level.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}</td>
            <td className={`text-right px-1.5 ${tone(e.equity.change_1d)}`}>{signed(e.equity.change_1d, 2)}</td>
            <td className={`text-right px-1.5 ${tone(e.equity.return_1m)}`}>{signed(e.equity.return_1m)}</td>
            <td className={`text-right px-1.5 ${tone(e.equity.return_ytd)}`}>{signed(e.equity.return_ytd)}</td>
            <td className={`text-right px-1.5 ${tone(e.equity.return_ytd_usd)}`}>{signed(e.equity.return_ytd_usd)}</td>
            <td className={`text-right px-1.5 ${tone(e.fx?.ccy_vs_usd_1m)}`} title={e.fx ? `${e.fx.pair} ${e.fx.spot ?? ''} (${e.fx.as_of ?? ''})` : 'USD'}>{e.fx ? signed(e.fx.ccy_vs_usd_1m) : '·'}</td>
            <td className={`text-right px-1.5 ${tone(e.fx?.ccy_vs_usd_ytd)}`}>{e.fx ? signed(e.fx.ccy_vs_usd_ytd) : '·'}</td>
          </>}
        </tr>
      ))}
    </>
  );
}

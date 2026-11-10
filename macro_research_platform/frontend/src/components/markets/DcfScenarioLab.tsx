/**
 * DCF scenario lab — the standalone FCFF scenario engine (POST /api/v1/mkt/dcf-scenarios): an analyst's own normalised
 * free cash flow, growth and risk premiums, a probability-weighted Bear / Base / Bull matrix, and the reverse DCF —
 * the growth, the perpetual growth and the discount rate today's price implies, each solved holding the rest fixed.
 *
 * Cost of equity = risk-free + beta × market premium + country premium + governance premium (additive, not scaled by
 * beta). The regional profiles are illustrative analyst presets, never inferred from a company's nationality; a WACC
 * band is shown beside the calculated rate, not forced onto it. Prefilled from the company's current DCF where the
 * engine's single-currency assumption holds.
 */
import { useMemo, useState } from 'react';
import { fetchJSONWithDeadline } from '@/lib/fetchDeadline';
import { fmtPrice } from './shared';
import { EChart, axisStyle, useChartTheme } from '@/components/charts/EChart';

type Scn = { name: string; probability: number; growth_shift: number; wacc_shift: number; fcf_multiplier: number };
const DEFAULT_SCN: Scn[] = [
  { name: 'Bear', probability: 0.25, growth_shift: -0.05, wacc_shift: 0.02, fcf_multiplier: 0.9 },
  { name: 'Base', probability: 0.5, growth_shift: 0, wacc_shift: 0, fcf_multiplier: 1 },
  { name: 'Bull', probability: 0.25, growth_shift: 0.05, wacc_shift: -0.01, fcf_multiplier: 1.1 },
];
const PROFILES: [string, string][] = [['', 'None (calculated premiums)'], ['western_tech', 'Western large-cap tech (illustrative)'], ['china_structural', 'China structural risk (illustrative)']];
const pct = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`);
const num = (s: string) => (s.trim() === '' ? NaN : Number(s));

function Field({ label, value, onChange, unit, hint }: { label: string; value: string; onChange: (v: string) => void; unit?: string; hint?: string }) {
  return (
    <label className="text-[10px] uppercase tracking-wider text-text-tertiary" title={hint}>{label}
      <div className="flex items-center mt-0.5">
        <input type="number" step="any" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}
          className="w-full bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary" />
        {unit && <span className="ml-1 text-text-tertiary normal-case w-3">{unit}</span>}
      </div>
    </label>
  );
}

export function DcfScenarioLab({ inp, v, w }: { inp: any; v: any; w: any }) {
  const t = useChartTheme();
  const oneCurrency = !inp?.price_currency || !inp?.currency || inp.price_currency === inp.currency;
  const p100 = (x: number | null | undefined) => (x == null || !Number.isFinite(x) ? '' : String(+(x * 100).toFixed(3)));
  const [f, setF] = useState<Record<string, string>>(() => ({
    base_fcf: '', growth: p100(v?.assumptions?.growth), years: String(v?.assumptions?.years ?? 10), terminal_growth: p100(v?.assumptions?.terminal_growth),
    shares: oneCurrency && inp?.shares ? String(inp.shares) : '', market_price: String(v?.price ?? inp?.price ?? ''), net_debt: '',
    risk_free: p100(w?.risk_free), beta: w?.beta != null ? String(+w.beta.toFixed(3)) : '1', market_risk_premium: p100(w?.market_risk_premium ?? w?.erp),
    country_risk_premium: p100(w?.country_risk_premium ?? 0), governance_risk_premium: p100(w?.governance_risk_premium ?? 0),
    cost_of_debt: p100(w?.cost_of_debt_after_tax), equity_weight: p100(w?.weight_equity ?? 1),
  }));
  const [profile, setProfile] = useState('');
  const [localized, setLocalized] = useState('');                          // China profile: 4–6% localized equity premium
  const [scn, setScn] = useState<Scn[]>(DEFAULT_SCN);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (val: string) => setF((o) => ({ ...o, [k]: val }));
  const probSum = scn.reduce((s, x) => s + (Number.isFinite(x.probability) ? x.probability : 0), 0);

  const run = async () => {
    setErr(null);
    const d = (k: string) => num(f[k]) / 100;
    const ew = d('equity_weight');
    const body: any = {
      model: { base_fcf: num(f.base_fcf), growth: d('growth'), years: Math.round(num(f.years)), terminal_growth: d('terminal_growth'),
        shares: num(f.shares), market_price: num(f.market_price), net_debt: f.net_debt.trim() === '' ? 0 : num(f.net_debt), mid_year: true },
      // the company's after-tax cost of debt is entered directly, so the engine's tax shield is set to zero
      risk: { risk_free: d('risk_free'), beta: num(f.beta), market_risk_premium: d('market_risk_premium'), country_risk_premium: d('country_risk_premium'),
        governance_risk_premium: d('governance_risk_premium'), cost_of_debt: d('cost_of_debt'), tax_rate: 0, equity_weight: ew, debt_weight: 1 - ew },
      scenarios: scn,
      ...(profile ? { profile } : {}),
      ...(profile === 'china_structural' && localized ? { localized_premium: Number(localized) / 100 } : {}),
    };
    const bad = [...Object.entries(body.model), ...Object.entries(body.risk)].filter(([, x]) => typeof x === 'number' && !Number.isFinite(x)).map(([k]) => k);
    if (bad.length) { setErr(`Fill in: ${bad.join(', ').replace(/_/g, ' ')}`); return; }
    if (Math.abs(probSum - 1) > 1e-9) { setErr(`Scenario probabilities sum to ${pct(probSum, 0)} — they must sum to 100%.`); return; }
    setBusy(true);
    try {
      const { response: r, json: j } = await fetchJSONWithDeadline('/api/v1/mkt/dcf-scenarios', new AbortController().signal, 20_000,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!r.ok || !j) throw new Error(typeof j?.detail === 'string' ? j.detail : `Scenario engine error (${r.status})`);
      setRes(j);
    } catch (e) { setErr(e instanceof Error ? e.message : 'Scenario engine unavailable'); setRes(null); }
    finally { setBusy(false); }
  };

  const chart = useMemo(() => {
    if (!res?.matrix) return null;
    const ax = axisStyle(t);
    const price = num(f.market_price);
    const rows = res.matrix as any[];
    return {
      legend: { show: false }, toolbox: { show: false },
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps: any[]) => { const r = rows[ps[0].dataIndex];
        return `<b>${r.scenario}</b> · ${pct(r.probability, 0)}<br/>${r.per_share == null ? r.status : `${fmtPrice(r.per_share)} per share (${pct(r.upside)} vs price)`}<br/>growth ${pct(r.fcf_growth)} · WACC ${pct(r.wacc)}`; } },
      xAxis: { type: 'category', data: rows.map((r) => `${r.scenario} (${pct(r.probability, 0)})`), ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (x: number) => x.toLocaleString(undefined, { maximumFractionDigits: Math.abs(x) >= 10 ? 0 : 2 }) } },
      series: [{ type: 'bar', barMaxWidth: 46, data: rows.map((r) => ({ value: r.per_share, itemStyle: { color: r.per_share == null ? t.muted : r.per_share >= price ? t.green : t.red, borderRadius: [4, 4, 0, 0] } })),
        label: { show: true, position: 'top', fontSize: 10, color: t.text, formatter: (q: any) => (q.value == null ? 'n/a' : fmtPrice(q.value)) },
        markLine: { symbol: 'none', silent: true, data: [{ yAxis: price, label: { formatter: `price ${fmtPrice(price)}`, position: 'insideEndTop', color: t.textStrong } },
          ...(res.expected_value != null ? [{ yAxis: res.expected_value, lineStyle: { type: 'dashed' as const, color: t.accent }, label: { formatter: `expected ${fmtPrice(res.expected_value)}`, position: 'insideStartTop', color: t.accent } }] : [])],
          lineStyle: { color: t.textStrong } } }],
    };
  }, [res, t, f.market_price]);

  // the solver reports one root, several (ambiguous) or none inside its search range — never a bound as an answer
  const solved = (s: any, fmt: (x: number) => string) => (!s ? '—' : s.status === 'solved' && s.value != null ? fmt(s.value)
    : s.status === 'multiple_roots' ? `ambiguous (${s.roots?.length} roots)` : s.bounds ? `outside ${fmt(s.bounds[0])}–${fmt(s.bounds[1])}` : '—');
  const rev = res?.reverse;
  return (
    <section className="mkt-panel bg-surface-1 border border-border" data-panel-title="Scenario lab">
      <div className="panel-hdr flex items-center justify-between gap-2 px-3 py-1.5 border-b border-border-subtle">
        <h2 className="text-[10px] uppercase tracking-wider text-text-tertiary">Scenario lab — your own FCFF, risk premiums and Bear / Base / Bull</h2>
      </div>
      <div className="p-3 space-y-3">
        {!oneCurrency && <p className="text-2xs text-amber">This company reports in {inp.currency} but trades in {inp.price_currency}. The lab works in one currency: enter free cash flow, net debt and shares on the same basis as the price.</p>}
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
          <Field label="Normalised FCFF (yr 0)" value={f.base_fcf} onChange={set('base_fcf')} hint="Positive, in the price currency" />
          <Field label="FCF growth" value={f.growth} onChange={set('growth')} unit="%" />
          <Field label="Years" value={f.years} onChange={set('years')} />
          <Field label="Terminal growth" value={f.terminal_growth} onChange={set('terminal_growth')} unit="%" />
          <Field label="Shares" value={f.shares} onChange={set('shares')} />
          <Field label="Net debt" value={f.net_debt} onChange={set('net_debt')} hint="Blank = 0" />
          <Field label="Market price" value={f.market_price} onChange={set('market_price')} />
          <Field label="Risk-free" value={f.risk_free} onChange={set('risk_free')} unit="%" />
          <Field label="Beta" value={f.beta} onChange={set('beta')} />
          <Field label="Market premium" value={f.market_risk_premium} onChange={set('market_risk_premium')} unit="%" />
          <Field label="Country premium" value={f.country_risk_premium} onChange={set('country_risk_premium')} unit="%" hint="Added to the cost of equity, not scaled by beta" />
          <Field label="Governance premium" value={f.governance_risk_premium} onChange={set('governance_risk_premium')} unit="%" hint="e.g. VIE structure, capital controls — only where established for this entity" />
          <Field label="After-tax cost of debt" value={f.cost_of_debt} onChange={set('cost_of_debt')} unit="%" />
          <Field label="Equity weight" value={f.equity_weight} onChange={set('equity_weight')} unit="%" />
        </div>
        <div className="flex flex-wrap items-center gap-3 text-2xs">
          <label className="text-text-tertiary">Regional profile
            <select value={profile} onChange={(e) => setProfile(e.target.value)} className="ml-2 bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary" aria-label="Regional profile">
              {PROFILES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          {profile === 'china_structural' && <label className="text-text-tertiary">Localized premium
            <select value={localized} onChange={(e) => setLocalized(e.target.value)} className="ml-2 bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary" aria-label="Localized premium">
              <option value="">Preset (3pt country + 2pt governance)</option>{['4', '4.5', '5', '5.5', '6'].map((x) => <option key={x} value={x}>{x}% (60% country / 40% governance)</option>)}</select></label>}
          <span className="text-text-tertiary">A profile replaces the country and governance premiums with its own illustrative values and shows its reference WACC band.</span>
        </div>
        <div className="overflow-x-auto"><table className="w-full text-xs">
          <thead><tr className="text-[10px] uppercase text-text-tertiary"><th className="text-left font-normal">Scenario</th><th className="text-right font-normal">Probability</th>
            <th className="text-right font-normal">Growth shift</th><th className="text-right font-normal">WACC shift</th><th className="text-right font-normal">FCF × </th></tr></thead>
          <tbody>{scn.map((s, i) => (
            <tr key={s.name} className="border-t border-border-subtle"><td className="py-1 text-text-primary">{s.name}</td>
              {(['probability', 'growth_shift', 'wacc_shift', 'fcf_multiplier'] as const).map((k) => (
                <td key={k} className="text-right"><input type="number" step="any" aria-label={`${s.name} ${k.replace('_', ' ')}`}
                  value={k === 'fcf_multiplier' ? s[k] : +(s[k] * 100).toFixed(3)}
                  onChange={(e) => { const x = Number(e.target.value); setScn(scn.map((o, j) => (j === i ? { ...o, [k]: k === 'fcf_multiplier' ? x : x / 100 } : o))); }}
                  className="w-20 bg-surface-1 border border-border px-1.5 py-0.5 text-xs font-mono text-right" />{k !== 'fcf_multiplier' && <span className="text-text-tertiary ml-0.5">%</span>}</td>))}
            </tr>))}</tbody>
          <tfoot><tr><td className="pt-1 text-text-tertiary">Total</td><td className={`pt-1 text-right font-mono ${Math.abs(probSum - 1) > 1e-9 ? 'text-red' : 'text-text-secondary'}`}>{pct(probSum, 0)}</td><td colSpan={3} /></tr></tfoot>
        </table></div>
        <div className="flex items-center gap-3">
          <button onClick={run} disabled={busy} className="px-4 py-1.5 text-xs bg-bloomberg text-text-inverse disabled:opacity-50">{busy ? 'Running…' : 'Run scenarios'}</button>
          <button onClick={() => { setScn(DEFAULT_SCN); setProfile(''); }} className="text-2xs text-text-tertiary hover:text-text-primary">Reset scenarios</button>
          {err && <span role="alert" className="text-2xs text-red">{err}</span>}
        </div>
        {res && <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {[['Expected value / share', res.expected_value != null ? fmtPrice(res.expected_value) : 'withheld', res.expected_upside != null ? `${pct(res.expected_upside)} vs price` : 'a scenario failed — no weighted value'],
              ['WACC used', pct(res.applied_base_wacc, 2), `cost of equity ${pct(res.risk?.cost_of_equity, 2)}`],
              ['Growth the price implies', solved(rev?.implied_fcf_cagr, (x) => pct(x)), `over ${rev?.forecast_years} years, rest fixed`],
              ['WACC the price implies', solved(rev?.implied_wacc, (x) => pct(x, 2)), 'cash flows fixed'],
              ['Perpetual growth implied', solved(rev?.implied_terminal_growth, (x) => pct(x, 2)), 'forecast path fixed']].map(([l, val, sub]) => (
              <div key={l} className="mkt-stat-card px-3 py-2 bg-surface-1 border border-border min-w-0">
                <div className="text-[10px] uppercase tracking-wider text-text-tertiary leading-tight">{l}</div>
                <div className="font-mono text-base tabular-nums text-text-primary">{val}</div>
                <div className="text-[10px] text-text-tertiary leading-tight">{sub}</div></div>))}
          </div>
          {res.profile?.reference_wacc_band && <p className="text-2xs text-text-secondary">Profile reference WACC band {pct(res.profile.reference_wacc_band[0])}–{pct(res.profile.reference_wacc_band[1])} — shown for comparison, not applied. {res.profile.note}</p>}
          {chart && <EChart option={chart} height={240} ariaLabel="Value per share by scenario against the price" />}
          <p className="text-[10px] text-text-tertiary">{res.note} {rev?.interpretation}</p>
        </>}
      </div>
    </section>
  );
}

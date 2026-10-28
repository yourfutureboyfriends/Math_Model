// LBO workbench: load a listed company (filings + live credit markets) or start from the illustrative case, edit
// any assumption, and the model re-runs — three cases, returns, the value bridge, the debt paydown, credit stats and
// covenants, IRR sensitivities, the highest price that clears the hurdle. Save to the fund's pipeline; export the
// investment-committee workbook. Reads /api/v1/pe/{defaults,company,lbo,lbo/excel,deals}.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Download, Loader2, Save, Search, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, IrrGrid, Kpi, NumField, amt, api, download, irrTone, onOpenDeal, pct, spct, unitFor, xx } from './peShared';

type Inputs = Record<string, any>;
const KIND_LABEL: Record<string, string> = { tla: 'Term loan A', tlb: 'Term loan B', notes: 'Senior notes', mezz: 'Mezzanine (PIK)' };
const NEW_TRANCHE: Record<string, any> = {
  tla: { name: 'Term Loan A', kind: 'tla', multiple: 1.0, floating: true, spread: 0.025, floor: 0, amort_pct: 0.1, tenor: 6, sweep: true },
  tlb: { name: 'Term Loan B', kind: 'tlb', multiple: 3.0, floating: true, spread: 0.0325, floor: 0, amort_pct: 0.01, tenor: 7, sweep: true },
  notes: { name: 'Senior notes', kind: 'notes', multiple: 1.5, floating: false, coupon: 0.0775, amort_pct: 0, tenor: 8, sweep: false },
  mezz: { name: 'Mezzanine', kind: 'mezz', multiple: 0.75, floating: false, coupon: 0.12, pik: true, amort_pct: 0, tenor: 9, sweep: false },
};
const asPath = (v: any, n: number): number[] => {
  const xs = Array.isArray(v) ? v.map(Number) : [Number(v ?? 0)];
  return Array.from({ length: n }, (_, i) => xs[Math.min(i, xs.length - 1)]);
};

export function Workbench() {
  const [inputs, setInputs] = useState<Inputs | null>(null);
  const [sources, setSources] = useState<Record<string, string> | null>(null);
  const [market, setMarket] = useState<any>(null);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sym, setSym] = useState('');
  const [premium, setPremium] = useState(0.3);
  const [loadingCo, setLoadingCo] = useState(false);
  const [deal, setDeal] = useState<{ id?: number; name: string; stage?: string }>({ name: '' });
  const [note, setNote] = useState<string | null>(null);
  const runId = useRef(0);

  useEffect(() => { api('/api/v1/pe/defaults').then((j) => setInputs(j.inputs)).catch((e) => setErr(e.message)); }, []);
  useEffect(() => onOpenDeal(async (id) => {
    try {
      const d = await api(`/api/v1/pe/deals/${id}`);
      setInputs(d.inputs); setDeal({ id: d.id, name: d.name, stage: d.stage }); setSources(null); setMarket(null); setSym(d.symbol ?? '');
    } catch (e: any) { setErr(e.message); }
  }), []);

  // Re-run the model whenever an assumption changes (debounced; only the latest run is shown)
  useEffect(() => {
    if (!inputs) return;
    const id = ++runId.current;
    setBusy(true);
    const t = setTimeout(() => {
      api('/api/v1/pe/lbo', { inputs }).then((j) => { if (id === runId.current) { setRes(j); setErr(null); } })
        .catch((e) => { if (id === runId.current) setErr(e.message); })
        .finally(() => { if (id === runId.current) setBusy(false); });
    }, 350);
    return () => clearTimeout(t);
  }, [inputs]);

  const set = useCallback((patch: Inputs) => setInputs((p) => (p ? { ...p, ...patch } : p)), []);
  const setTr = (i: number, patch: Inputs) => setInputs((p) => p && ({ ...p, tranches: p.tranches.map((t: any, j: number) => (j === i ? { ...t, ...patch } : t)) }));

  const loadCompany = async () => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setLoadingCo(true); setErr(null);
    try {
      const j = await api(`/api/v1/pe/company/${encodeURIComponent(s)}?premium=${premium}`);
      setInputs(j.inputs); setSources(j.sources); setMarket(j); setDeal({ name: j.inputs.name });
    } catch (e: any) { setErr(e.message); } finally { setLoadingCo(false); }
  };
  const saveDeal = async () => {
    if (!inputs) return;
    try {
      const body = { inputs: { ...inputs, name: deal.name || inputs.name }, name: deal.name || inputs.name };
      const d = deal.id ? await api(`/api/v1/pe/deals/${deal.id}`, body, 'PUT') : await api('/api/v1/pe/deals', body);
      setDeal({ id: d.id, name: d.name, stage: d.stage });
      setNote(`Saved to the pipeline (${d.stage}).`); setTimeout(() => setNote(null), 3000);
    } catch (e: any) { setErr(e.message); }
  };
  const exportXlsx = async () => {
    if (!inputs) return;
    try { await download('/api/v1/pe/lbo/excel', { inputs: { ...inputs, name: deal.name || inputs.name }, sources }, `LBO - ${deal.name || inputs.name || 'deal'}.xlsx`); }
    catch (e: any) { setErr(e.message); }
  };

  const n = Number(inputs?.years ?? 7);
  const unit = unitFor(inputs?.ebitda);
  const amtKind: 'm' | 'num' = unit === 1e6 ? 'm' : 'num';
  const ccy = inputs?.currency ?? '';
  const base = res?.cases?.base;
  const hurdle = Number(inputs?.hurdle_irr ?? 0.2);

  if (!inputs) return err ? <div className="text-xs text-red p-3">{err}</div> : <div className="p-6 text-xs text-text-tertiary"><Loader2 className="w-4 h-4 animate-spin inline mr-2" />Loading the workbench…</div>;

  return (
    <div className="space-y-3">
      {/* Load a company / name the deal */}
      <div className="flex flex-wrap items-end gap-2 p-3 rounded-xl border border-border bg-surface-1">
        <label className="block">
          <span className="block text-[10.5px] text-text-tertiary mb-0.5">Listed company (ticker)</span>
          <span className="flex items-center rounded-md border border-border bg-bg/40 focus-within:border-bloomberg/60">
            <Search className="w-3.5 h-3.5 ml-2 text-text-tertiary" />
            <input value={sym} onChange={(e) => setSym(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && loadCompany()} placeholder="e.g. HSY, DPZ, TSCO.L"
              className="w-40 bg-transparent px-2 py-1.5 text-xs uppercase text-text-primary outline-none" />
          </span>
        </label>
        <NumField label="Take-private premium" kind="pct" value={premium} onChange={(v) => setPremium(v ?? 0.3)} className="w-32" />
        <button onClick={loadCompany} disabled={loadingCo || !sym.trim()} className="h-[30px] px-3 rounded-lg bg-bloomberg text-white text-xs font-medium disabled:opacity-50">
          {loadingCo ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Load from filings'}</button>
        <button onClick={() => api('/api/v1/pe/defaults').then((j) => { setInputs(j.inputs); setSources(null); setMarket(null); setDeal({ name: '' }); })}
          className="h-[30px] px-3 rounded-lg border border-border text-xs text-text-secondary">Illustrative case</button>
        <label className="block ml-auto">
          <span className="block text-[10.5px] text-text-tertiary mb-0.5">Deal name</span>
          <input value={deal.name} onChange={(e) => setDeal({ ...deal, name: e.target.value })} placeholder={inputs.name ?? 'Project …'}
            className="w-52 rounded-md border border-border bg-bg/40 px-2 py-1.5 text-xs text-text-primary outline-none focus:border-bloomberg/60" />
        </label>
        <button onClick={saveDeal} className="h-[30px] px-3 rounded-lg border border-border text-xs inline-flex items-center gap-1.5"><Save className="w-3.5 h-3.5" />{deal.id ? 'Update deal' : 'Save to pipeline'}</button>
        <button onClick={exportXlsx} className="h-[30px] px-3 rounded-lg border border-border text-xs inline-flex items-center gap-1.5"><Download className="w-3.5 h-3.5" />Excel model</button>
      </div>
      {note && <div className="text-xs text-green">{note}</div>}
      {err && <div className="text-xs text-red flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" />{err}</div>}
      {market?.market?.offer_price && (
        <div className="text-[11px] text-text-tertiary">{inputs.name} · price {market.market.price?.toFixed(2)} {market.market.price_currency} · offer {market.market.offer_price.toFixed(2)}
          ({pct(market.market.premium, 0)} premium) · {ccy} {amt(market.market.ev_at_offer, ccy, unit)}{unit === 1e6 ? 'm' : ''} EV · {market.industry?.ev_ebitda ? `industry ${xx(market.industry.ev_ebitda, 1)} (${market.industry.industry})` : ''}
          {market.credit?.base_rate != null && ` · ${market.credit.base_rate_name} ${pct(market.credit.base_rate, 2)} · B spread ${pct(market.credit.b_spread, 2)}`}</div>)}

      <div className="grid grid-cols-1 xl:grid-cols-[400px_1fr] gap-3 items-start">
        {/* ── Assumptions ── */}
        <div className="space-y-3">
          <Card title="Target (LTM)">
            <div className="grid grid-cols-2 gap-2">
              <NumField label={`Revenue (${ccy}${unit === 1e6 ? 'm' : ''})`} kind={amtKind} value={inputs.revenue} onChange={(v) => set({ revenue: v })} />
              <NumField label={`EBITDA (${ccy}${unit === 1e6 ? 'm' : ''})`} kind={amtKind} value={inputs.ebitda} onChange={(v) => set({ ebitda: v })} />
              <NumField label="Existing debt (refinanced)" kind={amtKind} value={inputs.debt} onChange={(v) => set({ debt: v ?? 0 })} />
              <NumField label="Existing cash" kind={amtKind} value={inputs.cash} onChange={(v) => set({ cash: v ?? 0 })} />
            </div>
          </Card>
          <Card title="Entry & fees">
            <div className="grid grid-cols-2 gap-2">
              <NumField label="Entry EV / EBITDA" kind="x" value={inputs.entry_multiple} onChange={(v) => set({ entry_multiple: v })} />
              <NumField label="Transaction fees (% EV)" kind="pct" value={inputs.transaction_fee_pct} onChange={(v) => set({ transaction_fee_pct: v ?? 0 })} />
              <NumField label="Financing fees (% debt)" kind="pct" value={inputs.financing_fee_pct} onChange={(v) => set({ financing_fee_pct: v ?? 0 })} />
              <NumField label="Minimum cash" kind={amtKind} value={inputs.min_cash} onChange={(v) => set({ min_cash: v ?? 0 })} />
              <NumField label="Rollover equity" kind={amtKind} value={inputs.rollover_equity} onChange={(v) => set({ rollover_equity: v ?? 0 })} hint="Management / seller equity rolled into the deal" />
            </div>
          </Card>
          <Card title="Financing" right={
            <select onChange={(e) => { if (e.target.value) setInputs((p) => p && ({ ...p, tranches: [...p.tranches, { ...NEW_TRANCHE[e.target.value] }] })); e.target.value = ''; }}
              className="text-[11px] rounded-md border border-border bg-bg/40 px-1.5 py-0.5" defaultValue="">
              <option value="">+ Add tranche</option>{Object.entries(KIND_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>}>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <NumField label="Base rate (SOFR / SONIA / €STR)" kind="pct" value={inputs.base_rate} onChange={(v) => set({ base_rate: v ?? 0 })} />
              <label className="block"><span className="block text-[10.5px] text-text-tertiary mb-0.5">Interest on</span>
                <select value={inputs.interest_on} onChange={(e) => set({ interest_on: e.target.value })} className="w-full rounded-md border border-border bg-bg/40 px-2 py-1 text-xs">
                  <option value="average">Average balance (iterated)</option><option value="opening">Opening balance</option></select></label>
            </div>
            <div className="space-y-2">
              {inputs.tranches.map((t: any, i: number) => (
                <div key={i} className="p-2 rounded-lg border border-border-subtle bg-bg/30">
                  <div className="flex items-center gap-2 mb-1.5">
                    <input value={t.name} onChange={(e) => setTr(i, { name: e.target.value })} className="flex-1 min-w-0 bg-transparent text-xs font-medium text-text-primary outline-none" />
                    <span className="text-[10px] text-text-tertiary">{KIND_LABEL[t.kind] ?? t.kind}</span>
                    <button onClick={() => setInputs((p) => p && ({ ...p, tranches: p.tranches.filter((_: any, j: number) => j !== i) }))} className="text-text-tertiary hover:text-red" title="Remove"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                  <div className="grid grid-cols-4 gap-1.5">
                    <NumField label="× EBITDA" kind="x" value={t.multiple} onChange={(v) => setTr(i, { multiple: v ?? 0 })} />
                    {t.floating ? <NumField label="Spread" kind="pct" value={t.spread} onChange={(v) => setTr(i, { spread: v ?? 0 })} />
                      : <NumField label="Coupon" kind="pct" value={t.coupon} onChange={(v) => setTr(i, { coupon: v ?? 0 })} />}
                    <NumField label="Amort / yr" kind="pct" value={t.amort_pct} onChange={(v) => setTr(i, { amort_pct: v ?? 0 })} />
                    <NumField label="Tenor (yrs)" kind="int" value={t.tenor} onChange={(v) => setTr(i, { tenor: v ?? 7 })} />
                  </div>
                  <div className="flex gap-3 mt-1.5 text-[10.5px] text-text-secondary">
                    <label className="inline-flex items-center gap-1"><input type="checkbox" checked={!!t.floating} onChange={(e) => setTr(i, { floating: e.target.checked })} />Floating</label>
                    <label className="inline-flex items-center gap-1"><input type="checkbox" checked={!!t.sweep} onChange={(e) => setTr(i, { sweep: e.target.checked })} />Cash sweep</label>
                    {t.kind === 'mezz' && <label className="inline-flex items-center gap-1"><input type="checkbox" checked={t.pik !== false} onChange={(e) => setTr(i, { pik: e.target.checked })} />PIK</label>}
                  </div>
                </div>))}
            </div>
            <div className="grid grid-cols-3 gap-2 mt-2">
              <NumField label="Revolver size" kind={amtKind} value={inputs.revolver?.commitment} onChange={(v) => set({ revolver: { ...inputs.revolver, commitment: v ?? 0 } })} />
              <NumField label="Revolver spread" kind="pct" value={inputs.revolver?.spread} onChange={(v) => set({ revolver: { ...inputs.revolver, spread: v ?? 0 } })} />
              <NumField label="Sweep share" kind="pct" value={inputs.sweep_pct} onChange={(v) => set({ sweep_pct: v ?? 1 })} />
            </div>
          </Card>
          <Card title="Operating plan" right={
            <select value={n} onChange={(e) => set({ years: Number(e.target.value) })} className="text-[11px] rounded-md border border-border bg-bg/40 px-1.5 py-0.5">
              {[5, 6, 7, 8, 9, 10].map((y) => <option key={y} value={y}>{y} years</option>)}</select>}>
            {(['revenue_growth', 'ebitda_margin'] as const).map((k) => (
              <div key={k} className="mb-2">
                <div className="text-[10.5px] text-text-tertiary mb-0.5">{k === 'revenue_growth' ? 'Revenue growth by year' : 'EBITDA margin by year'}</div>
                <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${Math.min(n, 7)}, minmax(0, 1fr))` }}>
                  {asPath(inputs[k], n).map((v, i) => (
                    <NumField key={i} label={`Y${i + 1}`} kind="pct" value={v} onChange={(x) => { const p = asPath(inputs[k], n); p[i] = x ?? 0; set({ [k]: p }); }} />))}
                </div>
              </div>))}
            <div className="grid grid-cols-3 gap-2">
              <NumField label="D&A (% rev)" kind="pct" value={asPath(inputs.dna_pct, n)[0]} onChange={(v) => set({ dna_pct: v ?? 0 })} />
              <NumField label="Capex (% rev)" kind="pct" value={asPath(inputs.capex_pct, n)[0]} onChange={(v) => set({ capex_pct: v ?? 0 })} />
              <NumField label="NWC (% Δ rev)" kind="pct" value={asPath(inputs.nwc_pct, n)[0]} onChange={(v) => set({ nwc_pct: v ?? 0 })} />
              <NumField label="Tax rate" kind="pct" value={inputs.tax_rate} onChange={(v) => set({ tax_rate: v ?? 0 })} />
              <NumField label="Interest cap (% EBITDA)" kind="pct" value={inputs.interest_cap_pct} onChange={(v) => set({ interest_cap_pct: v })} hint="Leave empty for no cap" />
            </div>
          </Card>
          <Card title="Cases">
            {(['upside', 'downside'] as const).map((c) => (
              <div key={c} className="grid grid-cols-4 gap-1.5 mb-1.5 items-end">
                <span className="text-[11px] font-medium capitalize text-text-secondary pb-1.5">{c}</span>
                <NumField label="Growth ±" kind="pct" value={inputs.cases?.[c]?.growth} onChange={(v) => set({ cases: { ...inputs.cases, [c]: { ...inputs.cases?.[c], growth: v ?? 0 } } })} />
                <NumField label="Margin ±" kind="pct" value={inputs.cases?.[c]?.margin} onChange={(v) => set({ cases: { ...inputs.cases, [c]: { ...inputs.cases?.[c], margin: v ?? 0 } } })} />
                <NumField label="Exit mult ±" kind="x" value={inputs.cases?.[c]?.exit_multiple} onChange={(v) => set({ cases: { ...inputs.cases, [c]: { ...inputs.cases?.[c], exit_multiple: v ?? 0 } } })} />
              </div>))}
            <div className="grid grid-cols-3 gap-1.5">
              {(['base', 'upside', 'downside'] as const).map((c) => (
                <NumField key={c} label={`Weight · ${c}`} kind="pct" value={inputs.case_weights?.[c]} onChange={(v) => set({ case_weights: { ...inputs.case_weights, [c]: v ?? 0 } })} />))}
            </div>
          </Card>
          <Card title="Exit & returns">
            <div className="grid grid-cols-3 gap-2">
              <NumField label="Exit year" kind="int" value={inputs.exit_year} onChange={(v) => set({ exit_year: Math.max(1, Math.min(n, Math.round(v ?? 5))) })} />
              <NumField label="Exit EV / EBITDA" kind="x" value={inputs.exit_multiple ?? inputs.entry_multiple} onChange={(v) => set({ exit_multiple: v })} />
              <NumField label="Exit fees" kind="pct" value={inputs.exit_fee_pct} onChange={(v) => set({ exit_fee_pct: v ?? 0 })} />
              <NumField label="MIP (% of gain)" kind="pct" value={inputs.mip_pct} onChange={(v) => set({ mip_pct: v ?? 0 })} hint="Management incentive plan" />
              <NumField label="Hurdle IRR" kind="pct" value={inputs.hurdle_irr} onChange={(v) => set({ hurdle_irr: v ?? 0.2 })} />
            </div>
          </Card>
        </div>

        {/* ── Results ── */}
        <div className="space-y-3 min-w-0">
          {!base ? <div className="p-6 text-xs text-text-tertiary">{busy ? 'Running the model…' : 'Adjust the inputs to run the model.'}</div> : <Results res={res} unit={unit} ccy={ccy} hurdle={hurdle} busy={busy} inputs={inputs} />}
          {sources && (
            <Card title="Where the assumptions come from">
              <dl className="grid grid-cols-1 gap-1.5 text-[11px]">{Object.entries(sources).map(([k, v]) => (
                <div key={k} className="grid grid-cols-[90px_1fr] gap-2"><dt className="capitalize text-text-tertiary">{k}</dt><dd className="text-text-secondary">{v}</dd></div>))}</dl>
            </Card>)}
        </div>
      </div>
    </div>
  );
}

function Results({ res, unit, ccy, hurdle, busy, inputs }: { res: any; unit: number; ccy: string; hurdle: number; busy: boolean; inputs: Inputs }) {
  const b = res.cases.base;
  const m = unit === 1e6 ? 'm' : '';
  const me = res.max_entry;
  const sch: any[] = b.schedule;
  const H = b.exit_year;
  const maxDebt = Math.max(b.debt_raised, ...sch.map((x) => x.debt), 1);
  const bridgeRows = useMemo(() => [
    ['EBITDA growth', b.bridge.ebitda_growth], ['Multiple', b.bridge.multiple], ['Debt paydown / cash', b.bridge.deleveraging],
    ['Fees and costs', b.bridge.fees_and_costs], ['Management (MIP)', b.bridge.mip]] as [string, number][], [b]);
  const bMax = Math.max(...bridgeRows.map(([, v]) => Math.abs(v)), 1);
  return (
    <div className={cn('space-y-3 transition-opacity', busy && 'opacity-70')}>
      {b.warnings?.length > 0 && <div className="p-2.5 rounded-lg border border-amber/40 bg-amber/5 text-[11.5px] text-amber space-y-0.5">{b.warnings.map((w: string) => <div key={w}>⚠ {w}</div>)}</div>}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Kpi label="Sponsor IRR · base" value={pct(b.returns.sponsor_irr)} tone={irrTone(b.returns.sponsor_irr, hurdle)} sub={`hurdle ${pct(hurdle, 0)} · exit year ${H}`} />
        <Kpi label="Money multiple" value={xx(b.returns.moic)} sub={`${ccy} ${amt(b.returns.sponsor_proceeds, ccy, unit)}${m} back on ${amt(b.sponsor_equity, ccy, unit)}${m}`} />
        <Kpi label="Probability-weighted IRR" value={pct(res.weighted.irr)} tone={irrTone(res.weighted.irr, hurdle)} sub={`MOIC ${xx(res.weighted.moic)}`} />
        <Kpi label={`Max price at ${pct(hurdle, 0)} IRR`} value={me.multiple ? xx(me.multiple, 1) : '—'}
          sub={me.price_per_share ? `${me.price_per_share.toFixed(2)} / share (${spct(me.premium_to_price, 0)} vs today)` : me.note ?? `EV ${amt(me.ev, ccy, unit)}${m}`} />
        <Kpi label="Equity cheque" value={`${amt(b.sponsor_equity, ccy, unit)}${m}`} sub={`${pct(b.entry.equity_pct, 0)} of the total cost`} />
        <Kpi label="Closing leverage" value={xx(b.entry.leverage_close, 1)} sub={`net ${xx(b.entry.net_leverage_close, 1)} EBITDA`} />
        <Kpi label="EBITDA cushion" value={res.cushion.to_covenant_breach != null ? pct(res.cushion.to_covenant_breach, 0) : '> 95%'}
          sub={`to a covenant breach · ${res.cushion.to_liquidity_gap != null ? pct(res.cushion.to_liquidity_gap, 0) : '> 95%'} to running out of cash`} />
        <Kpi label="Exit equity" value={`${amt(b.exit.equity_net, ccy, unit)}${m}`} sub={`EV ${amt(b.exit.ev, ccy, unit)}${m} at ${xx(b.exit.multiple, 1)}`} />
      </div>

      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-3">
        <Card title="Cases">
          <table className="w-full text-[11.5px] tabular-nums">
            <thead><tr className="text-text-tertiary text-left"><th className="font-normal" /><th className="font-normal text-right">IRR</th><th className="font-normal text-right">MOIC</th>
              <th className="font-normal text-right">Exit EBITDA</th><th className="font-normal text-right">Exit EV</th><th className="font-normal text-right">Net lev. at exit</th></tr></thead>
            <tbody>{(['upside', 'base', 'downside'] as const).map((c) => { const r = res.cases[c]; const ex = r.schedule[r.exit_year - 1]; return (
              <tr key={c} className="border-t border-border-subtle"><td className="py-1 capitalize text-text-secondary">{c} <span className="text-text-tertiary">· {pct(res.weighted.weights?.[c], 0)}</span></td>
                <td className={cn('text-right font-semibold', irrTone(r.returns.sponsor_irr, hurdle))}>{pct(r.returns.sponsor_irr)}</td><td className="text-right">{xx(r.returns.moic)}</td>
                <td className="text-right">{amt(r.exit.ebitda, ccy, unit)}</td><td className="text-right">{amt(r.exit.ev, ccy, unit)}</td><td className="text-right">{xx(ex.net_leverage, 1)}</td></tr>); })}</tbody>
          </table>
        </Card>
        <Card title="Value creation (equity gain)" right={<span className="text-[11px] text-text-tertiary">{ccy}{m}</span>}>
          <div className="space-y-1.5">
            {bridgeRows.map(([lab, v]) => (
              <div key={lab} className="grid grid-cols-[130px_1fr_70px] items-center gap-2 text-[11.5px]">
                <span className="text-text-secondary">{lab}</span>
                <span className="relative h-3.5 rounded bg-text-primary/[0.04]">
                  <span className={cn('absolute top-0 bottom-0 rounded', v >= 0 ? 'bg-green/70 left-1/2' : 'bg-red/60 right-1/2')} style={{ width: `${(Math.abs(v) / bMax) * 50}%` }} />
                </span>
                <span className="text-right tabular-nums">{amt(v, ccy, unit)}</span>
              </div>))}
            <div className="grid grid-cols-[130px_1fr_70px] gap-2 text-[11.5px] font-semibold pt-1 border-t border-border-subtle"><span>Total gain</span><span /><span className="text-right tabular-nums">{amt(b.bridge.total, ccy, unit)}</span></div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 2xl:grid-cols-2 gap-3">
        <Card title="Sources & uses" right={<span className="text-[11px] text-text-tertiary">{ccy}{m}</span>}>
          <div className="grid grid-cols-2 gap-4 text-[11.5px] tabular-nums">
            <div>{Object.entries(b.sources).filter(([, v]) => (v as number) > 0).map(([k, v]) => (
              <div key={k} className="flex justify-between py-0.5"><span className="text-text-secondary">{k}</span><span>{amt(v as number, ccy, unit)} <span className="text-text-tertiary">{xx((v as number) / b.entry.ebitda, 1)}</span></span></div>))}
              <div className="flex justify-between py-0.5 border-t border-border-subtle font-semibold"><span>Total</span><span>{amt(b.total_uses, ccy, unit)}</span></div></div>
            <div>{Object.entries(b.uses).filter(([, v]) => Math.abs(v as number) > 0).map(([k, v]) => (
              <div key={k} className="flex justify-between py-0.5"><span className="text-text-secondary">{k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())}</span><span>{amt(v as number, ccy, unit)}</span></div>))}
              <div className="flex justify-between py-0.5 border-t border-border-subtle font-semibold"><span>Total</span><span>{amt(b.total_uses, ccy, unit)}</span></div></div>
          </div>
        </Card>
        <Card title="Debt paydown" right={<span className="text-[11px] text-text-tertiary">total debt · net leverage</span>}>
          <div className="flex items-end gap-1.5 h-32">
            {[{ year: 0, debt: b.debt_raised, net_leverage: b.entry.net_leverage_close }, ...sch].map((x: any) => (
              <div key={x.year} className={cn('flex-1 flex flex-col items-center justify-end h-full', x.year > H && 'opacity-40')} title={`Year ${x.year}: ${amt(x.debt, ccy, unit)}${m}`}>
                <span className="text-[9.5px] text-text-tertiary tabular-nums mb-0.5">{xx(x.net_leverage, 1)}</span>
                <span className="w-full rounded-t-md bg-bloomberg/70" style={{ height: `${(x.debt / maxDebt) * 85}%` }} />
                <span className="text-[9.5px] text-text-tertiary mt-0.5">{x.year === 0 ? 'Close' : `Y${x.year}`}</span>
              </div>))}
          </div>
        </Card>
      </div>

      <Card title="Operating model, credit and covenants" right={<span className="text-[11px] text-text-tertiary">{ccy}{m} · base case</span>}>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal" />{sch.map((x) => <th key={x.year} className={cn('text-right font-normal px-1', x.year === H && 'text-bloomberg')}>Y{x.year}{x.year === H ? ' · exit' : ''}</th>)}</tr></thead>
            <tbody>
              {([['Revenue', 'revenue', 'amt'], ['EBITDA', 'ebitda', 'amt'], ['Margin', 'margin', 'pct'], ['Capex', 'capex', 'amt'], ['Cash interest', 'cash_interest', 'amt'],
                ['Tax', 'tax', 'amt'], ['Levered FCF', 'fcf', 'amt'], ['Debt repaid', null, 'repaid'], ['Total debt', 'debt', 'amt'], ['Net debt / EBITDA', 'net_leverage', 'x'],
                ['EBITDA / cash interest', 'interest_cover', 'x'], ['FCF / debt', 'fcf_to_debt', 'pct']] as [string, string | null, string][]).map(([lab, k, f]) => (
                <tr key={lab} className="border-t border-border-subtle"><td className="py-1 pr-2 text-text-secondary whitespace-nowrap">{lab}</td>
                  {sch.map((x) => <td key={x.year} className="text-right px-1">{f === 'repaid' ? amt(x.mandatory + x.sweep, ccy, unit) : f === 'pct' ? pct(x[k!]) : f === 'x' ? xx(x[k!], 1) : amt(x[k!], ccy, unit)}</td>)}</tr>))}
              <tr className="border-t border-border-subtle"><td className="py-1 pr-2 text-text-secondary">Covenants</td>
                {b.covenants.map((c: any) => <td key={c.year} className="text-right px-1">{c.leverage_ok && c.cover_ok ? <span className="text-green">pass</span> : <span className="text-red font-semibold">breach</span>}
                  <div className="text-[9.5px] text-text-tertiary">≤ {xx(c.max_net_leverage, 2)}</div></td>)}</tr>
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="IRR sensitivities" right={<span className="text-[11px] text-text-tertiary">green clears the {pct(hurdle, 0)} hurdle</span>}>
        <div className="grid grid-cols-1 2xl:grid-cols-3 gap-4">
          <IrrGrid g={res.sensitivity.entry_exit} hurdle={hurdle} colFmt={(v) => xx(v, 1)} rowFmt={(v) => xx(v, 1)} />
          <IrrGrid g={res.sensitivity.leverage_growth} hurdle={hurdle} colFmt={(v) => spct(v, 0)} rowFmt={(v) => xx(v, 2)} />
          <IrrGrid g={res.sensitivity.year_exit} hurdle={hurdle} colFmt={(v) => xx(v, 1)} rowFmt={(v) => `Y${v}`} />
        </div>
      </Card>
      <div className="text-[10.5px] text-text-tertiary">Modelled returns are analysis — never a fund track record. {inputs.symbol ? '' : 'Illustrative inputs.'}</div>
    </div>
  );
}

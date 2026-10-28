// Fund tools: the carry waterfall (LP / GP split under a hurdle, catch-up and carry) and fund performance (IRR, TVPI,
// DPI, RVPI and public-market equivalents vs an index) from dated cash flows typed or pasted in.
// Reads /api/v1/pe/fund/{waterfall,performance}.
import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Card, Kpi, NumField, api, pct, spct, xx } from './peShared';

type Flow = { date: string; amount: number };

/** "2020-01-15, -100" lines (comma, tab or spaces) → flows; bad lines are reported. */
function parseFlows(text: string): { flows: Flow[]; bad: number } {
  let bad = 0;
  const flows = text.split(/\n+/).map((l) => l.trim()).filter(Boolean).flatMap((l) => {
    const m = l.match(/^(\d{4}-\d{2}-\d{2})[\s,;\t]+(-?[\d,.]+)$/);
    if (!m) { bad++; return []; }
    return [{ date: m[1], amount: Number(m[2].replace(/,/g, '')) }];
  });
  return { flows, bad };
}

function FlowBox({ label, value, onChange, hint }: { label: string; value: string; onChange: (s: string) => void; hint: string }) {
  return (
    <label className="block">
      <span className="block text-[10.5px] text-text-tertiary mb-0.5">{label}</span>
      <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={6} spellCheck={false}
        className="w-full rounded-md border border-border bg-bg/40 px-2 py-1.5 text-xs font-mono outline-none focus:border-bloomberg/60" />
      <span className="block text-[10px] text-text-tertiary mt-0.5">{hint}</span>
    </label>
  );
}

export function Waterfall() {
  const [contrib, setContrib] = useState('2019-03-01, -40\n2020-06-01, -35\n2021-09-01, -25');
  const [dist, setDist] = useState('2023-05-01, 60\n2024-11-01, 90\n2026-02-01, 85');
  const [terms, setTerms] = useState({ pref: 0.08, carry: 0.2, catch_up: 1.0, compounding: true });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    const c = parseFlows(contrib), d = parseFlows(dist);
    if (c.bad || d.bad) { setErr(`${c.bad + d.bad} line(s) not understood — use "YYYY-MM-DD, amount".`); return; }
    setBusy(true); setErr(null);
    try { setRes(await api('/api/v1/pe/fund/waterfall', { contributions: c.flows, distributions: d.flows, ...terms })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-3 items-start">
      <Card title="Fund cash flows and terms">
        <div className="space-y-2">
          <FlowBox label="Capital called (LP contributions)" value={contrib} onChange={setContrib} hint="One per line: date, amount (sign ignored)" />
          <FlowBox label="Distributions (gross, before carry)" value={dist} onChange={setDist} hint="One per line: date, amount" />
          <div className="grid grid-cols-3 gap-2">
            <NumField label="Preferred return" kind="pct" value={terms.pref} onChange={(v) => setTerms({ ...terms, pref: v ?? 0.08 })} />
            <NumField label="Carried interest" kind="pct" value={terms.carry} onChange={(v) => setTerms({ ...terms, carry: v ?? 0.2 })} />
            <NumField label="GP catch-up" kind="pct" value={terms.catch_up} onChange={(v) => setTerms({ ...terms, catch_up: v ?? 1 })} hint="100% = full catch-up; 50% = shared" />
          </div>
          <label className="inline-flex items-center gap-1.5 text-[11px] text-text-secondary"><input type="checkbox" checked={terms.compounding} onChange={(e) => setTerms({ ...terms, compounding: e.target.checked })} />Compound the preferred return annually</label>
          <button onClick={run} disabled={busy} className="w-full py-1.5 rounded-lg bg-bloomberg text-white text-xs font-medium">{busy ? <Loader2 className="w-3.5 h-3.5 animate-spin inline" /> : 'Run the waterfall'}</button>
          {err && <div className="text-xs text-red">{err}</div>}
          <p className="text-[10.5px] text-text-tertiary">European (whole-fund) waterfall: LPs get their capital back, then the preferred return, then the GP catches up, then the profit splits {pct(1 - terms.carry, 0)} / {pct(terms.carry, 0)}.</p>
        </div>
      </Card>
      {res && (
        <div className="space-y-3 min-w-0">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Kpi label="GP carry" value={res.gp_carry.toLocaleString(undefined, { maximumFractionDigits: 1 })} sub={`${pct(res.gp_share_of_profit)} of the profit`} />
            <Kpi label="LP net multiple" value={xx(res.lp_net_multiple)} sub={`${res.lp_total.toLocaleString(undefined, { maximumFractionDigits: 1 })} back on ${res.contributed.toLocaleString()}`} />
            <Kpi label="LP net IRR" value={pct(res.lp_net_irr)} sub={`gross ${pct(res.gross_irr)} · carry costs ${spct((res.lp_net_irr ?? 0) - (res.gross_irr ?? 0))}`} />
            <Kpi label="Still owed to LPs" value={(res.unreturned_capital + res.pref_outstanding).toLocaleString(undefined, { maximumFractionDigits: 1 })} sub="capital + preferred return outstanding" />
          </div>
          <Card title="Tiers">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[11.5px]">
              {[['Return of capital', res.totals.return_of_capital], ['Preferred return', res.totals.preferred], ['GP catch-up', res.totals.catch_up],
                ['Split to LPs', res.totals.split_lp], ['Split to GP', res.totals.split_gp]].map(([l, v]) => (
                <div key={l as string} className="p-2 rounded-lg bg-text-primary/[0.03]"><div className="text-text-tertiary text-[10.5px]">{l}</div><div className="font-semibold tabular-nums">{(v as number).toLocaleString(undefined, { maximumFractionDigits: 1 })}</div></div>))}
            </div>
          </Card>
          <Card title="Each distribution">
            <table className="w-full text-[11.5px] tabular-nums">
              <thead><tr className="text-text-tertiary text-left"><th className="font-normal">Date</th><th className="font-normal text-right">Distribution</th><th className="font-normal text-right">Capital</th>
                <th className="font-normal text-right">Pref</th><th className="font-normal text-right">Catch-up</th><th className="font-normal text-right">Split LP</th><th className="font-normal text-right">Split GP</th>
                <th className="font-normal text-right">To LPs</th><th className="font-normal text-right">To GP</th></tr></thead>
              <tbody>{res.rows.map((r: any) => (
                <tr key={r.date} className="border-t border-border-subtle">{[r.date, r.amount, r.return_of_capital, r.preferred, r.catch_up_gp, r.split_lp, r.split_gp, r.lp, r.gp].map((v, i) => (
                  <td key={i} className={i ? 'text-right py-1' : 'py-1'}>{typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 1 }) : v}</td>))}</tr>))}</tbody>
            </table>
          </Card>
        </div>)}
    </div>
  );
}

export function Performance() {
  const [flows, setFlows] = useState('2018-01-15, -30\n2019-04-01, -40\n2020-07-01, -30\n2022-03-01, 45\n2024-06-01, 70');
  const [nav, setNav] = useState<number | null>(60);
  const [navDate, setNavDate] = useState(new Date().toISOString().slice(0, 10));
  const [index, setIndex] = useState('^SP500TR');
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    const f = parseFlows(flows);
    if (f.bad) { setErr(`${f.bad} line(s) not understood — use "YYYY-MM-DD, amount" (negative = capital called).`); return; }
    setBusy(true); setErr(null);
    try { setRes(await api('/api/v1/pe/fund/performance', { flows: f.flows, nav: nav ?? 0, nav_date: navDate, index: index.trim() || null })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const p = res?.pme;
  return (
    <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-3 items-start">
      <Card title="Fund cash flows">
        <div className="space-y-2">
          <FlowBox label="Cash flows (LP view)" value={flows} onChange={setFlows} hint="date, amount — negative = capital called, positive = distribution" />
          <div className="grid grid-cols-2 gap-2">
            <NumField label="Current NAV" value={nav} onChange={setNav} />
            <label className="block"><span className="block text-[10.5px] text-text-tertiary mb-0.5">NAV date</span>
              <input type="date" value={navDate} onChange={(e) => setNavDate(e.target.value)} className="w-full rounded-md border border-border bg-bg/40 px-2 py-1 text-xs" /></label>
          </div>
          <label className="block"><span className="block text-[10.5px] text-text-tertiary mb-0.5">Public benchmark (total return)</span>
            <input value={index} onChange={(e) => setIndex(e.target.value)} className="w-full rounded-md border border-border bg-bg/40 px-2 py-1 text-xs" />
            <span className="block text-[10px] text-text-tertiary mt-0.5">^SP500TR (S&P 500 TR), URTH (MSCI World), ^FTAS… — Yahoo Finance</span></label>
          <button onClick={run} disabled={busy} className="w-full py-1.5 rounded-lg bg-bloomberg text-white text-xs font-medium">{busy ? <Loader2 className="w-3.5 h-3.5 animate-spin inline" /> : 'Measure performance'}</button>
          {err && <div className="text-xs text-red">{err}</div>}
        </div>
      </Card>
      {res && (
        <div className="space-y-3 min-w-0">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Kpi label="Net IRR" value={pct(res.irr)} sub={`over ${res.years.toFixed(1)} years`} />
            <Kpi label="TVPI" value={xx(res.tvpi)} sub="total value / paid-in" />
            <Kpi label="DPI" value={xx(res.dpi)} sub="distributed / paid-in" />
            <Kpi label="RVPI" value={xx(res.rvpi)} sub="NAV / paid-in" />
          </div>
          {p && !p.error && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Kpi label="KS-PME" value={xx(p.ks_pme)} tone={p.ks_pme >= 1 ? 'text-green' : 'text-red'} sub={p.ks_pme >= 1 ? `beat ${res.index_symbol}` : `lagged ${res.index_symbol}`} />
              <Kpi label="Direct Alpha" value={spct(p.direct_alpha)} tone={(p.direct_alpha ?? 0) >= 0 ? 'text-green' : 'text-red'} sub="annual excess return over the index" />
              <Kpi label="Index IRR (Long-Nickels)" value={pct(p.ln_pme_irr)} sub={p.ln_pme_note ? 'not defined — see note' : 'the same flows in the index'} />
              <Kpi label="Index over the period" value={spct(p.index_return)} sub={res.index_symbol} />
            </div>)}
          {p?.error && <div className="text-xs text-amber">{p.error}</div>}
          {p?.ln_pme_note && <div className="text-[11px] text-text-tertiary">{p.ln_pme_note}</div>}
          <p className="text-[10.5px] text-text-tertiary">KS-PME (Kaplan & Schoar 2005) above 1× means the fund beat the index on the same timing of cash flows; Direct Alpha (Gredil, Griffiths & Stucke 2014) is that excess as an annual rate.</p>
        </div>)}
    </div>
  );
}

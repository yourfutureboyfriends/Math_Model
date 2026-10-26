/**
 * Fund Governance — the operating controls of the fund's written plan (built for Moriah Capital Partners' Future
 * Growth Strategy): stage and mandate, the approved-instruments list, the G0–G5 model gates with independent
 * sign-offs, execution halt / incidents / reconciliation, the monthly internal reporting pack, the board scorecard,
 * the budget ledger, the milestone roadmap and break-even AUM. Backend: /api/v1/governance/* (api/governance.py).
 */
import { createContext, Fragment, useCallback, useContext, useEffect, useState } from 'react';
import { TeamPositions } from './TeamPositions';
import { BrokerLink } from './BrokerLink';
import { Loader2, ShieldAlert, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useConfirm } from '@/components/ui/ConfirmDialog';
import { forgetFundLogo } from '@/lib/fundLogo';
import { BrandShape, Letterhead } from '@/components/layout/FundIdentity';
import { currentFund } from '@/lib/fund';
import { apiCall } from '@/lib/http';
import { num } from '@/lib/format';

// what the signed-in person's position allows in this fund (buttons greyed out; the server enforces it regardless)
const CapsCtx = createContext<Record<string, boolean> | null>(null);
const useCan = () => { const c = useContext(CapsCtx); return (k: string) => !c || c[k] !== false; };
const NO = 'Your position in this fund does not include this';

// window.prompt/confirm are suppressed in some embedded browsers: an in-app dialog instead
function useSay() {
  const [dialog, ask] = useConfirm();
  const say = (title: string) => ask({ title, input: { label: 'Text', defaultValue: '' }, confirmLabel: 'OK' }) as Promise<string | null>;
  return { dialog, say, ask };
}

const call = apiCall;

const pct = (v?: number | null, d = 0) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
const inputCls = 'bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary focus:border-bloomberg outline-none';
const btn = 'px-2 py-0.5 border border-border hover:border-bloomberg text-2xs disabled:opacity-40';

function useLoad<T>(url: string) {
  const [d, setD] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => { call(url).then((x) => { setD(x); setErr(null); }).catch((e) => setErr(e.message)); }, [url]);
  useEffect(load, [load]);
  return { d, err, load, setErr };
}

function Box({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('border border-border bg-surface-2 p-2', className)}>
      <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">{title}</div>{children}
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex justify-between gap-2 text-2xs py-0.5 border-b border-border-subtle last:border-0"><span className="text-text-tertiary">{k}</span><span className="font-mono text-right">{v}</span></div>;
}

// ── overview ─────────────────────────────────────────────────────────────────
function Overview({ g, reload }: { g: any; reload: () => void }) {
  const { dialog, ask } = useSay();
  const sc = useLoad<any>('/api/v1/governance/scorecard');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const st = g.settings;
  const setup = async () => {
    if (!(await ask({ title: 'Configure THIS fund', confirmLabel: 'Configure', body: 'Configure THIS fund as Moriah Capital Partners (Phase I): GBP base, cash benchmark, £25,000 paper notional, governance on, proposed instruments, budget and milestones from the plan?' }))) return;
    setBusy(true);
    try { await call('/api/v1/governance/setup/moriah', 'POST'); setMsg('Configured.'); reload(); sc.load(); } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };
  const p = st.risk_policy;
  return (
    <div className="space-y-2 text-xs">
      {dialog}
      {!st.enabled && (
        <div className="p-2 border border-amber/40 text-amber text-2xs flex items-center gap-2">Governance controls (model gates, approved instruments, halts on breaks) are off for this fund; the monthly pack, reconciliation, budget, roadmap and data licences work without them.
          <button className={btn} disabled={busy} onClick={setup}>Set up as Moriah Capital Partners (admin)</button>{msg}</div>)}
      <div className={cn('p-2 border text-2xs flex items-center gap-2', g.halt ? 'border-red/50 text-red' : 'border-green/40 text-green')}>
        {g.halt ? <ShieldAlert className="w-3.5 h-3.5" /> : <ShieldCheck className="w-3.5 h-3.5" />}
        {g.halt ? `EXECUTION HALTED (${g.halt.kind}) since ${String(g.halt.started_at).slice(0, 16).replace('T', ' ')}: ${g.halt.reason}` : 'Execution enabled — no active halt'}
        <span className="ml-auto text-text-tertiary">{g.open_incidents} open incident(s)</span>
      </div>
      <div className="grid md:grid-cols-3 gap-2">
        <Box title="Fund">
          <KV k="Name" v={st.fund_name} /><KV k="Stage" v={st.stage_label} /><KV k="Base currency" v={st.base_currency} />
          <KV k="Capital" v={`${num(st.capital, 0)} ${st.base_currency}`} />
          {st.capital_basis && <div className="text-[10px] text-amber mt-1">{st.capital_basis}</div>}
          <div className="text-[10px] text-text-tertiary mt-1">Results label: <span className="text-text-secondary">{g.label}</span></div>
        </Box>
        <Box title="Risk policy">
          <KV k="Single-model ex-ante risk" v={`≤ ${pct(p.max_model_risk_share)}`} /><KV k="Single theme" v={`≤ ${pct(p.max_theme_risk_share)}`} />
          <KV k="Gross leverage" v={`≤ ${pct(p.max_gross_leverage)} (no borrowing)`} /><KV k="Short selling" v={p.allow_short ? 'allowed' : 'not permitted'} />
          <KV k="Daily loss pause" v={pct(p.daily_loss_pause)} /><KV k="Strategy drawdown" v={`review ${pct(p.strategy_dd_review)} · suspend ${pct(p.strategy_dd_suspend)}`} />
          <KV k="Order size / price band / price age" v={`${pct(p.max_order_pct_nav)} NAV · ±${pct(p.price_band)} · ${p.max_price_age_days}d`} />
          <KV k="Orders need an approved model" v={st.require_approved_model ? 'yes (G3+)' : 'no'} />
        </Box>
        <Box title="Board scorecard">
          {sc.d ? (<>
            <KV k="Models · approved (G2+) : rejected" v={`${sc.d.research.models} · ${sc.d.research.approved_to_rejected}`} />
            <KV k="Reconciliation rate (90d)" v={sc.d.trading_and_risk.reconciliation_rate == null ? '—' : pct(sc.d.trading_and_risk.reconciliation_rate)} />
            <KV k="Cost vs estimate" v={sc.d.trading_and_risk.cost_vs_estimate_bps == null ? '—' : `${sc.d.trading_and_risk.cost_vs_estimate_bps} bp`} />
            <KV k="Max drawdown · limit exceptions" v={`${sc.d.trading_and_risk.max_drawdown_pct}% · ${sc.d.trading_and_risk.limit_exceptions}`} />
            <KV k="Milestones done / signed off" v={`${sc.d.organisation.done}/${sc.d.organisation.milestones} · ${sc.d.organisation.signed_off}`} />
            <KV k="Open incidents · kill-switch tests" v={`${sc.d.organisation.incidents_open} · ${sc.d.organisation.kill_switch_tests}`} />
            <KV k="Budget spent / total" v={`${num(sc.d.organisation.budget.spent)} / ${num(sc.d.organisation.budget.total)}`} />
            {sc.d.data && <KV k="Data sources unreviewed / restricted" v={`${sc.d.data.unreviewed} / ${sc.d.data.not_allowed_or_restricted} of ${sc.d.data.sources}`} />}
            <div className="text-[10px] text-text-tertiary mt-1">{sc.d.commercial.note}</div>
          </>) : <div className="text-text-tertiary text-2xs">{sc.err ?? 'Loading…'}</div>}
        </Box>
      </div>
      <LogoUpload />
      {st.mandate_text && <Box title="Written mandate"><pre className="whitespace-pre-wrap text-[11px] text-text-secondary font-sans">{st.mandate_text}</pre></Box>}
    </div>
  );
}

function LogoUpload() {
  const [msg, setMsg] = useState<string | null>(null);
  const up = (variant: 'full' | 'mark' | 'mark_mask' | 'word_mask') => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        await call(`/api/v1/funds/${encodeURIComponent(currentFund())}/logo`, 'PUT', { variant, data_base64: String(reader.result) });
        forgetFundLogo(currentFund()); setMsg('Updated — reload to see it everywhere.');
      } catch (x: any) { setMsg(x.message); }
    };
    reader.readAsDataURL(file);
  };
  return (
    <div className="text-[10px] text-text-tertiary flex flex-wrap gap-3 items-center">Fund logo (administrator):
      <label className="cursor-pointer underline">full logo<input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={up('full')} /></label>
      <label className="cursor-pointer underline">emblem shape<input type="file" accept="image/png,image/webp" className="hidden" onChange={up('mark_mask')} /></label>
      <label className="cursor-pointer underline">wordmark shape<input type="file" accept="image/png,image/webp" className="hidden" onChange={up('word_mask')} /></label>
      <span>(shapes: white on transparent — the app colours them)</span>
      {msg && <span className="text-amber">{msg}</span>}
    </div>
  );
}

// ── models ───────────────────────────────────────────────────────────────────
const EMPTY = { name: '', sleeve: 'macro_transmission', mechanism: '', target_variable: '', horizon: '', dataset: '', null_hypothesis: '' };

function ModelDetail({ id, g, onChange }: { id: number; g: any; onChange: () => void }) {
  const { dialog, say } = useSay();
  const { d: m, err, load, setErr } = useLoad<any>(`/api/v1/governance/models/${id}`);
  const sh = useLoad<any>(`/api/v1/governance/models/${id}/shadow`);
  const [checks, setChecks] = useState<Record<string, { ok: boolean; note: string }>>({});
  const [result, setResult] = useState({ owner: '', id: '' });
  const [note, setNote] = useState('');
  const [alloc, setAlloc] = useState({ allocation: '', max_loss_budget: '', retirement_criterion: '' });
  if (!m) return <div className="text-2xs text-text-tertiary p-2">{err ?? 'Loading…'}</div>;
  const next = m.next_gate;
  const info = next ? g.gates[next] : null;
  const act = async (fn: () => Promise<any>) => { try { await fn(); setNote(''); setChecks({}); load(); onChange(); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="p-2 space-y-2 text-2xs">
      {dialog}
      {err && <div className="text-amber">{err}</div>}
      <div className="grid md:grid-cols-2 gap-2">
        <Box title={`#${m.id} ${m.name} — v${m.version}`}>
          <KV k="Sleeve · book" v={`${g.sleeves[m.sleeve] ?? m.sleeve} · ${m.book}`} /><KV k="Owner" v={m.owner} />
          <KV k="Gate · status" v={`${m.gate} ${g.gates[m.gate]?.name ?? ''} · ${m.status}`} />
          <KV k="Allocation · loss budget" v={`${num(m.allocation, 0)} · ${m.max_loss_budget ? pct(m.max_loss_budget, 1) : '—'}`} />
          <KV k="Retirement criterion" v={m.retirement_criterion ?? '—'} />
          <div className="mt-1 text-text-secondary"><b>Mechanism:</b> {m.mechanism}<br /><b>Target:</b> {m.target_variable} · <b>Horizon:</b> {m.horizon}<br /><b>Dataset:</b> {m.dataset}<br /><b>Null:</b> {m.null_hypothesis}</div>
        </Box>
        <Box title="Risk allocation (set before G3)">
          <div className="flex flex-wrap gap-1">
            <input className={inputCls} placeholder="allocation (base ccy)" value={alloc.allocation} onChange={(e) => setAlloc({ ...alloc, allocation: e.target.value })} />
            <input className={inputCls} placeholder="max loss budget e.g. 0.08" value={alloc.max_loss_budget} onChange={(e) => setAlloc({ ...alloc, max_loss_budget: e.target.value })} />
            <input className={cn(inputCls, 'w-full')} placeholder="retirement criterion" value={alloc.retirement_criterion} onChange={(e) => setAlloc({ ...alloc, retirement_criterion: e.target.value })} />
            <button className={btn} onClick={() => act(() => call(`/api/v1/governance/models/${id}`, 'PUT', {
              allocation: alloc.allocation ? Number(alloc.allocation) : undefined, max_loss_budget: alloc.max_loss_budget ? Number(alloc.max_loss_budget) : undefined,
              retirement_criterion: alloc.retirement_criterion || undefined }))}>Save</button>
          </div>
          <div className="flex gap-1 mt-2">
            {(['reject', 'retire', 'suspend', 'reactivate'] as const).map((a) => (
              <button key={a} className={btn} onClick={async () => { const n = await say(`Reason to ${a} model #${m.id}:`); if (n) act(() => call(`/api/v1/governance/models/${id}/close`, 'POST', { action: a, note: n })); }}>{a}</button>))}
          </div>
        </Box>
      </div>
      <Box title="Shadow trading (G3 evidence) — the model's Quant Lab paper deployment in this fund">
        {!sh.d ? <div className="text-text-tertiary">{sh.err ?? 'Loading…'}</div> : !sh.d.available ? (
          <div className="text-text-tertiary">{sh.d.reason}. Once the backtest is approved (G2), deploy it from Quant Lab and choose this model: its daily paper record, locked each session, becomes the evidence.</div>
        ) : (<>
          <KV k="Deployment" v={`#${sh.d.deployment_id} ${sh.d.name} · ${sh.d.active ? 'running' : 'stopped'} · from ${sh.d.deployed_at}`} />
          <KV k="Sessions recorded" v={`${sh.d.sessions} / ${sh.d.min_sessions} needed`} />
          {sh.d.live && <KV k="Live: return · vol · Sharpe · max DD" v={`${pct(sh.d.live.return, 1)} · ${pct(sh.d.live.vol, 1)} · ${sh.d.live.sharpe ?? '—'} · ${pct(sh.d.live.max_drawdown, 1)}`} />}
          <KV k="Backtest: CAGR · vol · Sharpe" v={`${pct(sh.d.backtest.cagr, 1)} · ${pct(sh.d.backtest.vol, 1)} · ${sh.d.backtest.sharpe ?? '—'}`} />
          {(sh.d.drift_flags ?? []).map((f: string) => <div key={f} className="text-amber">Drift: {f}</div>)}
          <div className={sh.d.ready ? 'text-green' : 'text-text-tertiary'}>{sh.d.ready ? 'Ready for the G3 sign-off by risk.' : 'Not yet sufficient for G3.'}</div>
        </>)}
      </Box>
      {next && m.status === 'active' && info && (
        <Box title={`Sign off ${next} — ${info.name} (${info.authority}; never the owner)`}>
          {m.pending_signoffs?.length > 0 && <div className="text-text-secondary mb-1">Signed so far: {m.pending_signoffs.map((s: any) => `${s.user} (${s.role})`).join(', ')} — needs {g.gate_signoffs[next].length} distinct sign-off(s)</div>}
          {info.evidence.map((e: string) => (
            <label key={e} className="flex items-center gap-2 py-0.5">
              <input type="checkbox" checked={!!checks[e]?.ok} onChange={(x) => setChecks({ ...checks, [e]: { ok: x.target.checked, note: checks[e]?.note ?? '' } })} />
              <span className="w-56">{e}</span>
              <input className={cn(inputCls, 'flex-1')} placeholder="evidence / reference" value={checks[e]?.note ?? ''} onChange={(x) => setChecks({ ...checks, [e]: { ok: checks[e]?.ok ?? false, note: x.target.value } })} />
            </label>))}
          {next === 'G2' && (
            <div className="flex gap-1 items-center mt-1">Quant Lab result: <input className={inputCls} placeholder="owner" value={result.owner} onChange={(e) => setResult({ ...result, owner: e.target.value })} />
              <input className={cn(inputCls, 'w-20')} placeholder="id" value={result.id} onChange={(e) => setResult({ ...result, id: e.target.value })} />
              <span className="text-text-tertiary">costs, out-of-sample, look-ahead and multiple-testing are checked automatically</span></div>)}
          <div className="flex gap-1 mt-1">
            <input className={cn(inputCls, 'flex-1')} placeholder="note" value={note} onChange={(e) => setNote(e.target.value)} />
            <button className={btn} onClick={() => act(() => call(`/api/v1/governance/models/${id}/signoff`, 'POST', {
              evidence: { checks, ...(next === 'G2' ? { result: { owner: result.owner, id: Number(result.id) } } : {}) }, note }))}>Sign off</button>
          </div>
        </Box>)}
      <Box title="History (research log)">
        {m.events.map((e: any) => (
          <div key={e.id} className="border-b border-border-subtle last:border-0 py-0.5">
            <span className="font-mono text-text-tertiary">{String(e.ts).slice(0, 16).replace('T', ' ')}</span> {e.action} {e.gate_to ?? e.gate_from ?? ''} · {e.user}{e.role ? ` (${e.role})` : ''}{e.note ? ` — ${e.note}` : ''}
            {e.evidence?.facts && Object.keys(e.evidence.facts).length > 0 && <div className="text-text-tertiary font-mono text-[10px]">{JSON.stringify(e.evidence.facts)}</div>}
          </div>))}
      </Box>
    </div>
  );
}

function Models({ g }: { g: any }) {
  const can = useCan();
  const { d, err, load } = useLoad<any>('/api/v1/governance/models');
  const [open, setOpen] = useState<number | null>(null);
  const [f, setF] = useState<any>(EMPTY);
  const [msg, setMsg] = useState<string | null>(null);
  const create = async () => { try { const m = await call('/api/v1/governance/models', 'POST', f); setF(EMPTY); setMsg(null); load(); setOpen(m.id); } catch (e: any) { setMsg(e.message); } };
  return (
    <div className="space-y-2 text-xs">
      <Box title="G0 — new research proposal (economic mechanism, target, horizon, dataset, null hypothesis)">
        <div className="grid md:grid-cols-2 gap-1">
          <input className={inputCls} placeholder="name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <select className={inputCls} value={f.sleeve} onChange={(e) => setF({ ...f, sleeve: e.target.value })}>
            {Object.entries(g.sleeves).map(([k, v]) => <option key={k} value={k}>{v as string}</option>)}</select>
          {(['mechanism', 'target_variable', 'horizon', 'dataset', 'null_hypothesis'] as const).map((k) => (
            <input key={k} className={inputCls} placeholder={k.replace('_', ' ')} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />))}
        </div>
        <div className="flex gap-2 items-center mt-1"><button disabled={!can('model_propose')} title={can('model_propose') ? undefined : NO} className={btn} onClick={create}>Propose</button>{msg && <span className="text-amber text-2xs">{msg}</span>}</div>
      </Box>
      {err && <div className="text-amber text-2xs">{err}</div>}
      <table className="w-full text-xs">
        <thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle"><th className="text-left font-normal py-1">Model</th><th className="text-left font-normal">Sleeve</th><th className="text-left font-normal">Owner</th><th className="text-left font-normal">Gate</th><th className="text-left font-normal">Status</th></tr></thead>
        <tbody>{(d?.models ?? []).map((m: any) => (
          <Fragment key={m.id}>
            <tr className="border-b border-border-subtle cursor-pointer hover:bg-surface-2" onClick={() => setOpen(open === m.id ? null : m.id)}>
              <td className="py-1">#{m.id} {m.name} <span className="text-text-tertiary">v{m.version}</span></td><td>{g.sleeves[m.sleeve] ?? m.sleeve}</td><td>{m.owner}</td>
              <td className="font-mono">{m.gate} <span className="text-text-tertiary font-sans">{g.gates[m.gate]?.name}</span></td>
              <td className={cn(m.status === 'active' ? 'text-green' : m.status === 'suspended' ? 'text-amber' : 'text-text-tertiary')}>{m.status}</td>
            </tr>
            {open === m.id && <tr><td colSpan={5}><ModelDetail id={m.id} g={g} onChange={load} /></td></tr>}
          </Fragment>))}
          {d && d.models.length === 0 && <tr><td colSpan={5} className="text-text-tertiary text-2xs py-2">No models yet. Year one per the plan: one benchmark sleeve and one original macro-transmission sleeve.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// ── instruments ──────────────────────────────────────────────────────────────
function Instruments() {
  const can = useCan();
  const { d, err, load, setErr } = useLoad<any>('/api/v1/governance/instruments');
  const [f, setF] = useState({ symbol: '', name: '', asset_class: '', theme: '', currency: '', tradable: true, note: '' });
  const act = async (fn: () => Promise<any>) => { try { await fn(); load(); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="space-y-2 text-xs">
      {err && <div className="text-amber text-2xs">{err}</div>}
      <table className="w-full">
        <thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle"><th className="text-left font-normal py-1">Symbol</th><th className="text-left font-normal">Name</th><th className="text-left font-normal">Class · theme</th><th className="text-left font-normal">Status</th><th /></tr></thead>
        <tbody>{(d?.instruments ?? []).map((i: any) => (
          <tr key={i.symbol} className="border-b border-border-subtle">
            <td className="py-1 font-mono">{i.symbol}</td>
            <td className="text-text-secondary">{i.name}{!i.tradable && <span className="text-amber"> · research series only</span>}{i.note ? <div className="text-[10px] text-text-tertiary">{i.note}</div> : null}</td>
            <td className="text-text-secondary">{i.asset_class} · {i.theme}</td>
            <td className={cn(i.status === 'approved' ? 'text-green' : i.status === 'removed' ? 'text-text-tertiary' : 'text-amber')}>{i.status}{i.approved_by ? ` (${i.approved_by})` : ''}</td>
            <td className="text-right whitespace-nowrap">
              {i.status !== 'approved' && <button className={btn} disabled={!can('instruments_approve')} title={can('instruments_approve') ? undefined : NO} onClick={() => act(() => call(`/api/v1/governance/instruments/${encodeURIComponent(i.symbol)}/decision`, 'POST', { approve: true }))}>Approve</button>}
              {i.status !== 'removed' && <button disabled={!can('instruments_approve')} title={can('instruments_approve') ? undefined : NO} className={cn(btn, 'ml-1')} onClick={() => act(() => call(`/api/v1/governance/instruments/${encodeURIComponent(i.symbol)}/decision`, 'POST', { approve: false }))}>Remove</button>}
            </td>
          </tr>))}</tbody>
      </table>
      <Box title="Propose an instrument (approved by another person — PM or risk)">
        <div className="flex flex-wrap gap-1">
          {(['symbol', 'name', 'asset_class', 'theme', 'currency', 'note'] as const).map((k) => (
            <input key={k} className={inputCls} placeholder={k.replace('_', ' ')} value={(f as any)[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />))}
          <label className="flex items-center gap-1 text-2xs"><input type="checkbox" checked={f.tradable} onChange={(e) => setF({ ...f, tradable: e.target.checked })} />tradable</label>
          <button className={btn} onClick={() => act(() => call('/api/v1/governance/instruments', 'POST', f))}>Propose</button>
        </div>
      </Box>
    </div>
  );
}

// ── controls ─────────────────────────────────────────────────────────────────
function Controls({ reload }: { reload: () => void }) {
  const can = useCan();
  const { dialog, say } = useSay();
  const { d, err, load, setErr } = useLoad<any>('/api/v1/governance/controls');
  const [busy, setBusy] = useState(false);
  const act = async (fn: () => Promise<any>) => { setBusy(true); try { await fn(); load(); reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); } };
  if (!d) return <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div>;
  return (
    <div className="space-y-2 text-xs">
      {dialog}
      {err && <div className="text-amber text-2xs">{err}</div>}
      <Box title="Kill switch">
        <div className="flex gap-1 flex-wrap items-center">
          {d.halt ? <>
            <span className="text-red text-2xs">Halted ({d.halt.kind}): {d.halt.reason}{d.halt.incident_id ? ` — incident #${d.halt.incident_id}` : ''}</span>
            <button disabled={busy || !can('resume_trading')} title={can('resume_trading') ? undefined : NO} className={btn} onClick={async () => { const r = await say('Resolution (risk role; an incident must be fixed and independently signed off first):'); if (r) act(() => call('/api/v1/governance/controls/resume', 'POST', { text: r })); }}>Resume trading</button>
          </> : <>
            <button disabled={busy || !can('halt_trading')} title={can('halt_trading') ? undefined : NO} className={btn} onClick={async () => { const r = await say('Reason to HALT all new orders and executions:'); if (r) act(() => call('/api/v1/governance/controls/halt', 'POST', { reason: r })); }}>Halt execution</button>
            <button disabled={busy || !can('halt_trading')} title={can('halt_trading') ? undefined : NO} className={btn} onClick={() => act(() => call('/api/v1/governance/controls/halt', 'POST', { reason: 'kill-switch test', test: true }))}>Start a kill-switch test</button>
          </>}
          <button disabled={busy || !can('reconcile')} title={can('reconcile') ? undefined : NO} className={cn(btn, 'ml-auto')} onClick={() => act(() => call('/api/v1/governance/controls/reconcile', 'POST'))}>{busy ? <Loader2 className="w-3 h-3 animate-spin inline" /> : 'Reconcile positions now'}</button>
        </div>
      </Box>
      <Box title="Incidents">
        <div className="flex justify-end mb-1"><button className={btn} onClick={async () => { const t = await say('Describe the operational incident:'); if (t) act(() => call('/api/v1/governance/incidents', 'POST', { text: t })); }}>Log incident</button></div>
        {d.incidents.length === 0 ? <div className="text-text-tertiary text-2xs">None.</div> : d.incidents.map((i: any) => (
          <div key={i.id} className="border-b border-border-subtle py-1 text-2xs flex gap-2 items-start">
            <span className="font-mono">#{i.id}</span><span className="text-text-tertiary">{String(i.ts).slice(0, 16).replace('T', ' ')}</span>
            <span className="flex-1">{i.kind}: {i.description}{i.fix ? <div className="text-text-tertiary">fix ({i.fixed_by}): {i.fix}</div> : null}</span>
            <span className={cn(i.status === 'signed_off' ? 'text-green' : 'text-amber')}>{i.status}{i.signed_off_by ? ` (${i.signed_off_by})` : ''}</span>
            {i.status === 'open' && <button className={btn} onClick={async () => { const t = await say('Fix and how it was tested:'); if (t) act(() => call(`/api/v1/governance/incidents/${i.id}/fix`, 'POST', { text: t })); }}>Record fix</button>}
            {i.status === 'fixed' && <button disabled={!can('incidents_signoff')} title={can('incidents_signoff') ? undefined : NO} className={btn} onClick={() => act(() => call(`/api/v1/governance/incidents/${i.id}/signoff`, 'POST'))}>Independent sign-off</button>}
          </div>))}
      </Box>
      <Box title="Reconciliations (positions vs fills ledger; daily T+1 at 06:30 UTC)">
        {d.reconciliations.length === 0 ? <div className="text-text-tertiary text-2xs">None yet.</div> : d.reconciliations.slice(0, 10).map((r: any) => (
          <div key={r.id} className="text-2xs border-b border-border-subtle py-0.5"><span className="font-mono">{String(r.ts).slice(0, 16).replace('T', ' ')}</span> · {r.checked} checked · <span className={r.ok ? 'text-green' : 'text-red'}>{r.ok ? 'clean' : `${r.breaks.length} break(s)`}</span> · {r.run_by}</div>))}
        <div className="text-[10px] text-text-tertiary mt-1">{d.reconciliations[0]?.notes}</div>
      </Box>
    </div>
  );
}

// ── monthly pack ─────────────────────────────────────────────────────────────
function Monthly() {
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const { d, err } = useLoad<any>(`/api/v1/governance/report/monthly?month=${month}`);
  return (
    <div className="space-y-2 text-xs">
      <div className="flex gap-2 items-center">
        <input type="month" className={inputCls} value={month} onChange={(e) => setMonth(e.target.value)} />
        <button className={btn} onClick={() => window.print()}>Print</button>
        {d && <span className="text-amber text-2xs">{d.label}</span>}
      </div>
      {d && <Letterhead title={`Monthly internal report — ${d.month}`}
                        sub={[String(d.stage).includes('governance off') ? null : d.stage, d.currency, d.label].filter(Boolean).join(' · ')} />}
      {!d ? <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div> : (
        <div className="grid md:grid-cols-2 gap-2">
          <Box title={`Returns (${d.currency})`}>
            <KV k="Month (net, flow-adjusted)" v={d.returns.month_return == null ? '—' : `${d.returns.month_return}%`} />
            <KV k="Cumulative since series start" v={d.returns.cumulative_return == null ? '—' : `${d.returns.cumulative_return}% (from ${d.returns.series_start})`} />
            <KV k="NAV start → end" v={`${num(d.returns.nav_start)} → ${num(d.returns.nav_end)}`} />
            <KV k="Cash flows" v={Object.keys(d.returns.cash_flows).length ? JSON.stringify(d.returns.cash_flows) : 'none'} />
            <KV k="Trading costs (commission + taxes)" v={`${num(d.returns.trading_costs.commission)} + ${num(d.returns.trading_costs.taxes)}`} />
            <KV k="Realised · unrealised P&L" v={`${num(d.returns.realised_pnl)} · ${num(d.returns.unrealised_pnl)}`} />
            {d.returns.benchmark && <KV k={`Benchmark (${d.returns.benchmark.code}) · active`} v={`${d.returns.benchmark.month_return ?? '—'}% · ${d.returns.benchmark.active_return ?? '—'}%`} />}
          </Box>
          <Box title="Risk">
            <KV k="Max drawdown to date" v={`${d.risk.max_drawdown_to_date}%`} /><KV k="Volatility (ann.)" v={d.risk.volatility_ann == null ? '—' : `${d.risk.volatility_ann}%`} />
            <KV k="Gross · net" v={`${pct(d.risk.gross, 1)} · ${pct(d.risk.net, 1)}`} />
            <KV k="Limit exceptions · incidents · halts" v={`${d.risk.limit_exceptions.length} · ${d.risk.incidents.length} · ${d.risk.halts.length}`} />
            <div className="text-[10px] text-text-tertiary uppercase mt-2">Stress conditions (the plan's list) on the book</div>
            {(d.risk.stress?.scenarios ?? []).map((x: any) => (
              <div key={x.id} className="flex justify-between gap-2 text-2xs py-0.5 border-b border-border-subtle last:border-0">
                <span className="text-text-tertiary">{x.label}{x.start ? ` (${x.start} → ${x.end})` : ''}</span>
                <span className="font-mono text-right">{x.kind === 'procedure' ? <span className="font-sans text-text-secondary">{x.result}</span>
                  : <>{num(x.pnl)} {d.currency} · {x.pnl_pct_gross ?? '—'}%{x.coverage != null && x.coverage < 1 ? ` · coverage ${Math.round(x.coverage * 100)}%` : ''}</>}</span>
              </div>))}
            <div className="text-[10px] text-text-tertiary mt-1">{d.risk.stress?.note}</div>
          </Box>
          <Box title="Attribution">
            {(['by_sleeve', 'by_instrument'] as const).map((k) => (
              <div key={k} className="mb-1"><div className="text-[10px] text-text-tertiary">{k.replace('by_', 'by ')}</div>
                {Object.entries(d.attribution[k]).length === 0 ? <div className="text-text-tertiary text-2xs">no fills</div> :
                  Object.entries(d.attribution[k]).map(([n, v]: any) => <KV key={n} k={n} v={`${v.pnl != null ? `P&L ${num(v.pnl)} · ` : ''}realised ${num(v.realised)} · costs ${num(v.costs)} · ${v.fills ?? 0} fills${v.unrealised_change != null ? ` · Δunrealised ${num(v.unrealised_change)}` : v.unrealised_now != null ? ` · unrealised ${num(v.unrealised_now)}` : ''}`} />)}
              </div>))}
            <div className="text-[10px] text-text-tertiary">by regime</div>
            {Object.entries(d.attribution.by_regime).map(([n, v]: any) => <KV key={n} k={n} v={`${v.days}d · ${v.return_pct}%`} />)}
            <div className="text-[10px] text-text-tertiary mt-1">{d.attribution.note}</div>
          </Box>
          <Box title="Implementation · research changes · validation">
            <KV k="Fills · median signal-to-fill" v={`${d.implementation.fills} · ${d.implementation.signal_to_fill_hours_median ?? '—'} h`} />
            <KV k="Avg slippage · rejected · not filled" v={`${d.implementation.slippage_bps_avg ?? '—'} bp · ${d.implementation.rejected_orders} · ${d.implementation.not_filled}`} />
            <KV k="Model changes" v={d.research_changes.length} />
            {d.research_changes.slice(0, 8).map((e: any, i: number) => <div key={i} className="text-[10px] text-text-secondary">{e.ts.slice(0, 10)} {e.model} {e.action} {e.gate ?? ''} ({e.by})</div>)}
            <KV k="Reconciliations · clean · breaks" v={`${d.validation.reconciliations} · ${d.validation.clean} · ${d.validation.breaks}`} />
            <div className="text-[10px] text-text-tertiary mt-1">{d.validation.conventions}</div>
          </Box>
        </div>)}
    </div>
  );
}

// ── budget, roadmap, break-even ──────────────────────────────────────────────
function Budget() {
  const can = useCan();
  const { d, err, load, setErr } = useLoad<any>('/api/v1/governance/budget');
  const [f, setF] = useState({ date: new Date().toISOString().slice(0, 10), category: '', amount: '', currency: 'GBP', description: '' });
  const act = async (fn: () => Promise<any>) => { try { await fn(); load(); } catch (e: any) { setErr(e.message); } };
  if (!d) return <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div>;
  return (
    <div className="space-y-2 text-xs">
      {err && <div className="text-amber text-2xs">{err}</div>}
      <table className="w-full"><thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle"><th className="text-left font-normal py-1">Category</th><th className="text-right font-normal">Budget</th><th className="text-right font-normal">Spent</th><th className="text-right font-normal">Remaining</th><th className="text-left font-normal pl-2">Outcome</th></tr></thead>
        <tbody>{d.lines.map((l: any) => (
          <tr key={l.id} className="border-b border-border-subtle"><td className="py-1">{l.category}</td><td className="text-right font-mono">{num(l.amount)} {l.currency}</td><td className="text-right font-mono">{num(l.spent)}</td>
            <td className={cn('text-right font-mono', l.remaining < 0 ? 'text-red' : '')}>{num(l.remaining)}</td><td className="pl-2 text-text-tertiary">{l.outcome}</td></tr>))}
          <tr className="font-medium"><td className="py-1">Total</td><td className="text-right font-mono">{num(d.total_budget)}</td><td className="text-right font-mono">{num(d.total_spent)}</td><td className="text-right font-mono">{num(d.variance)}</td><td /></tr>
        </tbody></table>
      <Box title="Record an expense (approved by another person — spending authority)">
        <div className="flex flex-wrap gap-1">
          <input type="date" className={inputCls} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
          <select className={inputCls} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}><option value="">category…</option>{d.lines.map((l: any) => <option key={l.id}>{l.category}</option>)}</select>
          <input className={cn(inputCls, 'w-24')} placeholder="amount" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} />
          <input className={cn(inputCls, 'flex-1')} placeholder="description" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          <button className={btn} onClick={() => act(() => call('/api/v1/governance/budget/expenses', 'POST', { ...f, amount: Number(f.amount) }))}>Add</button>
        </div>
      </Box>
      {d.expenses.map((e: any) => (
        <div key={e.id} className="text-2xs border-b border-border-subtle py-0.5 flex gap-2"><span className="font-mono">{e.date}</span><span>{e.category}</span><span className="font-mono">{num(e.amount)} {e.currency}</span><span className="flex-1 text-text-secondary">{e.description} · {e.recorded_by}</span>
          {e.approved_by ? <span className="text-green">approved ({e.approved_by})</span> : <button disabled={!can('budget_approve')} title={can('budget_approve') ? undefined : NO} className={btn} onClick={() => act(() => call(`/api/v1/governance/budget/expenses/${e.id}/approve`, 'POST'))}>Approve</button>}</div>))}
    </div>
  );
}

function Roadmap() {
  const can = useCan();
  const { dialog, say } = useSay();
  const { d, err, load, setErr } = useLoad<any>('/api/v1/governance/milestones');
  const act = async (fn: () => Promise<any>) => { try { await fn(); load(); } catch (e: any) { setErr(e.message); } };
  if (!d) return <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div>;
  const plans = Array.from(new Set(d.milestones.map((m: any) => m.plan))) as string[];
  return (
    <div className="space-y-2 text-xs">
      {dialog}
      {err && <div className="text-amber text-2xs">{err}</div>}
      {plans.map((p) => (
        <Box key={p} title={p}>
          {d.milestones.filter((m: any) => m.plan === p).map((m: any) => (
            <div key={m.id} className="border-b border-border-subtle last:border-0 py-1 text-2xs grid grid-cols-12 gap-2 items-start">
              <span className="col-span-1 font-mono">{m.period}</span>
              <span className="col-span-5">{m.output}<div className="text-text-tertiary">Owner: {m.owner} · Accept: {m.acceptance}</div>{m.evidence && <div className="text-text-secondary">Evidence: {m.evidence}</div>}</span>
              <span className={cn('col-span-2', m.status === 'done' ? 'text-green' : m.status === 'blocked' ? 'text-red' : m.status === 'in_progress' ? 'text-bloomberg' : 'text-text-tertiary')}>{m.status}{m.signed_off_by ? ` ✓ ${m.signed_off_by}` : ''}</span>
              <span className="col-span-4 flex gap-1 flex-wrap justify-end">
                {(['in_progress', 'blocked'] as const).map((s) => <button key={s} className={btn} onClick={() => act(() => call(`/api/v1/governance/milestones/${m.id}`, 'PUT', { status: s }))}>{s.replace('_', ' ')}</button>)}
                <button className={btn} onClick={async () => { const ev = await say('Evidence that meets the acceptance criterion:'); if (ev) act(() => call(`/api/v1/governance/milestones/${m.id}`, 'PUT', { status: 'done', evidence: ev })); }}>done</button>
                {m.status === 'done' && !m.signed_off_by && <button disabled={!can('milestones_signoff')} title={can('milestones_signoff') ? undefined : NO} className={btn} onClick={() => act(() => call(`/api/v1/governance/milestones/${m.id}/signoff`, 'POST'))}>sign off</button>}
              </span>
            </div>))}
        </Box>))}
    </div>
  );
}

function Licences() {
  const can = useCan();
  const { d, err, load, setErr } = useLoad<any>('/api/v1/governance/data-sources');
  const [edit, setEdit] = useState<any>(null);
  if (!d) return <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div>;
  const save = async () => { try { await call('/api/v1/governance/data-sources/review', 'POST', edit); setEdit(null); load(); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="space-y-2 text-xs">
      <div className="text-[10px] text-amber">{d.note}</div>
      {err && <div className="text-amber text-2xs">{err}</div>}
      <table className="w-full"><thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle"><th className="text-left font-normal py-1">Source</th><th className="text-left font-normal">Type</th><th className="text-left font-normal">Feeds</th><th className="text-left font-normal">Fund use</th><th /></tr></thead>
        <tbody>{d.sources.map((r: any) => (
          <tr key={r.name} className="border-b border-border-subtle align-top">
            <td className="py-1"><a className="hover:text-bloomberg" href={r.url} target="_blank" rel="noreferrer">{r.name}</a><div className="text-[10px] text-text-tertiary">{r.provider}</div></td>
            <td className="text-text-secondary" title={r.type_note}>{r.type.replace('_', ' ')}</td>
            <td className="text-text-secondary">{r.feeds}</td>
            <td className={cn(r.status === 'allowed' ? 'text-green' : r.status === 'unreviewed' ? 'text-amber' : 'text-red')}>{r.status.replace('_', ' ')}
              {r.terms_reference && <div className="text-[10px] text-text-tertiary">{r.terms_reference} · {r.reviewed_by} {String(r.reviewed_at ?? '').slice(0, 10)}</div>}
              {r.note && <div className="text-[10px] text-text-tertiary">{r.note}</div>}</td>
            <td className="text-right"><button disabled={!can('data_licences_review')} title={can('data_licences_review') ? undefined : NO} className={btn} onClick={() => setEdit({ name: r.name, status: r.status === 'unreviewed' ? 'allowed' : r.status, terms_reference: r.terms_reference ?? '', note: r.note ?? '' })}>Review</button></td>
          </tr>))}</tbody></table>
      {edit && (
        <Box title={`Review: ${edit.name}`}>
          <div className="flex flex-wrap gap-1">
            <select className={inputCls} value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })}>
              {['allowed', 'restricted', 'not_allowed', 'unreviewed'].map((x) => <option key={x} value={x}>{x.replace('_', ' ')}</option>)}</select>
            <input className={cn(inputCls, 'flex-1')} placeholder="terms reviewed (URL / document and date)" value={edit.terms_reference} onChange={(e) => setEdit({ ...edit, terms_reference: e.target.value })} />
            <input className={cn(inputCls, 'flex-1')} placeholder="conditions / note" value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} />
            <button className={btn} onClick={save}>Save</button><button className={btn} onClick={() => setEdit(null)}>Cancel</button>
          </div>
        </Box>)}
      <div className="text-[10px] text-text-tertiary">{Object.entries(d.types).map(([k, v]) => `${k.replace('_', ' ')}: ${v}`).join(' ')}</div>
    </div>
  );
}

function BreakEven() {
  const [cost, setCost] = useState('175000,250000,350000,500000');
  const [fees, setFees] = useState('0.01,0.015,0.02');
  const { d, err } = useLoad<any>(`/api/v1/governance/break-even?costs=${encodeURIComponent(cost)}&fees=${encodeURIComponent(fees)}`);
  return (
    <div className="space-y-2 text-xs">
      <div className="flex gap-1 flex-wrap"><input className={cn(inputCls, 'w-72')} value={cost} onChange={(e) => setCost(e.target.value)} title="annual operating cash costs (US$)" />
        <input className={cn(inputCls, 'w-48')} value={fees} onChange={(e) => setFees(e.target.value)} title="management-fee rates" /></div>
      {!d ? <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div> : (<>
        <table className="w-full"><thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle"><th className="text-left font-normal py-1">Annual cost</th>
          {Object.keys(d.thresholds[0]).filter((k) => k !== 'cost').map((k) => <th key={k} className="text-right font-normal">at {k} fee</th>)}</tr></thead>
          <tbody>{d.thresholds.map((r: any) => (
            <tr key={r.cost} className="border-b border-border-subtle"><td className="py-1 font-mono">${num(r.cost, 0)}</td>
              {Object.entries(r).filter(([k]) => k !== 'cost').map(([k, v]: any) => <td key={k} className="text-right font-mono">${num(v / 1e6, 1)}m</td>)}</tr>))}</tbody></table>
        <div className="text-[10px] text-text-tertiary">{d.formula}. {d.note}</div>
      </>)}
    </div>
  );
}

type Tab = 'overview' | 'team' | 'broker' | 'models' | 'instruments' | 'controls' | 'monthly' | 'budget' | 'roadmap' | 'licences' | 'breakeven';
const TABS: [Tab, string][] = [['overview', 'Overview'], ['team', 'Team & positions'], ['broker', 'Broker (IBKR)'], ['models', 'Models G0–G5'], ['instruments', 'Approved instruments'], ['controls', 'Controls'],
  ['monthly', 'Monthly pack'], ['budget', 'Budget'], ['roadmap', 'Roadmap'], ['licences', 'Data licences'], ['breakeven', 'Break-even AUM']];

export function GovernanceSection() {
  const { d: g, err, load } = useLoad<any>('/api/v1/governance');
  const me = useLoad<any>('/api/v1/positions/me');
  const [tab, setTab] = useState<Tab>('overview');
  return (
    <CapsCtx.Provider value={me.d?.capabilities ?? null}>
    <div className="border border-border bg-surface-1">
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 flex-wrap">
        <BrandShape variant="mark_mask" height={16} className="text-bloomberg" />
        <span className="text-xs font-medium text-text-primary uppercase tracking-wider">Fund Governance</span>
        {g && <span className="text-2xs text-text-tertiary">{g.settings.fund_name} · {g.settings.stage_label}</span>}
        {me.d?.position && <span className="text-[10px] px-1.5 border border-bloomberg/40 text-bloomberg">{me.d.position.title} · Tier {me.d.position.tier}</span>}
        <div className="flex gap-1 flex-wrap ml-auto">
          {TABS.map(([k, l]) => <button key={k} onClick={() => setTab(k)} className={cn('text-2xs px-2 py-0.5 border', tab === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-tertiary hover:text-text-primary')}>{l}</button>)}
        </div>
      </div>
      <div className="p-3">
        {!g ? <div className="text-2xs text-text-tertiary">{err ?? 'Loading…'}</div> : <>
          {tab === 'overview' && <Overview g={g} reload={load} />}
          {tab === 'team' && <TeamPositions />}
          {tab === 'broker' && <BrokerLink />}
          {tab === 'models' && <Models g={g} />}
          {tab === 'instruments' && <Instruments />}
          {tab === 'controls' && <Controls reload={load} />}
          {tab === 'monthly' && <Monthly />}
          {tab === 'budget' && <Budget />}
          {tab === 'roadmap' && <Roadmap />}
          {tab === 'licences' && <Licences />}
          {tab === 'breakeven' && <BreakEven />}
        </>}
      </div>
    </div>
    </CapsCtx.Provider>
  );
}

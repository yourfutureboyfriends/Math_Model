// Strategy builder: universe, signal/filter formulas (validated as you type, with a
// clickable function palette), selection, weighting, risk, rebalancing and costs.
import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api, BLANK_SPEC, Field, inputCls, type Spec } from './shared';

export interface Meta {
  functions: { functions: Record<string, { name: string; sig: string; desc: string }[]>; variables: { name: string; desc: string }[]; operators: string };
  universes: { id: string; label: string; symbols: string[]; note: string; survivorship: boolean }[];
  templates: any[];
  research: { title: string; text: string }[];
}

const MODES: [string, string, string][] = [
  ['top_n', 'Top N', 'Hold the N assets with the highest signal.'],
  ['top_pct', 'Top %', 'Hold the top fraction of the universe by signal.'],
  ['threshold', 'Above threshold', 'Hold every asset whose signal is above the minimum score (default 0).'],
  ['sign', 'Long / short by sign', 'Long when the signal is positive, short when negative (time-series momentum).'],
  ['long_short', 'Long top, short bottom', 'Long the N best, short the N worst — market-neutral.'],
];
const WEIGHTS: [string, string, string][] = [
  ['equal', 'Equal', 'Same weight in each holding.'],
  ['inverse_vol', 'Inverse volatility', 'Calmer assets get more weight so each contributes similar risk.'],
  ['signal', 'By signal strength', 'Weight proportional to the signal.'],
  ['equal_universe', 'Fixed slots (1/N of universe)', 'Each asset has a fixed 1/N slot; unselected slots stay in cash (Faber-style).'],
];

function useValidate(formula: string, optional: boolean) {
  const [state, setState] = useState<{ ok: boolean; error?: string } | null>(null);
  useEffect(() => {
    if (!formula.trim()) { setState(optional ? null : { ok: false, error: 'Required' }); return; }
    const t = setTimeout(() => {
      api('/api/v1/quant/validate', { json: { formula } }).then(setState).catch(() => setState(null));
    }, 350);
    return () => clearTimeout(t);
  }, [formula, optional]);
  return state;
}

function FormulaBox({ label, value, onChange, optional, hint, onFocus, inputRef }: {
  label: string; value: string; onChange: (v: string) => void; optional?: boolean; hint: string;
  onFocus: () => void; inputRef: React.RefObject<HTMLTextAreaElement>;
}) {
  const v = useValidate(value, !!optional);
  return (
    <Field label={label} hint={hint}>
      <textarea ref={inputRef} value={value} onChange={(e) => onChange(e.target.value)} onFocus={onFocus} rows={2} spellCheck={false}
        className={cn(inputCls, 'resize-y', v && !v.ok && 'border-red/60')} placeholder={optional ? 'optional, e.g. mkt > sma(mkt, 200)' : 'e.g. rank(mom(252, 21))'} />
      {v && (
        <span className={cn('flex items-center gap-1 mt-0.5 text-[10px]', v.ok ? 'text-green' : 'text-red')}>
          {v.ok ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}{v.ok ? 'Valid formula' : v.error}
        </span>
      )}
    </Field>
  );
}

export function StrategyBuilder({ spec, setSpec, meta }: { spec: Spec; setSpec: (s: Spec) => void; meta: Meta }) {
  const sigRef = useRef<HTMLTextAreaElement>(null);
  const filtRef = useRef<HTMLTextAreaElement>(null);
  const [target, setTarget] = useState<'signal' | 'filter'>('signal');
  const [palette, setPalette] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const custom = !spec.universe.preset || spec.universe.preset === 'custom';
  const uni = meta.universes.find((u) => u.id === spec.universe.preset);
  const set = (patch: Partial<Spec>) => setSpec({ ...spec, ...patch });
  const sel = spec.selection;

  const insert = (text: string) => {
    const ref = target === 'signal' ? sigRef : filtRef;
    const el = ref.current;
    const cur = (target === 'signal' ? spec.signal : spec.filter) ?? '';
    const at = el ? el.selectionStart ?? cur.length : cur.length;
    const end = el ? el.selectionEnd ?? at : at;
    const next = cur.slice(0, at) + text + cur.slice(end);
    set(target === 'signal' ? { signal: next } : { filter: next });
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + text.length, at + text.length); });
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <Field label="Strategy name">
          <input className={inputCls} value={spec.name} maxLength={80} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label="Universe" hint="The assets the strategy can choose from.">
          <select className={inputCls} value={custom ? 'custom' : spec.universe.preset}
            onChange={(e) => set({ universe: e.target.value === 'custom' ? { preset: 'custom', symbols: uni?.symbols ?? ['SPY', 'TLT', 'GLD'] } : { preset: e.target.value } })}>
            {meta.universes.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
            <option value="custom">Custom tickers…</option>
          </select>
        </Field>
      </div>
      {custom ? (
        <Field label="Tickers (comma or space separated, up to 80)" hint="Any Yahoo Finance symbol, e.g. SPY QQQ TLT GLD 7203.T">
          <input className={inputCls} value={(spec.universe.symbols ?? []).join(', ')}
            onChange={(e) => set({ universe: { preset: 'custom', symbols: e.target.value.split(/[\s,]+/).map((s) => s.trim().toUpperCase()).filter(Boolean) } })} />
        </Field>
      ) : uni && (
        <div className="text-[10px] text-text-tertiary leading-relaxed">
          {uni.symbols.join(' · ')}{uni.note && <> — {uni.note}</>}
          {uni.survivorship && <span className="text-amber"> Survivorship-biased.</span>}
        </div>
      )}

      <FormulaBox label="Signal — higher = more attractive" value={spec.signal} onChange={(v) => set({ signal: v })} inputRef={sigRef}
        onFocus={() => setTarget('signal')} hint="A formula computed for every asset every day from data up to that day. The selection rules below act on it." />
      <FormulaBox label="Filter — only trade assets where this is true" value={spec.filter ?? ''} optional onChange={(v) => set({ filter: v })}
        inputRef={filtRef} onFocus={() => setTarget('filter')} hint="Optional gate, e.g. a trend filter close > sma(close, 200) or a market filter mkt > sma(mkt, 200)." />

      <div className="border border-border">
        <button type="button" onClick={() => setPalette((p) => !p)} className="w-full flex items-center gap-1 px-2 py-1 text-2xs text-text-secondary hover:text-text-primary">
          {palette ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          Formula functions — click to insert into the {target}
        </button>
        {palette && (
          <div className="px-2 pb-2 space-y-2 max-h-72 overflow-y-auto">
            {Object.entries(meta.functions.functions).map(([cat, fns]) => (
              <div key={cat}>
                <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">{cat}</div>
                <div className="flex flex-wrap gap-1">
                  {fns.map((f) => (
                    <button key={f.name} type="button" title={f.desc} onClick={() => insert(f.sig.replace(/=\d+/g, ''))}
                      className="px-1.5 py-0.5 border border-border text-[11px] font-mono text-text-secondary hover:border-bloomberg hover:text-text-primary">{f.sig}</button>
                  ))}
                </div>
              </div>
            ))}
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-1">Data</div>
              <div className="flex flex-wrap gap-1">
                {meta.functions.variables.map((v) => (
                  <button key={v.name} type="button" title={v.desc} onClick={() => insert(v.name)}
                    className="px-1.5 py-0.5 border border-border text-[11px] font-mono text-text-secondary hover:border-bloomberg hover:text-text-primary">{v.name}</button>
                ))}
              </div>
            </div>
            <div className="text-[10px] text-text-tertiary">Operators: {meta.functions.operators}</div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <Field label="Selection" hint={MODES.find((m) => m[0] === sel.mode)?.[2]}>
          <select className={inputCls} value={sel.mode} onChange={(e) => set({ selection: { ...sel, mode: e.target.value, long_only: e.target.value === 'sign' ? sel.long_only : e.target.value !== 'long_short' } })}>
            {MODES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
        <Field label="Weighting" hint={WEIGHTS.find((w) => w[0] === spec.weighting)?.[2]}>
          <select className={inputCls} value={spec.weighting} onChange={(e) => set({ weighting: e.target.value })}>
            {WEIGHTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </Field>
        {(sel.mode === 'top_n' || sel.mode === 'long_short') && (
          <Field label={sel.mode === 'long_short' ? 'Holdings per side' : 'Number of holdings'}>
            <input type="number" min={1} max={200} className={inputCls} value={sel.n ?? 3}
              onChange={(e) => set({ selection: { ...sel, n: e.target.value === '' ? '' : Number(e.target.value) } })} />
          </Field>
        )}
        {sel.mode === 'top_pct' && (
          <Field label="Top % of universe">
            <input type="number" min={1} max={100} className={inputCls} value={Math.round((sel.pct ?? 0.2) * 100)}
              onChange={(e) => set({ selection: { ...sel, pct: Number(e.target.value) / 100 } })} />
          </Field>
        )}
        {(sel.mode === 'top_n' || sel.mode === 'top_pct' || sel.mode === 'threshold') && (
          <Field label="Minimum signal (optional)" hint="Assets must also score above this — e.g. 0 with a momentum signal = absolute momentum.">
            <input type="number" step="any" className={inputCls} value={sel.min_score ?? ''}
              onChange={(e) => set({ selection: { ...sel, min_score: e.target.value === '' ? null : Number(e.target.value) } })} />
          </Field>
        )}
        {sel.mode === 'sign' && (
          <label className="flex items-center gap-2 text-2xs text-text-secondary mt-4">
            <input type="checkbox" checked={!!sel.long_only} onChange={(e) => set({ selection: { ...sel, long_only: e.target.checked } })} />
            Long only (cash instead of shorts)
          </label>
        )}
        <Field label="Rebalance">
          <select className={inputCls} value={spec.rebalance} onChange={(e) => set({ rebalance: e.target.value })}>
            <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option>
          </select>
        </Field>
        <Field label="Cost per trade (bp of traded value)" hint="Commission + spread + slippage, per side. ETFs ~2–5 bp, large caps ~5–10 bp, small/EM 20+ bp.">
          <input type="number" min={0} max={200} step="0.5" className={inputCls} value={spec.costs?.bps ?? 5}
            onChange={(e) => set({ costs: { ...spec.costs, bps: Number(e.target.value) } })} />
        </Field>
      </div>

      <button type="button" onClick={() => setAdvanced((a) => !a)} className="flex items-center gap-1 text-2xs text-text-secondary hover:text-text-primary">
        {advanced ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}Risk, execution &amp; dates
      </button>
      {advanced && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <Field label="Volatility target %" hint="Scale the whole book to this annual volatility (blank = off). Stabilises risk; its Sharpe benefit is not guaranteed.">
            <input type="number" min={1} max={50} className={inputCls} value={spec.risk?.vol_target != null ? Math.round(spec.risk.vol_target * 100) : ''}
              onChange={(e) => set({ risk: { ...spec.risk, vol_target: e.target.value === '' ? null : Number(e.target.value) / 100 } })} />
          </Field>
          <Field label="Max weight per asset %">
            <input type="number" min={1} max={100} className={inputCls} value={Math.round((spec.risk?.max_weight ?? 1) * 100)}
              onChange={(e) => set({ risk: { ...spec.risk, max_weight: Number(e.target.value) / 100 } })} />
          </Field>
          <Field label="Max gross exposure (×)" hint="1 = no leverage. Long/short books need > 1 to hold both sides at full size.">
            <input type="number" min={0.1} max={4} step="0.1" className={inputCls} value={spec.risk?.max_gross ?? 1}
              onChange={(e) => set({ risk: { ...spec.risk, max_gross: Number(e.target.value) } })} />
          </Field>
          <Field label="Execution" hint="Orders are decided at the close and filled at the next session's open (or close).">
            <select className={inputCls} value={spec.execution ?? 'next_open'} onChange={(e) => set({ execution: e.target.value })}>
              <option value="next_open">Next open</option><option value="next_close">Next close</option>
            </select>
          </Field>
          <Field label="Short borrow (bp / year)">
            <input type="number" min={0} max={2000} className={inputCls} value={spec.costs?.borrow_bps ?? BLANK_SPEC.costs?.borrow_bps}
              onChange={(e) => set({ costs: { ...spec.costs, borrow_bps: Number(e.target.value) } })} />
          </Field>
          <Field label="Fallback when nothing qualifies" hint="Held when no asset is selected, e.g. IEF (bonds) or BIL (T-bills). Blank = cash.">
            <input className={inputCls} value={spec.fallback ?? ''} onChange={(e) => set({ fallback: e.target.value.toUpperCase() })} placeholder="e.g. IEF" />
          </Field>
          <Field label="Benchmark">
            <input className={inputCls} value={spec.benchmark ?? 'SPY'} onChange={(e) => set({ benchmark: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="Start date">
            <input type="date" className={inputCls} value={spec.start ?? '2005-01-01'} onChange={(e) => set({ start: e.target.value })} />
          </Field>
          <Field label="End date (blank = today)">
            <input type="date" className={inputCls} value={spec.end ?? ''} onChange={(e) => set({ end: e.target.value || null })} />
          </Field>
        </div>
      )}
    </div>
  );
}

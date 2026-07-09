/**
 * TradeWorkflowSection — Phase 6 trade-idea workflow + what-if pre-trade analysis.
 *
 * Left: a what-if calculator that shows how a proposed trade moves portfolio VaR,
 * exposure and concentration, plus a VaR-budgeted suggested size. Right: a trade-idea
 * board with lifecycle (Proposed -> Under Review -> Approved -> Executed -> Closed),
 * each transition timestamped. Reads /api/v1/portfolio/what-if and /trade-ideas.
 */
import { useCallback, useEffect, useState } from 'react';
import { FlaskConical, ClipboardList, ChevronRight, Trash2, Plus } from 'lucide-react';

const usd = (v: number | null | undefined) =>
  v == null ? '—' : `${v < 0 ? '-' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const delta = (v: number | null | undefined) =>
  v == null ? '—' : `${v >= 0 ? '+' : ''}${usd(v).replace('$', '$')}`;

const CONV_TONE: Record<string, string> = { HIGH: 'text-green', MEDIUM: 'text-amber', LOW: 'text-text-tertiary' };

export function TradeWorkflowSection() {
  // What-if
  const [wf, setWf] = useState({ symbol: '', quantity: '', var_limit: '2000' });
  const [wfResult, setWfResult] = useState<any>(null);
  const [wfBusy, setWfBusy] = useState(false);

  const runWhatIf = async () => {
    if (!wf.symbol || !wf.quantity) return;
    setWfBusy(true);
    try {
      const r = await fetch('/api/v1/portfolio/what-if', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: wf.symbol, quantity: Number(wf.quantity), var_limit: Number(wf.var_limit) || undefined }),
      });
      setWfResult(await r.json());
    } finally { setWfBusy(false); }
  };

  // Trade ideas
  const [ideas, setIdeas] = useState<any[]>([]);
  const [states, setStates] = useState<string[]>([]);
  const [form, setForm] = useState({ symbol: '', direction: 'LONG', conviction: 'HIGH', thesis: '' });

  const loadIdeas = useCallback(async () => {
    const r = await fetch('/api/v1/portfolio/trade-ideas');
    if (r.ok) { const d = await r.json(); setIdeas(d.ideas || []); setStates(d.states || []); }
  }, []);
  useEffect(() => { loadIdeas(); }, [loadIdeas]);

  const addIdea = async () => {
    if (!form.symbol) return;
    await fetch('/api/v1/portfolio/trade-ideas', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, symbol: form.symbol.toUpperCase() }),
    });
    setForm({ symbol: '', direction: 'LONG', conviction: 'HIGH', thesis: '' });
    loadIdeas();
  };
  const nextState = (s: string) => { const i = states.indexOf(s); return i >= 0 && i < states.length - 1 ? states[i + 1] : null; };
  const advance = async (id: number, to: string) => {
    await fetch(`/api/v1/portfolio/trade-ideas/${id}/transition`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ state: to }),
    });
    loadIdeas();
  };
  const removeIdea = async (id: number) => { await fetch(`/api/v1/portfolio/trade-ideas/${id}`, { method: 'DELETE' }); loadIdeas(); };

  const d = wfResult?.available ? wfResult.delta : null;

  return (
    <div id="trade-workflow" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><FlaskConical className="w-3 h-3" /></span>
          <h2 className="section-title">Trade Workflow &amp; What-If</h2>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* What-if */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Pre-Trade What-If</div>
          <div className="flex flex-wrap items-end gap-2 mb-2">
            <div className="w-24"><label className="text-2xs text-text-tertiary">Symbol</label>
              <input value={wf.symbol} onChange={(e) => setWf({ ...wf, symbol: e.target.value.toUpperCase() })} placeholder="NVDA"
                className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm font-mono text-text-primary" /></div>
            <div className="w-24"><label className="text-2xs text-text-tertiary">Quantity</label>
              <input value={wf.quantity} onChange={(e) => setWf({ ...wf, quantity: e.target.value })} placeholder="200"
                className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm font-mono text-text-primary" /></div>
            <div className="w-28"><label className="text-2xs text-text-tertiary">VaR Budget $</label>
              <input value={wf.var_limit} onChange={(e) => setWf({ ...wf, var_limit: e.target.value })}
                className="w-full bg-surface-2 border border-border-subtle px-2 py-1 text-sm font-mono text-text-primary" /></div>
            <button onClick={runWhatIf} disabled={wfBusy}
              className="px-3 py-1 border border-bloomberg-border bg-bloomberg-muted text-bloomberg text-xs hover:bg-bloomberg/20">
              {wfBusy ? 'Running…' : 'Run'}
            </button>
          </div>
          {wfResult && !wfResult.available && <div className="text-2xs text-red">{wfResult.reason}</div>}
          {wfResult?.available && (
            <div className="space-y-2">
              <div className="text-xs text-text-secondary">
                {wfResult.proposed.symbol} × {wfResult.proposed.quantity} @ {usd(wfResult.proposed.price)} = <span className="font-mono">{usd(wfResult.proposed.notional)}</span>
              </div>
              <table className="w-full text-xs">
                <thead><tr className="text-2xs text-text-tertiary uppercase">
                  <th className="text-left py-1">Metric</th><th className="text-right py-1">Before</th><th className="text-right py-1">After</th><th className="text-right py-1">Δ</th>
                </tr></thead>
                <tbody className="font-mono">
                  <tr><td className="py-1 text-text-secondary">VaR 95% 1d</td>
                    <td className="text-right">{usd(wfResult.before.var_95_1d)}</td>
                    <td className="text-right">{usd(wfResult.after.var_95_1d)}</td>
                    <td className={`text-right ${(d.var_95_1d ?? 0) > 0 ? 'text-red' : 'text-green'}`}>{delta(d.var_95_1d)}</td></tr>
                  <tr><td className="py-1 text-text-secondary">Gross Exp.</td>
                    <td className="text-right">{usd(wfResult.before.summary?.gross_exposure)}</td>
                    <td className="text-right">{usd(wfResult.after.summary?.gross_exposure)}</td>
                    <td className="text-right text-text-primary">{delta(d.gross_exposure)}</td></tr>
                  <tr><td className="py-1 text-text-secondary">Net Exp.</td>
                    <td className="text-right">{usd(wfResult.before.summary?.net_exposure)}</td>
                    <td className="text-right">{usd(wfResult.after.summary?.net_exposure)}</td>
                    <td className="text-right text-text-primary">{delta(d.net_exposure)}</td></tr>
                </tbody>
              </table>
              {wfResult.sizing && (
                <div className="text-2xs text-text-tertiary pt-1 border-t border-border-subtle">
                  VaR-budget sizing: max notional <span className="font-mono text-text-secondary">{usd(wfResult.sizing.max_notional)}</span>
                  {' '}(≈ <span className="font-mono text-bloomberg">{wfResult.sizing.suggested_shares}</span> shares, daily vol {(wfResult.sizing.daily_vol * 100).toFixed(1)}%)
                </div>
              )}
            </div>
          )}
        </div>

        {/* Trade ideas board */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-1 text-2xs text-text-tertiary uppercase tracking-wider mb-2">
            <ClipboardList className="w-3 h-3" /> Trade Ideas
          </div>
          <div className="flex flex-wrap items-end gap-1 mb-2">
            <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} placeholder="Symbol"
              className="w-20 bg-surface-2 border border-border-subtle px-2 py-1 text-xs font-mono text-text-primary" />
            <select value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}
              className="bg-surface-2 border border-border-subtle px-1 py-1 text-xs text-text-primary">
              <option>LONG</option><option>SHORT</option></select>
            <select value={form.conviction} onChange={(e) => setForm({ ...form, conviction: e.target.value })}
              className="bg-surface-2 border border-border-subtle px-1 py-1 text-xs text-text-primary">
              <option>HIGH</option><option>MEDIUM</option><option>LOW</option></select>
            <input value={form.thesis} onChange={(e) => setForm({ ...form, thesis: e.target.value })} placeholder="Thesis"
              className="flex-1 min-w-[100px] bg-surface-2 border border-border-subtle px-2 py-1 text-xs text-text-primary" />
            <button onClick={addIdea} className="px-2 py-1 border border-green/40 bg-green-dim text-green text-xs flex items-center gap-1"><Plus className="w-3 h-3" /></button>
          </div>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {ideas.length === 0 && <div className="text-2xs text-text-tertiary py-2">No trade ideas yet.</div>}
            {ideas.map((i) => {
              const nxt = nextState(i.state);
              return (
                <div key={i.id} className="flex items-center gap-2 p-2 bg-surface-2 border border-border-subtle text-xs">
                  <span className={`font-mono ${i.direction === 'SHORT' ? 'text-red' : 'text-green'}`}>{i.direction}</span>
                  <span className="font-medium text-text-primary">{i.symbol}</span>
                  <span className={`text-2xs ${CONV_TONE[i.conviction] || 'text-text-tertiary'}`}>{i.conviction}</span>
                  <span className="flex-1 text-2xs text-text-tertiary truncate">{i.thesis}</span>
                  <span className="text-2xs px-1.5 py-0.5 bg-surface-3 border border-border-subtle text-text-secondary">{i.state}</span>
                  {nxt && (
                    <button onClick={() => advance(i.id, nxt)} title={`Advance to ${nxt}`}
                      className="flex items-center text-bloomberg hover:text-bloomberg-bright text-2xs">
                      {nxt} <ChevronRight className="w-3 h-3" />
                    </button>
                  )}
                  <button onClick={() => removeIdea(i.id)} className="text-text-tertiary hover:text-red"><Trash2 className="w-3 h-3" /></button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

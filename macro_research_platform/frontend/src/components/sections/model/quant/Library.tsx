/** Strategy library — institutional strategies as code, each walk-forward optimised net of costs,
 *  with Monte Carlo sizing. Reads /api/v1/quant/library. */
import { useEffect, useState } from 'react';
import { Code2, Loader2, Rocket, BarChart3 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api, ErrorNote, num, pct, spct, tone } from './shared';
import { CodeResults } from './CodeLab';

export function Library({ onOpenCode, canDeploy }: { onOpenCode: (code: string, name: string) => void; canDeploy: boolean }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [res, setRes] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = () => api('/api/v1/quant/library').then((j) => setRows(j.strategies)).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const show = async (id: string) => {
    if (open === id) { setOpen(null); return; }
    setOpen(id);
    if (res[id]) return;
    setBusy(id); setErr(null);
    try {
      const r = await api(`/api/v1/quant/library/${id}`);
      setRes((x) => ({ ...x, [id]: r }));
      load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const deploy = async (s: any) => {
    const cap = Number(window.prompt(`Paper capital to deploy “${s.name}” with (USD):`, '1000000'));
    if (!cap) return;
    setErr(null);
    try {
      const d = await api('/api/v1/quant/trader/deploy', { json: { spec: { kind: 'library', library: s.id, name: s.name }, capital: cap } });
      setNote(`Deployed “${d.name}” to the ${d.book} Quant Trader — live from the session after ${d.deployed_at}.`);
    } catch (e: any) { setErr(e.message); }
  };

  if (!rows) return err ? <ErrorNote msg={err} /> : <div className="flex items-center gap-2 text-2xs text-text-tertiary"><Loader2 className="w-3 h-3 animate-spin" />Loading the library…</div>;
  return (
    <div className="space-y-2">
      <div className="text-[11px] text-text-secondary leading-relaxed">
        Published constructions from AQR, Man AHL, Bridgewater, Robeco and landmark papers, written as editable code. Every record is
        <b> out-of-sample</b> (parameters from a small grid taken from each paper, re-chosen each January using only past data) and
        <b> net of commissions, spreads, market impact, fees, borrow and financing</b>. “Maximum money” is pursued as maximum long-run
        growth: the Monte Carlo sizes leverage to the growth-optimal level within a drawdown limit, capped at half-Kelly.
      </div>
      <ErrorNote msg={err} />
      {note && <div className="px-3 py-2 border border-green/40 bg-green/5 text-xs text-green">{note}</div>}
      {rows.map((s) => {
        const h = s.headline, m = h?.metrics;
        return (
          <div key={s.id} className={cn('border bg-surface-1', s.id === 'multi_strategy' ? 'border-bloomberg/60' : 'border-border')}>
            <div className="p-3 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_420px] gap-3">
              <div>
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-xs font-semibold text-text-primary">{s.name}</span>
                  <span className="text-[10px] px-1.5 border border-border text-text-tertiary">{s.family}</span>
                </div>
                <div className="text-[10px] text-text-tertiary mt-0.5">{s.source}</div>
                <div className="text-[11px] text-text-secondary mt-1">{s.summary}</div>
                <div className="text-[11px] text-text-tertiary mt-1">{s.evidence}</div>
              </div>
              <div className="space-y-2">
                {m ? (
                  <table className="w-full text-[11px] font-mono">
                    <tbody>
                      <tr><td className="text-text-tertiary">CAGR net</td><td className={cn('text-right', tone(m.cagr) === 'up' ? 'text-green' : 'text-red')}>{spct(m.cagr)}</td>
                        <td className="text-text-tertiary pl-3">Sharpe</td><td className="text-right">{num(m.sharpe)}</td></tr>
                      <tr><td className="text-text-tertiary">Max DD</td><td className="text-right">{pct(m.max_drawdown, 0)}</td>
                        <td className="text-text-tertiary pl-3">Costs/yr</td><td className="text-right">{h.costs ? pct(h.costs.total_trading, 2) : '—'}</td></tr>
                      <tr><td className="text-text-tertiary">Sized lev.</td><td className="text-right">{h.recommended_leverage != null ? `${h.recommended_leverage}×` : '—'}</td>
                        <td className="text-text-tertiary pl-3">From</td><td className="text-right">{h.oos_start ?? '—'}</td></tr>
                    </tbody>
                  </table>
                ) : <div className="text-[11px] text-text-tertiary">Not evaluated yet — open results to run it (≈10 s).</div>}
                <div className="flex flex-wrap gap-1">
                  <button onClick={() => show(s.id)} className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs bg-bloomberg text-bg">
                    {busy === s.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <BarChart3 className="w-3 h-3" />}{open === s.id ? 'Hide results' : 'Results & Monte Carlo'}</button>
                  {s.code && <button onClick={() => onOpenCode(s.code, s.name)} className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs border border-border hover:border-bloomberg"><Code2 className="w-3 h-3" />Open in editor</button>}
                  {canDeploy && <button onClick={() => deploy(s)} className="inline-flex items-center gap-1 px-2 py-0.5 text-2xs border border-border hover:border-bloomberg"><Rocket className="w-3 h-3" />Deploy</button>}
                </div>
              </div>
            </div>
            {open === s.id && res[s.id] && (
              <div className="border-t border-border p-3">
                <CodeResults r={{ ...res[s.id], benchmark_label: 'SPY' }} a={{ deep: res[s.id].deep, monte_carlo: res[s.id].monte_carlo }} />
                <div className="text-[10px] text-text-tertiary mt-2">Evaluated {res[s.id].evaluated_at}; refreshed daily.</div>
              </div>)}
          </div>
        );
      })}
    </div>
  );
}

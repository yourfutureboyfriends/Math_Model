/**
 * Macro Event Dataset — point-in-time US releases (CPI, core CPI, payrolls, unemployment; ALFRED vintages) and FOMC
 * decisions, each with a labelled surprise proxy and the reaction of FX, equity, rates, gold and commodity proxies
 * from the first close after the release. Versioned by hash; summaries are descriptive and in-sample.
 * Backend: /api/v1/research/events (api/event_dataset.py).
 */
import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const f = (v: number | null | undefined, d = 2) => (v == null ? '—' : v.toFixed(d));
const sel = 'bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary outline-none';

export function EventDatasetSection() {
  const [event, setEvent] = useState('us_cpi');
  const [horizon, setHorizon] = useState('h0');
  const [d, setD] = useState<any>(null);
  const [s, setS] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    setErr(null);
    fetch(`/api/v1/research/events?event=${event}&limit=24`).then((r) => r.json()).then(setD).catch((e) => setErr(String(e)));
    fetch(`/api/v1/research/events/summary?event=${event}&horizon=${horizon}`).then((r) => r.json()).then(setS).catch((e) => setErr(String(e)));
  }, [event, horizon, nonce]);
  const rebuild = async () => {
    setBusy(true);
    try { const r = await fetch('/api/v1/research/events/rebuild', { method: 'POST' }); if (!r.ok) throw new Error(`HTTP ${r.status}`); setD(null); setS(null); setNonce((n) => n + 1); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const assets: string[] = d ? Object.keys(d.assets) : [];
  const show = ['USDJPY=X', 'EURUSD=X', 'CSPX.L', 'IDTL.L', 'SGLN.L', 'DGS2'];
  return (
    <div className="border border-border bg-surface-1">
      <div className="px-3 py-2 border-b border-border flex items-center gap-2 flex-wrap">
        <span className="text-xs font-medium text-text-primary uppercase tracking-wider">Macro Event Dataset</span>
        <span className="text-2xs text-text-tertiary">point-in-time releases · surprise proxies · cross-asset reactions</span>
        <div className="ml-auto flex gap-1 items-center">
          <select className={sel} value={event} onChange={(e) => setEvent(e.target.value)}>
            {Object.entries(d?.event_types ?? { us_cpi: 'US CPI' }).map(([k, v]) => <option key={k} value={k}>{v as string}</option>)}</select>
          <select className={sel} value={horizon} onChange={(e) => setHorizon(e.target.value)}><option value="h0">first close after</option><option value="h5">+5 sessions</option></select>
          <a className="text-2xs px-2 py-1 border border-border hover:border-bloomberg" href={`/api/v1/research/events.csv?event=${event}`} target="_blank" rel="noreferrer">CSV</a>
          <button className="text-2xs px-2 py-1 border border-border hover:border-bloomberg" disabled={busy} onClick={rebuild}>{busy ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Rebuild'}</button>
        </div>
      </div>
      <div className="p-3 space-y-3 text-xs">
        {err && <div className="text-amber text-2xs">{err}</div>}
        {!d || !s ? <div className="text-2xs text-text-tertiary flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin" />Building the dataset (first time ≈ 20 s)…</div> : (<>
          <div>
            <div className="text-2xs text-text-tertiary uppercase mb-1">Reaction per 1 s.d. surprise — {s.events} events ({horizon === 'h0' ? 'first close after the release' : 'five sessions later'})</div>
            <table className="w-full"><thead><tr className="text-2xs text-text-tertiary border-b border-border-subtle"><th className="text-left font-normal py-1">Asset</th><th className="text-right font-normal">n</th><th className="text-right font-normal">β per 1σ</th><th className="text-right font-normal">t</th><th className="text-right font-normal">corr</th></tr></thead>
              <tbody>{Object.entries(s.by_asset).map(([a, v]: any) => (
                <tr key={a} className="border-b border-border-subtle">
                  <td className="py-0.5 font-mono">{a}</td><td className="text-right font-mono">{v.n}</td>
                  {v.mechanical ? <td colSpan={3} className="text-right text-text-tertiary">{v.note}</td> : <>
                    <td className="text-right font-mono">{v.beta_per_1sd == null ? '—' : `${f(v.beta_per_1sd, v.unit === 'bp' ? 1 : 3)} ${v.unit}`}</td>
                    <td className={cn('text-right font-mono', v.t_stat != null && Math.abs(v.t_stat) >= 2 ? 'text-bloomberg' : '')}>{f(v.t_stat)}</td>
                    <td className="text-right font-mono">{f(v.corr, 2)}</td></>}
                </tr>))}</tbody></table>
            <div className="text-[10px] text-amber mt-1">{s.caveat}</div>
          </div>
          <div>
            <div className="text-2xs text-text-tertiary uppercase mb-1">Latest events ({d.count} since {d.start})</div>
            <div className="overflow-x-auto"><table className="w-full"><thead><tr className="text-2xs text-text-tertiary border-b border-border-subtle">
              <th className="text-left font-normal py-1">Released</th><th className="text-left font-normal">Period</th><th className="text-right font-normal">Actual</th><th className="text-right font-normal">Proxy exp.</th>
              <th className="text-right font-normal">Surprise</th><th className="text-right font-normal">z</th>
              {show.filter((a) => assets.includes(a)).map((a) => <th key={a} className="text-right font-normal">{a}</th>)}</tr></thead>
              <tbody>{[...d.events].reverse().slice(0, 12).map((e: any) => (
                <tr key={e.date + e.event} className="border-b border-border-subtle">
                  <td className="py-0.5 font-mono">{e.date} {e.time_et}</td><td className="font-mono">{e.period}</td>
                  <td className="text-right font-mono">{f(e.actual)}</td><td className="text-right font-mono">{f(e.expectation_proxy)}</td>
                  <td className="text-right font-mono">{f(e.surprise)}</td><td className="text-right font-mono">{f(e.surprise_z)}</td>
                  {show.filter((a) => assets.includes(a)).map((a) => { const r = e.reactions[a]?.[horizon]; return <td key={a} className={cn('text-right font-mono', r > 0 ? 'text-green' : r < 0 ? 'text-red' : '')}>{r == null ? '—' : `${f(r, e.reactions[a].unit === 'bp' ? 0 : 2)}${e.reactions[a].unit === 'bp' ? 'bp' : '%'}`}</td>; })}
                </tr>))}</tbody></table></div>
            <div className="text-[10px] text-text-tertiary mt-1">Surprise proxy: {d.events[0]?.proxy}. Dataset {d.version} · hash {d.hash} · built {String(d.built_at).replace('T', ' ')}{Object.keys(d.errors || {}).length ? ` · missing: ${Object.keys(d.errors).join(', ')}` : ''}.</div>
          </div>
        </>)}
      </div>
    </div>
  );
}

// ACTN: market-wide analyst actions (upgrades, downgrades, initiations, price-target changes) and company guidance
// changes, from Benzinga. Click a ticker to open it.
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { ErrorBox, fmtPrice, Loading, Panel, useJSON } from './shared';

type Kind = 'all' | 'up' | 'down' | 'init' | 'pt';

export function ActionsView({ onOpen }: { onOpen: (s: string) => void }) {
  const [days, setDays] = useState(3);
  const [kind, setKind] = useState<Kind>('all');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/actions?days=${days}`, 300_000);
  const rows = useMemo(() => (data?.ratings ?? []).filter((r: any) => kind === 'all' ? (/upgrade|downgrade|initiat/i.test(r.action) || r.pt_change)
    : kind === 'up' ? /upgrade/i.test(r.action) : kind === 'down' ? /downgrade/i.test(r.action) : kind === 'init' ? /initiat/i.test(r.action) : !!r.pt_change), [data, kind]);
  if (loading && !data) return <Loading label="Loading analyst and company actions…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  const c = data.counts;
  const chip = (on: boolean) => cn('px-2 py-0.5 border rounded-sm text-[11px]', on ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary');
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-2xs">
        {[1, 3, 7, 14].map((d) => <button key={d} className={chip(days === d)} onClick={() => setDays(d)}>{d === 1 ? 'Today' : `${d} days`}</button>)}
        <span className="text-text-tertiary ml-2">{c.upgrades} upgrades · {c.downgrades} downgrades · {c.initiations} initiations · targets {c.target_raised} up / {c.target_cut} down</span>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-3">
        <Panel title="Analyst actions" right={<div className="flex gap-1">{([['all', 'All'], ['up', 'Upgrades'], ['down', 'Downgrades'], ['init', 'Initiations'], ['pt', 'Target changes']] as const).map(([k, l]) =>
          <button key={k} className={chip(kind === k)} onClick={() => setKind(k)}>{l}</button>)}</div>}>
          <div className="max-h-[520px] overflow-auto"><table className="w-full text-2xs">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Date</th><th className="text-left font-normal">Stock</th>
              <th className="text-left font-normal">Firm · analyst</th><th className="text-left font-normal">Action</th><th className="text-right font-normal pr-2">Target</th></tr></thead>
            <tbody>{rows.map((r: any, i: number) => (
              <tr key={i} className="border-t border-border-subtle">
                <td className="font-mono text-text-tertiary py-1 pr-2 whitespace-nowrap">{r.date}</td>
                <td className="pr-2"><button className="font-mono text-bloomberg hover:underline" onClick={() => onOpen(r.ticker)}>{r.ticker}</button>
                  <span className="text-text-tertiary truncate inline-block max-w-[9rem] align-bottom ml-1">{r.name}</span></td>
                <td className="truncate max-w-[13rem] pr-2" title={`${r.firm}${r.analyst ? ` · ${r.analyst}` : ''}`}>{r.firm}{r.analyst ? <span className="text-text-tertiary"> · {r.analyst}</span> : null}</td>
                <td className={/upgrade/i.test(r.action) ? 'text-green' : /downgrade/i.test(r.action) ? 'text-red' : 'text-text-secondary'}>
                  {r.action}{r.rating ? `: ${r.rating_prior && r.rating_prior !== r.rating ? `${r.rating_prior} → ` : ''}${r.rating}` : ''}</td>
                <td className="text-right font-mono whitespace-nowrap pr-2">{r.pt ? <>{r.pt_prior ? <span className="text-text-tertiary">{fmtPrice(r.pt_prior)} → </span> : null}
                  <span className={r.pt_change > 0 ? 'text-green' : r.pt_change < 0 ? 'text-red' : ''}>{fmtPrice(r.pt)}</span></> : '—'}</td>
              </tr>))}</tbody>
          </table>{rows.length === 0 && <div className="text-2xs text-text-tertiary p-2">No actions of this kind in the window.</div>}</div>
        </Panel>
        <Panel title={`Company guidance — ${c.guidance_raised} raised, ${c.guidance_lowered} lowered`}>
          <div className="max-h-[520px] overflow-auto space-y-1.5">{data.guidance.map((g: any, i: number) => (
            <div key={i} className="border-b border-border-subtle pb-1.5 text-2xs">
              <div className="flex items-baseline gap-2">
                <button className="font-mono text-bloomberg hover:underline" onClick={() => onOpen(g.ticker)}>{g.ticker}</button>
                <span className="text-text-primary truncate">{g.name}</span>
                <span className={cn('ml-auto uppercase text-[10px]', g.direction === 'raised' ? 'text-green' : g.direction === 'lowered' ? 'text-red' : 'text-text-tertiary')}>{g.direction ?? ''}</span>
              </div>
              <div className="text-text-secondary">{g.period} EPS {g.eps_prior_low != null ? `${g.eps_prior_low}${g.eps_prior_high ? `–${g.eps_prior_high}` : ''} → ` : ''}{g.eps_low ?? '—'}{g.eps_high ? `–${g.eps_high}` : ''}
                {g.eps_consensus != null ? <span className="text-text-tertiary"> (consensus {g.eps_consensus})</span> : null}<span className="text-text-tertiary"> · {g.date}</span></div>
              {g.notes && <div className="text-text-tertiary truncate" title={g.notes}>{g.notes}</div>}
            </div>))}</div>
        </Panel>
      </div>
      <div className="text-[10px] text-text-tertiary">Source: {data.source}. Upgrades and downgrades move prices more than reiterations; clusters of target cuts often lead estimate cuts.</div>
    </div>
  );
}

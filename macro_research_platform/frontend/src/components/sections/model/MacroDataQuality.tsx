export function MacroDataQuality({data:q}:{data:any}) {
 if(!q)return null;
 return <section aria-label="Macro data readiness" className="p-3 rounded-lg border border-border bg-surface-1 space-y-2">
  <div className="flex flex-wrap justify-between gap-2"><h3 className="text-xs font-semibold">Data readiness and signal drivers</h3><span className="text-xs text-bloomberg">{String(q.status??'unknown').replace(/_/g,' ')}</span></div>
  {q.decision_month && <p className="text-xs text-text-secondary">Decision base {q.decision_month} · allocation month {q.target_month} · {q.used_inputs}/{q.configured_inputs} inputs used</p>}
  {q.warnings?.map((w:string)=><p key={w} className="text-xs text-amber">{w}</p>)}
  {!!q.drivers?.length && <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">{['growth','inflation'].map(block=><div key={block}><h4 className="text-xs capitalize mb-1">{block} factor associations</h4><table className="w-full text-xs"><thead><tr className="text-text-tertiary"><th className="text-left">Input</th><th>Loading</th><th>Available month</th></tr></thead><tbody>{q.drivers.filter((d:any)=>d.block===block).map((d:any)=><tr key={d.key} title={d.note} className="border-t border-border"><td>{d.label}</td><td className="text-center font-mono">{d.loading?.toFixed(2)??'—'}</td><td className="text-center font-mono">{d.available_month??'—'}</td></tr>)}</tbody></table></div>)}</div>}
  <p className="text-[10px] text-text-tertiary">{q.interpretation??'Saved results are being refreshed under the current data-quality checks.'}</p>
  <p className="text-[10px] text-text-tertiary">Factor loadings describe association, not causal impact. Release lags are approximate; historical data revisions remain a limitation.</p>
 </section>;
}

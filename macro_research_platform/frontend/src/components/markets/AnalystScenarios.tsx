import {Panel,fmtPrice} from './shared';
const pc=(v:any)=>typeof v==='number'&&Number.isFinite(v)?`${(v*100).toFixed(1)}%`:'Unavailable';
export function AnalystScenarios({data:d}:{data:any}){if(!d)return null;const risk=d.risk??{};return <Panel title="Probability-weighted DCF scenarios">
 <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-2">{[['Expected value / share',fmtPrice(d.expected_value)],['Expected vs price',pc(d.expected_upside)],['Implied fixed-cash-flow WACC',pc(d.reverse_fixed_cashflow_wacc)],['Implied revenue growth',pc(d.reverse_revenue_growth)]].map(([label,v])=><div className="border border-border rounded-lg p-3" key={label}><p className="text-[10px] text-text-tertiary">{label}</p><p className="text-sm font-mono mt-1">{v}</p></div>)}</div>
 <p className="text-xs text-text-secondary mt-3">Ke = risk-free {pc(risk.risk_free)} + beta {risk.beta?.toFixed(2)??'—'} × mature-market premium {pc(risk.market_risk_premium)} + country premium {pc(risk.country_risk_premium)} + governance premium {pc(risk.governance_risk_premium)}. Calculated WACC {pc(risk.wacc)}.</p>
 <div className="overflow-x-auto mt-3"><table className="w-full text-xs"><thead><tr><th>Path</th><th>Probability</th><th>Growth</th><th>WACC</th><th>Value / share</th><th>Weighted value</th></tr></thead><tbody>{d.matrix?.map((r:any)=><tr key={r.scenario} title={r.error??undefined}><td>{r.scenario}</td><td>{pc(r.probability)}</td><td>{pc(r.growth)}</td><td>{pc(r.wacc)}</td><td>{fmtPrice(r.per_share)}</td><td>{fmtPrice(r.weighted_value)}</td></tr>)}</tbody></table></div>
 {!d.complete_probability_mass&&<p className="text-xs text-amber mt-2">Expected value withheld: a positive-probability case could not be calculated.</p>}
 <p className="text-[11px] text-text-tertiary mt-3">{d.profile?.basis} · {d.profile?.profile} · forecast {d.forecast_years} years · quote currency {d.quote_currency}. {d.note}</p>
 </Panel>;}

export function DevelopedMarketContext({data:d}:{data:any}) {
 if(!d)return null;
 return <Panel title="Local market valuation assumptions">
 <div className="grid sm:grid-cols-3 gap-3 text-xs">
 <div><p className="text-text-tertiary">Country / cash-flow currency</p><p>{d.country ?? 'Unavailable'} · {d.cashflow_currency ?? 'Unavailable'}</p></div>
 <div><p className="text-text-tertiary">Marginal tax reference</p><p>{pc(d.marginal_tax)}</p><p className="text-text-tertiary">{d.tax_source}</p></div>
 <div><p className="text-text-tertiary">Long-run nominal growth ceiling</p><p>{pc(d.terminal_growth_ceiling)}</p></div>
 </div>
 <p className="text-xs mt-3">Risk-free source: {d.risk_free_source ?? 'Unavailable'}. {typeof d.risk_free_basis==='string'?d.risk_free_basis:JSON.stringify(d.risk_free_basis)}</p>
 <p className="text-xs mt-2">{d.method}</p>
 {d.notes?.length>0&&<ul className="list-disc pl-4 mt-2 text-xs text-text-secondary space-y-1">{d.notes.map((n:string)=><li key={n}>{n}</li>)}</ul>}
 <p className="text-[10px] text-text-tertiary mt-3">Developed-market classification snapshot: {d.classification_as_of}. Coverage does not guarantee complete company data.</p>
 </Panel>;
}

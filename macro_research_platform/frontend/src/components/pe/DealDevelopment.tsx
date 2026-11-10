import { Card, NumField, amt } from './peShared';
const CHECKS: Record<string, string> = {earnings:'Quality of earnings',cash:'Working capital and cash conversion',debt:'Debt, leases and lender terms',tax:'Tax structure and loss utilization',commercial:'Commercial plan and exit comparables',legal:'Legal and execution diligence'};
export function DealDevelopment({inputs, set, unit, ccy}: {inputs:any;set:(patch:any)=>void;unit:number;ccy:string}) {
  const kind = unit === 1e6 ? 'm' : 'num';
  const adjustments = inputs.ebitda_adjustments ?? [];
  const patch = (i:number, value:any) => set({ebitda_adjustments:adjustments.map((a:any,j:number)=>i===j?{...a,...value}:a)});
  const accepted = adjustments.filter((a:any)=>a.approved).reduce((sum:number,a:any)=>sum+Number(a.amount||0),0);
  return <div className="space-y-3">
    <Card title="Quality of earnings" right={<button className="text-xs text-bloomberg" onClick={()=>set({ebitda_adjustments:[...adjustments,{label:'',amount:0,source:'',approved:false}]})}>+ Adjustment</button>}>
      <p className="text-[11px] text-text-tertiary mb-2">Only accepted adjustments with an evidence source enter the valuation. Negative adjustments reduce EBITDA.</p>
      {adjustments.map((a:any,i:number)=><div key={i} className="border border-border rounded p-2 mb-2 space-y-2">
        <input aria-label={`Adjustment ${i+1} description`} placeholder="Description (e.g. nonrecurring legal cost)" value={a.label} onChange={e=>patch(i,{label:e.target.value})} className="w-full bg-bg border border-border rounded p-1.5 text-xs" />
        <NumField label={`Adjustment (${ccy}${unit===1e6?'m':''})`} kind={kind} value={a.amount} onChange={v=>patch(i,{amount:v??0})}/>
        <input aria-label={`Adjustment ${i+1} evidence`} placeholder="Evidence: filing, period and page / diligence note" value={a.source} onChange={e=>patch(i,{source:e.target.value})} className="w-full bg-bg border border-border rounded p-1.5 text-xs" />
        <div className="flex justify-between text-xs"><label><input type="checkbox" checked={!!a.approved} onChange={e=>patch(i,{approved:e.target.checked})}/> Accept in model</label><button onClick={()=>set({ebitda_adjustments:adjustments.filter((_:any,j:number)=>i!==j)})} className="text-red">Remove</button></div>
      </div>)}
      <div className="grid grid-cols-3 gap-1 text-[11px] tabular-nums"><span>Reported<br/>{amt(inputs.ebitda,ccy,unit)}</span><span>Accepted<br/>{amt(accepted,ccy,unit)}</span><span>Underwritten<br/>{amt(Number(inputs.ebitda)+accepted,ccy,unit)}</span></div>
      <label className="flex items-start gap-2 text-[11px] mt-3"><input type="checkbox" checked={!!inputs.apply_adjustments_to_plan} onChange={e=>set({apply_adjustments_to_plan:e.target.checked})}/>Also lift forecast margins by accepted adjustments / base revenue. Leave off when the plan already includes normalization.</label>
    </Card>
    <Card title="Tax structure · explicit assumptions">
      <p className="text-[11px] text-text-tertiary mb-2">Configurable tax mechanics. Local exemptions, group allocations, elections and ownership-change restrictions need tax diligence.</p>
      <div className="workspace-controls flex flex-wrap gap-2 mb-3 text-[11px]">
        <button className="border border-border rounded p-1.5" onClick={()=>set({interest_cap_basis:'ebitda',interest_cap_pct:.3,nol_utilization_pct:.8,interest_deduction_floor:0,tax_profile:'US-style screening'})}>US-style screening</button>
        <button className="border border-border rounded p-1.5" disabled={inputs.currency!=='GBP'} title="GBP deal currency required; excludes worldwide debt cap and group allocations" onClick={()=>set({interest_cap_basis:'ebitda',interest_cap_pct:.3,interest_deduction_floor:2e6,nol_utilization_pct:1,tax_profile:'UK-style screening'})}>UK-style screening (GBP)</button>
      </div>
      <div className="text-[10px] text-text-tertiary mb-2">{inputs.tax_profile??'Custom assumptions'} · presets set only selected structural assumptions, not tax compliance.</div>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-[11px]">Interest-cap basis<select aria-label="Interest-cap basis" value={inputs.interest_cap_basis??'ebitda'} onChange={e=>set({interest_cap_basis:e.target.value})} className="w-full bg-bg border border-border rounded p-1 mt-1"><option value="ebitda">EBITDA + tax adjustments</option><option value="ebit">EBIT + tax adjustments</option></select></label>
        <NumField label="NOL utilization (% income)" kind="pct" value={inputs.nol_utilization_pct??1} onChange={v=>set({nol_utilization_pct:v??1})}/>
        <NumField label="Opening tax losses" kind={kind} value={inputs.opening_nol??0} onChange={v=>set({opening_nol:v??0})}/>
        <NumField label="Opening disallowed interest" kind={kind} value={inputs.opening_disallowed_interest??0} onChange={v=>set({opening_disallowed_interest:v??0})}/>
        <NumField label="Annual interest income" kind={kind} value={inputs.interest_income??0} onChange={v=>set({interest_income:v??0})}/>
        <NumField label="Annual taxable-income adjustment" kind={kind} value={inputs.tax_adjustment??0} onChange={v=>set({tax_adjustment:v??0})}/>
        <NumField label="Interest deduction floor" kind={kind} value={inputs.interest_deduction_floor??0} onChange={v=>set({interest_deduction_floor:v??0})}/>
        <NumField label="Annual NOL amount limit (optional)" kind={kind} value={inputs.annual_nol_limit} onChange={v=>set({annual_nol_limit:v})}/>
      </div>
    </Card>
    <Card title="Lender terms & seasonal cash">
      <div className="grid grid-cols-2 gap-2 mb-3">
        <NumField label="Max closing net leverage (optional)" kind="x" value={inputs.covenants?.max_net_leverage} onChange={v=>set({covenants:{...inputs.covenants,max_net_leverage:v}})}/>
        <NumField label="Annual leverage step-down" kind="x" value={inputs.covenants?.step_down??.25} onChange={v=>set({covenants:{...inputs.covenants,step_down:v??0}})}/>
        <NumField label="Minimum interest cover" kind="x" value={inputs.covenants?.min_interest_cover??2} onChange={v=>set({covenants:{...inputs.covenants,min_interest_cover:v??0}})}/>
        <NumField label="Revolver maturity (year, optional)" kind="int" value={inputs.revolver?.tenor} onChange={v=>set({revolver:{...inputs.revolver,tenor:v}})}/>
        <NumField label="Revolver drawn at close" kind={kind} value={inputs.revolver?.drawn_at_close??0} onChange={v=>set({revolver:{...inputs.revolver,drawn_at_close:v??0}})}/>
      </div>
      {(['quarterly_cash_weights','quarterly_debt_weights'] as const).map(k=><div key={k} className="mb-2"><p className="text-[11px] text-text-secondary mb-1">{k==='quarterly_cash_weights'?'Annual FCF timing':'Mandatory debt-service timing'} · total must equal 100%</p><div className="grid grid-cols-4 gap-1">{(inputs[k]??(k==='quarterly_cash_weights'?[.25,.25,.25,.25]:[0,0,0,1])).map((v:number,i:number)=><NumField key={i} label={`Q${i+1}`} kind="pct" value={v} onChange={x=>{const a=[...(inputs[k]??(k==='quarterly_cash_weights'?[.25,.25,.25,.25]:[0,0,0,1]))];a[i]=x??0;set({[k]:a});}}/>)}</div></div>)}
      <p className="text-[10px] text-text-tertiary">Cash-timing diagnostic uses annual FCF; seasonal borrowing interest and quarterly tax true-ups are excluded.</p>
    </Card>
    <Card title="Diligence checklist">
      <div className="space-y-2">{Object.entries(CHECKS).map(([k,v])=><label key={k} className="flex gap-2 items-center text-xs"><input type="checkbox" checked={!!inputs.diligence?.[k]} onChange={e=>set({diligence:{...inputs.diligence,[k]:e.target.checked}})}/>{v}</label>)}</div>
      <p className="text-[10px] text-text-tertiary mt-3">User-attested checklist; retained with the saved deal. Completion is not IC approval.</p>
    </Card>
  </div>;
}
export function UnderwritingResults({res,unit,ccy}:{res:any;unit:number;ccy:string}) {
  const d=res.diligence, l=res.liquidity; if(!d||!l)return null;
  return <Card title="Underwriting review" right={<span className="text-xs text-text-secondary">{d.completed}/{d.total} diligence areas</span>}>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs mb-3">
      <div className="p-2 bg-bg rounded border border-border">Diligence<br/><strong className={d.reasons.length?'text-amber':'text-green'}>{d.reasons.length?'Review required':'Screening checks complete'}</strong></div>
      <div className="p-2 bg-bg rounded border border-border">Peak seasonal revolver<br/><strong>{amt(l.peak_revolver,ccy,unit)} {ccy}{unit===1e6?'m':''}</strong></div>
      <div className="p-2 bg-bg rounded border border-border">First reserve shortfall<br/><strong className={l.first_shortfall?'text-red':'text-green'}>{l.first_shortfall??'None modeled'}</strong></div>
    </div>
    {d.reasons.map((r:string)=><p key={r} className="text-[11px] text-amber mb-1">{r}</p>)}
    <details className="mt-3"><summary className="cursor-pointer text-xs text-text-secondary">Quarterly cash timing · {l.quarters.length} periods</summary><div className="overflow-auto max-h-72 mt-2"><table className="w-full text-[11px] tabular-nums"><thead className="sticky top-0 bg-surface-1"><tr>{['Period','FCF','Debt due','Cash','Revolver','Reserve gap'].map(x=><th key={x} className="text-right p-1">{x}</th>)}</tr></thead><tbody>{l.quarters.map((r:any)=><tr key={`${r.year}-${r.quarter}`} className={r.gap>0?'text-red':'text-text-secondary'}><td className="p-1">Y{r.year} Q{r.quarter}</td>{['fcf','mandatory','cash','revolver','gap'].map(k=><td key={k} className="text-right p-1">{amt(r[k],ccy,unit)}</td>)}</tr>)}</tbody></table></div></details>
    <p className="text-[10px] text-text-tertiary mt-2">{l.note}</p>
  </Card>;
}

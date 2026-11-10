import {useState} from 'react';
import {Panel} from './ui/Controls';
import {useDeepStatusQ} from './api';
const LABELS:Record<string,string>={financial_stress:'Financial stress',credit_cycle:'Credit cycle',liquidity:'Liquidity',expectations:'Rate expectations',global_trade:'Global trade',labour_housing:'Labour & housing',rates_credit:'Rates & credit',real_economy:'Real economy',market_prices:'Market prices',macro_factors:'Macro factors',news:'News & missing flags',other_core:'Other inputs',combined_inputs:'Combined inputs'};
export function ModularNetwork(){
 const q=useDeepStatusQ();const d=q.data;const [selected,setSelected]=useState<string|null>(null);
 if(!d)return <Panel title="Modular sequence network"><p role="status">{q.isError?'Network metadata unavailable. Retry when the backend is reachable.':'Loading network metadata…'}</p><button className="ml-btn" onClick={()=>q.refetch()}>Refresh metadata</button></Panel>;
 const modular=d.configured?.architecture==='modular';
 const measured=d.modules??{};const observed=Object.keys(measured).length>0;
 const actualModules=modular?measured:{combined_inputs:Object.values(measured).flat()};
 const names=observed?Object.keys(actualModules):[];
 const modules:string[]=observed?names:modular?(d.configured_modules??['rates_credit','real_economy','market_prices','macro_factors','news']):['combined_inputs'];
 const routing=modular?(d.routing??[]):[];const reports=d.training_reports??[];
 const info=selected??modules[0];
 return <Panel title={modular?'Modular sequence network':'Shared sequence reference'} sub="Architecture and completed training metadata. This diagram does not simulate GRU activations or recompute forecasts in the browser.">
 <div className="flex flex-wrap gap-3 text-xs mb-4"><span>{d.configured.profile}</span><span>{d.configured.hidden} units × {d.configured.layers} recurrent layers</span><span>{d.configured.attention_heads} attention heads</span><span>Version {d.fingerprint}</span><span role="status">{d.training?'Training in background':observed?'Completed model metadata':'Awaiting completed model metadata'}</span></div>
 <div className="overflow-x-auto rounded-lg border border-border p-4" aria-label="Sequence model architecture">
  <div className="grid grid-cols-[180px_24px_160px_24px_160px_24px_160px] gap-2 items-center min-w-[800px]">
   <div className="space-y-2"><p className="text-[10px] uppercase text-text-tertiary">{modular?'Specialist encoders':'Input representation'}</p>{modules.map(name=>{const share=routing.length?routing.reduce((sum:number,r:any)=>sum+(r[name]??0),0)/routing.length:null;return <button key={name} className={`block w-full text-left border rounded-lg p-3 text-xs ${info===name?'border-amber':'border-border'}`} onClick={()=>setSelected(name)} aria-pressed={info===name}><span>{LABELS[name]??name}</span><span className="block text-text-tertiary mt-1">{observed?`${actualModules[name].length} transformed inputs`:'Configured module'}{share==null?'':` · ${(share*100).toFixed(1)}% routing`}</span></button>;})}</div>
   <span aria-hidden>→</span><div className="border border-border rounded-lg p-3 text-xs"><b>{modular?'Routing + fusion':'Shared input'}</b><p className="text-text-secondary mt-2">{modular?'Softmax-weighted summary plus all specialist representations.':'Standardized core, factor and news inputs.'}</p></div>
   <span aria-hidden>→</span><div className="border border-border rounded-lg p-3 text-xs"><b>Historical memory</b><p className="text-text-secondary mt-2">24 monthly observations → stacked GRU{d.configured.attention_heads>0?' → temporal attention':''} → normalization</p></div>
   <span aria-hidden>→</span><div className="border border-border rounded-lg p-3 text-xs"><b>{modular?'Separate task heads':'Shared output layer'}</b><p className="text-text-secondary mt-2">Recession · equity drawdown · yields · inflation · oil · unemployment</p></div>
  </div>
 </div>
 <div className="grid sm:grid-cols-2 gap-4 mt-4 text-xs"><div><b>{LABELS[info]??info}</b><p className="text-text-secondary mt-2">{observed?`${actualModules[info]?.length??0} features enter this module.`:'Feature counts and learned routing will appear after a model completes.'} Routing weights describe internal combination, not causal importance or portfolio weights.</p></div><div><b>Training evidence</b><p className="text-text-secondary mt-2">{reports.length?`${reports.length} completed seeds · ${reports[0].parameters?.toLocaleString()} parameters per seed`:'No completed training report for this version yet.'}</p><p className="text-text-tertiary mt-2">The interactive shallow model has separate exported weights and controls. Rebuilding this model does not block that view.</p></div></div>
 {d.error&&<p role="alert" className="text-xs text-red mt-3">{d.error}</p>}
 </Panel>;
}

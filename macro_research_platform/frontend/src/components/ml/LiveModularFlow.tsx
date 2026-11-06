import {useEffect,useMemo,useState} from 'react';
import {Panel,RangeSlider,Segmented} from './ui/Controls';
import {EChart,axisStyle,chartTheme} from './ui/EChart';
import {measuredFlowOption,flowPoint} from './liveFlow';
import {useLiveStateQ,refreshLiveState} from './api';
const number=(v:any,d=3)=>typeof v==='number'&&Number.isFinite(v)?v.toFixed(d):'—';
export function LiveModularFlow(){
 const q=useLiveStateQ(),d=q.data,trace=d?.trace;
 const [seed,setSeed]=useState(0),[step,setStep]=useState(23),[playing,setPlaying]=useState(false),[follow,setFollow]=useState(true),[error,setError]=useState('');
 useEffect(()=>{let active=true;const update=()=>refreshLiveState().catch(e=>{if(active)setError(String(e.message));});void update();const timer=setInterval(update,60000);return()=>{active=false;clearInterval(timer);};},[]);
 useEffect(()=>{if(trace){setSeed(v=>Math.min(v,trace.seeds.length-1));if(follow)setStep(trace.months.length-1);else setStep(v=>Math.min(v,trace.months.length-1));}},[trace?.input_digest,trace?.trained_at,follow]);
 useEffect(()=>{if(!playing||!trace)return;const timer=setInterval(()=>setStep(v=>{if(v>=trace.months.length-1){setPlaying(false);return v;}return v+1;}),650);return()=>clearInterval(timer);},[playing,trace?.input_digest]);
 const [theme,setTheme]=useState(()=>chartTheme());
 const measurement=trace?.seeds?.[seed],at=Math.min(step,(trace?.months?.length??1)-1);
 const [motion,setMotion]=useState(true),[reduced,setReduced]=useState(false);
 useEffect(()=>{const media=window.matchMedia?.('(prefers-reduced-motion: reduce)');const update=()=>{setReduced(!!media?.matches||document.documentElement.classList.contains('terminal-reduce-motion'));setTheme(chartTheme());};update();media?.addEventListener('change',update);const observer=new MutationObserver(update);observer.observe(document.documentElement,{attributes:true,attributeFilter:['class']});return()=>{media?.removeEventListener('change',update);observer.disconnect();};},[]);
 const moving=motion&&!reduced;
 const graph=useMemo(()=>measurement&&trace?measuredFlowOption(measurement,trace,at,theme,moving):null,[measurement,at,trace?.trained_at,theme,moving]);
 const training=d?.training,preview=d?.preview_training;
 const progress=[['Full research training',training],['Inspection checkpoint',preview]].filter(([,p])=>p) as [string,any][];
 return <Panel title="Live modular signal flow" sub="Measured states from an actual saved checkpoint. Moving signals connect specialists, sequence memory, attention and task outputs. Measurements control line strength and node brightness; motion illustrates flow.">
  <div className="flex flex-wrap items-center gap-3 text-xs mb-3"><span role="status">{d?.job?.running?'Refreshing measured states':trace?'Measured checkpoint available':'Preparing first measured checkpoint'}</span><button className="ml-btn" disabled={d?.job?.running} onClick={()=>{setError('');void refreshLiveState().catch(e=>setError(e.message));}}>Refresh inputs</button>{trace&&<span>{trace.purpose==='inspection_preview'?'Bounded inspection preview · not a served model':'Full research checkpoint · promotion gates still apply'}</span>}</div>
  {progress.length>0&&<div className="grid sm:grid-cols-2 gap-2 mb-3">{progress.map(([label,p])=><div className="border border-border rounded-lg p-3 text-xs" key={label}><b>{label}</b><p className="mt-1">{p.stage?.replace(/_/g,' ')} · {p.message??''}</p>{p.epoch!=null&&<p>Seed {p.seed+1} · epoch {p.epoch} · validation loss {number(p.validation_loss,4)}</p>}<p className="text-text-tertiary mt-1">Updated {p.updated_at}</p></div>)}</div>}
  {!trace&&<p role="status" className="text-xs text-text-secondary">Waiting for measured model states. The architecture view remains available while the isolated worker reads data and fits an inspection checkpoint.</p>}
  {trace&&measurement&&<>
   <p className="text-xs text-text-secondary mb-3">Inputs through {trace.as_of} · inferred {trace.inferred_at} · {trace.inputs_changed?'new input values':'input values unchanged'} · trained {trace.trained_at}</p>
   <div className="flex flex-wrap gap-3 items-center mb-3"><Segmented label="Measured seed" value={String(seed)} onChange={v=>setSeed(Number(v))} options={trace.seeds.map((_:any,i:number)=>({value:String(i),label:`Seed ${i+1}`}))}/><button className="ml-btn" onClick={()=>{setFollow(false);if(at>=trace.months.length-1)setStep(0);setPlaying(v=>!v);}}>{playing?'Pause measured replay':'Replay measured sequence'}</button><button className="ml-btn" onClick={()=>{setPlaying(false);setFollow(true);setStep(trace.months.length-1);}}>Follow latest</button><button className="ml-btn" disabled={reduced} onClick={()=>setMotion(v=>!v)}>{reduced?'Reduced motion enabled':motion?'Pause signal motion':'Resume signal motion'}</button><span className="font-mono text-xs">{trace.months[at]}{follow?' · latest':' · prefix replay'}</span></div>
   <RangeSlider label="Measured month" value={at} min={0} max={trace.months.length-1} step={1} onChange={v=>{setPlaying(false);setFollow(false);setStep(v);}}/>
   <div className="overflow-x-auto mt-3 rounded-lg border border-border"><div className="min-w-[650px] relative ml-flow" style={{height:450}}>
    <div className="ml-flow-floor" aria-hidden/>
    <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>{[[1,29],[31,44],[46,62],[64,78],[80,99]].map(([a,b],i)=><polygon key={i} points={[flowPoint(a,3),flowPoint(b,3),flowPoint(b,97),flowPoint(a,97)].map(p=>p.join(',')).join(' ')} fill={theme.series[i===3?1:0]} fillOpacity={.035} stroke={theme.muted} strokeOpacity={.25} strokeWidth={.12}/>)}</svg>
    <div className="absolute inset-0 z-[1]"><EChart option={graph!} height={450} merge ariaLabel="Measured modular neural signal flow"/></div>
    <div className="absolute inset-0 pointer-events-none z-[2] text-[9px] font-mono text-text-tertiary">{[[3,'SPECIALISTS'],[32,'FUSION'],[47,'GRU MEMORY'],[65,'ATTENTION'],[81,'TASK HEADS']].map(([x,label])=><span key={label} className="absolute" style={{left:`${x}%`,top:'5%'}}>{label}</span>)}</div>
   </div></div>
   <p className="text-[10px] text-text-tertiary mt-2">Blue: routing and state flow · gold: temporal attention. Memory nodes group monthly states; hover for measured values. Lines summarize stages rather than individual neural weights.</p>
   <div className="grid xl:grid-cols-2 gap-3 mt-3">
    <div><p className="text-xs mb-1">Temporal attention over the available prefix</p>{measurement.attention[at]?.length?<EChart height={190} ariaLabel="Measured temporal attention" option={{tooltip:{trigger:'axis'},grid:{left:45,right:15,top:15,bottom:45},xAxis:{type:'category',data:trace.months.slice(0,at+1),...axisStyle(theme)},yAxis:{type:'value',min:0,max:1,...axisStyle(theme)},series:[{type:'bar',data:measurement.attention[at],itemStyle:{color:theme.series[1]}}]}}/>:<p className="text-xs">Attention is disabled for this checkpoint.</p>}</div>
    <div><p className="text-xs mb-1">Measured GRU memory · first {measurement.hidden[0].length} units</p><EChart height={190} ariaLabel="Measured recurrent memory" option={{tooltip:{trigger:'item'},grid:{left:45,right:15,top:15,bottom:45},xAxis:{type:'category',data:trace.months.slice(0,at+1),...axisStyle(theme)},yAxis:{type:'category',data:measurement.hidden[0].map((_:any,i:number)=>`h${i+1}`),...axisStyle(theme)},visualMap:{show:false,min:-1,max:1,inRange:{color:[theme.series[1],theme.surface,theme.series[0]]}},series:[{type:'heatmap',data:measurement.hidden.slice(0,at+1).flatMap((row:number[],i:number)=>row.map((v,j)=>[i,j,v]))}]}}/></div>
   </div>
   <p className="text-[10px] text-text-tertiary mt-3">{trace.note} {d?.cadence}</p>
  </>}
  {(error||d?.job?.error||q.isError)&&<p role="alert" className="text-xs text-red mt-3">{error||d?.job?.error||'Live state is temporarily unreachable; the last measured state is retained.'}</p>}
 </Panel>;
}

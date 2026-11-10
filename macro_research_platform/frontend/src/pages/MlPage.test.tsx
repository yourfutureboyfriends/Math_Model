import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {MlPage} from './MlPage';
import {mlQueryClient} from '@/components/ml/api';

const QUESTION='Will an NBER recession be under way at any point in the next 12 months?';
const NOTE='Answer known 12 months later plus the NBER announcement lag.';
const TITLE='US recession within 12 months';

type ChartOption={series?:Array<{type?:string;data?:unknown[]}>;tooltip?:{formatter:(p:{value:number[]})=>string}};
const charts=vi.hoisted(()=>({options:[] as ChartOption[]}));
vi.mock('@/hooks/useNeuralStream',()=>({useNeuralStream:()=>({status:'open',error:null,reconnects:0,gaps:{}})}));
vi.mock('@/context/AuthContext',()=>({useAuth:()=>({token:'t',user:{username:'ui',role:'quant'},isAuthenticated:true})}));
vi.mock('@/components/ml/ui/EChart',()=>({
 EChart:(p:{option:ChartOption;ariaLabel?:string})=>{charts.options.push(p.option);return <div role="img" aria-label={p.ariaLabel}/>;},
 axisStyle:()=>({axisLabel:{}}),
 chartTheme:()=>({series:['#3987e5','#f0a020','#40c040','#e05050'],muted:'#777',mutedText:'#999',textStrong:'#fff',surface:'#111',border:'#333',red:'#e05050',green:'#40c040',amber:'#f0a020',outcome:'rgba(9,9,9,.1)'}),
 useChartTheme:()=>({series:['#3987e5','#f0a020'],textStrong:'#fff'}),
}));

const model={name:'Logistic champion',what:'Logistic on the core inputs',probability:0.18,raw:0.18,
 record:{skill_vs_base_rate:0.12,auroc:0.78,brier:0.14,hit_rate:0.7},gain:{p_no_gain:0.3},gate:'baseline'};
/** `full` omits question/notes, the state the engine is in before it has answered for a task. */
const summary=(full:boolean)=>({task:'recession_12m',title:TITLE,used_for:'Recession risk on the desk',ready:true,flags:[],
 question:full?QUESTION:undefined,notes:full?[NOTE]:undefined,
 models:{champion:{probability:0.18,skill:0.12}},best_by_record:'champion',network_probability:null,network_range:null,
 signal:{probability:0.18,model:'champion',skill_vs_base_rate:0.12,useful:true}});
const detail=(full:boolean)=>({available:true,task:'recession_12m',title:TITLE,month:'2026-11',as_of_inputs:'2026-10',
 question:full?QUESTION:undefined,notes:full?[NOTE]:undefined,used_for:'Recession risk on the desk',
 signal:{probability:0.18,model:'champion',skill_vs_base_rate:0.12,useful:true},
 models:{champion:model},positive_share:0.15,promotion:{bar:0.05,comparisons:8},
 backtest:{from:'1985-01',to:'2026-10',forecasts:400,by_era:{},overall:{}}});

const routes:Record<string,unknown>={};
const seed=(full:boolean)=>{
 routes['/api/v1/ml/tasks']={tasks:[summary(full)]};
 routes['/api/v1/ml/tasks/recession_12m']=detail(full);
 routes['/api/v1/ml/tasks/recession_12m/history']={months:['2026-09','2026-10'],outcome:[0,0],models:{champion:[0.2,0.18]}};
 routes['/api/v1/ml/registry']={promotions:[],recent_forecasts:[],retrains:[],stages:[]};
 routes['/api/v1/ml/autonomous/status']={enabled:false,job:{running:false},state:{},schedule:'Daily',learning_policy:'Observed data only',promotion_policy:'Prospective gates'};
 routes['/api/v1/ml/online/status']={enabled:false,running:false,policy:'Supervision policy',sources:[],learning:'Learning note'};
};

let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{
 vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);
 vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}});
 vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener(){},removeEventListener(){}}));
 vi.stubGlobal('fetch',vi.fn(async(url:unknown)=>({ok:true,status:200,json:async()=>routes[String(url)]??{}})));
 charts.options.length=0;mlQueryClient.clear();localStorage.clear();
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(()=>{act(()=>root.unmount());host.remove();mlQueryClient.clear();localStorage.clear();vi.unstubAllGlobals();});

// TanStack Query resolves on later turns than the render, so flush macrotasks until the page settles.
const settle=async(turns=10)=>{for(let i=0;i<turns;i++)await act(async()=>{await new Promise((r)=>setTimeout(r,0));});};
const mount=async()=>{await act(async()=>root.render(<MlPage/>));await settle();};
const cellWithTitle=()=>[...host.querySelectorAll('td span')].find((s)=>s.textContent===TITLE);
// Charts push an option on every render, so read the most recent one that matches.
const lastChart=(pred:(o:ChartOption)=>boolean)=>[...charts.options].reverse().find(pred);
const stat=(label:string)=>[...host.querySelectorAll('.ml-stat')]
 .find((d)=>d.querySelector('.ml-stat-label')?.textContent===label)?.querySelector('.ml-stat-value')?.textContent;

it('shows the event a task is trained on beside its short title',async()=>{
 seed(true);await mount();
 const title=cellWithTitle()?.getAttribute('title')??'';
 expect(title).toContain('at any point in the next 12 months');
 expect(title).toContain(NOTE);
});

it('does not invent a definition the engine has not supplied',async()=>{
 // The short title is ambiguous on its own — "within 12 months" does not distinguish month t+12 from
 // any month in the window. Guessing at one in the frontend would state a training target as fact.
 seed(false);await mount();
 const cell=cellWithTitle();
 expect(cell).toBeTruthy();
 expect(cell?.hasAttribute('title')).toBe(false);
});

it('states the question in the task-by-model tooltip, where the probability is read',async()=>{
 seed(true);await mount();
 const heat=charts.options.find((o)=>o?.series?.[0]?.type==='heatmap');
 expect(heat).toBeTruthy();
 const text=heat!.tooltip!.formatter({value:[0,0,18,0.12]});
 expect(text).toContain(TITLE);
 expect(text).toContain('at any point in the next 12 months');
});

it('leaves the tooltip alone rather than printing undefined when the question is absent',async()=>{
 seed(false);await mount();
 const heat=charts.options.find((o)=>o?.series?.[0]?.type==='heatmap');
 const text=heat!.tooltip!.formatter({value:[0,0,18,0.12]});
 expect(text).toContain(TITLE);
 expect(text).not.toContain('undefined');
});

it('puts the question above every probability in the model lab',async()=>{
 seed(true);localStorage.setItem('ml_tab','lab');await mount();
 expect(host.textContent).toContain(`Leaderboard — ${TITLE}`);
 expect(host.textContent).toContain('at any point in the next 12 months');
 expect(host.textContent).toContain(NOTE);
});

it('does not report a model count or a promotion count it was not given',async()=>{
 // models.length || 9 asserted the engine's nine-model ladder while nothing had trained, and the
 // promotion total read 0 before the registry had answered at all.
 seed(true);
 routes['/api/v1/ml/tasks']={tasks:[{task:'recession_12m',title:TITLE,ready:false}]};
 routes['/api/v1/ml/registry']={recent_forecasts:[],retrains:[],stages:[]};
 await mount();
 expect(stat('Models per task')).toBe('—');
 expect(stat('Promotions')).toBe('—');
 expect(host.textContent).not.toContain('9');
});

it('counts promotions once the registry has actually answered',async()=>{
 seed(true);
 routes['/api/v1/ml/registry']={promotions:[{task:'recession_12m',model:'network',active:true}],recent_forecasts:[],retrains:[],stages:[]};
 await mount();
 expect(stat('Promotions')).toBe('1');
});

it('plots an unrecorded skill as no bar rather than as skill of zero',async()=>{
 // A bar sitting exactly on the zero line reads as the specific finding "no better than the base
 // rate", which is not the same as "not measured".
 seed(true);
 routes['/api/v1/ml/tasks']={tasks:[{...summary(true),signal:{probability:0.18,model:'champion',skill_vs_base_rate:null,useful:false}}]};
 await mount();
 const bar=lastChart((o)=>o?.series?.[0]?.type==='bar');
 expect(bar).toBeTruthy();
 const data=JSON.stringify(bar!.series![0].data);
 expect(data).toContain('"value":null');
 expect(data).not.toContain('"value":0');
});

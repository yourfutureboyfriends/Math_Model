import {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {AutonomousStatus} from './AutonomousStatus';
const state=vi.hoisted(()=>({data:null as any,send:vi.fn().mockResolvedValue({queued:true})}));
vi.mock('./api',()=>({useAutonomousStatusQ:()=>({data:state.data,refetch:vi.fn(),error:null}),send:state.send}));
let host:HTMLDivElement,root:ReturnType<typeof createRoot>;
beforeEach(()=>{vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT',true);host=document.createElement('div');document.body.append(host);root=createRoot(host);state.send.mockClear();state.data={enabled:true,job:{running:false},state:{phase:'complete'},recent_events:[],schedule:'Session-aware',learning_policy:'Observed data only',promotion_policy:'Prospective gates'};});
afterEach(()=>{act(()=>root.unmount());host.remove();vi.unstubAllGlobals();});
it('queues a real learning endpoint from the existing workspace',async()=>{await act(async()=>root.render(<AutonomousStatus/>));await act(async()=>host.querySelector('button')?.click());expect(state.send).toHaveBeenCalledWith('/api/v1/ml/autonomous/run','POST');expect(host.textContent).toContain('learning run queued');});
it('disables duplicate runs and labels uncalibrated research forecasts',async()=>{state.data.job.running=true;state.data.forecast={origin:'2026-11-05T12:00:00Z',graph_nodes:58,tasks:['recession_12m'],horizons:[1],probabilities:[[.3]],calibration_ready:[[false]]};await act(async()=>root.render(<AutonomousStatus/>));expect(host.querySelector('button')?.disabled).toBe(true);expect(host.textContent).toContain('30.0%');expect(host.textContent).toContain(' raw');});
it('displays source failures without implying a deployment',async()=>{state.data.state.last_run={status:'held_data_quality',source_failures:[{source:'feed'}]};await act(async()=>root.render(<AutonomousStatus/>));expect(host.textContent).toContain('held data quality');expect(host.textContent).toContain('1 source/extraction checks');});
it('distinguishes fitted research probes from an inactive live policy',async()=>{state.data.state.research_probes={scope:'Research only',causal:{status:'research_fit',variables:8,lagged_edges:12},world_model:{status:'research_fit',synthetic_paths:4},foraging:{status:'awaiting_offline_query_episodes',live_ppo_enabled:false}};await act(async()=>root.render(<AutonomousStatus/>));expect(host.textContent).toContain('8 observed variables');expect(host.textContent).toContain('4 synthetic research paths');expect(host.textContent).toContain('Live PPO selection inactive');});
it('shows query collection progress and explains normal validation waiting',async()=>{state.data.state.last_run={reason:'insufficient_evidence'};state.data.state.research_probes={scope:'Research only',foraging:{}};state.data.state.query_collection={status:'collecting_query_history',distinct_days:2,complete_episodes:3,live_ppo_enabled:false};await act(async()=>root.render(<AutonomousStatus/>));expect(host.textContent).toContain('Learning cycle complete');expect(host.textContent).toContain('2 distinct collection days');expect(host.textContent).toContain('Waiting for forecast outcomes');expect(host.textContent).toContain('existing served model stays active');});
it('shows verified replay records separately from outcome-ready monthly origins',async()=>{state.data.state.research_probes={scope:'Research only',foraging:{}};state.data.state.query_collection={status:'collecting_query_history',verified_episodes:5,labelled_monthly_origins:0,required_monthly_origins:24,live_ppo_enabled:false};state.data.state.source_policy={status:'collecting_outcomes'};await act(async()=>root.render(<AutonomousStatus/>));expect(host.textContent).toContain('5 verified episodes');expect(host.textContent).toContain('0/24 labelled monthly origins');expect(host.textContent).toContain('Offline source policy: collecting outcomes');});
// Reads one labelled field's value, because "Not reported" appears in several and asserting on the
// whole page lets one honest field cover for a sibling that is still inventing a zero.
const field=(label:string)=>[...host.querySelectorAll('b')].find(b=>b.textContent===label)?.parentElement?.querySelector('p')?.textContent;
it('reports absent learning counts as not reported instead of zero',async()=>{
 // new_matured_origins is only set during the checking_learning phase and evaluation only after a
 // prospective run; both were rendered as 0 whenever the pipeline had not reported them.
 await act(async()=>root.render(<AutonomousStatus/>));
 expect(field('New labelled origins')).toBe('Not reported');
 expect(field('Prospective evidence')).toBe('Not reported');
 expect(host.textContent).not.toContain('0 matured paired rows');
});
it('still reports the counts the pipeline did send',async()=>{
 state.data.state.new_matured_origins=3;state.data.state.evaluation={matured_paired_rows:11};
 await act(async()=>root.render(<AutonomousStatus/>));
 expect(field('New labelled origins')).toBe('3');
 expect(field('Prospective evidence')).toBe('11 matured paired rows');
});
it('states the labelled-origin threshold only when the server reported it',async()=>{
 state.data.state.research_probes={scope:'Research only',foraging:{}};
 state.data.state.query_collection={status:'collecting_query_history',verified_episodes:5,live_ppo_enabled:false};
 await act(async()=>root.render(<AutonomousStatus/>));
 expect(host.textContent).toContain('5 verified episodes');
 expect(host.textContent).toContain('labelled monthly origins not reported');
 expect(host.textContent).not.toContain('/24');
});
it('shows a reported count without inventing the threshold beside it',async()=>{
 state.data.state.research_probes={scope:'Research only',foraging:{}};
 state.data.state.query_collection={status:'collecting_query_history',verified_episodes:5,labelled_monthly_origins:7,live_ppo_enabled:false};
 await act(async()=>root.render(<AutonomousStatus/>));
 expect(host.textContent).toContain('7 labelled monthly origins');
 expect(host.textContent).not.toContain('7/');
});
it('does not report zero extraction confidence for an event that has none',async()=>{
 state.data.recent_events=[{entity:'Federal Reserve',action:'rate_hold',evidence:'Held the target range.',available_at:'2026-11-01T00:00:00Z'}];
 await act(async()=>root.render(<AutonomousStatus/>));
 expect(host.textContent).toContain('extraction confidence not reported');
 expect(host.textContent).not.toContain('0% (uncalibrated)');
});

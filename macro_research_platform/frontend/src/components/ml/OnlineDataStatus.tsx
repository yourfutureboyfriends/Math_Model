import {Panel} from './ui/Controls';
import {useOnlineStatusQ} from './api';
import {useStreamedPayload} from '@/store/mlStreamStore';
const date=(v:any)=>typeof v==='number'?new Date(v*1000).toISOString().replace('T',' ').slice(0,19)+' UTC':'Awaiting first update';
export function OnlineDataStatus(){
 // Prefer the pushed frame over the poll. The stream samples the same api.ml.online.status function
 // the REST route returns, on the same 30s cadence, so the payload is identical by construction.
 // The helper withholds it when the producer failed or the socket is no longer open, which resumes
 // the poll as an automatic fallback.
 const streamed=useStreamedPayload('online_status');
 const q=useOnlineStatusQ(streamed!==undefined),d=streamed??q.data;
 return <Panel title="Continuous financial data & learning" sub="Automatic provider checks, accepted data versions and learning readiness.">
 {!d?<p className="text-xs">{q.isError?'Provider supervision status is unavailable.':'Loading provider supervision…'}</p>:<>
 <p className="text-xs">{d.enabled?'Online supervision enabled':'Online supervision disabled'} · {d.running?'Refreshing a source':'Waiting for the next scheduled source'} · Last check {date(d.last_check)}</p>
 <p className="text-xs text-text-secondary mt-2">{d.policy}</p>
 <div className="overflow-x-auto mt-3"><table className="w-full text-xs"><thead><tr><th>Source</th><th>Status</th><th>Last accepted</th><th>Coverage / review</th></tr></thead><tbody>{d.sources?.map((s:any)=><tr key={s.id}><td className="py-2 pr-3">{s.title}<p className="text-[10px] text-text-tertiary">{s.used_for}</p></td><td>{s.status?.replace(/_/g,' ')??'Awaiting first check'}</td><td className="font-mono whitespace-nowrap">{date(s.last_success)}</td><td>{s.quality?.series?`${s.quality.series} series · through ${s.quality.latest}`:s.quality?.quotes?`${s.quality.quotes} context quotes`:'Coverage pending'}{s.drift?.review_flag&&<p className="text-amber">Input shift requires review</p>}{s.error&&<p className="text-red">{s.error}</p>}</td></tr>)}</tbody></table></div>
 <p className="text-[11px] text-text-tertiary mt-3">{d.learning} No new provider subscription or entitlement is implied by these checks. The backend must remain running for scheduled updates.</p>
 </>}
 </Panel>;
}

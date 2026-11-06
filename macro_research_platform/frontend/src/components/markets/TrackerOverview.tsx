import { Activity, Clock, Globe2, Radio } from 'lucide-react';
export function TrackerOverview({kind, count, shown, time, now, warning, coverage}:{kind:'Aircraft'|'Vessels';count:number;shown:number;time?:number;now:number;warning?:string|null;coverage:string}) {
 const age=typeof time==='number' ? Math.max(0,now-time) : null;
 return <section className="rounded-xl border border-border bg-gradient-to-br from-surface-2 to-surface-1 p-4 space-y-3" aria-label={`${kind} observation quality`}>
   <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="text-[10px] uppercase tracking-[.18em] text-bloomberg">Physical economy · observed activity</div><h2 className="text-lg font-semibold text-text-primary mt-1">{kind==='Aircraft'?'Air traffic monitor':'Maritime activity monitor'}</h2></div>
     <span role="status" className={`rounded-full border px-3 py-1 text-[11px] ${warning?'border-amber text-amber':'border-border text-text-secondary'}`}>{warning || 'Receiver coverage is incomplete'}</span></div>
   <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[
    [Radio,'Valid positions',count.toLocaleString()], [Globe2,'Filtered in view',shown.toLocaleString()],
    [Clock,'Snapshot age',age==null?'Not supplied':age<120?`${Math.floor(age)}s`:`${Math.floor(age/60)}m`],
    [Activity,'Interpretation','Observed sample'],
   ].map(([Icon,label,value])=>{const I=Icon as typeof Radio;return <div key={String(label)} className="rounded-lg border border-border-subtle bg-surface-1/70 p-3"><div className="flex gap-1.5 items-center text-[10px] text-text-tertiary"><I className="w-3 h-3"/>{String(label)}</div><div className="font-mono text-sm mt-1 text-text-primary">{String(value)}</div></div>;})}</div>
   <p className="text-[11px] text-text-secondary leading-relaxed">{coverage}</p>
 </section>;
}

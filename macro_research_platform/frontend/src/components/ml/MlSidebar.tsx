import { Activity, BookOpen, FlaskConical, Gauge, Library, Network, Radar, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { pct } from '@/lib/format';
import { KNOWN_TASKS, ML_TABS, setMlTab, setMlTask, useMlTab, useMlTask, useTasks } from './mlShared';

const ICONS = { overview: Activity, lab: FlaskConical, visualizer: Network, explain: Sparkles, monitoring: Gauge, registry: Library, knowledge: Radar, method: BookOpen };

/** ML area navigation: its tabs, then every task with its current signal (click to open its network). */
export function MlSidebar({ collapsed = false }: { collapsed?: boolean }) {
  const tab = useMlTab();
  const sel = useMlTask();
  const { tasks } = useTasks();
  return (
    <nav aria-label="Machine learning" className="h-full overflow-y-auto py-3 space-y-1">
      {!collapsed && <div className="px-5 pb-2 text-[10px] uppercase tracking-[.12em] text-text-tertiary">Machine learning</div>}
      {ML_TABS.map((t) => { const Icon = ICONS[t.id]; return (
        <button key={t.id} aria-label={t.label} aria-current={tab === t.id ? 'page' : undefined} onClick={() => setMlTab(t.id)} title={t.desc}
          className={cn('mx-2 w-[calc(100%-1rem)] flex items-center gap-2.5 rounded-md px-3 py-2 text-left hover:bg-surface-3', tab === t.id && 'bg-surface-3 text-text-primary')}>
          <Icon className={cn('w-3.5 h-3.5 shrink-0', tab === t.id && 'text-bloomberg')} />{!collapsed && <span className="text-xs">{t.label}</span>}
        </button>); })}
      {!collapsed && <>
        <div className="px-5 pt-4 pb-1 text-[10px] uppercase tracking-[.12em] text-text-tertiary">Tasks</div>
        {(tasks?.length ? tasks : KNOWN_TASKS.map((k) => ({ ...k, ready: false }))).map((t: any) => (
          <button key={t.task} onClick={() => { setMlTask(t.task); if (tab === 'overview' || tab === 'knowledge' || tab === 'method' || tab === 'registry') setMlTab('lab'); }}
            className={cn('mx-2 w-[calc(100%-1rem)] flex items-center justify-between gap-2 rounded-md px-3 py-1.5 text-left hover:bg-surface-3', sel === t.task && 'bg-surface-3')}>
            <span className="text-[11px] truncate text-text-secondary">{t.title}</span>
            <span className="text-[11px] font-mono text-text-primary">{t.ready ? pct(t.signal.probability) : '—'}</span>
          </button>))}
      </>}
    </nav>
  );
}

import { BookMarked, Calculator, GitBranch, Layers, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PE_TABS,setPeTab,usePeTab } from './peShared';
const ICONS={workbench:Calculator,pipeline:GitBranch,precedents:BookMarked,waterfall:Layers,performance:TrendingUp};
/** Fund identity is supplied by the common shell, as in Markets and Macro. */
export function PeSidebar({ collapsed=false }: { collapsed?:boolean }) {
 const tab=usePeTab();
 return <nav aria-label="Private equity" className="h-full overflow-y-auto py-3 space-y-1">
  {!collapsed&&<div className="px-5 pb-2 text-[10px] uppercase tracking-[.12em] text-text-tertiary">Private equity</div>}
  {PE_TABS.map(t=>{const Icon=ICONS[t.id];return <button key={t.id} aria-label={t.label} aria-current={tab===t.id?'page':undefined} onClick={()=>setPeTab(t.id)} title={t.desc} className={cn('mx-2 w-[calc(100%-1rem)] flex items-center gap-2.5 rounded-md transition-colors',collapsed?'justify-center h-9':'px-3 py-2 text-left',tab===t.id?'bg-bloomberg/10 text-text-primary':'text-text-secondary hover:bg-text-primary/5 hover:text-text-primary')}>
   <Icon className={cn('w-3.5 h-3.5 shrink-0',tab===t.id&&'text-bloomberg')}/>{!collapsed&&<span className="min-w-0"><span className="block text-xs">{t.label}</span><span className="block text-[9px] leading-relaxed text-text-tertiary mt-1">{t.desc}</span></span>}
  </button>;})}
 </nav>;
}

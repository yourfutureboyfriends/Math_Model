// Workspace tabs above the dashboard: one navigation group at a time (or the role's focus
// set, or everything), plus fold/unfold for all visible panels. Keys: [ and ] cycle.

import { useEffect } from 'react';
import { ChevronsDownUp, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { WORKSPACES, setWorkspace, useWorkspace, workspacePanels } from '@/lib/focusMode';

interface Props {
  onCollapseAll: (collapse: boolean) => void;
  visibleCount: number;
}

export function WorkspaceBar({ onCollapseAll, visibleCount }: Props) {
  const ws = useWorkspace();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey || (e.key !== '[' && e.key !== ']')) return;
      e.preventDefault();
      const i = WORKSPACES.findIndex((w) => w.id === ws);
      const n = WORKSPACES.length;
      setWorkspace(WORKSPACES[(i + (e.key === ']' ? 1 : n - 1)) % n].id);
      window.scrollTo({ top: 0 });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ws]);

  return (
    <div className="sticky top-16 z-30 bg-bg/95 backdrop-blur border-b border-border-subtle px-4">
      <div className="flex items-center gap-1 h-9">
        <div role="tablist" aria-label="Workspaces" className="flex items-center gap-0.5 min-w-0 flex-1 overflow-x-auto [scrollbar-width:none]">
          {WORKSPACES.map((w) => {
            const active = w.id === ws;
            const count = workspacePanels(w.id)?.size;
            return (
              <button key={w.id} role="tab" aria-selected={active}
                onClick={() => { setWorkspace(w.id); window.scrollTo({ top: 0 }); }}
                className={cn(
                  'relative h-9 px-2.5 text-2xs font-mono uppercase tracking-wider whitespace-nowrap transition-colors',
                  active ? 'text-bloomberg' : 'text-text-tertiary hover:text-text-primary',
                )}>
                {w.label}
                {count !== undefined && <span className={cn('ml-1', active ? 'text-bloomberg/70' : 'text-text-tertiary/70')}>{count}</span>}
                {active && <span className="absolute left-2 right-2 bottom-0 h-0.5 bg-bloomberg" />}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-1 pl-2 shrink-0 border-l border-border-subtle">
          <span className="hidden xl:inline text-2xs text-text-tertiary font-mono mr-1" title="Press [ or ] to switch workspace">
            {visibleCount} panels · [ ]
          </span>
          <button onClick={() => onCollapseAll(true)} title="Collapse all panels" aria-label="Collapse all panels"
            className="p-1 text-text-tertiary hover:text-bloomberg"><ChevronsDownUp className="w-3.5 h-3.5" /></button>
          <button onClick={() => onCollapseAll(false)} title="Expand all panels" aria-label="Expand all panels"
            className="p-1 text-text-tertiary hover:text-bloomberg"><ChevronsUpDown className="w-3.5 h-3.5" /></button>
        </div>
      </div>
    </div>
  );
}

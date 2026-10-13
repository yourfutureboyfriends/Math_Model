// A collapsible "go deeper" block for the macro dashboard: mounts (and fetches) only when opened.
import { useState } from 'react';
import { ChevronDown, ChevronRight, BookOpen } from 'lucide-react';

export function ResearchExpander({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 border border-border-subtle rounded-md">
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-2xs text-left hover:bg-surface-2">
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}<BookOpen className="w-3 h-3 text-bloomberg" />
        <span className="text-text-primary font-semibold">{title}</span>{subtitle && <span className="text-text-tertiary">— {subtitle}</span>}
      </button>
      {open && <div className="p-3 border-t border-border-subtle">{children}</div>}
    </div>
  );
}

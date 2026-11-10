// "How to read this panel" card, opened by the "?" button DashboardPage adds to each panel
// header. Fixed-position next to the button, clamped to the viewport; closes on Escape,
// an outside click or scrolling.
import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { PANEL_HELP } from '@/lib/panelHelp';

export interface HelpAnchor { id: string; title: string; rect: { left: number; right: number; bottom: number; top: number } }

const WIDTH = 380;

export function PanelHelpPopover({ anchor, onClose }: { anchor: HelpAnchor; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const help = PANEL_HELP[anchor.id];

  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    const down = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      if (!ref.current?.contains(t) && !t.closest('[data-help-btn]')) onClose();
    };
    const scroll = (e: Event) => { if (!ref.current?.contains(e.target as Node)) onClose(); };
    document.addEventListener('keydown', key);
    document.addEventListener('mousedown', down);
    window.addEventListener('scroll', scroll, true);
    ref.current?.focus();
    return () => {
      document.removeEventListener('keydown', key);
      document.removeEventListener('mousedown', down);
      window.removeEventListener('scroll', scroll, true);
    };
  }, [onClose]);

  if (!help) return null;
  const vw = window.innerWidth, vh = window.innerHeight;
  const width = Math.min(WIDTH, vw - 32);
  const left = Math.max(16, Math.min(anchor.rect.right - width, vw - width - 16));
  const below = anchor.rect.bottom + 6;
  const style: React.CSSProperties = below + 260 < vh
    ? { left, top: below, width }
    : { left, bottom: Math.max(16, vh - anchor.rect.top + 6), width };

  return (
    <div ref={ref} role="dialog" aria-label={`About ${anchor.title}`} tabIndex={-1}
      className="fixed z-50 max-h-[70vh] overflow-y-auto bg-surface-2 border border-border shadow-xl p-3 text-xs text-text-secondary outline-none"
      style={style}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="text-sm font-semibold text-text-primary">{anchor.title}</div>
        <button type="button" onClick={onClose} aria-label="Close" className="text-text-tertiary hover:text-text-primary">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <Block label="What it shows">{help.what}</Block>
      <Block label="How to read it">{help.read}</Block>
      {help.use && <Block label="What to do with it">{help.use}</Block>}
      {help.terms && help.terms.length > 0 && (
        <div className="mt-2 pt-2 border-t border-border-subtle">
          <div className="text-2xs uppercase tracking-wider text-text-tertiary mb-1">Key terms</div>
          <dl className="space-y-1">
            {help.terms.map(([t, d]) => (
              <div key={t}><dt className="inline font-medium text-text-primary">{t}: </dt><dd className="inline">{d}</dd></div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-2">
      <div className="text-2xs uppercase tracking-wider text-text-tertiary mb-0.5">{label}</div>
      <p className="leading-relaxed">{children}</p>
    </div>
  );
}

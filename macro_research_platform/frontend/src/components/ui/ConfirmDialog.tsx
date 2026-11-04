/**
 * In-app confirmation (and optional single input) — replaces window.confirm / window.prompt, which some
 * embedded browsers and desktop shells suppress (returning false/null without showing anything, so the
 * action silently never happens).
 *
 *   const [dialog, ask] = useConfirm();
 *   if (!(await ask({ title: 'Delete “X”?', confirmLabel: 'Delete', danger: true }))) return;
 *   const cap = await ask({ title: 'Paper capital', input: { label: 'USD', defaultValue: '1000000', type: 'number' } });
 *   ...render {dialog} somewhere in the component.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

export interface AskOptions {
  title: string;
  body?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  input?: { label: string; defaultValue?: string; type?: 'text' | 'number' };
}

type Pending = { opts: AskOptions; resolve: (v: any) => void } | null;

export function useConfirm(): [JSX.Element | null, (o: AskOptions) => Promise<any>] {
  const [pending, setPending] = useState<Pending>(null);
  const ask = useCallback((opts: AskOptions) => new Promise<any>((resolve) => setPending({ opts, resolve })), []);
  const close = (v: any) => { pending?.resolve(v); setPending(null); };
  const dialog = pending ? <ConfirmDialog opts={pending.opts} onClose={close} /> : null;
  return [dialog, ask];
}

function ConfirmDialog({ opts, onClose }: { opts: AskOptions; onClose: (v: any) => void }) {
  const [value, setValue] = useState(opts.input?.defaultValue ?? '');
  const ok = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLInputElement>(null);
  useEffect(() => {
    (opts.input ? field.current : ok.current)?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(opts.input ? null : false); };
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  const confirm = () => onClose(opts.input ? value : true);
  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50" role="dialog" aria-modal="true" aria-label={opts.title}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(opts.input ? null : false); }}>
      <div className="w-[min(92vw,440px)] bg-surface-1 border border-border shadow-xl p-4 space-y-3">
        <div className="text-sm font-semibold text-text-primary">{opts.title}</div>
        {opts.body && <div className="text-xs text-text-secondary leading-relaxed whitespace-pre-line">{opts.body}</div>}
        {opts.input && (
          <label className="block text-2xs">
            <span className="block text-[10px] uppercase tracking-wide text-text-tertiary mb-0.5">{opts.input.label}</span>
            <input ref={field} type={opts.input.type ?? 'text'} value={value} onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') confirm(); }}
              className="w-full bg-surface-2 border border-border px-2 py-1 text-xs font-mono text-text-primary focus:border-bloomberg outline-none" />
          </label>)}
        <div className="flex justify-end gap-2">
          <button onClick={() => onClose(opts.input ? null : false)} className="px-3 py-1 text-2xs border border-border text-text-secondary hover:text-text-primary">
            {opts.cancelLabel ?? 'Cancel'}</button>
          <button ref={ok} onClick={confirm}
            className={cn('px-3 py-1 text-2xs', opts.danger ? 'bg-red text-white' : 'bg-bloomberg text-bg')}>{opts.confirmLabel ?? 'OK'}</button>
        </div>
      </div>
    </div>
  );
}

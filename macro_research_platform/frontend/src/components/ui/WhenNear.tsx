// Mounts its children only once they come within ~1.5 screens of the viewport, then keeps them mounted.
// The research dashboard has ~130 panels: mounting them all at once fires hundreds of requests through the browser's
// six connections per host, so the slow ones queue everything else (panels looked "disconnected"). Deferred, a panel
// asks for its data when you are about to see it. Printing or a missing IntersectionObserver mounts at once.
import { useEffect, useRef, useState, type ReactNode } from 'react';

/** Ask the panel holding element `id` (or every panel, with '*') to mount now — the sidebar does this before it
 *  scrolls to a panel whose anchor lives inside the panel's own component. */
export function revealNear(id: string) { window.dispatchEvent(new CustomEvent('whennear:reveal', { detail: id })); }

export function WhenNear({ children, minHeight = 220, ids }: { children: ReactNode; minHeight?: number; ids?: string[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(() => typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    if (near || !ref.current) return;
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) setNear(true); }, { rootMargin: '1400px 0px' });
    io.observe(ref.current);
    const onPrint = () => setNear(true);
    const onReveal = (e: Event) => { const id = (e as CustomEvent).detail; if (id === '*' || ids?.includes(id)) setNear(true); };
    window.addEventListener('beforeprint', onPrint);
    window.addEventListener('whennear:reveal', onReveal);
    return () => { io.disconnect(); window.removeEventListener('beforeprint', onPrint); window.removeEventListener('whennear:reveal', onReveal); };
  }, [near, ids]);
  if (near) return <>{children}</>;
  return <div ref={ref} style={{ minHeight }} className="mkt-skeleton opacity-40 m-3 rounded-lg" aria-hidden />;
}

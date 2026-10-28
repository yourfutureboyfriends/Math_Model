// A number that moves: when the value changes it glides to the new figure (≈350 ms, eased) and flashes green or red
// for the direction of the move. Formatting stays the caller's; reduced-motion users get the plain swap.
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export function LiveNumber({ value, format, className, tween = true }: {
  value: number | null | undefined; format: (v: number) => string; className?: string; tween?: boolean;
}) {
  const [shown, setShown] = useState<number | null | undefined>(value);
  const [flash, setFlash] = useState('');
  const from = useRef(value);
  useEffect(() => {
    const a = from.current, b = value;
    from.current = value;
    if (a == null || b == null || a === b) { setShown(b); return; }
    setFlash(b > a ? 'num-up' : 'num-down');
    const off = setTimeout(() => setFlash(''), 900);
    if (!tween || reduced()) { setShown(b); return () => clearTimeout(off); }
    let raf = 0; const t0 = performance.now();
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / 350), e = 1 - (1 - k) ** 3;
      setShown(k < 1 ? a + (b - a) * e : b);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => { cancelAnimationFrame(raf); clearTimeout(off); };
  }, [value, tween]);
  return <span className={cn('live-num', flash, className)}>{shown == null ? '—' : format(shown)}</span>;
}

// Macro Terminal mark: a dark tile holding the growth × inflation regime map. A rising "cycle" curve runs to the
// quadrant of the current regime, which glows in that regime's colour — the platform's whole idea in one icon.
// The mark keeps its own fixed colours (dark tile, a cool-to-warm cycle curve) so it reads as the platform's icon in
// either theme and under any fund's brand accent.

import { useId } from 'react';
import { cn } from '@/lib/utils';

interface LogoProps {
  currentRegime?: string | null;
  className?: string;
  size?: number;
}

// quadrant centres (viewBox 32): growth left→right, inflation bottom→top
const QUAD: Record<string, { x: number; y: number; color: string; label: string }> = {
  goldilocks: { x: 22, y: 21.5, color: 'var(--green)', label: 'Goldilocks' },      // growth up, inflation down
  reflation: { x: 22, y: 10.5, color: 'var(--amber)', label: 'Reflation' },        // growth up, inflation up
  stagflation: { x: 10, y: 10.5, color: 'var(--red)', label: 'Stagflation' },      // growth down, inflation up
  slowdown: { x: 10, y: 21.5, color: 'var(--blue)', label: 'Slowdown' },          // growth down, inflation down
};

function regimeOf(raw?: string | null) {
  const r = (raw ?? '').toLowerCase();
  const k = Object.keys(QUAD).find((q) => r.includes(q)) ?? (r.includes('deflat') ? 'slowdown' : null);
  return k ? QUAD[k] : null;
}

export function Logo({ currentRegime, className, size = 24 }: LogoProps) {
  const id = useId().replace(/:/g, '');
  const q = regimeOf(currentRegime);
  const end = q ?? { x: 22, y: 10.5, color: '#fbbf24', label: '' };
  // the cycle: from the lower-left of the map, a smooth S up to the active quadrant
  const d = `M6.5 24.5 C 11 24.5, 12.5 ${end.y + 6}, 16 ${(end.y + 16) / 2} S ${end.x - 3.5} ${end.y}, ${end.x} ${end.y}`;
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} fill="none" className={cn('shrink-0', className)}
      role="img" aria-label={q ? `Macro Terminal — current regime: ${q.label}` : 'Macro Terminal'}>
      <defs>
        <linearGradient id={`${id}t`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1c2533" /><stop offset="1" stopColor="#0b1018" />
        </linearGradient>
        <linearGradient id={`${id}c`} x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#38bdf8" />
          <stop offset="0.55" stopColor="#a78bfa" />
          <stop offset="1" stopColor="#fb923c" />
        </linearGradient>
        <radialGradient id={`${id}g`}>
          <stop offset="0" stopColor={end.color} stopOpacity="0.55" /><stop offset="1" stopColor={end.color} stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill={`url(#${id}t)`} />
      <rect x="1.5" y="1.5" width="29" height="29" rx="7.5" stroke="#ffffff" strokeOpacity="0.16" />
      {/* the regime map: growth (x) and inflation (y) axes */}
      <path d="M16 6.5v19M6.5 16h19" stroke="#ffffff" strokeOpacity="0.14" strokeWidth="1" strokeLinecap="round" />
      <path d={d} stroke={`url(#${id}c)`} strokeWidth="2.5" strokeLinecap="round" />
      <circle cx={end.x} cy={end.y} r="5.5" fill={`url(#${id}g)`} />
      <circle cx={end.x} cy={end.y} r="2.6" fill={end.color} stroke="#0b1018" strokeWidth="1.2" />
    </svg>
  );
}

/** The platform name set beside the mark: MACRO bold, TERMINAL light, tracked out. */
export function Wordmark({ className, size = 'sm', version }: { className?: string; size?: 'sm' | 'lg'; version?: string }) {
  return (
    <span className={cn('inline-flex items-baseline leading-none select-none', size === 'lg' ? 'text-[22px] tracking-[0.2em]' : 'text-[12px] tracking-[0.18em]', className)}>
      <span className="font-semibold text-text-primary">MACRO</span>
      <span className="ml-[0.35em] font-light text-text-secondary">TERMINAL</span>
      {version && <span className="ml-2 tracking-normal text-[10px] text-text-tertiary font-mono">{version}</span>}
    </span>
  );
}

// Logo component — Bridgewater 2×2 regime matrix
// Updates active regime indicator based on current regime

import { cn } from '@/lib/utils';

interface LogoProps {
  currentRegime?: string;
  className?: string;
}

export function Logo({ currentRegime = 'stagflation', className }: LogoProps) {
  // Map regime to quadrant position
  // Top-left (8,8): Goldilocks
  // Top-right (24,8): Reflation
  // Bottom-left (8,24): Slowdown
  // Bottom-right (24,24): Stagflation
  const getActivePosition = (regime: string) => {
    const normalized = regime.toLowerCase();
    if (normalized.includes('goldilocks')) return { cx: 8, cy: 8 };
    if (normalized.includes('reflation')) return { cx: 24, cy: 8 };
    if (normalized.includes('slowdown')) return { cx: 8, cy: 24 };
    // Default: Stagflation (bottom-right)
    return { cx: 24, cy: 24 };
  };

  const activePos = getActivePosition(currentRegime);

  return (
    <svg
      viewBox="0 0 32 32"
      width="24"
      height="24"
      fill="none"
      aria-label="Macro OS"
      className={cn("text-text-secondary", className)}
    >
      {/* Outer square frame */}
      <rect
        x="1"
        y="1"
        width="30"
        height="30"
        stroke="currentColor"
        strokeWidth="1.5"
        fill="none"
      />

      {/* Inner diagonal cross — regime axes */}
      <line
        x1="1"
        y1="16"
        x2="31"
        y2="16"
        stroke="var(--accent)"
        strokeWidth="1"
      />
      <line
        x1="16"
        y1="1"
        x2="16"
        y2="31"
        stroke="var(--accent)"
        strokeWidth="1"
      />

      {/* Regime quadrant dots (Bridgewater 2×2) */}
      {/* Top-left: Goldilocks */}
      <circle cx="8" cy="8" r="2" fill="var(--green)" />
      {/* Top-right: Reflation */}
      <circle cx="24" cy="8" r="2" fill="var(--amber)" />
      {/* Bottom-left: Slowdown */}
      <circle cx="8" cy="24" r="2" fill="var(--blue)" />
      {/* Bottom-right: Stagflation */}
      <circle cx="24" cy="24" r="2" fill="var(--red)" />

      {/* Active regime indicator circle */}
      <circle
        cx={activePos.cx}
        cy={activePos.cy}
        r="4"
        fill="none"
        stroke={
          currentRegime.includes('goldilocks') ? 'var(--green)' :
          currentRegime.includes('reflation') ? 'var(--amber)' :
          currentRegime.includes('slowdown') ? 'var(--blue)' :
          'var(--red)'
        }
        strokeWidth="1"
      />
    </svg>
  );
}

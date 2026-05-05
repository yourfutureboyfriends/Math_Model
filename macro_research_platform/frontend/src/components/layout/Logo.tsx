// Logo component — Bridgewater 2×2 regime matrix
// Updates active regime indicator based on current regime

import { cn } from '@/lib/utils';

interface LogoProps {
  currentRegime?: string | null;
  className?: string;
}

export function Logo({ currentRegime: rawRegime, className }: LogoProps) {
  // Backend can return null before the regime engine runs — normalise to a safe default.
  const currentRegime = (rawRegime ?? 'stagflation').toLowerCase();

  // Map regime to quadrant position
  // Top-left (8,8): Goldilocks  Top-right (24,8): Reflation
  // Bottom-left (8,24): Slowdown  Bottom-right (24,24): Stagflation
  const getActivePosition = () => {
    if (currentRegime.includes('goldilocks')) return { cx: 8, cy: 8 };
    if (currentRegime.includes('reflation'))  return { cx: 24, cy: 8 };
    if (currentRegime.includes('slowdown'))   return { cx: 8, cy: 24 };
    return { cx: 24, cy: 24 }; // stagflation / unknown
  };

  const activePos = getActivePosition();
  const strokeColor =
    currentRegime.includes('goldilocks') ? 'var(--green)'  :
    currentRegime.includes('reflation')  ? 'var(--amber)'  :
    currentRegime.includes('slowdown')   ? 'var(--blue)'   :
    'var(--red)';

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
      <rect x="1" y="1" width="30" height="30" stroke="currentColor" strokeWidth="1.5" fill="none" />

      {/* Regime axes */}
      <line x1="1"  y1="16" x2="31" y2="16" stroke="var(--accent)" strokeWidth="1" />
      <line x1="16" y1="1"  x2="16" y2="31" stroke="var(--accent)" strokeWidth="1" />

      {/* Quadrant dots */}
      <circle cx="8"  cy="8"  r="2" fill="var(--green)" />   {/* Goldilocks */}
      <circle cx="24" cy="8"  r="2" fill="var(--amber)" />   {/* Reflation  */}
      <circle cx="8"  cy="24" r="2" fill="var(--blue)"  />   {/* Slowdown   */}
      <circle cx="24" cy="24" r="2" fill="var(--red)"   />   {/* Stagflation*/}

      {/* Active regime indicator */}
      <circle cx={activePos.cx} cy={activePos.cy} r="4" fill="none" stroke={strokeColor} strokeWidth="1" />
    </svg>
  );
}

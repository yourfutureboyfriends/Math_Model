/** Drift bullet: an input's recent shift in standard deviations against the ±1.5 alarm band (a table cell). */
export function DriftBullet({ shift, outside }: { shift: number; outside: boolean }) {
  const c = (v: number) => 50 + (Math.max(-3, Math.min(3, v)) / 3) * 48;              // % across the cell
  const bad = outside || Math.abs(shift) > 1.5;
  return (
    <span className="relative inline-block w-40 h-4 align-middle" role="img" aria-label={`shift ${shift} standard deviations`}>
      <span className="absolute top-1 bottom-1 bg-[var(--viz-outcome)] rounded-sm" style={{ left: `${c(-1.5)}%`, width: `${c(1.5) - c(-1.5)}%` }} />
      <span className="absolute top-0.5 bottom-0.5 w-px bg-border" style={{ left: '50%' }} />
      <span className="absolute top-1.5 h-1 rounded-full" style={{ left: `${Math.min(50, c(shift))}%`, width: `${Math.max(0.6, Math.abs(c(shift) - 50))}%`,
        background: bad ? 'rgb(var(--c-amber))' : 'var(--viz-1)' }} />
    </span>
  );
}

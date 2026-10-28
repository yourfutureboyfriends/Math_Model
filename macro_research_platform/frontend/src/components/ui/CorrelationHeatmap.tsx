/**
 * CorrelationHeatmap — reusable cross-asset correlation matrix (Phase 4).
 *
 * Diverging encoding: deep orange = strong negative, neutral surface = ~0, deep blue =
 * strong positive. Blue/orange rather than green/red: correlation is not good/bad, and the
 * pair stays distinct under red-green colour blindness. The coefficient is printed in every cell, so identity is never
 * color-alone (CVD-safe). Flat cells only — no gradients/shadows (terminal aesthetic).
 *
 * Pure presentational primitive: parent supplies labels + matrix and handles fetching.
 */
interface CorrelationHeatmapProps {
  labels: string[];
  matrix: (number | null)[][];
  onCellClick?: (a: string, b: string, value: number | null) => void;
  selected?: { a: string; b: string } | null;
}

// Diverging color: orange (neg) ↔ transparent surface (0) ↔ blue (pos), alpha ∝ |r|.
function cellBg(v: number | null): string {
  if (v === null || Number.isNaN(v)) return 'transparent';
  const a = Math.min(Math.abs(v), 1) * 0.85;
  return v >= 0 ? `rgba(57, 135, 229, ${a})` : `rgba(217, 89, 38, ${a})`;
}
// Plain-English reading for the hover tooltip.
function describe(v: number | null): string {
  if (v === null || Number.isNaN(v)) return 'no data';
  const m = Math.abs(v);
  const strength = m >= 0.7 ? 'strongly' : m >= 0.4 ? 'moderately' : m >= 0.2 ? 'weakly' : null;
  if (!strength) return 'largely unrelated';
  return v > 0 ? `move together ${strength}` : `move ${strength} in opposite directions (a hedge)`;
}
// Keep the number legible on both dark surface and saturated cells.
function cellFg(v: number | null): string {
  if (v === null) return 'var(--text-tertiary)';
  return Math.abs(v) > 0.45 ? '#0a0e14' : 'var(--text-secondary)';
}

export function CorrelationHeatmap({ labels, matrix, onCellClick, selected }: CorrelationHeatmapProps) {
  if (!labels.length || !matrix.length) {
    return <div className="text-2xs text-text-tertiary p-3">No correlation data.</div>;
  }
  const cols = `56px repeat(${labels.length}, minmax(30px, 1fr))`;

  return (
    <div className="overflow-x-auto">
      <div className="inline-block min-w-full">
        {/* Header row */}
        <div className="grid gap-px" style={{ gridTemplateColumns: cols }}>
          <div />
          {labels.map((l) => (
            <div key={l} className="text-2xs font-mono text-text-tertiary text-center py-1 uppercase tracking-wider">{l}</div>
          ))}
        </div>
        {/* Matrix rows */}
        {matrix.map((row, i) => (
          <div key={labels[i]} className="grid gap-px" style={{ gridTemplateColumns: cols }}>
            <div className="text-2xs font-mono text-text-tertiary flex items-center justify-end pr-2 uppercase tracking-wider">{labels[i]}</div>
            {row.map((v, j) => {
              const isSel = selected && ((selected.a === labels[i] && selected.b === labels[j]) || (selected.a === labels[j] && selected.b === labels[i]));
              const diagonal = i === j;
              return (
                <button
                  key={j}
                  onClick={() => !diagonal && onCellClick?.(labels[i], labels[j], v)}
                  title={`${labels[i]} vs ${labels[j]}: ${v === null ? 'n/a' : (v > 0 ? '+' : '') + v.toFixed(2)} — ${describe(v)}`}
                  className={`h-8 flex items-center justify-center text-2xs font-mono tabular-nums transition-none ${diagonal ? 'opacity-40' : 'cursor-pointer'} ${isSel ? 'ring-1 ring-bloomberg z-10' : ''}`}
                  style={{ background: diagonal ? 'var(--surface-3)' : cellBg(v), color: cellFg(v) }}
                >
                  {v === null ? '·' : v.toFixed(2)}
                </button>
              );
            })}
          </div>
        ))}
        {/* Diverging legend */}
        <div className="flex items-center gap-2 mt-3 text-2xs text-text-tertiary">
          <span>−1.0</span>
          <div className="flex h-2 w-40">
            {Array.from({ length: 20 }).map((_, k) => {
              const val = -1 + (k / 19) * 2;
              return <div key={k} className="flex-1" style={{ background: cellBg(Math.round(val * 100) / 100) || 'var(--surface-3)' }} />;
            })}
          </div>
          <span>+1.0</span>
          <span className="ml-2">orange = move opposite (diversifies) · blue = move together · hover a cell for detail</span>
        </div>
      </div>
    </div>
  );
}

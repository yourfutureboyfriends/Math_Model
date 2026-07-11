// Factor Rotation Section — regime-tilted factor composite scores.
//
// Renders the real factorRotation payload the dashboard provides: four factor composite
// scores (Momentum / Value / Growth / Quality, each 0–1, derived from the live growth /
// inflation / recession signals), plus the regime interpretation and the rotation signal.
import { cn } from '@/lib/utils';
import { TrendingUp } from 'lucide-react';
import { useMacroStore } from '@/store/macroStore';

interface FactorScore {
  momentum?: number;
  value?: number;
  growth?: number;
  quality?: number;
  interpretation?: string;
  rotationSignal?: string;
}

const FACTOR_META: { key: keyof FactorScore; label: string; ticker: string }[] = [
  { key: 'momentum', label: 'Momentum', ticker: 'MTUM' },
  { key: 'value', label: 'Value', ticker: 'VLUE' },
  { key: 'growth', label: 'Growth', ticker: 'IWF' },
  { key: 'quality', label: 'Quality', ticker: 'QUAL' },
];

function barColor(score: number) {
  if (score >= 0.66) return 'bg-green';
  if (score >= 0.5) return 'bg-bloomberg';
  if (score >= 0.34) return 'bg-amber';
  return 'bg-red';
}

function signalTag(score: number) {
  if (score >= 0.66) return { label: 'OVERWEIGHT', cls: 'text-green' };
  if (score >= 0.5) return { label: 'SL OVERWEIGHT', cls: 'text-bloomberg' };
  if (score >= 0.34) return { label: 'NEUTRAL', cls: 'text-text-secondary' };
  return { label: 'UNDERWEIGHT', cls: 'text-red' };
}

export function FactorRotationSection({ data: dataProp }: { data?: FactorScore }) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  const data: FactorScore | undefined = dataProp ?? (_fullDash as any)?.factorRotation;

  const scores = FACTOR_META
    .map((m) => ({ ...m, score: typeof data?.[m.key] === 'number' ? (data[m.key] as number) : null }))
    .filter((s) => s.score !== null) as { key: string; label: string; ticker: string; score: number }[];

  return (
    <div id="factor-rotation" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><TrendingUp className="w-3 h-3" /></span>
          <h2 className="section-title">Factor Rotation</h2>
          {data?.rotationSignal && (
            <span className="section-meta">tilt: <span className="text-bloomberg font-mono">{data.rotationSignal}</span></span>
          )}
        </div>
      </div>

      {scores.length === 0 ? (
        <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">
          Unavailable — factor rotation scores not present in the current dashboard payload.
        </div>
      ) : (
        <div className="space-y-3">
          {data?.interpretation && (
            <div className="text-2xs text-text-secondary">{data.interpretation}</div>
          )}
          <div className="space-y-2">
            {scores
              .slice()
              .sort((a, b) => b.score - a.score)
              .map((f) => {
                const tag = signalTag(f.score);
                return (
                  <div key={f.key} className="flex items-center gap-2 text-xs">
                    <span className="w-24 shrink-0">
                      <span className="font-mono font-bold text-text-primary">{f.ticker}</span>
                      <span className="text-2xs text-text-tertiary ml-1">{f.label}</span>
                    </span>
                    <div className="flex-1 h-2.5 bg-surface-3">
                      <div className={cn('h-2.5', barColor(f.score))} style={{ width: `${Math.round(f.score * 100)}%` }} />
                    </div>
                    <span className="w-10 text-right font-mono tabular-nums text-text-primary">{f.score.toFixed(2)}</span>
                    <span className={cn('w-28 text-right text-2xs font-medium', tag.cls)}>{tag.label}</span>
                  </div>
                );
              })}
          </div>
          <div className="text-2xs text-text-tertiary">
            Composite factor scores (0–1) tilted by the current regime; higher = favored. Rotation
            signal names the leading factor bias.
          </div>
        </div>
      )}
    </div>
  );
}

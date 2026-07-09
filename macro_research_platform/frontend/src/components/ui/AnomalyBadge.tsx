/**
 * AnomalyBadge — reusable flag for a metric outside its normal historical range (Phase 3).
 *
 * Shows the z-score with a σ suffix. Amber when |z| > 2 (anomalous), muted otherwise.
 * Color is paired with an icon + numeric label, never color-alone. Use on any metric card.
 */
import { AlertTriangle } from 'lucide-react';

interface AnomalyBadgeProps {
  zScore: number | null | undefined;
  isAnomalous?: boolean;
  /** compact = just "2.1σ"; full = "⚠ OUTSIDE NORMAL RANGE" */
  variant?: 'compact' | 'full';
}

export function AnomalyBadge({ zScore, isAnomalous, variant = 'compact' }: AnomalyBadgeProps) {
  if (zScore === null || zScore === undefined) return null;
  const flagged = isAnomalous ?? Math.abs(zScore) > 2;
  const tone = flagged ? 'text-amber border-amber/40 bg-amber-dim' : 'text-text-tertiary border-border';
  const sigma = `${zScore >= 0 ? '+' : ''}${zScore.toFixed(1)}σ`;

  if (variant === 'full' && flagged) {
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-2xs font-mono border ${tone} uppercase tracking-wider`}>
        <AlertTriangle className="w-3 h-3" /> Outside normal range · {sigma}
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-2xs font-mono border ${tone}`}
      title={flagged ? `Outside 2σ historical range (${sigma})` : `Within normal range (${sigma})`}>
      {flagged && <AlertTriangle className="w-3 h-3" />} {sigma}
    </span>
  );
}

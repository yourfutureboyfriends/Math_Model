// Phase 8 — Regime Classification Section (Redesigned) + Phase 1E Store Integration
// Dense panel using macroStore for live regime data

import { cn } from '@/lib/utils';
import { ComputedTag } from '@/components/ui/ComputedTag';
import { AnimatedValue, SkeletonCard } from '@/components/ui';
import { useMacroStore } from '@/store/macroStore';
import { fmtRegime, fmtProbability, fmtDuration } from '@/utils/format';
import type { RegimeData } from '@/types';

interface RegimeSectionProps {
  data?: RegimeData;
}

export function RegimeSection({ data }: RegimeSectionProps) {
  // Use macro store for live regime data
  const regime = useMacroStore((state) => state.regime);
  const isLoading = useMacroStore((state) => state.meta.dataStatus === 'loading');

  if (isLoading && !data) {
    return (
      <div id="regime" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">◆</span>
            <h2 className="section-title">Regime Classification</h2>
          </div>
        </div>
        <SkeletonCard />
      </div>
    );
  }

  // Prioritize store data, fallback to props
  const currentRegime = regime.current || data?.current;

  // Normalize confidence to a 0-100 percentage (handles string, null, undefined).
  // The store holds regime.confidence as a 0-1 fraction (e.g. 0.762); this component
  // treats confidence as a 0-100 percentage (width %, /100 for fmtProbability). Without
  // rescaling, 0.762 rendered as "1% CONFIDENCE" instead of 76%.
  const rawConfidence = regime.confidence ?? data?.confidenceScore ?? null;
  let confidence = typeof rawConfidence === 'number' ? rawConfidence
    : typeof rawConfidence === 'string' ? parseFloat(rawConfidence) || null
    : null;
  if (confidence !== null && confidence > 0 && confidence <= 1) {
    confidence = confidence * 100;  // fraction -> percentage
  }

  const duration = regime.duration || data?.duration;

  if (!currentRegime) {
    return (
      <div id="regime" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">◆</span>
            <h2 className="section-title">Regime Classification</h2>
          </div>
        </div>
        <div className="p-8 bg-surface-1 border border-border text-center text-text-secondary">
          No regime data available
        </div>
      </div>
    );
  }

  const getRegimeColor = (regimeName: string) => {
    const normalized = regimeName.toLowerCase();
    if (normalized.includes('goldilocks') || normalized.includes('risk-on')) return 'text-green';
    if (normalized.includes('reflation') || normalized.includes('recovery')) return 'text-blue';
    if (normalized.includes('slowdown')) return 'text-amber';
    if (normalized.includes('stagflation') || normalized.includes('risk-off')) return 'text-red';
    return 'text-text-primary';
  };

  const getRegimeBg = (regimeName: string) => {
    const normalized = regimeName.toLowerCase();
    if (normalized.includes('goldilocks') || normalized.includes('risk-on')) return 'bg-green-dim border-green';
    if (normalized.includes('reflation') || normalized.includes('recovery')) return 'bg-blue-dim border-blue';
    if (normalized.includes('slowdown')) return 'bg-amber-dim border-amber';
    if (normalized.includes('stagflation') || normalized.includes('risk-off')) return 'bg-red-dim border-red';
    return 'bg-surface-2 border-border';
  };

  const getConfidenceBadge = (conf: string | number | null) => {
    const confStr = typeof conf === 'number' ? (conf > 70 ? 'high' : conf > 40 ? 'medium' : 'low') : String(conf).toLowerCase();
    switch (confStr) {
      case 'high':
        return 'signal-tag bullish';
      case 'medium':
        return 'signal-tag warning';
      case 'low':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  return (
    <div id="regime" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Regime Classification</h2>
          <span className="section-meta">
            {fmtRegime(currentRegime).toUpperCase()} · {confidence ? fmtProbability(confidence / 100) : '—'} CONFIDENCE
          </span>
        </div>
        <ComputedTag section="regime" />
      </div>

      <div className="space-y-3">
        {/* Current Regime Card */}
        <div className={cn('p-3 border', getRegimeBg(currentRegime))}>
          <div className="flex items-center justify-between mb-2">
            <div>
              <div className="text-2xs text-text-secondary uppercase tracking-wider mb-0.5">
                Current Regime
              </div>
              <div className={cn('text-lg font-mono font-bold', getRegimeColor(currentRegime))}>
                {fmtRegime(currentRegime)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-2xs text-text-secondary uppercase tracking-wider mb-0.5">
                Duration
              </div>
              <div className="text-sm font-mono text-text-primary">
                {duration ? fmtDuration(duration) : '—'}
              </div>
            </div>
          </div>

          {/* Confidence Score Bar */}
          {confidence && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-2xs mb-1">
                <span className="text-text-tertiary">Confidence</span>
                <span className="font-mono text-text-primary">{fmtProbability(confidence / 100)}</span>
              </div>
              <div className="h-1 bg-surface-4">
                <div
                  className="h-full bg-bloomberg transition-all duration-500"
                  style={{ width: `${Math.min(100, confidence)}%` }}
                />
              </div>
              <div className="text-right mt-1">
                <span className="font-mono text-xs text-bloomberg">
                  <AnimatedValue value={confidence} decimals={0} suffix="%" />
                </span>
              </div>
            </div>
          )}

          {/* Regime Probabilities from Store */}
          {regime.probabilities && (
            <div className="mt-3 pt-3 border-t border-border-subtle">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Probabilities</div>
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(regime.probabilities).map(([key, prob]) => (
                  prob !== null && (
                    <div key={key} className="flex items-center justify-between">
                      <span className="text-xs text-text-secondary capitalize">{key}</span>
                      <span className="font-mono text-xs text-text-primary">{fmtProbability(prob)}</span>
                    </div>
                  )
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Factor Impacts Table */}
        {data?.interpretations && data.interpretations.length > 0 && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-2 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Factor Impacts</span>
            </div>
            <table className="w-full">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left py-1.5 px-3 text-2xs text-text-tertiary uppercase font-medium">Factor</th>
                  <th className="text-left py-1.5 px-3 text-2xs text-text-tertiary uppercase font-medium">Impact</th>
                  <th className="text-right py-1.5 px-3 text-2xs text-text-tertiary uppercase font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {(data.interpretations ?? []).map((interp) => (
                  <tr key={interp.factor} className="border-b border-border-subtle last:border-0">
                    <td className="py-2 px-3 text-sm text-text-primary">{interp.factor}</td>
                    <td className="py-2 px-3 text-sm text-text-secondary">{interp.impact}</td>
                    <td className="py-2 px-3 text-right">
                      <span className={getConfidenceBadge(interp.color === 'success' ? 'High' : interp.color === 'warning' ? 'Medium' : 'Low')}>
                        {interp.color === 'success' ? 'UP' : interp.color === 'danger' ? 'DOWN' : 'NEUTRAL'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Regime History */}
        {data?.history && data.history.length > 0 && (
          <div className="p-3 border border-border bg-surface-1">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">History</div>
            <div className="flex flex-wrap gap-1">
              {data.history.slice(-6).map((h, idx) => {
                const regimeColor = getRegimeColor(h.regime);
                const fmtRegimeDate = (d: string) => d.split('T')[0];
                const fmtRegimeName = (r: string) => {
                  const names: Record<string, string> = {
                    'Goldilocks': 'Goldilocks',
                    'Reflation': 'Reflation',
                    'Stagflation': 'Stagflation',
                    'Slowdown': 'Slowdown',
                    'Slow': 'Slowdown',
                  };
                  return names[r] || r;
                };
                return (
                  <div
                    key={idx}
                    className={cn(
                      'px-2 py-1 text-2xs font-mono',
                      regimeColor === 'text-green' ? 'text-green bg-green-dim' :
                      regimeColor === 'text-amber' ? 'text-amber bg-amber-dim' :
                      regimeColor === 'text-red' ? 'text-red bg-red-dim' :
                      regimeColor === 'text-blue' ? 'text-blue bg-blue-dim' :
                      'text-text-secondary bg-surface-2'
                    )}
                    title={`${h.date}: ${h.regime}`}
                  >
                    {fmtRegimeDate(h.date)}: {fmtRegimeName(h.regime)}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

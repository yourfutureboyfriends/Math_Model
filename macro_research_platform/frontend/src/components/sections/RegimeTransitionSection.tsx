// Phase 8 — Regime Transition Matrix Section (Redesigned)
// Historical regime transition analysis with terminal aesthetic

import { Shuffle, ArrowRight, BarChart3, Target } from 'lucide-react';

interface RegimeTransitionSectionProps {
  data?: any;
}

export function RegimeTransitionSection({ data }: RegimeTransitionSectionProps) {
  if (!data) return null;

  const currentRegime = data.currentRegime || 'Unknown';
  const mostLikelyNext = data.mostLikelyNext || 'Unknown';
  const nextRegimeProbability = data.nextRegimeProbability || 0;
  const secondMostLikely = data.secondMostLikely || 'Unknown';
  const warning = data.warning || '';

  // Handle transitions as object (new format) or array (old format)
  const transitionsData = data.transitions || {};
  const isObjectFormat = !Array.isArray(transitionsData);

  // Convert object format to array
  let fromCurrent: any[] = [];
  if (isObjectFormat && transitionsData[currentRegime]) {
    const currentTransitions = transitionsData[currentRegime];
    fromCurrent = Object.entries(currentTransitions).map(([toRegime, probability]: [string, any]) => ({
      toRegime,
      fromRegime: currentRegime,
      probability: typeof probability === 'number' ? probability : 0,
      avgReturn: 0,
      volatility: 0.15,
      sharpe: 0,
      maxDrawdown: -0.1,
      winRate: 0.5
    }));
  } else if (Array.isArray(transitionsData)) {
    fromCurrent = transitionsData.filter((t: any) => t.fromRegime === currentRegime);
  }

  return (
    <div id="regime-transition" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">25</span>
          <h2 className="section-title">Regime Transition</h2>
          <span className="section-meta">{currentRegime}</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Current State Header */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shuffle className="w-3 h-3 text-text-secondary" />
              <div>
                <div className="text-2xs text-text-tertiary uppercase tracking-wider">
                  Current Regime
                </div>
                <div className="text-lg font-bold text-text-primary">
                  {currentRegime}
                </div>
              </div>
            </div>

            <div className="text-right">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-0.5">
                Most Likely Next
              </div>
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-bloomberg">
                  {mostLikelyNext}
                </span>
                <ArrowRight className="w-3 h-3 text-text-tertiary" />
              </div>
            </div>
          </div>
        </div>

        {/* Warning if present */}
        {warning && (
          <div className="p-2 bg-amber-dim border border-amber text-xs text-amber">
            {warning}
          </div>
        )}

        {/* Transition Probability Bars */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2 flex items-center gap-2">
            <Target className="w-3 h-3" />
            From {currentRegime}
          </div>
          <div className="space-y-2">
            {fromCurrent
              .sort((a: any, b: any) => b.probability - a.probability)
              .map((t: any) => (
                <div key={t.toRegime} className="flex items-center justify-between text-sm">
                  <span className="text-text-primary text-xs">
                    → {t.toRegime}
                  </span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-1 bg-surface-4">
                      <div
                        className="h-full bg-bloomberg"
                        style={{ width: `${t.probability * 100}%` }}
                      />
                    </div>
                    <span className="font-mono text-xs w-10 text-right">
                      {(t.probability * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* Transition Stats */}
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
              Next Regime Probability
            </div>
            <div className="text-2xl font-mono font-bold text-bloomberg">
              {(nextRegimeProbability * 100).toFixed(0)}%
            </div>
            <div className="text-xs text-text-secondary mt-1">{mostLikelyNext}</div>
          </div>
          <div className="p-3 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
              Second Most Likely
            </div>
            <div className="text-xl font-mono font-bold text-text-primary">
              {secondMostLikely}
            </div>
          </div>
        </div>

        {/* Full Transition Matrix if available */}
        {isObjectFormat && Object.keys(transitionsData).length > 0 && (
          <div className="p-3 bg-surface-1 border border-border overflow-x-auto">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2 flex items-center gap-2">
              <BarChart3 className="w-3 h-3" />
              Full Transition Matrix
            </div>
            <TransitionMatrixGrid matrix={transitionsData} current={currentRegime} />
          </div>
        )}
      </div>
    </div>
  );
}

interface TransitionMatrixGridProps {
  matrix: Record<string, Record<string, number>>;
  current: string;
}

function TransitionMatrixGrid({ matrix, current }: TransitionMatrixGridProps) {
  const regimes = Object.keys(matrix);

  return (
    <table className="w-full text-xs">
      <thead>
        <tr>
          <th className="p-1.5 text-left text-2xs text-text-tertiary">From / To</th>
          {regimes.map((r) => (
            <th key={r} className="p-1.5 text-center text-2xs text-text-tertiary">
              {r.slice(0, 4)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {regimes.map((from) => (
          <tr key={from} className={from === current ? 'bg-bloomberg-dim' : ''}>
            <td className="p-1.5 font-medium text-text-primary">{from.slice(0, 8)}</td>
            {regimes.map((to) => {
              const prob = matrix[from]?.[to] || 0;
              return (
                <td key={to} className="p-1.5 text-center">
                  <div
                    className="py-0.5 px-1 font-mono text-2xs"
                    style={{
                      backgroundColor:
                        prob > 0.5
                          ? 'rgba(0, 212, 170, 0.3)'
                          : prob > 0.2
                            ? 'rgba(0, 212, 170, 0.1)'
                            : 'transparent',
                      color: prob > 0.3 ? 'var(--bloomberg)' : 'var(--text-tertiary)',
                    }}
                  >
                    {(prob * 100).toFixed(0)}%
                  </div>
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

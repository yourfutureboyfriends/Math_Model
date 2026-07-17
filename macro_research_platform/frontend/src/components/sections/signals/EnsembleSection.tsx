// Phase 8 — Master Ensemble Signal Section (Redesigned)
// Combined signal from all active models with terminal aesthetic

import { Activity, AlertCircle } from 'lucide-react';
import type { EnsembleSignalData, ModelContribution } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface EnsembleSectionProps {
  data?: EnsembleSignalData;
}

export function EnsembleSection({ data: dataProp }: EnsembleSectionProps) {
  const fullDash = useMacroStore((s) => s.fullDashboard);
  // Build EnsembleSignalData from the backend EnsembleData shape
  const backendEnsemble = (fullDash as any)?.ensemble;
  const synthesized: EnsembleSignalData | null = backendEnsemble ? {
    ensembleScore: backendEnsemble.score ?? 0,
    ensembleSignal: backendEnsemble.score > 0.6
      ? 'Bullish / Risk-On'
      : backendEnsemble.score < 0.35
      ? 'Bearish / Risk-Off'
      : 'Neutral',
    conviction: backendEnsemble.conviction ?? 'Medium',
    agreementRatio: backendEnsemble.agreement ?? 0.7,
    signalDispersion: 1 - (backendEnsemble.agreement ?? 0.7),
    adaptiveWeightingActive: backendEnsemble.mode === 'Dynamic',
    modelBreakdown: [
      { model: 'Regime', score: (fullDash as any)?.regime?.confidenceScore ?? 0.5, weight: 0.3, weightedContribution: ((fullDash as any)?.regime?.confidenceScore ?? 0.5) * 0.3 },
      { model: 'Growth',  score: ((fullDash as any)?.scores?.growth ?? 50) / 100, weight: 0.25, weightedContribution: (((fullDash as any)?.scores?.growth ?? 50) / 100) * 0.25 },
      { model: 'Inflation', score: 1 - ((fullDash as any)?.scores?.inflation ?? 50) / 100, weight: 0.2, weightedContribution: (1 - ((fullDash as any)?.scores?.inflation ?? 50) / 100) * 0.2 },
      { model: 'Risk',   score: 1 - ((fullDash as any)?.scores?.risk ?? 50) / 100, weight: 0.25, weightedContribution: (1 - ((fullDash as any)?.scores?.risk ?? 50) / 100) * 0.25 },
    ] as ModelContribution[],
    topContributors: [],
    dissenting: [],
    riskBudgetFinal: backendEnsemble.riskBudget ?? 0.5,
    interpretation: `Ensemble score ${((backendEnsemble.score ?? 0) * 100).toFixed(0)}% bullish. ` +
      `Agreement ${((backendEnsemble.agreement ?? 0) * 100).toFixed(0)}%. ` +
      `Mode: ${backendEnsemble.mode ?? 'Dynamic'}.`,
    lastUpdated: new Date().toISOString(),
  } : null;

  const data = dataProp ?? synthesized ?? (fullDash as any)?.ensembleSignal as EnsembleSignalData | undefined;
  if (!data) return null;

  const getSignalTag = (signal: string) => {
    if (signal.includes('Bullish') || signal.includes('Risk-On')) return 'signal-tag bullish';
    if (signal.includes('Bearish') || signal.includes('Risk-Off')) return 'signal-tag bearish';
    return 'signal-tag neutral';
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.6) return 'text-green';
    if (score >= 0.2) return 'text-amber';
    if (score >= -0.2) return 'text-text-secondary';
    if (score >= -0.6) return 'text-amber';
    return 'text-red';
  };

  const getAgreementColor = (ratio: number) => {
    if (ratio >= 0.8) return 'text-green';
    if (ratio >= 0.6) return 'text-amber';
    return 'text-red';
  };

  // Prepare chart data
  const chartData = (data.modelBreakdown || [])
    .map((m: ModelContribution) => ({
      ...m,
      colorClass: getScoreColor(m.score)
    }))
    .sort((a, b) => Math.abs(b.weightedContribution) - Math.abs(a.weightedContribution));

  return (
    <div id="ensemble" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Master Ensemble</h2>
          <span className="section-meta">{data.ensembleSignal.toUpperCase()}</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Master Signal Header */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Activity className="w-3 h-3 text-text-secondary" />
              <span className="text-xs font-medium text-text-primary">Ensemble Score</span>
            </div>
            <span className={getSignalTag(data.ensembleSignal)}>
              {data.ensembleSignal}
            </span>
          </div>

          <div className="flex items-baseline gap-2 mb-2">
            <span className="text-2xl font-bold text-text-primary">
              {data.ensembleScore > 0 ? '+' : ''}{data.ensembleScore.toFixed(3)}
            </span>
            <span className="text-xs text-text-tertiary">/ +1.0</span>
          </div>

          {/* Score Bar */}
          <div className="relative h-2 bg-surface-4 mb-2">
            <div
              className="absolute top-0 bottom-0 bg-bloomberg"
              style={{
                left: data.ensembleScore < 0 ? undefined : '50%',
                right: data.ensembleScore < 0 ? '50%' : undefined,
                width: `${Math.min(50, Math.max(0, Math.abs(data.ensembleScore) * 50))}%`,
                backgroundColor: data.ensembleScore > 0 ? '#00d4aa' : '#f85149'
              }}
            />
            <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
          </div>

          <div className="flex items-center justify-between text-2xs text-text-tertiary">
            <span>Conviction: {data.conviction}</span>
            <span className={getAgreementColor(data.agreementRatio)}>
              Agreement: {(() => {
                const raw = data?.agreementRatio ?? 0;
                const pct = raw > 1 ? raw : raw * 100;
                return Math.min(100, Math.max(0, Math.round(pct)));
              })()}%
            </span>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-2">
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Dispersion</div>
            <div className="text-base font-mono text-text-primary">{data.signalDispersion.toFixed(3)}</div>
          </div>
          <div className="p-2 bg-surface-1 border border-border">
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Risk Budget</div>
            <div className="text-base font-mono text-text-primary">{data.riskBudgetFinal.toFixed(2)}x</div>
          </div>
          <div className={`p-2 border ${data.adaptiveWeightingActive ? 'bg-amber-dim border-amber' : 'bg-surface-1 border-border'}`}>
            <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Adaptive</div>
            <div className={`text-base font-mono ${data.adaptiveWeightingActive ? 'text-amber' : 'text-text-primary'}`}>
              {data.adaptiveWeightingActive ? 'ACTIVE' : 'OFF'}
            </div>
          </div>
        </div>

        {/* Model Contributions */}
        {chartData.length > 0 && (
          <div className="border border-border bg-surface-1">
            <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2">
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">Model Contributions</span>
            </div>
            <div className="p-2 space-y-1">
              {chartData.map((entry) => (
                <div key={entry.model} className="flex items-center justify-between">
                  <span className="text-xs text-text-primary w-24 truncate">{entry.model}</span>
                  <div className="flex-1 mx-2">
                    <div className="h-1 bg-surface-4 relative">
                      <div
                        className={`absolute top-0 bottom-0 ${entry.colorClass.replace('text-', 'bg-')}`}
                        style={{
                          width: `${Math.abs(entry.weightedContribution) * 50}%`,
                          [entry.weightedContribution >= 0 ? 'left' : 'right']: '50%'
                        }}
                      />
                      <div className="absolute top-0 bottom-0 left-1/2 w-px bg-text-tertiary/30" />
                    </div>
                  </div>
                  <span className={`font-mono text-xs w-12 text-right ${entry.colorClass}`}>
                    {entry.weightedContribution >= 0 ? '+' : ''}{(entry.weightedContribution * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top Contributors */}
        {data.topContributors && data.topContributors.length > 0 && (
          <div>
            <div className="text-2xs text-green uppercase tracking-wider mb-2">Top Contributors</div>
            <div className="flex flex-wrap gap-1">
              {data.topContributors.map((c) => (
                <span
                  key={c.model}
                  className="signal-tag bullish text-2xs"
                >
                  {c.model}: {(c.contribution * 100).toFixed(1)}%
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Dissenting Models */}
        {data.dissenting && data.dissenting.length > 0 && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="text-2xs text-amber uppercase tracking-wider mb-2">
              Dissenting Models ({data.dissenting.length})
            </div>
            <div className="space-y-1">
              {data.dissenting.map((d) => (
                <div key={d.model} className="flex items-center gap-2 text-xs">
                  <AlertCircle className="w-3 h-3 text-amber" />
                  <span className="text-text-secondary">{d.model}:</span>
                  <span className="text-text-primary">{d.note}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* FIXED (BUG 5): Regime Conflict Warning */}
        {data.regimeConflict && (
          <div className="p-3 border border-amber bg-amber-dim">
            <div className="text-2xs text-amber uppercase tracking-wider mb-1">
              Regime / Signal Mismatch
            </div>
            <p className="text-xs text-amber">{data.regimeConflictNote}</p>
          </div>
        )}

        {/* Interpretation */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Interpretation</div>
          <p className="text-xs text-text-secondary">{data.interpretation}</p>
        </div>
      </div>
    </div>
  );
}

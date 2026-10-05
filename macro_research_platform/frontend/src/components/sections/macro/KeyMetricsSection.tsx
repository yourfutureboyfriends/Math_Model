// Phase 5 — Key Metrics Section using the unified MetricCard
// Signal cards now compose headline + sparkline + storytelling subtitle (Phase 2) +
// data-lineage "i" (Phase 1) + staleness (Phase 1), from the shared MetricCard primitive.

import { useEffect, useState } from 'react';
import { MetricCard } from '@/components/ui/MetricCard';
import { useFreshness, freshnessFor } from '@/hooks/useFreshness';
import { useMacroStore } from '@/store/macroStore';
import { fmtSignal, fmtDuration, fmtProbabilityPrecise } from '@/utils/format';
import type { KeyMetrics } from '@/types';

interface KeyMetricsSectionProps {
  data?: KeyMetrics;
}

/** Fetch the Phase-2 signal explanations once and index them by signal name. */
function useSignalStories() {
  const [stories, setStories] = useState<Record<string, any>>({});
  const [meta, setMeta] = useState<{ source?: string; as_of?: string }>({});
  useEffect(() => {
    let alive = true;
    fetch('/api/v1/signal-attribution').then((r) => r.json()).then((d) => {
      if (!alive || !d?.signals) return;
      const map: Record<string, any> = {};
      d.signals.forEach((s: any) => { map[s.signal] = s; });
      setStories(map);
      setMeta({ source: d.source, as_of: d.as_of });
    }).catch(() => {});
    return () => { alive = false; };
  }, []);
  return { stories, meta };
}

export function KeyMetricsSection({ data }: KeyMetricsSectionProps) {
  // Use macro store for all data - no hardcoded fallbacks
  // P3: narrow selectors — re-render only when these change, not on every price tick.
  const signals = useMacroStore((s) => s.signals);
  const regime = useMacroStore((s) => s.regime);
  const fullDashboard = useMacroStore((s) => s.fullDashboard);
  const { stories, meta } = useSignalStories();
  const freshness = useFreshness();
  const isStale = (metric: string) => {
    const f = freshnessFor(freshness, metric);
    return !!f && f.status !== 'FRESH' && f.status !== 'UNKNOWN';
  };
  // Lineage builder for a signal card (Phase 1), sharing the attribution provenance.
  const lineageFor = (name: string, value: number) => {
    const s = stories[name];
    return {
      value, source: meta.source || 'computed (yfinance/FRED)', fetched_at: meta.as_of,
      staleness_threshold_seconds: 900,
      formula: s ? `Score decomposed into ranked contributions; driver: ${s.driver}` : 'Composite signal score',
    };
  };
  // KeyMetricsSection is rendered without a `data` prop, so fall back to the raw
  // dashboard keyMetrics held in the store. Without this, recession/sparklines
  // defaulted to 0 and the card showed "0.0%" despite the API returning 13%.
  const km = (data ?? (fullDashboard as any)?.keyMetrics) as KeyMetrics | undefined;


  const getRecessionColor = (value: number) => {
    if (value > 30) return 'text-red';
    if (value < 15) return 'text-green';
    return 'text-amber';
  };

  // Format signal scores using format library
  const growthScore = signals.growth.score ?? 0;
  const inflationScore = signals.inflation.score ?? 0;
  const liquidityScore = signals.liquidity.score ?? 0;
  const riskScore = signals.risk.score ?? 0;

  // Sparklines on the SAME scale as the headline score: the signal histories (0–1). The
  // keyMetrics sparklines are 0–100 and, for risk, plot risk aversion (100 − appetite),
  // so the line moved opposite to the "Risk Appetite" number above it.
  const sig = (fullDashboard as any)?.signals ?? {};
  const hist = (k: string): number[] => (Array.isArray(sig[k]?.history) ? sig[k].history : []);
  const histLabels = (k: string): string[] | undefined => sig[k]?.historyLabels;
  const growthSparkline = hist('growth');
  const inflationSparkline = hist('inflation');
  const liquiditySparkline = hist('liquidity');
  const riskSparkline = hist('risk');
  const recessionSparkline = km?.recession?.sparklineData ?? [];
  const fmtScore = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
  // Direction = the move over the history window, not the sign of a 0–1 score (which made
  // every card read "UP"). Moves within ±0.03 (score) / ±0.5pp (recession) are flat.
  const trend = (xs: number[], tol: number): 'up' | 'down' | 'neutral' => {
    if (xs.length < 2) return 'neutral';
    const d = xs[xs.length - 1] - xs[0];
    return d > tol ? 'up' : d < -tol ? 'down' : 'neutral';
  };

  return (
    <div id="key-metrics" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Macro Indicators</h2>
        </div>
      </div>

      {/* KPI Grid — unified MetricCard (Phase 5) */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          label="Growth"
          value={fmtSignal(growthScore) ?? '—'}
          direction={trend(growthSparkline, 0.03)}
          sparklineData={growthSparkline}
          sparklineLabels={histLabels('growth')}
          sparklineFormat={fmtScore}
          color="var(--text-primary)"
          explanation={stories.Growth?.explanation_text}
          lineage={lineageFor('Growth', growthScore)}
          stale={isStale('growth')}
        />

        <MetricCard
          label="Inflation"
          value={fmtSignal(inflationScore) ?? '—'}
          direction={trend(inflationSparkline, 0.03)}
          color="var(--text-primary)"
          sparklineData={inflationSparkline}
          sparklineLabels={histLabels('inflation')}
          sparklineFormat={fmtScore}
          explanation={stories.Inflation?.explanation_text}
          lineage={lineageFor('Inflation', inflationScore)}
          stale={isStale('inflation')}
        />

        <MetricCard
          label="Fin. Conditions"
          value={fmtSignal(liquidityScore) ?? '—'}
          direction={trend(liquiditySparkline, 0.03)}
          color="var(--text-primary)"
          sparklineData={liquiditySparkline}
          sparklineLabels={histLabels('liquidity')}
          sparklineFormat={fmtScore}
          explanation={stories.Liquidity?.explanation_text}
          lineage={lineageFor('Liquidity', liquidityScore)}
          stale={isStale('liquidity')}
        />

        <MetricCard
          label="Risk Appetite"
          value={fmtSignal(riskScore) ?? '—'}
          direction={trend(riskSparkline, 0.03)}
          color="var(--text-primary)"
          sparklineData={riskSparkline}
          sparklineLabels={histLabels('risk')}
          sparklineFormat={fmtScore}
          explanation={stories.Risk?.explanation_text}
          lineage={lineageFor('Risk', riskScore)}
          stale={isStale('risk')}
        />

        <MetricCard
          label="Recession Risk"
          value={km?.recession?.formatted ?? '—'}
          direction={trend(recessionSparkline, 0.5)}
          sparklineData={recessionSparkline}
          sparklineFormat={(v) => `${v.toFixed(1)}%`}
          color={getRecessionColor(isNaN(km?.recession?.value ?? 0) ? 0 : (km?.recession?.value ?? 0)).replace('text-', 'var(--') + ')'}
          lineage={{ source: 'ensemble recession model', fetched_at: meta.as_of, formula: 'Estrella-Mishkin probit + Sahm + ensemble' }}
          stale={isStale('recession')}
        />

        {/* Regime Duration - Uses store */}
        <div className="relative h-full min-h-20 bg-surface-1 border border-border p-3 flex flex-col">
          <div className="absolute top-0 left-0 right-0 h-px bg-bloomberg" />
          <div className="flex items-center justify-between mb-1">
            <span className="text-2xs text-text-secondary uppercase tracking-wider">Duration</span>
            <span className="text-2xs text-text-tertiary uppercase">Current</span>
          </div>
          <div className="text-2xl font-mono font-bold text-text-primary tabular-nums leading-none">
            {regime.duration ? fmtDuration(regime.duration) : '—'}
          </div>
          <div className="mt-auto text-xs text-text-tertiary truncate">
            {regime.confidence ? fmtProbabilityPrecise(regime.confidence, 0) + ' confidence' : '—'}
          </div>
        </div>
      </div>
    </div>
  );
}

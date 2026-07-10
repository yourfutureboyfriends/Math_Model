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

  const getScoreDirection = (value: number): 'up' | 'down' | 'neutral' => {
    if (value > 0) return 'up';
    if (value < 0) return 'down';
    return 'neutral';
  };

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

  // Use data from store only - no hardcoded fallbacks
  const growthSparkline = km?.growth?.sparklineData ?? [];
  const inflationSparkline = km?.inflation?.sparklineData ?? [];
  const liquiditySparkline = km?.liquidity?.sparklineData ?? [];
  const riskSparkline = km?.risk?.sparklineData ?? [];
  const recessionSparkline = km?.recession?.sparklineData ?? [];

  return (
    <div id="key-metrics" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">03</span>
          <h2 className="section-title">Key Metrics</h2>
        </div>
      </div>

      {/* KPI Grid — unified MetricCard (Phase 5) */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          label="Growth"
          value={fmtSignal(growthScore) ?? '—'}
          direction={getScoreDirection(growthScore)}
          sparklineData={growthSparkline}
          color={getScoreDirection(growthScore) === 'up' ? 'var(--green)' : undefined}
          explanation={stories.Growth?.explanation_text}
          lineage={lineageFor('Growth', growthScore)}
          stale={isStale('growth')}
        />

        <MetricCard
          label="Inflation"
          value={fmtSignal(inflationScore) ?? '—'}
          direction={getScoreDirection(inflationScore)}
          sparklineData={inflationSparkline}
          explanation={stories.Inflation?.explanation_text}
          lineage={lineageFor('Inflation', inflationScore)}
          stale={isStale('inflation')}
        />

        <MetricCard
          label="Fin. Conditions"
          value={fmtSignal(liquidityScore) ?? '—'}
          direction="neutral"
          sparklineData={liquiditySparkline}
          explanation={stories.Liquidity?.explanation_text}
          lineage={lineageFor('Liquidity', liquidityScore)}
          stale={isStale('liquidity')}
        />

        <MetricCard
          label="Risk Appetite"
          value={fmtSignal(riskScore) ?? '—'}
          direction={getScoreDirection(riskScore)}
          sparklineData={riskSparkline}
          explanation={stories.Risk?.explanation_text}
          lineage={lineageFor('Risk', riskScore)}
          stale={isStale('risk')}
        />

        <MetricCard
          label="Recession Risk"
          value={km?.recession?.formatted ?? '—'}
          direction={isNaN(km?.recession?.value ?? 0) ? 'neutral' : ((km?.recession?.value ?? 0) > 15 ? 'down' : 'up')}
          sparklineData={recessionSparkline}
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

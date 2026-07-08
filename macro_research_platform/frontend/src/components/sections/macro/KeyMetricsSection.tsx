// Phase 8 — Key Metrics Section (Redesigned) + Phase 1E Store Integration
// Six KPI cards using macroStore data and format library

import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { AnimatedValue } from '@/components/ui';
import { StaleBadge } from '@/components/ui/StaleBadge';
import { useMacroStore } from '@/store/macroStore';
import { fmtSignal, fmtDuration, fmtProbabilityPrecise } from '@/utils/format';
import type { KeyMetrics } from '@/types';

interface KeyMetricsSectionProps {
  data?: KeyMetrics;
}

// SVG sparkline builder
function buildSparklinePath(data: number[], width: number, height: number) {
  if (!data || data.length < 2) return '';
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = Math.round((i / (data.length - 1)) * width * 10) / 10;
    const y = Math.round((height - ((v - min) / range) * height) * 10) / 10;
    return `${x},${y}`;
  });
  return `M${points.join('L')}`;
}

// Parse numeric value from formatted string for animation
function parseNumericValue(formatted: string): number {
  const cleaned = formatted.replace(/[$,%]/g, '').replace(/[+-]/g, '');
  const parsed = parseFloat(cleaned);
  return isNaN(parsed) ? 0 : parsed;
}

function KPICard({
  label,
  value,
  direction,
  sparklineData,
  valueColor,
  numericValue,
  suffix = '',
  staleMetric,
}: {
  label: string;
  value: string;
  direction: 'up' | 'down' | 'neutral';
  sparklineData?: number[];
  valueColor?: string;
  numericValue?: number;
  suffix?: string;
  staleMetric?: string;
}) {
  const getValueColor = () => {
    if (valueColor) return valueColor;
    if (direction === 'up') return 'text-green';
    if (direction === 'down') return 'text-red';
    return 'text-text-primary';
  };

  const getDirectionIcon = () => {
    if (direction === 'up') return <TrendingUp className="w-3 h-3" />;
    if (direction === 'down') return <TrendingDown className="w-3 h-3" />;
    return <Minus className="w-3 h-3" />;
  };

  // Parse numeric value for animation
  const parsedValue = numericValue ?? parseNumericValue(value);

  return (
    <div className="relative h-20 bg-surface-1 border border-border p-3 flex flex-col">
      {/* Top accent line */}
      <div className="absolute top-0 left-0 right-0 h-px bg-bloomberg" />

      {/* Header: Label + Direction */}
      <div className="flex items-center justify-between mb-1">
        <span className="text-2xs text-text-secondary uppercase tracking-wider flex items-center gap-1">
          {label}
          {staleMetric && <StaleBadge metric={staleMetric} />}
        </span>
        <div
          className={cn(
            'flex items-center gap-0.5 text-2xs',
            direction === 'up' ? 'text-green' : direction === 'down' ? 'text-red' : 'text-text-tertiary'
          )}
        >
          {getDirectionIcon()}
          <span className="uppercase">{direction}</span>
        </div>
      </div>

      {/* Value with animation */}
      <div className={cn('text-lg font-mono font-bold tabular-nums', getValueColor())}>
        <AnimatedValue
          value={parsedValue}
          decimals={suffix === '%' ? 1 : 2}
          suffix={suffix}
          duration={800}
        />
      </div>

      {/* Sparkline */}
      {sparklineData && sparklineData.length > 1 && (
        <div className="mt-auto">
          <svg width="80" height="20" className="overflow-visible">
            <path
              d={buildSparklinePath(sparklineData, 80, 20)}
              fill="none"
              stroke="var(--bloomberg)"
              strokeWidth="1.5"
            />
          </svg>
        </div>
      )}
    </div>
  );
}

export function KeyMetricsSection({ data }: KeyMetricsSectionProps) {
  // Use macro store for all data - no hardcoded fallbacks
  const store = useMacroStore((state) => state);
  const signals = store.signals;
  const regime = store.regime;
  // KeyMetricsSection is rendered without a `data` prop, so fall back to the raw
  // dashboard keyMetrics held in the store. Without this, recession/sparklines
  // defaulted to 0 and the card showed "0.0%" despite the API returning 13%.
  const km = (data ?? (store.fullDashboard as any)?.keyMetrics) as KeyMetrics | undefined;

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

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KPICard
          label="Growth"
          value={fmtSignal(growthScore) ?? '—'}
          numericValue={growthScore}
          direction={getScoreDirection(growthScore)}
          sparklineData={growthSparkline}
          valueColor={getScoreDirection(growthScore) === 'up' ? 'text-green' : 'text-text-primary'}
          staleMetric="growth"
        />

        <KPICard
          label="Inflation"
          value={fmtSignal(inflationScore) ?? '—'}
          numericValue={inflationScore}
          direction={getScoreDirection(inflationScore)}
          sparklineData={inflationSparkline}
          valueColor={getScoreDirection(inflationScore) === 'up' ? 'text-amber' : 'text-green'}
          staleMetric="inflation"
        />

        <KPICard
          label="Fin. Conditions"
          value={fmtSignal(liquidityScore) ?? '—'}
          numericValue={liquidityScore}
          direction="neutral"
          sparklineData={liquiditySparkline}
        />

        <KPICard
          label="Risk Appetite"
          value={fmtSignal(riskScore) ?? '—'}
          numericValue={riskScore}
          direction={getScoreDirection(riskScore)}
          sparklineData={riskSparkline}
        />

        <KPICard
          label="Recession Risk"
          value={km?.recession?.formatted ?? '—'}
          numericValue={isNaN(km?.recession?.value ?? 0) ? 0 : (km?.recession?.value ?? 0)}
          direction={isNaN(km?.recession?.value ?? 0) ? 'neutral' : ((km?.recession?.value ?? 0) > 15 ? 'down' : 'up')}
          sparklineData={recessionSparkline}
          valueColor={getRecessionColor(isNaN(km?.recession?.value ?? 0) ? 0 : (km?.recession?.value ?? 0))}
          suffix="%"
        />

        {/* Regime Duration - Uses store */}
        <div className="relative h-20 bg-surface-1 border border-border p-3 flex flex-col">
          <div className="absolute top-0 left-0 right-0 h-px bg-bloomberg" />
          <div className="flex items-center justify-between mb-1">
            <span className="text-2xs text-text-secondary uppercase tracking-wider">Duration</span>
            <span className="text-2xs text-text-tertiary uppercase">Current</span>
          </div>
          <div className="text-lg font-mono font-bold text-text-primary tabular-nums">
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

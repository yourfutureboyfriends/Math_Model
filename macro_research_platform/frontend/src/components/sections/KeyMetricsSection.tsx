// Phase 8 — Key Metrics Section (Redesigned)
// Six KPI cards, 80px fixed height, terminal aesthetic

import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
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
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `M${points.join('L')}`;
}

function KPICard({
  label,
  value,
  direction,
  sparklineData,
  valueColor,
}: {
  label: string;
  value: string;
  direction: 'up' | 'down' | 'neutral';
  sparklineData?: number[];
  valueColor?: string;
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

  return (
    <div className="relative h-20 bg-surface-1 border border-border p-3 flex flex-col">
      {/* Top accent line */}
      <div className="absolute top-0 left-0 right-0 h-px bg-accent" />

      {/* Header: Label + Direction */}
      <div className="flex items-center justify-between mb-1">
        <span className="text-2xs text-text-secondary uppercase tracking-wider">
          {label}
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

      {/* Value */}
      <div className={cn('text-lg font-mono font-bold tabular-nums', getValueColor())}>
        {value}
      </div>

      {/* Sparkline */}
      {sparklineData && sparklineData.length > 1 && (
        <div className="mt-auto">
          <svg width="80" height="20" className="overflow-visible">
            <path
              d={buildSparklinePath(sparklineData, 80, 20)}
              fill="none"
              stroke="var(--accent)"
              strokeWidth="1.5"
            />
          </svg>
        </div>
      )}
    </div>
  );
}

export function KeyMetricsSection({ data }: KeyMetricsSectionProps) {
  if (!data) return null;

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

  const getInflationColor = (direction: string) => {
    // Rising inflation is typically bad
    return direction === 'up' ? 'text-amber' : 'text-green';
  };

  return (
    <div id="key-metrics" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">02</span>
          <h2 className="section-title">Key Metrics</h2>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KPICard
          label="Growth"
          value={data.growth.formatted}
          direction={getScoreDirection(data.growth.value)}
          sparklineData={data.growth.sparklineData}
          valueColor={getScoreDirection(data.growth.value) === 'up' ? 'text-green' : 'text-text-primary'}
        />

        <KPICard
          label="Inflation"
          value={data.inflation.formatted}
          direction={getScoreDirection(data.inflation.value)}
          sparklineData={data.inflation.sparklineData}
          valueColor={getInflationColor(data.inflation.direction)}
        />

        <KPICard
          label="Fin. Conditions"
          value={data.liquidity.formatted}
          direction="neutral"
          sparklineData={data.liquidity.sparklineData}
        />

        <KPICard
          label="Risk Appetite"
          value={data.risk.formatted}
          direction={getScoreDirection(data.risk.value)}
          sparklineData={data.risk.sparklineData}
        />

        <KPICard
          label="Recession Risk"
          value={data.recession.formatted}
          direction={data.recession.value > 15 ? 'down' : 'up'}
          sparklineData={data.recession.sparklineData}
          valueColor={getRecessionColor(data.recession.value)}
        />

        {/* Regime Duration - Special Card */}
        <div className="relative h-20 bg-surface-1 border border-border p-3 flex flex-col">
          <div className="absolute top-0 left-0 right-0 h-px bg-accent" />
          <div className="flex items-center justify-between mb-1">
            <span className="text-2xs text-text-secondary uppercase tracking-wider">Duration</span>
            <span className="text-2xs text-text-tertiary uppercase">Current</span>
          </div>
          <div className="text-lg font-mono font-bold text-text-primary tabular-nums">
            {data.regimeDuration.value}
          </div>
          <div className="mt-auto text-xs text-text-tertiary truncate">
            {data.regimeDuration.currentRegime}
          </div>
        </div>
      </div>
    </div>
  );
}

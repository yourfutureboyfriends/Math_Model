// Phase 2 — Terminal Metric Card Component
// Compact KPI card with terminal aesthetic

import { Sparkline } from './Sparkline';
import { cn, getDirectionColor } from '@/lib/utils';

interface MetricCardProps {
  label: string;
  value: string;
  direction?: 'up' | 'down' | 'neutral';
  sparklineData?: number[];
  color?: string;
  className?: string;
}

export function MetricCard({
  label,
  value,
  direction = 'neutral',
  sparklineData,
  color,
  className,
}: MetricCardProps) {
  const valueColor = color || getDirectionColor(direction);

  return (
    <div
      className={cn(
        'bg-surface-1 border border-border p-2',
        'flex flex-col justify-between',
        className
      )}
    >
      <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">
        {label}
      </div>
      <div
        className="text-lg font-mono font-bold"
        style={{ color: valueColor }}
      >
        {value}
      </div>
      {sparklineData && (
        <div className="flex-grow mt-2">
          <Sparkline data={sparklineData} direction={direction} height={40} />
        </div>
      )}
    </div>
  );
}

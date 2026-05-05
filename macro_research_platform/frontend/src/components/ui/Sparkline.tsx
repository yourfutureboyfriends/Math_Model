// Phase 2 — Terminal Sparkline Component
// Minimal SVG sparkline for terminal aesthetic

import { getDirectionColor } from '@/lib/utils';

interface SparklineProps {
  data: number[];
  direction?: 'up' | 'down' | 'neutral';
  height?: number;
  color?: string;
}

export function Sparkline({
  data,
  direction = 'neutral',
  height = 40,
  color,
}: SparklineProps) {
  if (!data || data.length < 2) {
    return <div style={{ height }} className="w-full bg-surface-3" />;
  }

  const strokeColor = color || getDirectionColor(direction);
  const width = 100;
  const padding = 2;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  // Generate SVG path
  const points = data.map((value, index) => {
    const x = padding + (index / (data.length - 1)) * (width - 2 * padding);
    const y = height - padding - ((value - min) / range) * (height - 2 * padding);
    return `${x},${y}`;
  });

  const pathD = `M ${points.join(' L ')}`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full"
      style={{ height }}
      preserveAspectRatio="none"
    >
      <path
        d={pathD}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

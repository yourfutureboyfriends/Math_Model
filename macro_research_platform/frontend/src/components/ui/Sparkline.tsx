// Terminal sparkline on Apache ECharts (via MiniChart): full-width line coloured by direction, hover readout of the
// point's value and label (e.g. its date).

import { getDirectionColor } from '@/lib/utils';
import { MiniChart } from '@/components/charts/MiniChart';

interface SparklineProps {
  data: number[];
  direction?: 'up' | 'down' | 'neutral';
  height?: number;
  color?: string;
  /** Label per point for the hover readout (e.g. dates). */
  labels?: string[];
  format?: (v: number) => string;
}

export function Sparkline({ data, direction = 'neutral', height = 40, color, labels, format }: SparklineProps) {
  if (!data || data.length < 2) return <div style={{ height }} className="w-full bg-surface-3" />;
  return <MiniChart values={data} fill height={height} labels={labels} fmt={format} colour={color ?? getDirectionColor(direction)} dot={false} />;
}

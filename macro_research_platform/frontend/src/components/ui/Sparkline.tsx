// Terminal sparkline: minimal SVG line with a hover readout (point, value, optional label).

import { useState } from 'react';
import { getDirectionColor } from '@/lib/utils';

interface SparklineProps {
  data: number[];
  direction?: 'up' | 'down' | 'neutral';
  height?: number;
  color?: string;
  /** Label per point for the hover readout (e.g. dates); defaults to "n of N". */
  labels?: string[];
  format?: (v: number) => string;
}

export function Sparkline({
  data,
  direction = 'neutral',
  height = 40,
  color,
  labels,
  format = (v) => v.toLocaleString('en-US', { maximumFractionDigits: Math.abs(v) >= 100 ? 0 : 2, minimumFractionDigits: Math.abs(v) >= 100 ? 0 : 2 }),
}: SparklineProps) {
  const [hover, setHover] = useState<number | null>(null);

  if (!data || data.length < 2) {
    return <div style={{ height }} className="w-full bg-surface-3" />;
  }

  const strokeColor = color ?? getDirectionColor(direction);
  const width = 100;
  const padding = 2;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const xy = (value: number, index: number) => ({
    x: padding + (index / (data.length - 1)) * (width - 2 * padding),
    y: height - padding - ((value - min) / range) * (height - 2 * padding),
  });
  const pathD = `M ${data.map((v, i) => { const p = xy(v, i); return `${p.x},${p.y}`; }).join(' L ')}`;

  const onMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    setHover(Math.round(f * (data.length - 1)));
  };

  const hp = hover !== null ? xy(data[hover], hover) : null;
  const label = hover !== null ? (labels?.[hover] ?? `${hover + 1} of ${data.length}`) : '';

  return (
    <div className="relative w-full" style={{ height }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }} preserveAspectRatio="none" aria-hidden>
        <path d={pathD} fill="none" stroke={strokeColor} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        {hp && (
          <line x1={hp.x} x2={hp.x} y1={0} y2={height} stroke="var(--text-tertiary)" strokeWidth="1"
            strokeDasharray="2 2" vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      {hp && hover !== null && (
        <>
          <span className="pointer-events-none absolute w-2 h-2 rounded-full border-2 border-bg"
            style={{ left: `calc(${hp.x}% - 4px)`, top: hp.y - 4, background: strokeColor }} />
          <span className="pointer-events-none absolute px-1 text-[10px] font-mono whitespace-nowrap bg-surface-3 border border-border text-text-primary z-10"
            style={{ top: height + 2, ...(hp.x > 60 ? { right: `${100 - hp.x}%` } : { left: `${hp.x}%` }) }}>
            {format(data[hover])} <span className="text-text-tertiary">{label}</span>
          </span>
        </>
      )}
    </div>
  );
}

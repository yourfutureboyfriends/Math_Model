// Phase 8 — Horizon Tension Analysis Section (Three-Horizon Model)
// Short (1-5d) | Medium (1-4wk) | Long (3-12m) with tension detection

import { useState, useEffect } from 'react';
import { Clock, Zap, TrendingUp, Minus, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

// Safe number formatter
const fmt = (val: number | undefined | null, decimals = 0): string => {
  if (val === undefined || val === null || isNaN(val)) return '—';
  return Number(val).toFixed(decimals);
};

interface HorizonEvent {
  date?: string;
  event?: string;
  impact?: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  category?: string;
  days_away?: number;
}

interface NextHighImpact {
  date?: string;
  event?: string;
  days_away?: number;
}

interface HorizonData {
  horizon_events?: HorizonEvent[];
  next_high_impact?: NextHighImpact | null;
  risk_density?: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  last_updated?: string;
}

export function HorizonTensionSection() {
  const [data, setData] = useState<HorizonData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHorizonData = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/horizon');
        if (!response.ok) throw new Error('Failed to fetch horizon data');
        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load horizon data');
      } finally {
        setLoading(false);
      }
    };

    fetchHorizonData();
    // Refresh every 5 minutes
    const interval = setInterval(fetchHorizonData, 300000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div id="horizon-tension" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">30</span>
            <h2 className="section-title">Horizon Tensions</h2>
          </div>
        </div>
        <div className="p-4 bg-surface-1 border border-border text-center text-text-tertiary">
          Loading horizon analysis...
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div id="horizon-tension" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">30</span>
            <h2 className="section-title">Horizon Tensions</h2>
            <span style={{ color: 'var(--text-tertiary)', fontSize: '11px' }}>
              — data unavailable
            </span>
          </div>
        </div>
        <div className="p-4 bg-surface-1 border border-border text-center text-text-tertiary">
          {error || 'Horizon analysis unavailable'}
        </div>
      </div>
    );
  }

  // Safe defaults with null coalescing
  const horizon_events = data?.horizon_events ?? [];
  const next_high_impact = data?.next_high_impact ?? null;
  const risk_density = data?.risk_density ?? 'UNKNOWN';

  // Empty state guard
  if (horizon_events.length === 0) {
    return (
      <div id="horizon-tension" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">30</span>
            <h2 className="section-title">Horizon Tensions</h2>
          </div>
        </div>
        <div className="p-4 bg-surface-1 border border-border text-center text-text-tertiary">
          No horizon events available
        </div>
      </div>
    );
  }

  // Categorize events by timeframe
  const shortTermEvents = (horizon_events ?? []).filter(e => (e?.days_away ?? 0) <= 7);
  const mediumTermEvents = (horizon_events ?? []).filter(e => {
    const days = e?.days_away ?? 0;
    return days > 7 && days <= 30;
  });
  const longTermEvents = (horizon_events ?? []).filter(e => (e?.days_away ?? 0) > 30);

  // Calculate high impact event counts (next 14 days)
  const highImpactNext14 = (horizon_events ?? []).filter(e => e?.impact === 'HIGH' && (e?.days_away ?? 999) <= 14).length;

  const getImpactColor = (impact?: string) => {
    switch (impact) {
      case 'HIGH':
        return 'text-red bg-red-dim border-red';
      case 'MEDIUM':
        return 'text-amber bg-amber-dim border-amber';
      default:
        return 'text-text-secondary bg-surface-2 border-border';
    }
  };

  const getCategoryIcon = (category?: string) => {
    switch (category) {
      case 'MONETARY_POLICY':
        return <TrendingUp className="w-3 h-3" />;
      case 'INFLATION':
        return <Zap className="w-3 h-3" />;
      case 'LABOR':
        return <Clock className="w-3 h-3" />;
      default:
        return <Minus className="w-3 h-3" />;
    }
  };

  return (
    <div id="horizon-tension" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">30</span>
          <h2 className="section-title">Horizon Tensions</h2>
          <span className="section-meta">
            Risk density: {risk_density}
          </span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Next High Impact Event */}
        {next_high_impact && (
          <div className={cn(
            "p-3 border",
            (next_high_impact?.days_away ?? 999) <= 3
              ? "bg-red-dim border-red"
              : "bg-amber-dim border-amber"
          )}>
            <div className="flex items-start gap-2">
              <AlertTriangle className={cn(
                "w-4 h-4 flex-shrink-0 mt-0.5",
                (next_high_impact?.days_away ?? 999) <= 3 ? "text-red" : "text-amber"
              )} />
              <div className="flex-1">
                <div className={cn(
                  "text-sm font-medium",
                  (next_high_impact?.days_away ?? 999) <= 3 ? "text-red" : "text-amber"
                )}>
                  NEXT HIGH-IMPACT EVENT
                </div>
                <div className="text-sm text-text-primary">{next_high_impact?.event || 'Unknown'}</div>
                <div className="text-2xs text-text-secondary">
                  {next_high_impact?.date || '—'} • {fmt(next_high_impact?.days_away)} days away
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Event Summary by Timeframe */}
        <div className="grid grid-cols-3 gap-2">
          <div className="p-2 bg-surface-1 border border-border text-center">
            <div className="text-2xs text-text-tertiary uppercase">Short (7d)</div>
            <div className="text-lg font-mono text-text-primary">{shortTermEvents.length}</div>
            <div className="text-2xs text-text-secondary">
              {(shortTermEvents ?? []).filter(e => e?.impact === 'HIGH').length} high
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border text-center">
            <div className="text-2xs text-text-tertiary uppercase">Medium (30d)</div>
            <div className="text-lg font-mono text-text-primary">{mediumTermEvents.length}</div>
            <div className="text-2xs text-text-secondary">
              {(mediumTermEvents ?? []).filter(e => e?.impact === 'HIGH').length} high
            </div>
          </div>
          <div className="p-2 bg-surface-1 border border-border text-center">
            <div className="text-2xs text-text-tertiary uppercase">Long (90d)</div>
            <div className="text-lg font-mono text-text-primary">{longTermEvents.length}</div>
            <div className="text-2xs text-text-secondary">
              {(longTermEvents ?? []).filter(e => e?.impact === 'HIGH').length} high
            </div>
          </div>
        </div>

        {/* Upcoming Events Table */}
        <div className="border border-border bg-surface-1 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <th className="text-left py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  Event
                </th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  Date
                </th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  Days
                </th>
                <th className="text-center py-2 px-2 text-2xs text-text-tertiary uppercase font-medium">
                  Impact
                </th>
              </tr>
            </thead>
            <tbody>
              {(horizon_events ?? []).slice(0, 8).map((event, idx) => (
                <tr
                  key={idx}
                  className="border-b border-border-subtle last:border-0 hover:bg-surface-3 transition-colors"
                >
                  <td className="py-2 px-2">
                    <div className="flex items-center gap-2">
                      {getCategoryIcon(event?.category)}
                      <span className="text-sm text-text-primary">{event?.event || 'Unknown'}</span>
                    </div>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className="text-xs font-mono text-text-secondary">
                      {event?.date || '—'}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className={cn(
                      "text-xs font-mono",
                      (event?.days_away ?? 999) <= 3 ? "text-red font-bold" :
                      (event?.days_away ?? 999) <= 7 ? "text-amber" :
                      "text-text-secondary"
                    )}>
                      {fmt(event?.days_away)}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className={cn(
                      "px-1.5 py-0.5 text-2xs font-medium border",
                      getImpactColor(event?.impact)
                    )}>
                      {event?.impact || 'LOW'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Risk Summary */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-3 h-3 text-text-secondary" />
            <span className="text-xs font-medium text-text-primary">Risk Summary</span>
          </div>
          <div className="text-sm text-text-primary mb-2">
            {highImpactNext14 > 3
              ? 'HIGH risk density — Multiple high-impact events in next 14 days'
              : highImpactNext14 > 1
              ? 'MEDIUM risk density — Some volatility expected'
              : 'LOW risk density — Calm period ahead'}
          </div>
          <div className="flex items-center gap-2 pt-2 border-t border-border-subtle">
            <span className="text-2xs text-text-tertiary">High-impact events (14d):</span>
            <span className={cn(
              "text-xs font-mono font-bold",
              highImpactNext14 > 3 ? 'text-red' :
              highImpactNext14 > 1 ? 'text-amber' : 'text-green'
            )}>
              {highImpactNext14}
            </span>
            <span className="text-2xs text-text-tertiary">
              {highImpactNext14 > 3 ? '(elevated)' : '(normal)'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

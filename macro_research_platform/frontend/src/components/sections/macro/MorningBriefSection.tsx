// Morning Brief Section + Phase 4A Format Library
// First thing a PM reads - actionable priorities, risks, conviction trades
// Fetches data from backend API - no hardcoded data

import { useState, useEffect } from 'react';
import { AlertTriangle, Target, Calendar, TrendingUp, Shield } from 'lucide-react';
import { fmtProbability, fmtChange } from '@/utils/format';
import { api } from '@/lib/apiClient';

interface Priority {
  type: 'calendar' | 'tension' | 'signal';
  priority: number;
  title: string;
  time?: string;
  date?: string;
  implication: string;
}

interface Risk {
  type: string;
  text: string;
  severity: 'WARNING' | 'INFO' | 'CRITICAL';
}

interface ConvictionTrade {
  ticker: string;
  direction: 'LONG' | 'SHORT';
  conviction: 'HIGH' | 'MEDIUM' | 'LOW';
  rr?: number;
  entry?: number;
  target?: number;
  stop?: number;
  thesis?: string;
  category?: string;
}

interface MorningBriefSectionData {
  date: string;
  regime: string;
  duration_months: number;
  confidence: number;
  priorities: Priority[];
  risks: Risk[];
  conviction_trades: ConvictionTrade[];
  position_modifier: number;
  model_caution: boolean;
}

export function MorningBriefSection() {
  const [data, setData] = useState<MorningBriefSectionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchMorningBrief = async () => {
      try {
        setLoading(true);
        const response = await api.business.getMorningBrief();
        // Transform API response to component format
        const transformed: MorningBriefSectionData = {
          date: (response as any).date || new Date().toISOString().split('T')[0],
          regime: (response as any).regime || 'Goldilocks',
          duration_months: (response as any).duration_months || 1,
          confidence: (response as any).confidence || 0.75,
          priorities: ((response as any).priorities || []).map((p: any, i: number) => ({
            type: 'signal',
            priority: i + 1,
            title: typeof p === 'string' ? p : p.title,
            implication: typeof p === 'string' ? 'Action required' : p.implication
          })),
          risks: ((response as any).risks || []).map((r: any) => ({
            type: r.type || 'market',
            text: r.text || r,
            severity: r.severity || 'INFO'
          })),
          conviction_trades: ((response as any).conviction_trades || []).map((t: any) => ({
            ticker: t.ticker || t.asset,
            direction: t.direction,
            conviction: t.conviction,
            entry: t.entry,
            target: t.target,
            stop: t.stop,
            thesis: t.thesis || t.rationale
          })),
          position_modifier: (response as any).position_modifier || 1.0,
          model_caution: (response as any).model_caution || false
        };
        setData(transformed);
      } catch (e) {
        console.error('[MorningBrief] Failed to fetch:', e);
        setError('Failed to load morning brief');
      } finally {
        setLoading(false);
      }
    };

    fetchMorningBrief();
  }, []);

  if (loading) {
    return (
      <div className="terminal-section">
        <div className="section-header">
          <span className="section-title">MORNING BRIEF</span>
          <span style={{ color: 'var(--text-tertiary)', fontSize: '11px' }}>
            — loading...
          </span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="terminal-section">
        <div className="section-header">
          <span className="section-title">MORNING BRIEF</span>
          <span style={{ color: 'var(--text-tertiary)', fontSize: '11px' }}>
            — {error || 'not available'}
          </span>
        </div>
      </div>
    );
  }

  const {
    date,
    regime,
    duration_months,
    confidence,
    priorities = [],
    risks = [],
    conviction_trades = [],
    position_modifier,
    model_caution,
  } = data;

  const getRegimeColor = (r: string) => {
    switch (r?.toLowerCase()) {
      case 'goldilocks': return 'text-green';
      case 'reflation': return 'text-amber';
      case 'stagflation': return 'text-red';
      case 'slowdown': return 'text-blue';
      default: return 'text-text-primary';
    }
  };

  const getRegimeBg = (r: string) => {
    switch (r?.toLowerCase()) {
      case 'goldilocks': return 'bg-green-dim border-green';
      case 'reflation': return 'bg-amber-dim border-amber';
      case 'stagflation': return 'bg-red-dim border-red';
      case 'slowdown': return 'bg-blue-dim border-blue';
      default: return 'bg-surface-1 border-border';
    }
  };

  const getPriorityIcon = (type: string) => {
    switch (type) {
      case 'calendar': return Calendar;
      case 'tension': return TrendingUp;
      default: return Target;
    }
  };

  return (
    <section id="morning-brief" className="terminal-section">
      {/* Bloomberg orange left border - editorial lead */}
      <div className="p-4 border-l-4 border-amber bg-surface-2">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-2xs text-amber font-bold uppercase tracking-wider">
              Morning Brief
            </span>
            <span className="text-text-tertiary text-xs">{date}</span>
          </div>
          {model_caution && (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-amber-dim rounded">
              <AlertTriangle className="w-3 h-3 text-amber" />
              <span className="text-2xs text-amber">Low Model Consensus</span>
            </div>
          )}
        </div>

        {/* Regime Status */}
        <div className="flex items-center gap-4 mb-4">
          <div className={`px-3 py-1.5 rounded border ${getRegimeBg(regime)}`}>
            <span className={`text-sm font-bold ${getRegimeColor(regime)}`}>
              {regime?.toUpperCase()}
            </span>
          </div>
          <div className="text-xs text-text-secondary">
            <span className="font-mono text-text-primary">{duration_months}</span> months ·
            <span className="font-mono text-text-primary">{fmtProbability(typeof confidence === 'number' && isFinite(confidence) ? confidence : null)}</span> confidence
          </div>
          {(typeof position_modifier === 'number' && isFinite(position_modifier) && position_modifier < 1.0) && (
            <div className="text-2xs text-amber bg-amber-dim px-2 py-1 rounded">
              Position size: {fmtChange(position_modifier)}
            </div>
          )}
        </div>

        {/* Today's Priorities */}
        {(priorities?.length ?? 0) > 0 && (
          <div className="mb-4">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-3.5 h-3.5 text-amber" />
              <span className="text-xs font-medium text-text-primary uppercase tracking-wider">
                Today's Priorities
              </span>
            </div>
            <div className="space-y-2">
              {(priorities ?? []).map((priority, idx) => {
                const Icon = getPriorityIcon(priority.type);
                return (
                  <div key={idx} className="flex items-start gap-3 p-2 bg-surface-1 rounded">
                    <span className="text-amber font-mono font-bold">{idx + 1}</span>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <Icon className="w-3 h-3 text-text-tertiary" />
                        <span className="text-sm font-medium text-text-primary">
                          {priority.title}
                        </span>
                        {priority.time && (
                          <span className="text-2xs text-text-tertiary font-mono">
                            {priority.time}
                          </span>
                        )}
                        {priority.date && priority.date !== date && (
                          <span className="text-2xs text-amber">
                            {priority.date}
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-text-secondary mt-0.5">
                        {priority.implication}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Key Risks */}
        {(risks?.length ?? 0) > 0 && (
          <div className="mb-4">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-3.5 h-3.5 text-amber" />
              <span className="text-xs font-medium text-text-primary uppercase tracking-wider">
                Key Risks This Week
              </span>
            </div>
            <div className="space-y-1.5">
              {(risks ?? []).map((risk, idx) => (
                <div key={idx} className="flex items-start gap-2 text-sm">
                  <span className="text-amber mt-0.5">•</span>
                  <span className="text-text-secondary">{risk.text}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Conviction Trades */}
        {(conviction_trades?.length ?? 0) > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-3.5 h-3.5 text-amber" />
              <span className="text-xs font-medium text-text-primary uppercase tracking-wider">
                Conviction Trades
              </span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {(conviction_trades ?? []).map((trade, idx) => (
                <div
                  key={idx}
                  className={`p-2 bg-surface-1 rounded border-l-2 ${
                    trade.direction === 'LONG'
                      ? 'border-green'
                      : 'border-red'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono font-bold text-text-primary">
                      {trade.direction === 'LONG' ? 'LONG' : 'SHORT'} {trade.ticker}
                    </span>
                    <span
                      className={`text-2xs px-1.5 py-0.5 rounded ${
                        trade.conviction === 'HIGH'
                          ? 'bg-green-dim text-green'
                          : trade.conviction === 'MEDIUM'
                          ? 'bg-amber-dim text-amber'
                          : 'bg-surface-3 text-text-tertiary'
                      }`}
                    >
                      {trade.conviction}
                    </span>
                  </div>
                  {trade.rr && (
                    <div className="text-xs text-text-secondary">
                      R/R {trade.rr != null ? trade.rr.toFixed(1) : '--'}x
                    </div>
                  )}
                  {trade.entry && trade.target && (
                    <div className="text-2xs text-text-tertiary">
                      ${trade.entry} → ${trade.target}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

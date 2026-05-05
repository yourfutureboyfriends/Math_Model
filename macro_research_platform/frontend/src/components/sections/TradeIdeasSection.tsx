// Trade Ideas Section
// Displays actionable trade recommendations with Kelly sizing, R:R ratios, and exit conditions.

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Clock } from 'lucide-react';
import type { TradeIdeasData } from '@/types';

interface Props {
  data?: TradeIdeasData | null;
}

export function TradeIdeasSection({ data }: Props) {
  if (!data) return (
    <div className="terminal-section">
      <div className="section-header">
        <span className="section-title">TRADE IDEAS</span>
        <span style={{ color: 'var(--text-tertiary)', fontSize: '11px' }}>
          — awaiting data
        </span>
      </div>
    </div>
  );

  if (!data.ideas || data.ideas.length === 0) {
    return (
      <section id="trade-ideas" className="terminal-section">
        <div className="section-header">
          <span className="section-tag">IDEA</span>
          <h2 className="section-title">Trade Ideas</h2>
        </div>
        <div className="p-6 text-text-secondary text-sm bg-surface-1 border border-border">
          No active trade ideas. Signal threshold not met or market conditions unclear.
        </div>
      </section>
    );
  }

  const { ideas } = data;

  const getDirectionColor = (direction: string) => {
    switch (direction?.toUpperCase()) {
      case 'LONG':  return 'text-green bg-green-dim border-green';
      case 'SHORT': return 'text-red bg-red-dim border-red';
      default:      return 'text-text-secondary bg-surface-3 border-border';
    }
  };

  const getDirectionBorder = (direction: string) => {
    switch (direction?.toUpperCase()) {
      case 'LONG':  return 'border-l-4 border-l-green';
      case 'SHORT': return 'border-l-4 border-l-red';
      default:      return '';
    }
  };

  const getConvictionColor = (conviction: string) => {
    switch (conviction) {
      case 'HIGH':   return 'bg-green-dim text-green';
      case 'MEDIUM': return 'bg-amber-dim text-amber';
      case 'LOW':    return 'bg-surface-3 text-text-tertiary';
      default:       return 'bg-surface-3 text-text-secondary';
    }
  };

  const getCategoryColor = (category: string) => {
    switch (category?.toLowerCase()) {
      case 'regime':    return 'text-bloomberg';
      case 'macro':     return 'text-text-secondary';
      case 'hedge':     return 'text-amber';
      case 'defensive': return 'text-blue';
      case 'momentum':  return 'text-green';
      default:          return 'text-text-tertiary';
    }
  };

  return (
    <section id="trade-ideas" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">IDEA</span>
        <h2 className="section-title">Trade Ideas</h2>
        <Badge variant="neutral" className="ml-2">
          {ideas.length} Active · {(data.risk_budget || 1.0) * 100}% Risk Budget
        </Badge>
      </div>

      <div className="space-y-3">
        {(ideas ?? []).map((idea) => (
          <Card key={idea.id} className={`p-4 ${getDirectionBorder(idea.direction)} ${getDirectionColor(idea.direction)}`}>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                {/* Ticker, direction, conviction level, and category */}
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className="font-mono font-bold text-lg text-text-primary">
                    {idea.direction} {idea.ticker}
                  </span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getConvictionColor(idea.conviction)}`}>
                    {idea.conviction}
                  </span>
                  <span className={`text-2xs uppercase ${getCategoryColor(idea.category)}`}>
                    {idea.category}
                  </span>
                  {idea.regime_valid ? (
                    <span className="flex items-center gap-1 text-2xs text-green">
                      <CheckCircle className="w-3 h-3" />
                      Regime Valid
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-2xs text-amber">
                      <AlertTriangle className="w-3 h-3" />
                      Review
                    </span>
                  )}
                </div>

                {/* Trade thesis */}
                <p className="text-sm text-text-secondary mb-3">{idea.thesis}</p>

                {/* Price levels and sizing */}
                <div className="grid grid-cols-6 gap-3 text-sm mb-3">
                  {idea.entry && (
                    <div>
                      <div className="text-2xs text-text-tertiary uppercase">Entry</div>
                      <div className="font-mono font-medium">${(typeof idea.entry === 'number' && isFinite(idea.entry)) ? idea.entry.toFixed(2) : '—'}</div>
                    </div>
                  )}
                  {idea.target && (
                    <div>
                      <div className="text-2xs text-text-tertiary uppercase">Target</div>
                      <div className="font-mono font-medium text-green">${(typeof idea.target === 'number' && isFinite(idea.target)) ? idea.target.toFixed(2) : '—'}</div>
                    </div>
                  )}
                  {idea.stop && (
                    <div>
                      <div className="text-2xs text-text-tertiary uppercase">Stop</div>
                      <div className="font-mono font-medium text-red">${(typeof idea.stop === 'number' && isFinite(idea.stop)) ? idea.stop.toFixed(2) : '—'}</div>
                    </div>
                  )}
                  {idea.rr && idea.rr > 0 && (
                    <div>
                      <div className="text-2xs text-text-tertiary uppercase">R:R</div>
                      <div className="font-mono font-bold text-text-primary">{(typeof idea.rr === 'number' && isFinite(idea.rr)) ? idea.rr.toFixed(1) : '—'}x</div>
                    </div>
                  )}
                  {idea.kelly_size && idea.kelly_size > 0 && (
                    <div>
                      <div className="text-2xs text-text-tertiary uppercase">Kelly</div>
                      <div className="font-mono text-text-primary">{(typeof idea.kelly_size === 'number' && isFinite(idea.kelly_size)) ? Math.min(100, idea.kelly_size > 1 ? idea.kelly_size : idea.kelly_size * 100).toFixed(1) : '—'}%</div>
                    </div>
                  )}
                  {idea.suggested_size && idea.suggested_size > 0 && (
                    <div>
                      <div className="text-2xs text-text-tertiary uppercase">Suggested</div>
                      <div className="font-mono font-bold text-bloomberg">{(typeof idea.suggested_size === 'number' && isFinite(idea.suggested_size)) ? Math.min(100, idea.suggested_size > 1 ? idea.suggested_size : idea.suggested_size * 100).toFixed(1) : '—'}%</div>
                    </div>
                  )}
                </div>

                {/* Exit conditions (first 3 shown) */}
                {idea.exit_conditions && idea.exit_conditions.length > 0 && (
                  <div className="mb-3">
                    <div className="text-2xs text-text-tertiary uppercase mb-1">Exit Conditions</div>
                    <ul className="text-xs text-text-secondary space-y-0.5">
                      {idea.exit_conditions.slice(0, 3).map((condition, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="text-amber mt-0.5">→</span>
                          <span>{condition}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Footer: time metrics and live P&L */}
                <div className="flex items-center gap-4 text-2xs text-text-tertiary pt-2 border-t border-border-subtle">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {idea.horizon_days}d horizon
                  </span>
                  <span>{idea.days_open}d open</span>
                  {idea.pnl_pct !== 0 && (
                    <span className={idea.pnl_pct >= 0 ? 'text-green' : 'text-red'}>
                      {idea.pnl_pct >= 0 ? '+' : ''}{(typeof idea.pnl_pct === 'number' && isFinite(idea.pnl_pct)) ? idea.pnl_pct.toFixed(1) : '—'}%
                    </span>
                  )}
                </div>
              </div>

              <div className="ml-4">
                {idea.direction === 'LONG'
                  ? <TrendingUp className="w-6 h-6 text-green" />
                  : <TrendingDown className="w-6 h-6 text-red" />
                }
              </div>
            </div>
          </Card>
        ))}
      </div>

      <div className="mt-3 text-2xs text-text-tertiary flex items-center justify-between">
        <span>Regime: {data.regime || 'Unknown'}</span>
        <span>
          Last updated: {data.generated_at
            ? new Date(data.generated_at).toLocaleTimeString()
            : 'Real-time'}
        </span>
      </div>
    </section>
  );
}

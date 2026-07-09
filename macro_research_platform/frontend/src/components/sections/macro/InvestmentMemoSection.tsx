// Phase 8 — Investment Memo Section (Redesigned)
// Investment memo with terminal aesthetic
// POLISH-7: Added Decision Log for tracking historical decisions

import { FileText, Target, AlertTriangle, Lightbulb, History, CheckCircle, XCircle, Clock } from 'lucide-react';
import { useState } from 'react';
import type { InvestmentMemoData } from '@/types';
import { useMacroStore } from '@/store/macroStore';

interface Decision {
  id: string;
  date: string;
  action: 'ENTER' | 'EXIT' | 'HOLD' | 'REVIEW';
  ticker: string;
  direction: 'LONG' | 'SHORT';
  size_pct: number;
  rationale: string;
  outcome?: 'PENDING' | 'WIN' | 'LOSS';
  pnl_pct?: number;
}

interface InvestmentMemoSectionProps {
  data?: InvestmentMemoData & {
    decisionLog?: Decision[];
  };
}

export function InvestmentMemoSection({ data }: InvestmentMemoSectionProps) {
  const _fullDash = useMacroStore((s) => s.fullDashboard);
  if (!data) data = (_fullDash as any)?.["investmentMemo"] as any;

  if (!data) return null;

  const [showDecisionLog, setShowDecisionLog] = useState(false);

  const getDecisionIcon = (action: string) => {
    switch (action) {
      case 'ENTER': return <CheckCircle className="w-3 h-3 text-green" />;
      case 'EXIT': return <XCircle className="w-3 h-3 text-red" />;
      case 'HOLD': return <Clock className="w-3 h-3 text-amber" />;
      default: return <History className="w-3 h-3 text-text-tertiary" />;
    }
  };

  const getOutcomeColor = (outcome?: string) => {
    switch (outcome) {
      case 'WIN': return 'text-green';
      case 'LOSS': return 'text-red';
      default: return 'text-text-tertiary';
    }
  };

  return (
    <div id="investment-memo" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">38</span>
          <h2 className="section-title">Investment Memo</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Regime Summary */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2 mb-2">
            <FileText className="w-3 h-3 text-amber" />
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">
              Regime Summary
            </span>
          </div>
          <p className="text-xs text-text-primary leading-relaxed">{data.regimeSummary}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* Key Points */}
          <div className="p-3 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-2">
              <Target className="w-3 h-3 text-green" />
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">
                Key Points
              </span>
            </div>
            <ul className="space-y-1.5">
              {(data.keyPoints ?? []).map((point, index) => (
                <li key={index} className="flex items-start gap-2 text-xs text-text-secondary">
                  <span className="text-green">›</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Risks */}
          <div className="p-3 bg-surface-1 border border-border">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-3 h-3 text-red" />
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">
                Risks
              </span>
            </div>
            <ul className="space-y-1.5">
              {(data.risks ?? []).map((risk, index) => (
                <li key={index} className="flex items-start gap-2 text-xs text-text-secondary">
                  <span className="text-red">›</span>
                  <span>{risk}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Opportunities */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center gap-2 mb-2">
            <Lightbulb className="w-3 h-3 text-blue" />
            <span className="text-2xs text-text-tertiary uppercase tracking-wider">
              Opportunities
            </span>
          </div>
          <ul className="space-y-1.5">
            {(data.opportunities ?? []).map((opportunity, index) => (
              <li key={index} className="flex items-start gap-2 text-xs text-text-secondary">
                <span className="text-blue">›</span>
                <span>{opportunity}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* POLISH-7: Decision Log */}
        {data.decisionLog && data.decisionLog.length > 0 && (
          <div className="p-3 bg-surface-1 border border-border">
            <div
              className="flex items-center gap-2 mb-2 cursor-pointer hover:opacity-80"
              onClick={() => setShowDecisionLog(!showDecisionLog)}
            >
              <History className="w-3 h-3 text-bloomberg" />
              <span className="text-2xs text-text-tertiary uppercase tracking-wider">
                Decision Log ({data.decisionLog.length} entries)
              </span>
              <span className="text-xs text-bloomberg ml-auto">
                {showDecisionLog ? '▼' : '▶'}
              </span>
            </div>
            {showDecisionLog && (
              <div className="space-y-2">
                {data.decisionLog.map((decision) => (
                  <div
                    key={decision.id}
                    className="p-2 bg-surface-2 border border-border-subtle rounded text-xs"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        {getDecisionIcon(decision.action)}
                        <span className="font-mono font-medium text-text-primary">
                          {decision.action} {decision.ticker}
                        </span>
                        <span
                          className={`px-1.5 py-0.5 rounded text-2xs ${
                            decision.direction === 'LONG'
                              ? 'bg-green/20 text-green'
                              : 'bg-red/20 text-red'
                          }`}
                        >
                          {decision.direction}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-text-tertiary">{decision.date}</span>
                        {decision.pnl_pct !== undefined && (
                          <span className={`font-mono ${getOutcomeColor(decision.outcome)}`}>
                            {decision.pnl_pct >= 0 ? '+' : ''}{decision.pnl_pct.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-text-secondary">
                      <span>Size: {(decision.size_pct * 100).toFixed(1)}%</span>
                      <span className="text-text-tertiary truncate max-w-[60%]">{decision.rationale}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

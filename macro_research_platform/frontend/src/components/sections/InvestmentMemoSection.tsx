// Phase 8 — Investment Memo Section (Redesigned)
// Investment memo with terminal aesthetic

import { FileText, Target, AlertTriangle, Lightbulb } from 'lucide-react';
import type { InvestmentMemoData } from '@/types';

interface InvestmentMemoSectionProps {
  data?: InvestmentMemoData;
}

export function InvestmentMemoSection({ data }: InvestmentMemoSectionProps) {
  if (!data) return null;

  return (
    <div id="investment-memo" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">28</span>
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
              {data.keyPoints.map((point, index) => (
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
              {data.risks.map((risk, index) => (
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
            {data.opportunities.map((opportunity, index) => (
              <li key={index} className="flex items-start gap-2 text-xs text-text-secondary">
                <span className="text-blue">›</span>
                <span>{opportunity}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

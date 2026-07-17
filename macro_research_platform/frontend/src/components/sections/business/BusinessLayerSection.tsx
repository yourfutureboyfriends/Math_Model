// Phase 8 — Business Layer Outputs Section (Redesigned) + Phase 3D Business Hook + Phase 4B Performance
// Business outputs with terminal aesthetic using useBusinessLayer
// Wrapped with React.memo for performance optimization

import { useState, memo } from 'react';
import { FileText, ChevronDown, ChevronRight, TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle, Lightbulb, Target } from 'lucide-react';
import { useBusinessLayer } from '@/hooks/useBusinessLayer';
import { LoadingState } from '@/components/ui';
import { fmtChange } from '@/utils/format';
import {
  normalizeRecommendations,
  normalizeExpectedReturns,
  normalizePositionSizing,
  type BackendSummary,
} from '@/lib/businessAdapter';

// Type definitions matching API response
interface DecisionLogItem {
  date: string;
  action?: string;
  asset?: string;
  headline?: string;
  timestamp?: string;
  recommendationType?: string;
  conviction?: string;
}

function getConvictionTag(conviction: string): string {
  const c = conviction.toLowerCase();
  if (c.includes('high')) return 'signal-tag bullish';
  if (c.includes('medium')) return 'signal-tag warning';
  if (c.includes('low')) return 'signal-tag bearish';
  return 'signal-tag neutral';
}

function getPositionSizeIcon(size: string) {
  const s = size.toLowerCase();
  if (s.includes('overweight') || s.includes('large')) return <TrendingUp className="w-3 h-3 text-green" />;
  if (s.includes('underweight') || s.includes('small') || s.includes('no position')) return <TrendingDown className="w-3 h-3 text-red" />;
  return <Minus className="w-3 h-3 text-text-tertiary" />;
}

export const BusinessLayerSection = memo(function BusinessLayerSection() {
  const { recommendations, decisionLog, loading, error, refresh } = useBusinessLayer();

  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    recommendations: true,
    expectedReturns: false,
    positionSizing: false,
    signalScorecard: false,
    decisionLog: false,
  });

  if (loading) {
    return <LoadingState message="Loading business layer..." />;
  }

  if (error) {
    return (
      <div className="p-4 bg-surface-1 border border-border text-center">
        <div className="text-amber mb-2">{error}</div>
        <button onClick={refresh} className="px-3 py-1 bg-surface-2 text-xs font-mono">Retry</button>
      </div>
    );
  }

  // Normalize data using adapter layer
  // Backend returns objects, frontend components expect normalized arrays
  const expectedReturns = normalizeExpectedReturns(recommendations?.expected_returns || []);
  const positionSizing = normalizePositionSizing(recommendations?.position_sizing || []);
  const signalScorecard = recommendations?.signal_scorecard || [];
  const decisionEntries: DecisionLogItem[] = decisionLog?.entries || [];

  // summary can be string (legacy), object (current), or null
  const summary = recommendations?.summary as BackendSummary | string | null | undefined;
  const parsedRecommendations = normalizeRecommendations(summary);

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const getConfidenceTag = (confidence: string) => {
    switch (confidence.toLowerCase()) {
      case 'high':
        return 'signal-tag bullish';
      case 'medium':
        return 'signal-tag warning';
      case 'low':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  return (
    <div id="business-layer" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Business Layer</h2>
        </div>
      </div>

      <div className="space-y-2">
        {/* Recommendations */}
        {parsedRecommendations.length > 0 && (
          <div className="border border-border bg-surface-1">
            <button
              onClick={() => toggleSection('recommendations')}
              className="w-full flex items-center justify-between p-2 bg-surface-2 hover:bg-surface-3 transition-colors"
            >
              <div className="flex items-center gap-2">
                <FileText className="w-3 h-3 text-amber" />
                <span className="text-xs font-medium text-text-primary">Recommendations</span>
                <span className="signal-tag bullish">LIVE</span>
              </div>
              {expandedSections.recommendations ? (
                <ChevronDown className="w-3 h-3 text-text-tertiary" />
              ) : (
                <ChevronRight className="w-3 h-3 text-text-tertiary" />
              )}
            </button>
            {expandedSections.recommendations && (
              <div className="p-2 space-y-2">
                {parsedRecommendations.map((rec, idx) => (
                  <div key={idx} className="border border-border bg-surface-2">
                    {/* Header */}
                    <div className="p-2 border-b border-border-subtle bg-surface-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {rec.type === 'Research' && <Target className="w-3 h-3 text-blue" />}
                          {rec.type === 'Portfolio' && <TrendingUp className="w-3 h-3 text-green" />}
                          {rec.type === 'Action' && <Lightbulb className="w-3 h-3 text-amber" />}
                          <span className="text-2xs font-medium text-text-secondary uppercase">{rec.type}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          {getPositionSizeIcon(rec.positionSize)}
                          <span className={getConvictionTag(rec.conviction)}>{rec.conviction}</span>
                        </div>
                      </div>
                      <h4 className="mt-1 text-sm font-medium text-text-primary">{rec.headline}</h4>
                      <p className="mt-0.5 text-xs text-text-secondary">{rec.detail}</p>
                    </div>

                    {/* Details */}
                    <div className="p-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                      {rec.supportingSignals.length > 0 && (
                        <div>
                          <div className="flex items-center gap-1 text-2xs text-text-tertiary mb-1">
                            <CheckCircle className="w-3 h-3 text-green" />
                            Supporting
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {rec.supportingSignals.map((signal, sidx) => (
                              <span key={sidx} className="signal-tag bullish text-2xs">{signal}</span>
                            ))}
                          </div>
                        </div>
                      )}

                      {rec.opposingSignals.length > 0 && (
                        <div>
                          <div className="flex items-center gap-1 text-2xs text-text-tertiary mb-1">
                            <TrendingDown className="w-3 h-3 text-red" />
                            Opposing
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {rec.opposingSignals.map((signal, sidx) => (
                              <span key={sidx} className="signal-tag bearish text-2xs">{signal}</span>
                            ))}
                          </div>
                        </div>
                      )}

                      {rec.riskToView && (
                        <div className="md:col-span-2">
                          <div className="flex items-center gap-1 text-2xs text-text-tertiary mb-1">
                            <AlertTriangle className="w-3 h-3 text-amber" />
                            Risk
                          </div>
                          <p className="text-xs text-text-secondary">{rec.riskToView}</p>
                        </div>
                      )}

                      {rec.suggestedAction && (
                        <div className="md:col-span-2">
                          <div className="text-2xs text-text-tertiary mb-1">Action</div>
                          <p className="text-xs text-blue">{rec.suggestedAction}</p>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Expected Returns */}
        {expectedReturns.length > 0 && (
          <div className="border border-border bg-surface-1">
            <button
              onClick={() => toggleSection('expectedReturns')}
              className="w-full flex items-center justify-between p-2 bg-surface-2 hover:bg-surface-3 transition-colors"
            >
              <div className="flex items-center gap-2">
                <TrendingUp className="w-3 h-3 text-green" />
                <span className="text-xs font-medium text-text-primary">Expected Returns</span>
                <span className="signal-tag neutral">{expectedReturns.length}</span>
              </div>
              {expandedSections.expectedReturns ? (
                <ChevronDown className="w-3 h-3 text-text-tertiary" />
              ) : (
                <ChevronRight className="w-3 h-3 text-text-tertiary" />
              )}
            </button>
            {expandedSections.expectedReturns && (
              <div className="p-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                  {expectedReturns.map((item) => (
                    <div key={item.asset_class} className="p-2 border border-border bg-surface-2">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-text-primary">{item.asset_class}</span>
                        <span className={getConfidenceTag(item.conviction || 'Medium')}>{item.conviction || 'Medium'}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-2xs text-text-tertiary block">Return</span>
                          <div className="font-mono text-text-primary">
                            {fmtChange(item.expected_return_score / 100)}
                          </div>
                        </div>
                        <div>
                          <span className="text-2xs text-text-tertiary block">Sharpe</span>
                          <div className={`font-mono ${(item.sharpe_estimate || 0) > 0 ? 'text-green' : (item.sharpe_estimate || 0) < 0 ? 'text-red' : 'text-text-secondary'}`}>
                            {item.sharpe_estimate != null ? item.sharpe_estimate.toFixed(2) : '--'}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Position Sizing */}
        {positionSizing.length > 0 && (
          <div className="border border-border bg-surface-1">
            <button
              onClick={() => toggleSection('positionSizing')}
              className="w-full flex items-center justify-between p-2 bg-surface-2 hover:bg-surface-3 transition-colors"
            >
              <div className="flex items-center gap-2">
                <Target className="w-3 h-3 text-blue" />
                <span className="text-xs font-medium text-text-primary">Position Sizing</span>
              </div>
              {expandedSections.positionSizing ? (
                <ChevronDown className="w-3 h-3 text-text-tertiary" />
              ) : (
                <ChevronRight className="w-3 h-3 text-text-tertiary" />
              )}
            </button>
            {expandedSections.positionSizing && (
              <div className="p-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                  {positionSizing.map((item) => (
                    <div
                      key={item.asset_class}
                      className={`p-2 border ${
                        item.recommended_weight > 0 ? 'border-green/30 bg-green-dim' : item.recommended_weight < 0 ? 'border-red/30 bg-red-dim' : 'border-border bg-surface-2'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-text-primary">{item.asset_class}</span>
                        {item.recommended_weight > 0 ? <TrendingUp className="w-3 h-3 text-green" /> : item.recommended_weight < 0 ? <TrendingDown className="w-3 h-3 text-red" /> : <Minus className="w-3 h-3 text-text-tertiary" />}
                      </div>
                      <div className="text-base font-mono font-bold text-text-primary">
                        {fmtChange(item.recommended_weight / 100)}
                      </div>
                      <div className="flex items-center justify-between mt-1">
                        <span className={getConfidenceTag(item.conviction || 'Medium')}>{item.conviction || 'Medium'}</span>
                        <span className="text-2xs text-text-tertiary">{item.bucket || 'Neutral'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Signal Scorecard */}
        {signalScorecard.length > 0 && (
          <div className="border border-border bg-surface-1">
            <button
              onClick={() => toggleSection('signalScorecard')}
              className="w-full flex items-center justify-between p-2 bg-surface-2 hover:bg-surface-3 transition-colors"
            >
              <span className="text-xs font-medium text-text-primary">Signal Scorecard</span>
              {expandedSections.signalScorecard ? (
                <ChevronDown className="w-3 h-3 text-text-tertiary" />
              ) : (
                <ChevronRight className="w-3 h-3 text-text-tertiary" />
              )}
            </button>
            {expandedSections.signalScorecard && (
              <div className="p-2">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border-subtle">
                      <th className="text-left py-1.5 px-2 text-2xs text-text-tertiary uppercase">Signal</th>
                      <th className="text-left py-1.5 px-2 text-2xs text-text-tertiary uppercase">Category</th>
                      <th className="text-center py-1.5 px-2 text-2xs text-text-tertiary uppercase">Status</th>
                      <th className="text-center py-1.5 px-2 text-2xs text-text-tertiary uppercase">Conf</th>
                    </tr>
                  </thead>
                  <tbody>
                    {signalScorecard.map((item: any) => (
                      <tr key={item.signal} className="border-b border-border-subtle last:border-0">
                        <td className="py-1.5 px-2 text-xs text-text-primary">{item.signal}</td>
                        <td className="py-1.5 px-2 text-xs text-text-secondary">{item.category}</td>
                        <td className="py-1.5 px-2 text-center">
                          <span className={item.status === 'Active' ? 'signal-tag bullish' : 'signal-tag neutral'}>{item.status}</span>
                        </td>
                        <td className="py-1.5 px-2 text-center">
                          <span className={getConfidenceTag(item.confidence)}>{item.confidence.charAt(0)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Decision Log */}
        {decisionEntries.length > 0 && (
          <div className="border border-border bg-surface-1">
            <button
              onClick={() => toggleSection('decisionLog')}
              className="w-full flex items-center justify-between p-2 bg-surface-2 hover:bg-surface-3 transition-colors"
            >
              <span className="text-xs font-medium text-text-primary">Decision Log</span>
              {expandedSections.decisionLog ? (
                <ChevronDown className="w-3 h-3 text-text-tertiary" />
              ) : (
                <ChevronRight className="w-3 h-3 text-text-tertiary" />
              )}
            </button>
            {expandedSections.decisionLog && (
              <div className="p-2">
                <div className="space-y-1">
                  {decisionEntries.map((item, idx) => (
                    <div key={`${item.date}-${idx}`} className="flex items-center gap-3 p-2 border-b border-border-subtle last:border-0">
                      <div className="text-2xs text-text-tertiary w-20 shrink-0">
                        {item.date}
                      </div>
                      <span className="signal-tag neutral text-2xs shrink-0">{item.recommendationType || 'Action'}</span>
                      <span className="flex-1 text-xs text-text-secondary truncate">{item.headline || item.action}</span>
                      <span className={getConfidenceTag(item.conviction || 'Medium')}>{(item.conviction || 'M').charAt(0)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!parsedRecommendations.length &&
          expectedReturns.length === 0 &&
          positionSizing.length === 0 &&
          signalScorecard.length === 0 &&
          decisionEntries.length === 0 && (
            <div className="p-3 bg-surface-1 border border-border text-center">
              <p className="text-xs text-text-secondary">
                Business outputs not found. Run{' '}
                <code className="text-amber">python pipeline.py --mode run-sample</code>
              </p>
            </div>
          )}
      </div>
    </div>
  );
});

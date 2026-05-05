// Phase 8 — Business Layer Outputs Section (Redesigned)
// Business outputs with terminal aesthetic

import { useState } from 'react';
import { FileText, ChevronDown, ChevronRight, TrendingUp, TrendingDown, Minus, AlertTriangle, CheckCircle, Lightbulb, Target } from 'lucide-react';
import type { BusinessLayerData } from '@/types';

interface BusinessLayerSectionProps {
  data?: BusinessLayerData;
}

interface ParsedRecommendation {
  type: string;
  headline: string;
  detail: string;
  conviction: string;
  positionSize: string;
  supportingSignals: string[];
  opposingSignals: string[];
  riskToView: string;
  dataToWatch: string[];
  businessRelevance: string;
  suggestedAction: string;
}

function parseRecommendations(markdown: string): ParsedRecommendation[] {
  const recommendations: ParsedRecommendation[] = [];
  const sections = markdown.split('## ').filter(s => s.trim());

  for (const section of sections) {
    const lines = section.split('\n').filter(l => l.trim());
    if (lines.length === 0) continue;

    const rec: ParsedRecommendation = {
      type: lines[0].replace(' View', '').trim(),
      headline: '',
      detail: '',
      conviction: '',
      positionSize: '',
      supportingSignals: [],
      opposingSignals: [],
      riskToView: '',
      dataToWatch: [],
      businessRelevance: '',
      suggestedAction: '',
    };

    for (const line of lines.slice(1)) {
      const trimmed = line.trim();
      if (trimmed.startsWith('**Headline:**')) rec.headline = trimmed.replace('**Headline:**', '').trim();
      else if (trimmed.startsWith('**Detail:**')) rec.detail = trimmed.replace('**Detail:**', '').trim();
      else if (trimmed.startsWith('**Conviction:**')) rec.conviction = trimmed.replace('**Conviction:**', '').trim();
      else if (trimmed.startsWith('**Position Size:**')) rec.positionSize = trimmed.replace('**Position Size:**', '').trim();
      else if (trimmed.startsWith('**Supporting Signals:**')) {
        const signals = trimmed.replace('**Supporting Signals:**', '').trim();
        rec.supportingSignals = signals.split(',').map(s => s.trim()).filter(s => s && s !== 'None');
      }
      else if (trimmed.startsWith('**Opposing Signals:**')) {
        const signals = trimmed.replace('**Opposing Signals:**', '').trim();
        rec.opposingSignals = signals.split(',').map(s => s.trim()).filter(s => s && s !== 'None');
      }
      else if (trimmed.startsWith('**Risk to View:**')) rec.riskToView = trimmed.replace('**Risk to View:**', '').trim();
      else if (trimmed.startsWith('**Data to Watch:**')) {
        const data = trimmed.replace('**Data to Watch:**', '').trim();
        rec.dataToWatch = data.split(',').map(s => s.trim()).filter(s => s);
      }
      else if (trimmed.startsWith('**Business Relevance:**')) rec.businessRelevance = trimmed.replace('**Business Relevance:**', '').trim();
      else if (trimmed.startsWith('**Suggested Action:**')) rec.suggestedAction = trimmed.replace('**Suggested Action:**', '').trim();
    }

    if (rec.headline) recommendations.push(rec);
  }

  return recommendations;
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

export function BusinessLayerSection({ data }: BusinessLayerSectionProps) {
  if (!data) return null;

  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    recommendations: true,
    expectedReturns: false,
    positionSizing: false,
    signalScorecard: false,
    decisionLog: false,
  });

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

  const parsedRecommendations = data.recommendations ? parseRecommendations(data.recommendations) : [];

  return (
    <div id="business-layer" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">39</span>
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
        {data.expectedReturns.length > 0 && (
          <div className="border border-border bg-surface-1">
            <button
              onClick={() => toggleSection('expectedReturns')}
              className="w-full flex items-center justify-between p-2 bg-surface-2 hover:bg-surface-3 transition-colors"
            >
              <div className="flex items-center gap-2">
                <TrendingUp className="w-3 h-3 text-green" />
                <span className="text-xs font-medium text-text-primary">Expected Returns</span>
                <span className="signal-tag neutral">{data.expectedReturns.length}</span>
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
                  {(data.expectedReturns ?? []).map((item) => (
                    <div key={item.assetOrSector} className="p-2 border border-border bg-surface-2">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-text-primary">{item.assetOrSector}</span>
                        <span className={getConfidenceTag(item.confidence)}>{item.confidence}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-2xs text-text-tertiary block">Return</span>
                          <div className="font-mono text-text-primary">
                            {item.expectedReturn > 0 ? '+' : ''}{(item.expectedReturn * 100).toFixed(1)}%
                          </div>
                        </div>
                        <div>
                          <span className="text-2xs text-text-tertiary block">Sharpe</span>
                          <div className={`font-mono ${item.sharpeEstimate > 0 ? 'text-green' : item.sharpeEstimate < 0 ? 'text-red' : 'text-text-secondary'}`}>
                            {item.sharpeEstimate.toFixed(2)}
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
        {data.positionSizing.length > 0 && (
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
                  {(data.positionSizing ?? []).map((item) => (
                    <div
                      key={item.assetOrSector}
                      className={`p-2 border ${
                        item.suggestedSize > 0 ? 'border-green/30 bg-green-dim' : item.suggestedSize < 0 ? 'border-red/30 bg-red-dim' : 'border-border bg-surface-2'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-text-primary">{item.assetOrSector}</span>
                        {item.suggestedSize > 0 ? <TrendingUp className="w-3 h-3 text-green" /> : item.suggestedSize < 0 ? <TrendingDown className="w-3 h-3 text-red" /> : <Minus className="w-3 h-3 text-text-tertiary" />}
                      </div>
                      <div className="text-base font-mono font-bold text-text-primary">
                        {item.suggestedSize > 0 ? '+' : ''}{item.suggestedSize.toFixed(1)}%
                      </div>
                      <div className="flex items-center justify-between mt-1">
                        <span className={getConfidenceTag(item.conviction)}>{item.conviction}</span>
                        <span className="text-2xs text-text-tertiary">{item.bucket}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Signal Scorecard */}
        {data.signalScorecard.length > 0 && (
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
                    {(data.signalScorecard ?? []).map((item) => (
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
        {data.decisionLog.length > 0 && (
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
                  {(data.decisionLog ?? []).map((item, idx) => (
                    <div key={`${item.timestamp}-${idx}`} className="flex items-center gap-3 p-2 border-b border-border-subtle last:border-0">
                      <div className="text-2xs text-text-tertiary w-20 shrink-0">
                        {/* FIXED (BUG 8): Use ISO date format */}
                        {new Date(item.timestamp).toISOString().split('T')[0]}
                      </div>
                      <span className="signal-tag neutral text-2xs shrink-0">{item.recommendationType}</span>
                      <span className="flex-1 text-xs text-text-secondary truncate">{item.headline}</span>
                      <span className={getConfidenceTag(item.conviction)}>{item.conviction.charAt(0)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!data.recommendations &&
          data.expectedReturns.length === 0 &&
          data.positionSizing.length === 0 &&
          data.signalScorecard.length === 0 &&
          data.decisionLog.length === 0 && (
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
}

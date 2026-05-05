// Phase 8 — News Sentiment Section (Redesigned)
// NLP-based sentiment scoring with terminal aesthetic

import { Newspaper, TrendingUp, TrendingDown, Minus, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import type { NewsSentimentData } from '@/types';

interface NewsSentimentSectionProps {
  data?: NewsSentimentData;
}

export function NewsSentimentSection({ data }: NewsSentimentSectionProps) {
  const [showBearish, setShowBearish] = useState(false);
  const [showBullish, setShowBullish] = useState(false);

  if (!data) return null;

  const getSentimentColor = (score: number) => {
    if (score > 20) return 'text-green';
    if (score > 5) return 'text-amber';
    if (score > -5) return 'text-text-secondary';
    if (score > -20) return 'text-amber';
    return 'text-red';
  };

  const getSentimentTag = (label: string) => {
    switch (label) {
      case 'Bullish':
      case 'Slightly Bullish':
        return 'signal-tag bullish';
      case 'Bearish':
      case 'Slightly Bearish':
        return 'signal-tag bearish';
      default:
        return 'signal-tag neutral';
    }
  };

  const getMomentumIcon = (momentum: number) => {
    if (momentum > 5) return <TrendingUp className="w-3 h-3 text-green" />;
    if (momentum < -5) return <TrendingDown className="w-3 h-3 text-red" />;
    return <Minus className="w-3 h-3 text-text-tertiary" />;
  };

  const overallPosition = ((data.overall?.score || 0) + 100) / 2;

  return (
    <div id="news-sentiment" className="terminal-section">
      {/* Section Header */}
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">33</span>
          <h2 className="section-title">News Sentiment</h2>
        </div>
      </div>

      <div className="space-y-3">
        {/* Overall score gauge */}
        <div className="p-3 bg-surface-1 border border-border">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Newspaper className="w-3 h-3 text-text-secondary" />
              <span className="text-xs font-medium text-text-primary">Overall</span>
            </div>
            <div className="flex items-center gap-2">
              {getMomentumIcon(data.overall?.momentum || 0)}
              <span className="text-2xs text-text-tertiary">{data.overall?.momentumLabel}</span>
            </div>
          </div>

          {/* Gauge bar */}
          <div className="relative h-2 bg-surface-4 mb-2">
            <div className="absolute inset-0 bg-gradient-to-r from-red via-text-tertiary to-green" />
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-text-tertiary z-10"
              style={{ left: `${overallPosition}%` }}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-baseline gap-2">
              <span className={`text-xl font-bold font-mono ${getSentimentColor(data.overall?.score || 0)}`}>
                {data.overall?.score?.toFixed(1) || '0.0'}
              </span>
              <span className={getSentimentTag(data.overall?.label || 'Neutral')}>
                {data.overall?.label}
              </span>
            </div>
            <span className="text-2xs text-text-tertiary">
              {data.overall?.articleCount || 0} articles
            </span>
          </div>
        </div>

        {/* Theme breakdown */}
        <div className="grid grid-cols-3 gap-2">
          {data.byTheme?.inflation && (
            <div className="p-2 bg-surface-1 border border-border text-center">
              <div className="text-2xs text-text-tertiary mb-1">Inflation</div>
              <div className={`text-base font-bold font-mono ${getSentimentColor(data.byTheme.inflation.score)}`}>
                {data.byTheme.inflation.score.toFixed(1)}
              </div>
              <span className={getSentimentTag(data.byTheme.inflation.label)}>
                {data.byTheme.inflation.label.replace('Slightly ', 'S-')}
              </span>
              <div className="text-2xs text-text-tertiary mt-1">
                {data.byTheme.inflation.articleCount}
              </div>
            </div>
          )}

          {data.byTheme?.growth && (
            <div className="p-2 bg-surface-1 border border-border text-center">
              <div className="text-2xs text-text-tertiary mb-1">Growth</div>
              <div className={`text-base font-bold font-mono ${getSentimentColor(data.byTheme.growth.score)}`}>
                {data.byTheme.growth.score.toFixed(1)}
              </div>
              <span className={getSentimentTag(data.byTheme.growth.label)}>
                {data.byTheme.growth.label.replace('Slightly ', 'S-')}
              </span>
              <div className="text-2xs text-text-tertiary mt-1">
                {data.byTheme.growth.articleCount}
              </div>
            </div>
          )}

          {data.byTheme?.fed && (
            <div className="p-2 bg-surface-1 border border-border text-center">
              <div className="text-2xs text-text-tertiary mb-1">Fed</div>
              <div className={`text-base font-bold font-mono ${getSentimentColor(data.byTheme.fed.score)}`}>
                {data.byTheme.fed.score.toFixed(1)}
              </div>
              <span className={getSentimentTag(data.byTheme.fed.label)}>
                {data.byTheme.fed.label.replace('Slightly ', 'S-')}
              </span>
              <div className="text-2xs text-text-tertiary mt-1">
                {data.byTheme.fed.articleCount}
              </div>
            </div>
          )}
        </div>

        {/* Regime consistency */}
        {data.regimeConsistent !== undefined && (
          <div className={`p-3 border ${data.regimeConsistent ? 'bg-green-dim border-green' : 'bg-amber-dim border-amber'}`}>
            <div className="flex items-center gap-2">
              {data.regimeConsistent ? (
                <>
                  <div className="w-2 h-2 bg-green" />
                  <span className="text-xs text-green">Consistent with regime</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-3 h-3 text-amber" />
                  <span className="text-xs text-amber">Diverges — monitor for shift</span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Top bearish headlines - FIXED: BUG-F10 - Show 'No articles' when empty */}
        <div>
          <button
            onClick={() => setShowBearish(!showBearish)}
            className="flex items-center justify-between w-full p-2 bg-surface-1 border border-border hover:bg-surface-2 transition-colors"
          >
            <span className="text-xs font-medium text-red">Top Bearish</span>
            {showBearish ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          {showBearish && (
            <div className="mt-1 space-y-1">
              {(data.topBearishHeadlines ?? []).length > 0 ? (
                data.topBearishHeadlines.slice(0, 3).map((headline, idx) => (
                  <div key={idx} className="p-2 bg-surface-2 border border-border-subtle">
                    <div className="text-xs text-text-secondary mb-0.5">{headline.headline}</div>
                    <div className="flex items-center justify-between text-2xs">
                      <span className="text-text-tertiary">{headline.source}</span>
                      <span className="font-mono text-red">{headline.score.toFixed(0)}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-2 text-text-secondary text-xs">No bearish articles today</div>
              )}
            </div>
          )}
        </div>

        {/* Top bullish headlines - FIXED: BUG-F10 - Show 'No articles' when empty */}
        <div>
          <button
            onClick={() => setShowBullish(!showBullish)}
            className="flex items-center justify-between w-full p-2 bg-surface-1 border border-border hover:bg-surface-2 transition-colors"
          >
            <span className="text-xs font-medium text-green">Top Bullish</span>
            {showBullish ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          {showBullish && (
            <div className="mt-1 space-y-1">
              {(data.topBullishHeadlines ?? []).length > 0 ? (
                data.topBullishHeadlines.slice(0, 3).map((headline, idx) => (
                  <div key={idx} className="p-2 bg-surface-2 border border-border-subtle">
                    <div className="text-xs text-text-secondary mb-0.5">{headline.headline}</div>
                    <div className="flex items-center justify-between text-2xs">
                      <span className="text-text-tertiary">{headline.source}</span>
                      <span className="font-mono text-green">+{headline.score.toFixed(0)}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-2 text-text-secondary text-xs">No bullish articles today</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

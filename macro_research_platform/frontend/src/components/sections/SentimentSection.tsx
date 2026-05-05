import { Card } from '@/components/ui/Card';
import type { SentimentRiskData } from '@/types';

interface SentimentSectionProps {
  data?: SentimentRiskData;
}

export function SentimentSection({ data }: SentimentSectionProps) {
  if (!data) {
    return (
      <div id="sentiment" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">18</span>
            <h2 className="section-title">Sentiment</h2>
          </div>
        </div>
        <Card className="p-6">
          <div className="animate-pulse bg-surface-2 rounded h-32" />
        </Card>
      </div>
    );
  }

  const getRiskAppetiteColor = (score: number) => {
    if (score >= 70) return 'text-green';
    if (score >= 50) return 'text-amber';
    if (score >= 30) return 'text-orange-400';
    return 'text-red';
  };

  const getRiskAppetiteLabel = (score: number) => {
    if (score >= 80) return 'Extreme Greed';
    if (score >= 60) return 'Greed';
    if (score >= 40) return 'Neutral';
    if (score >= 20) return 'Fear';
    return 'Extreme Fear';
  };

  const getContrarianColor = (signal: string) => {
    if (signal?.toLowerCase().includes('bull')) return 'text-green';
    if (signal?.toLowerCase().includes('bear')) return 'text-red';
    return 'text-text-secondary';
  };

  return (
    <div id="sentiment" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag">18</span>
          <h2 className="section-title">Sentiment</h2>
        </div>
      </div>

      <Card className="p-4">
        {/* Risk Appetite Score */}
        <div className="mb-4 pb-4 border-b border-border-subtle">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-text-secondary">Risk Appetite</span>
            <span className={`text-lg font-bold font-mono ${getRiskAppetiteColor(data.compositeRiskAppetite)}`}>
              {data.compositeRiskAppetite?.toFixed(0) ?? '--'}
            </span>
          </div>
          <div className="w-full bg-surface-3 h-1">
            <div
              className="bg-gradient-to-r from-red via-amber to-green h-1 transition-all"
              style={{ width: `${Math.min(100, Math.max(0, data.compositeRiskAppetite ?? 50))}%` }}
            />
          </div>
          <div className="mt-2 text-xs text-text-secondary">
            {getRiskAppetiteLabel(data.compositeRiskAppetite ?? 50)}
            <span className="text-text-tertiary ml-2">— {data.regime || 'Unknown'} regime</span>
          </div>
        </div>

        {/* Gauges */}
        {data.gauges && data.gauges.length > 0 && (
          <div className="grid grid-cols-2 gap-3 mb-4 pb-4 border-b border-border-subtle">
            {data.gauges.slice(0, 4).map((gauge, idx) => (
              <div key={idx} className="bg-surface-2 p-2 rounded">
                <div className="text-2xs text-text-tertiary uppercase">{gauge.name}</div>
                <div className="flex items-baseline gap-2">
                  <span className={`font-mono font-medium ${gauge.value > 0 ? 'text-green' : gauge.value < 0 ? 'text-red' : 'text-text-secondary'}`}>
                    {gauge.value > 0 ? '+' : ''}{gauge.value?.toFixed(2) ?? '--'}
                  </span>
                  <span className="text-2xs text-text-tertiary">{gauge.signal}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* VIX & AAII */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          {data.vixTermStructure && (
            <div>
              <div className="text-2xs text-text-tertiary uppercase mb-1">VIX Term Structure</div>
              <div className="text-sm font-medium text-text-primary">
                {data.vixTermStructure.structure || '—'}
              </div>
              <div className="text-2xs text-text-secondary">
                Ratio: {data.vixTermStructure.ratio?.toFixed(2) ?? '—'}
              </div>
            </div>
          )}
          {data.aaiiSentiment && (
            <div>
              <div className="text-2xs text-text-tertiary uppercase mb-1">AAII Sentiment</div>
              <div className="text-sm font-medium text-text-primary">
                {data.aaiiSentiment.signal || '—'}
              </div>
              <div className="text-2xs text-text-secondary">
                Spread: {data.aaiiSentiment.bullBearSpread != null
                  ? `${data.aaiiSentiment.bullBearSpread >= 0 ? '+' : ''}${data.aaiiSentiment.bullBearSpread.toFixed(0)}%`
                  : '—'}
              </div>
            </div>
          )}
        </div>

        {/* Cross Asset Momentum */}
        {data.crossAssetMomentum && data.crossAssetMomentum.assets && data.crossAssetMomentum.assets.length > 0 && (
          <div className="mb-4">
            <div className="text-2xs text-text-tertiary uppercase mb-2">Cross Asset Momentum</div>
            <div className="flex flex-wrap gap-2">
              {data.crossAssetMomentum.assets.slice(0, 5).map((asset, idx) => (
                <span
                  key={idx}
                  className={`text-xs px-2 py-1 rounded ${
                    asset.signal?.toLowerCase().includes('bull') ? 'bg-green-dim text-green' :
                    asset.signal?.toLowerCase().includes('bear') ? 'bg-red-dim text-red' :
                    'bg-surface-3 text-text-secondary'
                  }`}
                >
                  {asset.asset}: {asset.momentum3m?.toFixed(1) ?? '--'}%
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Contrarian Signal & Description */}
        <div className="pt-3 border-t border-border-subtle">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xs text-text-tertiary uppercase">Contrarian Signal</span>
            <span className={`text-sm font-medium ${getContrarianColor(data.contrarianSignal)}`}>
              {data.contrarianSignal || 'Neutral'}
            </span>
          </div>
          <p className="text-xs text-text-secondary leading-relaxed">
            {data.description || 'No sentiment data available.'}
          </p>
        </div>
      </Card>
    </div>
  );
}

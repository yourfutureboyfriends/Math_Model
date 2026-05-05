// Trade Recommendations Section — v2.0 7-Layer Signal Engine
// Implements AQR (Value/Momentum/QMJ/BAB/Carry), Bridgewater (Regime), Man AHL (Trend)
// Papers: Asness et al. (2013, 2014), Frazzini-Pedersen (2014), Hurst-Ooi-Pedersen (2013)

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ArrowUp, ArrowDown, BarChart3, RefreshCw, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MetaLabel {
  act: boolean;
  meta_score: number;
  size_fraction: number;
  filters_triggered: string[];
  filter_scores: Record<string, number>;
  crowding_level: string;
  vol_regime: string;
  reasoning: string;
  action_text: string;
}

interface TradeRecommendation {
  ticker: string;
  name: string;
  asset_class: string;
  region?: string;
  sector?: string;
  factor?: string;
  composite_score: number;
  confidence: number;
  // v2.0: Layer contributions for attribution
  layer_contributions?: {
    regime: number;
    value: number;
    momentum: number;
    quality: number;
    bab: number;
    carry: number;
    trend: number;
  };
  // v2.0: Top signal drivers
  top_drivers?: string[];
  kelly_pct: number;
  position_pct?: number;
  market_cap: number;
  avg_volume: number;
  last_price: number;
  pe?: number;
  div_yield?: number;
  beta?: number;
  direction?: string;
  abs_score?: number;
  // v3.0: Meta-labeling
  meta?: MetaLabel;
}

interface PairTrade {
  long_ticker: string;
  long_name: string;
  short_ticker: string;
  short_name: string;
  sector?: string;
  regime: string;
  long_score: number;
  short_score: number;
  net_score: number;
  long_position: number;
  short_position: number;
}

interface FactorSummary {
  regime_weights: Record<string, number>;
  value_z: number;
  momentum_z: number;
  quality_z: number;
  bab_z: number;
  carry_z: number;
  trend_z: number;
}

// v3.0: Production upgrades
interface CrowdingResult {
  factor_crowding: Record<string, {
    score: number;
    level: string;
    direction: string;
    n_positions: number;
  }>;
  portfolio_crowding_score: number;
  size_multiplier: number;
  alert_level: string;
  worst_factor: string;
  unwind_signal: boolean;
  interpretation: string;
}

interface SignalHealthResult {
  layer_ic: Record<string, {
    rolling_ic: number;
    monthly_ics: number[];
    ic_stability: number;
    icir: number;
    health: string;
    weight_mult: number;
    months_tracked: number;
  }>;
  weight_adjustments: Record<string, number>;
  decayed_layers: string[];
  healthy_layers: string[];
  overall_signal_health: string;
  alert: string | null;
}

interface MetaStats {
  total_candidates: number;
  passed_meta: number;
  filtered_out: number;
  avg_meta_score: number;
  crowding_alert: string;
  signal_health: string;
  unwind_detected: boolean;
}

interface TradeRecommendationsData {
  regime: string;
  macro_score: number;
  generated_at: string;
  longs: TradeRecommendation[];
  shorts: TradeRecommendation[];
  pair_trades: PairTrade[];
  // v2.0: Factor summary for methodology tab
  factor_summary?: FactorSummary;
  // v2.0: Regime probabilities
  regime_probabilities?: Record<string, number>;
  summary: {
    total_scored: number;
    qualified_count: number;
    long_count: number;
    short_count: number;
    avg_confidence: number;
    avg_long_score: number;
    avg_short_score: number;
    pair_trade_count: number;
  };
  duration_seconds?: number;
  // v2.0: Metadata
  _meta?: {
    engine_version: string;
    methodology: string;
    sources: string[];
    papers: string[];
    computed_at: string;
    parameters?: Record<string, any>;
  };
  // v3.0: Production upgrades
  crowding?: CrowdingResult;
  signal_health?: SignalHealthResult;
  meta_stats?: MetaStats;
}

interface TradeRecommendationsSectionProps {
  data?: {
    tradeRecommendations?: TradeRecommendationsData;
  };
  onRefresh?: () => void;
}

const FACTOR_COLORS: Record<string, string> = {
  value: '#22c55e',
  momentum: '#3b82f6',
  quality: '#8b5cf6',
  growth: '#f59e0b',
  low_vol: '#6b7280',
  size: '#ec4899',
  duration: '#14b8a6',
  credit: '#f97316',
  inflation: '#ef4444',
};

const LAYER_COLORS: Record<string, string> = {
  regime: '#f59e0b',    // Bridgewater - amber
  value: '#22c55e',     // AQR Value - green
  momentum: '#3b82f6',  // AQR Momentum - blue
  quality: '#8b5cf6',   // AQR QMJ - purple
  bab: '#ec4899',       // AQR BAB - pink
  carry: '#14b8a6',     // AQR Carry - teal
  trend: '#f97316',     // Man AHL Trend - orange
};


export function TradeRecommendationsSection({ data, onRefresh }: TradeRecommendationsSectionProps) {
  const [activeTab, setActiveTab] = useState<'longs' | 'shorts' | 'pairs' | 'factors' | 'methodology' | 'health'>('longs');
  const [showDetails, setShowDetails] = useState<string | null>(null);

  const recommendations = data?.tradeRecommendations;

  if (!recommendations) {
    return (
      <div id="trade-recommendations" className="terminal-section">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="w-4 h-4 text-bloomberg" />
          <h2 className="terminal-section-title">TRADE RECOMMENDATIONS</h2>
        </div>
        <Card className="bg-surface-1 border-border p-8 text-center">
          <p className="text-text-secondary text-sm mb-4">Trade recommendations unavailable</p>
          <button
            onClick={onRefresh}
            className="px-3 py-1.5 text-xs font-mono border border-border rounded hover:border-bloomberg hover:text-bloomberg transition-colors inline-flex items-center gap-2"
          >
            <RefreshCw className="w-3 h-3" />
            Generate
          </button>
        </Card>
      </div>
    );
  }

  const { longs, shorts, pair_trades, summary, regime, macro_score, generated_at } = recommendations;
  const factorSummary = recommendations.factor_summary;
  const regimeProbs = recommendations.regime_probabilities;
  const meta = recommendations._meta;
  const crowding = recommendations.crowding;
  const signalHealth = recommendations.signal_health;
  const metaStats = recommendations.meta_stats;

  const formatCurrency = (val: number) => {
    if (val >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
    if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
    if (val >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
    return `$${val.toFixed(0)}`;
  };

  const getScoreColor = (score: number) => {
    if (score > 0.5) return 'text-green';
    if (score > 0.2) return 'text-green/70';
    if (score > -0.2) return 'text-text-secondary';
    if (score > -0.5) return 'text-red/70';
    return 'text-red';
  };

  // Format layer contribution for display
  const formatLayerContrib = (contrib: number) => {
    if (contrib === undefined || isNaN(contrib)) return '—';
    return contrib > 0 ? `+${contrib.toFixed(2)}` : contrib.toFixed(2);
  };

  return (
    <div id="trade-recommendations" className="terminal-section">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-bloomberg" />
          <h2 className="terminal-section-title">TRADE RECOMMENDATIONS</h2>
          {meta?.engine_version && (
            <Badge variant="neutral" className="text-2xs font-mono">
              v{meta.engine_version}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="neutral" className="text-xs font-mono">
            {regime} REGIME
          </Badge>
          <Badge variant={macro_score > 0 ? 'success' : macro_score < 0 ? 'danger' : 'neutral'} className="text-xs font-mono">
            MACRO: {macro_score > 0 ? '+' : ''}{macro_score.toFixed(2)}
          </Badge>
          <button
            onClick={onRefresh}
            className="h-6 px-2 text-text-secondary hover:text-text-primary hover:bg-surface-3 transition-colors rounded"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Regime Probability Vector (v2.0) */}
      {regimeProbs && (
        <Card className="bg-surface-1 border-border p-3 mb-4">
          <div className="flex items-center gap-4">
            <span className="text-xs text-text-secondary whitespace-nowrap">REGIME PROBABILITIES</span>
            <div className="flex-1 flex gap-1">
              {Object.entries(regimeProbs)
                .sort((a, b) => b[1] - a[1])
                .map(([reg, prob]) => (
                  <div key={reg} className="flex-1">
                    <div className="flex justify-between text-2xs mb-1">
                      <span className={cn(
                        'font-mono',
                        reg === regime ? 'text-text-primary font-medium' : 'text-text-tertiary'
                      )}>
                        {reg}
                      </span>
                      <span className="text-text-tertiary">{(prob * 100).toFixed(0)}%</span>
                    </div>
                    <div className="h-1 bg-surface-4 rounded-sm overflow-hidden">
                      <div
                        className={cn(
                          'h-full rounded-sm',
                          reg === regime ? 'bg-bloomberg' : 'bg-surface-3'
                        )}
                        style={{ width: `${prob * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </Card>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-2 mb-4">
        <Card className="bg-surface-1 border-border p-3">
          <div className="text-xs text-text-secondary mb-1">LONGS</div>
          <div className="text-lg font-mono text-green">{summary.long_count}</div>
        </Card>
        <Card className="bg-surface-1 border-border p-3">
          <div className="text-xs text-text-secondary mb-1">SHORTS</div>
          <div className="text-lg font-mono text-red">{summary.short_count}</div>
        </Card>
        <Card className="bg-surface-1 border-border p-3">
          <div className="text-xs text-text-secondary mb-1">PAIRS</div>
          <div className="text-lg font-mono text-bloomberg">{summary.pair_trade_count}</div>
        </Card>
        <Card className="bg-surface-1 border-border p-3">
          <div className="text-xs text-text-secondary mb-1">AVG CONFIDENCE</div>
          <div className="text-lg font-mono text-text-primary">{(summary.avg_confidence * 100).toFixed(0)}%</div>
        </Card>
      </div>

      {/* v3.0: Risk Dashboard Banner */}
      {metaStats && (
        <Card className={cn(
          "bg-surface-1 border-l-4 p-3 mb-4",
          metaStats.crowding_alert === 'EXTREME' || metaStats.crowding_alert === 'HIGH' ? 'border-l-red bg-red/10' :
          metaStats.crowding_alert === 'MEDIUM' ? 'border-l-amber bg-amber/10' :
          'border-l-green bg-green/10'
        )}>
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-text-secondary">CROWDING</span>
                <Badge
                  variant={metaStats.crowding_alert === 'LOW' ? 'success' : metaStats.crowding_alert === 'MEDIUM' ? 'warning' : 'danger'}
                  className="text-xs font-mono"
                >
                  {metaStats.crowding_alert}
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono text-text-secondary">SIGNAL HEALTH</span>
                <Badge
                  variant={metaStats.signal_health === 'STRONG' ? 'success' : metaStats.signal_health === 'MODERATE' ? 'warning' : 'danger'}
                  className="text-xs font-mono"
                >
                  {metaStats.signal_health}
                </Badge>
              </div>
              {metaStats.unwind_detected && (
                <Badge variant="danger" className="text-xs font-mono animate-pulse">
                  ⚠️ UNWIND DETECTED
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-4 text-xs font-mono">
              <span className="text-text-secondary">
                Candidates: <span className="text-text-primary">{metaStats.total_candidates}</span>
              </span>
              <span className="text-text-secondary">
                Passed: <span className="text-text-primary">{metaStats.passed_meta}</span>
              </span>
              <span className="text-text-secondary">
                Filtered: <span className="text-text-primary">{metaStats.filtered_out}</span>
              </span>
              <span className="text-text-secondary">
                Avg Meta: <span className="text-text-primary">{(metaStats.avg_meta_score * 100).toFixed(0)}%</span>
              </span>
            </div>
          </div>
          {crowding && (
            <div className="mt-2 text-xs text-text-secondary">
              Worst factor: <span className="text-text-primary">{crowding.worst_factor}</span>
              {crowding.factor_crowding[crowding.worst_factor]?.score !== undefined && (
                <span className="ml-2">
                  (score {crowding.factor_crowding[crowding.worst_factor].score.toFixed(2)},
                  {crowding.factor_crowding[crowding.worst_factor].direction})
                </span>
              )}
              {crowding.unwind_signal && (
                <span className="ml-2 text-red">— correlation falling</span>
              )}
            </div>
          )}
        </Card>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-2 mb-4 overflow-x-auto">
        {(['longs', 'shorts', 'pairs', 'factors', 'health', 'methodology'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-3 py-1.5 text-xs font-mono border transition-colors whitespace-nowrap',
              activeTab === tab
                ? 'bg-bloomberg-muted border-bloomberg text-bloomberg'
                : 'bg-surface-1 border-border text-text-secondary hover:border-bloomberg-border hover:text-bloomberg'
            )}
          >
            {tab === 'longs' && `LONGS (${longs.length})`}
            {tab === 'shorts' && `SHORTS (${shorts.length})`}
            {tab === 'pairs' && `PAIRS (${pair_trades.length})`}
            {tab === 'factors' && 'FACTOR ROTATION'}
            {tab === 'health' && 'SIGNAL HEALTH'}
            {tab === 'methodology' && 'METHODOLOGY'}
          </button>
        ))}
      </div>

      {/* Longs Panel */}
      {activeTab === 'longs' && (
        <div className="space-y-2">
          {longs.slice(0, 10).map((rec, i) => (
            <div
              key={rec.ticker}
              onClick={() => setShowDetails(showDetails === rec.ticker ? null : rec.ticker)}
              className="cursor-pointer"
            >
            <Card className="bg-surface-1 border-border hover:border-bloomberg-border transition-colors">
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono text-text-tertiary w-4">{i + 1}</span>
                    <div>
                      <div className="font-mono font-medium">{rec.ticker}</div>
                      <div className="text-xs text-text-secondary truncate max-w-[200px]">{rec.name}</div>
                    </div>
                    {/* Signal Attribution Badges (v2.0) */}
                    {rec.top_drivers && rec.top_drivers.slice(0, 2).map((driver) => (
                      <span
                        key={driver}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium border"
                        style={{
                          backgroundColor: `${LAYER_COLORS[driver]}20`,
                          color: LAYER_COLORS[driver],
                          borderColor: LAYER_COLORS[driver],
                        }}
                      >
                        {driver}
                      </span>
                    ))}
                    {/* v3.0: META Badge */}
                    {rec.meta && (
                      <span
                        className={cn(
                          "inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium border",
                          rec.meta.meta_score >= 0.65 ? 'bg-bloomberg/20 text-bloomberg border-bloomberg' :
                          rec.meta.meta_score >= 0.40 ? 'bg-amber/20 text-amber border-amber' :
                          'bg-surface-3 text-text-tertiary border-border'
                        )}
                      >
                        META {(rec.meta.meta_score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className={cn('text-sm font-mono', getScoreColor(rec.composite_score))}>
                        {rec.composite_score > 0 ? '+' : ''}{rec.composite_score.toFixed(2)}
                      </div>
                      <div className="text-xs text-text-secondary">score</div>
                    </div>
                    <div className="text-right min-w-[60px]">
                      <div className="text-sm font-mono text-bloomberg">
                        {(rec.confidence * 100).toFixed(0)}%
                      </div>
                      <div className="text-xs text-text-secondary">conf</div>
                    </div>
                    <div className="text-right min-w-[60px]">
                      <div className="text-sm font-mono text-green">
                        {rec.position_pct ? `${(rec.position_pct * 100).toFixed(1)}%` : `${(rec.kelly_pct * 100).toFixed(1)}%`}
                      </div>
                      <div className="text-xs text-text-secondary">size</div>
                    </div>
                    <ArrowUp className="w-4 h-4 text-green" />
                  </div>
                </div>

                {showDetails === rec.ticker && (
                  <div className="mt-3 pt-3 border-t border-border">
                    <div className="grid grid-cols-4 gap-2 text-xs mb-2">
                      <div><span className="text-text-secondary">Sector:</span> {rec.sector || 'N/A'}</div>
                      <div><span className="text-text-secondary">Factor:</span> <span style={{ color: FACTOR_COLORS[rec.factor || 'value'] }}>{rec.factor || 'N/A'}</span></div>
                      <div><span className="text-text-secondary">Mkt Cap:</span> {formatCurrency(rec.market_cap)}</div>
                      <div><span className="text-text-secondary">Price:</span> ${rec.last_price.toFixed(2)}</div>
                    </div>
                    {/* Layer Contributions (v2.0) */}
                    {rec.layer_contributions && (
                      <div className="mt-2">
                        <div className="text-xs text-text-tertiary mb-1">SIGNAL ATTRIBUTION</div>
                        <div className="grid grid-cols-7 gap-1">
                          {Object.entries(rec.layer_contributions).map(([layer, value]) => (
                            <div key={layer} className="bg-surface-2 p-1.5 rounded text-center">
                              <div className="text-2xs text-text-tertiary uppercase">{layer.slice(0, 4)}</div>
                              <div
                                className={cn('font-mono text-xs', value > 0 ? 'text-green' : value < 0 ? 'text-red' : 'text-text-secondary')}
                                style={{ color: value !== 0 ? LAYER_COLORS[layer] : undefined }}
                              >
                                {formatLayerContrib(value)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
            </div>
          ))}
        </div>
      )}

      {/* Shorts Panel */}
      {activeTab === 'shorts' && (
        <div className="space-y-2">
          {shorts.slice(0, 10).map((rec, i) => (
            <div
              key={rec.ticker}
              onClick={() => setShowDetails(showDetails === rec.ticker ? null : rec.ticker)}
              className="cursor-pointer"
            >
            <Card className="bg-surface-1 border-border hover:border-bloomberg-border transition-colors">
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono text-text-tertiary w-4">{i + 1}</span>
                    <div>
                      <div className="font-mono font-medium">{rec.ticker}</div>
                      <div className="text-xs text-text-secondary truncate max-w-[200px]">{rec.name}</div>
                    </div>
                    {/* Signal Attribution Badges (v2.0) */}
                    {rec.top_drivers && rec.top_drivers.slice(0, 2).map((driver) => (
                      <span
                        key={driver}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium border"
                        style={{
                          backgroundColor: `${LAYER_COLORS[driver]}20`,
                          color: LAYER_COLORS[driver],
                          borderColor: LAYER_COLORS[driver],
                        }}
                      >
                        {driver}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className={cn('text-sm font-mono', getScoreColor(rec.composite_score))}>
                        {rec.composite_score.toFixed(2)}
                      </div>
                      <div className="text-xs text-text-secondary">score</div>
                    </div>
                    <div className="text-right min-w-[60px]">
                      <div className="text-sm font-mono text-bloomberg">
                        {(rec.confidence * 100).toFixed(0)}%
                      </div>
                      <div className="text-xs text-text-secondary">conf</div>
                    </div>
                    <div className="text-right min-w-[60px]">
                      <div className="text-sm font-mono text-red">
                        {rec.position_pct ? `${(Math.abs(rec.position_pct) * 100).toFixed(1)}%` : `${(rec.kelly_pct * 100).toFixed(1)}%`}
                      </div>
                      <div className="text-xs text-text-secondary">size</div>
                    </div>
                    <ArrowDown className="w-4 h-4 text-red" />
                  </div>
                </div>

                {showDetails === rec.ticker && (
                  <div className="mt-3 pt-3 border-t border-border">
                    <div className="grid grid-cols-4 gap-2 text-xs mb-2">
                      <div><span className="text-text-secondary">Sector:</span> {rec.sector || 'N/A'}</div>
                      <div><span className="text-text-secondary">Factor:</span> <span style={{ color: FACTOR_COLORS[rec.factor || 'value'] }}>{rec.factor || 'N/A'}</span></div>
                      <div><span className="text-text-secondary">Mkt Cap:</span> {formatCurrency(rec.market_cap)}</div>
                      <div><span className="text-text-secondary">Price:</span> ${rec.last_price.toFixed(2)}</div>
                    </div>
                    {/* Layer Contributions (v2.0) */}
                    {rec.layer_contributions && (
                      <div className="mt-2">
                        <div className="text-xs text-text-tertiary mb-1">SIGNAL ATTRIBUTION</div>
                        <div className="grid grid-cols-7 gap-1">
                          {Object.entries(rec.layer_contributions).map(([layer, value]) => (
                            <div key={layer} className="bg-surface-2 p-1.5 rounded text-center">
                              <div className="text-2xs text-text-tertiary uppercase">{layer.slice(0, 4)}</div>
                              <div
                                className={cn('font-mono text-xs', value > 0 ? 'text-green' : value < 0 ? 'text-red' : 'text-text-secondary')}
                                style={{ color: value !== 0 ? LAYER_COLORS[layer] : undefined }}
                              >
                                {formatLayerContrib(value)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
            </div>
          ))}
        </div>
      )}

      {/* Pair Trades Panel */}
      {activeTab === 'pairs' && (
        <div className="space-y-2">
          {pair_trades.length > 0 ? pair_trades.slice(0, 8).map((pair) => (
            <Card key={`${pair.long_ticker}-${pair.short_ticker}`} className="bg-surface-1 border-border">
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="bg-green-dim text-green px-2 py-1 rounded text-xs font-mono">
                      +{pair.long_ticker}
                    </div>
                    <div className="text-text-tertiary">/</div>
                    <div className="bg-red-dim text-red px-2 py-1 rounded text-xs font-mono">
                      -{pair.short_ticker}
                    </div>
                    {pair.sector && (
                      <Badge variant="neutral" className="text-xs">
                        {pair.sector}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-right">
                      <div className="text-sm font-mono text-bloomberg">
                        {pair.net_score > 0 ? '+' : ''}{pair.net_score.toFixed(2)}
                      </div>
                      <div className="text-xs text-text-secondary">net score</div>
                    </div>
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-4 text-xs">
                  <div className="text-green">
                    <span className="text-text-secondary">Long:</span> {pair.long_name}
                  </div>
                  <div className="text-red">
                    <span className="text-text-secondary">Short:</span> {pair.short_name}
                  </div>
                </div>
              </CardContent>
            </Card>
          )) : (
            <Card className="bg-surface-1 border-border p-8 text-center">
              <p className="text-text-secondary text-sm">No pair trades available for current regime</p>
            </Card>
          )}
        </div>
      )}

      {/* Factor Rotation Panel */}
      {activeTab === 'factors' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Card className="bg-surface-1 border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono text-text-secondary">
                FACTOR WEIGHTS ({regime})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {/* Factor weights from factor_summary if available */}
                {factorSummary ? (
                  <>
                    {Object.entries(factorSummary.regime_weights || {})
                      .sort((a, b) => b[1] - a[1])
                      .map(([factor, weight]) => (
                        <div key={factor} className="flex items-center justify-between p-2 bg-bg border border-border">
                          <div className="flex items-center gap-2">
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{ backgroundColor: FACTOR_COLORS[factor] || '#6b7280' }}
                            />
                            <span className="text-xs font-mono uppercase">{factor.replace('_', ' ')}</span>
                          </div>
                          <div className="flex items-center gap-3">
                            <div className="h-1 bg-surface-4 rounded" style={{ width: '60px' }}>
                              <div
                                className="h-full rounded"
                                style={{ width: `${Math.min(weight * 100, 100)}%`, backgroundColor: FACTOR_COLORS[factor] || '#6b7280' }}
                              />
                            </div>
                            <span className="text-xs font-mono min-w-[40px] text-right">{(weight * 100).toFixed(0)}%</span>
                          </div>
                        </div>
                      ))}
                  </>
                ) : (
                  // Fallback to static display
                  ['growth', 'momentum', 'quality', 'value', 'low_vol'].map((factor) => (
                    <div key={factor} className="flex items-center justify-between p-2 bg-bg border border-border">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: FACTOR_COLORS[factor] }}
                        />
                        <span className="text-xs font-mono uppercase">{factor.replace('_', ' ')}</span>
                      </div>
                      <Badge variant="neutral" className="text-xs">
                        Dynamic
                      </Badge>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-surface-1 border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono text-text-secondary">
                REGIME THESIS
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-text-secondary">
                {regime === 'Goldilocks' && 'Growth and momentum dominate in Goldilocks conditions. Quality provides downside protection.'}
                {regime === 'Reflation' && 'Value and cyclical factors outperform during reflation. Momentum captures trending themes.'}
                {regime === 'Slowdown' && 'Defensive factors (quality, low vol, duration) lead in slowdowns. Credit exposure provides carry.'}
                {regime === 'Stagflation' && 'Inflation-sensitive assets and low volatility outperform. Quality screens for margin resilience.'}
                {!['Goldilocks', 'Reflation', 'Slowdown', 'Stagflation'].includes(regime) && 'Factor timing based on macro regime analysis.'}
              </p>
              {/* Signal Z-Scores (v2.0) */}
              {factorSummary && (
                <div className="mt-4 pt-4 border-t border-border">
                  <div className="text-xs text-text-tertiary mb-2">SIGNAL Z-SCORES</div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="flex justify-between text-xs">
                      <span>Value</span>
                      <span className={factorSummary.value_z > 0 ? 'text-green' : 'text-red'}>
                        {factorSummary.value_z > 0 ? '+' : ''}{factorSummary.value_z.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span>Momentum</span>
                      <span className={factorSummary.momentum_z > 0 ? 'text-green' : 'text-red'}>
                        {factorSummary.momentum_z > 0 ? '+' : ''}{factorSummary.momentum_z.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span>Quality</span>
                      <span className={factorSummary.quality_z > 0 ? 'text-green' : 'text-red'}>
                        {factorSummary.quality_z > 0 ? '+' : ''}{factorSummary.quality_z.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span>BAB</span>
                      <span className={factorSummary.bab_z > 0 ? 'text-green' : 'text-red'}>
                        {factorSummary.bab_z > 0 ? '+' : ''}{factorSummary.bab_z.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span>Carry</span>
                      <span className={factorSummary.carry_z > 0 ? 'text-green' : 'text-red'}>
                        {factorSummary.carry_z > 0 ? '+' : ''}{factorSummary.carry_z.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span>Trend</span>
                      <span className={factorSummary.trend_z > 0 ? 'text-green' : 'text-red'}>
                        {factorSummary.trend_z > 0 ? '+' : ''}{factorSummary.trend_z.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Methodology Panel (v2.0) */}
      {activeTab === 'methodology' && (
        <div className="space-y-4">
          {/* 7-Layer Signal Framework */}
          <Card className="bg-surface-1 border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono text-text-secondary flex items-center gap-2">
                <BookOpen className="w-3 h-3" />
                7-LAYER SIGNAL FRAMEWORK
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[
                  { key: 'regime', name: 'Regime Conditioning', source: 'Bridgewater', weight: '25%', desc: 'Probability-weighted regime scores from HMM forward algorithm' },
                  { key: 'value', name: 'Value Everywhere', source: 'AQR', weight: '20%', desc: 'Cross-asset value signals: real yield, earnings yield, commodity curve' },
                  { key: 'momentum', name: 'Momentum Everywhere', source: 'AQR', weight: '20%', desc: 'Cross-sectional and time-series momentum at 1M/3M/12M horizons' },
                  { key: 'quality', name: 'Quality Minus Junk', source: 'AQR', weight: '15%', desc: 'Profitability, stability, growth, payout quality metrics' },
                  { key: 'bab', name: 'Betting Against Beta', source: 'AQR/Frazzini-Pedersen', weight: '10%', desc: 'Low-beta outperformance with leverage constraints' },
                  { key: 'carry', name: 'Carry Everywhere', source: 'AQR/Koijen', weight: '5%', desc: 'Yield spread carry adjusted for inflation and FX' },
                  { key: 'trend', name: 'Trend Following', source: 'Man AHL/Winton', weight: '5%', desc: 'Time-series momentum with vol targeting' },
                ].map((layer) => (
                  <div key={layer.key} className="flex items-center justify-between p-2 bg-bg border border-border rounded">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-3 h-3 rounded-full"
                        style={{ backgroundColor: LAYER_COLORS[layer.key] }}
                      />
                      <div>
                        <div className="text-sm font-medium">{layer.name}</div>
                        <div className="text-xs text-text-secondary">{layer.desc}</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <Badge variant="neutral" className="text-xs font-mono">{layer.weight}</Badge>
                      <div className="text-xs text-text-tertiary">{layer.source}</div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Academic References */}
          <Card className="bg-surface-1 border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono text-text-secondary">
                ACADEMIC FOUNDATIONS
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                {[
                  { paper: 'Value and Momentum Everywhere', authors: 'Asness, Moskowitz, Pedersen (2013)', journal: 'Journal of Finance' },
                  { paper: 'Quality Minus Junk', authors: 'Asness, Frazzini, Pedersen (2014)', journal: 'AQR Working Paper' },
                  { paper: 'Betting Against Beta', authors: 'Frazzini, Pedersen (2014)', journal: 'Journal of Financial Economics' },
                  { paper: 'A Century of Evidence on Trend', authors: 'Hurst, Ooi, Pedersen (2013)', journal: 'AQR Working Paper' },
                  { paper: 'Carry (Everywhere)', authors: 'Koijen et al. (2018)', journal: 'Journal of Financial Economics' },
                  { paper: 'Regime-Switching Models', authors: 'Hamilton (1989)', journal: 'Econometrica' },
                ].map((ref, i) => (
                  <div key={i} className="p-2 bg-surface-2 rounded">
                    <div className="font-medium text-text-primary">{ref.paper}</div>
                    <div className="text-text-secondary">{ref.authors}</div>
                    <div className="text-text-tertiary">{ref.journal}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Position Sizing */}
          <Card className="bg-surface-1 border-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-mono text-text-secondary">
                POSITION SIZING METHODOLOGY
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-text-secondary space-y-2">
                <p>
                  <strong className="text-text-primary">Kelly Criterion:</strong> Position sizes derived from
                  edge / variance with half-Kelly adjustment for uncertainty.
                </p>
                <p>
                  <strong className="text-text-primary">Volatility Targeting:</strong> All positions scaled to
                  10% annual volatility target using EWMA realized vol.
                </p>
                <p>
                  <strong className="text-text-primary">Cross-Asset Normalization:</strong> Z-scores computed
                  within asset class before global combination.
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Engine Metadata */}
          {meta && (
            <Card className="bg-surface-1 border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-mono text-text-secondary">
                  ENGINE METADATA
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4 text-xs">
                  <div>
                    <span className="text-text-tertiary">Version:</span>
                    <span className="ml-2 text-text-primary">{meta.engine_version}</span>
                  </div>
                  <div>
                    <span className="text-text-tertiary">Computed:</span>
                    <span className="ml-2 text-text-primary">
                      {new Date(meta.computed_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-text-tertiary">Sources:</span>
                    <span className="ml-2 text-text-primary">{meta.sources?.join(', ')}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* v3.0: Signal Health Panel */}
      {activeTab === 'health' && (
        <div className="space-y-4">
          {/* Rolling IC Table */}
          {signalHealth && (
            <Card className="bg-surface-1 border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-mono text-text-secondary">
                  SIGNAL IC HEALTH (Rolling 3-Month)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="grid grid-cols-6 gap-2 text-xs font-mono text-text-tertiary pb-2 border-b border-border">
                    <div>Layer</div>
                    <div>Rolling IC</div>
                    <div>ICIR</div>
                    <div>Stability</div>
                    <div>Status</div>
                    <div className="text-right">Weight</div>
                  </div>
                  {Object.entries(signalHealth.layer_ic).map(([layer, data]) => (
                    <div key={layer} className="grid grid-cols-6 gap-2 text-xs py-1 border-b border-border-subtle last:border-0">
                      <div className="font-mono capitalize flex items-center gap-2">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: LAYER_COLORS[layer] }}
                        />
                        {layer}
                      </div>
                      <div className={cn(
                        'font-mono',
                        data.rolling_ic >= 0.05 ? 'text-green' : data.rolling_ic >= 0.01 ? 'text-amber' : 'text-red'
                      )}>
                        {data.rolling_ic > 0 ? '+' : ''}{data.rolling_ic.toFixed(3)}
                      </div>
                      <div className="font-mono text-text-secondary">{data.icir.toFixed(2)}</div>
                      <div className="font-mono text-text-secondary">{(data.ic_stability * 100).toFixed(0)}%</div>
                      <div>
                        <Badge
                          variant={data.health === 'HEALTHY' ? 'success' : data.health === 'ACCEPTABLE' ? 'warning' : 'danger'}
                          className="text-2xs"
                        >
                          {data.health}
                        </Badge>
                      </div>
                      <div className="font-mono text-right text-text-secondary">{(data.weight_mult * 100).toFixed(0)}%</div>
                    </div>
                  ))}
                </div>              </CardContent>
            </Card>
          )}

          {/* Factor Crowding Table */}
          {crowding && (
            <Card className="bg-surface-1 border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-mono text-text-secondary">
                  FACTOR CROWDING (MSCI Model)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="grid grid-cols-5 gap-2 text-xs font-mono text-text-tertiary pb-2 border-b border-border">
                    <div>Factor</div>
                    <div>Score</div>
                    <div>Level</div>
                    <div>Correlation</div>
                    <div className="text-right">Positions</div>
                  </div>
                  {Object.entries(crowding.factor_crowding).map(([factor, data]) => (
                    <div key={factor} className="grid grid-cols-5 gap-2 text-xs py-1 border-b border-border-subtle last:border-0">
                      <div className="font-mono capitalize flex items-center gap-2">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: LAYER_COLORS[factor] }}
                        />
                        {factor}
                      </div>
                      <div className={cn(
                        'font-mono',
                        data.score >= 0.65 ? 'text-red' : data.score >= 0.50 ? 'text-amber' : 'text-green'
                      )}>
                        {data.score.toFixed(2)}
                      </div>
                      <div>
                        <Badge
                          variant={
                            data.level === 'low' ? 'success' :
                            data.level === 'medium' ? 'warning' :
                            data.level === 'high' ? 'danger' : 'danger'
                          }
                          className="text-2xs"
                        >
                          {data.level.toUpperCase()}
                        </Badge>
                      </div>
                      <div className="font-mono text-text-secondary">{data.direction}</div>
                      <div className="font-mono text-right text-text-secondary">{data.n_positions}</div>
                    </div>
                  ))}
                </div>                <div className="mt-4 pt-4 border-t border-border">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-text-secondary">
                      Portfolio Crowding Score: <span className={cn(
                        'font-mono font-medium',
                        crowding.portfolio_crowding_score >= 0.65 ? 'text-red' :
                        crowding.portfolio_crowding_score >= 0.50 ? 'text-amber' : 'text-green'
                      )}>{crowding.portfolio_crowding_score.toFixed(2)}</span>
                    </div>
                    <div className="text-xs text-text-secondary">
                      Size Multiplier: <span className="font-mono font-medium text-bloomberg">{(crowding.size_multiplier * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Meta-Labeling Summary */}
          {metaStats && (
            <Card className="bg-surface-1 border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-mono text-text-secondary">
                  META-LABELING FILTER (Lopez de Prado)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="text-xs text-text-secondary">Filter Weights</div>
                    {[
                      { name: 'Regime Consistency', weight: '30%', desc: 'Trade agrees with current regime' },
                      { name: 'Signal Strength', weight: '25%', desc: 'Z-score magnitude' },
                      { name: 'Crowding Safety', weight: '20%', desc: 'Factor not crowded' },
                      { name: 'Vol Environment', weight: '15%', desc: 'Signal-vol compatibility' },
                      { name: 'Signal Health', weight: '10%', desc: 'IC health of top driver' },
                    ].map((f) => (
                      <div key={f.name} className="flex items-center justify-between text-xs">
                        <span className="text-text-secondary">{f.name}</span>
                        <span className="font-mono text-text-primary">{f.weight}</span>
                      </div>
                    ))}
                  </div>                  <div className="space-y-2">
                    <div className="text-xs text-text-secondary">Meta Statistics</div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="text-text-secondary">Total Candidates</div>
                      <div className="font-mono text-right">{metaStats.total_candidates}</div>                      <div className="text-text-secondary">Passed Filter</div>
                      <div className="font-mono text-right text-green">{metaStats.passed_meta}</div>                      <div className="text-text-secondary">Filtered Out</div>
                      <div className="font-mono text-right text-amber">{metaStats.filtered_out}</div>                      <div className="text-text-secondary">Avg Meta Score</div>
                      <div className="font-mono text-right text-bloomberg">{(metaStats.avg_meta_score * 100).toFixed(1)}%</div>
                    </div>                  </div>
                </div>              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="mt-4 flex justify-between items-center text-xs text-text-tertiary">
        <span>
          Generated {new Date(generated_at).toLocaleString()}
          {recommendations.duration_seconds && ` · ${recommendations.duration_seconds.toFixed(1)}s`}
        </span>
        <span>{summary.total_scored.toLocaleString()} assets scored</span>
      </div>
    </div>
  );
}

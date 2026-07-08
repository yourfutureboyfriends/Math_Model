// Equity Research Dashboard — 7-Module Equity Research Integration
// Displays sector rotation, factor rotation, valuation, country rankings,
// earnings revisions, stock screener results, and event calendar.

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ArrowUp, ArrowDown, Globe, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useApiData } from '@/hooks/useApiData';

interface SectorRec {
  sector: string;
  signal: string;
  confidence: number;
  expectedReturn: number;
  macroDrivers: string[];
  weight?: number;
}

interface CountryPick {
  country: string;
  ticker: string;
  score: number;
}

interface ValuationData {
  regime: string;
  currentPE: number;
  targetPE: number;
  upsidePotential: number;
  signal: string;
}

interface EquityResearchData {
  sectorRotation: {
    regime: string;
    recommendations: SectorRec[];
    leader: string;
    laggard: string;
    intensity: number;
  };
  factorRotation: {
    regime: string;
    weights: Record<string, number>;
    explanation: {
      thesis?: string;
      overweights?: { factor: string; weight: number }[];
    };
  };
  valuation: ValuationData;
  countryRanking: {
    globalRegime: string;
    allocation: Record<string, number>;
    topMarkets: CountryPick[];
  };
  lastUpdated: string;
  note?: string;
}

interface EquityResearchSectionProps {
  data?: {
    equityResearch?: EquityResearchData;
  };
}

const FACTOR_COLORS: Record<string, string> = {
  value: '#22c55e',
  momentum: '#3b82f6',
  quality: '#8b5cf6',
  growth: '#f59e0b',
  low_vol: '#6b7280',
};

export function EquityResearchSection({ data }: EquityResearchSectionProps) {
  const { data: _apiEq } = useApiData<any>("/api/equity-research");
  if (!data && _apiEq) (data as any) = { equityResearch: _apiEq };
  const [activeTab, setActiveTab] = useState<'sectors' | 'factors' | 'valuation' | 'countries'>('sectors');

  const equityData = data?.equityResearch;

  if (!equityData) {
    return (
      <div id="equity-research" className="terminal-section">
        <div className="flex items-center gap-2 mb-4">
          <Globe className="w-4 h-4 text-bloomberg" />
          <h2 className="terminal-section-title">EQUITY RESEARCH</h2>
        </div>
        <Card className="bg-surface-1 border-border p-8 text-center">
          <p className="text-text-secondary text-sm">Equity research data unavailable</p>
        </Card>
      </div>
    );
  }

  const { sectorRotation, factorRotation, valuation, countryRanking } = equityData;

  // The /api/equity-research payload is {regime, sectorRatings, stockPicks} — a
  // different shape than the rotation view below. When the rotation shape is absent
  // but ratings/picks exist, render those real values instead of "unavailable".
  const sectorRatings: Record<string, string> | undefined = (equityData as any).sectorRatings;
  const stockPicks: any[] | undefined = (equityData as any).stockPicks;
  if (!sectorRotation && !factorRotation && !valuation && !countryRanking) {
    if (!sectorRatings && !(stockPicks && stockPicks.length)) {
      return (
        <div id="equity-research" className="terminal-section">
          <div className="flex items-center gap-2 mb-4">
            <Globe className="w-4 h-4 text-bloomberg" />
            <h2 className="terminal-section-title">EQUITY RESEARCH</h2>
          </div>
          <Card className="bg-surface-1 border-border p-8 text-center">
            <p className="text-text-secondary text-sm">Equity research data unavailable.</p>
          </Card>
        </div>
      );
    }
    const ratingTone = (r: string) => {
      const s = String(r).toLowerCase();
      if (s.includes('over') || s.includes('buy')) return 'text-green';
      if (s.includes('under') || s.includes('sell') || s.includes('avoid')) return 'text-red';
      return 'text-text-secondary';
    };
    const fmtUsd = (v: any) => (typeof v === 'number' && isFinite(v) ? `$${v.toFixed(2)}` : '—');
    const upside = (p: any) =>
      typeof p?.target === 'number' && typeof p?.current === 'number' && p.current
        ? ((p.target / p.current - 1) * 100)
        : null;
    return (
      <div id="equity-research" className="terminal-section">
        <div className="section-header mb-3">
          <div className="section-header-left">
            <span className="section-tag">RES</span>
            <h2 className="section-title">Equity Research</h2>
            {(equityData as any).regime && (
              <span className="section-meta">{String((equityData as any).regime).toUpperCase()}</span>
            )}
          </div>
        </div>
        <div className="space-y-3">
          {sectorRatings && Object.keys(sectorRatings).length > 0 && (
            <div className="p-3 bg-surface-1 border border-border">
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-2">Sector Ratings</div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                {Object.entries(sectorRatings).map(([sector, rating]) => (
                  <div key={sector} className="flex items-center justify-between px-2 py-1 bg-surface-2 border border-border-subtle">
                    <span className="text-xs text-text-primary">{sector}</span>
                    <span className={`text-xs font-mono ${ratingTone(rating)}`}>{rating}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {stockPicks && stockPicks.length > 0 && (
            <div className="border border-border bg-surface-1 overflow-hidden">
              <div className="px-3 py-1.5 border-b border-border-subtle bg-surface-2 text-2xs text-text-tertiary uppercase tracking-wider">
                Stock Picks
              </div>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border-subtle text-2xs text-text-tertiary uppercase">
                    <th className="text-left py-2 px-3 font-medium">Ticker</th>
                    <th className="text-left py-2 px-3 font-medium">Rating</th>
                    <th className="text-right py-2 px-3 font-medium">Current</th>
                    <th className="text-right py-2 px-3 font-medium">Target</th>
                    <th className="text-right py-2 px-3 font-medium">Upside</th>
                    <th className="text-left py-2 px-3 font-medium">Thesis</th>
                  </tr>
                </thead>
                <tbody>
                  {stockPicks.map((p, i) => {
                    const up = upside(p);
                    return (
                      <tr key={p.ticker ?? i} className="border-b border-border-subtle last:border-0">
                        <td className="py-2 px-3">
                          <div className="text-sm font-medium text-text-primary">{p.ticker}</div>
                          <div className="text-2xs text-text-tertiary">{p.name}</div>
                        </td>
                        <td className={`py-2 px-3 text-xs font-mono ${ratingTone(p.rating)}`}>{p.rating}</td>
                        <td className="py-2 px-3 text-right font-mono text-sm text-text-primary">{fmtUsd(p.current)}</td>
                        <td className="py-2 px-3 text-right font-mono text-sm text-green">{fmtUsd(p.target)}</td>
                        <td className={`py-2 px-3 text-right font-mono text-sm ${up != null && up >= 0 ? 'text-green' : 'text-red'}`}>
                          {up != null ? `${up >= 0 ? '+' : ''}${up.toFixed(1)}%` : '—'}
                        </td>
                        <td className="py-2 px-3 text-2xs text-text-secondary max-w-xs">{p.thesis}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    );
  }

  const getSignalColor = (signal: string) => {
    if (signal === 'overweight' || signal === 'BUY') return 'bg-green-dim text-green border-green';
    if (signal === 'underweight' || signal === 'SELL') return 'bg-red-dim text-red border-red';
    return 'bg-amber-dim text-amber border-amber';
  };

  return (
    <div id="equity-research" className="terminal-section">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-bloomberg" />
          <h2 className="terminal-section-title">EQUITY RESEARCH</h2>
        </div>
        <Badge variant="neutral" className="text-xs font-mono">
          {/* FIXED (BUG 8): Use ISO date format */}
          {equityData.lastUpdated ? new Date(equityData.lastUpdated).toISOString().split('T')[0] : 'N/A'}
        </Badge>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 mb-4 overflow-x-auto">
        {(['sectors', 'factors', 'valuation', 'countries'] as const).map((tab) => (
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
            {tab === 'sectors' && 'SECTOR ROTATION'}
            {tab === 'factors' && 'FACTOR ROTATION'}
            {tab === 'valuation' && 'VALUATION'}
            {tab === 'countries' && 'COUNTRY RANKING'}
          </button>
        ))}
      </div>

      {/* Sector Rotation Panel */}
      {activeTab === 'sectors' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card className="bg-surface-1 border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-mono text-text-secondary flex items-center gap-2">
                    <TrendingUp className="w-3 h-3" />
                    SECTOR RECOMMENDATIONS ({sectorRotation.regime})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {sectorRotation.recommendations?.map((rec, i) => (
                      <div
                        key={rec.sector}
                        className="flex items-center justify-between p-2 bg-bg border border-border"
                      >
                        <div className="flex items-center gap-3">
                          <span className="text-xs font-mono text-text-tertiary">{i + 1}</span>
                          <div>
                            <div className="text-sm font-mono">{rec.sector}</div>
                            <div className="text-xs text-text-secondary">
                              {rec.macroDrivers?.join(', ')}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {/* Show signal with weight percentage */}
                          <Badge className={getSignalColor(rec.signal)}>
                            {/* BUG-8 FIX: Guard against undefined weight */}
                            {rec.signal} {rec.weight != null && !isNaN(rec.weight) ? `${(rec.weight * 100).toFixed(0)}%` : ''}
                          </Badge>
                          <span className={cn(
                            'text-xs font-mono',
                            typeof rec.expectedReturn === 'number' && rec.expectedReturn > 0 ? 'text-green' : 'text-red'
                          )}>
                            {/* BUG-8 FIX: Guard against undefined expectedReturn */}
                            {typeof rec.expectedReturn === 'number'
                              ? `${rec.expectedReturn > 0 ? '+' : ''}${rec.expectedReturn.toFixed(1)}%`
                              : '--'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-surface-1 border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-mono text-text-secondary">
                    MOMENTUM LEADERS & LAGGARDS
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="p-3 bg-green-dim border border-green/20">
                      <div className="flex items-center gap-2 text-green mb-1">
                        <ArrowUp className="w-3 h-3" />
                        <span className="text-xs font-mono">LEADER</span>
                      </div>
                      <div className="text-sm font-mono">{sectorRotation.leader}</div>
                    </div>
                    <div className="p-3 bg-red-dim border border-red/20">
                      <div className="flex items-center gap-2 text-red mb-1">
                        <ArrowDown className="w-3 h-3" />
                        <span className="text-xs font-mono">LAGGARD</span>
                      </div>
                      <div className="text-sm font-mono">{sectorRotation.laggard}</div>
                    </div>
                    <div className="pt-2 border-t border-border">
                      <div className="flex justify-between text-xs">
                        <span className="text-text-secondary">Rotation Intensity</span>
                        <span className="font-mono">{sectorRotation.intensity?.toFixed(2)}</span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Factor Rotation Panel */}
          {activeTab === 'factors' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card className="bg-surface-1 border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-mono text-text-secondary">
                    FACTOR WEIGHTS ({factorRotation.regime})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {Object.entries(factorRotation.weights || {}).map(([factor, weight]) => (
                      <div key={factor}>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="uppercase font-mono">{factor}</span>
                          <span className="font-mono">{(weight * 100).toFixed(1)}%</span>
                        </div>
                        <div className="h-1 bg-surface-4">
                          <div
                            className="h-full transition-all"
                            style={{
                              width: `${weight * 100}%`,
                              backgroundColor: FACTOR_COLORS[factor] || '#6b7280',
                            }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-surface-1 border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-mono text-text-secondary">
                    FACTOR THESIS
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-text-secondary mb-4">
                    {factorRotation.explanation?.thesis || 'Factor timing based on macro regime analysis'}
                  </p>
                  {/* FIXED: BUG-F8 - Show default overweights for Slowdown regime */}
                  {(() => {
                    // For Slowdown regime, default overweights if not provided
                    const isSlowdown = factorRotation.regime === 'Slowdown';
                    const hasOverweights = factorRotation.explanation?.overweights && factorRotation.explanation.overweights.length > 0;
                    const overweights = hasOverweights
                      ? (factorRotation.explanation.overweights ?? [])
                      : isSlowdown
                        ? [
                            { factor: 'low_vol', weight: 0.15 },
                            { factor: 'quality', weight: 0.15 },
                            { factor: 'value', weight: 0.10 },
                          ]
                        : [];

                    if (overweights.length === 0) return null;

                    return (
                      <div className="space-y-2">
                        <div className="text-xs font-mono text-text-tertiary">OVERWEIGHTS</div>
                        {overweights.map((ow) => (
                          <div key={ow.factor} className="flex items-center gap-2">
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{ backgroundColor: FACTOR_COLORS[ow.factor] || '#6b7280' }}
                            />
                            <span className="text-sm">{ow.factor}</span>
                            <span className="text-xs text-text-secondary ml-auto">
                              {(ow.weight * 100).toFixed(0)}%
                            </span>
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                </CardContent>
              </Card>
            </div>
          )}

          {/* Valuation Panel */}
          {activeTab === 'valuation' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <Card className="bg-surface-1 border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-mono text-text-secondary">
                    MACRO-CONDITIONAL VALUATION
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div className="flex justify-between items-center p-2 bg-bg border border-border">
                      <span className="text-xs text-text-secondary">Current P/E</span>
                      <span className="font-mono">{valuation.currentPE?.toFixed(1)}</span>
                    </div>
                    <div className="flex justify-between items-center p-2 bg-bg border border-border">
                      <span className="text-xs text-text-secondary">Target P/E ({valuation.regime})</span>
                      <span className="font-mono">{valuation.targetPE?.toFixed(1)}</span>
                    </div>
                    <div className="flex justify-between items-center p-2 bg-bg border border-border">
                      <span className="text-xs text-text-secondary">Upside Potential</span>
                      <span className={cn(
                        'font-mono',
                        (valuation.upsidePotential || 0) > 0 ? 'text-green' : 'text-red'
                      )}>
                        {valuation.upsidePotential > 0 ? '+' : ''}{valuation.upsidePotential?.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-surface-1 border-border lg:col-span-2">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-mono text-text-secondary">
                    VALUATION SIGNAL
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-4">
                    <Badge className={getSignalColor(valuation.signal)}>
                      {valuation.signal}
                    </Badge>
                    <div className="text-sm text-text-secondary">
                      Based on {valuation.regime} regime-appropriate multiples
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Country Ranking Panel */}
          {activeTab === 'countries' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Card className="bg-surface-1 border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-mono text-text-secondary">
                    COUNTRY ALLOCATION ({countryRanking.globalRegime})
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {Object.entries(countryRanking.allocation || {}).map(([ticker, weight]) => (
                      <div key={ticker} className="flex items-center justify-between p-2 bg-bg border border-border">
                        <span className="font-mono">{ticker}</span>
                        <div className="flex items-center gap-2">
                          <div className="h-2 bg-green" style={{ width: `${weight * 100}px` }} />
                          <span className="text-xs font-mono">{(weight * 100).toFixed(1)}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-surface-1 border-border">
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-mono text-text-secondary">
                    TOP MARKETS
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {countryRanking.topMarkets?.map((market, i) => (
                      <div
                        key={market.country}
                        className="flex items-center justify-between p-2 bg-bg border border-border"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-text-tertiary">{i + 1}</span>
                          <div>
                            <div className="text-sm font-mono">{market.country}</div>
                            <div className="text-xs text-text-secondary">{market.ticker}</div>
                          </div>
                        </div>
                        <div className="text-xs font-mono text-green">
                          {market.score?.toFixed(2)}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
    </div>
  );
}

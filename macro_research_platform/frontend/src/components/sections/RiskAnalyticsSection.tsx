// Risk Dashboard Scenarios — Hedge Fund Grade Risk Analytics
// Shows macro scenarios, position-level risk, and concentration detection

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import { useAuth } from '@/context/AuthContext';
import { AlertTriangle, Target } from 'lucide-react';

interface DrawdownMetrics {
  currentDrawdown?: number;
  currentSeverity: string;
  maxDrawdown12m?: number;
  daysInDrawdown: number;
  expectedRecoveryDays?: number;
  recoveryTimeEstimate: string;
}

interface RiskAdjustedReturns {
  sharpeRatio?: number;
  sortinoRatio?: number;
  calmarRatio?: number;
  informationRatio?: number;
  betaVsSpy?: number;
  var95?: number;
  cvar95?: number;
  annualReturn?: number;
  annualVolatility?: number;
}

interface StressScenario {
  name: string;
  description: string;
  portfolioPnlPct?: number;
  worstComponent?: string;
  status: string;
}

interface CorrelationData {
  assets: string[];
  matrix3m: number[][];
  diversificationScore: number;
  diversificationRating: string;
  highCorrelationPairs?: Array<{ pair: string; corr: number }>;
}

// Macro Scenario Analysis
interface MacroScenario {
  name: string;
  probability: number;
  spyShock: number;
  tltShock: number;
  gldShock: number;
  hygShock: number;
  dxyShock: number;
  portfolioImpact: number;
  hedgeSuggestion: string;
}

// Position-Level Risk
interface PositionRisk {
  ticker: string;
  weight: number;
  contributionPct: number;
  var95: number;
  beta: number;
  stressLoss: number;
  flags: string[];
}

interface RiskAnalyticsData {
  drawdown: DrawdownMetrics;
  riskAdjustedReturns: RiskAdjustedReturns;
  correlation: CorrelationData;
  stressTests: StressScenario[];
  // New fields
  macroScenarios?: MacroScenario[];
  positions?: PositionRisk[];
  totalPortfolioVar?: number;
}

type TabType = 'returns' | 'drawdown' | 'correlation' | 'stress' | 'scenarios' | 'positions';

export function RiskAnalyticsSection() {
  const [data, setData] = useState<RiskAnalyticsData | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('returns');
  const [loading, setLoading] = useState(true);
  const { token } = useAuth();

  useEffect(() => {
    // Don't fetch if not authenticated
    if (!token) {
      setLoading(false);
      return;
    }

    fetch('/api/risk/full', {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [token]);

  if (loading) {
    return <div className="h-64 bg-surface-1 border border-border animate-pulse" />;
  }

  const tabs: { key: TabType; label: string }[] = [
    { key: 'returns', label: 'RETURNS' },
    { key: 'drawdown', label: 'DRAWDOWN' },
    { key: 'correlation', label: 'CORRELATION' },
    { key: 'stress', label: 'STRESS TEST' },
    { key: 'scenarios', label: 'SCENARIOS' },
    { key: 'positions', label: 'POSITIONS' },
  ];

  const renderReturnsTab = () => (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">Sharpe</div>
          <div className={cn(
            'font-mono text-lg font-bold',
            data?.riskAdjustedReturns?.sharpeRatio && data.riskAdjustedReturns.sharpeRatio > 1 ? 'text-green' : 'text-text-primary'
          )}>
            {data?.riskAdjustedReturns?.sharpeRatio?.toFixed(2) || '--'}
          </div>
        </div>
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">Sortino</div>
          <div className="font-mono text-lg font-bold">
            {data?.riskAdjustedReturns?.sortinoRatio?.toFixed(2) || '--'}
          </div>
        </div>
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">Calmar</div>
          <div className="font-mono text-lg font-bold">
            {data?.riskAdjustedReturns?.calmarRatio?.toFixed(2) || '--'}
          </div>
        </div>
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">Info Ratio</div>
          <div className="font-mono text-lg font-bold">
            {data?.riskAdjustedReturns?.informationRatio?.toFixed(2) || '--'}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">Beta vs SPY</div>
          <div className="font-mono text-lg">
            {data?.riskAdjustedReturns?.betaVsSpy?.toFixed(2) || '--'}
          </div>
          <div className="text-2xs text-text-tertiary">
            {data?.riskAdjustedReturns?.betaVsSpy && data.riskAdjustedReturns.betaVsSpy < 0.5
              ? 'Low correlation — good for HF'
              : ''}
          </div>
        </div>
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">VaR 95%</div>
          <div className="font-mono text-lg text-red">
            {(() => {
              const val = data?.riskAdjustedReturns?.var95;
              if (!val) return '--';
              const abs = Math.abs(val);
              if (abs >= 1000000) return `-$${(abs/1000000).toFixed(2)}M/day`;
              if (abs >= 1000) return `-$${(abs/1000).toFixed(1)}K/day`;
              return `-$${abs.toFixed(0)}/day`;
            })()}
          </div>
        </div>
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">CVaR 95%</div>
          <div className="font-mono text-lg text-red">
            {(() => {
              const val = data?.riskAdjustedReturns?.cvar95;
              if (!val) return '--';
              const abs = Math.abs(val);
              if (abs >= 1000000) return `-$${(abs/1000000).toFixed(2)}M/day`;
              if (abs >= 1000) return `-$${(abs/1000).toFixed(1)}K/day`;
              return `-$${abs.toFixed(0)}/day`;
            })()}
          </div>
        </div>
      </div>
    </div>
  );

  const renderDrawdownTab = () => (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">Current Drawdown</div>
          <div className={cn(
            'font-mono text-lg font-bold',
            data?.drawdown?.currentDrawdown && data.drawdown.currentDrawdown < -10 ? 'text-red' : 'text-text-primary'
          )}>
            {data?.drawdown?.currentDrawdown?.toFixed(1) || '--'}%
          </div>
          <Badge
            variant={
              data?.drawdown?.currentSeverity === 'SEVERE' ? 'danger' :
              data?.drawdown?.currentSeverity === 'SIGNIFICANT' ? 'warning' : 'neutral'
            }
          >
            {data?.drawdown?.currentSeverity}
          </Badge>
        </div>
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">Max 12M Drawdown</div>
          <div className="font-mono text-lg font-bold">
            {data?.drawdown?.maxDrawdown12m?.toFixed(1) || '--'}%
          </div>
        </div>
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">Days in DD</div>
          <div className="font-mono text-lg">
            {data?.drawdown?.daysInDrawdown || 0}
          </div>
          <div className="text-2xs text-text-tertiary">
            Est. recovery: {data?.drawdown?.recoveryTimeEstimate}
          </div>
        </div>
      </div>
    </div>
  );

  const renderCorrelationTab = () => (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-2xs text-text-tertiary uppercase">Diversification Score</div>
          <div className="flex items-center gap-2">
            <span className={cn(
              'font-mono text-xl font-bold',
              data?.correlation?.diversificationScore && data.correlation.diversificationScore > 0.5 ? 'text-green' :
              data?.correlation?.diversificationScore && data.correlation.diversificationScore > 0.3 ? 'text-amber' : 'text-red'
            )}>
              {data?.correlation?.diversificationScore?.toFixed(2) || '--'}
            </span>
            <Badge
              variant={
                data?.correlation?.diversificationRating === 'GOOD' ? 'success' :
                data?.correlation?.diversificationRating === 'FAIR' ? 'warning' : 'danger'
              }
            >
              {data?.correlation?.diversificationRating}
            </Badge>
          </div>
        </div>
      </div>

      {/* UPGRADE-3: Concentration Risk Flags */}
      {data?.correlation?.highCorrelationPairs && data.correlation.highCorrelationPairs.length > 0 && (
        <div className="p-3 border border-red/30 bg-red/5">
          <div className="flex items-center gap-2 text-red mb-2">
            <AlertTriangle className="w-4 h-4" />
            <span className="font-medium text-sm">Concentration Risk Detected</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.correlation.highCorrelationPairs.map((pair, idx) => (
              <span key={idx} className="text-xs bg-red-dim/20 text-red px-2 py-1 rounded">
                {pair.pair} ({pair.corr.toFixed(2)})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Simplified correlation matrix display */}
      <div className="grid grid-cols-10 gap-0.5">
        {data?.correlation?.assets?.map((asset) => (
          <div key={asset} className="text-center text-2xs text-text-tertiary p-1">
            {asset}
          </div>
        ))}
        {data?.correlation?.matrix3m?.map((row, i) =>
          row.map((corr, j) => (
            <div
              key={`${i}-${j}`}
              className={cn(
                'p-1 text-center text-xs font-mono',
                i === j ? 'bg-surface-3' :
                Math.abs(corr) > 0.7 ? 'bg-red-dim text-red border border-red/50' :
                Math.abs(corr) > 0.5 ? 'bg-amber-dim text-amber' :
                'bg-green-dim/30'
              )}
            >
              {corr.toFixed(2)}
            </div>
          ))
        )}
      </div>
    </div>
  );

  const renderStressTab = () => (
    <div className="space-y-2">
      {data?.stressTests?.map((scenario, idx) => (
        <div
          key={idx}
          className="flex items-center justify-between p-3 border border-border-subtle bg-surface-2"
        >
          <div>
            <div className="text-sm font-medium">{scenario.name}</div>
            <div className="text-2xs text-text-tertiary">{scenario.description}</div>
          </div>
          <div className="text-right">
            <div className={cn(
              'font-mono font-bold',
              scenario.portfolioPnlPct && scenario.portfolioPnlPct < -15 ? 'text-red' :
              scenario.portfolioPnlPct && scenario.portfolioPnlPct < -10 ? 'text-amber' : 'text-text-primary'
            )}>
              {scenario.portfolioPnlPct?.toFixed(1) || '--'}%
            </div>
            <div className="text-2xs text-text-tertiary">
              Worst: {scenario.worstComponent}
            </div>
          </div>
          <Badge
            variant={
              scenario.status.includes('analog') ? 'warning' :
              scenario.status === 'Recent' ? 'info' : 'neutral'
            }
          >
            {scenario.status}
          </Badge>
        </div>
      ))}
    </div>
  );

  // Macro Scenario Analysis Table
  const renderScenariosTab = () => {
    const scenarios = data?.macroScenarios || [
      { name: 'Soft Landing', probability: 40, spyShock: 8, tltShock: 5, gldShock: 2, hygShock: 4, dxyShock: -2, portfolioImpact: 5.2, hedgeSuggestion: 'Maintain current allocation' },
      { name: 'Inflation Spike', probability: 15, spyShock: -12, tltShock: -15, gldShock: 8, hygShock: -8, dxyShock: 3, portfolioImpact: -8.5, hedgeSuggestion: 'Long GLD, Short TLT' },
      { name: 'Policy Mistake', probability: 25, spyShock: -18, tltShock: 8, gldShock: 5, hygShock: -12, dxyShock: 2, portfolioImpact: -10.2, hedgeSuggestion: 'Long TLT, Reduce SPY' },
      { name: 'Stagflation', probability: 20, spyShock: -15, tltShock: -10, gldShock: 12, hygShock: -10, dxyShock: -5, portfolioImpact: -9.8, hedgeSuggestion: 'Long GLD, Commodity exposure' },
    ];

    const totalProb = scenarios.reduce((sum, s) => sum + s.probability, 0);
    const weightedReturn = scenarios.reduce((sum, s) => sum + (s.probability / 100) * s.portfolioImpact, 0);

    return (
      <div className="space-y-4">
        {/* Scenario Table Header */}
        <div className="text-2xs text-text-tertiary uppercase mb-2">
          Macro Scenario Analysis · Probabilities Sum to {totalProb}%
        </div>

        {/* Scenario Rows */}
        <div className="space-y-2">
          {scenarios.map((scenario, idx) => (
            <div
              key={idx}
              className={cn(
                'p-3 border bg-surface-2 transition-colors',
                scenario.probability > 30 ? 'border-amber/50' : 'border-border-subtle'
              )}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <span className="font-medium text-sm">{scenario.name}</span>
                  <Badge variant={scenario.probability > 30 ? 'warning' : 'neutral'}>
                    {scenario.probability}% Prob
                  </Badge>
                  {scenario.probability === Math.max(...scenarios.map(s => s.probability)) && (
                    <span className="flex items-center gap-1 text-2xs text-amber">
                      <Target className="w-3 h-3" />
                      Base Case
                    </span>
                  )}
                </div>
                <div className={cn(
                  'font-mono font-bold',
                  scenario.portfolioImpact < -5 ? 'text-red' :
                  scenario.portfolioImpact > 0 ? 'text-green' : 'text-text-primary'
                )}>
                  {scenario.portfolioImpact > 0 ? '+' : ''}{scenario.portfolioImpact.toFixed(1)}%
                </div>
              </div>

              {/* Asset Shocks Grid */}
              <div className="grid grid-cols-6 gap-2 mb-2">
                <div className="text-center p-1.5 bg-surface-3">
                  <div className="text-2xs text-text-tertiary">SPY</div>
                  <div className={cn(
                    'font-mono text-xs',
                    scenario.spyShock < 0 ? 'text-red' : 'text-green'
                  )}>
                    {scenario.spyShock > 0 ? '+' : ''}{scenario.spyShock}%
                  </div>
                </div>
                <div className="text-center p-1.5 bg-surface-3">
                  <div className="text-2xs text-text-tertiary">TLT</div>
                  <div className={cn(
                    'font-mono text-xs',
                    scenario.tltShock < 0 ? 'text-red' : 'text-green'
                  )}>
                    {scenario.tltShock > 0 ? '+' : ''}{scenario.tltShock}%
                  </div>
                </div>
                <div className="text-center p-1.5 bg-surface-3">
                  <div className="text-2xs text-text-tertiary">GLD</div>
                  <div className={cn(
                    'font-mono text-xs',
                    scenario.gldShock < 0 ? 'text-red' : 'text-green'
                  )}>
                    {scenario.gldShock > 0 ? '+' : ''}{scenario.gldShock}%
                  </div>
                </div>
                <div className="text-center p-1.5 bg-surface-3">
                  <div className="text-2xs text-text-tertiary">HYG</div>
                  <div className={cn(
                    'font-mono text-xs',
                    scenario.hygShock < 0 ? 'text-red' : 'text-green'
                  )}>
                    {scenario.hygShock > 0 ? '+' : ''}{scenario.hygShock}%
                  </div>
                </div>
                <div className="text-center p-1.5 bg-surface-3">
                  <div className="text-2xs text-text-tertiary">DXY</div>
                  <div className={cn(
                    'font-mono text-xs',
                    scenario.dxyShock < 0 ? 'text-red' : 'text-green'
                  )}>
                    {scenario.dxyShock > 0 ? '+' : ''}{scenario.dxyShock}%
                  </div>
                </div>
              </div>

              {/* Hedge Suggestion */}
              <div className="text-xs text-text-secondary flex items-center gap-2">
                <span className="text-2xs text-text-tertiary uppercase">Hedge:</span>
                <span className="text-amber">{scenario.hedgeSuggestion}</span>
              </div>
            </div>
          ))}
        </div>

        {/* Expected Value Summary */}
        <div className="p-3 border border-border bg-surface-1">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">Probability-Weighted Expected Return</div>
            <div className={cn(
              'font-mono font-bold text-lg',
              weightedReturn < 0 ? 'text-red' : 'text-green'
            )}>
              {weightedReturn > 0 ? '+' : ''}{weightedReturn.toFixed(2)}%
            </div>
          </div>
        </div>
      </div>
    );
  };

  // Position-Level Risk Contribution
  const renderPositionsTab = () => {
    const positions = data?.positions || [];
    const totalVar = data?.totalPortfolioVar || 0;

    if (positions.length === 0) {
      return (
        <div className="p-6 text-center text-text-secondary text-sm bg-surface-1 border border-border">
          No active positions. Load trade ideas to see position-level risk.
        </div>
      );
    }

    return (
      <div className="space-y-4">
        {/* Portfolio VaR Summary */}
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">Portfolio VaR 95%</div>
            <div className="font-mono text-lg font-bold text-red">
              {totalVar >= 1000000 ? `-$${(totalVar/1000000).toFixed(2)}M` :
               totalVar >= 1000 ? `-$${(totalVar/1000).toFixed(1)}K` :
               `-$${totalVar.toFixed(0)}`}
            </div>
          </div>
          <div className="p-3 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">Total Positions</div>
            <div className="font-mono text-lg font-bold">{positions.length}</div>
          </div>
          <div className="p-3 border border-border-subtle bg-surface-2">
            <div className="text-2xs text-text-tertiary uppercase">High Risk Flags</div>
            <div className="font-mono text-lg font-bold text-amber">
              {positions.filter(p => p.flags.length > 0).length}
            </div>
          </div>
        </div>

        {/* Position Table */}
        <div className="space-y-1">
          <div className="grid grid-cols-7 gap-2 text-2xs text-text-tertiary uppercase px-2">
            <div>Ticker</div>
            <div className="text-right">Weight</div>
            <div className="text-right">Risk Contr %</div>
            <div className="text-right">VaR 95%</div>
            <div className="text-right">Beta</div>
            <div className="text-right">Stress Loss</div>
            <div>Flags</div>
          </div>

          {positions.map((pos, idx) => (
            <div
              key={idx}
              className={cn(
                'grid grid-cols-7 gap-2 p-2 text-sm border',
                pos.flags.length > 0 ? 'bg-red/5 border-red/30' : 'bg-surface-2 border-border-subtle'
              )}
            >
              <div className="font-mono font-medium">{pos.ticker}</div>
              <div className="text-right font-mono">{(pos.weight * 100).toFixed(1)}%</div>
              <div className="text-right font-mono">{pos.contributionPct.toFixed(1)}%</div>
              <div className="text-right font-mono text-red">
                -${(pos.var95 / 1000).toFixed(1)}K
              </div>
              <div className={cn(
                'text-right font-mono',
                pos.beta > 1.2 ? 'text-amber' : 'text-text-primary'
              )}>
                {pos.beta.toFixed(2)}
              </div>
              <div className={cn(
                'text-right font-mono',
                pos.stressLoss < -15 ? 'text-red' : pos.stressLoss < -10 ? 'text-amber' : 'text-text-primary'
              )}>
                {pos.stressLoss.toFixed(1)}%
              </div>
              <div className="flex gap-1">
                {pos.flags.map((flag, fidx) => (
                  <span key={fidx} className="text-2xs bg-red/20 text-red px-1 rounded">{flag}</span>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="text-2xs text-text-tertiary flex flex-wrap gap-3">
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-red rounded-full"/>Concentration</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-amber rounded-full"/>High Beta</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 bg-text-tertiary rounded-full"/>Vol Spike</span>
        </div>
      </div>
    );
  };

  return (
    <div id="risk-analytics" className="terminal-section">
    <Card title="RISK ANALYTICS">
      <div className="space-y-4">
        {/* Tabs */}
        <div className="flex gap-1">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'px-3 py-1.5 text-xs border transition-colors',
                activeTab === tab.key
                  ? 'bg-bloomberg text-bg border-bloomberg'
                  : 'bg-surface-2 text-text-secondary border-border-subtle hover:bg-surface-3'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'returns' && renderReturnsTab()}
        {activeTab === 'drawdown' && renderDrawdownTab()}
        {activeTab === 'correlation' && renderCorrelationTab()}
        {activeTab === 'stress' && renderStressTab()}
        {activeTab === 'scenarios' && renderScenariosTab()}
        {activeTab === 'positions' && renderPositionsTab()}
      </div>
    </Card>
    </div>
  );
}

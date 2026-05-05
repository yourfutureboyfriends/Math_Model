// Section G Panel 8 — Risk Analytics
// Hedge fund risk metrics with tabs for returns, drawdown, correlation, stress test

import { useState, useEffect } from 'react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';

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
}

interface RiskAnalyticsData {
  drawdown: DrawdownMetrics;
  riskAdjustedReturns: RiskAdjustedReturns;
  correlation: CorrelationData;
  stressTests: StressScenario[];
}

type TabType = 'returns' | 'drawdown' | 'correlation' | 'stress';

export function RiskAnalyticsSection() {
  const [data, setData] = useState<RiskAnalyticsData | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('returns');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/risk/analytics')
      .then(r => r.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="h-64 bg-surface-1 border border-border animate-pulse" />;
  }

  const tabs: { key: TabType; label: string }[] = [
    { key: 'returns', label: 'RETURNS' },
    { key: 'drawdown', label: 'DRAWDOWN' },
    { key: 'correlation', label: 'CORRELATION' },
    { key: 'stress', label: 'STRESS TEST' },
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
            -${data?.riskAdjustedReturns?.var95
              ? (data.riskAdjustedReturns.var95 / 1000000).toFixed(2)
              : '--'}M/day
          </div>
        </div>
        <div className="p-3 border border-border-subtle bg-surface-2">
          <div className="text-2xs text-text-tertiary uppercase">CVaR 95%</div>
          <div className="font-mono text-lg text-red">
            -${data?.riskAdjustedReturns?.cvar95
              ? (data.riskAdjustedReturns.cvar95 / 1000000).toFixed(2)
              : '--'}M/day
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
                Math.abs(corr) > 0.7 ? 'bg-red-dim text-red' :
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

  return (
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
                  ? 'bg-accent text-bg border-accent'
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
      </div>
    </Card>
  );
}

// Regime Playbook — Tactical Allocation Guide
// Shows regime-specific recommendations: asset bias, factor preferences, risk guidelines

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus, Target, AlertTriangle, Clock, History } from 'lucide-react';
import type { RegimePlaybookData } from '@/types';

interface Props {
  data?: RegimePlaybookData | null;
  currentRegime?: string;
}

// Default playbook data by regime
const DEFAULT_PLAYBOOKS: Record<string, RegimePlaybookData> = {
  'Goldilocks': {
    regime: 'Goldilocks',
    summary: 'Strong growth, contained inflation. Risk-on regime favoring equities and cyclicals.',
    assetAllocation: [
      { asset: 'Equities', bias: 'LONG', conviction: 'HIGH', sizing: '40-50%', rationale: 'Earnings growth acceleration' },
      { asset: 'Credit', bias: 'LONG', conviction: 'HIGH', sizing: '20-25%', rationale: 'Spread compression likely' },
      { asset: 'Commodities', bias: 'NEUTRAL', conviction: 'MEDIUM', sizing: '10-15%', rationale: 'Selective demand strength' },
      { asset: 'Treasuries', bias: 'SHORT', conviction: 'MEDIUM', sizing: '5-10%', rationale: 'Rates drifting higher' },
      { asset: 'Cash', bias: 'NEUTRAL', conviction: 'LOW', sizing: '5%', rationale: 'Opportunity reserve' },
    ],
    factorPreferences: [
      { factor: 'Momentum', preference: 'OVERWEIGHT', conviction: 'HIGH', rationale: 'Trend persistence high' },
      { factor: 'Quality', preference: 'UNDERWEIGHT', conviction: 'MEDIUM', rationale: 'Cyclicals outperform' },
      { factor: 'Value', preference: 'OVERWEIGHT', conviction: 'MEDIUM', rationale: 'Reflation beneficiaries' },
      { factor: 'Size', preference: 'OVERWEIGHT', conviction: 'MEDIUM', rationale: 'Small cap leverage' },
    ],
    riskGuidelines: [
      { rule: 'Max Net Exposure', priority: 'CRITICAL', description: '130% gross, 100% net maximum' },
      { rule: 'VIX Trigger', priority: 'HIGH', description: 'Reduce 20% if VIX > 25' },
      { rule: 'Stop Loss', priority: 'HIGH', description: '8% trailing on all equity positions' },
      { rule: 'Sector Limit', priority: 'MEDIUM', description: 'Max 25% in single sector' },
    ],
    historicalPerformance: {
      avgReturn: 18.5,
      winRate: 78,
      avgDuration: 8,
      bestAsset: 'Small Cap Value',
      worstAsset: 'Long Treasuries',
    },
    tradeSetup: {
      primaryTrade: 'Long SPY / Short TLT',
      secondaryTrade: 'Long XLI (Industrials)',
      exitTrigger: 'ISM Manufacturing < 50 OR CPI > 4%',
      timeHorizon: '3-6 months',
    },
  },
  'Reflation': {
    regime: 'Reflation',
    summary: 'Accelerating growth and inflation. Commodities and value leadership.',
    assetAllocation: [
      { asset: 'Equities', bias: 'LONG', conviction: 'MEDIUM', sizing: '35-40%', rationale: 'Nominal growth positive' },
      { asset: 'Commodities', bias: 'LONG', conviction: 'HIGH', sizing: '25-30%', rationale: 'Inflation proxy' },
      { asset: 'Credit', bias: 'NEUTRAL', conviction: 'MEDIUM', sizing: '15-20%', rationale: 'Monitor spreads' },
      { asset: 'Treasuries', bias: 'SHORT', conviction: 'HIGH', sizing: '0-5%', rationale: 'Duration risk elevated' },
      { asset: 'Cash', bias: 'NEUTRAL', conviction: 'MEDIUM', sizing: '10%', rationale: 'Dry powder for dips' },
    ],
    factorPreferences: [
      { factor: 'Value', preference: 'OVERWEIGHT', conviction: 'HIGH', rationale: 'Energy/materials/Financials' },
      { factor: 'Momentum', preference: 'NEUTRAL', conviction: 'MEDIUM', rationale: 'Rotational environment' },
      { factor: 'Quality', preference: 'UNDERWEIGHT', conviction: 'HIGH', rationale: 'Low duration assets preferred' },
      { factor: 'Size', preference: 'OVERWEIGHT', conviction: 'MEDIUM', rationale: 'Domestic cyclicals' },
    ],
    riskGuidelines: [
      { rule: 'Duration Limit', priority: 'CRITICAL', description: 'Max 2yr duration in fixed income' },
      { rule: 'Inflation Hedge', priority: 'CRITICAL', description: 'Maintain 20%+ inflation protection' },
      { rule: 'Rate Sensitivity', priority: 'HIGH', description: 'Avoid rate-sensitive sectors' },
      { rule: 'Commodity Cap', priority: 'MEDIUM', description: 'Max 30% commodity exposure' },
    ],
    historicalPerformance: {
      avgReturn: 12.3,
      winRate: 65,
      avgDuration: 6,
      bestAsset: 'Commodities (DBC)',
      worstAsset: 'Long Duration Bonds',
    },
    tradeSetup: {
      primaryTrade: 'Long XLE / Short XLU',
      secondaryTrade: 'Long DBC, Gold',
      exitTrigger: 'Fed pause OR commodity peak',
      timeHorizon: '2-4 months',
    },
  },
  'Stagflation': {
    regime: 'Stagflation',
    summary: 'High inflation, slowing growth. Defensive positioning required.',
    assetAllocation: [
      { asset: 'Equities', bias: 'SHORT', conviction: 'HIGH', sizing: '20-30%', rationale: 'Earnings compression' },
      { asset: 'Commodities', bias: 'LONG', conviction: 'HIGH', sizing: '25-30%', rationale: 'Inflation hedge' },
      { asset: 'Credit', bias: 'SHORT', conviction: 'HIGH', sizing: '5-10%', rationale: 'Default risk rising' },
      { asset: 'Treasuries', bias: 'NEUTRAL', conviction: 'LOW', sizing: '20-25%', rationale: 'Mixed signals' },
      { asset: 'Cash', bias: 'LONG', conviction: 'HIGH', sizing: '15-20%', rationale: 'Preserve capital' },
    ],
    factorPreferences: [
      { factor: 'Quality', preference: 'OVERWEIGHT', conviction: 'HIGH', rationale: 'Balance sheet strength' },
      { factor: 'Low Vol', preference: 'OVERWEIGHT', conviction: 'HIGH', rationale: 'Defensive positioning' },
      { factor: 'Value', preference: 'NEUTRAL', conviction: 'MEDIUM', rationale: 'Energy exception' },
      { factor: 'Momentum', preference: 'UNDERWEIGHT', conviction: 'HIGH', rationale: 'Trend reversals likely' },
    ],
    riskGuidelines: [
      { rule: 'Net Exposure', priority: 'CRITICAL', description: 'Reduce to 50% net max' },
      { rule: 'Volatility', priority: 'CRITICAL', description: 'Long VIX protection' },
      { rule: 'Credit', priority: 'HIGH', description: 'Avoid HY, focus on IG' },
      { rule: 'Liquidity', priority: 'HIGH', description: 'Maintain 15%+ cash' },
    ],
    historicalPerformance: {
      avgReturn: -8.5,
      winRate: 35,
      avgDuration: 10,
      bestAsset: 'Gold',
      worstAsset: 'Growth Equities',
    },
    tradeSetup: {
      primaryTrade: 'Long GLD / Short QQQ',
      secondaryTrade: 'Defensive Sector Rotation',
      exitTrigger: 'CPI peak OR growth stabilizes',
      timeHorizon: '3-6 months',
    },
  },
  'Slowdown': {
    regime: 'Slowdown',
    summary: 'Decelerating growth, falling inflation. Bonds rally, defensive sectors outperform.',
    assetAllocation: [
      { asset: 'Equities', bias: 'SHORT', conviction: 'MEDIUM', sizing: '30-40%', rationale: 'Earnings risk' },
      { asset: 'Commodities', bias: 'SHORT', conviction: 'HIGH', sizing: '0-5%', rationale: 'Demand destruction' },
      { asset: 'Credit', bias: 'SHORT', conviction: 'MEDIUM', sizing: '10-15%', rationale: 'Spread widening' },
      { asset: 'Treasuries', bias: 'LONG', conviction: 'HIGH', sizing: '35-45%', rationale: 'Flight to safety' },
      { asset: 'Cash', bias: 'LONG', conviction: 'MEDIUM', sizing: '10-15%', rationale: 'Dry powder' },
    ],
    factorPreferences: [
      { factor: 'Quality', preference: 'OVERWEIGHT', conviction: 'HIGH', rationale: 'Defensive leadership' },
      { factor: 'Low Vol', preference: 'OVERWEIGHT', conviction: 'HIGH', rationale: 'Volatility compression' },
      { factor: 'Value', preference: 'UNDERWEIGHT', conviction: 'HIGH', rationale: 'Cyclicals underperform' },
      { factor: 'Momentum', preference: 'NEUTRAL', conviction: 'LOW', rationale: 'Choppy trends' },
    ],
    riskGuidelines: [
      { rule: 'Duration Target', priority: 'CRITICAL', description: 'Target 7-10yr duration' },
      { rule: 'Equity Beta', priority: 'HIGH', description: 'Reduce to <0.5 portfolio beta' },
      { rule: 'Recession Watch', priority: 'HIGH', description: 'Monitor leading indicators' },
      { rule: 'Stop Tightening', priority: 'MEDIUM', description: 'Tighter stops (5-6%)' },
    ],
    historicalPerformance: {
      avgReturn: 2.1,
      winRate: 45,
      avgDuration: 5,
      bestAsset: 'Long Treasuries',
      worstAsset: 'Cyclical Equities',
    },
    tradeSetup: {
      primaryTrade: 'Long TLT / Short SPY',
      secondaryTrade: 'Long Defensive Sectors (XLU, XLP)',
      exitTrigger: 'ISM > 45 OR Fed cuts begin',
      timeHorizon: '2-4 months',
    },
  },
};

export function RegimePlaybookSection({ data, currentRegime }: Props) {
  // Use provided data or fall back to default playbook based on regime
  const playbook = data || (currentRegime ? DEFAULT_PLAYBOOKS[currentRegime] : null);

  if (!playbook) {
    return (
      <section id="regime-playbook" className="terminal-section">
        <div className="section-header">
          <span className="section-tag">PLAYBOOK</span>
          <h2 className="section-title">Regime Playbook</h2>
        </div>
        <div className="p-6 text-text-secondary text-sm bg-surface-1 border border-border">
          No active regime. Await regime classification.
        </div>
      </section>
    );
  }

  const getBiasIcon = (bias: string) => {
    switch (bias) {
      case 'LONG': return <TrendingUp className="w-4 h-4 text-green" />;
      case 'SHORT': return <TrendingDown className="w-4 h-4 text-red" />;
      default: return <Minus className="w-4 h-4 text-text-tertiary" />;
    }
  };

  const getBiasColor = (bias: string) => {
    switch (bias) {
      case 'LONG': return 'text-green border-green bg-green-dim';
      case 'SHORT': return 'text-red border-red bg-red-dim';
      default: return 'text-text-secondary border-border bg-surface-3';
    }
  };

  const getConvictionBadge = (conviction: string) => {
    switch (conviction) {
      case 'HIGH': return 'bg-green-dim text-green';
      case 'MEDIUM': return 'bg-amber-dim text-amber';
      case 'LOW': return 'bg-surface-3 text-text-tertiary';
      default: return 'bg-surface-3 text-text-secondary';
    }
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'CRITICAL': return 'text-red';
      case 'HIGH': return 'text-amber';
      case 'MEDIUM': return 'text-text-secondary';
      default: return 'text-text-tertiary';
    }
  };

  return (
    <section id="regime-playbook" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">PLAYBOOK</span>
        <h2 className="section-title">Regime Playbook</h2>
        <Badge variant="neutral" className="ml-2">{playbook.regime}</Badge>
      </div>

      {/* Regime Summary */}
      <div className="mb-4 p-4 border-l-4 border-bloomberg bg-surface-1">
        <p className="text-sm text-text-secondary">{playbook.summary}</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Asset Allocation */}
        <Card title="TACTICAL ALLOCATION" className="h-full">
          <div className="space-y-2">
            {playbook.assetAllocation.map((asset, idx) => (
              <div
                key={idx}
                className={cn(
                  'flex items-center justify-between p-2 border rounded',
                  getBiasColor(asset.bias)
                )}
              >
                <div className="flex items-center gap-2">
                  {getBiasIcon(asset.bias)}
                  <div>
                    <div className="font-medium text-sm">{asset.asset}</div>
                    <div className="text-2xs opacity-80">{asset.sizing}</div>
                  </div>
                </div>
                <div className="text-right">
                  <span className={cn('px-2 py-0.5 rounded text-xs', getConvictionBadge(asset.conviction))}>
                    {asset.conviction}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Factor Preferences */}
        <Card title="FACTOR PREFERENCES" className="h-full">
          <div className="space-y-2">
            {playbook.factorPreferences.map((factor, idx) => (
              <div key={idx} className="p-2 border border-border-subtle bg-surface-2">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm">{factor.factor}</span>
                  <span className={cn(
                    'text-xs px-2 py-0.5 rounded',
                    factor.preference === 'OVERWEIGHT' ? 'bg-green-dim text-green' :
                    factor.preference === 'UNDERWEIGHT' ? 'bg-red-dim text-red' :
                    'bg-surface-3 text-text-tertiary'
                  )}>
                    {factor.preference}
                  </span>
                </div>
                <div className="text-2xs text-text-tertiary">{factor.rationale}</div>
              </div>
            ))}
          </div>
        </Card>

        {/* Risk Guidelines */}
        <Card title="RISK GUIDELINES" className="h-full">
          <div className="space-y-2">
            {playbook.riskGuidelines.map((guideline, idx) => (
              <div key={idx} className="flex items-start gap-2 p-2 border border-border-subtle bg-surface-2">
                <AlertTriangle className={cn('w-4 h-4 flex-shrink-0 mt-0.5', getPriorityColor(guideline.priority))} />
                <div>
                  <div className={cn('text-sm font-medium', getPriorityColor(guideline.priority))}>
                    {guideline.rule}
                  </div>
                  <div className="text-2xs text-text-tertiary">{guideline.description}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Trade Setup */}
        <Card title="TRADE SETUP" className="h-full">
          <div className="space-y-3">
            <div className="p-3 border border-bloomberg/30 bg-bloomberg/5">
              <div className="text-2xs text-text-tertiary uppercase mb-1">Primary Trade</div>
              <div className="font-mono font-bold text-bloomberg">{playbook.tradeSetup.primaryTrade}</div>
            </div>
            <div className="p-3 border border-border-subtle bg-surface-2">
              <div className="text-2xs text-text-tertiary uppercase mb-1">Secondary Trade</div>
              <div className="font-mono text-text-primary">{playbook.tradeSetup.secondaryTrade}</div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="p-2 border border-border-subtle bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase mb-1 flex items-center gap-1">
                  <Target className="w-3 h-3" /> Exit Trigger
                </div>
                <div className="text-xs text-text-secondary">{playbook.tradeSetup.exitTrigger}</div>
              </div>
              <div className="p-2 border border-border-subtle bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase mb-1 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> Horizon
                </div>
                <div className="text-xs text-text-secondary">{playbook.tradeSetup.timeHorizon}</div>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* Historical Performance */}
      <div className="mt-4 p-4 border border-border bg-surface-1">
        <div className="flex items-center gap-2 mb-3">
          <History className="w-4 h-4 text-text-secondary" />
          <span className="text-sm font-medium text-text-secondary">HISTORICAL PERFORMANCE IN {playbook.regime.toUpperCase()}</span>
        </div>
        <div className="grid grid-cols-5 gap-4 text-center">
          <div>
            <div className="text-2xs text-text-tertiary uppercase">Avg Return</div>
            <div className={cn(
              'font-mono text-lg font-bold',
              playbook.historicalPerformance.avgReturn >= 0 ? 'text-green' : 'text-red'
            )}>
              {playbook.historicalPerformance.avgReturn > 0 ? '+' : ''}{playbook.historicalPerformance.avgReturn}%
            </div>
          </div>
          <div>
            <div className="text-2xs text-text-tertiary uppercase">Win Rate</div>
            <div className="font-mono text-lg font-bold text-text-primary">
              {playbook.historicalPerformance.winRate}%
            </div>
          </div>
          <div>
            <div className="text-2xs text-text-tertiary uppercase">Avg Duration</div>
            <div className="font-mono text-lg font-bold text-text-primary">
              {playbook.historicalPerformance.avgDuration}mo
            </div>
          </div>
          <div>
            <div className="text-2xs text-text-tertiary uppercase">Best Asset</div>
            <div className="font-mono text-sm font-bold text-green">
              {playbook.historicalPerformance.bestAsset}
            </div>
          </div>
          <div>
            <div className="text-2xs text-text-tertiary uppercase">Worst Asset</div>
            <div className="font-mono text-sm font-bold text-red">
              {playbook.historicalPerformance.worstAsset}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

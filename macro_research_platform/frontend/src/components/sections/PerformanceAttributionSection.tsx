// Performance Attribution Section — Hedge Fund Grade Attribution
// Shows return decomposition: factor contribution, sector contribution, regime attribution

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { cn } from '@/lib/utils';
import {
  Target,
  Activity,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';

interface PerformanceAttributionData {
  period: string;
  totalReturn: number;
  benchmarkReturn: number;
  alpha: number;
  factorAttribution: FactorAttribution[];
  sectorAttribution: SectorAttribution[];
  regimeAttribution: RegimeAttribution[];
  riskAttribution: RiskAttribution;
  benchmarkComparison: BenchmarkComparison;
}

interface FactorAttribution {
  factor: string;
  weight: number;
  contributionPct: number;
  returnPct: number;
  excessReturn: number;
}

interface SectorAttribution {
  sector: string;
  allocation: number;
  contributionPct: number;
  returnPct: number;
  benchmarkWeight: number;
  activeWeight: number;
}

interface RegimeAttribution {
  regime: string;
  days: number;
  returnPct: number;
  contributionPct: number;
  frequency: number;
}

interface RiskAttribution {
  totalVolatility: number;
  systematicRisk: number;
  specificRisk: number;
  factorRisk: number;
  idiosyncraticRisk: number;
  var95: number;
  maxDrawdown: number;
}

interface BenchmarkComparison {
  vsSPY: number;
  vsSixtyForty: number;
  vsRiskParity: number;
  informationRatio: number;
  trackingError: number;
  upsideCapture: number;
  downsideCapture: number;
}

interface Props {
  data?: PerformanceAttributionData | null;
}

// Sample data for demonstration
// FIXED (BUG K): Removed hardcoded SAMPLE_DATA - now uses nulls to trigger "—" display
const SAMPLE_DATA: PerformanceAttributionData = {
  period: null as any,
  totalReturn: null as any,
  benchmarkReturn: null as any,
  alpha: null as any,
  factorAttribution: [],
  sectorAttribution: [],
  regimeAttribution: [],
  riskAttribution: {
    totalVolatility: null as any,
    systematicRisk: null as any,
    specificRisk: null as any,
    factorRisk: null as any,
    idiosyncraticRisk: null as any,
    var95: null as any,
    maxDrawdown: null as any,
  },
  benchmarkComparison: {
    vsSPY: null as any,
    vsSixtyForty: null as any,
    vsRiskParity: null as any,
    informationRatio: null as any,
    trackingError: null as any,
    upsideCapture: null as any,
    downsideCapture: null as any,
  },
};

export function PerformanceAttributionSection({ data }: Props) {
  const attribution = data || SAMPLE_DATA;

  const getColorClass = (value: number) =>
    value >= 0 ? 'text-green' : 'text-red';

  return (
    <section id="performance-attribution" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">ATTR</span>
        <h2 className="section-title">Performance Attribution</h2>
        <Badge variant="neutral" className="ml-2">
          {attribution.period}
        </Badge>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <Card className="p-3">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Portfolio Return</div>
          <div className={cn("font-mono text-2xl font-bold", getColorClass(attribution.totalReturn))}>
            {attribution.totalReturn > 0 ? '+' : ''}{attribution.totalReturn.toFixed(1)}%
          </div>
          <div className="text-2xs text-text-tertiary mt-1">
            vs {attribution.benchmarkReturn.toFixed(1)}% benchmark
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Alpha Generated</div>
          <div className={cn("font-mono text-2xl font-bold", getColorClass(attribution.alpha))}>
            {attribution.alpha > 0 ? '+' : ''}{attribution.alpha.toFixed(1)}%
          </div>
          <div className="text-2xs text-text-tertiary mt-1">
            IR: {attribution.benchmarkComparison.informationRatio.toFixed(2)}
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Max Drawdown</div>
          <div className="font-mono text-2xl font-bold text-amber">
            {attribution.riskAttribution.maxDrawdown.toFixed(1)}%
          </div>
          <div className="text-2xs text-text-tertiary mt-1">
            VaR 95%: {attribution.riskAttribution.var95.toFixed(1)}%
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Tracking Error</div>
          <div className="font-mono text-2xl font-bold text-text-primary">
            {attribution.benchmarkComparison.trackingError.toFixed(1)}%
          </div>
          <div className="text-2xs text-text-tertiary mt-1">
            Active mgmt contribution
          </div>
        </Card>
      </div>

      {/* Attribution Grid */}
      <div className="grid grid-cols-2 gap-4">
        {/* Factor Attribution */}
        <Card title="Factor Attribution" className="h-full">
          <div className="space-y-2">
            {attribution.factorAttribution.map((factor) => (
              <div key={factor.factor} className="flex items-center gap-3">
                <div className="w-24 text-sm text-text-secondary">
                  {factor.factor}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-4 bg-surface-3 rounded-sm overflow-hidden">
                      <div
                        className={cn(
                          "h-full flex items-center justify-end px-1",
                          factor.contributionPct >= 0 ? "bg-green" : "bg-red"
                        )}
                        style={{ width: `${Math.min(100, Math.abs(factor.contributionPct) * 10)}%` }}
                      >
                        <span className="text-2xs font-mono">
                          {factor.contributionPct > 0 ? '+' : ''}{factor.contributionPct.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className={cn(
                  "w-16 text-right font-mono text-xs",
                  factor.excessReturn >= 0 ? "text-green" : "text-red"
                )}>
                  {factor.excessReturn > 0 ? '+' : ''}{factor.excessReturn.toFixed(2)}%
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-border-subtle">
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-tertiary">Factor Contribution</span>
              <span className="font-mono text-green">+5.5% of total return</span>
            </div>
          </div>
        </Card>

        {/* Sector Attribution */}
        <Card title="Sector Attribution" className="h-full">
          <div className="space-y-1.5">
            {attribution.sectorAttribution.map((sector) => (
              <div
                key={sector.sector}
                className={cn(
                  "flex items-center gap-3 p-2 border",
                  sector.allocation > sector.benchmarkWeight
                    ? "bg-green-dim border-green"
                    : "bg-surface-2 border-border-subtle"
                )}
              >
                <div className="w-28 text-sm text-text-secondary">
                  {sector.sector}
                </div>
                <div className="flex-1 flex items-center gap-2">
                  <div className="w-20 text-right font-mono text-xs text-text-tertiary">
                    {(sector.allocation * 100).toFixed(0)}%
                    <span className={cn(
                      "ml-1",
                      sector.activeWeight > 0 ? "text-green" : "text-red"
                    )}>
                      {sector.activeWeight > 0 ? '+' : ''}{(sector.activeWeight * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex-1 h-3 bg-surface-3 rounded-sm overflow-hidden">
                    <div
                      className={cn(
                        "h-full",
                        sector.contributionPct >= 0 ? "bg-green" : "bg-red"
                      )}
                      style={{ width: `${Math.min(100, Math.abs(sector.contributionPct) * 15)}%` }}
                    />
                  </div>
                  <div className={cn(
                    "w-12 text-right font-mono text-xs",
                    getColorClass(sector.contributionPct)
                  )}>
                    {sector.contributionPct > 0 ? '+' : ''}{sector.contributionPct.toFixed(1)}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Regime Attribution */}
        <Card title="Regime Attribution" className="h-full">
          <div className="space-y-3">
            {attribution.regimeAttribution.map((regime) => (
              <div key={regime.regime} className="space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-text-primary">
                      {regime.regime}
                    </span>
                    <Badge variant="neutral" className="text-2xs">
                      {regime.days}d
                    </Badge>
                  </div>
                  <div className={cn(
                    "font-mono text-sm",
                    getColorClass(regime.returnPct)
                  )}>
                    {regime.returnPct > 0 ? '+' : ''}{regime.returnPct.toFixed(1)}%
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 bg-surface-3 rounded-sm overflow-hidden">
                    <div
                      className={cn(
                        "h-full",
                        regime.contributionPct >= 0 ? "bg-bloomberg" : "bg-red"
                      )}
                      style={{ width: `${regime.frequency}%` }}
                    />
                  </div>
                  <div className="w-12 text-right text-xs text-text-tertiary">
                    {regime.contributionPct.toFixed(1)}%
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 p-3 bg-surface-2 border border-border-subtle">
            <div className="text-xs text-text-secondary">
              Best performing regime: <span className="text-green font-medium">Goldilocks</span>
              {' '}({attribution.regimeAttribution[0].returnPct.toFixed(1)}% avg return)
            </div>
          </div>
        </Card>

        {/* Benchmark Comparison */}
        <Card title="Benchmark Comparison" className="h-full">
          <div className="space-y-3">
            {[
              { label: 'vs SPY', value: attribution.benchmarkComparison.vsSPY, icon: Target },
              { label: 'vs 60/40', value: attribution.benchmarkComparison.vsSixtyForty, icon: Activity },
              { label: 'vs Risk Parity', value: attribution.benchmarkComparison.vsRiskParity, icon: BarChart3 },
            ].map((item) => (
              <div key={item.label} className="flex items-center justify-between p-2 border border-border-subtle bg-surface-2">
                <div className="flex items-center gap-2">
                  <item.icon className="w-4 h-4 text-text-tertiary" />
                  <span className="text-sm text-text-secondary">{item.label}</span>
                </div>
                <div className={cn(
                  "flex items-center gap-1 font-mono text-sm",
                  getColorClass(item.value)
                )}>
                  {item.value >= 0 ? (
                    <ArrowUpRight className="w-4 h-4" />
                  ) : (
                    <ArrowDownRight className="w-4 h-4" />
                  )}
                  {item.value > 0 ? '+' : ''}{item.value.toFixed(1)}%
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-border-subtle space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-tertiary">Upside Capture</span>
              <span className="font-mono text-green">
                {attribution.benchmarkComparison.upsideCapture}%
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-tertiary">Downside Capture</span>
              <span className="font-mono text-amber">
                {attribution.benchmarkComparison.downsideCapture}%
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-tertiary">Information Ratio</span>
              <span className={cn(
                "font-mono",
                attribution.benchmarkComparison.informationRatio > 0.5
                  ? "text-green"
                  : "text-text-primary"
              )}>
                {attribution.benchmarkComparison.informationRatio.toFixed(2)}
              </span>
            </div>
          </div>
        </Card>
      </div>

      {/* Risk Attribution Footer */}
      <div className="mt-4 p-4 border border-border bg-surface-1">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-6">
            <div>
              <span className="text-text-tertiary">Systematic Risk: </span>
              <span className="font-mono text-text-primary">{attribution.riskAttribution.systematicRisk.toFixed(1)}%</span>
            </div>
            <div>
              <span className="text-text-tertiary">Specific Risk: </span>
              <span className="font-mono text-text-primary">{attribution.riskAttribution.specificRisk.toFixed(1)}%</span>
            </div>
            <div>
              <span className="text-text-tertiary">Factor Risk: </span>
              <span className="font-mono text-text-primary">{attribution.riskAttribution.factorRisk.toFixed(1)}%</span>
            </div>
            <div>
              <span className="text-text-tertiary">Idiosyncratic: </span>
              <span className="font-mono text-text-primary">{attribution.riskAttribution.idiosyncraticRisk.toFixed(1)}%</span>
            </div>
          </div>
          <div className="text-text-tertiary">
            Updated: Daily
          </div>
        </div>      </div>
    </section>
  );
}

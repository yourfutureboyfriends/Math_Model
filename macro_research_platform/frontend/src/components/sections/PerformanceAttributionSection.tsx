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

export function PerformanceAttributionSection({ data }: Props) {
  // Safe formatters for potentially null values
  const fmt = (
    val: number | null | undefined,
    decimals = 1,
    prefix = '',
    suffix = '%'
  ): string => {
    if (val === null || val === undefined || isNaN(Number(val))) {
      return '--';
    }
    const n = Number(val);
    const sign = prefix === '+' && n >= 0 ? '+' : '';
    return `${sign}${n.toFixed(decimals)}${suffix}`;
  };

  const fmtPct = (v: number | null | undefined, decimals = 1) =>
    fmt(v, decimals, '+', '%');

  const getColorClass = (value: number | null | undefined) => {
    if (value === null || value === undefined || isNaN(Number(value))) {
      return 'text-text-tertiary';
    }
    return Number(value) >= 0 ? 'text-green' : 'text-red';
  };

  // Loading guard - if no real data yet
  if (!data) {
    return (
      <section id="performance-attribution" className="terminal-section">
        <div className="section-header">
          <span className="section-tag">ATTR</span>
          <h2 className="section-title">Performance Attribution</h2>
          <Badge variant="neutral" className="ml-2">--</Badge>
        </div>
        <div className="text-text-secondary text-sm">Loading attribution data...</div>
      </section>
    );
  }

  return (
    <section id="performance-attribution" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">ATTR</span>
        <h2 className="section-title">Performance Attribution</h2>
        <Badge variant="neutral" className="ml-2">
          {data.period}
        </Badge>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <Card className="p-3">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Portfolio Return</div>
          <div className={cn("font-mono text-2xl font-bold", getColorClass(data.totalReturn))}>
            {fmtPct(data.totalReturn)}
          </div>
          <div className="text-2xs text-text-tertiary mt-1">
            vs {fmt(data.benchmarkReturn, 1, '', '%')} benchmark
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Alpha Generated</div>
          <div className={cn("font-mono text-2xl font-bold", getColorClass(data.alpha))}>
            {fmtPct(data.alpha)}
          </div>
          <div className="text-2xs text-text-tertiary mt-1">
            IR: {fmt(data.benchmarkComparison.informationRatio, 2, '', '')}
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Max Drawdown</div>
          <div className="font-mono text-2xl font-bold text-amber">
            {fmt(data.riskAttribution.maxDrawdown, 1, '', '%')}
          </div>
          <div className="text-2xs text-text-tertiary mt-1">
            VaR 95%: {fmt(data.riskAttribution.var95, 1, '', '%')}
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-2xs text-text-tertiary uppercase mb-1">Tracking Error</div>
          <div className="font-mono text-2xl font-bold text-text-primary">
            {fmt(data.benchmarkComparison.trackingError, 1, '', '%')}
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
            {data.factorAttribution.map((factor) => (
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
                        style={{ width: `${Math.min(100, Math.abs(factor.contributionPct || 0) * 10)}%` }}
                      >
                        <span className="text-2xs font-mono">
                          {fmtPct(factor.contributionPct)}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className={cn(
                  "w-16 text-right font-mono text-xs",
                  factor.excessReturn >= 0 ? "text-green" : "text-red"
                )}>
                  {fmt(factor.excessReturn, 2, '+', '%')}
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
            {data.sectorAttribution.map((sector) => (
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
                    {fmt((sector.allocation || 0) * 100, 0, '', '')}%
                    <span className={cn(
                      "ml-1",
                      (sector.activeWeight || 0) > 0 ? "text-green" : "text-red"
                    )}>
                      {fmt((sector.activeWeight || 0) * 100, 1, '+', '%')}
                    </span>
                  </div>
                  <div className="flex-1 h-3 bg-surface-3 rounded-sm overflow-hidden">
                    <div
                      className={cn(
                        "h-full",
                        (sector.contributionPct || 0) >= 0 ? "bg-green" : "bg-red"
                      )}
                      style={{ width: `${Math.min(100, Math.abs(sector.contributionPct || 0) * 15)}%` }}
                    />
                  </div>
                  <div className={cn(
                    "w-12 text-right font-mono text-xs",
                    getColorClass(sector.contributionPct)
                  )}>
                    {fmtPct(sector.contributionPct)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Regime Attribution */}
        <Card title="Regime Attribution" className="h-full">
          <div className="space-y-3">
            {data.regimeAttribution.map((regime) => (
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
                    {fmtPct(regime.returnPct)}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 bg-surface-3 rounded-sm overflow-hidden">
                    <div
                      className={cn(
                        "h-full",
                        (regime.contributionPct || 0) >= 0 ? "bg-bloomberg" : "bg-red"
                      )}
                      style={{ width: `${regime.frequency || 0}%` }}
                    />
                  </div>
                  <div className="w-12 text-right text-xs text-text-tertiary">
                    {fmt(regime.contributionPct, 1, '', '%')}
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 p-3 bg-surface-2 border border-border-subtle">
            <div className="text-xs text-text-secondary">
              Best performing regime: <span className="text-green font-medium">Goldilocks</span>
              {' '}({data.regimeAttribution[0] ? fmt(data.regimeAttribution[0].returnPct, 1, '', '%') : '--'} avg return)
            </div>
          </div>
        </Card>

        {/* Benchmark Comparison */}
        <Card title="Benchmark Comparison" className="h-full">
          <div className="space-y-3">
            {[
              { label: 'vs SPY', value: data.benchmarkComparison.vsSPY, icon: Target },
              { label: 'vs 60/40', value: data.benchmarkComparison.vsSixtyForty, icon: Activity },
              { label: 'vs Risk Parity', value: data.benchmarkComparison.vsRiskParity, icon: BarChart3 },
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
                  {(item.value || 0) >= 0 ? (
                    <ArrowUpRight className="w-4 h-4" />
                  ) : (
                    <ArrowDownRight className="w-4 h-4" />
                  )}
                  {fmtPct(item.value)}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 pt-3 border-t border-border-subtle space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-tertiary">Upside Capture</span>
              <span className="font-mono text-green">
                {fmt(data.benchmarkComparison.upsideCapture, 0, '', '%')}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-tertiary">Downside Capture</span>
              <span className="font-mono text-amber">
                {fmt(data.benchmarkComparison.downsideCapture, 0, '', '%')}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-text-tertiary">Information Ratio</span>
              <span className={cn(
                "font-mono",
                (data.benchmarkComparison.informationRatio || 0) > 0.5
                  ? "text-green"
                  : "text-text-primary"
              )}>
                {fmt(data.benchmarkComparison.informationRatio, 2, '', '')}
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
              <span className="font-mono text-text-primary">{fmt(data.riskAttribution.systematicRisk, 1, '', '%')}</span>
            </div>
            <div>
              <span className="text-text-tertiary">Specific Risk: </span>
              <span className="font-mono text-text-primary">{fmt(data.riskAttribution.specificRisk, 1, '', '%')}</span>
            </div>
            <div>
              <span className="text-text-tertiary">Factor Risk: </span>
              <span className="font-mono text-text-primary">{fmt(data.riskAttribution.factorRisk, 1, '', '%')}</span>
            </div>
            <div>
              <span className="text-text-tertiary">Idiosyncratic: </span>
              <span className="font-mono text-text-primary">{fmt(data.riskAttribution.idiosyncraticRisk, 1, '', '%')}</span>
            </div>
          </div>
          <div className="text-text-tertiary">
            Updated: Daily
          </div>
        </div>
      </div>
    </section>
  );
}

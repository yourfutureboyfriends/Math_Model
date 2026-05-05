// Portfolio Fit / Portfolio Analytics Section
// Shows portfolio analytics and fit metrics

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface PortfolioFitMetrics {
  totalReturn: number;
  sharpeRatio: number;
  maxDrawdown: number;
  volatility: number;
  beta: number;
  alpha: number;
  informationRatio: number;
  trackingError: number;
}

interface BenchmarkComparison {
  benchmark: string;
  portfolioReturn: number;
  benchmarkReturn: number;
  excessReturn: number;
  hitRate: number;
}

interface Props {
  data?: {
    metrics?: PortfolioFitMetrics;
    benchmark?: BenchmarkComparison;
    fitScore?: number;
    rating?: string;
  } | null;
}

export function PortfolioFitSection({ data }: Props) {
  const [loading, setLoading] = useState(!data);

  useEffect(() => {
    if (data) setLoading(false);
  }, [data]);

  const metrics = data?.metrics || {
    totalReturn: 12.5,
    sharpeRatio: 1.34,
    maxDrawdown: -8.2,
    volatility: 14.3,
    beta: 0.95,
    alpha: 2.1,
    informationRatio: 0.78,
    trackingError: 3.2,
  };

  const benchmark = data?.benchmark || {
    benchmark: 'S&P 500',
    portfolioReturn: 12.5,
    benchmarkReturn: 10.2,
    excessReturn: 2.3,
    hitRate: 68,
  };

  const fitScore = data?.fitScore ?? 85;
  const rating = data?.rating || 'A-';

  const getTrendIcon = (value: number) => {
    if (value > 0) return <TrendingUp className="w-4 h-4 text-green" />;
    if (value < 0) return <TrendingDown className="w-4 h-4 text-red" />;
    return <Minus className="w-4 h-4 text-text-tertiary" />;
  };

  return (
    <section id="portfolio-fit" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">FIT</span>
        <h2 className="section-title">Portfolio Fit</h2>
        <Badge variant={fitScore >= 80 ? 'success' : fitScore >= 60 ? 'warning' : 'danger'} className="ml-2">
          {rating}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card className="p-4">
          <h3 className="text-xs text-text-secondary uppercase mb-3">Performance Metrics</h3>
          {loading ? (
            <div className="h-32 animate-pulse bg-surface-2 rounded" />
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase">Total Return</div>
                <div className="flex items-center gap-1">
                  {getTrendIcon(metrics.totalReturn)}
                  <span className={`text-lg font-mono font-bold ${metrics.totalReturn >= 0 ? 'text-green' : 'text-red'}`}>
                    {metrics.totalReturn > 0 ? '+' : ''}{metrics.totalReturn.toFixed(1)}%
                  </span>
                </div>
              </div>
              <div className="p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase">Sharpe Ratio</div>
                <div className="text-lg font-mono font-bold text-text-primary">
                  {metrics.sharpeRatio.toFixed(2)}
                </div>
              </div>
              <div className="p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase">Max Drawdown</div>
                <div className="text-lg font-mono font-bold text-red">
                  {metrics.maxDrawdown.toFixed(1)}%
                </div>
              </div>
              <div className="p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase">Volatility</div>
                <div className="text-lg font-mono font-bold text-text-primary">
                  {metrics.volatility.toFixed(1)}%
                </div>
              </div>
            </div>
          )}
        </Card>

        <Card className="p-4">
          <h3 className="text-xs text-text-secondary uppercase mb-3">Risk Metrics</h3>
          {loading ? (
            <div className="h-32 animate-pulse bg-surface-2 rounded" />
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div className="p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase">Beta</div>
                <div className="text-lg font-mono font-bold text-text-primary">
                  {metrics.beta.toFixed(2)}
                </div>
              </div>
              <div className="p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase">Alpha</div>
                <div className={`text-lg font-mono font-bold ${metrics.alpha >= 0 ? 'text-green' : 'text-red'}`}>
                  {metrics.alpha > 0 ? '+' : ''}{metrics.alpha.toFixed(1)}%
                </div>
              </div>
              <div className="p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase">Info Ratio</div>
                <div className="text-lg font-mono font-bold text-text-primary">
                  {metrics.informationRatio.toFixed(2)}
                </div>
              </div>
              <div className="p-2 bg-surface-2">
                <div className="text-2xs text-text-tertiary uppercase">Tracking Error</div>
                <div className="text-lg font-mono font-bold text-text-primary">
                  {metrics.trackingError.toFixed(1)}%
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card className="p-4 mt-4">
        <h3 className="text-xs text-text-secondary uppercase mb-3">Benchmark vs {benchmark.benchmark}</h3>
        {loading ? (
          <div className="h-16 animate-pulse bg-surface-2 rounded" />
        ) : (
          <div className="grid grid-cols-4 gap-4">
            <div>
              <div className="text-2xs text-text-tertiary uppercase">Portfolio</div>
              <div className="text-xl font-mono font-bold text-green">
                +{benchmark.portfolioReturn.toFixed(1)}%
              </div>
            </div>
            <div>
              <div className="text-2xs text-text-tertiary uppercase">Benchmark</div>
              <div className="text-xl font-mono font-bold text-text-primary">
                +{benchmark.benchmarkReturn.toFixed(1)}%
              </div>
            </div>
            <div>
              <div className="text-2xs text-text-tertiary uppercase">Excess Return</div>
              <div className={`text-xl font-mono font-bold ${benchmark.excessReturn >= 0 ? 'text-green' : 'text-red'}`}>
                {benchmark.excessReturn > 0 ? '+' : ''}{benchmark.excessReturn.toFixed(1)}%
              </div>
            </div>
            <div>
              <div className="text-2xs text-text-tertiary uppercase">Hit Rate</div>
              <div className="text-xl font-mono font-bold text-text-primary">
                {benchmark.hitRate}%
              </div>
            </div>
          </div>
        )}
      </Card>
    </section>
  );
}

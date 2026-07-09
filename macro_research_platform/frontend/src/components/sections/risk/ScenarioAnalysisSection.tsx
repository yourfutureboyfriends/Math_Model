// Scenario Analysis Section
// Bull/Base/Bear scenario outcomes with probability-weighted expected returns

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { TrendingUp, TrendingDown, Minus, AlertTriangle, Target } from 'lucide-react';
import { useApiData } from '@/hooks/useApiData';

interface Scenario {
  scenario: string;
  probability: number;
  expectedReturn: number;
  confidenceInterval: [number, number];
  description: string;
  trigger: string;
  regime_shift: string;
}

interface ScenarioData {
  regime: string;
  scenarios: Scenario[];
  timestamp: string;
}

interface Props {
  data?: ScenarioData | null;
}

export function ScenarioAnalysisSection({ data }: Props) {
  const { data: _apiData } = useApiData<any>("/api/business/scenario");
  if (!data) data = _apiData as any;
  if (!data || !data.scenarios || data.scenarios.length === 0) {
    return (
      <section id="scenarios" className="terminal-section">
        <div className="section-header">
          <span className="section-tag">SCENARIO</span>
          <h2 className="section-title">Scenario Analysis</h2>
        </div>
        <div className="p-6 text-text-secondary text-sm bg-surface-1 border border-border">
          Scenario data unavailable. Calculating probability-weighted outcomes...
        </div>
      </section>
    );
  }

  const { regime, scenarios } = data;

  // Calculate weighted expected return
  const weightedReturn = scenarios.reduce(
    (sum, s) => sum + s.expectedReturn * s.probability,
    0
  );

  const getScenarioIcon = (return_: number) => {
    if (return_ > 0.05) return <TrendingUp className="w-4 h-4 text-green" />;
    if (return_ < -0.05) return <TrendingDown className="w-4 h-4 text-red" />;
    return <Minus className="w-4 h-4 text-text-tertiary" />;
  };

  const getScenarioColor = (return_: number) => {
    if (return_ > 0.05) return 'border-green bg-green-dim';
    if (return_ < -0.05) return 'border-red bg-red-dim';
    return 'border-amber bg-amber-dim';
  };

  const getReturnColor = (return_: number) => {
    if (return_ > 0) return 'text-green';
    if (return_ < 0) return 'text-red';
    return 'text-text-secondary';
  };

  return (
    <section id="scenarios" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">SCENARIO</span>
        <h2 className="section-title">Scenario Analysis</h2>
        <Badge variant="neutral" className="ml-2">{regime}</Badge>
      </div>

      {/* Summary Banner */}
      <div className="mb-4 p-4 border border-bloomberg/30 bg-bloomberg/5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-2xs text-text-tertiary uppercase mb-1">Probability-Weighted Expected Return</div>
            <div className={`text-2xl font-mono font-bold ${getReturnColor(weightedReturn)}`}>
              {weightedReturn > 0 ? '+' : ''}{(weightedReturn * 100).toFixed(1)}%
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xs text-text-tertiary uppercase mb-1">Scenarios Analyzed</div>
            <div className="text-lg font-mono font-bold text-text-primary">{scenarios.length}</div>
          </div>
        </div>
      </div>

      {/* Scenario Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {scenarios.map((scenario, idx) => (
          <Card
            key={idx}
            className={`p-4 border ${getScenarioColor(scenario.expectedReturn)}`}
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="text-xs font-medium text-text-primary mb-1">
                  {scenario.scenario}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-2xs text-text-tertiary">Probability:</span>
                  <span className="text-sm font-mono font-bold text-bloomberg">
                    {(scenario.probability * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              {getScenarioIcon(scenario.expectedReturn)}
            </div>

            {/* Expected Return */}
            <div className="mb-3">
              <div className="text-2xs text-text-tertiary uppercase mb-1">Expected Return</div>
              <div className={`text-xl font-mono font-bold ${getReturnColor(scenario.expectedReturn)}`}>
                {scenario.expectedReturn > 0 ? '+' : ''}{(scenario.expectedReturn * 100).toFixed(1)}%
              </div>
              <div className="text-2xs text-text-tertiary mt-1">
                95% CI: [{(scenario.confidenceInterval[0] * 100).toFixed(1)}%, {(scenario.confidenceInterval[1] * 100).toFixed(1)}%]
              </div>
            </div>

            {/* Description */}
            <div className="mb-3">
              <div className="text-2xs text-text-tertiary uppercase mb-1">Description</div>
              <p className="text-xs text-text-secondary">{scenario.description}</p>
            </div>

            {/* Trigger */}
            <div className="mb-3 p-2 bg-surface-2 rounded">
              <div className="text-2xs text-text-tertiary uppercase mb-1 flex items-center gap-1">
                <Target className="w-3 h-3" /> Trigger
              </div>
              <p className="text-xs text-text-secondary">{scenario.trigger}</p>
            </div>

            {/* Regime Shift */}
            <div className="flex items-center gap-2">
              <span className="text-2xs text-text-tertiary">Potential Shift:</span>
              <Badge variant="neutral" className="text-xs">
                {scenario.regime_shift}
              </Badge>
            </div>
          </Card>
        ))}
      </div>

      {/* Footer Note */}
      <div className="mt-4 p-3 border border-amber bg-amber-dim flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 text-amber flex-shrink-0 mt-0.5" />
        <p className="text-xs text-text-secondary">
          Scenarios are probabilistic estimates based on historical regime transitions and current macro conditions.
          Actual outcomes may differ. Confidence intervals represent 95% historical bounds.
        </p>
      </div>
    </section>
  );
}

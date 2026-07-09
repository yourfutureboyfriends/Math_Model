/**
 * Signal stack and momentum types
 * Contains: Signals, signal stack, momentum, nowcast, liquidity, sentiment, etc.
 */

// ── Nowcast & Macro Conditions ────────────────────────────────────────────────

export interface NowcastComponent {
  name: string;
  weight: number;
  contribution: number;
  status: string;
}

export interface NowcastData {
  gdpNowcast: number;
  nowcastQoQ: number;
  nowcastYoY: number;
  confidenceInterval: {
    lower: number;
    upper: number;
    rmse: number;
  };
  components: NowcastComponent[];
  revisionHistory: { date: string; nowcast: number; actual: number | null }[];
  methodology: string;
  lastUpdated: string;
}

export interface LiquidityIndicator {
  name: string;
  value: number;
  formatted: string;
  zScore: number;
  trend: string;
  interpretation: string;
}

export interface LiquidityConditionsData {
  compositeScore: number;
  regime: string;
  indicators: LiquidityIndicator[];
  fedPolicyStance: string;
  creditAvailability: string;
  description: string;
}

export interface SentimentGauge {
  name: string;
  value: number;
  formatted: string;
  signal: string;
  percentile: number;
  description: string;
}

export interface SentimentRiskData {
  compositeRiskAppetite: number;
  regime: string;
  gauges: SentimentGauge[];
  vixTermStructure: {
    ratio?: number;
    structure?: string;
    interpretation?: string;
  };
  aaiiSentiment: {
    bullBearSpread?: number;
    signal?: string;
    percentile?: number;
    inferredFrom?: string;
  };
  crossAssetMomentum: {
    averageMomentum: number;
    assets: { asset: string; momentum3m: number; signal: string }[];
    regime: string;
  };
  contrarianSignal: string;
  description: string;
}

export interface ValuationMetric {
  name: string;
  currentValue: number;
  historicalMean: number;
  zScore: number;
  percentile: number;
  signal: string;
  interpretation: string;
}

export interface ValuationFilterData {
  compositeScore: number;
  regime: string;
  metrics: ValuationMetric[];
  expectedReturns: Record<string, number>;
  description: string;
}

export interface AssetMomentum {
  asset: string;
  return12m: number;
  return1m: number;
  momentum12_1: number;
  dampenedSignal: number;
  rawSignal: string;
  interpretation: string;
}

export interface MomentumVetoData {
  vetoActive: boolean;
  dampenerApplied: number;
  assets: AssetMomentum[];
  portfolioAdjustment: {
    action: string;
    magnitude: number;
    affectedAssets: string[];
    rationale: string;
  };
  description: string;
  reasoning?: string;
}

// ── Correlation & Portfolio Construction ─────────────────────────────────────

export interface CorrelationPair {
  assetPair: string;
  correlation60d: number;
  regime: string;
  interpretation: string;
}

export interface CorrelationRegimeData {
  currentRegime: string;
  equityBondCorrelation: number;
  switchTriggered: boolean;
  fallbackStrategy: string;
  correlations: CorrelationPair[];
  riskParityAdjustment: {
    normalWeights: Record<string, number>;
    adjustedWeights: Record<string, number>;
    rationale: string;
  };
  description: string;
}

export interface RiskParityAsset {
  asset: string;
  volatility: number;
  targetRisk: number;
  currentWeight: number;
  proposedWeight: number;
  contribution: number;
}

export interface RiskParityCorrelation {
  pair: string;
  correlation: number;
  regime: 'diversifying' | 'neutral' | 'concentrated';
}

export interface RiskParityData {
  assets: RiskParityAsset[];
  correlations: RiskParityCorrelation[];
  leverage: number;
  portfolioVolatility: number;
  targetVolatility: number;
  rebalancingNeeded: boolean;
  lastRebalanced: string;
}

// ── Expected Returns & Alpha Signals ─────────────────────────────────────────

export interface ExpectedReturnScenario {
  scenario: string;
  probability: number;
  expectedReturn: number;
  confidenceInterval: [number, number];
}

export interface ExpectedReturnsData {
  currentRegimeReturn: number;
  next12Months: ExpectedReturnScenario[];
  byAssetClass: Record<string, number>;
  riskAdjustedReturns: Record<string, number>;
}

export interface PureAlphaSignal {
  name: string;
  category: 'value' | 'momentum' | 'carry' | 'volatility' | 'sentiment';
  signal: number;
  zScore: number;
  percentile: number;
  strength: 'weak' | 'moderate' | 'strong';
  direction: 'long' | 'short' | 'neutral';
  confidence: number;
  description: string;
}

export interface PureAlphaData {
  signals: PureAlphaSignal[];
  compositeScore: number;
  regime: 'expansion' | 'contraction' | 'neutral';
  topIdeas: string[];
}

// ── CTA Trend Signals ─────────────────────────────────────────────────────────

export interface TrendSignal {
  return: number;
  signal: number;
}

export interface TrendAsset {
  ticker: string;
  name: string;
  assetClass: string;
  signals: {
    fast: TrendSignal;
    medium: TrendSignal;
    slow: TrendSignal;
  };
  trendScore: number;
  direction: 'UPTREND' | 'DOWNTREND' | 'NO TREND';
  conviction: 'High' | 'Medium' | 'Low';
  regimeExpected: string;
  contradiction: boolean;
  note: string;
}

export interface TrendContradiction {
  ticker: string;
  expected: string;
  actual: string;
  conviction: string;
  warning: string;
}

export interface TrendSignalsData {
  assets: TrendAsset[];
  summary: {
    uptrends: number;
    downtrends: number;
    noTrend: number;
    contradictions: number;
    overallTrendRegime: string;
  };
  contradictions: TrendContradiction[];
  ctaSignal: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  lastUpdated: string;
}

// ── Alternative Data: News, GMO, Geopolitical, Options ───────────────────────

export interface NewsSentimentData {
  overall: {
    score: number;
    label: string;
    momentum: number;
    momentumLabel: string;
    articleCount: number;
    timeWindow: string;
  };
  byTheme: {
    inflation: { score: number; label: string; articleCount: number };
    growth: { score: number; label: string; articleCount: number };
    fed: { score: number; label: string; articleCount: number };
  };
  regimeConsistent: boolean;
  topBearishHeadlines: Array<{
    headline: string;
    source: string;
    score: number;
    publishedAt: string;
  }>;
  topBullishHeadlines: Array<{
    headline: string;
    source: string;
    score: number;
    publishedAt: string;
  }>;
  divergenceAlert: string | null;
  lastUpdated: string;
  error?: string;
}

export interface GMOForecast {
  assetClass: string;
  ticker: string;
  currentValuation: {
    metric: string;
    value: number;
    historicalAvg: number;
  };
  overvaluation: number;
  expectedReturn7Y: number;
  incomeYield: number;
  totalExpectedReturn: number;
  signal: 'STRONG BUY' | 'BUY' | 'NEUTRAL' | 'AVOID' | 'STRONG AVOID';
  confidence: string;
  gmoNote: string;
}

export interface GMOForecastsData {
  forecasts: GMOForecast[];
  tensions: Array<{
    assetClass: string;
    shortTermSignal: string;
    longTermSignal: string;
    divergence: boolean;
  }>;
  summary: {
    strongBuy: number;
    buy: number;
    neutral: number;
    avoid: number;
    strongAvoid: number;
    avgExpectedReturn: number;
  };
  lastUpdated: string;
  error?: string;
}

export interface GeopoliticalRiskComponent {
  value: number;
  zscore: number;
  trend: string;
  series: string;
}

export interface GeopoliticalRiskData {
  tailRiskScore: number;
  tailRiskLevel: 'Extreme' | 'Elevated' | 'Moderate' | 'Low';
  components: {
    geopoliticalRisk: GeopoliticalRiskComponent;
    policyUncertainty: GeopoliticalRiskComponent;
    financialStress: GeopoliticalRiskComponent;
  };
  confidenceAdjustment: number;
  interpretation: string;
  note: string;
  lastUpdated: string;
}

export interface OptionsComponent {
  value: number;
  normalised: number;
  level: string;
}

export interface OptionsTermStructure {
  slope: number;
  normalised: number;
  structure: string;
}

export interface OptionsContrarianSignal {
  signal: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  strength: 'Strong' | 'Moderate' | 'None';
  note: string;
}

export interface OptionsIntelligenceData {
  optionsFearComposite: number;
  sentiment: 'Extreme Fear' | 'Fear' | 'Neutral' | 'Greed' | 'Extreme Greed';
  contrarian: OptionsContrarianSignal;
  components: {
    vix?: OptionsComponent;
    vvix?: OptionsComponent;
    skew?: OptionsComponent;
    putCallRatio?: OptionsComponent;
    termStructure?: OptionsTermStructure;
  };
  interpretation: string;
  lastUpdated: string;
}

// ── Reflexivity & Factor Decomposition ───────────────────────────────────────

export interface ReflexivityLoop {
  loop: string;
  id: string;
  active: boolean;
  strength: number;
  severity: string;
  correlation: number;
  variables: {
    cause: { name: string; trend: string; change3m: number };
    effect: { name: string; trend: string; change3m: number };
  };
  interpretation: string;
  implication?: string;
  breakCondition: string;
}

export interface ReflexivityData {
  activeLoops: ReflexivityLoop[];
  inactiveLoops: ReflexivityLoop[];
  loopCount: {
    active: number;
    inactive: number;
  };
  reflexivityAlert: boolean;
  alertMessage: string;
  regimeImplication: string;
  lastUpdated: string;
  error?: string;
}

export interface FactorExposure {
  beta: number;
  optimal: number;
  alignment: number;
  signal: string;
}

export interface AssetBeta {
  ticker: string;
  weight?: number;
  equity?: number;
  rates?: number;
  inflation?: number;
  credit?: number;
  r2: number;
}

export interface FactorDecompositionData {
  portfolioType: string;
  factorExposures: {
    equity: FactorExposure;
    rates: FactorExposure;
    inflation: FactorExposure;
    credit: FactorExposure;
  };
  overallAlignment: number;
  alignmentLabel: string;
  dominantFactor: string;
  dominantFactorBeta: number;
  interpretation: string;
  rebalanceSuggestions: string[];
  assetBetas: AssetBeta[];
  lastUpdated: string;
  error?: string;
}

// ── Horizon Analysis ──────────────────────────────────────────────────────────

export interface HorizonSignal {
  horizon: string;
  signal: string;
  source: string;
}

export interface AssetHorizonAnalysis {
  assetClass: string;
  signals: {
    shortTerm: HorizonSignal;
    mediumTerm: HorizonSignal;
    longTerm: HorizonSignal;
  };
  tensionScore: number;
  tensionType: string;
  recommendation: string;
  actionable: boolean;
}

export interface HorizonTensionSummary {
  fullyAligned: string[];
  partialTension: string[];
  fullyContradictory: string[];
  highestTension: string | null;
  tensionAlert: string | null;
}

export interface HorizonActionableSummary {
  fullyAlignedBuys: string[];
  fullyAlignedAvoids: string[];
  mixedSignals: string[];
  recommendation: string;
}

export interface HorizonSignalData {
  signal: 'RISK_ON' | 'RISK_OFF' | 'NEUTRAL';
  score: number;
  sources: string[];
  confidence: number;
}

export interface HorizonTension {
  type: string;
  description: string;
  severity: 'HIGH' | 'PARTIAL';
  implication: string;
}

export interface HorizonAnalysisData {
  short_term?: HorizonSignalData;
  medium_term?: HorizonSignalData;
  long_term?: HorizonSignalData;
  tensions?: HorizonTension[];
  aligned_count?: number;
  recommendation?: string;
  position_size_modifier?: number;
  assetAnalysis?: AssetHorizonAnalysis[];
  tensionSummary?: HorizonTensionSummary;
  actionableSummary?: HorizonActionableSummary;
  lastUpdated?: string;
  generated_at?: string;
  error?: string;
}

// ── ML Layer ──────────────────────────────────────────────────────────────────

export interface AnomalousFeature {
  feature: string;
  currentValue: number;
  historicalMean: number;
  zscore: number;
  percentile: number;
  interpretation: string;
}

export interface AnomalyDetectionData {
  anomalyScore: number;
  isAnomaly: boolean;
  severity: string;
  interpretation: string;
  anomalousFeatures: AnomalousFeature[];
  normalFeatures: string[];
  regimeImplication: string;
  historicalAnalog: string | null;
  lastUpdated: string;
  error?: string;
}

export interface LSTMPrediction {
  predictedNextRegime: string;
  currentRegimeProb: number;
  transitionWarning: boolean;
  rawProbabilities: Record<string, number>;
  blendedProbabilities: Record<string, number>;
  modelNote: string;
  confidence: string;
  trainedSteps?: number;
}

export interface LSTMPredictionData {
  lstmPrediction: LSTMPrediction;
  error?: string;
}

// ── Ensemble Signal ───────────────────────────────────────────────────────────

export interface ModelContribution {
  model: string;
  signal: string;
  score: number;
  weight: number;
  weightedContribution: number;
}

export interface TopContributor {
  model: string;
  contribution: number;
}

export interface DissentingModel {
  model: string;
  score: number;
  note: string;
}

export interface EnsembleSignalData {
  ensembleScore: number;
  ensembleSignal: string;
  conviction: string;
  agreementRatio: number;
  signalDispersion: number;
  adaptiveWeightingActive: boolean;
  modelBreakdown: ModelContribution[];
  topContributors: TopContributor[];
  dissenting: DissentingModel[];
  riskBudgetFinal: number;
  interpretation: string;
  lastUpdated: string;
  regimeConflict?: boolean;
  regimeConflictNote?: string;
  error?: string;
}

export interface WeightAdaptation {
  model: string;
  oldWeight: number;
  newWeight: number;
  reason: string;
}

export interface EnsembleCalibration {
  riskOnAccuracy: number | null;
  riskOffAccuracy: number | null;
}

export interface PerformanceTrackingData {
  trackingPeriod: string;
  totalPredictions: number;
  regimeAccuracy: number | null;
  ensembleCalibration: EnsembleCalibration | null;
  modelAccuracies: Record<string, number>;
  weightAdaptations: WeightAdaptation[];
  note: string;
  lastUpdated: string;
  error?: string;
}

// ── System Health ─────────────────────────────────────────────────────────────

export interface HealthStatus {
  component: string;
  status: 'healthy' | 'degraded' | 'down' | 'unknown';
  latency?: number;
  lastCheck?: string;
  message?: string;
}

export interface SystemHealthData {
  overallStatus: 'healthy' | 'degraded' | 'critical' | 'unknown';
  apiStatus: HealthStatus;
  modelStatus: HealthStatus;
  dataPipeline: HealthStatus;
  cacheStatus: HealthStatus;
  uptime: string;
  version: string;
  activeModels: number;
  totalModels: number;
  lastPrediction: string;
  errorRate: number;
  avgLatency: number;
}

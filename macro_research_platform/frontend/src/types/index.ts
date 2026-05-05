// API Response Types

export interface DashboardData {
  regime: RegimeData;
  keyMetrics: KeyMetrics;
  scores: Scores;
  signals: SignalsData;
  sectorAllocation: SectorAllocationData;
  riskIndicators: RiskIndicatorsData;
  advancedIndicators: AdvancedIndicatorsData;
  recession: RecessionData;
  businessLayer: BusinessLayerData;
  modelAgreement: ModelAgreementData;
  transmissionAnalysis: TransmissionAnalysisData;
  investmentMemo: InvestmentMemoData;
  dataToWatch: DataToWatchItem[];
  metadata: DataMetadata;
  nowcast?: NowcastData;
  liquidity?: LiquidityConditionsData;
  sentiment?: SentimentRiskData;
  valuation?: ValuationFilterData;
  momentumVeto?: MomentumVetoData;
  correlationRegime?: CorrelationRegimeData;
  signalStack?: SignalStackData;
  signalStackV2?: SignalStackData;
  // ADDED: Phase 4 properties
  alerts?: AlertsData;
  internationalMacro?: InternationalMacroData;
  // ADDED: Phase 5 properties
  debtCycle?: DebtCycleData;
  riskParityAllocation?: RiskParityData;
  regimeTransitions?: TransitionMatrixData;
  pureAlpha?: PureAlphaData;
  portfolioAnalytics?: PortfolioAnalytics;
  expectedReturns?: ExpectedReturnsData;
  // ADDED: Phase 6 properties
  factorRotation?: FactorRotationData;
  geopoliticalRisk?: GeopoliticalRiskData;
  optionsIntelligence?: OptionsIntelligenceData;
  trendSignals?: TrendSignalsData;
  // ADDED: Phase 7 properties
  newsSentiment?: NewsSentimentData;
  gmoForecasts?: GMOForecastsData;
  reflexivity?: ReflexivityData;
  factorDecomposition?: FactorDecompositionData;
  horizonAnalysis?: HorizonAnalysisData;
  // ADDED: Phase 8 properties
  anomalyDetection?: AnomalyDetectionData;
  lstmPrediction?: LSTMPredictionData;
  ensembleSignal?: EnsembleSignalData;
  performanceTracking?: PerformanceTrackingData;
  // ADDED: Phase 9 properties
  earningsSurprises?: any;
  yieldCurveShape?: any;
  cbDivergence?: any;
  // ADDED: Phase 10 properties
  portfolioSimulation?: PortfolioSimulationData;
}

export interface RegimeData {
  current: string;
  confidence: string;
  confidenceScore: number;
  duration: number;
  history: RegimeHistoryPoint[];
  interpretations: RegimeInterpretation[];
}

export interface RegimeHistoryPoint {
  date: string;
  regime: string;
}

export interface RegimeInterpretation {
  factor: string;
  impact: string;
  color: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
}

export interface KeyMetrics {
  growth: MetricWithSparkline;
  inflation: MetricWithSparkline;
  liquidity: MetricWithSparkline;
  risk: MetricWithSparkline;
  recession: MetricWithSparkline;
  regimeDuration: {
    value: string;
    delta?: string;
    currentRegime: string;
  };
}

export interface MetricWithSparkline {
  value: number;
  formatted: string;
  direction: 'up' | 'down' | 'neutral';
  sparklineData: number[];
}

export interface Scores {
  growth: number;
  inflation: number;
  liquidity: number;
  risk: number;
}

export interface SignalsData {
  growth: SignalDetails;
  inflation: SignalDetails;
  liquidity: SignalDetails;
  risk: SignalDetails;
}

export interface SignalDetails {
  latestScore: number;
  threeMonthChange: string;
  state: string;
  direction: 'improving' | 'deteriorating' | 'stable';
  interpretation: string;
  history: number[];
}

export interface SectorAllocationData {
  sectors: Sector[];
  chartData: SectorChartPoint[];
}

export interface Sector {
  name: string;
  score: number;
  signal: 'Overweight' | 'Slight Overweight' | 'Neutral' | 'Slight Underweight' | 'Underweight';
  conviction: 'High' | 'Medium' | 'Low';
  rationale: string;
}

export interface SectorChartPoint {
  sector: string;
  score: number;
  color: string;
}

export interface RiskIndicatorsData {
  indicators: RiskIndicator[];
  compositeScore: number;
  regime: string;
}

export interface RecessionData {
  probability: number;
  level: string;
  logisticProb: number;
  emProbitProb: number;
  sahmValue: number;
  sahmSignal: string;
  description: string;
}

export interface RiskIndicator {
  name: string;
  value: string;
  level: 'low' | 'medium' | 'high' | 'extreme';
  interpretation: string;
}

export interface AdvancedIndicator {
  name: string;
  value: string;
  status: string;
  trend: string;
  description: string;
}

export interface AdvancedIndicatorsData {
  sahmRule: AdvancedIndicator;
  creditImpulse: AdvancedIndicator;
  leiComposite: AdvancedIndicator;
  riskParity: AdvancedIndicator;
}

export interface ExpectedReturn {
  assetOrSector: string;
  expectedReturn: number;
  sharpeEstimate: number;
  confidence: string;
  interpretation: string;
}

export interface PositionSizing {
  assetOrSector: string;
  suggestedSize: number;
  bucket: string;
  conviction: string;
  reason: string;
}

export interface SignalScorecardItem {
  signal: string;
  category: string;
  status: string;
  confidence: string;
  researchSupport: string;
}

export interface DecisionLogEntry {
  timestamp: string;
  recommendationType: string;
  headline: string;
  conviction: string;
  suggestedPositionSize: number;
}

export interface BusinessLayerData {
  recommendations: string | null;
  expectedReturns: ExpectedReturn[];
  positionSizing: PositionSizing[];
  signalScorecard: SignalScorecardItem[];
  decisionLog: DecisionLogEntry[];
}

export interface ModelAgreementItem {
  model: string;
  indicator: string;
  impact: string;
  color: 'success' | 'warning' | 'danger' | 'info';
}

export interface ModelAgreementData {
  items: ModelAgreementItem[];
}

export interface TransmissionChannel {
  channel: string;
  status: string;
  description: string;
}

export interface TransmissionAnalysisData {
  channels: TransmissionChannel[];
  summary: string;
}

export interface InvestmentMemoData {
  regimeSummary: string;
  keyPoints: string[];
  risks: string[];
  opportunities: string[];
}

export interface DataToWatchItem {
  indicator: string;
  importance: string;
  nextRelease: string;
  expectedImpact: string;
}

export interface DataMetadata {
  latestDate: string;
  dataStatus: 'current' | 'acceptable' | 'stale' | 'unknown';
  daysSinceUpdate: number;
  mode: 'live' | 'sample';
  validationWarnings?: string[];
  supportingEvidence?: string[];
}

// =============================================================================
// NEW QUANTITATIVE MODULES (7 modules)
// =============================================================================

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
}

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

export interface SignalLayer {
  layer: string;
  priority: number;
  signal: string;
  conviction: number;
  override?: string;
}

export interface SignalStackData {
  finalSignal: string;
  conviction: number;
  layers: SignalLayer[];
  overridesApplied: string[];
  overrideLog?: OverrideLogEntry[];
  reasoning: string;
  timestamp: string;
}

export interface OverrideLogEntry {
  timestamp: string;
  layer: string;
  originalSignal: string;
  newSignal: string;
  reason: string;
  triggeredBy: string;
}

// =============================================================================
// PHASE 4 TYPES
// =============================================================================

export interface AlertItem {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  triggered: boolean;
  triggeredAt?: string;
  message: string;
  action: string;
  currentValue: number | string;
  threshold: number | string;
  acknowledged: boolean;
}

export interface AlertsData {
  active: AlertItem[];
  count: {
    critical: number;
    warning: number;
    info: number;
  };
  lastEvaluated: string;
}

export interface RegionMacroData {
  regime: string;
  growth: number;
  inflation: number;
  confidence?: number;
}

export interface RegimeDivergence {
  pair: string;
  us: string;
  other: string;
  divergence: boolean;
}

export interface FXImplication {
  pair: string;
  bias: string;
  reason: string;
}

export interface InternationalMacroData {
  regions: {
    US: RegionMacroData;
    EU: RegionMacroData;
    UK: RegionMacroData;
    Japan: RegionMacroData;
  };
  globalLiquidityComposite: number;
  regimeDivergences: RegimeDivergence[];
  fxImplications: FXImplication[];
  lastUpdated: string;
}

// =============================================================================
// DEBT CYCLE MONITOR TYPES
// =============================================================================

export type CyclePosition = 'Early Expansion' | 'Mid Cycle' | 'Late Cycle' | 'Deleveraging';
export type CycleSeverity = 'mild' | 'moderate' | 'severe';

export interface DebtCycleIndicator {
  name: string;
  value: number;
  formatted: string;
  signal: 'contraction' | 'neutral' | 'expansion';
  description: string;
}

export interface DebtCycleData {
  cyclePosition: CyclePosition;
  cycleScore: number;
  severity: CycleSeverity;
  indicators: {
    realRate: DebtCycleIndicator;
    debtGDP: DebtCycleIndicator;
    debtServiceRatio: DebtCycleIndicator;
    creditImpulse: DebtCycleIndicator;
    m2Growth: DebtCycleIndicator;
  };
  historicalAnalog: string;
  implication: string;
}

// =============================================================================
// PHASE 5 TYPES - Risk Parity, Regime Transition, International, Alpha Signals
// =============================================================================

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

export interface RegimeTransition {
  fromRegime: string;
  toRegime: string;
  probability: number;
  avgReturn: number;
  volatility: number;
  sharpe: number;
  maxDrawdown: number;
  winRate: number;
  sampleSize: number;
}

export interface TransitionMatrixData {
  transitions: RegimeTransition[];
  currentRegime: string;
  mostLikelyNext: string;
  matrix: Record<string, Record<string, number>>;
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

export interface PortfolioHolding {
  asset: string;
  ticker: string;
  currentWeight: number;
  targetWeight: number;
  drift: number;
  pnl: number;
  regimeAlignment: 'aligned' | 'neutral' | 'contrarian';
}

export interface PortfolioAnalytics {
  holdings: PortfolioHolding[];
  totalValue: number;
  dayPnl: number;
  totalReturn: number;
  volatility: number;
  sharpe: number;
  maxDrawdown: number;
  beta: number;
  correlationToBenchmark: number;
  sectorExposure: Record<string, number>;
  factorExposure: Record<string, number>;
}

export interface PortfolioSimulationMetrics {
  totalReturn: number;
  annReturn: number;
  sharpe: number;
  maxDrawdown: number;
  winRate: number | null;
}

export interface PortfolioSimulationHolding {
  etf: string;
  signal: string;
  weight: number;
  pnlPct: number;
  entryDate: string;
}

export interface PortfolioSimulationData {
  inceptionDate: string;
  benchmark: string;
  metrics: {
    terminal: PortfolioSimulationMetrics;
    benchmark6040: PortfolioSimulationMetrics;
    spy: PortfolioSimulationMetrics;
  };
  holdings: PortfolioSimulationHolding[];
  monthsTracked: number;
  monthlyReturns: number[];
  benchmarkReturns: number[];
  lastUpdated: string;
}

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

// =============================================================================
// PHASE 6 TYPES - Factor Rotation, Geopolitical Risk, Options, Trends
// =============================================================================

export interface FactorRotationData {
  currentRegime: string;
  factors: FactorData[];
  topPicks: string[];
  avoid: string[];
  regimeFactorSummary: string;
  lastUpdated: string;
}

export interface FactorData {
  factor: string;
  ticker: string;
  name: string;
  regimeBase: number;
  momentum3m: number;
  momentum12m: number;
  relativeStrength: number;
  percentile52w: number;
  compositeScore: number;
  signal: 'OVERWEIGHT' | 'SLIGHT OVERWEIGHT' | 'NEUTRAL' | 'SLIGHT UNDERWEIGHT' | 'UNDERWEIGHT';
  conviction: 'High' | 'Medium' | 'Low';
  rationale: string;
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

// Component Props Types

export interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
  loading?: boolean;
}

export interface MetricCardProps {
  label: string;
  value: string;
  direction?: 'up' | 'down' | 'neutral';
  sparklineData?: number[];
  color?: string;
}

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
}

export interface TableProps<T> {
  data: T[];
  columns: TableColumn<T>[];
  keyExtractor: (item: T) => string;
}

export interface TableColumn<T> {
  header: string;
  accessor: keyof T | ((item: T) => React.ReactNode);
  align?: 'left' | 'center' | 'right';
}

export interface SparklineProps {
  data: number[];
  color?: string;
  height?: number;
  width?: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PHASE 7 TYPE DEFINITIONS
// ═══════════════════════════════════════════════════════════════════════════════

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

export interface ReflexivityLoop {
  loop: string;
  id: string;
  active: boolean;
  strength: number;
  severity: string;
  correlation: number;
  variables: {
    cause: {
      name: string;
      trend: string;
      change3m: number;
    };
    effect: {
      name: string;
      trend: string;
      change3m: number;
    };
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

export interface HorizonAnalysisData {
  assetAnalysis: AssetHorizonAnalysis[];
  tensionSummary: HorizonTensionSummary;
  actionableSummary: HorizonActionableSummary;
  lastUpdated: string;
  error?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PHASE 8 TYPE DEFINITIONS — ML Layer
// ═══════════════════════════════════════════════════════════════════════════════

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

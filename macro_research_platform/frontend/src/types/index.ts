// ─────────────────────────────────────────────────────────────────────────────
// API Response Types
// Central type definitions for all dashboard data consumed by the frontend.
// ─────────────────────────────────────────────────────────────────────────────

// ── Top-level dashboard payload ──────────────────────────────────────────────

export interface DashboardData {
  regime: RegimeData;
  keyMetrics: KeyMetrics;
  scores: Scores;
  signals: SignalsData;
  morningBrief?: MorningBriefData;
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
  alerts?: AlertsData;
  internationalMacro?: InternationalMacroData;
  debtCycle?: DebtCycleData;
  riskParityAllocation?: RiskParityData;
  regimeTransitions?: TransitionMatrixData;
  pureAlpha?: PureAlphaData;
  portfolioAnalytics?: PortfolioAnalytics;
  expectedReturns?: ExpectedReturnsData;
  factorRotation?: FactorRotationData;
  geopoliticalRisk?: GeopoliticalRiskData;
  optionsIntelligence?: OptionsIntelligenceData;
  trendSignals?: TrendSignalsData;
  newsSentiment?: NewsSentimentData;
  gmoForecasts?: GMOForecastsData;
  reflexivity?: ReflexivityData;
  factorDecomposition?: FactorDecompositionData;
  horizonAnalysis?: HorizonAnalysisData;
  anomalyDetection?: AnomalyDetectionData;
  lstmPrediction?: LSTMPredictionData;
  ensembleSignal?: EnsembleSignalData;
  performanceTracking?: PerformanceTrackingData;
  systemHealth?: SystemHealthData;
  portfolioSimulation?: PortfolioSimulationData;
  equityResearch?: EquityResearchData;
  tradeIdeas?: TradeIdeasData;
  tradeRecommendations?: TradeRecommendationsData;
  eventCalendar?: EventCalendarData;
  scenarioAnalysis?: ScenarioAnalysisData;
}

// ── Morning Brief ─────────────────────────────────────────────────────────────

export interface MorningBriefPriority {
  type: 'calendar' | 'tension' | 'signal';
  priority: number;
  title: string;
  time?: string;
  date?: string;
  implication: string;
}

export interface MorningBriefRisk {
  type: string;
  text: string;
  severity: 'WARNING' | 'INFO' | 'CRITICAL';
}

export interface MorningBriefTrade {
  ticker: string;
  direction: 'LONG' | 'SHORT';
  conviction: 'HIGH' | 'MEDIUM' | 'LOW';
  rr?: number;
  entry?: number;
  target?: number;
  stop?: number;
  thesis?: string;
  category?: string;
  horizon_days?: number;
}

export interface MorningBriefData {
  date: string;
  regime: string;
  duration_months: number;
  confidence: number;
  priorities: MorningBriefPriority[];
  risks: MorningBriefRisk[];
  conviction_trades: MorningBriefTrade[];
  position_modifier: number;
  model_caution: boolean;
}

// ── Regime ────────────────────────────────────────────────────────────────────

export interface RegimeData {
  current: string;
  confidence: string;
  confidenceScore: number;
  duration: number;
  history: RegimeHistoryPoint[];
  interpretations: RegimeInterpretation[];
  playbook?: RegimePlaybookData;
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

export interface RegimePlaybookData {
  regime: string;
  summary: string;
  assetAllocation: PlaybookAssetAllocation[];
  factorPreferences: PlaybookFactorPreference[];
  riskGuidelines: PlaybookRiskGuideline[];
  historicalPerformance: PlaybookHistoricalPerformance;
  tradeSetup: PlaybookTradeSetup;
}

export interface PlaybookAssetAllocation {
  asset: string;
  bias: 'LONG' | 'SHORT' | 'NEUTRAL';
  conviction: 'HIGH' | 'MEDIUM' | 'LOW';
  sizing: string;
  rationale: string;
}

export interface PlaybookFactorPreference {
  factor: string;
  preference: 'OVERWEIGHT' | 'UNDERWEIGHT' | 'NEUTRAL';
  conviction: 'HIGH' | 'MEDIUM' | 'LOW';
  rationale: string;
}

export interface PlaybookRiskGuideline {
  rule: string;
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  description: string;
}

export interface PlaybookHistoricalPerformance {
  avgReturn: number;
  winRate: number;
  avgDuration: number;
  bestAsset: string;
  worstAsset: string;
}

export interface PlaybookTradeSetup {
  primaryTrade: string;
  secondaryTrade: string;
  exitTrigger: string;
  timeHorizon: string;
}

// ── Key Metrics & Scores ─────────────────────────────────────────────────────

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

// ── Signals ───────────────────────────────────────────────────────────────────

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
  historyLabels?: string[];
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

// ── Sector & Factor Allocation ────────────────────────────────────────────────

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

// ── Risk ──────────────────────────────────────────────────────────────────────

export interface RiskIndicatorsData {
  indicators: RiskIndicator[];
  compositeScore: number;
  regime: string;
}

export interface RiskIndicator {
  name: string;
  value: string;
  level: 'low' | 'medium' | 'high' | 'extreme';
  interpretation: string;
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

// ── Business Layer ────────────────────────────────────────────────────────────

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

// ── Model Agreement & Transmission ───────────────────────────────────────────

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

// ── Investment Memo & Data Watch ──────────────────────────────────────────────

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
  lastRefreshed: string;
  dataStatus: 'current' | 'acceptable' | 'stale' | 'unknown';
  daysSinceUpdate: number;
  mode: 'live' | 'sample';
  validationWarnings?: string[];
  supportingEvidence?: string[];
}

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

// ── Correlation & Portfolio Construction ──────────────────────────────────────

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

// ── International Macro & Regime Transitions ──────────────────────────────────

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

// ── Debt Cycle ────────────────────────────────────────────────────────────────

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
  // Three-horizon format (current)
  short_term?: HorizonSignalData;
  medium_term?: HorizonSignalData;
  long_term?: HorizonSignalData;
  tensions?: HorizonTension[];
  aligned_count?: number;
  recommendation?: string;
  position_size_modifier?: number;
  // Legacy format
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

// ── Alerts ────────────────────────────────────────────────────────────────────

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

// ── Equity Research ───────────────────────────────────────────────────────────

export interface SectorRec {
  sector: string;
  signal: string;
  confidence: number;
  expectedReturn: number;
  macroDrivers: string[];
  weight?: number;
}

export interface CountryPick {
  country: string;
  ticker: string;
  score: number;
}

export interface EquityValuationData {
  regime: string;
  currentPE: number;
  targetPE: number;
  upsidePotential: number;
  signal: string;
}

export interface EquityResearchData {
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
  valuation: EquityValuationData;
  countryRanking: {
    globalRegime: string;
    allocation: Record<string, number>;
    topMarkets: CountryPick[];
  };
  lastUpdated: string;
  note?: string;
}

// ── Trade Ideas ───────────────────────────────────────────────────────────────

export interface TradeIdea {
  id: number | string;
  ticker: string;
  direction: 'LONG' | 'SHORT';
  thesis: string;
  entry?: number | null;
  target?: number | null;
  stop?: number | null;
  rr?: number;
  kelly_size?: number;
  suggested_size?: number;
  position_size_pct?: number;
  horizon_days: number;
  conviction: 'HIGH' | 'MEDIUM' | 'LOW';
  category: string;
  regime_valid: boolean;
  regime_current: string;
  status: 'ACTIVE' | 'REVIEW';
  days_open: number;
  pnl_pct: number;
  exit_conditions: string[];
}

export interface TradeIdeasData {
  ideas?: TradeIdea[];
  regime?: string;
  total_ideas?: number;
  generated_at?: string;
  risk_budget?: number;
}

// ── Trade Recommendations (Dynamic Engine) ────────────────────────────────────

export interface TradeComponentScores {
  regime_alignment: number;
  factor_alignment: number;
  momentum: number;
  fundamental: number;
  macro: number;
  analyst: number;
}

export interface TradeRecommendation {
  ticker: string;
  name: string;
  asset_class: string;
  sector: string;
  factor: string;
  composite_score: number;
  confidence: number;
  component_scores: TradeComponentScores;
  kelly_pct: number;
  position_pct?: number;
  market_cap: number;
  avg_volume: number;
  last_price: number;
  pe?: number;
  div_yield?: number;
  beta?: number;
}

export interface PairTrade {
  long_ticker: string;
  long_name: string;
  short_ticker: string;
  short_name: string;
  sector: string;
  regime: string;
  long_score: number;
  short_score: number;
  net_score: number;
  long_position: number;
  short_position: number;
}

export interface TradeRecommendationsSummary {
  total_scored: number;
  qualified_count: number;
  long_count: number;
  short_count: number;
  avg_confidence: number;
  avg_long_score: number;
  avg_short_score: number;
  pair_trade_count: number;
}

export interface TradeRecommendationsData {
  regime: string;
  macro_score: number;
  generated_at: string;
  longs: TradeRecommendation[];
  shorts: TradeRecommendation[];
  pair_trades: PairTrade[];
  summary: TradeRecommendationsSummary;
  duration_seconds?: number;
}

// ── Economic Calendar ─────────────────────────────────────────────────────────

export interface CalendarEvent {
  id: number;
  event_name: string;
  importance: 'HIGH' | 'MEDIUM' | 'LOW';
  release_datetime: string;
  time_et?: string;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  affected_assets?: string[];
}

export interface EventCalendarData {
  upcoming?: CalendarEvent[];
  this_week?: CalendarEvent[];
  blackout_active?: boolean;
  minutes_to_next?: number;
}

// ── Scenario Analysis ─────────────────────────────────────────────────────────

export interface ScenarioData {
  scenario: string;
  probability: number;
  expectedReturn: number;
  confidenceInterval: [number, number];
  description: string;
  trigger: string;
  regime_shift: string;
}

export interface ScenarioAnalysisData {
  regime: string;
  scenarios: ScenarioData[];
  timestamp: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// UI Component Prop Types
// ─────────────────────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────────────────────
// Unified Dashboard API Response (Phase 1 Standardized)
// ─────────────────────────────────────────────────────────────────────────────

export interface UnifiedDashboardResponse {
  prices: {
    SPX: number | null;
    NDX: number | null;
    VIX: number | null;
    TENYR: number | null;
    TWYR: number | null;
    FED: number | null;
    DXY: number | null;
    EURUSD: number | null;
    GBPUSD: number | null;
    USDJPY: number | null;
    USDCAD: number | null;
    USDCHF: number | null;
    AUDUSD: number | null;
    NZDUSD: number | null;
    GLD: number | null;
    WTI: number | null;
  };
  changes: Record<string, number | null>;
  regime: {
    current: string | null;
    confidence: number | null;
    duration: number | null;
    probabilities: {
      goldilocks: number | null;
      reflation: number | null;
      stagflation: number | null;
      slowdown: number | null;
    };
  };
  signals: {
    growth: {
      score: number | null;
      threeMonth: number | null;
      state: string | null;
    };
    inflation: {
      score: number | null;
      threeMonth: number | null;
      state: string | null;
    };
    liquidity: {
      score: number | null;
      threeMonth: number | null;
      state: string | null;
    };
    risk: {
      score: number | null;
      threeMonth: number | null;
      state: string | null;
    };
  };
  ensemble: {
    score: number | null;
    conviction: string | null;
    agreement: number | null;
    riskBudget: number | null;
  };
  meta: {
    latestDate: string | null;
    dataStatus: 'loading' | 'live' | 'stale' | 'error';
    lastUpdated: string | null;
  };
}

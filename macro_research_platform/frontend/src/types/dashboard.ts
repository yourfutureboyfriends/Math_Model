/**
 * Dashboard and regime types
 * Contains: Dashboard data, regime, key metrics, sectors, business layer
 */

import type {
  RiskIndicatorsData,
  AdvancedIndicatorsData,
  RecessionData,
  AlertsData,
  PortfolioAnalytics,
  TradeIdeasData,
  TradeRecommendationsData,
  PortfolioSimulationData,
} from './risk';

import type {
  NowcastData,
  LiquidityConditionsData,
  SentimentRiskData,
  ValuationFilterData,
  MomentumVetoData,
  CorrelationRegimeData,
  RiskParityData,
  PureAlphaData,
  TrendSignalsData,
  NewsSentimentData,
  GMOForecastsData,
  ReflexivityData,
  FactorDecompositionData,
  HorizonAnalysisData,
  AnomalyDetectionData,
  LSTMPredictionData,
  EnsembleSignalData,
  PerformanceTrackingData,
  SystemHealthData,
  GeopoliticalRiskData,
  OptionsIntelligenceData,
  ExpectedReturnsData,
} from './signals';

// ── UI Component Prop Types ─────────────────────────────────────────────────

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

// ── Sector & Factor Allocation ─────────────────────────────────────────────────

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

// ── Business Layer ───────────────────────────────────────────────────────────

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

// ── Investment Memo & Data Watch ─────────────────────────────────────────────

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

// ── International Macro & Regime Transitions ───────────────────────────────────

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

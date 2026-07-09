"""
Pydantic models for API request/response schemas.

Extracted from main.py for better organization.
"""
from pydantic import BaseModel, field_validator, Field
from typing import List, Dict, Optional, Any
from datetime import datetime
import numpy as np


# ══════════════════════════════════════════════════════════════
# REGIME MODELS
# ══════════════════════════════════════════════════════════════

class RegimePlaybookData(BaseModel):
    """Regime-specific playbook/guidance."""
    summary: str
    keyRisks: List[str]
    opportunities: List[str]
    positioningGuidance: str


class RegimeData(BaseModel):
    """Regime classification response."""
    current: str
    confidence: str  # Textual confidence (e.g., "high", "medium", "low")
    confidenceScore: float  # Numeric confidence score 0-1
    duration: int
    history: List[Dict[str, str]]
    interpretations: List[Dict[str, str]]
    alert: Optional[str] = None
    playbook: Optional[RegimePlaybookData] = None

    @field_validator('confidenceScore', mode='before')
    @classmethod
    def clean_confidence_score(cls, v):
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return 0.0
        return round(float(v), 6) if v is not None else 0.0

    @classmethod
    def default(cls) -> "RegimeData":
        return cls(
            current="Unknown",
            confidence="low",
            confidenceScore=0.0,
            duration=0,
            history=[],
            interpretations=[],
            alert=None
        )


class RegimeContextData(BaseModel):
    """Regime context for dashboard (mirrors RegimeContext dataclass)."""
    regime: str
    confidence: float
    growth_zscore: float
    inflation_zscore: float
    liquidity_zscore: float
    duration_months: int
    timestamp: float

    class Config:
        from_attributes = True


class CurrentRegimeValidation(BaseModel):
    """Current regime validation data."""
    activeRegime: str
    expectedSectors: List[str]
    unexpectedSectors: List[str]
    regimePersistence: int
    riskFlags: List[str]
    notes: str


class RegimeTransitionProbabilities(BaseModel):
    """Regime transition probabilities as 2D matrix."""
    transitions: List[Dict[str, Any]] = []
    currentRegime: str = ""
    mostLikelyNext: str = ""
    matrix: Dict[str, Dict[str, float]] = {}


class RegimeBacktestResult(BaseModel):
    """Regime backtest result."""
    regime: str
    sectors: List[Dict[str, Any]]
    summary: Dict[str, Any]


# ══════════════════════════════════════════════════════════════
# KEY METRICS MODELS
# ══════════════════════════════════════════════════════════════

class MetricWithSparkline(BaseModel):
    """Metric with historical sparkline data."""
    value: float
    formatted: str
    direction: str
    sparklineData: List[float]

    @field_validator('value', mode='before')
    @classmethod
    def clean_value(cls, v):
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return 0.0
        return round(float(v), 6)

    @field_validator('sparklineData', mode='before')
    @classmethod
    def clean_sparkline(cls, v):
        if not isinstance(v, list):
            return []
        return [0.0 if (isinstance(x, float) and (np.isnan(x) or np.isinf(x))) else round(float(x), 6) for x in v]

    @classmethod
    def default(cls) -> "MetricWithSparkline":
        return cls(
            value=0.0,
            formatted="—",
            direction="neutral",
            sparklineData=[]
        )


class KeyMetrics(BaseModel):
    """Key economic metrics."""
    growth: MetricWithSparkline
    inflation: MetricWithSparkline
    liquidity: MetricWithSparkline
    risk: MetricWithSparkline
    recession: MetricWithSparkline
    regimeDuration: Dict[str, str]
    spxLevel: Optional[float] = None
    spxChange: Optional[float] = None
    spxChangePct: Optional[float] = None
    ndxLevel: Optional[float] = None
    ndxChangePct: Optional[float] = None
    tenYearYield: Optional[float] = None
    tenYearChange: Optional[float] = None
    twoYearYield: Optional[float] = None
    dxy: Optional[float] = None
    dxyChangePct: Optional[float] = None
    eurusd: Optional[float] = None
    eurusdChangePct: Optional[float] = None
    gold: Optional[float] = None
    goldChangePct: Optional[float] = None
    oil: Optional[float] = None
    oilChangePct: Optional[float] = None
    fedRate: Optional[float] = None
    vix: Optional[float] = None
    vixChange: Optional[float] = None

    @classmethod
    def default(cls) -> "KeyMetrics":
        return cls(
            growth=MetricWithSparkline.default(),
            inflation=MetricWithSparkline.default(),
            liquidity=MetricWithSparkline.default(),
            risk=MetricWithSparkline.default(),
            recession=MetricWithSparkline.default(),
            regimeDuration={"current": "N/A"}
        )


# ══════════════════════════════════════════════════════════════
# SIGNAL MODELS
# ══════════════════════════════════════════════════════════════

class SignalDetails(BaseModel):
    """Signal details for signals panel.

    Field names match frontend TypeScript expectations (dashboard.ts).
    """
    # Primary field names matching frontend contract
    latestScore: float
    threeMonthChange: str  # Frontend expects string like "+0.2" or "-0.1"
    state: str
    direction: str = "stable"
    interpretation: str = ""
    history: List[float] = []
    historyLabels: Optional[List[str]] = None

    # Legacy fields kept for backward compatibility (will be deprecated)
    score: Optional[float] = None
    threeMonth: Optional[float] = None

    @field_validator('latestScore', 'score', 'threeMonth', mode='before')
    @classmethod
    def validate_signal_score(cls, v):
        """Validate signal score is a number, handle NaN/None."""
        if v is None:
            return None
        try:
            val = float(v)
            if np.isnan(val) or np.isinf(val):
                return 0.0
            return round(val, 4)
        except (ValueError, TypeError):
            return 0.0

    @field_validator('threeMonthChange', mode='before')
    @classmethod
    def validate_three_month_change(cls, v):
        """Ensure threeMonthChange is a formatted string."""
        if v is None:
            return "0.0"
        if isinstance(v, str):
            return v
        try:
            val = float(v)
            if np.isnan(val) or np.isinf(val):
                return "0.0"
            sign = "+" if val > 0 else ""
            return f"{sign}{val:.1f}"
        except (ValueError, TypeError):
            return "0.0"

    @field_validator('history', mode='before')
    @classmethod
    def validate_history(cls, v):
        """Ensure history array is never None."""
        return v if v is not None else []

    def model_post_init(self, __context):
        """Sync legacy fields with primary fields after validation."""
        if self.score is None and self.latestScore is not None:
            self.score = self.latestScore
        if self.threeMonth is None:
            # Parse from threeMonthChange string
            try:
                self.threeMonth = float(self.threeMonthChange.replace('+', ''))
            except (ValueError, AttributeError):
                self.threeMonth = 0.0


class SignalsData(BaseModel):
    """Signals data for signals panel."""
    finalSignal: str
    growth: SignalDetails
    inflation: SignalDetails
    liquidity: SignalDetails
    risk: SignalDetails


class SignalStackLayer(BaseModel):
    """Signal stack layer data."""
    layer: str
    priority: int
    signal: str
    conviction: float
    override: Optional[str] = None


class SignalStackResult(BaseModel):
    """Signal stack result."""
    finalStance: str
    finalSignal: str
    riskBudget: float
    conviction: float
    activeLayer: str
    overrideReason: Optional[str] = None
    reasoning: str
    layerOutputs: List[Dict[str, Any]]
    layers: List[SignalStackLayer]
    divergences: List[str]
    overridesApplied: List[str]
    lastUpdated: str
    timestamp: str


class SignalStackData(BaseModel):
    """Signal stack data."""
    layers: List[SignalStackLayer]
    finalSignal: str
    finalStance: Optional[str] = None
    confidence: float
    riskBudget: Optional[float] = None
    activeLayer: Optional[str] = None
    reasoning: Optional[str] = None
    layerOutputs: Optional[List[Dict[str, Any]]] = None
    divergences: Optional[List[str]] = None
    overridesApplied: Optional[List[str]] = None
    lastUpdated: Optional[str] = None
    timestamp: str


class SignalLayer(BaseModel):
    """Signal layer for stack."""
    name: str
    score: float
    weight: float


class SignalScorecardItem(BaseModel):
    """Signal scorecard item."""
    asset: str
    signal: str
    confidence: str
    score: float
    zScore: float
    rationale: str


# ══════════════════════════════════════════════════════════════
# SECTOR ALLOCATION MODELS
# ══════════════════════════════════════════════════════════════

class Sector(BaseModel):
    """Sector allocation data."""
    name: str
    score: float
    z_score: float
    allocation: float
    rationale: str
    signal: str = "Neutral"
    conviction: str = "Medium"


class SectorAllocationData(BaseModel):
    """Sector allocation response."""
    sectors: List[Sector]
    regime: str
    confidence: float
    totalScore: float


class SectorPerformance(BaseModel):
    """Sector performance data."""
    sector: str
    return_1m: float
    return_3m: float
    return_6m: float
    return_12m: float
    volatility: float


# ══════════════════════════════════════════════════════════════
# RISK PARITY MODELS
# ══════════════════════════════════════════════════════════════

class RiskParityItem(BaseModel):
    """Risk parity portfolio item."""
    ticker: str
    sector: str
    annualisedVol: float
    baseWeight: float
    signalScore: float
    signal: str
    conviction: str
    adjustedWeight: float
    targetAllocationPct: float


class RiskParityAllocationData(BaseModel):
    """Risk parity allocation response."""
    holdings: List[RiskParityItem]
    totalHoldings: int
    lastRebalanced: str
    methodology: str
    portfolioVol: Optional[float] = None
    diversificationRatio: Optional[float] = None
    regimeAdjustmentActive: bool
    lastUpdated: str


# ══════════════════════════════════════════════════════════════
# EXPECTED RETURNS MODELS
# ══════════════════════════════════════════════════════════════

class ExpectedReturnSector(BaseModel):
    """Expected return for a sector."""
    sector: str
    ticker: str
    earningsYield: float
    regimePremium: float
    expectedReturn: float
    currentWeight: float
    signal: str


class ExpectedReturnsResult(BaseModel):
    """Expected returns calculation result."""
    sectors: List[ExpectedReturnSector]
    weightedPortfolioReturn: float
    methodology: str
    lastUpdated: str


class ExpectedReturn(BaseModel):
    """Expected return data."""
    asset: str
    expectedReturn: float
    confidence: str
    components: Dict[str, float]


# ══════════════════════════════════════════════════════════════
# DEBT CYCLE MODELS
# ══════════════════════════════════════════════════════════════

class DebtCycleIndicator(BaseModel):
    """Debt cycle indicator."""
    name: str
    value: float
    zScore: float
    regime: str


class DebtCycleIndicators(BaseModel):
    """Collection of debt cycle indicators."""
    debtToGDP: DebtCycleIndicator
    creditImpulse: DebtCycleIndicator
    privateDebt: DebtCycleIndicator


class DebtCycleResult(BaseModel):
    """Debt cycle analysis result."""
    phase: str
    indicators: DebtCycleIndicators
    riskLevel: str
    transmissionChannels: List[str]


# ══════════════════════════════════════════════════════════════
# RECESSION MODELS
# ══════════════════════════════════════════════════════════════

class RecessionData(BaseModel):
    """Recession probability data."""
    probability: float
    level: str
    logisticProb: float
    emProbitProb: float
    sahmValue: float
    sahmSignal: str
    description: str
    components: List[Dict[str, Any]]
    history: List[Dict[str, Any]]

    @field_validator('probability', 'logisticProb', 'emProbitProb', mode='before')
    @classmethod
    def validate_probability(cls, v):
        """Validate probability is 0-1, handle NaN/None."""
        if v is None:
            return 0.0
        try:
            val = float(v)
            if np.isnan(val) or np.isinf(val):
                return 0.0
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.0

    @field_validator('components', 'history', mode='before')
    @classmethod
    def validate_arrays(cls, v):
        """Ensure arrays are never None."""
        return v if v is not None else []


# ══════════════════════════════════════════════════════════════
# ALERTS MODELS
# ══════════════════════════════════════════════════════════════

class AlertItem(BaseModel):
    """Individual alert."""
    severity: str
    message: str
    timestamp: str
    category: Optional[str] = None
    id: Optional[str] = None
    type: Optional[str] = None
    active: Optional[bool] = None


class AlertsData(BaseModel):
    """Alerts data."""
    alerts: List[AlertItem]
    count: int
    lastUpdated: str


# ══════════════════════════════════════════════════════════════
# BUSINESS LAYER MODELS
# ══════════════════════════════════════════════════════════════

class BusinessRecommendation(BaseModel):
    """Business recommendation."""
    type: str
    headline: str
    rationale: str
    conviction: str
    timeHorizon: str


class PositionSizing(BaseModel):
    """Position sizing recommendation."""
    assetOrSector: str
    suggestedSize: float
    bucket: str
    conviction: str
    reason: str


class DecisionLogEntry(BaseModel):
    """Decision log entry."""
    timestamp: str
    recommendationType: str
    headline: str
    conviction: str
    suggestedPositionSize: Optional[str] = None


class BusinessLayerData(BaseModel):
    """Business layer data."""
    recommendations: Optional[str] = None
    expectedReturns: List[ExpectedReturnSector]
    positionSizing: List[PositionSizing]
    signalScorecard: List[SignalScorecardItem]
    decisionLog: List[DecisionLogEntry]


# ══════════════════════════════════════════════════════════════
# MACRO & FX MODELS
# ══════════════════════════════════════════════════════════════

class RegionMacroData(BaseModel):
    """Region macro data."""
    region: str
    regime: str
    score: float
    outlook: str


class RegimeDivergence(BaseModel):
    """Regime divergence between regions."""
    regions: List[str]
    divergenceScore: float
    implications: str


class FXImplication(BaseModel):
    """FX implication from regime analysis."""
    currency: str
    signal: str
    expectedMove: str


class InternationalMacroResult(BaseModel):
    """International macro analysis result."""
    regions: List[RegionMacroData]
    divergences: List[RegimeDivergence]
    fxImplications: List[FXImplication]


# ══════════════════════════════════════════════════════════════
# RISK INDICATOR MODELS
# ══════════════════════════════════════════════════════════════

class RiskIndicator(BaseModel):
    """Risk indicator."""
    name: str
    value: float
    signal: str
    weight: float


class RiskIndicatorsData(BaseModel):
    """Risk indicators data."""
    indicators: List[RiskIndicator]
    compositeScore: float
    riskLevel: str


class AdvancedIndicator(BaseModel):
    """Advanced risk indicator."""
    name: str
    value: float
    zScore: float
    signal: str


class AdvancedIndicatorsData(BaseModel):
    """Advanced indicators data."""
    indicators: Optional[List[AdvancedIndicator]] = None
    regime: Optional[str] = None
    timestamp: Optional[str] = None
    sahmRule: Optional[Dict[str, Any]] = None
    creditImpulse: Optional[Dict[str, Any]] = None
    lei: Optional[Dict[str, Any]] = None
    riskParity: Optional[Dict[str, Any]] = None
    lastUpdated: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# MODEL AGREEMENT MODELS
# ══════════════════════════════════════════════════════════════

class ModelAgreementItem(BaseModel):
    """Model agreement item."""
    model: str
    agreement: float


class ModelAgreementData(BaseModel):
    """Model agreement data."""
    items: List[ModelAgreementItem]
    consensus: float


# ══════════════════════════════════════════════════════════════
# TRANSMISSION CHANNEL MODELS
# ══════════════════════════════════════════════════════════════

class TransmissionChannel(BaseModel):
    """Transmission channel."""
    name: str
    strength: float
    direction: str


class TransmissionAnalysisData(BaseModel):
    """Transmission analysis data."""
    channels: List[TransmissionChannel]
    primaryChannel: str
    lagMonths: int


# ══════════════════════════════════════════════════════════════
# INVESTMENT MEMO MODELS
# ══════════════════════════════════════════════════════════════

class DataToWatchItem(BaseModel):
    """Data to watch item."""
    indicator: str
    expectedImpact: str
    nextRelease: Optional[str] = None


class InvestmentMemoData(BaseModel):
    """Investment memo data."""
    summary: str
    keyPoints: List[str]
    dataToWatch: List[DataToWatchItem]
    updatedAt: str


# ══════════════════════════════════════════════════════════════
# NOWCAST MODELS
# ══════════════════════════════════════════════════════════════

class NowcastComponent(BaseModel):
    """Nowcast component."""
    name: str
    weight: float
    contribution: float
    status: str


class NowcastData(BaseModel):
    """Nowcast data."""
    gdpNowcast: float
    nowcastQoQ: float
    nowcastYoY: float
    confidenceInterval: Dict[str, Any]
    components: List[NowcastComponent]
    revisionHistory: List[Dict[str, Any]]
    methodology: str
    lastUpdated: str


# ══════════════════════════════════════════════════════════════
# LIQUIDITY MODELS
# ══════════════════════════════════════════════════════════════

class LiquidityIndicator(BaseModel):
    """Liquidity indicator."""
    name: str
    value: float
    status: str
    contribution: float


class LiquidityConditionsData(BaseModel):
    """Liquidity conditions data."""
    indicators: List[LiquidityIndicator]
    liquidityScore: float
    regime: str


# ══════════════════════════════════════════════════════════════
# SENTIMENT MODELS
# ══════════════════════════════════════════════════════════════

class SentimentGauge(BaseModel):
    """Sentiment gauge."""
    name: str
    score: float
    interpretation: str


class SentimentRiskData(BaseModel):
    """Sentiment risk data."""
    gauges: List[SentimentGauge]
    compositeScore: float
    riskLevel: str


# ══════════════════════════════════════════════════════════════
# VALUATION MODELS
# ══════════════════════════════════════════════════════════════

class ValuationMetric(BaseModel):
    """Valuation metric."""
    name: str
    value: float
    zScore: float
    percentile: float


class ValuationFilterData(BaseModel):
    """Valuation filter data."""
    metrics: List[ValuationMetric]
    summary: str


# ══════════════════════════════════════════════════════════════
# MOMENTUM MODELS
# ══════════════════════════════════════════════════════════════

class AssetMomentum(BaseModel):
    """Asset momentum data."""
    asset: str
    return12m: float
    return1m: float
    momentum12_1: float
    dampenedSignal: float
    rawSignal: str
    interpretation: str


class MomentumVetoData(BaseModel):
    """Momentum veto data."""
    vetoActive: bool
    dampenerApplied: float
    assets: List[AssetMomentum]
    portfolioAdjustment: Dict[str, Any]
    reasoning: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# CORRELATION MODELS
# ══════════════════════════════════════════════════════════════

class CorrelationPair(BaseModel):
    """Correlation pair."""
    assetPair: str
    correlation60d: float
    regime: str
    interpretation: str


class CorrelationRegimeData(BaseModel):
    """Correlation regime data."""
    currentRegime: str
    equityBondCorrelation: float
    switchTriggered: bool
    fallbackStrategy: str
    correlations: List[CorrelationPair]
    riskParityAdjustment: Dict[str, Any]


# ══════════════════════════════════════════════════════════════
# METADATA MODELS
# ══════════════════════════════════════════════════════════════

class DataMetadata(BaseModel):
    """Data metadata."""
    lastUpdated: str
    source: str
    freshness: str
    nextUpdate: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# DASHBOARD MODELS
# ══════════════════════════════════════════════════════════════

class Scores(BaseModel):
    """Composite scores for dashboard (0-100)."""
    growth: float = 50.0
    inflation: float = 50.0
    liquidity: float = 50.0
    risk: float = 50.0

    @field_validator('growth', 'inflation', 'liquidity', 'risk', mode='before')
    @classmethod
    def validate_score(cls, v):
        """Validate score is a number between 0-100, handle NaN/None."""
        if v is None:
            return 50.0
        try:
            val = float(v)
            if np.isnan(val) or np.isinf(val):
                return 50.0
            return max(0.0, min(100.0, val))
        except (ValueError, TypeError):
            return 50.0


# ══════════════════════════════════════════════════════════════
# PHASE 2: ADDITIONAL ANALYTICS MODELS
# ══════════════════════════════════════════════════════════════

class FactorRotationData(BaseModel):
    """Factor rotation analysis."""
    momentum: float = 0.5
    value: float = 0.3
    growth: float = 0.7
    quality: float = 0.6
    interpretation: str = ""
    rotationSignal: str = "Balanced"


class RegionMacro(BaseModel):
    """Macro regime for a specific region."""
    region: str
    regime: str
    confidence: float
    divergence: float  # Divergence from US regime


class InternationalMacroData(BaseModel):
    """International macro regime analysis."""
    regions: List[RegionMacro] = []
    globalSync: float = 0.65  # 0-1: how synchronized global regimes are
    interpretation: str = ""


class DebtCycleData(BaseModel):
    """Long-term debt cycle analysis."""
    phase: str = "Expansion"
    privateDebtGDP: float = 180.0
    publicDebtGDP: float = 120.0
    totalDebtGDP: float = 300.0
    debtServiceRatio: float = 12.5
    trend: str = "Rising"
    interpretation: str = ""


# ══════════════════════════════════════════════════════════════
# METADATA MODELS
# ══════════════════════════════════════════════════════════════

class EnsembleData(BaseModel):
    """Ensemble signal data matching frontend expectations."""
    score: float = 0.0
    conviction: str = "Medium"
    agreement: float = 0.0
    riskBudget: float = 0.5
    mode: str = "Dynamic"
    bullishPct: Optional[float] = None   # % of ensemble models bullish (0-100)

    @field_validator('score', 'agreement', 'riskBudget', mode='before')
    @classmethod
    def validate_ensemble_fields(cls, v):
        """Validate ensemble numeric fields."""
        if v is None:
            return 0.0
        try:
            val = float(v)
            if np.isnan(val) or np.isinf(val):
                return 0.0
            return val
        except (ValueError, TypeError):
            return 0.0


class DataMetadata(BaseModel):
    """Data quality metadata."""
    latestDate: str = ""
    lastRefreshed: str = ""
    dataStatus: str = "current"
    daysSinceUpdate: int = 0
    mode: str = "live"
    validationWarnings: Optional[str] = None
    supportingEvidence: Optional[str] = None

    @field_validator('daysSinceUpdate', mode='before')
    @classmethod
    def validate_days(cls, v):
        """Ensure daysSinceUpdate is non-negative integer."""
        if v is None:
            return 0
        try:
            val = int(v)
            return max(0, val)
        except (ValueError, TypeError):
            return 0

    @field_validator('dataStatus', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Ensure dataStatus is a valid string."""
        if v is None or not isinstance(v, str):
            return "current"
        return v.lower() if v else "current"


class DashboardData(BaseModel):
    """Complete dashboard response."""
    regime: RegimeData
    keyMetrics: KeyMetrics
    scores: Scores
    recession: RecessionData
    signals: SignalsData
    sectorAllocation: SectorAllocationData
    riskParity: RiskParityAllocationData
    expectedReturns: ExpectedReturnsResult
    businessLayer: Optional[BusinessLayerData] = None
    alerts: Optional[AlertsData] = None
    metadata: DataMetadata
    ensemble: Optional[EnsembleData] = None  # Added for frontend compatibility
    # Phase 2 optional fields
    factorRotation: Optional[FactorRotationData] = None
    internationalMacro: Optional[InternationalMacroData] = None
    debtCycle: Optional[DebtCycleData] = None
    # Additional fields for frontend compatibility (all optional, accept raw dicts)
    riskIndicators: Optional[Dict[str, Any]] = None
    advancedIndicators: Optional[Dict[str, Any]] = None
    modelAgreement: Optional[Dict[str, Any]] = None
    transmissionAnalysis: Optional[Dict[str, Any]] = None
    investmentMemo: Optional[Dict[str, Any]] = None
    dataToWatch: Optional[List[Dict[str, Any]]] = None
    nowcast: Optional[Dict[str, Any]] = None
    liquidity: Optional[Dict[str, Any]] = None
    sentiment: Optional[Dict[str, Any]] = None
    valuation: Optional[Dict[str, Any]] = None
    momentumVeto: Optional[MomentumVetoData] = None
    correlationRegime: Optional[CorrelationRegimeData] = None
    signalStack: Optional[SignalStackData] = None
    regime_confidence: Optional[float] = None
    regimePlaybook: Optional[RegimePlaybookData] = None
    # Extended optional fields (populated from individual handlers)
    riskParityAllocation: Optional[Dict[str, Any]] = None  # alias populated from riskParity
    gmoForecasts: Optional[Dict[str, Any]] = None
    reflexivity: Optional[Dict[str, Any]] = None
    factorDecomposition: Optional[Dict[str, Any]] = None
    anomalyDetection: Optional[Dict[str, Any]] = None
    lstmPrediction: Optional[Dict[str, Any]] = None
    pureAlpha: Optional[Dict[str, Any]] = None
    regimeTransitions: Optional[Dict[str, Any]] = None
    trendSignals: Optional[Dict[str, Any]] = None
    newsSentiment: Optional[Dict[str, Any]] = None
    performanceTracking: Optional[Dict[str, Any]] = None
    timestamp: str
    mode: str = "live"


# ══════════════════════════════════════════════════════════════
# AUTH MODELS
# ══════════════════════════════════════════════════════════════

class LoginResponse(BaseModel):
    """Login response."""
    success: bool
    token: Optional[str] = None
    error: Optional[str] = None


# ══════════════════════════════════════════════════════════════
# QUERY MODELS
# ══════════════════════════════════════════════════════════════

class AskRequest(BaseModel):
    """Ask request."""
    question: str
    context: Optional[str] = None


class AskResponse(BaseModel):
    """Ask response."""
    answer: str
    sources: List[str]
    confidence: float


# ══════════════════════════════════════════════════════════════
# MISSING MODELS - Added for runtime compatibility
# ══════════════════════════════════════════════════════════════

class NewsItem(BaseModel):
    """News item."""
    headline: str
    source: str
    timestamp: str
    sentiment: str
    relevance: float


class CalendarEvent(BaseModel):
    """Economic calendar event."""
    date: str
    time: Optional[str] = None
    country: str
    event: str
    impact: str
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None


class HistoricalPoint(BaseModel):
    """Historical data point."""
    date: str
    value: float


class SparklineData(BaseModel):
    """Sparkline data."""
    data: List[float]
    labels: Optional[List[str]] = None


class FinancialConditionsData(BaseModel):
    """Financial conditions data."""
    score: float
    level: str
    components: Dict[str, float]
    trend: str


class CreditImpulseData(BaseModel):
    """Credit impulse data."""
    value: float
    zScore: float
    trend: str
    components: Dict[str, float]


class LEIData(BaseModel):
    """Leading economic indicators data."""
    value: float
    change: float
    trend: str
    components: List[Dict[str, Any]]


class SahmRuleData(BaseModel):
    """Sahm rule data."""
    value: float
    signal: str
    threshold: float
    interpretation: str


class EstrellaMishkinData(BaseModel):
    """Estrella-Mishkin model data."""
    probability: float
    spread: float
    signal: str


class MacroIndicatorsData(BaseModel):
    """Macro indicators data."""
    indicators: List[Dict[str, Any]]
    regime: str
    timestamp: str


class MarketData(BaseModel):
    """Market data."""
    prices: Dict[str, float]
    changes: Dict[str, float]
    volumes: Dict[str, float]
    timestamp: str


class YieldCurveData(BaseModel):
    """Yield curve data."""
    tenYear: float
    twoYear: float
    spread: float
    inversion: bool


class FXData(BaseModel):
    """FX data."""
    rate: float
    change: float
    changePct: float


class CommodityData(BaseModel):
    """Commodity data."""
    price: float
    change: float
    unit: str


class PriceData(BaseModel):
    """Price data."""
    price: float
    change: float
    volume: Optional[int] = None


class AlertData(BaseModel):
    """Alert data."""
    id: str
    type: str
    severity: str
    message: str
    timestamp: str
    active: bool


class RiskMetrics(BaseModel):
    """Risk metrics."""
    var95: float
    cvar95: float
    maxDrawdown: float
    sharpe: float


class FullRiskData(BaseModel):
    """Full risk analytics data."""
    sharpe: float
    sortino: float
    calmar: float
    informationRatio: float
    beta: float
    var95: float
    cvar95: float
    maxDrawdown: float
    status: str
    drawdown: Dict[str, Any]
    riskAdjustedReturns: Dict[str, Any]
    correlation: Dict[str, Any]
    volatility: float


class FactorData(BaseModel):
    """Factor data."""
    name: str
    value: float
    zScore: float
    contribution: float


class TrendData(BaseModel):
    """Trend data."""
    direction: str
    strength: float
    duration: int


class PositionSizeData(BaseModel):
    """Position size data."""
    asset: str
    size: float
    maxSize: float
    confidence: float


class SignalScorecardData(BaseModel):
    """Signal scorecard data."""
    signals: List[SignalScorecardItem]
    lastUpdated: str


class ICPackData(BaseModel):
    """IC pack data."""
    name: str
    description: str
    signals: List[str]
    conviction: float


class TradeIdeaData(BaseModel):
    """Trade idea data."""
    asset: str
    direction: str
    entry: float
    stop: float
    target: float
    conviction: str
    rationale: str


class MorningBriefData(BaseModel):
    """Morning brief data."""
    date: str
    summary: str
    keyEvents: List[str]
    tradeIdeas: List[TradeIdeaData]


class ValidationMetrics(BaseModel):
    """Validation metrics."""
    accuracy: float
    precision: float
    recall: float
    f1Score: float


class RecessionProbabilityPoint(BaseModel):
    """Recession probability point."""
    date: str
    probability: float
    signal: str


class DrawdownData(BaseModel):
    """Drawdown data."""
    current: float
    max: float
    duration: int
    recovery: int


class RiskAdjustedReturnsData(BaseModel):
    """Risk adjusted returns data."""
    sharpe: float
    sortino: float
    calmar: float
    treynor: float


class CorrelationData(BaseModel):
    """Correlation data."""
    matrix: List[List[float]]
    assets: List[str]
    regime: str


class StressTestData(BaseModel):
    """Stress test data."""
    name: str
    scenario: str
    result: float
    status: str


# ═══════════════════════════════════════════════════════════════
# PHASE 3: RESPONSE WRAPPER MODELS
# ═══════════════════════════════════════════════════════════════

class TradeIdeasResponse(BaseModel):
    """Trade ideas list response."""
    ideas: List[TradeIdeaData]
    count: int
    lastUpdated: str


class DecisionLogResponse(BaseModel):
    """Decision log response."""
    entries: List[DecisionLogEntry]
    count: int
    total: int


class ExpectedReturnsResponse(BaseModel):
    """Expected returns response."""
    returns: List[ExpectedReturn]
    lastUpdated: str


class PositionSizingResponse(BaseModel):
    """Position sizing response."""
    recommendations: List[PositionSizeData]
    lastUpdated: str


class YieldPoint(BaseModel):
    """Yield curve point."""
    tenor: float
    yield_: float = Field(..., alias="yield")

    class Config:
        populate_by_name = True


class YieldCurveData(BaseModel):
    """Yield curve data for a country."""
    country: str = "US"
    points: List[YieldPoint]
    spread2s10s: Optional[float] = None
    spread3m10y: Optional[float] = None
    spread5s30s: Optional[float] = None
    realYield10y: Optional[float] = None
    shape: str = "unknown"
    recessionProb: Optional[float] = None


class CreditSpread(BaseModel):
    """Credit spread data."""
    name: str
    spreadBps: float
    signal: str


class RatesData(BaseModel):
    """Interest rates data - updated to match frontend expectations."""
    # New structure expected by frontend
    yieldCurves: Dict[str, YieldCurveData] = {}
    creditSpreads: List[CreditSpread] = []
    realYieldSignal: str = "neutral"

    # Legacy fields for backward compatibility
    tenYear: Optional[float] = None
    twoYear: Optional[float] = None
    fedFunds: Optional[float] = None
    yieldCurve: Optional[str] = None
    lastUpdated: str = ""


class ICPackResponse(BaseModel):
    """Investment Committee pack response."""
    pack: Dict[str, Any]
    generatedAt: str
    version: str


# ═══════════════════════════════════════════════════════════════
# PHASE 3: ADDITIONAL SIGNAL ENDPOINT MODELS
# ═══════════════════════════════════════════════════════════════

class TrendSignal(BaseModel):
    """Individual trend signal."""
    asset: str
    direction: str
    strength: float
    timeframe: str
    confidence: float


class TrendsData(BaseModel):
    """CTA Trend Following data."""
    signals: List[TrendSignal]
    aggregateScore: float
    regime: str
    lastUpdated: str


class NewsSentimentItem(BaseModel):
    """News sentiment item."""
    headline: str
    source: str
    sentiment: str
    score: float
    timestamp: str


class NewsSentimentData(BaseModel):
    """NLP News Sentiment data."""
    overallSentiment: str
    score: float
    trend: str
    articles: List[NewsSentimentItem]
    lastUpdated: str


class AssetClassForecast(BaseModel):
    """Forecast for an asset class."""
    assetClass: str
    expectedReturn: float
    volatility: float
    sharpeRatio: float
    confidence: float


class LongtermForecastsData(BaseModel):
    """GMO 7-Year Asset Class Return Model."""
    forecasts: List[AssetClassForecast]
    methodology: str
    asOfDate: str
    disclaimer: str


class ReflexivitySignal(BaseModel):
    """Reflexivity detection signal."""
    asset: str
    divergence: float
    feedbackLoop: str
    confidence: float


class ReflexivityData(BaseModel):
    """Soros Reflexivity Detector data."""
    signals: List[ReflexivitySignal]
    aggregateDivergence: float
    regime: str
    interpretation: str
    lastUpdated: str


class FactorDecompositionItem(BaseModel):
    """Factor decomposition item."""
    factor: str
    exposure: float
    contribution: float
    tStat: float
    significance: str


class FactorDecompositionData(BaseModel):
    """Two Sigma Factor Decomposition data."""
    asset: str
    rSquared: float
    factors: List[FactorDecompositionItem]
    residual: float
    lastUpdated: str


class GeopoliticalRiskEvent(BaseModel):
    """Geopolitical risk event."""
    region: str
    event: str
    severity: str
    probability: float
    impact: str
    timeframe: str


class GeopoliticalData(BaseModel):
    """Geopolitical Risk Layer data."""
    overallRisk: str
    score: float
    trend: str
    events: List[GeopoliticalRiskEvent]
    lastUpdated: str


class OptionsFlowItem(BaseModel):
    """Options flow item."""
    underlying: str
    expiration: str
    strike: float
    type: str
    volume: int
    openInterest: int
    impliedVol: float
    sentiment: str


class OptionsIntelligenceData(BaseModel):
    """Options Market Intelligence data."""
    underlying: str
    currentPrice: float
    impliedVolRank: float
    putCallRatio: float
    unusualActivity: List[OptionsFlowItem]
    keyLevels: Dict[str, float]
    sentiment: str
    lastUpdated: str

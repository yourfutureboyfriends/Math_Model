"""
Pydantic models for API request/response schemas.

Extracted from main.py for better organization.
"""
from pydantic import BaseModel, field_validator
from typing import List, Dict, Optional, Any
from datetime import datetime
import numpy as np


# ══════════════════════════════════════════════════════════════
# REGIME MODELS
# ══════════════════════════════════════════════════════════════

class RegimeData(BaseModel):
    """Regime classification response."""
    current: str
    confidence: str
    confidenceScore: float
    duration: int
    history: List[Dict[str, str]]
    interpretations: List[Dict[str, str]]
    alert: Optional[str] = None

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


class CurrentRegimeValidation(BaseModel):
    """Current regime validation data."""
    activeRegime: str
    expectedSectors: List[str]
    unexpectedSectors: List[str]
    regimePersistence: int
    riskFlags: List[str]
    notes: str


class RegimeTransitionProbabilities(BaseModel):
    """Regime transition probabilities."""
    current: str
    probabilities: Dict[str, float]
    notes: str


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
    """Signal details for signals panel."""
    score: float
    threeMonth: float
    state: str


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


class SignalLayerItem(BaseModel):
    """Signal layer item for stack."""
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
    layers: List[SignalLayerItem]
    divergences: List[str]
    overridesApplied: List[str]
    lastUpdated: str
    timestamp: str


class SignalStackData(BaseModel):
    """Signal stack data."""
    layers: List[SignalStackLayer]
    finalSignal: str
    confidence: float
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


# ══════════════════════════════════════════════════════════════
# ALERTS MODELS
# ══════════════════════════════════════════════════════════════

class AlertItem(BaseModel):
    """Individual alert."""
    severity: str
    message: str
    timestamp: str
    category: str


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
    asset: str
    size: float
    conviction: str
    riskContribution: float


class DecisionLogEntry(BaseModel):
    """Decision log entry."""
    timestamp: str
    recommendationType: str
    headline: str
    conviction: str
    suggestedPositionSize: Optional[str] = None


class BusinessLayerData(BaseModel):
    """Business layer data."""
    recommendations: List[str]
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
    indicators: List[AdvancedIndicator]
    regime: str
    timestamp: str


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

class DashboardData(BaseModel):
    """Complete dashboard response."""
    regime: RegimeData
    keyMetrics: KeyMetrics
    recession: RecessionData
    signals: SignalsData
    sectorAllocation: SectorAllocationData
    riskParity: RiskParityAllocationData
    expectedReturns: ExpectedReturnsResult
    businessLayer: Optional[BusinessLayerData] = None
    alerts: Optional[AlertsData] = None
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

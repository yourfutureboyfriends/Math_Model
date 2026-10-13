"""Pydantic schemas for API requests and responses."""

from typing import Dict, List, Optional
from pydantic import BaseModel


class RegimeData(BaseModel):
    date: str
    regime: str
    growth: Optional[float] = None
    inflation: Optional[float] = None
    growth_roc: Optional[float] = None
    inflation_roc: Optional[float] = None
    regime_display: str
    regime_color: str
    recession_probability: Optional[float] = None


class MetricWithSparkline(BaseModel):
    label: str
    value: str
    raw_value: float
    sparkline: List[float]
    color: Optional[str] = None


class KeyMetrics(BaseModel):
    last_updated: str
    metrics: List[MetricWithSparkline]


class SignalDetails(BaseModel):
    name: str
    value: float
    direction: str
    confidence: float
    last_updated: str


class SignalsData(BaseModel):
    last_updated: str
    signals: List[SignalDetails]


class Sector(BaseModel):
    name: str
    ticker: str
    expected_return: float
    z_score: float
    regime_aligned: bool


class SectorAllocationData(BaseModel):
    last_updated: str
    sectors: List[Sector]


class RiskParityItem(BaseModel):
    asset: str
    weight: float
    leverage: float
    volatility: float
    contribution: float


class RiskParityAllocationData(BaseModel):
    last_updated: str
    assets: List[RiskParityItem]


class RegimeTransitionProbabilities(BaseModel):
    current_regime: str
    probabilities: Dict[str, float]
    avg_duration_days: int
    last_transition: Optional[str] = None


class DebtCycleIndicator(BaseModel):
    label: str
    value: float
    direction: str
    threshold: float
    status: str


class DebtCycleIndicators(BaseModel):
    total_debt_to_gdp: float
    change_1y: float
    change_5y: float
    regime: str


class DebtCycleResult(BaseModel):
    regime: str
    indicators: DebtCycleIndicators
    risk_level: str


class SignalStackLayer(BaseModel):
    layer: str
    signal: str
    confidence: float
    priority: int


class SignalLayerItem(BaseModel):
    name: str
    weight: float
    contribution: float
    status: str


class SignalStackResult(BaseModel):
    final_signal: str
    confidence: float
    layers: List[SignalLayerItem]
    timestamp: str


class ExpectedReturnSector(BaseModel):
    sector: str
    expected_return: float
    volatility: float
    sharpe: float
    regime_aligned: bool


class ExpectedReturnsResult(BaseModel):
    sectors: List[ExpectedReturnSector]
    risk_free_rate: float
    timestamp: str


class SectorPerformance(BaseModel):
    sector: str
    return_1m: float
    return_3m: float
    return_6m: float
    return_12m: float


class CurrentRegimeValidation(BaseModel):
    regime: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    sample_size: int


class RegimeBacktestResult(BaseModel):
    start_date: str
    end_date: str
    cumulative_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float


class AlertItem(BaseModel):
    id: str
    severity: str
    message: str
    category: str
    timestamp: str
    acknowledged: bool = False


class AlertsData(BaseModel):
    alerts: List[AlertItem]
    unread_count: int


class RegionMacroData(BaseModel):
    region: str
    gdp_growth: float
    inflation: float
    unemployment: float
    policy_rate: float
    leading_indicators: float
    regime: str


class RegimeDivergence(BaseModel):
    region: str
    divergence_score: float
    vs_us: float


class FXImplication(BaseModel):
    pair: str
    signal: str
    strength: float


class InternationalMacroResult(BaseModel):
    regions: List[RegionMacroData]
    divergences: List[RegimeDivergence]
    fx_implications: List[FXImplication]


class RiskIndicator(BaseModel):
    name: str
    value: float
    percentile: Optional[float] = None
    level: str


class RiskIndicatorsData(BaseModel):
    composite_score: float
    regime: str
    indicators: List[RiskIndicator]


class AdvancedIndicator(BaseModel):
    name: str
    value: float
    normalized_score: float
    weight: float
    weighted_contribution: float


class AdvancedIndicatorsData(BaseModel):
    indicators: List[AdvancedIndicator]
    composite_score: float
    interpretation: str


class RecessionData(BaseModel):
    probability: float
    estimated_months_ahead: Optional[int] = None
    leading_indicators: List[str]
    confidence: str


class BusinessRecommendation(BaseModel):
    action: str
    confidence: float
    rationale: str
    timeframe: str


class ExpectedReturn(BaseModel):
    asset_class: str
    expected_return: float
    confidence_interval: tuple[float, float]


class PositionSizing(BaseModel):
    asset_class: str
    base_allocation: float
    adjusted_allocation: float
    risk_budget: float


class SignalScorecardItem(BaseModel):
    signal: str
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None
    sample_size: Optional[int] = None
    category: Optional[str] = None
    status: Optional[str] = None
    confidence: Optional[str] = None
    description: Optional[str] = None
    researchSupport: Optional[str] = None


class DecisionLogEntry(BaseModel):
    timestamp: str
    decision: str
    rationale: str
    outcome: Optional[str] = None
    pnl: Optional[float] = None


class BusinessLayerData(BaseModel):
    recommendations: List[BusinessRecommendation]
    expected_returns: List[ExpectedReturn]
    position_sizing: List[PositionSizing]
    signal_scorecard: List[SignalScorecardItem]
    decision_log: List[DecisionLogEntry]


class ModelAgreementItem(BaseModel):
    model: str
    signal: str
    strength: float
    confidence: float


class ModelAgreementData(BaseModel):
    agreement_ratio: float
    models: List[ModelAgreementItem]


class TransmissionChannel(BaseModel):
    channel: str
    impact: str
    lag_days: int
    confidence: float

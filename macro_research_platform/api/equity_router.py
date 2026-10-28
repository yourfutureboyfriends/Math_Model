"""
Equity Router — Equity Research API Endpoints

Exposes:
- /equity/sector-rotation — Regime-aware sector recommendations
- /equity/factor-rotation — Factor timing model
- /equity/earnings-revision — Earnings revision analysis
- /equity/macro-valuation — Regime-conditional valuation
- /equity/country-ranking — Macro-driven market selection
- /equity/stock-screener — Macro-aware stock filtering
- /equity/event-calendar — Macro event tracking
- /equity/dashboard — Complete equity dashboard
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import pandas as pd

from equity.sector_rotation import (
    SectorRotationEngine,
)
from equity.factor_rotation import (
    FactorRotationEngine,
)
from equity.earnings_revision import (
    EarningsRevisionAnalyzer,
    get_earnings_momentum_picks,
)
from equity.macro_valuation import (
    MacroValuationEngine,
    get_valuation_signal,
)
from equity.country_ranking import (
    CountryRankingEngine,
)
from equity.stock_screener import (
    create_default_screener,
    get_screening_summary,
)
from equity.event_calendar import (
    create_default_calendar,
    get_event_risk_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/equity", tags=["equity"])


# Dynamic Regime Configuration — No Hardcoded Defaults


import sqlite3
from pathlib import Path

def get_current_regime() -> str:
    """
    Fetch current regime from authoritative source.
    Reads from macro_platform.db regime_history table (live HMM output).
    Falls back to Slowdown if no data (conservative default).
    """
    try:
        db_path = Path(__file__).parent.parent / "database" / "macro_platform.db"
        conn = sqlite3.connect(str(db_path))
        # Get most recent regime
        row = conn.execute('''
            SELECT regime FROM regime_history
            ORDER BY recorded_at DESC LIMIT 1
        ''').fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception as e:
        logger.warning(f"[EQUITY] Failed to fetch regime from DB: {e}")

    # Fallback: check if we can get regime from CSV data
    try:
        csv_path = Path(__file__).parent.parent / "data" / "us_economic_data.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            if len(df) > 0:
                # Use growth and inflation to determine regime
                latest = df.iloc[-1]
                growth = latest.get('gdp_growth', 0)
                inflation = latest.get('core_cpi_yoy', latest.get('us_cpi', 0))
                # Classify
                if growth > 2.0 and inflation < 2.5:
                    return "Goldilocks"
                elif growth > 2.0 and inflation >= 2.5:
                    return "Reflation"
                elif growth <= 2.0 and inflation >= 2.5:
                    return "Stagflation"
                else:
                    return "Slowdown"
    except Exception as e:
        logger.warning(f"[EQUITY] Failed to derive regime from CSV: {e}")

    logger.warning("[EQUITY] Using Slowdown as fallback regime")
    return "Slowdown"  # Conservative fallback


# Regime-specific factor weights (normalized to sum to 1)
# Based on historical factor performance by regime
REGIME_FACTOR_WEIGHTS = {
    'Goldilocks':  {'value': 0.16, 'momentum': 0.26, 'quality': 0.20, 'growth': 0.28, 'low_vol': 0.10},
    'Slowdown':    {'value': 0.20, 'momentum': 0.05, 'quality': 0.40, 'growth': 0.05, 'low_vol': 0.30},
    'Reflation':   {'value': 0.30, 'momentum': 0.15, 'quality': 0.15, 'growth': 0.25, 'low_vol': 0.15},
    'Stagflation': {'value': 0.25, 'momentum': 0.05, 'quality': 0.35, 'growth': 0.05, 'low_vol': 0.30},
    'Crisis':      {'value': 0.10, 'momentum': 0.00, 'quality': 0.50, 'growth': 0.00, 'low_vol': 0.40},
}

# Regime-specific thesis statements
REGIME_THESIS = {
    'Goldilocks':  'Goldilocks regime: growth and momentum factors historically outperform. Quality and growth maintain exposure.',
    'Slowdown':    'Slowdown regime: quality and low-volatility factors outperform. Avoid growth and momentum. Focus on defensive positioning.',
    'Reflation':   'Reflation regime: value and cyclical factors lead. Inflation beneficiaries outperform. Growth maintains moderate exposure.',
    'Stagflation': 'Stagflation regime: quality and real assets outperform. Avoid duration and high-multiple growth. Maximum defensive positioning.',
    'Crisis':      'Crisis regime: capital preservation dominant. Maximum quality and minimum volatility. Avoid all cyclical exposure.',
}

# Regime-specific sector scores (-2 to +2)
# +2 = Strong OW, +1 = OW, 0 = Neutral, -1 = UW, -2 = Strong UW
REGIME_SECTOR_SCORES = {
    'Goldilocks':  {'XLK': 2, 'XLY': 2, 'XLI': 1, 'XLC': 1, 'XLF': 1, 'XLV': 0, 'XLP': -1, 'XLU': -1, 'XLRE': -1, 'XLB': 0, 'XLE': 0},
    'Slowdown':    {'XLP': 2, 'XLV': 2, 'XLU': 1, 'XLRE': 1, 'XLF': 0, 'XLC': -1, 'XLK': -1, 'XLY': -2, 'XLI': -1, 'XLB': -2, 'XLE': -2},
    'Reflation':   {'XLE': 2, 'XLB': 2, 'XLF': 1, 'XLI': 1, 'XLK': 0, 'XLC': 0, 'XLY': 0, 'XLP': -1, 'XLU': -2, 'XLRE': -1, 'XLV': 0},
    'Stagflation': {'XLP': 2, 'XLV': 1, 'XLE': 1, 'XLB': 1, 'XLU': 0, 'XLF': -1, 'XLK': -2, 'XLY': -2, 'XLI': -1, 'XLRE': -1, 'XLC': -1},
    'Crisis':      {'XLP': 2, 'XLV': 2, 'XLU': 2, 'XLRE': 0, 'XLF': -1, 'XLC': -2, 'XLK': -2, 'XLY': -2, 'XLI': -1, 'XLB': -2, 'XLE': -2},
}

# Sector name mapping
SECTOR_NAMES = {
    'XLK': 'Technology',
    'XLY': 'Consumer Discretionary',
    'XLP': 'Consumer Staples',
    'XLF': 'Financials',
    'XLV': 'Healthcare',
    'XLI': 'Industrials',
    'XLE': 'Energy',
    'XLB': 'Materials',
    'XLU': 'Utilities',
    'XLRE': 'Real Estate',
    'XLC': 'Communication Services',
}


def get_sector_recommendations_for_regime(regime: str) -> List[Dict]:
    """Generate sector recommendations based on regime."""
    scores = REGIME_SECTOR_SCORES.get(regime, REGIME_SECTOR_SCORES['Goldilocks'])
    recommendations = []

    for ticker, score in scores.items():
        if score >= 1:
            signal = "overweight"
            confidence = 0.7 + (score * 0.1)  # 0.8-0.9
        elif score <= -1:
            signal = "underweight"
            confidence = 0.7 + (abs(score) * 0.1)
        else:
            signal = "neutral"
            confidence = 0.5

        expected_return = score * 0.03  # +6% to -6% annual

        recommendations.append({
            "sector": SECTOR_NAMES.get(ticker, ticker),
            "ticker": ticker,
            "signal": signal,
            "confidence": round(min(confidence, 0.95), 2),
            "expected_return": round(expected_return, 3),
            "macro_drivers": ["regime"],
        })

    # Sort by score descending
    recommendations.sort(key=lambda x: x['expected_return'], reverse=True)
    return recommendations


# Shared engine instances
_sector_engine = SectorRotationEngine()
_factor_engine = FactorRotationEngine()
_valuation_engine = MacroValuationEngine()
_country_engine = CountryRankingEngine()


# Pydantic Models


class SectorRotationResponse(BaseModel):
    regime: str
    recommendations: List[Dict]
    momentum_leader: str
    momentum_laggard: str
    rotation_intensity: float
    timestamp: str
    # NEW: Calibration-enhanced fields
    conviction_multiplier: float = Field(default=1.0, description="Regime transition alpha boost multiplier")
    momentum_decay_adjustment: float = Field(default=0.0, description="Average momentum decay adjustment")
    transition_alpha_boost: float = Field(default=0.0, description="Alpha boost from regime transition")
    calibration_score: float = Field(default=0.0, description="Model calibration confidence score")


class FactorRotationResponse(BaseModel):
    regime: str
    factor_weights: Dict[str, float]
    recommendations: List[Dict]
    dispersion: float
    explanation: Dict
    timestamp: str


class EarningsRevisionResponse(BaseModel):
    total_revisions: int
    upgrade_ratio: float
    consensus: str
    top_upgrades: List[Dict]
    top_downgrades: List[Dict]
    timestamp: str


class MacroValuationResponse(BaseModel):
    market: str
    regime: str
    current_pe: float
    target_pe: float
    valuation_discount: float
    erp: float
    upside_potential: float
    valuation_percentile: float
    signal: str
    timestamp: str


class CountryRankingResponse(BaseModel):
    global_regime: str
    rankings: List[Dict]
    top_picks: List[Dict]
    regional_breakdown: Dict[str, Any]
    timestamp: str


class StockScreenerRequest(BaseModel):
    universe: List[Dict[str, Any]]
    regime: Optional[str] = Field(default=None)  # Changed from Goldilocks to dynamic
    min_market_cap: float = Field(default=1e9)


class StockScreenerResponse(BaseModel):
    regime: str
    total_universe: int
    passed_count: int
    pass_rate: float
    top_picks: List[Dict]
    timestamp: str


class EventCalendarResponse(BaseModel):
    event_risk_level: str
    high_impact_events_next_7d: int
    next_major_event: Optional[Dict]
    upcoming_events: List[Dict]
    recommendations: List[Dict]
    timestamp: str


class EquityDashboardResponse(BaseModel):
    current_regime: str  # FIX-2: Top-level regime field for frontend
    sector_rotation: Dict
    factor_rotation: Dict
    valuation: Dict
    country_ranking: Dict
    earnings_momentum: Dict
    event_risk: Dict
    timestamp: str


# Endpoints


@router.get("/sector-rotation", response_model=SectorRotationResponse)
async def get_sector_rotation(
    regime: Optional[str] = None,  # Changed from default to dynamic
):
    """Get regime-aware sector rotation recommendations."""
    try:
        # P0-FIX-2: Use dynamic regime if not provided
        if regime is None:
            regime = get_current_regime()
            logger.info(f"[EQUITY] Using dynamic regime for sector rotation: {regime}")

        # Get regime-specific sector recommendations
        sector_recs = get_sector_recommendations_for_regime(regime)

        # Determine leader/laggard from recommendations
        overweights = [r for r in sector_recs if r['signal'] == 'overweight']
        underweights = [r for r in sector_recs if r['signal'] == 'underweight']

        leader = overweights[0]['sector'] if overweights else 'None'
        laggard = underweights[-1]['sector'] if underweights else 'None'

        # Calculate rotation intensity based on regime dispersion
        scores = [r['expected_return'] for r in sector_recs]
        rotation_intensity = max(scores) - min(scores) if scores else 0.0

        return SectorRotationResponse(
            regime=regime,
            recommendations=sector_recs[:5],
            momentum_leader=leader,
            momentum_laggard=laggard,
            rotation_intensity=round(rotation_intensity, 3),
            timestamp=datetime.now().isoformat(),
            conviction_multiplier=1.0,  # Placeholder for calibration
            momentum_decay_adjustment=0.0,
            transition_alpha_boost=0.0,
            calibration_score=0.75,
        )
    except Exception as e:
        logger.error(f"Sector rotation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/factor-rotation", response_model=FactorRotationResponse)
async def get_factor_rotation(
    regime: Optional[str] = None,  # Changed from default to dynamic
):
    """Get macro-aware factor rotation recommendations."""
    try:
        # P0-FIX-2: Use dynamic regime if not provided
        if regime is None:
            regime = get_current_regime()
            logger.info(f"[EQUITY] Using dynamic regime for factor rotation: {regime}")

        # Get regime-specific factor weights
        weights = REGIME_FACTOR_WEIGHTS.get(regime, REGIME_FACTOR_WEIGHTS['Goldilocks'])

        # Factor returns (would come from data)
        factor_returns = {
            "value": 0.15,
            "momentum": 0.22,
            "quality": 0.18,
            "growth": 0.25,
            "low_vol": 0.05,
        }

        model = _factor_engine.calculate_rotation(
            regime=regime,
            factor_returns=factor_returns,
        )

        # Override with regime-specific weights
        model.factor_weights = weights

        # Generate regime-specific explanation
        thesis = REGIME_THESIS.get(regime, REGIME_THESIS['Goldilocks'])
        top_factors = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:2]
        bottom_factors = sorted(weights.items(), key=lambda x: x[1])[:2]

        explanation = {
            "regime": regime,
            "thesis": thesis,
            "overweights": [
                {"factor": f[0], "weight": f[1], "confidence": 0.75}
                for f in top_factors if f[1] > 0.15
            ],
            "underweights": [
                {"factor": f[0], "weight": f[1]}
                for f in bottom_factors if f[1] < 0.15
            ],
            "dispersion": model.dispersion,
            "timestamp": datetime.now().isoformat(),
        }

        # Build recommendations from weights
        recommendations = []
        for factor, weight in weights.items():
            if weight > 0.25:
                signal = "overweight"
            elif weight < 0.10:
                signal = "underweight"
            else:
                signal = "neutral"
            recommendations.append({
                "factor": factor,
                "signal": signal,
                "weight": weight,
                "confidence": 0.75,
                "momentum": factor_returns.get(factor, 0.0),
            })

        return FactorRotationResponse(
            regime=regime,
            factor_weights=weights,
            recommendations=recommendations,
            dispersion=model.dispersion,
            explanation=explanation,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Factor rotation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/earnings-revision", response_model=EarningsRevisionResponse)
async def get_earnings_revision(
    min_analysts: int = 5,
):
    """Get earnings revision analysis."""
    try:
        # Simulated earnings data
        estimates_data = pd.DataFrame([
            {"ticker": "AAPL", "eps_consensus": 6.50, "prior_eps": 6.20, "num_analysts": 35, "std_dev": 0.30},
            {"ticker": "MSFT", "eps_consensus": 12.20, "prior_eps": 11.80, "num_analysts": 40, "std_dev": 0.45},
            {"ticker": "GOOGL", "eps_consensus": 7.80, "prior_eps": 7.90, "num_analysts": 30, "std_dev": 0.25},
            {"ticker": "AMZN", "eps_consensus": 4.20, "prior_eps": 3.80, "num_analysts": 45, "std_dev": 0.50},
            {"ticker": "NVDA", "eps_consensus": 18.50, "prior_eps": 16.20, "num_analysts": 38, "std_dev": 1.20},
        ])

        analyzer = EarningsRevisionAnalyzer()
        model = analyzer.analyze_universe(estimates_data)

        top_upgrades = get_earnings_momentum_picks(model, n=5)

        return EarningsRevisionResponse(
            total_revisions=model.total_revisions,
            upgrade_ratio=model.upgrade_ratio,
            consensus=model.broad_consensus,
            top_upgrades=top_upgrades,
            top_downgrades=[],
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Earnings revision error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro-valuation", response_model=MacroValuationResponse)
async def get_macro_valuation(
    regime: Optional[str] = None,  # Changed from default to dynamic
    market: str = "US",
):
    """Get macro-aware valuation metrics."""
    try:
        # P0-FIX-2: Use dynamic regime if not provided
        if regime is None:
            regime = get_current_regime()
            logger.info(f"[EQUITY] Using dynamic regime for valuation: {regime}")

        # Simulated market data
        market_data = {
            "market": market,
            "current_pe": 21.5,
            "forward_pe": 19.8,
            "earnings_growth": 0.08,
            "risk_free_rate": 0.042,
            "ev_ebitda": 14.2,
            "pb_ratio": 3.8,
            "dividend_yield": 0.015,
            "fcf_yield": 0.045,
            "eps": 225.0,
        }

        model = _valuation_engine.calculate_valuation(
            market_data=market_data,
            regime=regime,
        )

        signal = get_valuation_signal(model)

        return MacroValuationResponse(
            market=market,
            regime=regime,
            current_pe=model.metrics.current_pe,
            target_pe=model.metrics.regime_target_pe,
            valuation_discount=model.metrics.valuation_discount,
            erp=model.metrics.erp,
            upside_potential=model.metrics.upside_potential,
            valuation_percentile=model.valuation_percentile,
            signal=signal["signal"],
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Macro valuation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/country-ranking", response_model=CountryRankingResponse)
async def get_country_ranking(
    global_regime: Optional[str] = None,  # Changed from default to dynamic
):
    """Get macro-driven country/market rankings."""
    try:
        # P0-FIX-2: Use dynamic regime if not provided
        if global_regime is None:
            global_regime = get_current_regime()
            logger.info(f"[EQUITY] Using dynamic regime for country ranking: {global_regime}")

        # Simulated country data
        macro_data = {
            "United States": {"gdp_growth": 2.5, "inflation": 2.8, "real_rate": 1.2, "fx_valuation": 5, "cb_stance": 0.2},
            "Europe": {"gdp_growth": 1.2, "inflation": 2.5, "real_rate": 0.5, "fx_valuation": -5, "cb_stance": -0.1},
            "Japan": {"gdp_growth": 0.8, "inflation": 2.2, "real_rate": 0.0, "fx_valuation": -10, "cb_stance": -0.3},
            "Emerging Markets": {"gdp_growth": 4.2, "inflation": 3.5, "real_rate": 2.5, "fx_valuation": 10, "cb_stance": 0.1},
            "China": {"gdp_growth": 4.8, "inflation": 1.5, "real_rate": 1.8, "fx_valuation": -15, "cb_stance": -0.2},
            "India": {"gdp_growth": 6.5, "inflation": 4.8, "real_rate": 2.0, "fx_valuation": 0, "cb_stance": 0.0},
            "Brazil": {"gdp_growth": 2.8, "inflation": 3.8, "real_rate": 4.5, "fx_valuation": 15, "cb_stance": 0.3},
            "UK": {"gdp_growth": 1.0, "inflation": 3.2, "real_rate": 0.8, "fx_valuation": -8, "cb_stance": -0.1},
            "Germany": {"gdp_growth": 0.5, "inflation": 2.8, "real_rate": 0.3, "fx_valuation": -3, "cb_stance": -0.2},
        }

        model = _country_engine.calculate_scores(
            macro_data=macro_data,
            global_regime=global_regime,
        )

        return CountryRankingResponse(
            global_regime=global_regime,
            rankings=[
                {
                    "country": r.country,
                    "ticker": r.ticker,
                    "rank": r.rank,
                    "score": r.composite_score,
                    "signal": r.signal,
                }
                for r in model.rankings[:10]
            ],
            top_picks=[
                {"country": p.country, "ticker": p.ticker, "score": p.composite_score}
                for p in model.top_picks[:5]
            ],
            regional_breakdown=model.regional_breakdown,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Country ranking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stock-screener", response_model=StockScreenerResponse)
async def run_stock_screener(request: StockScreenerRequest):
    """Run macro-aware stock screener on universe."""
    try:
        # P0-FIX-2: Use dynamic regime if not provided
        regime = request.regime
        if regime is None:
            regime = get_current_regime()
            logger.info(f"[EQUITY] Using dynamic regime for stock screener: {regime}")

        universe_df = pd.DataFrame(request.universe)

        if universe_df.empty:
            # Return demo result
            return StockScreenerResponse(
                regime=regime,
                total_universe=0,
                passed_count=0,
                pass_rate=0.0,
                top_picks=[],
                timestamp=datetime.now().isoformat(),
            )

        # Regime-specific sector scores
        sector_scores = {
            "Goldilocks":  {"Technology": 0.9, "Healthcare": 0.6, "Financials": 0.5, "Energy": 0.3, "Consumer Staples": 0.3},
            "Slowdown":    {"Technology": 0.3, "Healthcare": 0.8, "Financials": 0.3, "Energy": 0.1, "Consumer Staples": 0.9},
            "Reflation":   {"Technology": 0.6, "Healthcare": 0.4, "Financials": 0.8, "Energy": 0.9, "Consumer Staples": 0.3},
            "Stagflation": {"Technology": 0.2, "Healthcare": 0.7, "Financials": 0.3, "Energy": 0.6, "Consumer Staples": 0.8},
        }
        scores = sector_scores.get(regime, sector_scores["Goldilocks"])

        screener = create_default_screener(scores)
        result = screener.screen(
            universe=universe_df,
            regime=regime,
            min_market_cap=request.min_market_cap,
        )

        summary = get_screening_summary(result)

        return StockScreenerResponse(
            regime=regime,
            total_universe=result.total_universe,
            passed_count=result.passed_count,
            pass_rate=result.pass_rate,
            top_picks=summary["top_picks"],
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Stock screener error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/event-calendar", response_model=EventCalendarResponse)
async def get_event_calendar(
    days_ahead: int = 30,
):
    """Get macro event calendar with positioning recommendations."""
    try:
        calendar = create_default_calendar()
        model = calendar.get_calendar(days_ahead=days_ahead)

        risk_summary = get_event_risk_summary(model)

        return EventCalendarResponse(
            event_risk_level=risk_summary["event_risk_level"],
            high_impact_events_next_7d=risk_summary["high_impact_events_next_7d"],
            next_major_event=risk_summary["next_major_event"],
            upcoming_events=[
                {
                    "name": e.name,
                    "date": e.date.isoformat(),
                    "importance": e.importance,
                    "days_away": e.days_to_event,
                    "impact": e.market_impact,
                }
                for e in model.next_7_days
            ],
            recommendations=model.positioning_recommendations,
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Event calendar error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard", response_model=EquityDashboardResponse)
async def get_equity_dashboard(
    regime: Optional[str] = None,  # Changed from default to dynamic
):
    """Get complete equity research dashboard."""
    try:
        # P0-FIX-2: Use dynamic regime if not provided
        if regime is None:
            regime = get_current_regime()
            logger.info(f"[EQUITY] Using dynamic regime for dashboard: {regime}")

        # Aggregate all equity signals
        sector_rec = await get_sector_rotation(regime)
        factor_rec = await get_factor_rotation(regime)
        valuation = await get_macro_valuation(regime)
        countries = await get_country_ranking(regime)
        earnings = await get_earnings_revision()
        events = await get_event_calendar()

        # FIX-1: Include regime in each section for frontend display
        # FIX-2: Ensure regime is never None
        if regime is None:
            regime = "Slowdown"

        return EquityDashboardResponse(
            current_regime=regime,  # FIX-2: Top-level regime
            sector_rotation={
                "regime": regime,
                "recommendations": sector_rec.recommendations[:3],
                "leader": sector_rec.momentum_leader,
                "laggard": sector_rec.momentum_laggard,
            },
            factor_rotation={
                "regime": regime,
                "weights": factor_rec.factor_weights,
                "thesis": factor_rec.explanation.get("thesis", ""),
            },
            valuation={
                "regime": regime,
                "pe": valuation.current_pe,
                "target_pe": valuation.target_pe,
                "upside": valuation.upside_potential,
                "signal": valuation.signal,
            },
            country_ranking={
                "top_picks": countries.top_picks[:3],
            },
            earnings_momentum={
                "consensus": earnings.consensus,
                "upgrade_ratio": earnings.upgrade_ratio,
                "top": earnings.top_upgrades[:3],
            },
            event_risk={
                "risk_level": events.event_risk_level,
                "next_major": events.next_major_event,
            },
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        logger.error(f"Equity dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

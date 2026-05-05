"""
Performance API Router — Expose signal performance metrics
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

from .signal_tracker import SignalPerformanceTracker, get_tracker, SIGNAL_MODULES

router = APIRouter(prefix="/performance", tags=["performance"])


class SignalMetricsResponse(BaseModel):
    """Signal performance metrics response."""
    module: str
    window: str
    timestamp: Optional[str] = None
    directional_accuracy: Optional[float] = None
    ic_1d: Optional[float] = None
    ic_5d: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    total_signals: int = 0
    correct_signals: Optional[int] = None
    avg_confidence: Optional[float] = None
    calibration_error: Optional[float] = None
    status: str
    message: Optional[str] = None
    data_source: Optional[str] = None  # "live" | "backtest" | "none"
    warmup_note: Optional[str] = None  # Explanation for WARMING_UP/PARTIAL status


class HealthSummaryResponse(BaseModel):
    """Overall signal health summary."""
    status: str
    modules_tracked: int
    healthy_count: int
    degraded_count: int
    unhealthy_count: int
    timestamp: Optional[str] = None
    module_details: Optional[List[Dict]] = None


class PredictionRequest(BaseModel):
    """Request to record a prediction."""
    module: str
    signal_value: float
    confidence: float
    direction: str


class MarketOutcomeRequest(BaseModel):
    """Request to record market outcome."""
    spy_return_1d: float
    spy_return_5d: float
    spy_direction_1d: int
    realized_vol: float
    vix: float


def _convert_numpy(obj):
    """Convert numpy types to Python native types."""
    import numpy as np
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_, np.bool)):
        return bool(obj)
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _convert_numpy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_numpy(item) for item in obj]
    return obj


@router.get("/signals", response_model=List[SignalMetricsResponse])
async def get_signal_performance(
    module: Optional[str] = None,
    window: str = "1m"
):
    """
    Get signal performance metrics for all modules or specific module.

    Args:
        module: Filter by specific module (optional)
        window: Rolling window ("1d", "1w", "1m", "3m", "6m", "1y")

    Returns:
        List of performance metrics per module
    """
    tracker = get_tracker()

    if module:
        metrics = tracker.calculate_metrics(module, window)
        if metrics.get("status") == "error":
            raise HTTPException(status_code=500, detail=metrics.get("error"))
        return [_convert_numpy(metrics)]
    else:
        all_metrics = []
        for mod in SIGNAL_MODULES:
            metrics = tracker.calculate_metrics(mod, window)
            if metrics.get("status") not in ["error"]:
                all_metrics.append(_convert_numpy(metrics))
        return all_metrics


@router.get("/signals/health", response_model=HealthSummaryResponse)
async def get_signal_health():
    """
    Get overall signal health summary.

    Returns:
        Health summary with module counts by status
    """
    tracker = get_tracker()
    summary = tracker.get_health_summary()
    return _convert_numpy(summary)


@router.post("/signals/record")
async def record_prediction(prediction: PredictionRequest):
    """
    Record a new signal prediction.

    Args:
        prediction: Prediction data including module, signal value, confidence

    Returns:
        Confirmation of recorded prediction
    """
    tracker = get_tracker()
    tracker.record_prediction(
        module=prediction.module,
        signal_value=prediction.signal_value,
        confidence=prediction.confidence,
        direction=prediction.direction
    )
    return {
        "success": True,
        "message": f"Prediction recorded for {prediction.module}",
        "timestamp": datetime.now().isoformat()
    }


@router.post("/signals/outcome")
async def record_market_outcome(outcome: MarketOutcomeRequest):
    """
    Record market outcome for signal validation.

    Args:
        outcome: Market outcome data including SPY returns

    Returns:
        Confirmation of recorded outcome
    """
    tracker = get_tracker()
    tracker.record_market_outcome(
        spy_return_1d=outcome.spy_return_1d,
        spy_return_5d=outcome.spy_return_5d,
        spy_direction_1d=outcome.spy_direction_1d,
        realized_vol=outcome.realized_vol,
        vix=outcome.vix
    )
    return {
        "success": True,
        "message": "Market outcome recorded",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/signals/history/{module}")
async def get_signal_history(
    module: str,
    window: str = "1m",
    limit: int = 100
):
    """
    Get historical performance metrics for a module.

    Args:
        module: Signal module name
        window: Rolling window
        limit: Maximum records to return

    Returns:
        List of historical metrics
    """
    tracker = get_tracker()
    try:
        with sqlite3.connect(tracker.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM signal_performance
                WHERE module = ? AND window = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (module, window, limit)).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {e}")


@router.post("/signals/calculate/{module}")
async def calculate_module_metrics(module: str, window: str = "1m"):
    """
    Trigger manual calculation of metrics for a module.

    Args:
        module: Signal module name
        window: Rolling window

    Returns:
        Calculated metrics
    """
    tracker = get_tracker()
    metrics = tracker.calculate_metrics(module, window)

    if metrics.get("status") == "error":
        raise HTTPException(status_code=500, detail=metrics.get("error"))

    # Save to database
    tracker.save_metrics(metrics)

    return _convert_numpy(metrics)


@router.get("/signals/modules")
async def get_tracked_modules():
    """
    Get list of all tracked signal modules.

    Returns:
        List of module names and their descriptions
    """
    return [
        {"id": "hmm_regime", "name": "HMM Regime Detector", "description": "Hidden Markov Model regime classification"},
        {"id": "kalman_filter", "name": "Kalman Filter", "description": "Noise-reduced macro indicator smoothing"},
        {"id": "bayesian_aggregator", "name": "Bayesian Aggregator", "description": "Multi-signal Bayesian fusion"},
        {"id": "news_sentiment", "name": "News Sentiment", "description": "NLP-based sentiment analysis"},
        {"id": "multifactor_alpha", "name": "Multi-Factor Alpha", "description": "Equity alpha scoring model"},
        {"id": "sector_rotation", "name": "Sector Rotation", "description": "Sector allocation optimizer"},
    ]

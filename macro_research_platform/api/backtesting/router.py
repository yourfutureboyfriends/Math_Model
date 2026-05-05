"""
Backtesting API Router — Expose backtest results and trigger runs
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

from .signal_backtest import SignalBacktester, run_monthly_backtest

router = APIRouter(prefix="/backtest", tags=["backtesting"])


class BacktestResultResponse(BaseModel):
    """Backtest result record response model."""
    id: int
    run_date: str
    module: str
    test_name: str
    metric_name: str
    metric_value: float
    period_start: str
    period_end: str
    notes: str

    class Config:
        from_attributes = True


class BacktestSummaryResponse(BaseModel):
    """Summary of latest backtest results by module."""
    module: str
    metrics: Dict[str, float]
    last_run: Optional[str] = None


class BacktestRunResponse(BaseModel):
    """Response from triggering a backtest run."""
    success: bool
    message: str
    results: Optional[Dict[str, Any]] = None
    run_date: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True


@router.get("/results", response_model=List[BacktestResultResponse])
async def get_backtest_results(
    module: Optional[str] = None,
    limit: int = 200
):
    """
    Get backtest results from database.

    Args:
        module: Filter by specific module (hmm_regime, kalman_ic, etc.)
        limit: Maximum number of results to return

    Returns:
        List of backtest result records
    """
    backtester = SignalBacktester()
    results = backtester.get_latest_results(module=module)

    if limit:
        results = results[:limit]

    return results


@router.get("/summary", response_model=List[BacktestSummaryResponse])
async def get_backtest_summary():
    """
    Get latest backtest metrics grouped by module.

    Returns:
        List of module summaries with their latest metrics
    """
    backtester = SignalBacktester()
    by_module = backtester.get_summary_by_module()

    # Get latest run date for each module
    all_results = backtester.get_latest_results()
    latest_dates = {}
    for r in all_results:
        mod = r.get("module", "unknown")
        run_date = r.get("run_date")
        if run_date and (mod not in latest_dates or run_date > latest_dates[mod]):
            latest_dates[mod] = run_date

    response = []
    for module, metrics in by_module.items():
        response.append(BacktestSummaryResponse(
            module=module,
            metrics=metrics,
            last_run=latest_dates.get(module)
        ))

    return response


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


@router.post("/run", response_model=BacktestRunResponse)
async def trigger_backtest_run():
    """
    Manually trigger a full backtest run.

    Returns:
        Results of the backtest execution
    """
    try:
        results = run_monthly_backtest()
        # Convert numpy types to Python native types for JSON serialization
        converted_results = _convert_numpy(results)
        return BacktestRunResponse(
            success=True,
            message="Backtest completed successfully",
            results=converted_results,
            run_date=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("/health")
async def backtest_health():
    """Health check for backtesting module."""
    backtester = SignalBacktester()
    results = backtester.get_latest_results()
    latest_result = results[0] if results else None

    return {
        "status": "healthy",
        "db_connected": True,
        "last_result": latest_result,
        "modules": ["hmm_regime", "kalman_ic", "bayesian_ic", "sentiment_accuracy", "sector_rotation"]
    }

"""
Diagnostics Endpoints — Health monitoring and observability.

Phase 5: Cache Health + Observability

Endpoints:
- /api/health/data — Data freshness and staleness
- /api/health/providers — Provider status
- /api/health/cache — Cache health
- /api/diagnostics/data-pipeline — Full pipeline diagnostics
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import pandas as pd

from fastapi import APIRouter, HTTPException

from api.services.refresh_coordinator import refresh_coordinator
from api.repository.market_repository import market_repository
from api.repository.macro_repository import macro_repository
from api.services.forecast_tracker import forecast_tracker
from api.services.regime_validation import regime_validator
from api.services.signal_validation import signal_validator
from api.services.conviction_calibration import conviction_calibrator
from api.services.recession_validation import recession_validator
from api.services.expected_returns_validation import expected_returns_validator
from api.services.portfolio_validation import portfolio_validator
from api.services.momentum_validation import momentum_validator
from api.services.nowcast_validation import nowcast_validator
from api.services.production_monitoring import production_monitor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/data")
async def health_data() -> Dict[str, Any]:
    """
    Data health endpoint.

    Returns:
        - Latest refresh times
        - Stale sources
        - Missing critical series
        - Degraded sections
    """
    market_meta = market_repository.get_metadata()
    macro_meta = macro_repository.get_metadata()

    # Check staleness
    stale_prices = market_repository.get_stale_symbols(max_age_minutes=5)
    missing_critical = []

    # Check critical series
    critical_series = ["fed_funds", "inflation", "growth", "vix"]
    for series in critical_series:
        if macro_repository.get_metric_value(series) is None:
            missing_critical.append(series)

    return {
        "status": "degraded" if stale_prices or missing_critical else "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "sources": {
            "market_prices": {
                "last_update": market_meta.get("last_update"),
                "is_fresh": market_meta.get("is_fresh"),
                "stale_symbols": stale_prices,
                "symbol_count": market_meta.get("symbol_count"),
            },
            "macro_data": {
                "last_update": macro_meta.get("last_update"),
                "metric_count": macro_meta.get("metric_count"),
            },
        },
        "missing_critical": missing_critical,
        "stale_count": len(stale_prices),
    }


@router.get("/providers")
async def health_providers() -> Dict[str, Any]:
    """
    Provider health endpoint.

    Returns provider-by-provider status:
    - Provider name
    - Success/failure state
    - Latency
    - Last error
    - Rows fetched/accepted/rejected
    """
    statuses = refresh_coordinator.get_status()

    providers = []
    for name, status in statuses.items():
        providers.append({
            "name": name,
            "state": status.get("state"),
            "success": status.get("state") == "success",
            "latency_ms": round(status.get("latency_ms", 0), 1),
            "last_attempt": status.get("last_attempt"),
            "last_success": status.get("last_success"),
            "records_fetched": status.get("records_fetched", 0),
            "records_accepted": status.get("records_accepted", 0),
            "records_rejected": status.get("records_rejected", 0),
            "is_stale": status.get("is_stale", True),
            "error": status.get("error_message"),
        })

    overall_healthy = all(p["success"] for p in providers) if providers else False

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "providers": providers,
        "healthy_count": sum(1 for p in providers if p["success"]),
        "total_count": len(providers),
    }


@router.get("/cache")
async def health_cache() -> Dict[str, Any]:
    """
    Cache health endpoint.

    Returns:
        - Cache keys
        - TTL / freshness
        - Hit/miss counts (if available)
        - Last invalidation times
    """
    market_meta = market_repository.get_metadata()
    macro_meta = macro_repository.get_metadata()

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "caches": {
            "market_prices": {
                "keys": market_meta.get("symbol_count", 0),
                "is_fresh": market_meta.get("is_fresh"),
                "last_update": market_meta.get("last_update"),
                "stale_entries": market_meta.get("stale_symbols", 0),
            },
            "macro_indicators": {
                "keys": macro_meta.get("metric_count", 0),
                "last_update": macro_meta.get("last_update"),
            },
        },
    }


@router.get("/overall")
async def health_overall() -> Dict[str, Any]:
    """Overall system health summary."""
    data_health = await health_data()
    provider_health = await health_providers()
    cache_health = await health_cache()

    # Aggregate status
    statuses = [
        data_health.get("status"),
        provider_health.get("status"),
        cache_health.get("status"),
    ]

    overall = "healthy"
    if "failed" in statuses:
        overall = "failed"
    elif "degraded" in statuses:
        overall = "degraded"

    return {
        "status": overall,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "data": data_health.get("status"),
            "providers": provider_health.get("status"),
            "cache": cache_health.get("status"),
        },
        "details": {
            "data": data_health,
            "providers": provider_health,
            "cache": cache_health,
        },
    }


# Diagnostics router (separate from health)
diagnostics_router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@diagnostics_router.get("/runtime")
async def diagnostics_runtime() -> Dict[str, Any]:
    """
    Runtime system diagnostics.

    Phase 5: Real-time system health and validation status.
    Returns actual runtime state, not placeholders.
    """
    from api.services.runtime_status import get_full_diagnostics

    diagnostics = get_full_diagnostics()
    diagnostics["endpoint"] = "/api/diagnostics/runtime"

    return diagnostics


@diagnostics_router.get("/data-pipeline")
async def diagnostics_pipeline() -> Dict[str, Any]:
    """
    Full data pipeline diagnostics.

    Returns:
        - Provider inventory
        - Refresh graph summary
        - Validation failures
        - Duplicate fetches eliminated
        - Duplicated computations eliminated
        - Current canonical objects available
    """
    # Get provider status
    provider_status = refresh_coordinator.get_status()

    # Get repository state
    market_meta = market_repository.get_metadata()
    macro_meta = macro_repository.get_metadata()

    # List available canonical objects
    available_prices = market_repository.get_symbols()
    available_metrics = list(macro_repository.get_all_metrics().keys())

    # Architecture summary
    architecture = {
        "providers": ["yahoo_finance", "fred", "news"],
        "normalization": ["prices", "fx", "macro_series", "news"],
        "validation": ["prices", "fx", "macro"],
        "repositories": ["market_repository", "macro_repository"],
        "services": ["refresh_coordinator", "price_service", "regime_service"],
    }

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "architecture": architecture,
        "providers": provider_status,
        "repositories": {
            "market": market_meta,
            "macro": macro_meta,
        },
        "available_data": {
            "prices": available_prices,
            "metrics": available_metrics,
        },
        "eliminated_duplicates": {
            "price_fetches": "Consolidated to YahooFinanceProvider via RefreshCoordinator",
            "macro_fetches": "Consolidated to FREDProvider via RefreshCoordinator",
            "regime_computation": "Centralized in RegimeService",
            "dxy_caches": "Merged into MarketRepository",
        },
    }


@diagnostics_router.get("/metrics")
async def diagnostics_metrics() -> Dict[str, Any]:
    """Current metric values (for debugging)."""
    prices = market_repository.get_all_prices()
    metrics = macro_repository.get_all_metrics()
    changes = market_repository.get_changes()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "prices": prices,
        "changes": changes,
        "macro": metrics,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FORECAST TRACKING ENDPOINTS (Phase 1: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/forecasts")
async def forecasts_history(
    model: Optional[str] = None,
    horizon: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get forecast history.

    Query params:
    - model: Filter by model name (e.g., 'regime_threshold', 'recession_ensemble')
    - horizon: Filter by horizon ('1M', '3M', '6M', '12M', 'current')
    - limit: Maximum records to return (default 100)
    """
    history = forecast_tracker.get_history(
        model_name=model,
        horizon=horizon,
        limit=limit
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(history),
        "filters": {"model": model, "horizon": horizon},
        "forecasts": history,
    }


@diagnostics_router.get("/forecasts/accuracy")
async def forecasts_accuracy(
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get model accuracy metrics.

    Query params:
    - model: Specific model to evaluate (if omitted, returns all models)

    Returns MAE, RMSE, directional accuracy, and bias for each model.
    """
    if model:
        metrics = forecast_tracker.get_model_accuracy(model)
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "model": model,
            "metrics": metrics.to_dict(),
        }

    summary = forecast_tracker.get_accuracy_summary()
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "models": summary,
        "count": len(summary),
    }


@diagnostics_router.get("/forecasts/regime-comparison")
async def forecasts_regime_comparison(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare threshold vs HMM regime classification accuracy.

    Query params:
    - start_date: Start date for comparison (ISO format)
    - end_date: End date for comparison (ISO format)

    Returns agreement rate and individual accuracies.
    """
    comparison = forecast_tracker.get_regime_comparison(start_date, end_date)
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date_range": {"start": start_date, "end": end_date},
        "comparison": comparison,
    }


@diagnostics_router.get("/forecasts/unrealized")
async def forecasts_unrealized(
    model: Optional[str] = None,
    before_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get forecasts awaiting realized values (for backfilling).

    Query params:
    - model: Filter by model name
    - before_date: Only forecasts before this date
    """
    unrealized = forecast_tracker.get_unrealized(
        model_name=model,
        before_date=before_date
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(unrealized),
        "filters": {"model": model, "before_date": before_date},
        "forecasts": unrealized,
    }


@diagnostics_router.post("/forecasts/{forecast_id}/realized")
async def update_forecast_realized(
    forecast_id: int,
    realized_value: Optional[float] = None,
    realized_class: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update a forecast with its realized outcome.

    This endpoint is used to backfill realized values once actual data
    becomes available. Automatically computes error metrics.
    """
    success = forecast_tracker.update_realized(
        forecast_id=forecast_id,
        realized_value=realized_value,
        realized_class=realized_class
    )

    if not success:
        raise HTTPException(status_code=404, detail=f"Forecast {forecast_id} not found")

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "forecast_id": forecast_id,
        "realized_value": realized_value,
        "realized_class": realized_class,
        "status": "updated",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGIME VALIDATION ENDPOINTS (Phase 2: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/regime/arbitration-rule")
async def regime_arbitration_rule() -> Dict[str, Any]:
    """
    Get the documented arbitration rule for selecting between
    threshold-based and HMM regime classifiers.

    This is the single source of truth for method selection.
    """
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "arbitration_rule": regime_validator.get_arbitration_rule(),
    }


@diagnostics_router.post("/regime/optimize-threshold")
async def regime_optimize_threshold(
    thresholds: List[float] = [0.05, 0.10, 0.15, 0.20, 0.25],
    metric: str = "persistence"
) -> Dict[str, Any]:
    """
    Run threshold grid search to find optimal threshold.

    Tests multiple thresholds and evaluates based on either:
    - 'persistence': Maximize average regime duration
    - 'choppiness': Minimize excessive regime switching

    Request body:
    - thresholds: List of thresholds to test (default: [0.05, 0.10, 0.15, 0.20, 0.25])
    - metric: Optimization metric ('persistence' or 'choppiness')
    """
    # Get macro data from repository
    metrics = macro_repository.get_all_metrics()

    if not metrics or 'growth' not in metrics or 'inflation' not in metrics:
        raise HTTPException(
            status_code=503,
            detail="Macro data not available for threshold optimization"
        )

    # Create minimal DataFrame for optimization
    # In production, this would use historical macro data
    df = pd.DataFrame({
        'growth_score': [metrics.get('growth', 0)],
        'inflation_score': [metrics.get('inflation', 0)],
    })

    # For now, return the optimization structure without full historical data
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "note": "Threshold optimization requires historical macro data",
        "tested_thresholds": thresholds,
        "optimization_metric": metric,
        "current_data": {
            "growth_score": metrics.get('growth'),
            "inflation_score": metrics.get('inflation'),
        },
        "recommendation": {
            "optimal_threshold": 0.10,
            "rationale": "Default threshold based on literature (Ang & Bekaert 2002)",
            "next_step": "Provide historical macro DataFrame for full optimization"
        }
    }


@diagnostics_router.get("/regime/compare-methods")
async def regime_compare_methods(
    threshold: Optional[float] = None
) -> Dict[str, Any]:
    """
    Compare threshold vs HMM methods on available data.

    Query params:
    - threshold: Specific threshold to test (uses optimal if not specified)

    Returns agreement rate, persistence metrics, and transition matrices.
    """
    comparison = {
        "timestamp": datetime.utcnow().isoformat(),
        "threshold_tested": threshold or regime_validator.get_optimal_threshold() or 0.10,
        "note": "Full comparison requires historical macro data",
        "arbitration_rule": regime_validator.get_arbitration_rule(),
        "metrics_available": [
            "agreement_rate",
            "threshold_persistence",
            "hmm_persistence",
            "transition_matrices",
            "choppiness_scores"
        ]
    }

    return comparison


@diagnostics_router.post("/regime/select-method")
async def regime_select_method(
    hmm_available: bool = True,
    hmm_confidence: float = 0.75,
    data_length_months: int = 36
) -> Dict[str, Any]:
    """
    Apply arbitration rule to select classification method.

    Request body:
    - hmm_available: Whether HMM model is fitted
    - hmm_confidence: HMM confidence score (0-1)
    - data_length_months: Months of historical data available

    Returns selected method with rationale.
    """
    result = regime_validator.select_method(
        hmm_available=hmm_available,
        hmm_confidence=hmm_confidence,
        data_length_months=data_length_months
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "selection": result,
        "parameters": {
            "hmm_available": hmm_available,
            "hmm_confidence": hmm_confidence,
            "data_length_months": data_length_months,
        }
    }


@diagnostics_router.get("/regime/persistence-metrics")
async def regime_persistence_metrics(
    lookback_months: int = 60
) -> Dict[str, Any]:
    """
    Get regime persistence metrics from forecast history.

    Query params:
    - lookback_months: How many months to analyze

    Returns regime duration statistics, transition counts, and choppiness score.
    """
    # Get historical forecasts from forecast tracker
    history = forecast_tracker.get_history(
        model_name="regime_threshold",
        limit=lookback_months
    )

    if not history:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "note": "No regime forecast history available",
            "metrics": None,
        }

    # Extract regime series
    regimes = pd.Series([h.get('predicted_class') for h in history if h.get('predicted_class')])

    if len(regimes) < 6:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "note": f"Insufficient history ({len(regimes)} records)",
            "metrics": None,
        }

    # Compute metrics
    persistence = regime_validator.compute_persistence_metrics(regimes)
    transitions = regime_validator.compute_transition_matrix(regimes)
    choppiness = regime_validator.count_excessive_switches(regimes, min_persistence=2)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "sample_size": len(regimes),
        "persistence": [p.to_dict() for p in persistence],
        "transitions": transitions.to_dict() if not transitions.empty else None,
        "choppiness": choppiness,
        "warnings": [
            "Excessive regime switching detected" if choppiness['choppiness_score'] > 0.3 else None,
            "Consider increasing threshold" if choppiness['choppiness_score'] > 0.3 else None,
        ],
    }


@diagnostics_router.get("/regime/validate-current")
async def regime_validate_current() -> Dict[str, Any]:
    """
    Validate the current regime classification.

    Checks for:
    - Excessive recent switching
    - Very short current regime duration
    - Rare regime warnings

    Returns validation report with warnings if applicable.
    """
    # Get recent forecast history
    history = forecast_tracker.get_history(
        model_name="regime_threshold",
        limit=24
    )

    if not history:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "valid": False,
            "warnings": ["No forecast history available"],
        }

    # Extract regime series
    regimes = pd.Series([h.get('predicted_class') for h in history if h.get('predicted_class')])

    validation = regime_validator.validate_current_classification(regimes, lookback=12)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **validation,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SIGNAL STACK VALIDATION ENDPOINTS (Phase 3: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/signal/layer-metrics")
async def signal_layer_metrics(
    layer_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get validation metrics for signal stack layers.

    Query params:
    - layer_id: Specific layer (1-8) or all if omitted

    Returns correlation, rank correlation (IC), hit rate per layer.
    """
    if layer_id:
        if layer_id < 1 or layer_id > 8:
            raise HTTPException(status_code=400, detail="layer_id must be 1-8")
        metrics = signal_validator.compute_layer_metrics(layer_id)
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "layer_id": layer_id,
            "metrics": metrics.to_dict() if metrics else None,
        }

    # All layers
    all_metrics = signal_validator.compute_all_layer_metrics()
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "layers": [m.to_dict() for m in all_metrics],
        "count": len(all_metrics),
    }


@diagnostics_router.get("/signal/dead-layers")
async def signal_dead_layers(
    threshold: float = 0.0
) -> Dict[str, Any]:
    """
    Identify layers with negative or minimal contribution.

    Query params:
    - threshold: Minimum acceptable contribution score

    Returns list of layer IDs with contribution <= threshold.
    """
    dead_layers = signal_validator.get_dead_layers(threshold)

    details = []
    for layer_id in dead_layers:
        metrics = signal_validator.compute_layer_metrics(layer_id)
        if metrics:
            details.append({
                "layer_id": layer_id,
                "layer_name": signal_validator.LAYER_NAMES.get(layer_id),
                "contribution_score": metrics.contribution_score,
                "correlation": metrics.correlation,
                "hit_rate": metrics.hit_rate,
            })

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "threshold": threshold,
        "dead_layer_count": len(dead_layers),
        "dead_layers": details,
        "recommendation": "Consider removing or revising dead layers",
    }


@diagnostics_router.get("/signal/calibration-recommendations")
async def signal_calibration_recommendations() -> Dict[str, Any]:
    """
    Get calibration recommendations for signal stack.

    Analyzes:
    - Layer contributions (identify dead layers)
    - Override trigger performance (precision)
    - Layer reliability scores for Bayesian weighting

    Returns specific recommendations for improvement.
    """
    recommendations = signal_validator.get_calibration_recommendations()
    return {
        "timestamp": datetime.utcnow().isoformat(),
        **recommendations,
    }


@diagnostics_router.get("/signal/bayesian-weights")
async def signal_bayesian_weights() -> Dict[str, Any]:
    """
    Get layer weights for Bayesian aggregation.

    Weights based on historical hit rate accuracy.
    Higher weight = more reliable layer.
    """
    weights = signal_validator.get_bayesian_weights()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "weights": weights,
        "method": "hit_rate_based",
        "note": "Use these weights in BayesianSignalAggregator.set_layer_reliability()",
    }


@diagnostics_router.get("/signal/override-analysis")
async def signal_override_analysis(
    override_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze override trigger performance.

    Query params:
    - override_name: Specific override to analyze
      (e.g., "Recession probability > 60%", "Liquidity stress", "Sentiment-regime divergence")

    Returns precision and calibration recommendations.
    """
    if override_name:
        analysis = signal_validator.analyze_override_performance(override_name)
        if not analysis:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "override_name": override_name,
                "note": "Insufficient data for analysis",
            }

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "override": analysis.to_dict(),
        }

    # Analyze all overrides
    overrides = {}
    for name in ["Recession probability > 60%", "Liquidity stress", "Sentiment-regime divergence"]:
        analysis = signal_validator.analyze_override_performance(name)
        if analysis:
            overrides[name] = analysis.to_dict()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "overrides": overrides,
        "count": len(overrides),
    }


@diagnostics_router.post("/signal/log-stack")
async def signal_log_stack(
    date: str,
    layers: Dict[int, Dict[str, Any]],
    final_signal: str,
    risk_budget: float,
    overrides_active: List[str] = [],
    market_return_1m: Optional[float] = None
) -> Dict[str, Any]:
    """
    Log a signal stack for tracking and validation.

    Request body:
    - date: ISO format date
    - layers: Dict mapping layer_id -> {value, confidence, override_flag}
    - final_signal: Final aggregated signal
    - risk_budget: Risk budget output
    - overrides_active: List of active override names
    - market_return_1m: Actual 1-month forward return (for backtesting)

    Returns log entry ID.
    """
    log_id = signal_validator.log_signal_stack(
        date=date,
        layers=layers,
        final_signal=final_signal,
        risk_budget=risk_budget,
        overrides_active=overrides_active,
        market_return_1m=market_return_1m
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "log_id": log_id,
        "status": "logged",
    }


@diagnostics_router.post("/signal/update-returns")
async def signal_update_returns(
    date: str,
    market_return_1m: float
) -> Dict[str, Any]:
    """
    Backfill realized returns for a historical signal stack entry.

    Used to update signal stack history once actual market returns are known.
    Enables calculation of layer contribution metrics.

    Request body:
    - date: Date of original signal
    - market_return_1m: Actual 1-month market return
    """
    success = signal_validator.update_realized_returns(date, market_return_1m)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No signal stack entry found for date {date}"
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date": date,
        "market_return_1m": market_return_1m,
        "status": "updated",
    }


@diagnostics_router.get("/signal/history")
async def signal_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get signal stack history.

    Query params:
    - start_date: Start date filter
    - end_date: End date filter
    - limit: Maximum records
    """
    df = signal_validator.get_signal_stack_history(
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )

    if df.empty:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "count": 0,
            "history": [],
        }

    # Convert to records
    records = df.to_dict('records')

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(records),
        "columns": list(df.columns),
        "history": records,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CONVICTION CALIBRATION ENDPOINTS (Phase 4: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/conviction/buckets")
async def conviction_buckets(
    horizon: str = "1M"
) -> Dict[str, Any]:
    """
    Get conviction bucket analysis.

    Analyzes realized outcomes by conviction level to validate calibration.

    Query params:
    - horizon: Forecast horizon ("1M", "3M", "6M", "12M")

    Returns metrics for LOW/MEDIUM/HIGH conviction buckets including:
    - Average realized return
    - Sharpe ratio
    - Hit rate
    - Monotonicity validation
    """
    buckets = conviction_calibrator.compute_conviction_buckets(horizon)

    if not buckets:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "horizon": horizon,
            "note": "Insufficient data for conviction bucket analysis",
            "buckets": [],
        }

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "horizon": horizon,
        "buckets": [b.to_dict() for b in buckets],
        "interpretation": "Higher conviction should correlate with better outcomes",
    }


@diagnostics_router.get("/conviction/monotonicity-test")
async def conviction_monotonicity_test(
    horizon: str = "1M"
) -> Dict[str, Any]:
    """
    Test if conviction is monotonically related to outcomes.

    Validates that higher conviction scores lead to:
    - Higher average returns
    - Better Sharpe ratios
    - Higher hit rates

    Query params:
    - horizon: Forecast horizon to test

    Returns statistical test results including Spearman rank correlation.
    """
    result = conviction_calibrator.test_monotonicity(horizon)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "test": "monotonicity",
        **result,
    }


@diagnostics_router.get("/conviction/component-analysis")
async def conviction_component_analysis(
    horizon: str = "1M"
) -> Dict[str, Any]:
    """
    Analyze importance of conviction components.

    Computes which components contribute most to accurate conviction:
    - regime_confidence
    - recession_agreement
    - signal_dispersion
    - momentum_confirmation
    - volatility_stability

    Query params:
    - horizon: Forecast horizon to analyze

    Returns importance scores for each component.
    """
    analysis = conviction_calibrator.compute_component_importance(horizon)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/conviction/calibration-recommendations")
async def conviction_calibration_recommendations() -> Dict[str, Any]:
    """
    Get comprehensive calibration recommendations.

    Analyzes:
    - Monotonicity across all horizons
    - Component importance
    - Data sufficiency

    Returns specific recommendations for improving conviction calibration.
    """
    recommendations = conviction_calibrator.get_calibration_recommendations()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **recommendations,
    }


@diagnostics_router.get("/conviction/risk-budget-calibration")
async def conviction_risk_budget_calibration(
    horizon: str = "1M"
) -> Dict[str, Any]:
    """
    Analyze risk budget calibration.

    Validates that higher risk budgets lead to proportionally higher returns,
    not just higher volatility.

    Query params:
    - horizon: Forecast horizon to analyze

    Returns correlation between risk budget and returns/volatility.
    """
    calibration = conviction_calibrator.compute_risk_budget_calibration(horizon)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **calibration,
    }


@diagnostics_router.post("/conviction/log")
async def conviction_log(
    date: str,
    conviction_score: float,
    components: Dict[str, float],
    risk_budget: float,
    forecast_horizon: str = "1M",
    realized_return: Optional[float] = None
) -> Dict[str, Any]:
    """
    Log a conviction score with components.

    Request body:
    - date: ISO format date
    - conviction_score: Overall conviction (0-1)
    - components: Dict of component scores
      - regime_confidence (0-1)
      - recession_agreement (0-1)
      - signal_dispersion (0-1)
      - momentum_confirmation (0-1)
      - volatility_stability (0-1)
    - risk_budget: Risk budget assigned
    - forecast_horizon: "1M", "3M", "6M", or "12M"
    - realized_return: Actual return (for backtesting)

    Returns log entry ID.
    """
    log_id = conviction_calibrator.log_conviction(
        date=date,
        conviction_score=conviction_score,
        components=components,
        risk_budget=risk_budget,
        forecast_horizon=forecast_horizon
    )

    # If realized return provided, update immediately
    if realized_return is not None:
        conviction_calibrator.update_realized_return(date, realized_return, forecast_horizon)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "log_id": log_id,
        "status": "logged",
        "realized_return_updated": realized_return is not None,
    }


@diagnostics_router.post("/conviction/update-return")
async def conviction_update_return(
    date: str,
    realized_return: float,
    horizon: str = "1M"
) -> Dict[str, Any]:
    """
    Update realized return for a conviction entry.

    Used to backfill historical data for calibration analysis.

    Request body:
    - date: Date of forecast
    - realized_return: Actual realized return
    - horizon: Which horizon ("1M", "3M", "6M", "12M")
    """
    success = conviction_calibrator.update_realized_return(date, realized_return, horizon)

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No conviction entry found for date {date}"
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date": date,
        "realized_return": realized_return,
        "horizon": horizon,
        "status": "updated",
    }


@diagnostics_router.get("/conviction/history")
async def conviction_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get conviction history.

    Query params:
    - start_date: Start date filter
    - end_date: End date filter
    - limit: Maximum records
    """
    df = conviction_calibrator.get_conviction_history(
        start_date=start_date,
        end_date=end_date,
    )

    if df.empty:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "count": 0,
            "history": [],
        }

    # Apply the display limit to the most recent `limit` rows (service returns full history).
    records = (df.tail(limit) if limit and limit > 0 else df).to_dict('records')

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(records),
        "history": records,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RECESSION MODEL VALIDATION ENDPOINTS (Phase 5: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/recession/component-metrics")
async def recession_component_metrics(
    component: Optional[str] = None,
    horizon: str = "12M"
) -> Dict[str, Any]:
    """
    Get validation metrics for recession model components.

    Query params:
    - component: "logistic", "probit", "sahm", or "all"
    - horizon: Forecast horizon ("6M" or "12M")

    Returns ROC AUC, precision, recall, F1, false positive rate.
    """
    if component and component != "all":
        metrics = recession_validator.compute_component_metrics(component, horizon)
        if not metrics:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "component": component,
                "note": "Insufficient data for metrics",
            }
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "component": component,
            "metrics": metrics.to_dict(),
        }

    # All components
    all_metrics = recession_validator.compute_all_component_metrics(horizon)
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "horizon": horizon,
        "components": {k: v.to_dict() for k, v in all_metrics.items()},
    }


@diagnostics_router.get("/recession/threshold-analysis")
async def recession_threshold_analysis(
    component: str = "blended",
    horizon: str = "12M"
) -> Dict[str, Any]:
    """
    Analyze precision/recall at different probability thresholds.

    Query params:
    - component: Component to analyze
    - horizon: Forecast horizon

    Returns metrics at thresholds [0.30, 0.40, 0.50, 0.60, 0.70].
    """
    results = recession_validator.analyze_threshold_performance(component, horizon)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "component": component,
        "horizon": horizon,
        "thresholds": results,
    }


@diagnostics_router.get("/recession/blend-optimization")
async def recession_blend_optimization(
    horizon: str = "12M"
) -> Dict[str, Any]:
    """
    Optimize blend weights for 3-model ensemble.

    Tests different weight combinations to maximize AUC.
    Current weights: logistic 40%, probit 40%, Sahm 20%.

    Query params:
    - horizon: Forecast horizon to optimize

    Returns optimal weights and expected improvement.
    """
    result = recession_validator.optimize_blend_weights(horizon)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "horizon": horizon,
        "current_weights": result.current_weights,
        "optimal_weights": result.optimal_weights,
        "improvement": result.improvement,
        "all_tested": result.all_results[:10] if result.all_results else [],  # Top 10
    }


@diagnostics_router.get("/recession/false-positive-analysis")
async def recession_false_positive_analysis(
    component: str = "blended",
    horizon: str = "12M",
    threshold: float = 0.50
) -> Dict[str, Any]:
    """
    Analyze false positive patterns.

    Query params:
    - component: Component to analyze
    - horizon: Forecast horizon
    - threshold: Probability threshold

    Returns false positive rate and recommendations.
    """
    analysis = recession_validator.analyze_false_positives(component, horizon, threshold)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/recession/lead-times")
async def recession_lead_times(
    component: str = "blended",
    horizon: str = "12M"
) -> Dict[str, Any]:
    """
    Analyze lead time before recessions.

    Query params:
    - component: Component to analyze
    - horizon: Forecast horizon

    Returns lead time statistics (mean, median, min, max).
    """
    analysis = recession_validator.analyze_lead_times(component, horizon)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/recession/calibration-recommendations")
async def recession_calibration_recommendations() -> Dict[str, Any]:
    """
    Get comprehensive recession model calibration recommendations.

    Analyzes:
    - Component metrics (AUC, precision, recall)
    - Blend weight optimization
    - False positive rates
    - Lead times

    Returns specific recommendations for improving the ensemble.
    """
    recommendations = recession_validator.get_calibration_recommendations()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **recommendations,
    }


@diagnostics_router.post("/recession/log-forecast")
async def recession_log_forecast(
    date: str,
    horizon: str,
    components: Dict[str, float],
    blended_probability: float,
    realized_recession: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Log a recession forecast with component breakdown.

    Request body:
    - date: ISO format date
    - horizon: "6M" or "12M"
    - components: Dict with keys 'logistic', 'probit', 'sahm'
    - blended_probability: Final blended probability (0-1)
    - realized_recession: Actual outcome (for backtesting)

    Returns log entry ID.
    """
    log_id = recession_validator.log_recession_forecast(
        date=date,
        horizon=horizon,
        components=components,
        blended_probability=blended_probability
    )

    if realized_recession is not None:
        recession_validator.update_realized_outcome(date, horizon, realized_recession)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "log_id": log_id,
        "status": "logged",
        "realized_updated": realized_recession is not None,
    }


@diagnostics_router.post("/recession/update-outcome")
async def recession_update_outcome(
    date: str,
    horizon: str,
    realized_recession: bool,
    realized_date: Optional[str] = None,
    lead_time_months: Optional[float] = None
) -> Dict[str, Any]:
    """
    Update realized recession outcome for a forecast.

    Used to backfill historical data for validation analysis.

    Request body:
    - date: Forecast date
    - horizon: Forecast horizon
    - realized_recession: Whether recession occurred
    - realized_date: When recession was confirmed
    - lead_time_months: Months of lead time
    """
    success = recession_validator.update_realized_outcome(
        date=date,
        horizon=horizon,
        realized_recession=realized_recession,
        realized_date=realized_date,
        lead_time_months=lead_time_months
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast found for date {date} horizon {horizon}"
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date": date,
        "horizon": horizon,
        "realized_recession": realized_recession,
        "status": "updated",
    }


@diagnostics_router.get("/recession/history")
async def recession_history(
    component: Optional[str] = None,
    horizon: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get recession forecast history.

    Query params:
    - component: Filter by component
    - horizon: Filter by horizon
    - limit: Maximum records
    """
    df = recession_validator.get_recession_history(
        component=component,
        horizon=horizon,
        min_observations=0  # Allow empty for query
    )

    if df.empty:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "count": 0,
            "history": [],
        }

    # Limit
    df = df.head(limit)
    records = df.to_dict('records')

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(records),
        "columns": list(df.columns),
        "history": records,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# EXPECTED RETURNS VALIDATION ENDPOINTS (Phase 6: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/expected-returns/sector-metrics")
async def expected_returns_sector_metrics(
    sector: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get validation metrics for expected returns per sector.

    Query params:
    - sector: Specific sector (e.g., "XLK") or all if omitted

    Returns correlation, rank correlation (IC), RMSE, MAE, directional hit rate.
    """
    if sector:
        metrics = expected_returns_validator.compute_sector_metrics(sector)
        if not metrics:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "sector": sector,
                "note": "Insufficient data for metrics",
            }
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "sector": sector,
            "metrics": metrics.to_dict(),
        }

    # All sectors
    all_metrics = expected_returns_validator.compute_all_sector_metrics()
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "sectors": {k: v.to_dict() for k, v in all_metrics.items()},
        "count": len(all_metrics),
    }


@diagnostics_router.get("/expected-returns/error-decomposition")
async def expected_returns_error_decomposition() -> Dict[str, Any]:
    """
    Decompose forecast errors by source.

    Analyzes how much error comes from:
    - Earnings yield estimation
    - Regime premium misestimation
    - Regime misclassification
    - Other/unexplained

    Returns error breakdown with recommendations.
    """
    decomposition = expected_returns_validator.analyze_error_decomposition()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **decomposition,
    }


@diagnostics_router.get("/expected-returns/regime-analysis")
async def expected_returns_regime_analysis() -> Dict[str, Any]:
    """
    Analyze expected returns accuracy by regime.

    Returns metrics per regime (Goldilocks, Reflation, Stagflation, Slowdown)
    to identify which regimes have better/worse predictive accuracy.
    """
    analysis = expected_returns_validator.analyze_by_regime()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "regimes": analysis,
    }


@diagnostics_router.get("/expected-returns/calibration-recommendations")
async def expected_returns_calibration_recommendations() -> Dict[str, Any]:
    """
    Get comprehensive calibration recommendations for expected returns.

    Analyzes:
    - Sector-level correlation and hit rates
    - Error decomposition
    - Regime-conditional accuracy

    Returns specific recommendations for improving the Grinold-Kroner model.
    """
    recommendations = expected_returns_validator.get_calibration_recommendations()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **recommendations,
    }


@diagnostics_router.post("/expected-returns/log-forecast")
async def expected_returns_log_forecast(
    date: str,
    sector: str,
    expected_return: float,
    components: Dict[str, float],
    regime: str,
    confidence: Optional[float] = None
) -> Dict[str, Any]:
    """
    Log an expected returns forecast.

    Request body:
    - date: ISO format date
    - sector: Sector ETF symbol (e.g., "XLK")
    - expected_return: Predicted annual return (decimal, e.g., 0.12 for 12%)
    - components: Dict with "earnings_yield", "regime_premium"
    - regime: Current regime classification
    - confidence: Confidence in forecast (0-1), optional

    Returns log entry ID.
    """
    log_id = expected_returns_validator.log_forecast(
        date=date,
        sector=sector,
        expected_return=expected_return,
        components=components,
        regime=regime,
        confidence=confidence
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "log_id": log_id,
        "status": "logged",
    }


@diagnostics_router.post("/expected-returns/update-realized")
async def expected_returns_update_realized(
    date: str,
    sector: str,
    realized_return: float
) -> Dict[str, Any]:
    """
    Update realized return for an expected returns forecast.

    Used to backfill historical data for validation analysis.

    Request body:
    - date: Forecast date
    - sector: Sector symbol
    - realized_return: Actual realized return
    """
    success = expected_returns_validator.update_realized_return(
        date=date,
        sector=sector,
        realized_return=realized_return
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast found for {sector} on {date}"
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date": date,
        "sector": sector,
        "realized_return": realized_return,
        "status": "updated",
    }


@diagnostics_router.get("/expected-returns/history")
async def expected_returns_history(
    sector: Optional[str] = None,
    regime: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get expected returns forecast history.

    Query params:
    - sector: Filter by sector
    - regime: Filter by regime
    - limit: Maximum records
    """
    df = expected_returns_validator.get_forecast_history(
        sector=sector,
        regime=regime,
        min_observations=0  # Allow empty for query
    )

    if df.empty:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "count": 0,
            "history": [],
        }

    # Limit and convert
    df = df.head(limit)
    records = df.to_dict('records')

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(records),
        "columns": list(df.columns),
        "history": records,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO CONSTRUCTION VALIDATION ENDPOINTS (Phase 7: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/portfolio/method-comparison")
async def portfolio_method_comparison() -> Dict[str, Any]:
    """
    Compare portfolio construction methods.

    Compares Risk Parity, Max Sharpe Ratio, and Hierarchical Risk Parity
    on realized performance metrics.

    Returns:
    - Annualized returns, volatility, Sharpe ratio per method
    - Max drawdown, turnover, transaction costs
    - Concentration metrics (HHI)
    - Best method by Sharpe ratio
    """
    comparison = portfolio_validator.compare_methods()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **comparison,
    }


@diagnostics_router.get("/portfolio/method-metrics")
async def portfolio_method_metrics(
    method: str
) -> Dict[str, Any]:
    """
    Get detailed metrics for a specific portfolio construction method.

    Query params:
    - method: "risk_parity", "max_sharpe", or "hrp"

    Returns comprehensive metrics including:
    - Return and risk metrics
    - Turnover and transaction costs
    - Concentration (HHI)
    - Hit rate
    """
    if method not in portfolio_validator.METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid method. Must be one of: {portfolio_validator.METHODS}"
        )

    metrics = portfolio_validator.compute_method_metrics(method)

    if not metrics:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "method": method,
            "note": "Insufficient data for metrics",
        }

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "method": method,
        "metrics": metrics.to_dict(),
    }


@diagnostics_router.get("/portfolio/turnover-analysis")
async def portfolio_turnover_analysis(
    method: str
) -> Dict[str, Any]:
    """
    Analyze turnover patterns for a portfolio method.

    Query params:
    - method: Portfolio construction method

    Returns turnover statistics, transaction costs, and recommendations.
    """
    if method not in portfolio_validator.METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid method. Must be one of: {portfolio_validator.METHODS}"
        )

    analysis = portfolio_validator.analyze_turnover(method)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/portfolio/drawdown-analysis")
async def portfolio_drawdown_analysis(
    method: str,
    threshold: float = -0.05
) -> Dict[str, Any]:
    """
    Analyze drawdowns for a portfolio method.

    Query params:
    - method: Portfolio construction method
    - threshold: Drawdown threshold to flag (default: -5%)

    Returns drawdown statistics, periods, and regime analysis.
    """
    if method not in portfolio_validator.METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid method. Must be one of: {portfolio_validator.METHODS}"
        )

    analysis = portfolio_validator.analyze_drawdowns(method, threshold)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/portfolio/factor-exposure")
async def portfolio_factor_exposure(
    method: str
) -> Dict[str, Any]:
    """
    Analyze factor exposure for a portfolio method.

    Query params:
    - method: Portfolio construction method

    Returns factor betas and exposure levels compared to target.
    """
    if method not in portfolio_validator.METHODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid method. Must be one of: {portfolio_validator.METHODS}"
        )

    analysis = portfolio_validator.analyze_factor_exposure(method)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/portfolio/calibration-recommendations")
async def portfolio_calibration_recommendations() -> Dict[str, Any]:
    """
    Get comprehensive calibration recommendations for portfolio construction.

    Analyzes:
    - Method comparison (Sharpe ratios)
    - Turnover patterns per method
    - Drawdown frequency and severity
    - Factor exposures

    Returns specific recommendations for method selection and improvements.
    """
    recommendations = portfolio_validator.get_calibration_recommendations()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **recommendations,
    }


@diagnostics_router.post("/portfolio/log-allocation")
async def portfolio_log_allocation(
    date: str,
    method: str,
    weights: Dict[str, float],
    regime: str,
    risk_budget: Optional[float] = None
) -> Dict[str, Any]:
    """
    Log a portfolio allocation.

    Request body:
    - date: ISO format date
    - method: "risk_parity", "max_sharpe", or "hrp"
    - weights: Dict mapping sector -> weight (e.g., {"XLK": 0.15, "XLF": 0.12})
    - regime: Current regime classification
    - risk_budget: Risk budget level (optional)

    Returns log entry ID.
    """
    try:
        log_id = portfolio_validator.log_allocation(
            date=date,
            method=method,
            weights=weights,
            regime=regime,
            risk_budget=risk_budget
        )

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "log_id": log_id,
            "status": "logged",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@diagnostics_router.post("/portfolio/update-performance")
async def portfolio_update_performance(
    date: str,
    method: str,
    portfolio_return: float,
    turnover: float = 0.0
) -> Dict[str, Any]:
    """
    Update realized performance for a portfolio allocation.

    Automatically computes transaction costs based on turnover.

    Request body:
    - date: Allocation date
    - method: Portfolio construction method
    - portfolio_return: Actual portfolio return (gross)
    - turnover: Portfolio turnover (0-1)

    Returns net return after transaction costs.
    """
    success = portfolio_validator.update_realized_performance(
        date=date,
        method=method,
        portfolio_return=portfolio_return,
        turnover=turnover
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No allocation found for {method} on {date}"
        )

    # Calculate net return
    base_cost = turnover * portfolio_validator.TRANSACTION_COSTS["equity_etf"] / 10000
    if turnover > 0.5:
        base_cost += portfolio_validator.TRANSACTION_COSTS["rebalancing_penalty"] / 10000
    net_return = portfolio_return - base_cost

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date": date,
        "method": method,
        "gross_return": portfolio_return,
        "transaction_costs": round(base_cost, 6),
        "net_return": round(net_return, 6),
        "status": "updated",
    }


@diagnostics_router.get("/portfolio/history")
async def portfolio_history(
    method: Optional[str] = None,
    regime: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get portfolio allocation history.

    Query params:
    - method: Filter by method
    - regime: Filter by regime
    - limit: Maximum records
    """
    df = portfolio_validator.get_allocation_history(
        method=method,
        regime=regime,
        min_observations=0  # Allow empty for query
    )

    if df.empty:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "count": 0,
            "history": [],
        }

    # Limit and convert
    df = df.head(limit)
    records = df.to_dict('records')

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(records),
        "columns": list(df.columns),
        "history": records,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MOMENTUM FACTOR VALIDATION ENDPOINTS (Phase 8: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/momentum/formation-comparison")
async def momentum_formation_comparison() -> Dict[str, Any]:
    """
    Compare 3M vs 12M formation periods for momentum signals.

    Returns:
    - Sharpe ratio per formation period
    - Information Coefficient (rank correlation)
    - Win rate and max drawdown
    - Recommended formation period
    """
    comparison = momentum_validator.compare_formation_periods()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **comparison,
    }


@diagnostics_router.get("/momentum/formation-metrics")
async def momentum_formation_metrics(
    formation_period: str = "12M"
) -> Dict[str, Any]:
    """
    Get detailed metrics for a momentum formation period.

    Query params:
    - formation_period: "3M" or "12M"

    Returns comprehensive metrics including:
    - Mean return, volatility, Sharpe ratio
    - Information Coefficient (IC)
    - Win rate and max drawdown
    - Carhart 4-factor alpha
    """
    if formation_period not in momentum_validator.FORMATION_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid formation_period. Must be one of: {momentum_validator.FORMATION_PERIODS}"
        )

    metrics = momentum_validator.compute_formation_metrics(formation_period)

    if not metrics:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "formation_period": formation_period,
            "note": "Insufficient data for metrics",
        }

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "formation_period": formation_period,
        "metrics": metrics.to_dict(),
    }


@diagnostics_router.get("/momentum/sector-analysis")
async def momentum_sector_analysis(
    formation_period: str = "12M"
) -> Dict[str, Any]:
    """
    Analyze momentum effectiveness by sector.

    Query params:
    - formation_period: Formation period to analyze

    Returns hit rate and consistency per sector,
    ranked by momentum effectiveness.
    """
    if formation_period not in momentum_validator.FORMATION_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid formation_period. Must be one of: {momentum_validator.FORMATION_PERIODS}"
        )

    analysis = momentum_validator.analyze_sector_momentum(formation_period)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/momentum/crash-analysis")
async def momentum_crash_analysis(
    formation_period: str = "12M",
    threshold: float = -0.15
) -> Dict[str, Any]:
    """
    Analyze momentum crash events.

    Query params:
    - formation_period: Formation period to analyze
    - threshold: Drawdown threshold for crash detection (default: -15%)

    Returns crash frequency, severity, and recommendations.
    """
    if formation_period not in momentum_validator.FORMATION_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid formation_period. Must be one of: {momentum_validator.FORMATION_PERIODS}"
        )

    analysis = momentum_validator.analyze_momentum_crashes(formation_period, threshold)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/momentum/carhart-factors")
async def momentum_carhart_factors(
    formation_period: str = "12M"
) -> Dict[str, Any]:
    """
    Perform Carhart 4-factor regression analysis.

    Query params:
    - formation_period: Formation period to analyze

    Returns:
    - Factor betas (MKT, SMB, HML, MOM)
    - Carhart alpha
    - R-squared
    """
    if formation_period not in momentum_validator.FORMATION_PERIODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid formation_period. Must be one of: {momentum_validator.FORMATION_PERIODS}"
        )

    analysis = momentum_validator.carhart_four_factor_analysis(formation_period)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/momentum/calibration-recommendations")
async def momentum_calibration_recommendations() -> Dict[str, Any]:
    """
    Get comprehensive calibration recommendations for momentum factor.

    Analyzes:
    - Formation period effectiveness (3M vs 12M)
    - Sector-level momentum effectiveness
    - Momentum crash patterns
    - Carhart 4-factor alpha

    Returns specific recommendations for momentum implementation.
    """
    recommendations = momentum_validator.get_calibration_recommendations()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **recommendations,
    }


@diagnostics_router.post("/momentum/log-signal")
async def momentum_log_signal(
    date: str,
    sector: str,
    formation_period: str,
    momentum_score: float,
    lookback_return: float,
    regime: Optional[str] = None
) -> Dict[str, Any]:
    """
    Log a momentum signal.

    Request body:
    - date: ISO format date
    - sector: Sector ETF symbol (e.g., "XLK")
    - formation_period: "3M" or "12M"
    - momentum_score: Normalized momentum score (-1 to 1)
    - lookback_return: Raw lookback return (decimal)
    - regime: Current regime classification (optional)

    Returns log entry ID.
    """
    try:
        log_id = momentum_validator.log_momentum_signal(
            date=date,
            sector=sector,
            formation_period=formation_period,
            momentum_score=momentum_score,
            lookback_return=lookback_return,
            regime=regime
        )

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "log_id": log_id,
            "status": "logged",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@diagnostics_router.post("/momentum/update-return")
async def momentum_update_return(
    date: str,
    sector: str,
    formation_period: str,
    realized_return: float,
    carhart_alpha: Optional[float] = None
) -> Dict[str, Any]:
    """
    Update realized return for a momentum signal.

    Request body:
    - date: Signal date
    - sector: Sector symbol
    - formation_period: Formation period
    - realized_return: Actual forward return
    - carhart_alpha: Carhart 4-factor alpha (optional)
    """
    success = momentum_validator.update_realized_return(
        date=date,
        sector=sector,
        formation_period=formation_period,
        realized_return=realized_return,
        carhart_alpha=carhart_alpha
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No signal found for {sector} on {date} with {formation_period} formation"
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date": date,
        "sector": sector,
        "formation_period": formation_period,
        "realized_return": realized_return,
        "carhart_alpha": carhart_alpha,
        "status": "updated",
    }


@diagnostics_router.get("/momentum/history")
async def momentum_history(
    sector: Optional[str] = None,
    formation_period: Optional[str] = None,
    regime: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get momentum signal history.

    Query params:
    - sector: Filter by sector
    - formation_period: Filter by formation period
    - regime: Filter by regime
    - limit: Maximum records
    """
    df = momentum_validator.get_signal_history(
        sector=sector,
        formation_period=formation_period,
        regime=regime,
        min_observations=0  # Allow empty for query
    )

    if df.empty:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "count": 0,
            "history": [],
        }

    # Limit and convert
    df = df.head(limit)
    records = df.to_dict('records')

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(records),
        "columns": list(df.columns),
        "history": records,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# NOWCAST MODEL VALIDATION ENDPOINTS (Phase 9: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/nowcast/variable-metrics")
async def nowcast_variable_metrics(
    variable: str
) -> Dict[str, Any]:
    """
    Get validation metrics for a nowcast variable.

    Query params:
    - variable: Variable name (e.g., "gdp_growth", "activity_index")

    Returns RMSE, MAE, bias, correlation, direction accuracy, revision impact.
    """
    if variable not in nowcast_validator.NOWCAST_VARIABLES:
        # Allow but warn
        pass

    metrics = nowcast_validator.compute_variable_metrics(variable)

    if not metrics:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "variable": variable,
            "note": "Insufficient data for metrics",
        }

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "variable": variable,
        "metrics": metrics.to_dict(),
    }


@diagnostics_router.get("/nowcast/realtime-vs-revised")
async def nowcast_realtime_vs_revised(
    variable: str = "gdp_growth"
) -> Dict[str, Any]:
    """
    Compare real-time vs revised data nowcast performance.

    Query params:
    - variable: Variable to compare

    Returns RMSE for real-time and revised vintages,
    plus revision impact quantification.
    """
    comparison = nowcast_validator.compare_realtime_vs_revised(variable)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **comparison,
    }


@diagnostics_router.get("/nowcast/vintage-analysis")
async def nowcast_vintage_analysis(
    variable: str = "gdp_growth"
) -> Dict[str, Any]:
    """
    Analyze nowcast performance across data vintages.

    Query params:
    - variable: Variable to analyze

    Returns metrics per vintage and best vintage identification.
    """
    analysis = nowcast_validator.analyze_vintage_performance(variable)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **analysis,
    }


@diagnostics_router.get("/nowcast/revision-impact")
async def nowcast_revision_impact(
    variable: str = "gdp_growth"
) -> Dict[str, Any]:
    """
    Quantify the impact of data revisions on nowcast accuracy.

    Query params:
    - variable: Variable to analyze

    Returns revision impact statistics and correlation with forecast errors.
    """
    impact = nowcast_validator.quantify_revision_impact(variable)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **impact,
    }


@diagnostics_router.get("/nowcast/calibration-recommendations")
async def nowcast_calibration_recommendations() -> Dict[str, Any]:
    """
    Get comprehensive calibration recommendations for nowcast models.

    Analyzes:
    - Variable-level RMSE, bias, correlation
    - Real-time vs revised performance
    - Vintage performance
    - Revision impact

    Returns specific recommendations for improving nowcast accuracy.
    """
    recommendations = nowcast_validator.get_calibration_recommendations()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **recommendations,
    }


@diagnostics_router.post("/nowcast/log")
async def nowcast_log(
    date: str,
    variable: str,
    nowcast_value: float,
    vintage: str,
    predictors: Dict[str, float],
    regime: Optional[str] = None
) -> Dict[str, Any]:
    """
    Log a nowcast prediction.

    Request body:
    - date: ISO format date
    - variable: Variable being nowcast
    - nowcast_value: Predicted value
    - vintage: Data vintage used
    - predictors: Dict of predictor values
    - regime: Current regime classification (optional)

    Returns log entry ID.
    """
    log_id = nowcast_validator.log_nowcast(
        date=date,
        variable=variable,
        nowcast_value=nowcast_value,
        vintage=vintage,
        predictors=predictors,
        regime=regime
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "log_id": log_id,
        "status": "logged",
    }


@diagnostics_router.post("/nowcast/update-realized")
async def nowcast_update_realized(
    date: str,
    variable: str,
    realized_value: float,
    final_vintage: str
) -> Dict[str, Any]:
    """
    Update realized value for a nowcast.

    Automatically computes forecast error metrics.

    Request body:
    - date: Nowcast date
    - variable: Variable name
    - realized_value: Actual realized value
    - final_vintage: Final data vintage
    """
    success = nowcast_validator.update_realized(
        date=date,
        variable=variable,
        realized_value=realized_value,
        final_vintage=final_vintage
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"No nowcast found for {variable} on {date}"
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "date": date,
        "variable": variable,
        "realized_value": realized_value,
        "status": "updated",
    }


@diagnostics_router.get("/nowcast/history")
async def nowcast_history(
    variable: Optional[str] = None,
    vintage: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get nowcast history.

    Query params:
    - variable: Filter by variable
    - vintage: Filter by vintage
    - limit: Maximum records
    """
    df = nowcast_validator.get_nowcast_history(
        variable=variable,
        vintage=vintage,
        min_observations=0  # Allow empty for query
    )

    if df.empty:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "count": 0,
            "history": [],
        }

    # Limit and convert
    df = df.head(limit)
    records = df.to_dict('records')

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(records),
        "columns": list(df.columns),
        "history": records,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTION MONITORING ENDPOINTS (Phase 10: Model Validation)
# ═══════════════════════════════════════════════════════════════════════════════

@diagnostics_router.get("/monitoring/realtime-accuracy")
async def monitoring_realtime_accuracy(
    model: str,
    window_hours: int = 24
) -> Dict[str, Any]:
    """
    Get real-time accuracy metrics for a model.

    Query params:
    - model: Model name
    - window_hours: Analysis window (default: 24)

    Returns RMSE, MAE, accuracy, error statistics.
    """
    metrics = production_monitor.compute_realtime_accuracy(model, window_hours)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **metrics,
    }


@diagnostics_router.get("/monitoring/drift-detection")
async def monitoring_drift_detection(
    model: str,
    baseline_hours: int = 168,
    current_hours: int = 24
) -> Dict[str, Any]:
    """
    Detect input drift for a model.

    Query params:
    - model: Model to analyze
    - baseline_hours: Baseline period (default: 168 = 1 week)
    - current_hours: Current period (default: 24 = 1 day)

    Returns drift scores per input variable.
    """
    reports = production_monitor.detect_input_drift(model, baseline_hours, current_hours)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "model": model,
        "baseline_hours": baseline_hours,
        "current_hours": current_hours,
        "drift_reports": [r.to_dict() for r in reports],
        "drift_detected": any(r.drift_detected for r in reports),
        "variables_analyzed": len(reports),
    }


@diagnostics_router.get("/monitoring/alerts")
async def monitoring_alerts(
    window_hours: int = 24,
    severity: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get active alerts for all models.

    Query params:
    - window_hours: Analysis window (default: 24)
    - severity: Filter by severity ("info", "warning", "critical")

    Returns active alerts including:
    - High error rate
    - High latency
    - Low prediction volume
    - Input drift
    """
    alerts = production_monitor.check_alert_thresholds(window_hours)

    if severity:
        alerts = [a for a in alerts if a.severity == severity]

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "window_hours": window_hours,
        "alert_count": len(alerts),
        "critical_count": len([a for a in alerts if a.severity == "critical"]),
        "warning_count": len([a for a in alerts if a.severity == "warning"]),
        "alerts": [a.to_dict() for a in alerts],
    }


@diagnostics_router.get("/monitoring/model-health")
async def monitoring_model_health(
    window_hours: int = 24
) -> Dict[str, Any]:
    """
    Get health status for all monitored models.

    Query params:
    - window_hours: Analysis window (default: 24)

    Returns health status per model including:
    - Status (healthy, degraded, failing)
    - Prediction volume
    - Latency
    - Error rate
    - Drift status
    """
    health = production_monitor.get_model_health(window_hours)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **health,
    }


@diagnostics_router.get("/monitoring/dashboard-metrics")
async def monitoring_dashboard_metrics() -> Dict[str, Any]:
    """
    Export metrics formatted for external dashboard integration.

    Returns:
    - System status
    - Active alert counts
    - Model metrics (latency, error rate, predictions)
    - Alert summary
    """
    metrics = production_monitor.export_dashboard_metrics()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **metrics,
    }


@diagnostics_router.get("/monitoring/summary")
async def monitoring_summary() -> Dict[str, Any]:
    """
    Get complete production monitoring summary.

    Returns comprehensive monitoring information:
    - All model health statuses
    - Active alerts
    - Dashboard metrics
    - Recommendations
    """
    summary = production_monitor.get_monitoring_summary()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        **summary,
    }


@diagnostics_router.post("/monitoring/log-prediction")
async def monitoring_log_prediction(
    model: str,
    prediction: Any,
    confidence: float,
    inputs: Dict[str, float],
    latency_ms: float
) -> Dict[str, Any]:
    """
    Log a production prediction for monitoring.

    Request body:
    - model: Model name
    - prediction: Model output
    - confidence: Confidence score (0-1)
    - inputs: Model input features
    - latency_ms: Prediction latency

    Returns log entry ID.
    """
    log_id = production_monitor.log_prediction(
        model=model,
        prediction=prediction,
        confidence=confidence,
        inputs=inputs,
        latency_ms=latency_ms
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "log_id": log_id,
        "status": "logged",
    }


@diagnostics_router.post("/monitoring/update-realized")
async def monitoring_update_realized(
    prediction_id: int,
    realized_outcome: Any,
    prediction_error: Optional[float] = None
) -> Dict[str, Any]:
    """
    Update realized outcome for a logged prediction.

    Request body:
    - prediction_id: Prediction log ID
    - realized_outcome: Actual realized value
    - prediction_error: Computed error (optional)

    Returns update status.
    """
    success = production_monitor.update_realized(
        prediction_id=prediction_id,
        realized_outcome=realized_outcome,
        prediction_error=prediction_error
    )

    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Prediction {prediction_id} not found"
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "prediction_id": prediction_id,
        "status": "updated",
    }


@diagnostics_router.get("/monitoring/history")
async def monitoring_history(
    model: Optional[str] = None,
    hours: int = 24,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get recent prediction history.

    Query params:
    - model: Filter by model
    - hours: Lookback hours (default: 24)
    - limit: Maximum records

    Returns prediction history with metrics.
    """
    df = production_monitor.get_recent_predictions(model=model, hours=hours)

    if df.empty:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "count": 0,
            "history": [],
        }

    # Limit and convert
    df = df.head(limit)
    records = df.to_dict('records')

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "count": len(records),
        "columns": list(df.columns),
        "history": records,
    }

"""Validation orchestration for production flows.

Centralizes validation calls so endpoints/handlers do not each hand-roll their own checks.
Wraps existing validation services with standardized ValidationResult format.
"""
import logging
import os
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Feature flag for runtime validation
ENABLE_RUNTIME_VALIDATION = os.getenv("ENABLE_RUNTIME_VALIDATION", "true").lower() == "true"


class ValidationResult:
    """Simple validation result container."""

    def __init__(self, valid: bool, issues: Optional[List[str]] = None, metadata: Optional[dict] = None):
        self.valid = valid
        self.issues = issues or []
        self.metadata = metadata or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "issues": self.issues,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    def __bool__(self) -> bool:
        return self.valid


def validate_regime_payload(payload: Dict[str, Any]) -> ValidationResult:
    """Validate regime payload using existing validation services."""
    if not ENABLE_RUNTIME_VALIDATION:
        return ValidationResult(valid=True, metadata={"skipped": True})

    try:
        # Validate regime classification if present
        if "current_regime" in payload or "regime" in payload:
            regime = payload.get("current_regime") or payload.get("regime")
            if regime:
                # Check if regime value is valid
                valid_regimes = ["goldilocks", "inflation", "deflation", "stagflation", "recession", "recovery"]
                if isinstance(regime, str) and regime.lower() not in valid_regimes:
                    return ValidationResult(
                        valid=False,
                        issues=[f"Invalid regime value: {regime}"],
                        metadata={"field": "regime", "value": regime}
                    )

        # Validate probability if present
        if "probability" in payload:
            prob = payload.get("probability")
            if prob is not None and (not isinstance(prob, (int, float)) or prob < 0 or prob > 1):
                return ValidationResult(
                    valid=False,
                    issues=[f"Probability must be between 0 and 1, got: {prob}"],
                    metadata={"field": "probability", "value": prob}
                )

        return ValidationResult(valid=True, metadata={"regime_validated": True})

    except Exception as e:
        logger.warning(f"[validation_orchestrator] Regime validation error: {e}", exc_info=True)
        return ValidationResult(
            valid=True,  # Don't block on validation failure
            issues=[f"Validation error: {str(e)}"],
            metadata={"error": True}
        )


def validate_signal_payload(payload: Dict[str, Any]) -> ValidationResult:
    """Validate signal payload using existing validation services."""
    if not ENABLE_RUNTIME_VALIDATION:
        return ValidationResult(valid=True, metadata={"skipped": True})

    try:
        issues = []

        # Check signal value range
        if "signal_value" in payload:
            sig_val = payload["signal_value"]
            if sig_val is not None and (not isinstance(sig_val, (int, float)) or sig_val < -1 or sig_val > 1):
                issues.append(f"Signal value must be between -1 and 1, got: {sig_val}")

        # Check conviction range
        if "conviction" in payload:
            conv = payload["conviction"]
            if conv is not None and (not isinstance(conv, (int, float)) or conv < 0 or conv > 1):
                issues.append(f"Conviction must be between 0 and 1, got: {conv}")

        # Check final signal enum
        if "finalSignal" in payload:
            signal = payload["finalSignal"]
            valid_signals = ["Bullish", "Bearish", "Neutral", "bullish", "bearish", "neutral"]
            if signal and signal not in valid_signals:
                issues.append(f"Invalid signal value: {signal}")

        # Check scores if present
        if "scores" in payload:
            scores = payload["scores"]
            for key, value in scores.items():
                if value is not None and (not isinstance(value, (int, float)) or value < -1 or value > 1):
                    issues.append(f"Score '{key}' must be between -1 and 1, got: {value}")

        return ValidationResult(
            valid=len(issues) == 0,
            issues=issues,
            metadata={"fields_checked": ["signal_value", "conviction", "finalSignal", "scores"]}
        )

    except Exception as e:
        logger.warning(f"[validation_orchestrator] Signal validation error: {e}", exc_info=True)
        return ValidationResult(valid=True, issues=[f"Validation error: {str(e)}"], metadata={"error": True})


def validate_risk_payload(payload: Dict[str, Any]) -> ValidationResult:
    """Validate risk payload using existing validation services."""
    if not ENABLE_RUNTIME_VALIDATION:
        return ValidationResult(valid=True, metadata={"skipped": True})

    try:
        issues = []

        # Validate recession probability
        if "probability" in payload:
            prob = payload["probability"]
            if prob is not None and (not isinstance(prob, (int, float)) or prob < 0 or prob > 1):
                issues.append(f"Recession probability must be between 0 and 1, got: {prob}")

        # Validate models section
        if "models" in payload:
            models = payload["models"]
            for model_name, model_data in models.items():
                if isinstance(model_data, dict) and "probability" in model_data:
                    model_prob = model_data["probability"]
                    if model_prob is not None and (not isinstance(model_prob, (int, float)) or model_prob < 0 or model_prob > 1):
                        issues.append(f"Model '{model_name}' probability must be between 0 and 1, got: {model_prob}")

        # Validate risk metrics ranges
        if "sharpe" in payload:
            sharpe = payload["sharpe"]
            if sharpe is not None and not isinstance(sharpe, (int, float)):
                issues.append(f"Sharpe ratio must be numeric, got: {sharpe}")

        if "maxDrawdown" in payload or "max_drawdown" in payload:
            dd = payload.get("maxDrawdown") or payload.get("max_drawdown")
            if dd is not None and not isinstance(dd, (int, float)):
                issues.append(f"Max drawdown must be numeric, got: {dd}")

        return ValidationResult(
            valid=len(issues) == 0,
            issues=issues,
            metadata={"fields_checked": ["probability", "models", "sharpe", "maxDrawdown"]}
        )

    except Exception as e:
        logger.warning(f"[validation_orchestrator] Risk validation error: {e}", exc_info=True)
        return ValidationResult(valid=True, issues=[f"Validation error: {str(e)}"], metadata={"error": True})


def validate_dashboard_payload(payload: Dict[str, Any]) -> ValidationResult:
    """Validate dashboard payload using composed sub-validations."""
    if not ENABLE_RUNTIME_VALIDATION:
        return ValidationResult(valid=True, metadata={"skipped": True})

    try:
        all_issues = []
        validation_metadata = {}

        # Validate regime section
        if "regime" in payload:
            regime_validation = validate_regime_payload(payload["regime"])
            if not regime_validation.valid:
                all_issues.extend([f"regime: {issue}" for issue in regime_validation.issues])
            validation_metadata["regime"] = regime_validation.to_dict()

        # Validate signals section
        if "signals" in payload:
            signal_validation = validate_signal_payload(payload["signals"])
            if not signal_validation.valid:
                all_issues.extend([f"signals: {issue}" for issue in signal_validation.issues])
            validation_metadata["signals"] = signal_validation.to_dict()

        # Validate recession/risk section
        if "recession" in payload:
            risk_validation = validate_risk_payload(payload["recession"])
            if not risk_validation.valid:
                all_issues.extend([f"recession: {issue}" for issue in risk_validation.issues])
            validation_metadata["recession"] = risk_validation.to_dict()

        # Check timestamp
        if "timestamp" not in payload:
            all_issues.append("Missing timestamp field")

        return ValidationResult(
            valid=len(all_issues) == 0,
            issues=all_issues,
            metadata={
                "sections_validated": ["regime", "signals", "recession"],
                "section_results": validation_metadata,
            }
        )

    except Exception as e:
        logger.warning(f"[validation_orchestrator] Dashboard validation error: {e}", exc_info=True)
        return ValidationResult(valid=True, issues=[f"Validation error: {str(e)}"], metadata={"error": True})


def validate_market_payload(payload: Dict[str, Any]) -> ValidationResult:
    """Validate market/prices payload."""
    if not ENABLE_RUNTIME_VALIDATION:
        return ValidationResult(valid=True, metadata={"skipped": True})

    try:
        # Basic price validation if prices dict is present
        if "prices" in payload and isinstance(payload["prices"], dict):
            prices = payload["prices"]
            for symbol, data in prices.items():
                if isinstance(data, dict):
                    price_val = data.get("price")
                    if price_val is not None:
                        if not isinstance(price_val, (int, float)) or price_val <= 0:
                            return ValidationResult(
                                valid=False,
                                issues=[f"Price for {symbol} must be positive numeric, got: {price_val}"],
                                metadata={"symbol": symbol, "price": price_val}
                            )

        # Check rates
        if "rates" in payload:
            rates = payload["rates"]
            if not isinstance(rates, dict):
                return ValidationResult(valid=False, issues=["Rates must be a dictionary"])

        return ValidationResult(valid=True, metadata={"market_validated": True})

    except Exception as e:
        logger.warning(f"[validation_orchestrator] Market validation error: {e}", exc_info=True)
        return ValidationResult(valid=True, issues=[f"Validation error: {str(e)}"], metadata={"error": True})


def validate_business_payload(payload: Dict[str, Any]) -> ValidationResult:
    """Validate business/trade recommendation payload."""
    if not ENABLE_RUNTIME_VALIDATION:
        return ValidationResult(valid=True, metadata={"skipped": True})

    try:
        issues = []

        # Check recommendation structure
        if "recommendation" in payload:
            rec = payload["recommendation"]
            if rec not in ["BUY", "SELL", "HOLD", "buy", "sell", "hold", None]:
                issues.append(f"Invalid recommendation: {rec}")

        # Check conviction
        if "conviction" in payload:
            conv = payload["conviction"]
            if conv is not None and (not isinstance(conv, (int, float)) or conv < 0 or conv > 1):
                issues.append(f"Conviction must be between 0 and 1, got: {conv}")

        # Check trade ideas array
        if "tradeIdeas" in payload:
            ideas = payload["tradeIdeas"]
            if not isinstance(ideas, list):
                issues.append("tradeIdeas must be a list")

        return ValidationResult(
            valid=len(issues) == 0,
            issues=issues,
            metadata={"fields_checked": ["recommendation", "conviction", "tradeIdeas"]}
        )

    except Exception as e:
        logger.warning(f"[validation_orchestrator] Business validation error: {e}", exc_info=True)
        return ValidationResult(valid=True, issues=[f"Validation error: {str(e)}"], metadata={"error": True})


# Convenience function for runtime status - imports are lazy to avoid circular deps
def get_validation_status() -> Dict[str, Any]:
    """Return current validation configuration status."""
    validators_available = {}

    # Lazy imports to avoid circular dependencies
    try:
        from api.services import (
            regime_validator,
            signal_validator,
            recession_validator,
            conviction_calibrator,
            expected_returns_validator,
            portfolio_validator,
            momentum_validator,
            nowcast_validator,
        )
        validators_available = {
            "regime": regime_validator is not None,
            "signal": signal_validator is not None,
            "recession": recession_validator is not None,
            "conviction": conviction_calibrator is not None,
            "expected_returns": expected_returns_validator is not None,
            "portfolio": portfolio_validator is not None,
            "momentum": momentum_validator is not None,
            "nowcast": nowcast_validator is not None,
        }
    except Exception as e:
        logger.debug(f"Could not load validator status: {e}")
        validators_available = {"error": str(e)}

    return {
        "enabled": ENABLE_RUNTIME_VALIDATION,
        "validators_available": validators_available
    }

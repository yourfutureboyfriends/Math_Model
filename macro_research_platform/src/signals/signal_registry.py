"""
Signal Registry

Central registry for all systematic signals.

Manages signal lifecycle:
- Registration and discovery
- Parameter updates
- Performance tracking
- Signal combination
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .signal_base import (
    CompositeSignal,
    Signal,
    SignalDirection,
    SignalOutput,
    SignalPerformance,
    calculate_signal_performance,
)

logger = logging.getLogger(__name__)


class SignalRegistry:
    """
    Central registry for all systematic signals.

    Provides:
    - Signal discovery and lookup
    - Performance tracking
    - Signal combination
    - Research lineage tracking
    """

    def __init__(self, storage_path: Optional[Path] = None):
        self.signals: Dict[str, Signal] = {}
        self.performance_history: Dict[str, List[SignalPerformance]] = {}
        self.signal_metadata: Dict[str, Dict] = {}
        self.storage_path = storage_path

    def register_signal(
        self,
        signal: Signal,
        author: str = "system",
        hypothesis: str = "",
        backtest_results: Optional[Dict] = None,
    ) -> bool:
        """
        Register a new signal.

        Args:
            signal: Signal instance to register
            author: Who created the signal
            hypothesis: Research hypothesis behind signal
            backtest_results: Initial backtest results

        Returns:
            True if registration successful
        """
        if signal.name in self.signals:
            logger.warning(f"Signal {signal.name} already registered, updating")

        self.signals[signal.name] = signal
        self.signal_metadata[signal.name] = {
            "registered_at": datetime.now(),
            "author": author,
            "hypothesis": hypothesis,
            "backtest_results": backtest_results or {},
            "status": "active",
            "tags": [],
        }

        logger.info(f"Registered signal: {signal.name}")
        return True

    def get_signal(self, name: str) -> Optional[Signal]:
        """Get signal by name."""
        return self.signals.get(name)

    def unregister_signal(self, name: str) -> bool:
        """Remove signal from registry."""
        if name in self.signals:
            del self.signals[name]
            del self.signal_metadata[name]
            logger.info(f"Unregistered signal: {name}")
            return True
        return False

    def list_signals(
        self,
        active_only: bool = True,
        asset_class: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[Dict]:
        """
        List all registered signals.

        Args:
            active_only: Only return active signals
            asset_class: Filter by asset class
            tag: Filter by tag

        Returns:
            List of signal metadata
        """
        results = []

        for name, signal in self.signals.items():
            meta = self.signal_metadata[name]

            if active_only and meta.get("status") != "active":
                continue

            if asset_class and asset_class not in signal.asset_universe:
                continue

            if tag and tag not in meta.get("tags", []):
                continue

            results.append({
                "name": name,
                "description": signal.description,
                "asset_universe": signal.asset_universe,
                "frequency": signal.frequency,
                "status": meta.get("status"),
                "author": meta.get("author"),
                "registered_at": meta.get("registered_at"),
            })

        return results

    def update_signal_status(
        self,
        name: str,
        status: str,  # active, paused, deprecated
        reason: str = "",
    ) -> bool:
        """Update signal status."""
        if name not in self.signal_metadata:
            return False

        self.signal_metadata[name]["status"] = status
        self.signal_metadata[name]["status_changed_at"] = datetime.now()
        self.signal_metadata[name]["status_reason"] = reason

        if status != "active":
            signal = self.signals.get(name)
            if signal:
                signal.is_active = False

        logger.info(f"Updated signal {name} status to {status}: {reason}")
        return True

    def calculate_all_signals(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> Dict[str, SignalOutput]:
        """
        Calculate all active signals.

        Args:
            data: Data dictionary for signal calculation
            as_of_date: Point-in-time date

        Returns:
            Dict of signal_name to SignalOutput
        """
        results = {}

        for name, signal in self.signals.items():
            if not signal.is_active:
                continue

            try:
                # Validate data availability
                is_valid, error = signal.validate(data)
                if not is_valid:
                    logger.warning(f"Signal {name} validation failed: {error}")
                    continue

                # Calculate signal
                output = signal.calculate(data, as_of_date)
                results[name] = output

                # Store in history
                signal.signal_history.append(output)

            except Exception as e:
                logger.error(f"Error calculating signal {name}: {e}")
                continue

        return results

    def combine_signals(
        self,
        signal_names: List[str],
        weights: Optional[Dict[str, float]] = None,
        combination_method: str = "weighted_average",
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """
        Combine multiple signals into composite.

        Args:
            signal_names: Names of signals to combine
            weights: Optional weights (default equal)
            combination_method: How to combine
            as_of_date: Point-in-time date

        Returns:
            Combined SignalOutput
        """
        signals = [self.signals[name] for name in signal_names if name in self.signals]

        if not signals:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalDirection.NEUTRAL,
            )

        # Create temporary composite
        composite = CompositeSignal(
            name="temp_composite",
            description="Temporary composite",
            asset_universe=[],
            sub_signals=signals,
            combination_method=combination_method,
        )

        # Set weights
        if weights:
            composite.set_weights(weights)
        else:
            equal_weight = 1.0 / len(signals)
            composite.set_weights({name: equal_weight for name in signal_names})

        # Calculate
        return composite.calculate({}, as_of_date)

    def update_performance(
        self,
        signal_name: str,
        performance: SignalPerformance,
    ) -> None:
        """Update performance metrics for a signal."""
        if signal_name not in self.performance_history:
            self.performance_history[signal_name] = []

        self.performance_history[signal_name].append(performance)

    def get_performance_summary(
        self,
        signal_name: Optional[str] = None,
    ) -> Dict:
        """
        Get performance summary for signals.

        Args:
            signal_name: Specific signal, or all if None

        Returns:
            Performance summary dict
        """
        if signal_name:
            history = self.performance_history.get(signal_name, [])
            if not history:
                return {}

            latest = history[-1]
            return {
                "signal": signal_name,
                "latest_performance": {
                    "win_rate": latest.win_rate,
                    "sharpe_ratio": latest.sharpe_ratio,
                    "max_drawdown": latest.max_drawdown,
                    "avg_return": latest.avg_return,
                },
                "history_count": len(history),
            }

        # Summary for all signals
        summaries = {}
        for name, history in self.performance_history.items():
            if history:
                latest = history[-1]
                summaries[name] = {
                    "win_rate": latest.win_rate,
                    "sharpe_ratio": latest.sharpe_ratio,
                    "status": self.signal_metadata[name].get("status"),
                }

        return summaries

    def archive_signal(self, name: str, reason: str = "") -> bool:
        """Archive signal with full history."""
        if name not in self.signals:
            return False

        self.signal_metadata[name]["archived"] = True
        self.signal_metadata[name]["archived_at"] = datetime.now()
        self.signal_metadata[name]["archive_reason"] = reason

        # Save to disk if storage path set
        if self.storage_path:
            self._archive_to_disk(name)

        return True

    def _archive_to_disk(self, name: str) -> None:
        """Archive signal data to disk."""
        if not self.storage_path:
            return

        archive_dir = self.storage_path / "archived_signals"
        archive_dir.mkdir(parents=True, exist_ok=True)

        signal = self.signals[name]
        meta = self.signal_metadata[name]

        archive_data = {
            "name": name,
            "description": signal.description,
            "parameters": signal.parameters,
            "metadata": {
                "registered_at": str(meta.get("registered_at")),
                "author": meta.get("author"),
                "hypothesis": meta.get("hypothesis"),
            },
            "signal_history": [
                {
                    "timestamp": str(s.timestamp),
                    "direction": s.direction.name,
                    "strength": s.strength,
                    "rationale": s.rationale,
                }
                for s in signal.signal_history
            ],
            "performance_history": [
                {
                    "n_signals": p.n_signals,
                    "win_rate": p.win_rate,
                    "sharpe_ratio": p.sharpe_ratio,
                }
                for p in self.performance_history.get(name, [])
            ],
        }

        archive_file = archive_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.json"
        with open(archive_file, "w") as f:
            json.dump(archive_data, f, indent=2, default=str)

        logger.info(f"Archived signal {name} to {archive_file}")

    def export_registry(self, filepath: Path) -> None:
        """Export full registry to file."""
        export_data = {
            "signals": [
                {
                    "name": name,
                    "description": sig.description,
                    "asset_universe": sig.asset_universe,
                    "frequency": sig.frequency,
                    "parameters": sig.parameters,
                    "metadata": self.signal_metadata.get(name, {}),
                }
                for name, sig in self.signals.items()
            ],
            "performance_summary": self.get_performance_summary(),
            "exported_at": str(datetime.now()),
        }

        with open(filepath, "w") as f:
            json.dump(export_data, f, indent=2, default=str)

        logger.info(f"Exported signal registry to {filepath}")

    def import_registry(self, filepath: Path) -> bool:
        """Import signal registry from file."""
        try:
            with open(filepath) as f:
                data = json.load(f)

            for sig_data in data.get("signals", []):
                # Note: Would need to reconstruct actual signal objects
                self.signal_metadata[sig_data["name"]] = sig_data.get("metadata", {})

            logger.info(f"Imported signal registry from {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to import registry: {e}")
            return False


def get_default_registry(storage_path: Optional[Path] = None) -> SignalRegistry:
    """Get default signal registry with built-in signals."""
    registry = SignalRegistry(storage_path)

    # Register built-in signals would go here
    # (Actual signal implementations would be imported and registered)

    return registry

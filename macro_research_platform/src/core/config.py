"""
Platform Configuration

Configuration management for the macro research platform.
"""

import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DataConfig:
    """Data module configuration."""
    fred_api_key: Optional[str] = None
    alfread_api_key: Optional[str] = None
    cache_dir: str = "data/cache"
    pit_data_dir: str = "data/pit"
    min_data_quality_score: float = 0.5
    max_staleness_days: int = 90


@dataclass
class EconomicMachineConfig:
    """Economic machine configuration."""
    default_regime: str = "neutral"
    debt_cycle_threshold: float = 300.0  # Debt to GDP %
    policy_neutral_rate: float = 2.5
    inflation_target: float = 2.0


@dataclass
class SignalConfig:
    """Signal module configuration."""
    min_sharpe_ratio: float = 0.5
    min_information_coefficient: float = 0.05
    max_drawdown: float = 0.25
    max_turnover: float = 2.0
    default_lookback: int = 60


@dataclass
class PortfolioConfig:
    """Portfolio module configuration."""
    target_volatility: float = 0.10
    max_position_size: float = 0.25
    min_position_size: float = 0.0
    risk_budget_method: str = "equal_risk"
    rebalance_frequency: str = "monthly"


@dataclass
class ResearchConfig:
    """Research module configuration."""
    min_observations_for_validation: int = 60
    validation_split: float = 0.7
    out_of_sample_threshold: float = 0.3
    enable_auto_postmortem: bool = True


@dataclass
class PlatformConfig:
    """Master configuration for the platform."""
    name: str = "Macro Research Platform"
    version: str = "1.0.0"
    environment: str = "development"  # development, staging, production

    # Sub-configs
    data: DataConfig = None
    economic_machine: EconomicMachineConfig = None
    signals: SignalConfig = None
    portfolio: PortfolioConfig = None
    research: ResearchConfig = None

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/platform.log"

    def __post_init__(self):
        """Initialize default sub-configs if not provided."""
        if self.data is None:
            self.data = DataConfig()
        if self.economic_machine is None:
            self.economic_machine = EconomicMachineConfig()
        if self.signals is None:
            self.signals = SignalConfig()
        if self.portfolio is None:
            self.portfolio = PortfolioConfig()
        if self.research is None:
            self.research = ResearchConfig()

    @classmethod
    def from_dict(cls, config_dict: Dict) -> "PlatformConfig":
        """Create config from dictionary."""
        data_config = DataConfig(**config_dict.get("data", {}))
        em_config = EconomicMachineConfig(**config_dict.get("economic_machine", {}))
        signal_config = SignalConfig(**config_dict.get("signals", {}))
        portfolio_config = PortfolioConfig(**config_dict.get("portfolio", {}))
        research_config = ResearchConfig(**config_dict.get("research", {}))

        return cls(
            name=config_dict.get("name", "Macro Research Platform"),
            version=config_dict.get("version", "1.0.0"),
            environment=config_dict.get("environment", "development"),
            data=data_config,
            economic_machine=em_config,
            signals=signal_config,
            portfolio=portfolio_config,
            research=research_config,
            log_level=config_dict.get("log_level", "INFO"),
            log_file=config_dict.get("log_file", "logs/platform.log"),
        )

    @classmethod
    def from_file(cls, filepath: Path) -> "PlatformConfig":
        """Load config from JSON file."""
        with open(filepath) as f:
            config_dict = json.load(f)
        return cls.from_dict(config_dict)

    def to_dict(self) -> Dict:
        """Convert config to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "environment": self.environment,
            "data": asdict(self.data),
            "economic_machine": asdict(self.economic_machine),
            "signals": asdict(self.signals),
            "portfolio": asdict(self.portfolio),
            "research": asdict(self.research),
            "log_level": self.log_level,
            "log_file": self.log_file,
        }

    def save(self, filepath: Path) -> None:
        """Save config to JSON file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Saved configuration to {filepath}")


def get_default_config() -> PlatformConfig:
    """Get default platform configuration."""
    return PlatformConfig()


def get_production_config() -> PlatformConfig:
    """Get production-optimized configuration."""
    config = PlatformConfig(
        environment="production",
        log_level="WARNING",
    )
    # Stricter validation thresholds in production
    config.signals.min_sharpe_ratio = 0.7
    config.signals.min_information_coefficient = 0.08
    config.research.min_observations_for_validation = 120
    return config


def get_research_config() -> PlatformConfig:
    """Get configuration optimized for research/development."""
    config = PlatformConfig(
        environment="development",
        log_level="DEBUG",
    )
    # More permissive thresholds for research
    config.signals.min_sharpe_ratio = 0.3
    config.data.min_data_quality_score = 0.3
    return config

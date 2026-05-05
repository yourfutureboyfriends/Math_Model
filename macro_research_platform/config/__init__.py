"""
Config module for macro regime model.

Provides centralized configuration management for:
- Data sources and API settings
- Indicator mappings
- Model parameters
- Sector allocation rules
- Research framework
"""

from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

# Try to import yaml - if not available, provide fallback
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    yaml = None

CONFIG_DIR = Path(__file__).parent


def load_yaml_config(filename: str) -> Dict[str, Any]:
    """Load a YAML configuration file."""
    if not HAS_YAML:
        raise ImportError(
            "PyYAML is required to load config files. "
            "Install with: pip install pyyaml"
        )

    config_path = CONFIG_DIR / filename
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


# Cache loaded configs
_config_cache: Dict[str, Dict] = {}


def get_config(name: str) -> Dict[str, Any]:
    """Get a cached config or load it."""
    if name not in _config_cache:
        _config_cache[name] = load_yaml_config(f"{name}.yaml")
    return _config_cache[name]


# Convenience accessors
def get_data_sources() -> Dict[str, Any]:
    """Get data sources configuration."""
    return get_config("data_sources")


def get_indicator_mapping() -> Dict[str, Any]:
    """Get indicator mapping configuration."""
    return get_config("indicator_mapping")


def get_model_settings() -> Dict[str, Any]:
    """Get model settings configuration."""
    return get_config("model_settings")


def get_sector_rules() -> Dict[str, Any]:
    """Get sector rules configuration."""
    return get_config("sector_rules")


def get_research_map() -> Dict[str, Any]:
    """Get research mapping configuration."""
    return get_config("research_map")


@dataclass
class IndicatorConfig:
    """Typed indicator configuration."""
    name: str
    source: str
    source_series_id: Optional[str]
    frequency: str
    category: str
    transformation: str
    direction: str
    release_lag_days: int
    importance_weight: float
    model_bucket: str
    description: str = ""


def get_indicator_config(indicator_name: str) -> Optional[IndicatorConfig]:
    """Get typed configuration for a specific indicator."""
    mapping = get_indicator_mapping()
    indicators = mapping.get("indicators", {})

    if indicator_name not in indicators:
        return None

    cfg = indicators[indicator_name]
    return IndicatorConfig(
        name=indicator_name,
        source=cfg.get("source", "sample"),
        source_series_id=cfg.get("source_series_id"),
        frequency=cfg.get("frequency", "monthly"),
        category=cfg.get("category", "other"),
        transformation=cfg.get("transformation", "level"),
        direction=cfg.get("direction", "neutral"),
        release_lag_days=cfg.get("release_lag_days", 30),
        importance_weight=cfg.get("importance_weight", 1.0),
        model_bucket=cfg.get("model_bucket", "other"),
        description=cfg.get("description", ""),
    )


def get_all_indicators() -> Dict[str, IndicatorConfig]:
    """Get all indicator configurations."""
    mapping = get_indicator_mapping()
    indicators = mapping.get("indicators", {})
    return {
        name: get_indicator_config(name)
        for name in indicators.keys()
    }


def get_indicators_for_bucket(bucket: str) -> list:
    """Get all indicators assigned to a specific model bucket."""
    mapping = get_indicator_mapping()
    indicators = mapping.get("indicators", {})
    return [
        name for name, cfg in indicators.items()
        if cfg.get("model_bucket") == bucket
    ]


__all__ = [
    "get_config",
    "get_data_sources",
    "get_indicator_mapping",
    "get_model_settings",
    "get_sector_rules",
    "get_research_map",
    "get_indicator_config",
    "get_all_indicators",
    "get_indicators_for_bucket",
    "IndicatorConfig",
]

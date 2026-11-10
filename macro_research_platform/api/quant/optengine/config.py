from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any
import hashlib
import json
import math

STRATEGIES = ("bull_put", "bull_call", "bear_put", "iron_condor")
FEATURES = ("momentum21", "momentum63", "momentum252", "market_momentum63", "volatility20", "volatility63", "drawdown")

class ConfigError(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigError(f"{name} must be finite numeric")
    return float(value)

def construct(cls, raw):
    if not isinstance(raw, dict):
        raise ConfigError(f"{cls.__name__} must be an object")
    unknown = set(raw) - {f.name for f in fields(cls)}
    if unknown:
        raise ConfigError(f"Unknown {cls.__name__} fields: {sorted(unknown)}")
    return cls(**raw)

@dataclass(frozen=True)
class StrategyConfig:
    enabled: bool = True
    long_delta: float = 0.50
    short_delta: float = 0.25
    wing_delta: float = 0.10
    delta_tolerance: float = 0.10
    min_dte: int = 30
    max_dte: int = 45
    min_reward_risk: float = 0.15
    min_premium_risk: float = 0.10
    min_expected_risk_return: float = 0.02
    min_expected_net_dollars: float = 1.0
    min_confidence: float = 0.50
    profit_take: float = 0.50
    stop_loss: float = 0.50
    close_dte: int = 7
    max_hold_days: int = 45

    def __post_init__(self):
        if not isinstance(self.enabled, bool):raise ConfigError("enabled must be boolean")
        for name in ("long_delta", "short_delta", "wing_delta", "delta_tolerance", "min_confidence"):
            x=finite(getattr(self,name),name)
            if not 0<x<1:raise ConfigError(f"Invalid {name}")
        if not self.wing_delta<self.short_delta<self.long_delta:raise ConfigError("Deltas must satisfy wing < short < long")
        for name in ("min_dte","max_dte","close_dte","max_hold_days"):
            x=getattr(self,name)
            if isinstance(x,bool) or not isinstance(x,int) or not 1<=x<=400:raise ConfigError(f"Invalid {name}")
        if not self.close_dte<self.min_dte<=self.max_dte:raise ConfigError("Invalid expiration window")
        for name in ("min_reward_risk","min_premium_risk","min_expected_risk_return","min_expected_net_dollars","profit_take","stop_loss"):
            x=finite(getattr(self,name),name)
            if not 0<=x<=100:raise ConfigError(f"Invalid {name}")
        if not 0<self.stop_loss<=1 or not 0<self.profit_take<=2:raise ConfigError("Invalid exits")

@dataclass(frozen=True)
class RiskConfig:
    max_positions: int = 10
    max_position_loss: float = 0.01
    max_aggregate_loss: float = 0.05
    max_sector_loss: float = 0.02
    max_country_loss: float = 0.03
    max_correlation: float = 0.80
    max_correlated_loss: float = 0.025
    max_delta_notional: float = 0.50
    max_vega_nav_per_point: float = 0.02
    max_gamma_nav_per_percent_squared: float = 0.02
    emergency_drawdown: float = 0.15
    max_contracts: int = 1000
    assignment_collateral_fraction: float = 1.0

    def __post_init__(self):
        for name in ("max_positions","max_contracts"):
            x=getattr(self,name)
            if isinstance(x,bool) or not isinstance(x,int) or not 1<=x<=1000:raise ConfigError(f"Invalid {name}")
        for f in fields(self):
            if f.name in ("max_positions","max_contracts"):continue
            x=finite(getattr(self,f.name),f.name)
            if not 0<x<=1:raise ConfigError(f"Invalid {f.name}")
        if self.max_position_loss>self.max_aggregate_loss:raise ConfigError("Per-position risk exceeds aggregate limit")

@dataclass(frozen=True)
class DataConfig:
    shortlist: int = 75
    finalists: int = 35
    min_history: int = 253
    min_observations: int = 200
    min_underlying_dollar_volume: float = 1_000_000
    min_option_volume: int = 10
    min_open_interest: int = 100
    max_relative_spread: float = 0.20
    max_quote_age_seconds: int = 900
    max_bar_age_seconds: int = 4*86400
    allow_model_quotes: bool = False
    max_chain_cache: int = 128

    def __post_init__(self):
        if not 50<=self.shortlist<=100 or not 20<=self.finalists<=50 or self.finalists>self.shortlist:raise ConfigError("Invalid screening stages")
        for name in ("shortlist","finalists","min_history","min_observations","min_option_volume","min_open_interest","max_quote_age_seconds","max_bar_age_seconds","max_chain_cache"):
            x=getattr(self,name)
            if isinstance(x,bool) or not isinstance(x,int) or x<0:raise ConfigError(f"Invalid {name}")
        if not 63<=self.min_history<=2520 or not 20<=self.min_observations<=self.min_history:raise ConfigError("Invalid history requirement")
        if self.max_quote_age_seconds<1 or self.max_bar_age_seconds<1 or self.max_chain_cache<1:raise ConfigError("Invalid age/cache limit")
        if finite(self.min_underlying_dollar_volume,"liquidity")<0 or not 0<finite(self.max_relative_spread,"spread")<=1:raise ConfigError("Invalid liquidity settings")
        if not isinstance(self.allow_model_quotes,bool):raise ConfigError("allow_model_quotes must be boolean")

@dataclass(frozen=True)
class RegimeConfig:
    bullish_momentum: float = 0.03
    strong_momentum: float = 0.08
    bearish_momentum: float = -0.03
    range_momentum: float = 0.03
    min_iv_rv: float = 1.10
    max_vol_expansion: float = 1.50
    panic_drawdown: float = -0.20
    rebound_momentum: float = 0.08

    def __post_init__(self):
        for f in fields(self):finite(getattr(self,f.name),f.name)
        if not self.bearish_momentum<0<self.bullish_momentum<=self.strong_momentum:raise ConfigError("Invalid directional regimes")
        if not 0<self.range_momentum<1 or not 1<=self.min_iv_rv<=3 or not 1<=self.max_vol_expansion<=5:raise ConfigError("Invalid volatility regimes")
        if not -1<self.panic_drawdown<0 or not 0<self.rebound_momentum<1:raise ConfigError("Invalid market states")

@dataclass(frozen=True)
class CostConfig:
    commission_per_contract: float = 0.65
    slippage_fraction_spread: float = 0.25
    exercise_fee_per_contract: float = 0.0
    stock_slippage_bps: float = 5.0
    financing_spread: float = 0.01

    def __post_init__(self):
        for f in fields(self):
            if not 0<=finite(getattr(self,f.name),f.name)<=100:raise ConfigError(f"Invalid {f.name}")

@dataclass(frozen=True)
class ForecastConfig:
    model: str = "daily_log_linear"
    coefficients: dict = field(default_factory=dict)
    intercept: float = 0.0
    mean_uncertainty_daily: float = 0.0
    volatility_weights: tuple = (0.50,0.35,0.15)
    trained_through: str | None = None
    validation_id: str | None = None
    validated: bool = False

    def __post_init__(self):
        if self.model!="daily_log_linear" or not isinstance(self.validated,bool):raise ConfigError("Unsupported forecast model")
        if not isinstance(self.coefficients,dict) or set(self.coefficients)-set(FEATURES):raise ConfigError("Unknown forecast features")
        for name,x in self.coefficients.items():finite(x,name)
        finite(self.intercept,"intercept")
        if finite(self.mean_uncertainty_daily,"mean uncertainty")<0:raise ConfigError("Negative forecast uncertainty")
        w=self.volatility_weights
        if len(w)!=3 or any(finite(x,"vol weight")<0 for x in w) or abs(sum(w)-1)>1e-9:raise ConfigError("Invalid volatility weights")
        if self.validated and (not self.trained_through or not self.validation_id):raise ConfigError("Validation provenance missing")

@dataclass(frozen=True)
class EngineConfig:
    schema_version: int = 1
    name: str = "Multi-strategy defined-risk options"
    version: str = "1.0.0"
    account_currency: str = "USD"
    universe: str = "GLOBAL"
    strategies: dict = field(default_factory=lambda:{n:StrategyConfig() for n in STRATEGIES})
    risk: RiskConfig = field(default_factory=RiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    forecast: ForecastConfig = field(default_factory=ForecastConfig)
    score_weights: dict = field(default_factory=lambda:{"edge":0.55,"direction":0.15,"liquidity":0.20,"diversification":0.10})
    approved_ranges: dict = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.schema_version,bool) or self.schema_version!=1 or not self.name or not self.version:raise ConfigError("Invalid configuration identity")
        if not isinstance(self.account_currency,str) or len(self.account_currency)!=3 or not self.account_currency.isalpha() or self.account_currency!=self.account_currency.upper():raise ConfigError("Invalid account currency")
        if not isinstance(self.universe,str) or not self.universe:raise ConfigError("Missing universe")
        if set(self.strategies)!=set(STRATEGIES):raise ConfigError("Four strategy configurations required")
        if set(self.score_weights)!={"edge","direction","liquidity","diversification"}:raise ConfigError("Unknown scoring terms")
        if any(finite(x,"score weight")<0 for x in self.score_weights.values()) or abs(sum(self.score_weights.values())-1)>1e-9:raise ConfigError("Invalid scoring weights")
        raw=asdict(self)
        for path,bounds in self.approved_ranges.items():
            val=raw
            try:
                for part in path.split("."):val=val[part]
            except (KeyError,TypeError):raise ConfigError(f"Unknown approved range {path}")
            if not isinstance(bounds,(list,tuple)) or len(bounds)!=2 or not finite(bounds[0],path)<=finite(val,path)<=finite(bounds[1],path):raise ConfigError(f"Outside approved range: {path}")

    @classmethod
    def from_dict(cls,raw):
        raw=dict(raw)
        types={"risk":RiskConfig,"data":DataConfig,"regime":RegimeConfig,"costs":CostConfig,"forecast":ForecastConfig}
        for name,kind in types.items():
            if name in raw:raw[name]=construct(kind,raw[name])
        if "strategies" in raw:raw["strategies"]={k:construct(StrategyConfig,v) for k,v in raw["strategies"].items()}
        return construct(cls,raw)

    def to_dict(self):return asdict(self)
    @property
    def config_id(self):return digest(self.to_dict())

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math

class DataError(ValueError):
    pass

def utc(value):
    if isinstance(value,str):value=datetime.fromisoformat(value.replace("Z","+00:00"))
    if not isinstance(value,datetime) or value.tzinfo is None:raise DataError("Timestamp must include a timezone")
    return value.astimezone(timezone.utc)

def number(value,name):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise DataError(f"Missing or invalid {name}")
    return float(value)

@dataclass(frozen=True)
class Spot:
    underlying: str
    bid: float
    ask: float
    currency: str
    quoted_at: str
    available_at: str

    def validate(self,asof,max_age):
        at=utc(asof);quoted=utc(self.quoted_at);known=utc(self.available_at)
        if not 0<number(self.bid,"spot bid")<=number(self.ask,"spot ask"):raise DataError("Invalid spot market")
        if quoted>known or known>at or quoted>at or (at-quoted).total_seconds()>max_age:raise DataError("Stale or future spot")
        if not self.currency or len(self.currency)!=3:raise DataError("Invalid spot currency")
        return self
    @property
    def mid(self):return (self.bid+self.ask)/2

@dataclass(frozen=True)
class Quote:
    contract_id: str
    underlying: str
    option_type: str
    strike: float
    expiry: str
    bid: float
    ask: float
    iv: float
    delta: float
    gamma: float
    vega: float
    theta: float
    volume: int
    open_interest: int
    quoted_at: str
    available_at: str
    multiplier: int = 100
    currency: str = "USD"
    exercise: str = "american"
    settlement: str = "physical"
    tick_size: float = 0.01
    source: str = "observed"

    def validate(self,asof,data,mode):
        at=utc(asof);quoted=utc(self.quoted_at);known=utc(self.available_at);expiry=utc(self.expiry)
        if not self.contract_id or not self.underlying or self.option_type not in ("call","put"):raise DataError("Invalid contract identity")
        if not 0<number(self.strike,"strike") or not 0<=number(self.bid,"bid")<=number(self.ask,"ask") or self.ask<=0:raise DataError("Invalid option market")
        for key in ("iv","delta","gamma","vega","theta","tick_size"):number(getattr(self,key),key)
        if not 0<self.iv<5 or self.gamma<0 or self.vega<0 or not 0<self.tick_size<=self.ask:raise DataError("Invalid option analytics")
        if not (0<=self.delta<=1 if self.option_type=="call" else -1<=self.delta<=0):raise DataError("Invalid signed delta")
        if isinstance(self.multiplier,bool) or not isinstance(self.multiplier,int) or self.multiplier<=0:raise DataError("Invalid contract multiplier")
        if self.exercise not in ("american","european") or self.settlement not in ("cash","physical"):raise DataError("Unsupported exercise/settlement")
        if self.currency is None or len(self.currency)!=3:raise DataError("Invalid quote currency")
        if quoted>known or known>at or quoted>at or (at-quoted).total_seconds()>data.max_quote_age_seconds:raise DataError("Stale or future option")
        if expiry<=at:raise DataError("Expired contract")
        if self.source!="observed" and not (mode=="research" and data.allow_model_quotes):raise DataError("Model quotes are research-only")
        for name in ("volume","open_interest"):
            x=getattr(self,name)
            if isinstance(x,bool) or not isinstance(x,int) or x<0:raise DataError(f"Missing or invalid {name}")
        return self

    @property
    def signature(self):return (self.contract_id,self.underlying,self.option_type,self.strike,self.expiry,self.multiplier,self.currency,self.exercise,self.settlement)
    @property
    def mid(self):return (self.bid+self.ask)/2
    def dte(self,asof):return (utc(self.expiry)-utc(asof)).total_seconds()/86400
    def to_dict(self):return asdict(self)

@dataclass(frozen=True)
class Leg:
    quote: Quote
    quantity: int

@dataclass
class Opportunity:
    strategy: str
    underlying: str
    legs: tuple[Leg,...]
    asof: str
    feature: dict
    regime: dict
    entry: float = 0.0
    max_loss: float = 0.0
    max_profit: float = 0.0
    margin: float = 0.0
    expected_net: float = 0.0
    expected_risk_return: float = 0.0
    confidence: float = 0.0
    probability_profit: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    score: float = 0.0
    terms: dict = field(default_factory=dict)
    breakevens: tuple = ()
    rejection: str | None = None

    @property
    def contract_ids(self):return tuple(l.quote.contract_id for l in self.legs)
    @property
    def expiry(self):return self.legs[0].quote.expiry if self.legs else self.terms["expiry"]
    @property
    def currency(self):return self.legs[0].quote.currency if self.legs else self.terms["currency"]
    @property
    def multiplier(self):return self.legs[0].quote.multiplier if self.legs else self.terms["multiplier"]
    def to_dict(self):
        raw=asdict(self)
        raw["legs"]=[{"quantity":l.quantity,"quote":l.quote.to_dict()} for l in self.legs]
        return raw
    @classmethod
    def from_dict(cls,raw):
        raw=dict(raw);raw["legs"]=tuple(Leg(Quote(**l["quote"]),l["quantity"]) for l in raw["legs"]);return cls(**raw)

@dataclass(frozen=True)
class AssignmentEvent:
    event_id: str
    position_id: str
    contract_id: str
    contracts: int
    effective_at: str
    available_at: str
    action: str = "assigned"

    def validate(self,asof):
        if not self.event_id or not self.position_id or not self.contract_id:raise DataError("Missing assignment identity")
        if self.action not in ("assigned","exercised") or isinstance(self.contracts,bool) or not isinstance(self.contracts,int) or self.contracts<=0:raise DataError("Invalid assignment")
        if utc(self.effective_at)>utc(self.available_at) or utc(self.available_at)>utc(asof):raise DataError("Future assignment event")
        return self

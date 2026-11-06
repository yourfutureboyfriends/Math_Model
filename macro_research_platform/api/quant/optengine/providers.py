from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable
from .schema import AssignmentEvent, DataError, Quote, Spot, number, utc

@dataclass(frozen=True)
class Snapshot:
    asof: str
    spots: dict[str,Spot]
    fx: dict[str,float]
    fx_available_at: str
    account_currency: str = "USD"
    annual_cash_rate: float | None = None
    buying_power: float | None = None
    assignments: tuple[AssignmentEvent,...] = ()
    dividends: dict = field(default_factory=dict)

    def validate(self):
        at=utc(self.asof)
        if utc(self.fx_available_at)>at:raise DataError("Future FX input")
        if self.account_currency not in self.fx or abs(self.fx[self.account_currency]-1)>1e-9:raise DataError("Account FX must be one")
        if (at-utc(self.fx_available_at)).total_seconds()>86400:raise DataError("Stale FX inputs")
        if any(number(v,"FX")<=0 for v in self.fx.values()):raise DataError("Invalid FX")
        if self.annual_cash_rate is not None:number(self.annual_cash_rate,"cash rate")
        if self.buying_power is not None and number(self.buying_power,"buying power")<0:raise DataError("Negative buying power")
        if any(k!=s.underlying for k,s in self.spots.items()):raise DataError("Spot key/underlying mismatch")
        for e in self.assignments:e.validate(self.asof)
        return self

    def conversion(self,currency):
        if currency not in self.fx:raise DataError(f"No point-in-time FX for {currency}")
        return self.fx[currency]

class HistoricalProvider:
    def __init__(self,panel,chain_loader:Callable,snapshots,cache_size=128,availability=None,universe_name="GLOBAL"):
        self.panel=panel;self.chain_loader=chain_loader;self.snapshots=snapshots;self.cache=OrderedDict();self.cache_size=cache_size
        self.chain_requests=[];self.availability=availability;self.universe_name=universe_name
    @property
    def universe(self):return self.panel.symbols
    def snapshot(self,asof):
        value=self.snapshots[asof] if isinstance(self.snapshots,dict) else self.snapshots(asof)
        return value.validate()
    def features(self,asof,min_history=253):return self.panel.features(asof,min_history)
    def correlation(self,a,b,asof):return self.panel.correlation(a,b,asof)
    def has_chain(self,underlying,asof):
        if self.availability is None:return None
        entry=self.availability(underlying,asof)
        if entry is None:return False
        if utc(entry["available_at"])>utc(asof):raise DataError("Future chain-availability index")
        return bool(entry.get("available",False))
    def chain(self,underlying,asof):
        key=(underlying,utc(asof).isoformat())
        if key in self.cache:self.cache.move_to_end(key);return self.cache[key]
        self.chain_requests.append(key)
        raw=self.chain_loader(underlying,asof)
        quotes=tuple(q if isinstance(q,Quote) else Quote(**q) for q in (raw or ()))
        if any(q.underlying!=underlying for q in quotes):raise DataError("Chain contains another underlying")
        ids=[q.contract_id for q in quotes]
        if len(ids)!=len(set(ids)):raise DataError("Duplicate option contract IDs")
        self.cache[key]=quotes
        while len(self.cache)>self.cache_size:self.cache.popitem(last=False)
        return quotes

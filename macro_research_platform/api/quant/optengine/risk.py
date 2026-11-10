from __future__ import annotations
from dataclasses import dataclass
import math
from .schema import DataError

@dataclass(frozen=True)
class RiskDecision:
    contracts: int
    reason: str
    calculation: dict

def size(op,book,snapshot,provider,config,provisional=()):
    p=config.risk
    nav=book.nav*(1-p.max_aggregate_loss)
    if not math.isfinite(op.max_loss) or op.max_loss<=0 or not math.isfinite(op.margin) or op.margin<=0:return RiskDecision(0,"Invalid defined loss or margin",{})
    if book.stopped:return RiskDecision(0,"Emergency stop latched",{})
    if not math.isfinite(nav) or nav<=0:return RiskDecision(0,"Invalid portfolio equity",{})
    exposures=book.risk_exposures(snapshot)+list(provisional)
    if len(exposures)>=p.max_positions:return RiskDecision(0,"Position limit",{})
    if any(e["underlying"]==op.underlying for e in exposures):return RiskDecision(0,"Underlying already reserved",{})
    fx=snapshot.conversion(op.currency)
    sector=op.feature.get("sector") or "UNKNOWN"
    country=op.feature.get("country") or "UNKNOWN"
    total=sum(e["risk"] for e in exposures)
    sector_risk=sum(e["risk"] for e in exposures if e["sector"]==sector)
    country_risk=sum(e["risk"] for e in exposures if e["country"]==country)
    correlated=0.0
    correlations={}
    for e in exposures:
        corr=provider.correlation(op.underlying,e["underlying"],snapshot.asof)
        if corr is None:return RiskDecision(0,"Correlation data unavailable",{})
        correlations[e["underlying"]]=corr
        if abs(corr)>=p.max_correlation:correlated+=e["risk"]
    used_delta=sum(e["delta_notional"] for e in exposures)
    used_vega=sum(e["vega"] for e in exposures)
    used_gamma=sum(e["gamma"] for e in exposures)
    per_delta=abs(op.delta)*op.feature["spot"]*fx
    per_vega=abs(op.vega)*fx
    per_gamma=abs(op.gamma)*(op.feature["spot"]*.01)**2*.5*fx
    reserved=sum(e["margin"] for e in exposures)
    available=max(0.0,min(book.cash-book.collateral(snapshot),snapshot.buying_power if snapshot.buying_power is not None else book.cash-book.collateral(snapshot)))
    provisional_margin=sum(e["margin"] for e in provisional)
    limits=[p.max_contracts,p.max_position_loss*nav/op.max_loss,(p.max_aggregate_loss*nav-total)/op.max_loss,
            (p.max_sector_loss*nav-sector_risk)/op.max_loss,(p.max_country_loss*nav-country_risk)/op.max_loss,
            (p.max_correlated_loss*nav-correlated)/op.max_loss,(available-provisional_margin)/op.margin]
    for available_risk,per in ((p.max_delta_notional*nav-used_delta,per_delta),(p.max_vega_nav_per_point*nav-used_vega,per_vega),(p.max_gamma_nav_per_percent_squared*nav-used_gamma,per_gamma)):
        if per>0:limits.append(available_risk/per)
    count=max(0,int(math.floor(min(limits))))
    calculation={"equity":nav,"per_contract_loss":op.max_loss,"aggregate_loss_before":total,"available_buying_power":available,
                 "correlations":correlations,"contracts":count,"max_loss":count*op.max_loss,"margin":count*op.margin,
                 "delta_notional":count*per_delta,"vega":count*per_vega,"gamma":count*per_gamma,"sector":sector,"country":country}
    return RiskDecision(count,"Approved risk budget" if count else "No whole contract fits risk/buying-power limits",calculation)

def reservation(op,contracts,snapshot):
    fx=snapshot.conversion(op.currency)
    return {"underlying":op.underlying,"sector":op.feature.get("sector") or "UNKNOWN","country":op.feature.get("country") or "UNKNOWN",
            "risk":contracts*op.max_loss,"margin":contracts*op.margin,"delta_notional":contracts*abs(op.delta)*op.feature["spot"]*fx,"vega":contracts*abs(op.vega)*fx,"gamma":contracts*abs(op.gamma)*(op.feature["spot"]*.01)**2*.5*fx}

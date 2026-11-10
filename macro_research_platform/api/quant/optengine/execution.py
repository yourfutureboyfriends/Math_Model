from __future__ import annotations

from dataclasses import dataclass,field
from datetime import timedelta
import hashlib
import math
import copy
from .schema import DataError,Leg,Opportunity,Quote,utc
from .scoring import execution_value
from .strategies.base import bounds

class LiveExecutionDisabled(PermissionError):
    pass

@dataclass
class PaperBook:
    capital: float
    config_id: str
    mode: str = "research"
    cash: float | None = None
    nav: float | None = None
    peak_nav: float | None = None
    positions: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    inventory: dict = field(default_factory=dict)
    last_asof: str | None = None
    last_rate: float | None = None
    stopped: bool = False
    stop_reason: str | None = None
    processed_events: list = field(default_factory=list)
    fills: list = field(default_factory=list)

    def __post_init__(self):
        if self.mode not in ("research","paper"):raise LiveExecutionDisabled("Live execution is not implemented or authorized")
        if isinstance(self.capital,bool) or not isinstance(self.capital,(int,float)) or not math.isfinite(self.capital) or self.capital<=0:raise DataError("Invalid capital")
        if self.cash is None:self.cash=float(self.capital)
        if self.nav is None:self.nav=float(self.capital)
        if self.peak_nav is None:self.peak_nav=float(self.capital)

    def to_dict(self):
        from dataclasses import asdict
        return asdict(self)
    @classmethod
    def from_dict(cls,raw):return cls(**raw)

    def emergency_stop(self,reason):
        self.stopped=True;self.stop_reason=reason;self.pending=[]

    def accrue(self,snapshot,config):
        if self.last_asof and self.last_rate is not None:
            years=(utc(snapshot.asof)-utc(self.last_asof)).total_seconds()/(365*86400)
            if years<0:raise DataError("Out-of-order book clock")
            spread=config.costs.financing_spread if self.cash<0 else 0.0
            self.cash*=math.exp((self.last_rate+spread)*years)

    def collateral(self,snapshot):
        total=0.0
        for pos in self.positions:
            op=Opportunity.from_dict(pos["opportunity"])
            low,_=bounds(op.legs)
            total+=max(0.0,-low,op.terms.get("operational_reserve_local",0.0))*snapshot.conversion(op.currency)*pos["contracts"]
        return total

    def risk_exposures(self,snapshot):
        out=[]
        for pos in self.positions:
            op=Opportunity.from_dict(pos["opportunity"]);n=pos["contracts"];fx=snapshot.conversion(op.currency)
            risk=max(op.max_loss,op.terms.get("original_local_risk",op.max_loss/fx)*fx)*n
            spot=snapshot.spots[op.underlying].mid
            out.append({"underlying":op.underlying,"sector":op.feature.get("sector") or "UNKNOWN","country":op.feature.get("country") or "UNKNOWN",
                        "risk":risk,"margin":risk,"delta_notional":abs(op.delta)*spot*fx*n,"vega":abs(op.vega)*fx*n,"gamma":abs(op.gamma)*(spot*.01)**2*.5*fx*n})
        return out

    def mark(self,snapshot,quotes,config):
        value=self.cash
        for pos in self.positions:
            op=Opportunity.from_dict(pos["opportunity"])
            spot=snapshot.spots.get(op.underlying)
            if spot is None:raise DataError("Position spot missing")
            spot.validate(snapshot.asof,config.data.max_quote_age_seconds)
            if spot.currency!=op.currency:raise DataError("Position spot/option currency mismatch")
            mark=0.0
            legs=[]
            for leg in op.legs:
                q=quotes.get(leg.quote.contract_id)
                if q is None:raise DataError(f"Missing position quote {leg.quote.contract_id}")
                q.validate(snapshot.asof,config.data,self.mode)
                if q.signature!=leg.quote.signature:raise DataError("Contract identity changed")
                legs.append(Leg(q,leg.quantity))
                mark+=leg.quantity*q.multiplier*q.mid*snapshot.conversion(q.currency)*pos["contracts"]
            op.legs=tuple(legs)
            op.delta=sum(l.quantity*l.quote.multiplier*l.quote.delta for l in op.legs)
            op.gamma=sum(l.quantity*l.quote.multiplier*l.quote.gamma for l in op.legs)
            op.vega=sum(l.quantity*l.quote.multiplier*l.quote.vega for l in op.legs)
            op.theta=sum(l.quantity*l.quote.multiplier*l.quote.theta for l in op.legs)
            pos["opportunity"]=op.to_dict();pos["mark"]=mark
            value+=mark
        for u,units in self.inventory.items():
            spot=snapshot.spots.get(u)
            if spot is None:raise DataError("Assigned stock mark missing")
            spot.validate(snapshot.asof,config.data.max_quote_age_seconds)
            value+=units*spot.mid*snapshot.conversion(spot.currency)
        if not math.isfinite(value):raise DataError("Nonfinite NAV")
        self.nav=value;self.peak_nav=max(self.peak_nav,value)
        return value

    def fill(self,intent,op,contracts,snapshot,config):
        if utc(snapshot.asof)<=utc(intent["created_at"]):raise DataError("Cannot fill on the signal snapshot")
        if any(x["order_id"]==intent["order_id"] for x in self.fills):return None
        amount=sum(execution_value(l,config.costs) for l in op.legs)*snapshot.conversion(op.currency)*contracts
        fee=sum(abs(l.quantity) for l in op.legs)*config.costs.commission_per_contract*contracts
        self.cash-=amount+fee
        op.terms["original_local_risk"]=op.max_loss/snapshot.conversion(op.currency)
        pos={"position_id":intent["order_id"],"contracts":contracts,"opened_at":snapshot.asof,"entry_cash":amount+fee,"opportunity":op.to_dict(),"mark":0.0,"assignment_unwind":False}
        self.positions.append(pos)
        fill={"order_id":intent["order_id"],"asof":snapshot.asof,"kind":"open","contracts":contracts,"entry":amount,"fees":fee,
              "legs":[{"contract_id":l.quote.contract_id,"contracts":contracts*l.quantity,"price":abs(execution_value(l,config.costs)/(l.quote.multiplier*l.quantity))} for l in op.legs],"simulation":"atomic multi-leg bid/ask plus slippage"}
        self.fills.append(fill);self.fills[:]=self.fills[-256:];return fill

    def close(self,pos,snapshot,quotes,config,reason):
        op=Opportunity.from_dict(pos["opportunity"]);current=[]
        for l in op.legs:
            q=quotes.get(l.quote.contract_id)
            if q is None:raise DataError("Exit quote missing")
            q.validate(snapshot.asof,config.data,self.mode)
            if q.signature!=l.quote.signature:raise DataError("Exit contract identity changed")
            current.append(Leg(q,l.quantity))
        credit=sum(execution_value(l,config.costs,opening=False) for l in current)*snapshot.conversion(op.currency)*pos["contracts"]
        fee=sum(abs(l.quantity) for l in current)*config.costs.commission_per_contract*pos["contracts"]
        self.cash+=credit-fee
        self.positions.remove(pos)
        fill={"order_id":pos["position_id"]+":close","asof":snapshot.asof,"kind":"close","contracts":pos["contracts"],"cashflow":credit-fee,"fees":fee,"reason":reason,"legs":[{"contract_id":l.quote.contract_id,"contracts":-pos["contracts"]*l.quantity,"price":abs(execution_value(l,config.costs,opening=False)/(l.quote.multiplier*l.quantity))} for l in current]}
        self.fills.append(fill);self.fills[:]=self.fills[-256:];return fill

    def apply_assignments(self,snapshot,config):
        records=[]
        for event in snapshot.assignments:
            if event.event_id in self.processed_events:continue
            event.validate(snapshot.asof)
            pos=next((p for p in self.positions if p["position_id"]==event.position_id),None)
            if pos is None:raise DataError("Assignment position missing")
            op=Opportunity.from_dict(pos["opportunity"])
            index=next((i for i,l in enumerate(op.legs) if l.quote.contract_id==event.contract_id),None)
            if index is None:raise DataError("Assignment contract missing")
            leg=op.legs[index];q=leg.quote
            if event.contracts>pos["contracts"] or abs(leg.quantity)!=1:raise DataError("Assignment quantity exceeds position")
            if event.action=="assigned" and leg.quantity>=0 or event.action=="exercised" and leg.quantity<=0:raise DataError("Assignment/exercise side mismatch")
            if q.exercise!="american" and utc(snapshot.asof)<utc(q.expiry):raise DataError("European early exercise is invalid")
            if q.settlement!="physical":raise DataError("Physical assignment on cash-settled option")
            if event.contracts<pos["contracts"]:
                old=pos
                pos=copy.deepcopy(old)
                fraction=event.contracts/old["contracts"]
                pos["position_id"]=old["position_id"]+":assignment:"+event.event_id
                pos["contracts"]=event.contracts;pos["entry_cash"]*=fraction
                old["contracts"]-=event.contracts;old["entry_cash"]*=1-fraction
                self.positions.append(pos)
            units=event.contracts*q.multiplier*leg.quantity*(1 if q.option_type=="call" else -1)
            self.inventory[q.underlying]=self.inventory.get(q.underlying,0)+units
            self.cash-=units*q.strike*snapshot.conversion(q.currency)
            self.cash-=event.contracts*config.costs.exercise_fee_per_contract
            op.legs=tuple(l for i,l in enumerate(op.legs) if i!=index)
            pos["opportunity"]=op.to_dict();pos["assignment_unwind"]=True
            self.processed_events.append(event.event_id)
            records.append({"event":"assignment","event_id":event.event_id,"asof":snapshot.asof,"underlying":q.underlying,"stock_units":units,"strike":q.strike})
        return records

    def unwind_inventory(self,snapshot,config):
        records=[]
        for u,units in list(self.inventory.items()):
            if units==0:self.inventory.pop(u);continue
            spot=snapshot.spots.get(u)
            if spot is None:raise DataError("Assignment unwind spot missing")
            spot.validate(snapshot.asof,config.data.max_quote_age_seconds)
            price=(spot.bid if units>0 else spot.ask)*(1-config.costs.stock_slippage_bps/10000 if units>0 else 1+config.costs.stock_slippage_bps/10000)
            self.cash+=units*price*snapshot.conversion(spot.currency)
            records.append({"event":"assigned_stock_unwind","asof":snapshot.asof,"underlying":u,"units":units,"price":price})
            self.inventory.pop(u)
        return records

    def settle(self,snapshot,settlements,config):
        records=[]
        for pos in list(self.positions):
            op=Opportunity.from_dict(pos["opportunity"])
            if utc(op.expiry)>utc(snapshot.asof):continue
            event=settlements.get((op.underlying,op.expiry))
            if event is None:raise DataError("Official expiry settlement missing")
            if utc(event["available_at"])>utc(snapshot.asof) or utc(event["available_at"])<utc(op.expiry):raise DataError("Invalid settlement timestamp")
            if event.get("source")!="observed" and not (self.mode=="research" and config.data.allow_model_quotes):raise DataError("Model settlement is research-only")
            if event.get("underlying")!=op.underlying or event.get("expiry")!=op.expiry or event.get("currency")!=op.currency:raise DataError("Settlement identity/currency mismatch")
            price=event["price"]
            if any(l.quote.settlement=="physical" and l.quote.contract_id not in event.get("exercises",{}) for l in op.legs):raise DataError("Physical expiry needs explicit exercise/assignment instructions")
            if isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or price<=0:raise DataError("Invalid expiry price")
            fx=snapshot.conversion(op.currency)
            exercises=event.get("exercises",{})
            if any(not isinstance(v,bool) for v in exercises.values()):raise DataError("Exercise instructions must be boolean")
            for l in op.legs:
                q=l.quote;intr=max(price-q.strike,0) if q.option_type=="call" else max(q.strike-price,0)
                if q.settlement=="cash":self.cash+=l.quantity*q.multiplier*intr*pos["contracts"]*fx
                else:
                    if q.contract_id not in exercises:raise DataError("Physical expiry needs explicit exercise/assignment instructions")
                    if exercises[q.contract_id]:
                        units=pos["contracts"]*q.multiplier*l.quantity*(1 if q.option_type=="call" else -1)
                        self.inventory[q.underlying]=self.inventory.get(q.underlying,0)+units
                        self.cash-=units*q.strike*fx
                        self.cash-=pos["contracts"]*config.costs.exercise_fee_per_contract
            self.positions.remove(pos)
            records.append({"event":"expiry_settlement","asof":snapshot.asof,"position_id":pos["position_id"],"price":price,"source":event["source"]})
        return records

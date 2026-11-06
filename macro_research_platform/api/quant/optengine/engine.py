from __future__ import annotations

import copy
import hashlib
import time
from datetime import timedelta
from .schema import DataError,Leg,Opportunity,utc
from .regimes import classify,forecast
from .scoring import measure,assignment_hazard
from .risk import size,reservation
from .strategies import BUILDERS

class DecisionEngine:
    def __init__(self,config,provider,approval=None):
        self.config=config;self.provider=provider;self.approval=approval

    def entry_permission(self,book,asof):
        if book.mode=="research":return True
        a=self.approval or {}
        return a.get("status")=="approved" and a.get("scope")=="paper" and a.get("config_id")==self.config.config_id and bool(a.get("approved_at")) and utc(a["approved_at"])<=utc(asof)

    def quotes(self,underlyings,asof,events):
        quotes={}
        for u in sorted(set(underlyings)):
            try:
                for q in self.provider.chain(u,asof):
                    if q.contract_id in quotes and quotes[q.contract_id]!=q:raise DataError("Conflicting contract identity")
                    quotes[q.contract_id]=q
            except (DataError,KeyError,ValueError) as e:events.append({"event":"chain_rejected","underlying":u,"reason":str(e)})
        return quotes

    def filter_chain(self,chain,snapshot,mode,events):
        out=[]
        for q in chain:
            try:
                q.validate(snapshot.asof,self.config.data,mode)
                rel=(q.ask-q.bid)/max(q.mid,1e-9)
                if q.volume<self.config.data.min_option_volume or q.open_interest<self.config.data.min_open_interest or rel>self.config.data.max_relative_spread+1e-12:raise DataError("Option liquidity threshold")
                snapshot.conversion(q.currency)
                out.append(q)
            except (DataError,ValueError) as e:events.append({"event":"contract_rejected","contract_id":q.contract_id,"underlying":q.underlying,"reason":str(e)})
        return out

    def refresh(self,raw,features,market,snapshot,quotes,mode):
        old=Opportunity.from_dict(raw)
        feature=dict(features[old.underlying])
        spot=snapshot.spots[old.underlying];spot.validate(snapshot.asof,self.config.data.max_quote_age_seconds)
        if spot.currency!=feature["currency"]:raise DataError("History/spot currency mismatch")
        feature["spot"]=spot.mid
        legs=tuple(Leg(quotes[l.quote.contract_id],l.quantity) for l in old.legs)
        if any(a.quote.signature!=b.quote.signature for a,b in zip(legs,old.legs)):raise DataError("Fill contract identity changed")
        for l in legs:
            l.quote.validate(snapshot.asof,self.config.data,mode)
            if l.quote.currency!=spot.currency:raise DataError("Fill quote/spot currency mismatch")
            if (l.quote.ask-l.quote.bid)/max(l.quote.mid,1e-9)>self.config.data.max_relative_spread+1e-12 or l.quote.volume<self.config.data.min_option_volume or l.quote.open_interest<self.config.data.min_open_interest:raise DataError("Fill liquidity changed")
        estimate=forecast(feature,self.config,snapshot.asof)
        regime=classify(feature,market,sum(l.quote.iv for l in legs)/len(legs),estimate,self.config)
        if old.strategy not in regime["strategies"] or not self.config.strategies[old.strategy].enabled:raise DataError("Strategy no longer eligible at fill")
        if any(not self.config.strategies[old.strategy].min_dte<=l.quote.dte(snapshot.asof)<=self.config.strategies[old.strategy].max_dte for l in legs):raise DataError("Fill expiration no longer eligible")
        op=Opportunity(old.strategy,old.underlying,legs,snapshot.asof,feature,regime)
        measure(op,snapshot,self.config)
        if op.rejection:raise DataError(op.rejection)
        hazard=assignment_hazard(op,snapshot)
        if hazard:raise DataError(hazard)
        return op

    def tick(self,book,asof,settlements=None):
        cfg=self.config;events=[];start=time.perf_counter()
        if self.provider.universe_name!=cfg.universe:raise DataError("Provider universe/configuration mismatch")
        if book.config_id!=cfg.config_id:raise DataError("Book configuration hash mismatch")
        if book.last_asof and utc(asof)<=utc(book.last_asof):raise DataError("Duplicate or out-of-order decision snapshot")
        snapshot=self.provider.snapshot(asof)
        if utc(snapshot.asof)!=utc(asof) or snapshot.account_currency!=cfg.account_currency:raise DataError("Snapshot clock/account mismatch")
        used=[p["opportunity"]["underlying"] for p in book.positions]+[p["opportunity"]["underlying"] for p in book.pending]
        quotes=self.quotes(used,asof,events)
        before=copy.deepcopy(book.to_dict())
        book.accrue(snapshot,cfg)
        try:
            events.extend(book.apply_assignments(snapshot,cfg))
            events.extend(book.settle(snapshot,settlements or {},cfg))
            for pos in list(book.positions):
                if pos.get("assignment_unwind"):
                    events.append({"event":"fill",**book.close(pos,snapshot,quotes,cfg,"Assignment unwind")})
            events.extend(book.unwind_inventory(snapshot,cfg))
            book.mark(snapshot,quotes,cfg)
        except (DataError,KeyError,ValueError) as e:
            for k,v in before.items():setattr(book,k,v)
            book.emergency_stop("Position/settlement data inconsistent: "+str(e))
            events.append({"event":"data_blocked","reason":str(e)})
            return {"asof":asof,"status":"data_blocked","nav":None,"book":book.to_dict(),"events":events,"decisions":[],"source":"research" if book.mode=="research" else "observed paper","elapsed_seconds":time.perf_counter()-start}
        drawdown=1-book.nav/book.peak_nav if book.peak_nav>0 else 1
        if book.positions:
            exposures=book.risk_exposures(snapshot)
            if sum(e["risk"] for e in exposures)>cfg.risk.max_aggregate_loss*book.nav or any(e["risk"]>cfg.risk.max_position_loss*book.nav for e in exposures):book.emergency_stop("Defined-loss exposure exceeds current equity limits")
            for field,limit in (("sector",cfg.risk.max_sector_loss),("country",cfg.risk.max_country_loss)):
                for group in {e[field] for e in exposures}:
                    if sum(e["risk"] for e in exposures if e[field]==group)>limit*book.nav:book.emergency_stop("Portfolio concentration limit")
            for exposure in exposures:
                cluster=exposure["risk"]
                for other in exposures:
                    if other is exposure:continue
                    corr=self.provider.correlation(exposure["underlying"],other["underlying"],asof)
                    if corr is None:book.emergency_stop("Portfolio correlation data unavailable")
                    elif abs(corr)>=cfg.risk.max_correlation:cluster+=other["risk"]
                if cluster>cfg.risk.max_correlated_loss*book.nav:book.emergency_stop("Correlated portfolio loss limit")
            if sum(e["delta_notional"] for e in exposures)>cfg.risk.max_delta_notional*book.nav or sum(e["vega"] for e in exposures)>cfg.risk.max_vega_nav_per_point*book.nav or sum(e["gamma"] for e in exposures)>cfg.risk.max_gamma_nav_per_percent_squared*book.nav:book.emergency_stop("Greek exposure limit")
        if drawdown>=cfg.risk.emergency_drawdown:book.emergency_stop("Portfolio drawdown emergency stop")
        if not self.entry_permission(book,asof) and book.mode=="paper":book.emergency_stop("Configuration not approved for this paper clock")
        features=self.provider.features(asof,cfg.data.min_history)
        market=features.get(self.provider.panel.market)
        for pos in list(book.positions):
            op=Opportunity.from_dict(pos["opportunity"]);sc=cfg.strategies[op.strategy]
            pnl=pos["mark"]-pos["entry_cash"]
            held=(utc(asof)-utc(pos["opened_at"])).total_seconds()/86400
            reason=None
            if book.stopped:reason=book.stop_reason
            elif min(l.quote.dte(asof) for l in op.legs)<=sc.close_dte:reason="Expiration management"
            elif pnl>=sc.profit_take*op.max_profit*pos["contracts"]:reason="Profit target"
            elif pnl<=-sc.stop_loss*op.max_loss*pos["contracts"]:reason="Loss exit"
            elif held>=sc.max_hold_days:reason="Maximum holding period"
            else:
                spot=snapshot.spots.get(op.underlying)
                if spot:
                    op.feature["spot"]=spot.mid
                    try:reason=assignment_hazard(op,snapshot)
                    except DataError as e:reason=str(e)
            if reason:
                try:events.append({"event":"fill",**book.close(pos,snapshot,quotes,cfg,reason)})
                except DataError as e:book.emergency_stop(str(e));events.append({"event":"exit_rejected","position_id":pos["position_id"],"reason":str(e)})
        provisional=[]
        if not book.stopped and market:
            for intent in book.pending:
                try:
                    if utc(asof)>utc(intent["expires_at"]):raise DataError("Entry intent expired")
                    op=self.refresh(intent["opportunity"],features,market,snapshot,quotes,book.mode)
                    decision=size(op,book,snapshot,self.provider,cfg)
                    count=min(intent["contracts"],decision.contracts)
                    if count<=0:raise DataError(decision.reason)
                    events.append({"event":"risk_at_fill","order_id":intent["order_id"],**decision.calculation})
                    fill=book.fill(intent,op,count,snapshot,cfg)
                    if fill:events.append({"event":"fill",**fill})
                except (DataError,KeyError,ValueError) as e:events.append({"event":"entry_rejected","order_id":intent["order_id"],"reason":str(e)})
        elif book.pending:events.append({"event":"pending_cancelled","reason":"Stop or benchmark unavailable"})
        book.pending=[]
        book.mark(snapshot,quotes,cfg)
        candidates=[];signals=[]
        for u in self.provider.universe:
            f=features.get(u)
            reason=None
            if not f:reason="Insufficient/invalid history"
            elif not f["tradable"]:reason="Underlying not tradable"
            elif f["underlying_type"] not in ("stock","etf","index"):reason="Underlying requires a separate delivery/settlement adapter"
            elif f["observations"]<cfg.data.min_observations:reason="Insufficient observed bars"
            elif (utc(asof)-utc(f["available_at"])).total_seconds()>cfg.data.max_bar_age_seconds:reason="Stale underlying history"
            elif f["currency"] not in snapshot.fx:reason="Missing FX"
            elif f["traded_value"]*snapshot.conversion(f["currency"])<cfg.data.min_underlying_dollar_volume:reason="Underlying liquidity"
            elif book.stopped:reason="Emergency stop"
            elif market is None:reason="Benchmark missing"
            try:
                estimate=forecast(f,cfg,asof) if reason is None else None
            except DataError as e:reason=str(e);estimate=None
            signal={"underlying":u,"reason":reason,"features":f,"forecast":estimate}
            signals.append(signal)
            if reason is None:
                strength=abs(f["momentum63"])/max(f["volatility63"],0.01)
                candidates.append((strength,u,f,estimate))
        events.append({"event":"underlying_signals","asof":asof,"signals":signals})
        shortlist=sorted(candidates,key=lambda r:(-r[0],r[1]))[:cfg.data.shortlist]
        finalists=[]
        for candidate in shortlist:
            try:
                available=self.provider.has_chain(candidate[1],asof)
                if available is False:
                    events.append({"event":"underlying_rejected","underlying":candidate[1],"reason":"No point-in-time chain availability"})
                    continue
                finalists.append(candidate)
                if len(finalists)>=cfg.data.finalists:break
            except (DataError,KeyError,ValueError) as e:events.append({"event":"underlying_rejected","underlying":candidate[1],"reason":str(e)})
        opportunities=[]
        occupied={p["opportunity"]["underlying"] for p in book.positions}
        for strength,u,feature,estimate in finalists:
            if u in occupied:continue
            try:
                spot=snapshot.spots[u];spot.validate(asof,cfg.data.max_quote_age_seconds)
                if spot.currency!=feature["currency"]:raise DataError("History/spot currency mismatch")
                feature=dict(feature,spot=spot.mid)
                chain=self.filter_chain(self.provider.chain(u,asof),snapshot,book.mode,events)
                chain=[q for q in chain if q.currency==spot.currency]
                if not chain:raise DataError("No eligible historical option quotes")
                iv=sum(q.iv for q in chain)/len(chain)
                regime=classify(feature,market,iv,estimate,cfg)
                events.append({"event":"regime","underlying":u,"asof":asof,**regime})
                max_corr=0.0
                for pos in book.positions:
                    corr=self.provider.correlation(u,pos["opportunity"]["underlying"],asof)
                    if corr is None:raise DataError("Correlation history unavailable")
                    max_corr=max(max_corr,abs(corr))
                best=None
                for name in regime["strategies"]:
                    sc=cfg.strategies[name]
                    if not sc.enabled:continue
                    built=BUILDERS[name](chain,asof,feature,regime,sc)
                    if not built:events.append({"event":"opportunity_rejected","strategy":name,"underlying":u,"reason":"No coherent spread meets approved strike/delta/expiry targets"})
                    for op in built:
                        try:
                            measure(op,snapshot,cfg,max_corr)
                            op.rejection=op.rejection or assignment_hazard(op,snapshot)
                            events.append({"event":"opportunity","opportunity":op.to_dict(),"reason":op.rejection})
                            if not op.rejection and (best is None or op.score>best.score):best=op
                        except (DataError,ValueError) as e:events.append({"event":"opportunity_rejected","strategy":name,"underlying":u,"contracts":op.contract_ids,"reason":str(e)})
                if best:opportunities.append(best)
                else:events.append({"event":"underlying_rejected","underlying":u,"reason":"No eligible regime or structure passing approved edge/liquidity/assignment checks"})
            except (DataError,KeyError,ValueError) as e:events.append({"event":"underlying_rejected","underlying":u,"reason":str(e)})
        decisions=[]
        for op in sorted(opportunities,key=lambda o:(-o.score,o.underlying,o.strategy)):
            decision=size(op,book,snapshot,self.provider,cfg,provisional)
            events.append({"event":"risk_decision","underlying":op.underlying,"strategy":op.strategy,"reason":decision.reason,**decision.calculation})
            if decision.contracts<=0:continue
            order_id=hashlib.sha256((book.config_id+asof+op.strategy+":".join(op.contract_ids)).encode()).hexdigest()[:32]
            intent={"order_id":order_id,"created_at":asof,"expires_at":(utc(asof)+timedelta(days=3)).isoformat(),"contracts":decision.contracts,"opportunity":op.to_dict(),"risk":decision.calculation}
            decisions.append(intent);book.pending.append(intent)
            provisional.append(reservation(op,decision.contracts,snapshot))
            events.append({"event":"order_intent","intent":intent,"execution":"paper_next_snapshot"})
        book.last_asof=asof;book.last_rate=snapshot.annual_cash_rate
        return {"asof":asof,"status":"stopped" if book.stopped else "ok","nav":book.nav,"drawdown":drawdown,"book":book.to_dict(),"events":events,"decisions":decisions,
                "screening":{"universe":len(self.provider.universe),"valid":len(candidates),"shortlist":len(shortlist),"finalists":len(finalists),"approved_intents":len(decisions)},
                "source":"research" if book.mode=="research" else "observed paper","config_id":cfg.config_id,"elapsed_seconds":time.perf_counter()-start}

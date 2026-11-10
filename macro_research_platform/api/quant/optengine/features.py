from __future__ import annotations

from collections import OrderedDict
import numpy as np
import pandas as pd
from .schema import DataError, utc

class FeaturePanel:
    def __init__(self,close,volume,metadata=None,observed=None,market="SPY",cache_size=32):
        if not isinstance(close,pd.DataFrame) or not isinstance(close.index,pd.DatetimeIndex):raise DataError("Dated close matrix required")
        if close.index.tz is None:raise DataError("History needs available-at timestamps with timezone")
        if not close.index.is_unique or not close.index.is_monotonic_increasing or not close.columns.is_unique:raise DataError("History must be unique and ordered")
        if not close.index.equals(volume.index) or not close.columns.equals(volume.columns):raise DataError("Price/volume alignment mismatch")
        self.index=close.index.tz_convert("UTC")
        self.symbols=tuple(str(c) for c in close.columns)
        self.columns={s:i for i,s in enumerate(self.symbols)}
        self.close=close.to_numpy(float,copy=True)
        self.volume=volume.to_numpy(float,copy=True)
        self.observed=np.isfinite(self.close)&(self.close>0)&np.isfinite(self.volume)&(self.volume>0)
        if observed is not None:
            if not observed.index.equals(close.index) or not observed.columns.equals(close.columns):raise DataError("Observed mask alignment mismatch")
            self.observed &= observed.to_numpy(bool)
        self.metadata=metadata or {}
        self.market=market
        if market not in self.columns:raise DataError("Market benchmark history missing")
        self.cache=OrderedDict();self.cache_size=cache_size

    def features(self,asof,min_history=253):
        at=pd.Timestamp(utc(asof));end=int(self.index.searchsorted(at,side="right"))
        key=(end,min_history)
        if key in self.cache:
            self.cache.move_to_end(key);return self.cache[key]
        if end<min_history:return {}
        x=self.close[max(0,end-253):end]
        obs=self.observed[max(0,end-253):end]
        safe=np.where(obs,x,np.nan)
        with np.errstate(invalid="ignore",divide="ignore"):
            lr=np.diff(np.log(safe),axis=0)
            moms={k:np.log(safe[-1]/safe[-1-k]) for k in (21,63,252) if len(safe)>k}
            vols={k:np.nanstd(lr[-k:],axis=0,ddof=1)*np.sqrt(252) for k in (20,63,252)}
            daily_volume=np.nanmedian(np.where(obs[-20:],x[-20:]*self.volume[end-min(20,end):end],np.nan),axis=0)
            sma=np.nanmean(np.where(obs[-200:],x[-200:],np.nan),axis=0)
            dd=safe[-1]/np.nanmax(safe,axis=0)-1
        stamps=self.index[max(0,end-253):end].as_unit("ns").asi8
        last=np.max(np.where(obs,stamps[:,None],-1),axis=0)
        market_mom=float(moms.get(63,np.full(len(self.symbols),np.nan))[self.columns[self.market]])
        vol_counts={k:np.isfinite(lr[-k:]).sum(axis=0) for k in (20,63,252)}
        result={}
        for i,u in enumerate(self.symbols):
            if any(vol_counts[k][i]<max(10,int(.8*k)) for k in (20,63,252)):continue
            values=[safe[-1,i],sma[i],dd[i],market_mom,daily_volume[i]]+[vols[k][i] for k in (20,63,252)]+[moms[k][i] for k in (21,63,252) if k in moms]
            if len(moms)!=3 or not np.isfinite(values).all() or last[i]<0:continue
            meta=self.metadata.get(u,{})
            if meta.get("available_at") is None or pd.Timestamp(utc(meta["available_at"]))>at:meta={"currency":meta.get("currency"),"tradable":meta.get("tradable",True)}
            result[u]={"underlying":u,"price":float(safe[-1,i]),"sma200":float(sma[i]),"drawdown":float(dd[i]),
                       "momentum21":float(moms[21][i]),"momentum63":float(moms[63][i]),"momentum252":float(moms[252][i]),
                       "market_momentum63":market_mom,"volatility20":float(vols[20][i]),"volatility63":float(vols[63][i]),"volatility252":float(vols[252][i]),
                       "traded_value":float(daily_volume[i]),"observations":int(obs[:,i].sum()),
                       "available_at":pd.Timestamp(last[i],tz="UTC").isoformat(),"currency":meta.get("currency"),
                       "sector":meta.get("sector") or "UNKNOWN","country":meta.get("country") or "UNKNOWN",
                       "tradable":bool(meta.get("tradable",True)),"underlying_type":meta.get("underlying_type","stock"),"source":"observed_underlying"}
        self.cache[key]=result
        while len(self.cache)>self.cache_size:self.cache.popitem(last=False)
        return result

    def correlation(self,a,b,asof):
        if a==b:return 1.0
        if a not in self.columns or b not in self.columns:return None
        end=int(self.index.searchsorted(pd.Timestamp(utc(asof)),side="right"))
        if end<64:return None
        x=self.close[max(0,end-64):end][:,[self.columns[a],self.columns[b]]]
        obs=self.observed[max(0,end-64):end][:,[self.columns[a],self.columns[b]]]
        with np.errstate(invalid="ignore",divide="ignore"):r=np.diff(np.log(x),axis=0)
        ok=np.isfinite(r).all(axis=1)&obs[1:].all(axis=1)&obs[:-1].all(axis=1)
        if ok.sum()<30 or np.min(np.std(r[ok],axis=0))<=0:return None
        return float(np.corrcoef(r[ok].T)[0,1])

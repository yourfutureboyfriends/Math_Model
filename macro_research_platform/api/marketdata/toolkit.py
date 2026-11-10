"""
Analysis tools on free data:

  technicals(sym)   TECH — moving averages, RSI, MACD, Bollinger, ATR, ADX, stochastics; a vote summary;
                           trend state; support / resistance (pivots, swing levels, 52-week range); and how
                           each classic signal has actually worked on THIS stock over ten years
  spread(a, b)      SPRD — pairs analysis: hedge ratio, spread z-score, Engle–Granger cointegration,
                           mean-reversion half-life, rolling correlation, and an out-of-sample z-score backtest
  central_banks()   CBRT — policy rates of ~40 central banks (BIS): level, last move, 12-month path
  fred_search(q)    ECOS — search FRED's ~800k economic series
  fred_series(id)   ECOS — one FRED series with its metadata
"""
from __future__ import annotations
from api.market_dates import weekly_last

import io
import logging
import math
import os
from datetime import date, timedelta
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from api.marketdata.core import NotFound, Upstream, _cached, _info, yahoo_call

logger = logging.getLogger(__name__)


def _history(symbol: str, period: str = "10y") -> pd.DataFrame:
    import yfinance as yf

    def fetch():
        df = yahoo_call(lambda: yf.Ticker(symbol).history(period=period, auto_adjust=True))
        if df is None or df.empty:
            raise NotFound(f"No price history for {symbol}.")
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        return _stitch_quote(symbol, df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]))
    return _cached(f"tkhist:{symbol}:{period}", 1800, fetch)


def _stitch_quote(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    """Append the latest session from the quote when the daily history is a session behind (Yahoo's long daily
    histories omit the latest completed Tokyo / Hong Kong session for hours after the close), so indicators use the
    same last price as the quote screen."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from api.marketdata.core import _info
        i = _info(symbol)
        px, t = i.get("regularMarketPrice"), i.get("regularMarketTime")
        if not px or not t or df.empty:
            return df
        tz = ZoneInfo(i.get("exchangeTimezoneName") or "UTC")
        day = pd.Timestamp(datetime.fromtimestamp(int(t), tz).date())
        if day <= df.index[-1] or day.dayofweek >= 5:
            return df
        row = pd.DataFrame({"Open": [i.get("regularMarketOpen") or px], "High": [i.get("regularMarketDayHigh") or px],
                            "Low": [i.get("regularMarketDayLow") or px], "Close": [px],
                            "Volume": [i.get("regularMarketVolume") or 0]}, index=[day])
        return pd.concat([df, row])
    except Exception:                                    # a stitch must never break the history
        return df


# ── TECH ─────────────────────────────────────────────────────────────────────
def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _adx(df: pd.DataFrame, n: int = 14):
    h, l = df["High"], df["Low"]
    upm, dnm = h.diff(), -l.diff()
    pdm = upm.where((upm > dnm) & (upm > 0), 0.0)
    ndm = dnm.where((dnm > upm) & (dnm > 0), 0.0)
    atr = _atr(df, n)
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False).mean() / atr
    ndi = 100 * ndm.ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, ndi


def _signal_stats(c: pd.Series, mask: pd.Series, horizons=(20, 60)) -> Dict[str, Any]:
    """Forward returns after each occurrence (occurrences within 10 days of the last are skipped so
    one episode isn't counted ten times), against all days as the baseline."""
    idx = np.flatnonzero(mask.fillna(False).values)
    picked, last = [], -10_000
    for i in idx:
        if i - last >= 10:
            picked.append(i)
            last = i
    out: Dict[str, Any] = {"count": len(picked), "last": c.index[picked[-1]].strftime("%Y-%m-%d") if picked else None}
    vals = c.values
    for h in horizons:
        fwd = [vals[i + h] / vals[i] - 1 for i in picked if i + h < len(vals)]
        base = vals[h:] / vals[:-h] - 1 if len(vals) > h else np.array([])
        out[f"avg_{h}d"] = float(np.mean(fwd)) if fwd else None
        out[f"hit_{h}d"] = float(np.mean([x > 0 for x in fwd])) if fwd else None
        out[f"n_{h}d"] = len(fwd)
        out[f"base_{h}d"] = float(np.mean(base)) if len(base) else None
        out[f"base_hit_{h}d"] = float(np.mean(base > 0)) if len(base) else None
    return out


def _swing_levels(df: pd.DataFrame, price: float, atr: float) -> List[Dict[str, Any]]:
    """Swing highs / lows (5-bar fractals) over the last year, clustered within half an ATR;
    a level touched more often is stronger."""
    d = df.iloc[-260:]
    h, l = d["High"].values, d["Low"].values
    pts = []
    for i in range(2, len(d) - 2):
        if h[i] == max(h[i - 2:i + 3]):
            pts.append((float(h[i]), d.index[i]))
        if l[i] == min(l[i - 2:i + 3]):
            pts.append((float(l[i]), d.index[i]))
    pts.sort()
    clusters: List[List] = []
    for v, t in pts:
        if clusters and abs(v - np.mean([x for x, _ in clusters[-1]])) <= 0.5 * atr:
            clusters[-1].append((v, t))
        else:
            clusters.append([(v, t)])
    lv = [{"level": float(np.mean([x for x, _ in c])), "touches": len(c), "last": max(t for _, t in c).strftime("%Y-%m-%d")} for c in clusters]
    sup = sorted([x for x in lv if x["level"] < price], key=lambda x: -x["level"])[:3]
    res = sorted([x for x in lv if x["level"] > price], key=lambda x: x["level"])[:3]
    return [{**x, "kind": "support"} for x in sup] + [{**x, "kind": "resistance"} for x in res]


def technicals(symbol: str) -> Dict[str, Any]:
    """Technical indicators of a security with an overall buy / sell / neutral tally and score."""
    s = symbol.strip().upper()

    def build():
        df = _history(s, "10y")
        if len(df) < 220:
            raise NotFound(f"Not enough history for {s} (needs about a year).")
        c = df["Close"]
        sma = {n: c.rolling(n).mean() for n in (20, 50, 100, 200)}
        ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        sig = macd.ewm(span=9, adjust=False).mean()
        rsi = _rsi(c)
        mid, sd = sma[20], c.rolling(20).std()
        bb_up, bb_lo = mid + 2 * sd, mid - 2 * sd
        atr = _atr(df)
        adx, pdi, ndi = _adx(df)
        ll, hh = df["Low"].rolling(14).min(), df["High"].rolling(14).max()
        stoch_k = 100 * (c - ll) / (hh - ll).replace(0, np.nan)
        stoch_d = stoch_k.rolling(3).mean()
        willr = -100 * (hh - c) / (hh - ll).replace(0, np.nan)
        tp = (df["High"] + df["Low"] + c) / 3
        cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True))
        roc = c.pct_change(12) * 100
        obv = (np.sign(c.diff()).fillna(0) * df["Volume"]).cumsum()
        px = float(c.iloc[-1])
        last = lambda x: float(x.iloc[-1]) if pd.notna(x.iloc[-1]) else None

        osc = []
        def vote(name, value, buy, sell, detail):
            osc.append({"name": name, "value": value, "signal": "buy" if buy else "sell" if sell else "neutral", "detail": detail})
        r = last(rsi)
        vote("RSI (14)", r, r is not None and r < 30, r is not None and r > 70, "below 30 oversold, above 70 overbought")
        k, dd = last(stoch_k), last(stoch_d)
        vote("Stochastic %K (14, 3)", k, k is not None and dd is not None and k < 20 and k > dd, k is not None and dd is not None and k > 80 and k < dd, "below 20 and turning up / above 80 and turning down")
        cc = last(cci)
        vote("CCI (20)", cc, cc is not None and cc < -100, cc is not None and cc > 100, "below −100 / above +100")
        m, sg = last(macd), last(sig)
        vote("MACD (12, 26, 9)", m, m is not None and sg is not None and m > sg, m is not None and sg is not None and m < sg, "MACD above / below its signal line")
        w = last(willr)
        vote("Williams %R (14)", w, w is not None and w < -80, w is not None and w > -20, "below −80 / above −20")
        ro = last(roc)
        vote("Momentum (12-day ROC)", ro, ro is not None and ro > 0, ro is not None and ro < 0, "rising / falling over 12 days")
        a, p_, n_ = last(adx), last(pdi), last(ndi)
        vote("ADX (14) direction", a, a is not None and a > 20 and p_ > n_, a is not None and a > 20 and n_ > p_, "trend strength above 20, direction from +DI / −DI")
        ma = []
        for n in (20, 50, 100, 200):
            v = last(sma[n])
            ma.append({"name": f"SMA {n}", "value": v, "signal": "buy" if v and px > v else "sell" if v else "neutral", "distance": px / v - 1 if v else None})
        for n, e in ((12, ema12), (26, ema26)):
            v = last(e)
            ma.append({"name": f"EMA {n}", "value": v, "signal": "buy" if px > v else "sell", "distance": px / v - 1})

        def summary(rows):
            b = sum(r_["signal"] == "buy" for r_ in rows)
            s_ = sum(r_["signal"] == "sell" for r_ in rows)
            score = (b - s_) / max(1, len(rows))
            label = "Strong buy" if score >= 0.5 else "Buy" if score >= 0.1 else "Strong sell" if score <= -0.5 else "Sell" if score <= -0.1 else "Neutral"
            return {"label": label, "buy": b, "sell": s_, "neutral": len(rows) - b - s_, "score": score}
        s50, s200 = sma[50], sma[200]
        cross = (s50 > s200).astype(int).diff()
        gc = cross[cross == 1].index
        dcx = cross[cross == -1].index
        trend = ("uptrend" if px > last(s200) and last(s50) > last(s200) else "downtrend" if px < last(s200) and last(s50) < last(s200) else "mixed")
        atr_v = last(atr)
        # classic floor pivots from the last full day
        H, L, C = float(df["High"].iloc[-1]), float(df["Low"].iloc[-1]), px
        P = (H + L + C) / 3
        pivots = {"P": P, "R1": 2 * P - L, "S1": 2 * P - H, "R2": P + (H - L), "S2": P - (H - L)}
        yr = df.iloc[-252:]
        # does each signal work on this stock?
        rsi_x_up = (rsi > 30) & (rsi.shift() <= 30)
        rsi_x_dn = (rsi < 70) & (rsi.shift() >= 70)
        macd_up = (macd > sig) & (macd.shift() <= sig.shift())
        gold = (s50 > s200) & (s50.shift() <= s200.shift())
        death = (s50 < s200) & (s50.shift() >= s200.shift())
        bb_touch = (c < bb_lo)
        above200 = (c > s200) & (c.shift() <= s200.shift())
        new_high = c >= c.rolling(252).max()
        studies = [("RSI crosses back above 30", rsi_x_up), ("RSI falls back below 70", rsi_x_dn), ("MACD crosses above signal", macd_up),
                   ("Golden cross (50 over 200)", gold), ("Death cross (50 under 200)", death), ("Close below lower Bollinger band", bb_touch),
                   ("Close crosses above 200-day", above200), ("New 52-week high", new_high)]
        study = [{"signal": n, **_signal_stats(c, m_)} for n, m_ in studies]
        tail = df.iloc[-260:]
        chart = [{"date": d.strftime("%Y-%m-%d"), "close": round(float(tail["Close"].iloc[i]), 4),
                  "sma50": _r(s50, d), "sma200": _r(s200, d), "bb_up": _r(bb_up, d), "bb_lo": _r(bb_lo, d),
                  "rsi": _r(rsi, d, 2), "macd": _r(macd, d), "signal": _r(sig, d), "hist": _r(macd - sig, d)}
                 for i, d in enumerate(tail.index)]
        info = {}
        try:
            info = _info(s)
        except Exception:
            pass
        vol20 = float(np.log(c).diff().iloc[-20:].std() * math.sqrt(252))
        return {"symbol": s, "name": info.get("longName") or info.get("shortName"), "currency": info.get("currency"), "price": px,
                "date": c.index[-1].strftime("%Y-%m-%d"),
                "summary": {"oscillators": summary(osc), "moving_averages": summary(ma), "overall": summary(osc + ma)},
                "oscillators": osc, "moving_averages": ma,
                "trend": {"state": trend, "adx": a, "last_golden_cross": gc[-1].strftime("%Y-%m-%d") if len(gc) else None,
                          "last_death_cross": dcx[-1].strftime("%Y-%m-%d") if len(dcx) else None,
                          "above_200d": px > last(s200), "pct_from_200d": px / last(s200) - 1},
                "levels": {"swings": _swing_levels(df, px, atr_v or px * 0.02), "pivots": pivots,
                           "high_52w": float(yr["High"].max()), "low_52w": float(yr["Low"].min()),
                           "from_high": px / float(yr["High"].max()) - 1, "from_low": px / float(yr["Low"].min()) - 1,
                           "atr": atr_v, "atr_pct": atr_v / px if atr_v else None,
                           "stop_long_2atr": px - 2 * atr_v if atr_v else None, "stop_short_2atr": px + 2 * atr_v if atr_v else None},
                "bollinger": {"upper": last(bb_up), "lower": last(bb_lo), "pct_b": (px - last(bb_lo)) / (last(bb_up) - last(bb_lo)) if last(bb_up) and last(bb_up) != last(bb_lo) else None,
                              "bandwidth": (last(bb_up) - last(bb_lo)) / last(sma[20]) if last(sma[20]) else None},
                "volume": {"obv_trend_20d": "rising" if obv.iloc[-1] > obv.iloc[-21] else "falling",
                           "rel_volume": float(df["Volume"].iloc[-1] / df["Volume"].iloc[-21:-1].mean()) if df["Volume"].iloc[-21:-1].mean() else None},
                "realized_vol_20d": vol20, "study": study, "study_years": round(len(c) / 252, 1), "chart": chart,
                "note": "Signals vote buy / sell / neutral by their textbook rules; the summary is the balance of votes. The study "
                        "shows what actually followed each signal on this stock (10 years, adjusted closes), against an average day — "
                        "most signals are close to coin flips, which is worth knowing before acting on one.",
                "source": "Yahoo Finance daily prices (adjusted)"}
    return _cached(f"tech:{s}", 900, build)


def _r(series: pd.Series, d, nd: int = 4):
    v = series.get(d)
    return round(float(v), nd) if v is not None and pd.notna(v) else None


# ── SPRD ─────────────────────────────────────────────────────────────────────
def spread(a: str, b: str, years: int = 5, entry: float = 2.0, exit_: float = 0.5) -> Dict[str, Any]:
    """A pair-spread study: hedge ratio, z-score and a mean-reversion backtest with entry / exit thresholds."""
    A, B = a.strip().upper(), b.strip().upper()
    if A == B:
        raise NotFound("Pick two different instruments.")

    def build():
        from statsmodels.tsa.stattools import coint
        pa, pb = _history(A, "10y")["Close"], _history(B, "10y")["Close"]
        df = pd.concat([pa.rename("a"), pb.rename("b")], axis=1).dropna()
        df = df[df.index >= df.index[-1] - pd.Timedelta(days=int(365.25 * years))]
        if len(df) < 250:
            raise NotFound("Not enough overlapping history (needs a year).")
        la, lb = np.log(df["a"]), np.log(df["b"])
        beta, alpha = np.polyfit(lb, la, 1)
        resid = la - (alpha + beta * lb)
        z_full = (resid - resid.mean()) / resid.std()
        try:
            t, p, _ = coint(la, lb)
        except Exception:
            t, p = None, None
        ds, lag = resid.diff().dropna(), resid.shift().dropna()
        lag = lag.loc[ds.index]
        k = np.polyfit(lag - lag.mean(), ds, 1)[0]
        half_life = float(-math.log(2) / k) if k < 0 else None
        ratio = df["a"] / df["b"]
        ra, rb = df["a"].pct_change(), df["b"].pct_change()
        corr60 = ra.rolling(60).corr(rb)
        # out-of-sample backtest: hedge ratio from the previous year only, z from the last 60 days
        W, Z = 252, 60
        rb_beta = la.rolling(W).cov(lb) / lb.rolling(W).var()
        sp = la - rb_beta.shift() * lb
        z = (sp - sp.rolling(Z).mean()) / sp.rolling(Z).std()
        pos, trades, cur = 0, [], None
        pnl = []
        for i in range(1, len(df)):
            zi = z.iloc[i - 1]
            bi = rb_beta.shift().iloc[i - 1]
            day = 0.0
            if pos and pd.notna(bi):
                day = pos * (ra.iloc[i] - bi * rb.iloc[i]) / (1 + abs(bi))
            pnl.append(day)
            if pd.isna(zi) or pd.isna(bi):
                continue
            if pos == 0 and abs(zi) >= entry:
                pos = -1 if zi > 0 else 1                    # spread rich → short A / long B
                cur = {"open": df.index[i].strftime("%Y-%m-%d"), "z": float(zi), "side": "short A / long B" if pos < 0 else "long A / short B", "ret": 0.0}
            elif pos and (abs(zi) <= exit_ or abs(zi) >= 4.0 or (cur and (df.index[i] - pd.Timestamp(cur["open"])).days > 180)):
                cur["close"] = df.index[i].strftime("%Y-%m-%d")
                cur["reason"] = "reverted" if abs(zi) <= exit_ else "stop (|z| ≥ 4)" if abs(zi) >= 4 else "time stop (6 months)"
                trades.append(cur)
                pos, cur = 0, None
            if cur is not None:
                cur["ret"] = (1 + cur["ret"]) * (1 + day) - 1
        eq = (1 + pd.Series(pnl, index=df.index[1:])).cumprod()
        yrs = len(eq) / 252
        sd = float(pd.Series(pnl).std() * math.sqrt(252))
        bt = {"trades": len(trades), "win_rate": float(np.mean([t_["ret"] > 0 for t_ in trades])) if trades else None,
              "total_return": float(eq.iloc[-1] - 1), "cagr": float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 and eq.iloc[-1] > 0 else None,
              "vol": sd, "max_drawdown": float((eq / eq.cummax() - 1).min()), "open": cur, "recent": trades[-8:][::-1],
              "rules": f"Enter when the 60-day z-score of the spread passes ±{entry:g} (hedge ratio from the previous 252 days only — "
                       f"no look-ahead), exit at ±{exit_:g}, stop at ±4 or after six months. Returns per $1 gross, before costs."}
        step = max(1, len(df) // 600)
        rows = [{"date": d.strftime("%Y-%m-%d"), "a": round(float(df["a"].iloc[i] / df["a"].iloc[0] * 100), 3),
                 "b": round(float(df["b"].iloc[i] / df["b"].iloc[0] * 100), 3), "ratio": round(float(ratio.iloc[i]), 6),
                 "z": round(float(z.iloc[i]), 3) if pd.notna(z.iloc[i]) else None, "z_full": round(float(z_full.iloc[i]), 3),
                 "corr60": round(float(corr60.iloc[i]), 3) if pd.notna(corr60.iloc[i]) else None,
                 "equity": round(float(eq.iloc[i - 1]) * 100, 3) if i >= 1 else 100.0}
                for i, d in enumerate(df.index) if i % step == 0 or i == len(df) - 1]
        ia, ib = {}, {}
        try:
            ia, ib = _info(A), _info(B)
        except Exception:
            pass
        verdict = ("cointegrated — the spread has tended to revert" if p is not None and p < 0.05 else
                   "weak evidence of cointegration" if p is not None and p < 0.10 else
                   "not cointegrated — the spread can drift indefinitely; treat z-scores with care")
        return {"a": A, "b": B, "name_a": ia.get("shortName") or A, "name_b": ib.get("shortName") or B,
                "currency_a": ia.get("currency"), "currency_b": ib.get("currency"), "start": df.index[0].strftime("%Y-%m-%d"),
                "hedge_ratio": float(beta), "coint_p": float(p) if p is not None else None, "coint_t": float(t) if t is not None else None,
                "verdict": verdict, "half_life_days": half_life, "z_now": float(z.iloc[-1]) if pd.notna(z.iloc[-1]) else None,
                "z_full_now": float(z_full.iloc[-1]), "ratio_now": float(ratio.iloc[-1]),
                "ratio_percentile": float((ratio < ratio.iloc[-1]).mean()), "corr_now": float(corr60.iloc[-1]) if pd.notna(corr60.iloc[-1]) else None,
                "corr_full": float(ra.corr(rb)), "return_a": float(df["a"].iloc[-1] / df["a"].iloc[0] - 1),
                "return_b": float(df["b"].iloc[-1] / df["b"].iloc[0] - 1), "backtest": bt, "rows": rows,
                "note": "Log-price regression of A on B gives the hedge ratio; the Engle–Granger test asks whether the residual "
                        "spread is stationary; half-life from an AR(1) fit of the spread." +
                        (f" Different currencies ({ia.get('currency')} / {ib.get('currency')}): FX moves are part of the spread."
                         if ia.get("currency") and ib.get("currency") and ia.get("currency") != ib.get("currency") else ""),
                "source": "Yahoo Finance (adjusted closes)"}
    return _cached(f"sprd:{A}:{B}:{years}:{entry}:{exit_}", 1800, build)


# ── CBRT ─────────────────────────────────────────────────────────────────────
CB_NAMES = {
    "US": ("United States", "Federal Reserve"), "XM": ("Euro area", "ECB"), "GB": ("United Kingdom", "Bank of England"),
    "JP": ("Japan", "Bank of Japan"), "CN": ("China", "People's Bank of China"), "CA": ("Canada", "Bank of Canada"),
    "AU": ("Australia", "Reserve Bank of Australia"), "CH": ("Switzerland", "Swiss National Bank"), "SE": ("Sweden", "Riksbank"),
    "NO": ("Norway", "Norges Bank"), "DK": ("Denmark", "Danmarks Nationalbank"), "NZ": ("New Zealand", "Reserve Bank of NZ"),
    "IN": ("India", "Reserve Bank of India"), "BR": ("Brazil", "Banco Central do Brasil"), "MX": ("Mexico", "Banxico"),
    "KR": ("South Korea", "Bank of Korea"), "ZA": ("South Africa", "SARB"), "RU": ("Russia", "Bank of Russia"),
    "TR": ("Türkiye", "CBRT"), "ID": ("Indonesia", "Bank Indonesia"), "PL": ("Poland", "NBP"), "CZ": ("Czechia", "CNB"),
    "HU": ("Hungary", "MNB"), "IL": ("Israel", "Bank of Israel"), "CL": ("Chile", "Banco Central de Chile"), "CO": ("Colombia", "BanRep"),
    "PE": ("Peru", "BCRP"), "AR": ("Argentina", "BCRA"), "SA": ("Saudi Arabia", "SAMA"), "TH": ("Thailand", "Bank of Thailand"),
    "MY": ("Malaysia", "Bank Negara"), "PH": ("Philippines", "BSP"), "HK": ("Hong Kong", "HKMA"), "IS": ("Iceland", "Central Bank of Iceland"),
    "RO": ("Romania", "NBR"), "RS": ("Serbia", "NBS"), "MK": ("North Macedonia", "NBRNM"), "HR": ("Croatia", "HNB"), "BG": ("Bulgaria", "BNB"),
    "CY": ("Cyprus", "CBC"), "KW": ("Kuwait", "Central Bank of Kuwait"), "MA": ("Morocco", "Bank Al-Maghrib"),
    "AE": ("United Arab Emirates", "CBUAE"), "QA": ("Qatar", "QCB"), "EG": ("Egypt", "Central Bank of Egypt"),
    "NG": ("Nigeria", "CBN"), "VN": ("Vietnam", "SBV"), "TW": ("Taiwan", "CBC Taiwan"), "UA": ("Ukraine", "NBU"),
}
# A series that has stopped updating is a bank that no longer sets policy (Croatia joined the euro in 2023) or a
# broken feed — not a current rate. Older than this, it is left out of the table and the breadth counts.
CB_STALE_DAYS = 120


def central_banks() -> Dict[str, Any]:
    """Policy rates of central banks worldwide (BIS) with recent changes."""
    def build():
        import requests
        r = requests.get("https://stats.bis.org/api/v1/data/WS_CBPOL/D./all",
                         params={"startPeriod": (date.today() - timedelta(days=365 * 6)).isoformat(), "detail": "dataonly"},
                         headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0", "User-Agent": "Mozilla/5.0"}, timeout=90)
        if r.status_code != 200:
            raise Upstream(f"BIS policy-rate data unavailable (HTTP {r.status_code}).")
        df = pd.read_csv(io.StringIO(r.text), usecols=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"])
        df["TIME_PERIOD"] = pd.to_datetime(df["TIME_PERIOD"])
        out, hist = [], {}
        for area, g in df.groupby("REF_AREA"):
            sr = g.set_index("TIME_PERIOD")["OBS_VALUE"].astype(float).sort_index().dropna()
            if sr.empty:
                continue
            if (pd.Timestamp(date.today()) - sr.index[-1]).days > CB_STALE_DAYS:
                logger.info("[cbrt] %s left out: last observation %s", area, sr.index[-1].date())
                continue
            last = float(sr.iloc[-1])
            chg = sr[sr.diff().abs() > 1e-9]
            last_move = chg.index[-1] if len(chg) else None
            prev = float(sr[sr.index < last_move].iloc[-1]) if last_move is not None and len(sr[sr.index < last_move]) else None
            y1 = sr[sr.index <= sr.index[-1] - pd.Timedelta(days=365)]
            moves12 = sr[sr.index > sr.index[-1] - pd.Timedelta(days=365)].diff()
            name, bank = CB_NAMES.get(area, (area, area))
            out.append({"code": area, "country": name, "bank": bank, "rate": last, "as_of": sr.index[-1].strftime("%Y-%m-%d"),
                        "last_move": last_move.strftime("%Y-%m-%d") if last_move is not None else None,
                        "last_change_bp": (last - prev) * 100 if prev is not None else None,
                        "change_1y_bp": (last - float(y1.iloc[-1])) * 100 if len(y1) else None,
                        "hikes_12m": int((moves12 > 1e-9).sum()), "cuts_12m": int((moves12 < -1e-9).sum()),
                        "peak_6y": float(sr.max()), "trough_6y": float(sr.min())})
            wk = weekly_last(sr).dropna()
            hist[area] = wk
        H = pd.DataFrame(hist)
        rows = [{"date": d.strftime("%Y-%m-%d"), **{k: (round(float(v), 3) if pd.notna(v) else None) for k, v in r_.items()}} for d, r_ in H.iterrows()]
        out.sort(key=lambda x: -(x["rate"] or 0))
        easing = sum(1 for x in out if (x["change_1y_bp"] or 0) < 0)
        tightening = sum(1 for x in out if (x["change_1y_bp"] or 0) > 0)
        recent = sorted([x for x in out if x["last_move"]], key=lambda x: x["last_move"], reverse=True)[:10]
        return {"banks": out, "history": rows, "easing_1y": easing, "tightening_1y": tightening, "unchanged_1y": len(out) - easing - tightening,
                "recent_moves": recent, "source": "BIS central bank policy rates (daily)",
                "note": "Policy rate as published by each central bank, compiled by the BIS. The breadth count — how many banks cut vs "
                        "hiked over the year — is a classic gauge of the global monetary cycle."}
    return _cached("cbrt", 6 * 3600, build)


# ── ECOS: FRED explorer ──────────────────────────────────────────────────────
def _fred_key() -> str:
    key = os.getenv("FRED_API_KEY") or ""
    if not key:
        raise Upstream("FRED_API_KEY isn't set on the server — add a free key to .env to search FRED.")
    return key


def fred_search(q: str, limit: int = 40) -> Dict[str, Any]:
    """Search FRED series."""
    q = q.strip()
    if len(q) < 2:
        return {"results": []}

    def build():
        import requests
        r = requests.get("https://api.stlouisfed.org/fred/series/search",
                         params={"search_text": q, "api_key": _fred_key(), "file_type": "json", "limit": limit,
                                 "order_by": "popularity", "sort_order": "desc"}, timeout=30)
        if r.status_code != 200:
            raise Upstream(f"FRED search failed (HTTP {r.status_code}).")
        res = []
        for x in r.json().get("seriess", []):
            res.append({"id": x["id"], "title": x["title"], "frequency": x.get("frequency_short"), "units": x.get("units_short"),
                        "sa": x.get("seasonal_adjustment_short"), "start": x.get("observation_start"), "end": x.get("observation_end"),
                        "updated": (x.get("last_updated") or "")[:10], "popularity": x.get("popularity")})
        # a series whose data stopped well over a year ago is discontinued — keep it, but below the live ones
        cutoff = (date.today() - timedelta(days=500)).isoformat()
        for x in res:
            x["active"] = (x.get("end") or "") >= cutoff
        res.sort(key=lambda x: not x["active"])                  # stable: popularity order kept within each group
        return {"query": q, "results": res}
    return _cached(f"fredsearch2:{q.lower()}:{limit}", 6 * 3600, build)


def fred_series(sid: str) -> Dict[str, Any]:
    """One FRED series' observations and metadata."""
    sid = sid.strip().upper()
    if not sid.replace("_", "").isalnum():
        raise NotFound("Not a FRED series id.")

    def build():
        import requests
        if not os.getenv("FRED_API_KEY"):
            # no key: FRED's public CSV download still serves the data (without the metadata)
            from api.marketdata.insights import _fred
            d = _fred(sid, years=120)
            if not d:
                raise NotFound(f"FRED has no series {sid}.")
            return {"id": sid, "title": sid, "units": "", "frequency": None, "frequency_short": None, "sa": None, "notes": "",
                    "updated": None, "rows": [{"date": k, "value": v} for k, v in sorted(d.items())], "source": "FRED, Federal Reserve Bank of St. Louis"}
        key = _fred_key()
        meta = requests.get("https://api.stlouisfed.org/fred/series", params={"series_id": sid, "api_key": key, "file_type": "json"}, timeout=30)
        if meta.status_code == 400:
            raise NotFound(f"FRED has no series {sid}.")
        if meta.status_code != 200:
            raise Upstream(f"FRED unavailable (HTTP {meta.status_code}).")
        m = (meta.json().get("seriess") or [{}])[0]
        obs = requests.get("https://api.stlouisfed.org/fred/series/observations",
                           params={"series_id": sid, "api_key": key, "file_type": "json"}, timeout=60)
        if obs.status_code != 200:
            raise Upstream(f"FRED observations unavailable (HTTP {obs.status_code}).")
        rows = [{"date": o["date"], "value": float(o["value"])} for o in obs.json().get("observations", []) if o.get("value") not in (".", None, "")]
        if not rows:
            raise NotFound(f"{sid} has no observations.")
        return {"id": sid, "title": m.get("title"), "units": m.get("units"), "frequency": m.get("frequency"),
                "frequency_short": m.get("frequency_short"), "sa": m.get("seasonal_adjustment"), "notes": (m.get("notes") or "")[:2000],
                "updated": m.get("last_updated"), "rows": rows, "source": "FRED, Federal Reserve Bank of St. Louis"}
    return _cached(f"fredseries:{sid}", 6 * 3600, build)

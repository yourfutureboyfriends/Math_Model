"""13F point-in-time strategies, multi-manager pod rules and the factor lens — offline."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codeserver, library, smartmoney as sm


def _f(cik, period, filed, top):
    return {"cik": cik, "period": period, "filed": filed, "total": 1.0, "n_positions": len(top),
            "top": [{"cusip": t, "issuer": t, "ticker": t, "weight": w, "value": w} for t, w in top]}


def test_13f_used_only_after_its_filing_date(monkeypatch):
    berk, viking = "1067983", "1103804"
    pn = [_f(berk, "2020-03-31", "2020-05-15", [("AAPL", 0.4), ("KO", 0.1)]),
          _f(berk, "2020-06-30", "2020-08-14", [("BAC", 0.5), ("AAPL", 0.3)]),
          _f(viking, "2020-06-30", "2020-08-14", [("BAC", 0.2), ("MSFT", 0.1)])]
    monkeypatch.setattr(sm, "panel", lambda: {"filings": pn})
    # 2020-08-14 is the filing date: not usable that day, usable from the next rebalance
    latest = sm._latest(pn, "2020-08-14", ("fundamental",))
    assert latest[berk]["period"] == "2020-03-31" and viking not in latest
    latest = sm._latest(pn, "2020-08-17", ("fundamental",))
    assert latest[berk]["period"] == "2020-06-30"
    W = sm.portfolio("consensus", n=2, start="2020-06-01")
    jun, sep = W.loc["2020-06-16"], W.loc["2020-09-16"]
    assert set(jun[jun > 0].index) == {"AAPL", "KO"}
    assert set(sep[sep > 0].index) == {"BAC", "AAPL"}          # BAC in two funds' top-10 ranks first


def test_stale_filers_drop_out(monkeypatch):
    pn = [_f("1067983", "2019-03-31", "2019-05-15", [("AAPL", 0.5)])]
    assert sm._latest(pn, "2020-06-01", ("fundamental",)) == {}


def test_signal_dates_are_mid_month():
    d = sm.signal_dates("2024-01-01")[:3]
    assert [x.day >= 16 for x in d] == [True] * 3 and len({x.month for x in d}) == 3


def _members(n=4, T=1500, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-02", periods=T)
    out = []
    for j in range(n):
        r = rng.normal(0.0003, 0.01, T)
        if j == 0:
            r[600:700] = -0.01                                      # a pod in a sustained losing streak
        out.append({"id": f"s{j}", "dates": [d.strftime("%Y-%m-%d") for d in idx], "returns": list(r)})
    return out, idx


def test_pod_rules_halve_close_and_rehire(monkeypatch):
    mem, idx = _members()
    monkeypatch.setattr(codeserver, "_index_series", lambda s, start: pd.Series(100 + np.arange(len(idx)) * 0.0, index=idx))
    book, events, _ = library._pods(mem, hedge=False, rules=True)
    kinds = [e["event"].split(" ")[0] for e in events if e["pod"] == "s0"]
    assert "capital" in kinds and "closed" in kinds and "re-hired" in kinds
    first_close = next(e for e in events if e["pod"] == "s0" and e["event"].startswith("closed"))
    rehire = next(e for e in events if e["pod"] == "s0" and e["event"] == "re-hired")
    assert (pd.Timestamp(rehire["date"]) - pd.Timestamp(first_close["date"])).days >= 170   # ≈126 trading days
    free, _, _ = library._pods(mem, hedge=False, rules=False)
    lo = idx[650]
    assert book.loc[lo:idx[700]].sum() > free.loc[lo:idx[700]].sum()          # the stop limited the damage


def test_factor_lens_recovers_a_known_beta(monkeypatch):
    idx = pd.bdate_range("2014-01-01", periods=1300)
    rng = np.random.default_rng(5)
    rets = {s: rng.normal(0.0003, 0.01, len(idx)) for s in ("SPY", "IEF", "HYG", "DBC", "EEM", "UUP", "TIP", "MTUM", "VLUE", "QUAL", "USMV", "IWM")}
    px = pd.DataFrame({s: 100 * np.cumprod(1 + r) for s, r in rets.items()}, index=idx)
    monkeypatch.setattr(codeserver.qdata, "panel", lambda syms, start=None, end=None: ({"close": px}, []))
    monkeypatch.setattr(codeserver, "rf_for", lambda dates: pd.Series(0.0, index=pd.to_datetime(dates)))
    strat = 1.5 * rets["SPY"] + rng.normal(0.0002, 0.003, len(idx))
    lens = codeserver.factor_lens([d.strftime("%Y-%m-%d") for d in idx], list(strat))
    eq = next(f for f in lens["factors"] if f["factor"] == "Equity")
    assert eq["beta"] == pytest.approx(1.5, abs=0.1) and lens["r2"] > 0.8

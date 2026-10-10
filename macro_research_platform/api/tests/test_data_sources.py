"""Free data providers, offline: EDGAR statement maths and point-in-time timing, the factor
file parser and regression, ALFRED revision stats, and fundamentals in Quant Lab formulas."""
import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from api.providers import alfred, factor_library, sec_edgar


def _fact(start, end, val, filed, form="10-Q", accn=None):
    d = {"end": end, "val": val, "filed": filed, "form": form, "accn": accn or f"a-{end}-{filed}"}
    if start:
        d["start"] = start
    return d


def test_quarterly_derives_q4_from_annual_and_ytd_cash_flow():
    # Revenue: Q1–Q3 filed as 3-month facts, Q4 only inside the 10-K year
    rev = [_fact("2025-01-01", "2025-03-31", 10, "2025-04-30"), _fact("2025-04-01", "2025-06-30", 11, "2025-07-30"),
           _fact("2025-07-01", "2025-09-30", 12, "2025-10-30"),
           _fact("2025-01-01", "2025-12-31", 50, "2026-02-20", form="10-K")]
    q = sec_edgar.quarterly(rev)
    assert [r["val"] for r in q] == [10, 11, 12, 17] and q[-1]["filed"] == "2026-02-20"
    # Cash flow: year-to-date 3, 6, 9, 12 months
    cf = [_fact("2025-01-01", "2025-03-31", 5, "2025-04-30"), _fact("2025-01-01", "2025-06-30", 9, "2025-07-30"),
          _fact("2025-01-01", "2025-09-30", 15, "2025-10-30"), _fact("2025-01-01", "2025-12-31", 22, "2026-02-20", "10-K")]
    assert [r["val"] for r in sec_edgar.quarterly(cf)] == [5, 4, 6, 7]


def test_first_filed_value_wins_and_ttm():
    pts = [_fact("2025-01-01", "2025-03-31", 10, "2025-04-30"),
           _fact("2025-01-01", "2025-03-31", 99, "2026-04-30")]      # a later restatement
    assert sec_edgar.quarterly(pts)[0]["val"] == 10
    qs = [{"end": e, "val": v, "filed": f} for e, v, f in [("2025-03-31", 1, "2025-04-30"), ("2025-06-30", 2, "2025-07-30"),
                                                           ("2025-09-30", 3, "2025-10-30"), ("2025-12-31", 4, "2026-02-20")]]
    t = sec_edgar.ttm(qs)
    assert t == [{"end": "2025-12-31", "val": 10, "filed": "2026-02-20"}]


def test_pit_frame_shows_values_only_after_filing(monkeypatch):
    monkeypatch.setattr(sec_edgar, "pit_events", lambda t: {"eps_ttm": [("2025-04-30", 2.0), ("2025-07-30", 2.5)]})
    idx = pd.bdate_range("2025-04-25", "2025-08-05")
    f = sec_edgar.pit_frame(["X"], idx)["eps_ttm"]["X"]
    assert np.isnan(f.loc["2025-04-30"])                  # filed during/after that session
    assert f.loc["2025-05-01"] == 2.0 and f.loc["2025-07-30"] == 2.0 and f.loc["2025-07-31"] == 2.5


def test_factor_file_parser_and_attribution(monkeypatch):
    rng = np.random.default_rng(0)
    rows = "\n".join(f"{d.strftime('%Y%m%d')}," + ",".join(f"{x:.4f}" for x in rng.normal(0.02, 1, 5)) + ",0.01"
                     for d in pd.bdate_range("2020-01-01", periods=600))
    text = f"header line\n\n,Mkt-RF,SMB,HML,RMW,CMA,RF\n{rows}\n\n Annual Factors\n,Mkt-RF\n2020,1.0\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("f.csv", text)
    df = factor_library._parse(buf.getvalue())
    assert len(df) == 600 and abs(df["RF"].iloc[0] - 0.0001) < 1e-12
    df["Mom"] = np.random.default_rng(1).normal(0, 0.01, len(df))
    monkeypatch.setattr(factor_library, "factors", lambda: df)
    r = 1.5 * df["Mkt-RF"] + df["RF"] + 0.0002                  # beta 1.5, alpha 2 bp/day
    out = factor_library.attribution(r.to_numpy(), [d.strftime("%Y-%m-%d") for d in df.index], model="ff5")
    assert out["loadings"][0]["beta"] == pytest.approx(1.5, abs=1e-6)
    assert out["alpha_annual"] == pytest.approx(0.0002 * 252, abs=1e-6)


def test_alfred_revision_stats(monkeypatch):
    first = [{"date": f"2020-0{i}-01", "value": v, "released": "x"} for i, v in enumerate([100, 101, 103, 102, 104, 106, 105, 107, 108], 1)]
    latest = [{"date": o["date"], "value": o["value"] + (1 if i % 2 else -1)} for i, o in enumerate(first)]
    monkeypatch.setattr(alfred, "first_release", lambda s, start: first)
    monkeypatch.setattr(alfred, "latest", lambda s, start: latest)
    out = alfred.revisions("X", transform="level")
    assert len(out["rows"]) == 9 and out["stats"]["mean_abs_revision"] == 1.0


def test_formula_fundamentals_use_the_loader():
    from api.quant import expr
    idx = pd.bdate_range("2024-01-01", periods=10)
    close = pd.DataFrame({"A": 10.0, "B": 20.0}, index=idx)
    f = {k: pd.DataFrame(np.nan, index=idx, columns=["A", "B"]) for k in sec_edgar.PIT_FIELDS}
    f["eps_ttm"].loc[:, :] = [1.0, 1.0]
    f["shares"].loc[:, :] = [100.0, 100.0]
    f["equity"].loc[:, :] = [500.0, 4000.0]
    ctx = expr.Ctx(close, fundamentals_loader=lambda t, i: f)
    ey = expr.evaluate("earnings_yield", ctx).iloc[-1]
    assert ey["A"] == pytest.approx(0.1) and ey["B"] == pytest.approx(0.05)
    assert expr.evaluate("book_to_price", ctx).iloc[-1]["B"] == pytest.approx(2.0)

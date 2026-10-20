"""update_csv: a partial refresh must not blank values already recorded for this month."""
from datetime import date

import pandas as pd

from api import data_pipeline


def test_partial_refresh_keeps_this_months_values(tmp_path, monkeypatch):
    month = pd.Timestamp(date.today().replace(day=1))
    prev = month - pd.offsets.MonthBegin(1)
    csv = tmp_path / "econ.csv"
    pd.DataFrame({"us_cpi": [3.0, 3.35], "yield_10y": [5.0, 5.24], "vix": [14.0, 15.3],
                  "oil_price": [80.0, 91.1], "equity_index": [7000.0, 7722.7], "dollar_index": [100.0, 101.9]},
                 index=[prev, month]).to_csv(csv)
    monkeypatch.setattr(data_pipeline, "CSV_PATH", csv)

    # FRED blocked: only market fields come back
    assert data_pipeline.update_csv({"vix": 15.55, "oil_price": 90.2, "equity_index": 7758.9,
                                     "dollar_index": 102.2, "us_cpi": float("nan")})
    out = pd.read_csv(csv, index_col=0, parse_dates=True)
    assert out.loc[month, "vix"] == 15.55                      # refreshed
    assert out.loc[month, "us_cpi"] == 3.35                    # kept, not blanked
    assert out.loc[month, "yield_10y"] == 5.24
    assert out.loc[prev, "us_cpi"] == 3.0                      # earlier month untouched

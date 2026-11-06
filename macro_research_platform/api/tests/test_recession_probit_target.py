"""The probit must be trained on the same event the ensemble and the challenger are.

`_prepare_data` used `df['recession'].shift(-horizon)`, which labels "in recession in exactly month
t+12". api/research_indicators._recession_ahead — used by recession_ensemble and
recession_challenger — labels "any recession month in (t, t+12]", the Federal Reserve staff
definition. Same NBER calendar, two different events, and the probit was the outlier: 99 of 780
months labelled oppositely, base rate halved, and all of 2001 and 2020 marked negative in their own
years, so the model never saw two of the recessions it exists to predict.
"""
import pandas as pd
import pytest

from api.models_ml.recession_probit import NBER_RECESSIONS, recession_window_label
from api.research_indicators import _recession_ahead


def _months(start="1960-01-01", end="2025-12-01"):
    return [d.strftime("%Y-%m") for d in pd.date_range(start, end, freq="MS")]


def _nber_series(months):
    rec = set()
    for start, end in NBER_RECESSIONS:
        for d in pd.date_range(start, end, freq="MS"):
            rec.add(d.strftime("%Y-%m"))
    return pd.Series([1.0 if m in rec else 0.0 for m in months], index=pd.to_datetime(months))


def test_label_agrees_with_the_definition_the_ensemble_uses():
    months = _months()
    mine = recession_window_label(_nber_series(months), 12)
    theirs = _recession_ahead(months, 12)
    compared = 0
    for month, expected in theirs.items():
        got = mine.loc[pd.Timestamp(f"{month}-01")]
        if expected is None:
            assert pd.isna(got), f"{month}: an incomplete window must be NaN, got {got}"
        else:
            assert float(got) == float(expected), f"{month}: {got} != {expected}"
            compared += 1
    assert compared > 700, f"only {compared} months compared — the two calendars have diverged"


def test_an_incomplete_window_is_not_labelled_zero():
    months = _months()
    lab = recession_window_label(_nber_series(months), 12)
    # the final `horizon` months cannot know their own window yet
    assert lab.iloc[-12:].isna().all()
    assert lab.iloc[:-12].notna().all()


def test_short_recessions_are_visible_in_their_own_year():
    months = _months()
    rec = _nber_series(months)
    window = recession_window_label(rec, 12)
    point = rec.shift(-12)                      # what this module used to train on
    for year in (2001, 2020):
        assert window.loc[str(year)].dropna().sum() > 0, f"{year}: the window label must see it"
        assert point.loc[str(year)].dropna().sum() == 0, (
            f"{year}: the old point label saw nothing — that contrast is the reason for this file"
        )


def test_the_base_rate_is_the_window_rate():
    months = _months()
    rec = _nber_series(months)
    window = recession_window_label(rec, 12)
    both = pd.concat([window.rename("w"), rec.shift(-12).rename("p")], axis=1).dropna()
    # 0.2487 against 0.1218 measured over 1960-2025; assert the relationship, not the digits
    assert both["w"].mean() == pytest.approx(0.2487, abs=0.02)
    assert both["w"].mean() > 1.5 * both["p"].mean()


def test_a_persisted_fit_from_an_earlier_label_definition_is_refused(tmp_path, monkeypatch):
    """_load_persisted is the outage fallback, so it can hand back a fit up to 30 days old. Those
    coefficients answer the question they were fitted on: serving a point-target fit as a
    window-target probability would be a silent inconsistency in exactly the situation where
    nobody can cross-check it. A version mismatch must be refused, not used."""
    import pickle

    from api.models_ml import recession_probit as rp

    path = tmp_path / "recession_probit.pkl"
    monkeypatch.setattr(rp, "_PERSIST_PATH", path)

    def persist(**attrs):
        m = rp.RecessionProbitModel()
        m.fitted = True
        for k, v in attrs.items():
            setattr(m, k, v)
        path.write_bytes(pickle.dumps(m))

    unversioned = rp.RecessionProbitModel()
    unversioned.fitted = True
    del unversioned.label_version                     # written before versioning existed
    path.write_bytes(pickle.dumps(unversioned))
    assert rp._load_persisted() is None, "an unversioned pickle is version 1 and must be refused"

    persist(label_version=1)                          # fitted on the point target
    assert rp._load_persisted() is None

    persist(label_version=99)                         # from a future definition
    assert rp._load_persisted() is None

    persist()                                         # __init__ stamps the current version
    loaded = rp._load_persisted()
    assert loaded is not None and loaded.label_version == rp.LABEL_VERSION

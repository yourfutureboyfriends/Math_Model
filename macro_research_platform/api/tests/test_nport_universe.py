"""N-PORT membership: equity holdings only, tickers normalised, and membership known only from each quarter-end."""
import pandas as pd

from api.quant import nport_universe as nu

XML = """<edgarSubmission><repPdDate>2025-06-30</repPdDate>
<invstOrSec><name>A</name><identifiers><ticker value="ABC"/></identifiers><assetCat>EC</assetCat></invstOrSec>
<invstOrSec><name>B</name><identifiers><ticker value="BRK.B"/></identifiers><assetCat>EC</assetCat></invstOrSec>
<invstOrSec><name>Cash fund</name><identifiers><ticker value="TMPXX"/></identifiers><assetCat>STIV</assetCat></invstOrSec>
<invstOrSec><name>Future</name><assetCat>DE</assetCat></invstOrSec></edgarSubmission>"""


def test_holdings_keep_equities_and_normalise_tickers(tmp_path, monkeypatch):
    monkeypatch.setattr(nu, "CACHE", tmp_path)
    monkeypatch.setattr(nu, "_get", lambda url, **p: XML)
    period, tickers = nu._holdings("0000000000-25-000001")
    assert period == "2025-06-30" and tickers == ["ABC", "BRK-B"]
    monkeypatch.setattr(nu, "_get", lambda url, **p: (_ for _ in ()).throw(AssertionError("refetched")))
    assert nu._holdings("0000000000-25-000001")[1] == ["ABC", "BRK-B"]          # cached


def test_members_frame_uses_only_snapshots_already_dated(monkeypatch):
    snaps = [(pd.Timestamp("2025-03-31"), frozenset({"OLD", "KEEP"})), (pd.Timestamp("2025-06-30"), frozenset({"NEW", "KEEP"}))]
    monkeypatch.setattr(nu, "snapshots", lambda funds=("IJH", "IJR"): snaps)
    idx = pd.DatetimeIndex(["2025-02-28", "2025-04-30", "2025-07-31"])
    m = nu.members_frame(idx, ["OLD", "NEW", "KEEP"])
    assert not m.iloc[0].any()                                                  # before the first snapshot: unknown
    assert m.loc["2025-04-30"].to_dict() == {"OLD": True, "NEW": False, "KEEP": True}
    assert m.loc["2025-07-31"].to_dict() == {"OLD": False, "NEW": True, "KEEP": True}

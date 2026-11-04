"""Custom data uploads (api/quant/customdata.py): parsing, as-of alignment without look-ahead, and use from both strategy
styles; plus the sandbox header naming the datasets."""
import numpy as np
import pandas as pd
import pytest

from api.quant import codelab, customdata, sandbox
from api.tests.test_qcalgo import _data

CSV = "date,value,breadth\n2019-06-04,1.5,0.2\n2019-06-08,2.5,0.4\n2019-07-01,-1.0,0.1\n"


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(customdata, "DIR", tmp_path)
    customdata.save("sentiment", CSV, "tester")
    return tmp_path


def test_parse_and_catalog(store):
    meta = customdata.catalog()[0]
    assert meta["name"] == "sentiment" and meta["columns"] == ["value", "breadth"] and meta["rows"] == 3
    with pytest.raises(ValueError):
        customdata.save("Bad Name", CSV, "tester")
    with pytest.raises(ValueError):
        customdata.save("x", "a,b\nnot-a-date,zz\n", "tester")


def test_alignment_is_as_of_and_marks_new_rows(store):
    idx = pd.bdate_range("2019-06-03", "2019-07-03")
    f = customdata.align(customdata.load("sentiment"), idx)
    assert np.isnan(f.loc["2019-06-03", "value"])                          # nothing before its first date
    assert f.loc["2019-06-04", "value"] == 1.5 and f.loc["2019-06-04", "_new"] == 1
    assert f.loc["2019-06-07", "value"] == 1.5 and f.loc["2019-06-07", "_new"] == 0
    # a Saturday row (8 June) arrives on Monday 10 June, not before
    assert f.loc["2019-06-10", "value"] == 2.5 and f.loc["2019-06-10", "_new"] == 1
    assert f.loc["2019-07-01", "value"] == -1.0


def _with_custom(data, names):
    from api.quant import codeserver
    codeserver.attach_custom(data, names)
    return data


def test_plain_strategy_reads_data_custom(store):
    code = '''
UNIVERSE = ["AAA"]
CUSTOM_DATA = ["sentiment"]
def strategy(data, **p):
    s = data.custom["sentiment"]["value"]
    return pd.DataFrame({"AAA": (s > 0).astype(float)}, index=data.close.index)
'''
    st = codelab.load_strategy(code)
    assert st["custom"] == ["sentiment"]
    data = _with_custom(_data(tickers=("AAA",)), st["custom"])
    res = codelab.backtest(st["strategy"](data), data, {"capital": 100_000}, "2019-06-03")
    assert res is not None


def test_algorithm_add_data_delivers_points_on_new_rows(store):
    code = '''
class Sent(PythonData):
    pass

class A(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2019, 6, 3)
        self.add_equity("AAA")
        self.s = self.add_data(Sent, "sentiment").symbol
        self.seen = []
    def on_data(self, data):
        if data.contains_key(self.s):
            p = data[self.s]
            self.seen.append((str(self.time.date()), p.value, p["breadth"], p.breadth))
'''
    st = codelab.load_strategy(code)
    assert st["custom"] == ["sentiment"]
    data = _with_custom(_data(tickers=("AAA",)), st["custom"])
    codelab.backtest(None, data, {"capital": 100_000}, "2019-06-03", on_bar=st["on_bar"])
    algo = st["on_bar"].state["algo"]
    assert algo.seen[:2] == [("2019-06-04", 1.5, 0.2, 0.2), ("2019-06-10", 2.5, 0.4, 0.4)]
    h = algo.history(algo.s)                                  # all rows up to the last session
    assert list(h["value"]) == [1.5, 2.5, -1.0]


def test_sandbox_header_names_custom_data_and_refuses_unknown(store):
    ok = 'UNIVERSE = ["SPY"]\nCUSTOM_DATA = ["sentiment"]\ndef strategy(data):\n    return data.close * 0\n'
    assert sandbox.check(ok)["custom"] == ["sentiment"]
    with pytest.raises(sandbox.SandboxError, match="not been uploaded"):
        sandbox.check(ok.replace('["sentiment"]', '["nope"]'))

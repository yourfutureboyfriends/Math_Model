import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from api.marketdata.dcf import _rf_persist


def test_parallel_currency_updates_are_merged_and_unreachable_source_uses_saved_yield(tmp_path):
    path=tmp_path/'rates.json';barrier=Barrier(4)
    def save(i):
        def fetched():barrier.wait(timeout=5);return (.01*i,f'observation {i}')
        return _rf_persist(f'CC{i}',fetched,cache_path=path)
    with ThreadPoolExecutor(max_workers=4) as pool:assert len(list(pool.map(save,range(1,5))))==4
    saved=json.loads(path.read_text())
    assert set(saved)=={'CC1','CC2','CC3','CC4'}
    value,source=_rf_persist('CC2',lambda:None,cache_path=path)
    assert value==.02 and 'last saved' in source
    with pytest.raises(RuntimeError,match='no yield'):_rf_persist('UNKNOWN',lambda:None,cache_path=path)
    assert list(tmp_path.iterdir())==[path]

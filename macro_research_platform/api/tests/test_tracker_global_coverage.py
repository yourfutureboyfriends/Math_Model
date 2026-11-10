"""Regional coverage supplements must not silently discard usable observations."""
import pytest
from api.marketdata import airtraffic as A

@pytest.mark.parametrize('field',['ac','aircraft'])
def test_regional_sweep_accepts_both_provider_envelopes(monkeypatch,field):
    now=1800000000
    monkeypatch.setattr(A.time,'time',lambda:now)
    monkeypatch.setattr(A,'SWEEP',[(31.1,121.8)])
    monkeypatch.setattr(A,'_sweep',{})
    monkeypatch.setattr(A,'_sweep_n',[0])
    rows=[{'hex':'fresh','lat':31,'lon':121,'seen_pos':0,'gs':400},
          {'hex':'contact-only','lat':31,'lon':121,'seen':0},
          {'hex':'invalid','lat':91,'lon':121,'seen_pos':0},
          {'hex':'expired','lat':31,'lon':121,'seen_pos':500}]
    monkeypatch.setattr(A,'_adsbfi',lambda path:{field:rows})
    assert A._sweep_once()==1
    assert A._sweep_rows()[0][0]=='fresh'
    assert A._sweep_rows()[0][7]==400


def test_failed_global_provider_keeps_fresh_regional_aircraft(monkeypatch):
    now=1800000000
    monkeypatch.setattr(A.time,'time',lambda:now)
    monkeypatch.setattr(A,'_cached',lambda k,t,fn:fn())
    def unavailable(): raise A.Upstream('provider unavailable')
    monkeypatch.setattr(A,'_world_base',unavailable)
    row=['abc','TEST',None,121,31,30000,0,400,90,0,None,now-10,0,'B77L']
    monkeypatch.setattr(A,'_sweep_rows',lambda:[row])
    monkeypatch.setattr(A,'_record_history',lambda *a:pytest.fail('partial outage must not enter comparable history'))
    result=A.world()
    assert len(result['rows'])==1 and result['stale']
    assert 'regional' in result['source'].lower()

"""Maritime evidence must preserve spatial/temporal uncertainty and sample scope."""
import threading
from types import SimpleNamespace
from datetime import datetime, timezone
import pytest
from api.marketdata import tracking as T, vessel_intel as VI


def test_historical_cells_are_not_artificially_displaced(monkeypatch):
    monkeypatch.setattr(T,'_presence',{'rows':{123456789:[1.2,103.4,'Cargo','','Test','','','2026-11-01T00:00:00Z']},'built':1})
    monkeypatch.setattr(T,'_sat_cache',{'built':None,'rows':[]})
    monkeypatch.setattr(VI,'notable_reasons',lambda v:[])
    row=T._sat_rows()[0]
    assert row[1:3]==[1.2,103.4] and row[T.WORLD_SHIP_COLS.index('time_basis')]=='historical_cell'
    assert row[3:5]==[None,None]


def test_nearest_port_assignment_excludes_old_reports_and_uses_radius_cache(monkeypatch):
    now=1800000000
    monkeypatch.setattr(T,'time_now',lambda:now)
    keys=[]
    monkeypatch.setattr(T,'_cached',lambda k,t,fn:(keys.append(k),fn())[1])
    monkeypatch.setattr(T,'MAJOR_PORTS',{'West':(1,2),'East':(1,2.1),'Uncovered':(10,10)})
    rows=[{'mmsi':1,'lat':1,'lon':2.02,'seen':now-30,'status':1,'type':'Cargo'},
          {'mmsi':2,'lat':1,'lon':2.1,'seen':now-901,'status':1,'type':'Tanker'}]
    monkeypatch.setattr(T,'ais_collector',lambda:SimpleNamespace(started=now-1000,all=lambda:rows))
    out=T.port_congestion(30)
    assert sum(p['total'] for p in out['ports'])==1
    assert next(p for p in out['ports'] if p['port']=='West')['anchored']==1
    assert next(p for p in out['ports'] if p['port']=='Uncovered')['sample_status']=='no recent observations'
    T.port_congestion(15)
    assert keys[0]!=keys[1]


def collector(monkeypatch,now):
    monkeypatch.setattr(T,'time_now',lambda:now)
    c=T._AisCollector.__new__(T._AisCollector)
    c.lock=threading.Lock();c.ships={};c.static={};c.tracks={};c.t0=now-1000
    c.msgs=0;c.static_saved=now;c.pruned=now
    return c


def report(stamp,lat=1):
    return {'MetaData':{'MMSI':123456789,'time_utc':stamp},'MessageType':'PositionReport',
            'Message':{'PositionReport':{'Latitude':lat,'Longitude':2,'Sog':10,'Cog':90,'TrueHeading':90}}}


def test_receiver_replays_and_future_times_do_not_refresh_positions(monkeypatch):
    now=1800000000;c=collector(monkeypatch,now)
    iso=lambda t:datetime.fromtimestamp(t,timezone.utc).isoformat()
    c._ingest(report(iso(now-60)))
    assert c.ships[123456789]['seen']==now-60
    c._ingest(report(iso(now-120),lat=3));c._ingest(report(iso(now+60),lat=4))
    assert c.ships[123456789]['lat']==1
    c._ingest(report('bad timestamp',lat=5))
    assert c.msgs==1


def test_missing_provider_timestamp_is_explicit_receipt_basis(monkeypatch):
    now=1800000000;c=collector(monkeypatch,now);c._ingest(report(None))
    assert c.ships[123456789]['time_basis']=='receiver_receipt'


def test_receiver_response_does_not_materialize_historical_world(monkeypatch):
    monkeypatch.setattr(T,'_cached',lambda k,t,fn:fn())
    monkeypatch.setattr(T,'ais_collector',lambda:None)
    monkeypatch.setattr(T,'_sat_rows',lambda:pytest.fail('historical layer should not be built for receiver polling'))
    assert T.world_vessels(False)['live_count']==0


def test_bad_ais_movement_values_remain_missing():
    assert T._ais_clean(-1,-20,float('nan'))==(None,None,None)
    assert T._ais_clean(102.3,360,511)==(None,None,None)
    assert T._ais_clean(0,0,0)==(0,0,0)

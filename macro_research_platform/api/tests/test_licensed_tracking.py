"""Contract fixtures exercise opt-in feeds without contacting vendors."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import pytest
from api.marketdata import global_tracking as G, tracking_trade as T

NOW=1800000000
@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(G,'DATA',tmp_path)
    monkeypatch.setattr(G,'_states',{})
    monkeypatch.setattr(G,'_cached_regions',{})
    for provider in G.SPECS:
        monkeypatch.delenv(f'TRACKING_{provider.upper()}_ENABLED',raising=False)


def test_disabled_feeds_never_acquire(monkeypatch):
    monkeypatch.setattr(G,'_request',lambda *a,**k:pytest.fail('disabled feed contacted'))
    assert G.ship_region('shanghai')['vessels']==[]
    assert not G.reserve_request('shipxy')


def test_request_cap_atomic_and_persistent(monkeypatch):
    monkeypatch.setenv('TRACKING_SHIPXY_ENABLED','true');monkeypatch.setenv('SHIPXY_API_KEY','test')
    monkeypatch.setenv('TRACKING_SHIPXY_DAILY_REQUESTS','3')
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _:G.reserve_request('shipxy'),range(12)))==3
    G._states.clear()  # Process-local state is not the budget ledger.
    assert not G.reserve_request('shipxy')
    assert G.provider_status('shipxy')['status']=='daily request cap reached'


def test_shipxy_preserves_report_time_and_rejects_old_positions():
    good={'mmsi':123456789,'lat':31,'lng':121,'last_time_utc':NOW-20,'sog':12,'hdg':511}
    rows,bad,partial,cursor=G.parse_shipxy({'status':0,'data':{'ship_list':[good,{**good,'last_time_utc':NOW-7200}], 'continue':True,'scode':'next'}},NOW)
    assert len(rows)==1 and bad==1 and partial and cursor=='next'
    assert rows[0]['seen']==NOW-20 and rows[0]['heading'] is None


def test_kpler_uses_position_timestamp_not_later_ingestion_time():
    p={'data':{'vessels':{'nodes':[{'staticData':{'mmsi':123456789,'shipType':'CONTAINER'},'lastPositionUpdate':{'latitude':31,'longitude':121,'timestamp':NOW-7200,'updateTimestamp':NOW,'collectionType':'SATELLITE'}}]}}}
    assert G.parse_kpler(p,NOW)[0]==[]
    with pytest.raises(ValueError):G.parse_kpler({'errors':[{'message':'private vendor error'}]},NOW)


def test_vesselfinder_source_and_utc_date():
    from datetime import datetime,timezone
    rows,*_=G.parse_vesselfinder([{'AIS':{'MMSI':123456789,'LATITUDE':1,'LONGITUDE':103,'TIMESTAMP':datetime.fromtimestamp(NOW-10,timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),'SRC':'TER'}}],NOW)
    assert rows[0]['collection_type']=='terrestrial' and rows[0]['seen']==NOW-10


def test_map_cache_never_acquires_and_prefers_latest(monkeypatch):
    monkeypatch.setattr(G.time,'time',lambda:NOW)
    monkeypatch.setattr(G,'_request',lambda *a,**k:pytest.fail('map initiated acquisition'))
    G._cached_regions.update({('a','a'):{'rows':[{'mmsi':1,'seen':NOW-5}]},('b','b'):{'rows':[{'mmsi':1,'seen':NOW-10},{'mmsi':2,'seen':NOW-7200}]}})
    assert G.ship_snapshot()==[{'mmsi':1,'seen':NOW-5}]


def test_firehose_rejects_estimates_and_bad_credentials(monkeypatch):
    p={'type':'position','hexid':'abcdef','lat':31,'lon':121,'clock':NOW-10,'updateType':'A','gs':'400'}
    assert G.parse_firehose(p,NOW)['speed']==400
    assert G.parse_firehose({**p,'updateType':'E'},NOW) is None
    assert G.parse_firehose({**p,'clock':NOW-7200},NOW) is None
    monkeypatch.setenv('FLIGHTAWARE_FIREHOSE_USERNAME','user\ncommand');monkeypatch.setenv('FLIGHTAWARE_FIREHOSE_API_KEY','secret')
    with pytest.raises(ValueError,match='invalid stream credentials'):G.firehose_command()


def test_no_observations_means_unknown_coverage():
    r=G.regional_summary([],'ship',NOW)[0]
    assert r['observed']==0 and r['median_age_s'] is None and 'unknown' in r['coverage']


def trade_rows():
    end=date(2026,11,1)
    return [{'portname':'Shanghai','date':str(end-timedelta(days=i+offset)),'import':100,'export':200,'portcalls':10} for offset in (0,364) for i in range(28)]


def test_trade_requires_full_calendar_windows_and_deduplicates():
    rows=trade_rows()
    result=T.summarize(rows+[rows[0]])['ports'][0]
    assert result['tonnes_day']==300 and result['tonnes_yoy']==0 and result['complete_window']
    result=T.summarize(rows[1:])['ports'][0]
    assert result['tonnes_day'] is None and result['tonnes_yoy'] is None


def test_partial_trade_withholds_comparisons():
    result=T.summarize(trade_rows(),partial=True)['ports'][0]
    assert result['imports_t_day'] is None and result['calls_day'] is None and result['tonnes_yoy'] is None

"""Regression evidence for tracker outages, incomplete samples and analytics gaps."""
import json
import math
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from api.marketdata import airtraffic as A, analytics, tracking as T, security
from api.marketdata.tracker_quality import position, recent, ship_phase


@pytest.mark.parametrize('lat,lon', [(float('nan'),0),(0,float('inf')),(91,0),(0,181),(None,0)])
def test_invalid_coordinates_never_reach_maps(lat,lon):
    assert not position(lat,lon)


def test_timestamp_and_status_unknowns_are_not_invented():
    assert position(0,0)
    assert not recent(None,1000,120) and not recent(1200,1000,120)
    assert ship_phase(None,None)=='unknown'
    assert ship_phase(None,0.1)=='unknown'
    assert ship_phase(2,0)=='unknown'  # not under command is not automatically underway
    assert ship_phase(1,0)=='anchored' and ship_phase(5,0)=='moored'


def test_fresh_contact_does_not_replace_missing_position_timestamp():
    s=['abc','TEST','US',None,1000,1,2,100,False,10,90,0,None,100,None,False,0]
    assert A._world_rows({'time':1000,'states':[s]})==[]
    s[3]=990
    assert A._world_rows({'time':1000,'states':[s]})[0][11]==990


def test_outage_snapshot_ages_against_wall_clock(monkeypatch,tmp_path):
    now=1800000000
    monkeypatch.setattr(A.time,'time',lambda:now)
    monkeypatch.setattr(A,'_cached',lambda k,t,fn:fn())
    row=['abc','TEST','US',1,2,10000,0,300,90,0,None,now-7200,0,None]
    monkeypatch.setattr(A,'_world_base',lambda:{'rows':[row],'time':now-7200,'stale':'provider down'})
    monkeypatch.setattr(A,'_sweep_rows',lambda:[])
    monkeypatch.setattr(A,'HISTORY',tmp_path/'history.json')
    w=A.world()
    assert w['rows']==[] and w['stale_dropped']==1 and not A.HISTORY.exists()


def test_area_rejects_old_unknown_and_future_position_ages(monkeypatch):
    monkeypatch.setattr(A,'_cached',lambda k,t,fn:fn())
    rows=[{'hex':str(n),'lat':1,'lon':2,'seen_pos':age} for n,age in enumerate([0,60,121,-1,None])]
    monkeypatch.setattr(A,'_adsbfi',lambda path:{'ac':rows})
    result=A.area(1,2)
    assert [r['hex'] for r in result['aircraft']]==['0','1']
    assert all(r['position_time']>0 for r in result['aircraft'])


def test_port_unknown_status_counts_without_claiming_a_queue(monkeypatch):
    monkeypatch.setattr(T,'_cached',lambda k,t,fn:fn())
    monkeypatch.setattr(T,'MAJOR_PORTS',{'Test':(1,2)})
    monkeypatch.setattr(T,'ais_collector',lambda:SimpleNamespace(started=T.time_now(),all=lambda:[{'mmsi':123456789,'lat':1,'lon':2,'status':None,'speed':None,'seen':T.time_now()}]))
    p=T.port_congestion(15)
    assert p['ports'][0]['unknown']==1 and p['ports'][0]['anchored']==0 and p['ports'][0]['total']==1
    assert '15 km' in p['note'] and 'not measured congestion' in p['note']


def prices():
    idx=pd.bdate_range('2026-01-01',periods=150)
    x=100*np.exp(np.cumsum(np.sin(np.arange(150))*0.01+0.001))
    frame=pd.DataFrame({'AAA':x,'BBB':x*2,'ZERO':np.zeros(150)},index=idx)
    frame.loc[idx[60:90],'BBB']=np.nan
    return frame


def test_correlation_reports_real_pair_counts_without_gap_zero_returns(monkeypatch):
    p=prices()
    monkeypatch.setattr(analytics,'_closes',lambda *args:p)
    monkeypatch.setattr(analytics,'_cached',lambda k,t,fn:fn())
    result=analytics.correlation(['AAA','BBB','ZERO'])
    i,j=[result['symbols'].index(s) for s in ['AAA','BBB']]
    assert result['pair_observations'][i][j] < result['pair_observations'][i][i]
    assert result['matrix'][i][j]==1 and result['missing']==['ZERO']
    json.dumps(result,allow_nan=False)


def test_comparison_sharpe_uses_arithmetic_mean_and_observed_returns(monkeypatch):
    p=prices()[['AAA','BBB']]
    monkeypatch.setattr(security,'_closes',lambda *args:p)
    monkeypatch.setattr(security,'_cached',lambda k,t,fn:fn())
    result=security.compare(['AAA','BBB','AAA'])
    assert result['symbols']==['AAA','BBB']
    s=result['stats'][0]
    r=p.AAA.pct_change(fill_method=None).dropna()
    assert s['sharpe']==pytest.approx(r.mean()/r.std()*math.sqrt(252))
    assert s['risk_free_rate']==0
    json.dumps(result,allow_nan=False)


def test_calendar_averages_reject_gaps_nulls_and_duplicates():
    from api.marketdata.tracker_quality import calendar_average
    rows=[{'date':f'2026-10-{n:02}','n':0} for n in range(1,8)]
    assert calendar_average(rows,'2026-10-07',7,'n')==0
    assert calendar_average(rows[:-1],'2026-10-07',7,'n') is None
    assert calendar_average(rows[:-1]+[rows[0]],'2026-10-07',7,'n') is None
    rows[-1]['n']=None
    assert calendar_average(rows,'2026-10-07',7,'n') is None


def test_sparse_comparison_risk_is_missing_not_nan_or_zero(monkeypatch):
    p=prices()[['AAA','BBB']]
    p.loc[p.index[::2],'BBB']=np.nan
    monkeypatch.setattr(security,'_closes',lambda *args:p)
    monkeypatch.setattr(security,'_cached',lambda k,t,fn:fn())
    result=security.compare(['AAA','BBB'])
    assert result['stats'][1]['vol'] is None and result['stats'][1]['sharpe'] is None
    json.dumps(result,allow_nan=False)


def test_mixed_crypto_and_equities_keep_weekday_assets_and_monday_returns(monkeypatch):
    idx=pd.date_range('2026-01-01',periods=180)
    p=pd.DataFrame({'STOCK':np.exp(np.sin(np.arange(180))*0.1+5),'COIN':np.exp(np.cos(np.arange(180))*0.1+5)},index=idx)
    p.loc[idx.dayofweek>=5,'STOCK']=np.nan
    monkeypatch.setattr(analytics,'_closes',lambda *args:p)
    monkeypatch.setattr(analytics,'_cached',lambda k,t,fn:fn())
    result=analytics.correlation(['STOCK','COIN'])
    assert set(result['symbols'])=={'STOCK','COIN'} and result['calendar_basis']=='weekdays'
    assert min(min(row) for row in result['pair_observations'])>55
    from api.marketdata.return_quality import observed_returns
    r,annual=observed_returns(p.STOCK)
    assert annual==252 and r.loc['2026-01-05']==pytest.approx(p.STOCK.loc['2026-01-05']/p.STOCK.loc['2026-01-02']-1)


def test_all_weekend_traded_assets_use_calendar_annualization(monkeypatch):
    from api.marketdata.return_quality import analysis_calendar, observed_returns
    idx=pd.date_range('2026-01-01',periods=50)
    p=pd.DataFrame({'X':np.arange(50)+100,'Y':np.arange(50)+200},index=idx)
    frame,annual=analysis_calendar(p)
    assert len(frame)==50 and annual==365
    p.loc[idx[20],'X']=np.nan
    r,annual=observed_returns(p.X)
    assert annual==365 and pd.isna(r.loc[idx[21]])

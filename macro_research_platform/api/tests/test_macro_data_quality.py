import numpy as np
import pandas as pd
import pytest
from api.model.data import transform,excess_returns,build_macro_panel
from api.model.core import diffusion_factor,decide,ModelParams
from api.tests.test_macro_model import _synthetic


def test_nonpositive_levels_do_not_create_infinite_growth():
    s=pd.Series([10.]*24);s.iloc[12]=0;s.iloc[13]=-1
    out=transform(s,'yoy')
    assert not np.isinf(out).any() and pd.isna(out.iloc[12]) and pd.isna(out.iloc[13])


def test_missing_price_month_does_not_become_zero_or_two_month_return():
    r=excess_returns({'Asset':{'2020-01':100.,'2020-03':110.,'2020-04':121.}},pd.Series([0.]*5,index=pd.date_range('2020-01-01',periods=5,freq='MS')))
    assert pd.isna(r.loc['2020-02-01','Asset']) and pd.isna(r.loc['2020-03-01','Asset'])
    assert r.loc['2020-04-01','Asset']==pytest.approx(.1)


def test_cash_rate_does_not_forward_fill_indefinitely():
    prices={'A':{f'2020-{m:02d}':100.+m for m in range(1,9)}}
    r=excess_returns(prices,pd.Series([1.],index=pd.to_datetime(['2020-01-01'])))
    assert pd.notna(r.loc['2020-03-01','A']) and pd.isna(r.loc['2020-04-01','A'])


def test_constant_or_infinite_inputs_cannot_break_factor():
    panel,*_=_synthetic(n=160);b=panel[['INDPRO','G1','G2']].copy();b['constant']=1.;b['bad']=np.inf
    f,load=diffusion_factor(b,'INDPRO')
    assert not f.empty and np.isfinite(f).all() and 'constant' not in load and 'bad' not in load


def test_stale_asset_is_excluded_without_blocking_valid_assets():
    panel,rets,blocks,env=_synthetic(n=200);rets['Dead']=rets['Eq'];rets.loc[rets.index[-24]:,'Dead']=np.nan;env['Dead']='Equity'
    d=decide(panel,rets,blocks,env,rets.index[-1],ModelParams(min_history_months=60))
    assert d is not None and 'Dead' not in d.assets


def test_us_stale_input_is_reported_against_decision_month():
    from api.model.engine import _series_status
    from api.model.economies import ECONOMIES
    raw={'INDPRO':pd.Series([1.,2.],index=pd.to_datetime(['2020-01-01','2020-02-01']))}
    panel=build_macro_panel(raw)
    row=next(x for x in _series_status(ECONOMIES['us'],raw,panel,pd.Timestamp('2022-01-01')) if x['key']=='INDPRO')
    assert not row['used']


def test_backtest_missing_held_return_is_not_scored_as_zero():
    from api.model.backtest import run_backtest
    panel,rets,blocks,env=_synthetic(n=170);rets.iloc[-2,:]=np.nan
    result=run_backtest(panel,rets,blocks,env,ModelParams(min_history_months=60),start=rets.index[-5])
    assert not result['available'] and 'missing realized returns' in result['reason']


def test_staleness_is_decision_date_specific_not_hindsight_feature_selection():
    from api.model import core
    panel,rets,blocks,env=_synthetic(n=230)
    panel['DISCONTINUED']=panel['G1'];panel.loc[panel.index[-15]:,'DISCONTINUED']=np.nan;blocks['DISCONTINUED']='growth'
    p=ModelParams(min_history_months=60)
    old=core.decide(panel,rets,blocks,env,rets.index[-30],p)
    current=core.decide(panel,rets,blocks,env,rets.index[-1],p)
    assert 'DISCONTINUED' in old.loadings['growth']
    assert 'DISCONTINUED' not in current.loadings['growth']


def test_quality_marks_ragged_edge_and_uses_actual_factor_membership():
    from api.model.quality import decision_quality
    panel,rets,blocks,env=_synthetic(n=200)
    d=decide(panel,rets,blocks,env,rets.index[-1],ModelParams(min_history_months=60))
    month=rets.index[-1].strftime('%Y-%m')
    rows=[{'key':k,'label':k,'block':b,'used':True,'available_month':month if k!='G1' else '1990-01','latest_transformed':1.} for k,b in blocks.items()]
    rows.append({'key':'constant','label':'constant','block':'growth','used':True,'available_month':month})
    q=decision_quality(rows,d,rets.index[-1],rets,now=rets.index[-1]+pd.offsets.MonthBegin())
    assert not next(r for r in rows if r['key']=='constant')['used']
    assert q['status']=='review_required' and not q['point_in_time_verified']
    assert any('ragged' in w for w in q['warnings'])


def test_unsynchronized_factor_months_do_not_generate_a_next_month_allocation():
    panel,rets,blocks,env=_synthetic(n=200)
    panel.loc[panel.index[-1],[k for k,b in blocks.items() if b=='growth']]=np.nan
    assert decide(panel,rets,blocks,env,rets.index[-1],ModelParams(min_history_months=60)) is None


def test_direction_changes_follow_calendar_months_and_leave_missing_targets_unknown():
    from api.model.core import direction_features,realized_regimes
    f=pd.Series([1.,3.,4.],index=pd.to_datetime(['2020-01-01','2020-03-01','2020-04-01']))
    features=direction_features(f,1)
    assert pd.isna(features.loc['2020-03-01','change'])
    assert features.loc['2020-04-01','change']==1
    labels=realized_regimes(f,f,1)
    assert pd.isna(labels.loc['2020-03-01']) and labels.loc['2020-04-01']=='Reflation'


def test_refresh_failures_are_observed_instead_of_unhandled_background_exceptions():
    import asyncio
    from api.model import engine
    async def check():
        async def bad():raise ValueError('source unavailable')
        task=asyncio.create_task(bad());await asyncio.sleep(0)
        engine._refresh_finished('test-quality',task)
        assert 'source unavailable' in engine._REFRESH_FAILURES.pop('test-quality')[1]
    asyncio.run(check())


def test_fresh_current_version_disk_run_does_not_trigger_another_cold_fit(monkeypatch,tmp_path):
    import asyncio
    from api.model import engine
    monkeypatch.setattr(engine,'_SNAPSHOT_DIR',tmp_path)
    monkeypatch.setattr(engine,'_CACHE',{})
    monkeypatch.setattr(engine,'_REFRESHING',{})
    key=engine.params_hash(ModelParams())
    engine._save_snapshot(key,{'available':True,'version':engine.MODEL_VERSION,'run_id':42})
    result=asyncio.run(engine.run_model(persist=False))
    assert result['cache_source']=='disk' and 'snapshot' not in result
    assert not engine._REFRESHING


def test_gold_proxy_and_cache_follow_the_actual_configured_instrument(monkeypatch):
    from api.model import sources
    from api.model.data import ASSETS
    from api.model.economies import EA_ASSETS,ROW_ASSETS
    assert ASSETS['Gold'][0]=='GLD' and ROW_ASSETS['Gold'][0]=='GLD' and EA_ASSETS['Gold (EUR)'][0]=='usd:GLD'
    keys=[]
    monkeypatch.setattr(sources,'_cached',lambda key,fetch: keys.append(key) or {})
    sources.yahoo_monthly(['GLD','SPY'],'test')
    sources.yahoo_monthly(['SPY','GLD'],'test')
    sources.yahoo_monthly(['GC=F','SPY'],'test')
    assert keys[0]==keys[1] and keys[0]!=keys[2]

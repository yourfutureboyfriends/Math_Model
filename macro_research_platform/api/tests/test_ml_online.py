import copy,gzip,json
import pytest
from api.ml import online as O,continual as C


def table(n=140):
    return {'a':{f'{(2026*12+10-i)//12}-{(2026*12+10-i)%12+1:02d}':float(i) for i in range(n)}}


def test_contract_rejects_broken_or_future_data():
    contract={'minimum_series':1,'required':['a']};good=table()
    assert O.validate_table(good,contract,origin='2026-11')['observations']==140
    for value in (float('nan'),float('inf'),True):
        bad=copy.deepcopy(good);bad['a']['2026-11']=value
        with pytest.raises(ValueError):O.validate_table(bad,contract,origin='2026-11')
    bad=copy.deepcopy(good);bad['a']['2026-12']=1.
    with pytest.raises(ValueError):O.validate_table(bad,contract,origin='2026-11')
    with pytest.raises(ValueError):O.validate_table(good,contract,previous={'a':{},'b':{}},origin='2026-11')


def test_snapshots_are_replayable_content_addressed_observations(monkeypatch,tmp_path):
    monkeypatch.setattr(O,'ROOT',tmp_path)
    a,path=O.archive('macro_features',table(),now=1_700_000_000)
    b,same=O.archive('macro_features',table(),now=1_800_000_000)
    assert a==b and path==same
    saved=json.loads(gzip.decompress((tmp_path/path).read_bytes()))
    assert saved['data']==table() and saved['source']=='macro_features' and saved['observed_at'].startswith('2023')


def test_supervisor_rate_limits_and_preserves_last_good_on_failure(monkeypatch,tmp_path):
    monkeypatch.setattr(O,'ROOT',tmp_path);monkeypatch.setenv('ML_ONLINE_ENABLED','1')
    monkeypatch.setattr(O,'CONTRACTS',{'market_context':{'seconds':900,'cache':None,'timeout':10}})
    calls=[]
    def run(name):calls.append(name);return {'digest':'good','quality':{'quotes':3}}
    now=2_000_000_000
    assert O.cycle(now=now,runner=run)['action']=='accepted'
    assert O.cycle(now=now+1,runner=run)['action']=='not_due'
    def fail(name):raise ValueError('bad provider')
    assert O.cycle(now=now+901,runner=fail)['action']=='last_good_retained'
    assert O.read()['sources']['market_context']['digest']=='good'
    assert O.cycle(now=now+902,runner=run)['action']=='not_due'


def test_new_matured_labels_allow_daily_research_update(monkeypatch,tmp_path):
    from api.ml import deep
    monkeypatch.setattr(C,'STATE',tmp_path/'learning.json');monkeypatch.setenv('ML_AUTO_LEARN','1')
    monkeypatch.setattr(deep,'status',lambda:{'training':False})
    now=2_000_000_000
    C._write({'last_attempt':now-30000,'last_queued':now-2*86400,'accepted_digest':'old','observation':{'known_label_counts':{'a':100}}})
    result=C.cycle(now=now,observer=lambda:{'digest':'new','known_label_counts':{'a':101}},requester=lambda:{'queued':True})
    assert result['action']=='queued' and result['new_matured_labels'] and result['refit_minimum_days']==1


def test_pending_new_labels_survive_a_refit_cooldown(monkeypatch,tmp_path):
    from api.ml import deep
    monkeypatch.setattr(C,'STATE',tmp_path/'learning.json');monkeypatch.setenv('ML_AUTO_LEARN','1')
    monkeypatch.setattr(deep,'status',lambda:{'training':False})
    now=2_000_000_000
    C._write({'last_attempt':now-30000,'last_queued':now-40000,'accepted_digest':'old','accepted_label_counts':{'a':100}})
    observation=lambda:{'digest':'new','known_label_counts':{'a':101}}
    assert C.cycle(now=now,observer=observation,requester=lambda:{'queued':True})['action']=='refit_cooldown'
    assert C.cycle(now=now+86400,observer=observation,requester=lambda:{'queued':True})['action']=='queued'

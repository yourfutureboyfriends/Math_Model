"""Exercise workflow routes through the real authentication/fund middleware on temporary databases."""
from api.tests.test_funds import env


def test_server_records_follow_auth_fund_scope_and_optimistic_versions(env):
    analyst=env('analyst');pm=env('pm')
    body={'kind':'thesis','payload':{'id':'research-one','symbol':'MSFT','thesis':'Evidence'},'expected_version':0}
    created=analyst.put('/api/v1/workflows/research/research-one',json=body)
    assert created.status_code==200,created.text
    assert created.json()['version']==1
    assert pm.get('/api/v1/workflows/research').json()['records']==[]
    assert analyst.put('/api/v1/workflows/research/research-one',json=body).status_code==409
    body['expected_version']=1;body['payload']['thesis']='Updated evidence'
    assert analyst.put('/api/v1/workflows/research/research-one',json=body).json()['version']==2
    history=analyst.get('/api/v1/workflows/research/research-one/history').json()['versions']
    assert [r['version'] for r in history]==[2,1]
    assert pm.post('/api/v1/funds',json={'id':'research-other','name':'Research Other'}).status_code==200
    other=env('analyst','research-other')
    assert other.get('/api/v1/workflows/research').json()['records']==[]
    assert other.get('/api/v1/workflows/research/research-one/history').json()['versions']==[]


def test_readonly_and_password_pending_users_cannot_write_or_bypass_research_auth(env):
    from api.core import accounts
    from api import positions
    positions.upsert_position({'key':'test_observer','title':'Test observer','tier':4,'base_role':'viewer','capabilities':[],'panels':[]},'admin')
    positions.assign('analyst','test_observer','admin')
    viewer=env('analyst')
    assert viewer.get('/api/v1/workflows/research').status_code==200
    assert viewer.put('/api/v1/workflows/research/x',json={'kind':'thesis','payload':{}}).status_code==403
    accounts.set_password('pm','Temporary-Test-Only-2026!Z',must_change=True)
    pending=env('pm')
    assert pending.get('/api/v1/workflows/research').status_code==403
    anonymous=env('analyst');anonymous.headers.pop('Authorization')
    assert anonymous.get('/api/v1/workflows/research').status_code==401
    positions._bust()


def test_performance_is_admin_only_and_monitor_limits_are_enforced(env):
    analyst=env('analyst')
    assert analyst.get('/api/v1/workflows/performance').status_code==403
    assert analyst.put('/api/v1/workflows/monitor',json={'symbols':['MSFT'],'interval_minutes':5,'enabled':True}).status_code==422
    configured=analyst.put('/api/v1/workflows/monitor',json={'symbols':['MSFT'],'interval_minutes':60,'enabled':False})
    assert configured.status_code==200
    assert analyst.post('/api/v1/workflows/monitor/run').status_code==422
    assert analyst.put('/api/v1/workflows/monitor',json={'symbols':['MSFT'],'interval_minutes':60,'enabled':True}).status_code==200
    assert analyst.post('/api/v1/workflows/monitor/run').json()['queued'] is True
    from api.core import accounts
    accounts.update_user('analyst',role='admin')
    diagnostics=env('analyst').get('/api/v1/workflows/performance')
    assert diagnostics.status_code==200,diagnostics.text
    assert 'routes' in diagnostics.json() and 'upstream_work' in diagnostics.json()

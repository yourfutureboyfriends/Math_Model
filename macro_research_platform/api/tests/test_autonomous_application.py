from datetime import datetime,timezone,date
import json
import sqlite3
import subprocess
import sys
import numpy as np
import pandas as pd
import pytest
from api.ml.institutional import application_data as D
from api.ml.institutional.application import market_close
from api.ml import autonomous


def test_exchange_calendar_has_holidays_and_early_closes():
    assert market_close(date(2026,11,26)) is None
    assert market_close(date(2026,11,27)).hour==18
    assert market_close(date(2026,11,5)).hour==21


def test_horizon_targets_are_distinct_and_maturity_is_causal(monkeypatch):
    from api.ml import features
    months=pd.date_range('2018-01-01','2022-01-01',freq='MS')
    def fred(sid):
        if sid=='USREC':return pd.Series((months==pd.Timestamp('2020-04-01')).astype(float),index=months)
        return pd.Series(np.arange(len(months))+100.,index=months)
    prices=pd.Series(100.,index=pd.date_range('2018-01-01','2022-01-01',freq='D'))
    prices.loc['2020-03-05']=70
    monkeypatch.setattr(features,'_fred_monthly',fred)
    monkeypatch.setattr(features,'_yahoo_daily',lambda symbol:prices)
    labels=D.targets(['2020-01'])
    assert labels.shape==(1,4,6)
    assert labels[0,:,0].tolist()==[0,0,1,1]
    assert labels[0,0,1]==0 and labels[0,1,1]==1
    known=D.maturity('2020-01','2020-06-01T00:00:00Z')
    assert not known[3,0] and known[1,2] and not known[2,2]


def test_feature_packing_survives_sorted_json_round_trip():
    from api.ml.deep import fit_preprocessor
    rng=np.random.default_rng(8)
    frame={'core_keys':['ts','pay6','spx6'],'panel_keys':['p_'+str(i) for i in range(9)],'text_keys':['t_news','x_nfci'],
           'C':rng.normal(size=(180,3)),'P':rng.normal(size=(180,9)),'T':rng.normal(size=(180,2)),
           'months':pd.date_range('2000-01-01',periods=180,freq='MS').strftime('%Y-%m').tolist()}
    state=fit_preprocessor(frame,120)
    structure,_=D.feature_schema(frame,state)
    restored=json.loads(json.dumps(structure,sort_keys=True))
    before=D.pack(frame,state,179,structure['groups'])
    after=D.pack(frame,state,179,restored['groups'])
    np.testing.assert_array_equal(before['specialists'].numpy(),after['specialists'].numpy())
    assert structure['domain_names']==sorted(structure['groups'])


def test_serving_requires_current_promoted_pointer_and_calibration(tmp_path,monkeypatch):
    monkeypatch.setattr(autonomous,'ROOT',tmp_path)
    registry=tmp_path/'registry.sqlite'
    with sqlite3.connect(registry) as c:c.execute('CREATE TABLE champion(singleton INTEGER,id TEXT)');c.execute("INSERT INTO champion VALUES(1,'approved')")
    record={'origin':datetime.now(timezone.utc).isoformat(),'model_id':'approved','registry_path':str(registry),
            'probabilities':np.full((4,6),.6).tolist(),'calibration_ready':np.ones((4,6),dtype=bool).tolist()}
    (tmp_path/'serving.json').write_text(json.dumps(record))
    assert autonomous.served('recession_12m')['probability']==.6
    record['model_id']='shadow';(tmp_path/'serving.json').write_text(json.dumps(record))
    assert autonomous.served('recession_12m') is None
    record['model_id']='approved';record['calibration_ready'][3][0]=False;(tmp_path/'serving.json').write_text(json.dumps(record))
    assert autonomous.served('recession_12m') is None


def test_supervisor_import_does_not_load_torch():
    p=subprocess.run([sys.executable,'-c',"import sys;from api.ml import autonomous;assert 'torch' not in sys.modules"],capture_output=True,text=True,timeout=20)
    assert p.returncode==0,p.stderr


def test_fed_rdf_feed_entities_and_atom_are_parsed():
    from api.ml.institutional.ingestion import parse_feed
    rdf=b'''<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"><item><title>Rates&nbsp;and credit</title><link>https://www.federalreserve.gov/test</link><dc:date>2026-11-05T12:00:00Z</dc:date></item></rdf:RDF>'''
    assert parse_feed(rdf)==[{'link':'https://www.federalreserve.gov/test','published':'2026-11-05T12:00:00Z'}]
    atom=b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="https://example.com/article"/><published>2026-11-05T12:00:00Z</published></entry></feed>'''
    assert len(parse_feed(atom))==1
    with pytest.raises(ValueError):parse_feed(b'<html><body>Error page</body></html>')


def test_legacy_official_http_link_is_fetched_over_https(tmp_path):
    from api.ml.institutional.ingestion import FinancialIngestionAgent,Source
    class Extractor:
        def invoke(self,messages):return {'events':[]}
    agent=FinancialIngestionAgent(Extractor(),'test-v1',tmp_path)
    visited=[]
    class Fetcher:
        def get(self,url,hosts):
            visited.append(url)
            if url.endswith('.xml'):
                return b'<rss><channel><item><link>http://www.federalreserve.gov/release</link><pubDate>Thu, 05 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>'
            return b'<html><body>Official release text</body></html>'
    agent.fetcher=Fetcher()
    _,failures=agent.ingest([Source('Fed','https://www.federalreserve.gov/feed.xml',('www.federalreserve.gov',))],now='2026-11-05T21:00:00Z')
    assert not failures
    assert visited[-1]=='https://www.federalreserve.gov/release'


def test_release_anchor_excludes_other_announcements():
    from api.ml.institutional.ingestion import TextExtractor
    p=TextExtractor('new')
    p.feed('<p>Navigation</p><a name="new"></a><strong>Current release</strong><div>New information</div><hr><a name="old"></a>Outdated claim')
    assert p.found
    assert ' '.join(p.parts)=='Current release New information'


def test_exact_document_budget_is_not_a_false_source_failure(tmp_path):
    from api.ml.institutional.ingestion import FinancialIngestionAgent,Source
    class Extractor:
        def invoke(self,messages):return {'events':[]}
    agent=FinancialIngestionAgent(Extractor(),'test-budget',tmp_path)
    class Fetcher:
        def get(self,url,hosts):
            if url.endswith('empty.xml'):return b'<rss><channel/></rss>'
            if url.endswith('.xml'):return b'<rss><channel><item><link>https://example.com/document</link><pubDate>Fri, 06 Nov 2026 12:00:00 GMT</pubDate></item></channel></rss>'
            return b'<html><body>Public document</body></html>'
    agent.fetcher=Fetcher();observed=[]
    agent.source_observer=lambda source,events,failures,metrics:observed.append((source.name,failures))
    _,failures=agent.ingest([Source('one','https://example.com/a.xml',('example.com',)),Source('two','https://example.com/empty.xml',('example.com',))],now='2026-11-06T13:00:00Z',max_documents=1)
    assert not failures and observed==[('one',[]),('two',[])]

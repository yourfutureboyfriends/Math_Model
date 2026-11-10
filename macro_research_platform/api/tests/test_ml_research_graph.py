from api.ml.research_graph import build


def test_configured_graph_has_no_fabricated_measurements():
    graph=build(trace={},provider_state={'sources':{}})
    ids={n['id'] for n in graph['nodes']}
    assert len(ids)==len(graph['nodes'])
    assert all(e['source'] in ids and e['target'] in ids for e in graph['edges'])
    assert not any(e['observed'] for e in graph['edges'])
    assert not any(n['kind']=='observation' for n in graph['nodes'])
    assert all(n['status']=='research reference' for n in graph['nodes'] if n['kind']=='paper')
    assert graph['revision']==build(trace={},provider_state={'sources':{}})['revision']


def test_saved_outputs_and_routing_preserve_provenance_and_missing_heads():
    trace={'tasks':['recession_12m','oil_up_3m'],'as_of':'2026-11','inferred_at':'2026-11-05T09:00:00Z','input_digest':'abc',
           'seeds':[{'modules':['rates_credit'],'routing':[[.6]],'probabilities':[[.2,None]]},
                    {'modules':['rates_credit'],'routing':[[.8]],'probabilities':[[.4,None]]}]}
    graph=build(trace=trace,provider_state={'sources':{}})
    outputs=[n for n in graph['nodes'] if n['kind']=='observation']
    assert len(outputs)==1
    assert abs(outputs[0]['value']-.3)<1e-9
    assert outputs[0]['digest']=='abc'
    routing=next(e for e in graph['edges'] if e['source']=='module:rates_credit' and e['target']=='model:fusion')
    assert routing['observed'] and abs(routing['weight']-.7)<1e-9
    assert routing['observed_at']==trace['inferred_at']
    assert graph['revision']!=build(trace={},provider_state={'sources':{}})['revision']

import numpy as np
import pandas as pd
from api.ml import context
from api.ml.modular import feature_groups,validate_groups


def test_publication_lag_is_causal_and_limits_carry():
    series=pd.Series([1.,3.,9.],index=pd.to_datetime(['2024-01-01','2024-04-01','2024-07-01']))
    values=context.transform(series,'level',4,origin='2024-08')
    assert values['2024-05']==1 and values['2024-08']==3
    assert max(values)<='2024-08'
    assert '2024-04' not in values


def test_missing_optional_factors_do_not_change_schema_or_training_statistics(monkeypatch):
    from api import research_indicators as ri
    from api.ml.deep import fit_preprocessor,transform_features
    monkeypatch.setattr(ri,'_cached',lambda *a,**k:({'x_nfci':{'2024-01':1}},'ok'))
    assert set(context.load())==set(context.SPECS)
    assert context.load()['x_hy']=={}
    rng=np.random.default_rng(4)
    frame={'C':rng.normal(size=(40,2)),'P':rng.normal(size=(40,9)),'T':np.full((40,2),np.nan)}
    state=fit_preprocessor(frame,30);out=transform_features(frame,state)
    assert np.isfinite(out).all() and np.all(out[:,-2:]==1)


def test_specialist_assignment_covers_values_and_corresponding_missing_flags():
    groups=feature_groups(['ts'],8,['t_news','x_nfci','x_rrp','x_dsr'])
    assert groups['news']==[9,13]
    assert groups['financial_stress']==[10,14]
    assert groups['liquidity']==[11,15]
    assert groups['credit_cycle']==[12,16]
    validate_groups(groups,17)

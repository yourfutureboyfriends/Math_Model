"""Bounded, versioned sequence-network research profiles (no Torch import in API process)."""
from dataclasses import asdict,dataclass,replace
import hashlib
import json
import os

@dataclass(frozen=True)
class DeepConfig:
    profile:str='expanded'
    architecture:str='modular'
    hidden:int=64
    layers:int=2
    attention_heads:int=4
    dropout:float=.25
    seeds:int=5
    epochs:int=150
    patience:int=15
    learning_rate:float=.001
    weight_decay:float=.001
    gradient_clip:float=1.
    recent_half_life_months:int=120
    seed_budget_seconds:int=120
    batch_size:int=64

PROFILES={
 'reference':DeepConfig(profile='reference',architecture='shared',hidden=32,layers=1,attention_heads=0,dropout=.2),
 'expanded':DeepConfig(),
 'research_xl':DeepConfig(profile='research_xl',hidden=256,layers=4,attention_heads=8,dropout=.35,weight_decay=.003,batch_size=32),
}

def validate(config:DeepConfig):
    if config.architecture not in ('shared','modular'):raise ValueError('Unknown neural architecture')
    for key,low,high in [('hidden',16,512),('layers',1,6),('attention_heads',0,16),('seeds',1,9),('epochs',1,300),('patience',1,40),('recent_half_life_months',12,360),('seed_budget_seconds',1,600),('batch_size',8,256)]:
        value=getattr(config,key)
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:raise ValueError(f'Invalid deep-model {key}')
    if config.attention_heads and config.hidden%config.attention_heads:raise ValueError('Hidden units must divide evenly among attention heads')
    if not 0<=config.dropout<.8 or not 0<config.learning_rate<=.01 or not 0<=config.weight_decay<=.1 or not 0<config.gradient_clip<=10:raise ValueError('Invalid network optimization settings')
    return config


def configured():
    name=os.getenv('ML_DEEP_PROFILE','expanded')
    if name not in PROFILES:raise ValueError('ML_DEEP_PROFILE must be reference, expanded or research_xl')
    cfg=PROFILES[name]
    changes={}
    for field,env in [('seeds','ML_DEEP_SEEDS'),('epochs','ML_DEEP_EPOCHS'),('seed_budget_seconds','ML_DEEP_SEED_SECONDS')]:
        if os.getenv(env):changes[field]=int(os.environ[env])
    return validate(replace(cfg,**changes))


def fingerprint(cfg=None):
    cfg=cfg or configured()
    return hashlib.sha256(json.dumps({'protocol':'modular-purged-context-v5','config':asdict(cfg)},sort_keys=True).encode()).hexdigest()[:12]


def model_key(cfg=None):return 'deep_sequence__'+fingerprint(cfg)


def catalogue():
    cfg=configured()
    from api.ml.modular import STAGES
    from api.ml.context import SPECS
    return {'configured_modules':['rates_credit','real_economy','market_prices','macro_factors','news',*sorted({v[2] for v in SPECS.values()})],'stages':STAGES,'configured':asdict(cfg),'fingerprint':fingerprint(cfg),'forecast_key':model_key(cfg),'profiles':{k:asdict(v) for k,v in PROFILES.items()},
      'learning':'Scheduled refits learn only from matured observed labels. Recent training examples are weighted with a 120-month default half-life. No self-generated labels.',
      'validation':'Chronological holdout, label-horizon purge, train-only scalers/PCA, early stopping, gradient clipping and per-profile immutable forecast keys.',
      'promotion':'Network size does not establish accuracy. Existing walk-forward significance, live evidence and human approval gates remain required. Architecture changes reset the deep live-record cohort.',
      'limits':'XL is an opt-in research profile, not a promised accuracy gain. Per-seed wall-clock limits and one shared worker protect the local app.'}

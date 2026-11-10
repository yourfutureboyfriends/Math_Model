"""Trusted server-created valuation artifacts. Imported JSON never supplies executable code."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import types
import tempfile
from api.workflows.evidence import canonical, digest


def root():
    return Path(__file__).resolve().parents[2]/'data'/'processed'/'model_archive'


def _write_once(path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_text()!=payload:raise ValueError('Archive integrity conflict')
        return
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as f:
            tmp=Path(f.name);f.write(payload);f.flush();os.fsync(f.fileno())
        try:os.link(tmp,path)
        except FileExistsError:
            if path.read_text()!=payload:raise ValueError('Archive integrity conflict')
    finally:
        if tmp is not None:tmp.unlink(missing_ok=True)


def pack(value):
    if isinstance(value,float) and not math.isfinite(value):return {'__float__':str(value)}
    if isinstance(value,set):return {'__set__':sorted(value)}
    if isinstance(value,(tuple,list)):return [pack(x) for x in value]
    if isinstance(value,dict):return {k:pack(v) for k,v in value.items()}
    return value


def unpack(value):
    if isinstance(value,dict):
        if set(value)=={'__float__'}:return float(value['__float__'])
        if set(value)=={'__set__'}:return set(value['__set__'])
        return {k:unpack(v) for k,v in value.items()}
    if isinstance(value,list):return [unpack(x) for x in value]
    return value


def calculate(inp,model='fcff',**kwargs):
    """Use a private module namespace so FX recording cannot race other valuations."""
    from api.marketdata import dcf
    source=Path(dcf.__file__).read_text()
    engine=hashlib.sha256(source.encode()).hexdigest()
    constants=pack({k:v for k,v in vars(dcf).items() if not k.startswith('_') and k.isupper() and isinstance(v,(str,int,float,bool,dict,list,tuple,set,type(None)))})
    namespace=types.ModuleType('archived_dcf').__dict__
    exec(compile(source,'server_dcf.py','exec'),namespace)
    namespace.update(unpack(constants))
    rates={}
    original=dcf.to_usd
    def fx(value,currency):
        if currency not in rates:rates[currency]=original(1.,currency)
        return value*rates[currency] if rates[currency] is not None and value is not None else None
    namespace['to_usd']=fx
    if model not in ('fcff','excess_return'):raise ValueError('Forecast engine archive supports FCFF and excess-return models')
    result=namespace['value' if model=='fcff' else 'value_financial'](inp,**kwargs)
    manifest={'schema':1,'engine':engine,'python':sys.version.split()[0],'adapter':'captured-fx-v1','model':model,
              'inputs':inp,'kwargs':kwargs,'constants':constants,'fx_usd_per_unit':rates,'result':result}
    rid=digest(manifest)
    try:
        _write_once(root()/'engines'/f'{engine}.py',source)
        # Bound growth; stop creating artifacts once budget is exhausted, without breaking valuation.
        runs=root()/'runs';runs.mkdir(parents=True,exist_ok=True)
        if not (runs/f'{rid}.json').exists() and sum(p.stat().st_size for p in runs.glob('*.json'))>250_000_000:raise OSError('Archive storage budget reached')
        _write_once(runs/f'{rid}.json',canonical(manifest))
        result={**result,'_model_archive':{'id':rid,'engine_sha256':engine,'input_sha256':digest(inp),'python':manifest['python'],
                                       'basis':'Server engine, effective constants, exact keyword arguments and captured FX'}}
    except OSError:
        result={**result,'_model_archive':{'available':False,'reason':'Model artifact could not be stored'}}
    return result


def replay_forecast(valuation):
    ref=valuation.get('_model_archive') or {};rid=ref.get('id','')
    if len(rid)!=64 or any(c not in '0123456789abcdef' for c in rid):raise ValueError('No trusted server forecast artifact is linked to this valuation')
    path=root()/'runs'/f'{rid}.json'
    if not path.exists():raise ValueError('Forecast artifact is unavailable on this server')
    raw=json.loads(path.read_text())
    if digest(raw)!=rid:raise ValueError('Forecast artifact checksum mismatch')
    if digest({k:v for k,v in valuation.items() if k!='_model_archive'})!=digest(raw['result']):raise ValueError('Captured valuation does not match the server artifact')
    worker=Path(__file__).with_name('model_replay_worker.py')
    result=subprocess.run([sys.executable,'-I',str(worker),str(root()),rid],capture_output=True,text=True,timeout=20,
                          env={'PATH':os.defpath,'PYTHONHASHSEED':'0'})
    if result.returncode:raise ValueError('Offline forecast replay failed: incompatible runtime, artifact or unsupported dependency')
    replayed=json.loads(result.stdout)
    expected=raw['result'];numeric={}
    for key in ('per_share','per_share_reporting_ccy','enterprise_value','equity_value','pv_terminal'):
        a,b=expected.get(key),replayed.get(key)
        if isinstance(a,(int,float)) and isinstance(b,(int,float)):numeric[key]={'saved':a,'replayed':b,'difference':b-a}
    reconciled=digest(expected)==digest(replayed)
    return {'engine':'archived-forecast-v1','artifact_id':rid,'model':raw['model'],'exact_output_match':reconciled,'reconciled':reconciled,
            'values':numeric,'engine_sha256':raw['engine'],'input_sha256':digest(raw['inputs']),
            'note':'Original saved forecasting code, effective constants, exact inputs/arguments and recorded FX rerun in a separate process with network operations blocked. Same Python version required. Source ingestion, sensitivities, DDM and macro engines are outside this artifact.'}

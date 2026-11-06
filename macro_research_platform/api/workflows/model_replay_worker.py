"""Standalone isolated interpreter; only server-generated content-addressed artifacts."""
import hashlib
import json
from pathlib import Path
import sys
import types


def main():
    base=Path(sys.argv[1]);rid=sys.argv[2]
    canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    manifest=json.loads((base/'runs'/f'{rid}.json').read_text())
    if hashlib.sha256(canonical(manifest).encode()).hexdigest()!=rid:raise ValueError('Manifest checksum')
    if manifest['python']!=sys.version.split()[0] or manifest['adapter']!='captured-fx-v1':raise ValueError('Incompatible runtime')
    engine=manifest['engine']
    if len(engine)!=64 or any(c not in '0123456789abcdef' for c in engine):raise ValueError('Invalid engine')
    source=(base/'engines'/f'{engine}.py').read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=engine:raise ValueError('Engine checksum')
    def guard(event,args):
        if event.startswith(('socket.','subprocess.','os.system','os.exec','os.spawn')):raise RuntimeError('Offline replay forbids network and process access')
    sys.addaudithook(guard)
    core=types.ModuleType('api.marketdata.core')
    class NotFound(ValueError):pass
    core.NotFound=NotFound
    def unavailable(*args,**kwargs):raise ValueError('Uncaptured provider dependency')
    core._info=core._f=unavailable
    rates=manifest['fx_usd_per_unit']
    def to_usd(value,currency):
        if currency not in rates:raise ValueError('Uncaptured FX')
        return value*rates[currency] if value is not None and rates[currency] is not None else None
    core.to_usd=to_usd
    sys.modules['api.marketdata.core']=core
    namespace={'__name__':'archived_dcf'}
    exec(compile(source,'server_dcf.py','exec'),namespace)
    def unpack(value):
        if isinstance(value,dict):
            if set(value)=={'__float__'}:return float(value['__float__'])
            if set(value)=={'__set__'}:return set(value['__set__'])
            return {k:unpack(v) for k,v in value.items()}
        if isinstance(value,list):return [unpack(x) for x in value]
        return value
    namespace.update(unpack(manifest['constants']))
    fn={'fcff':'value','excess_return':'value_financial'}[manifest['model']]
    value=namespace[fn](manifest['inputs'],**manifest['kwargs'])
    print(canonical(value))


if __name__=='__main__':main()

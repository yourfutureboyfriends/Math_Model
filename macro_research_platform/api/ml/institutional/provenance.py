"""PROV-JSON export of the same immutable manifests used by serving inference."""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime,timezone
from functools import wraps
from pathlib import Path
from typing import Callable,Any,ParamSpec,TypeVar
from uuid import uuid4
from api.ml.institutional.lineage import InferenceManifest,digest,write_once
P=ParamSpec('P');R=TypeVar('R')


def prov_document(manifest:InferenceManifest,*,identifier:str,started:str,ended:str,output_digest:str|None,status:str) -> dict[str,Any]:
    """Emit PROV-JSON entities, activities, usage, generation and derivation.

    The PROV-JSON serialization is a W3C Member Submission. Custom metadata use
    a declared namespace, not undeclared non-PROV predicates.
    """
    manifest.validate();activity='macro:inference_'+identifier
    entities={};used={};derived={};output='macro:output_'+identifier
    for key,value in asdict(manifest).items():
        entity='macro:'+key+'_'+digest(value)
        entities[entity]={'prov:type':'prov:Entity','macro:role':key,'macro:identity':value}
        used['_:use_'+key]={'prov:activity':activity,'prov:entity':entity}
        if output_digest:derived['_:derive_'+key]={'prov:generatedEntity':output,'prov:usedEntity':entity}
    document={'prefix':{'prov':'http://www.w3.org/ns/prov#','macro':'urn:macro:'},'entity':entities,
              'activity':{activity:{'prov:startTime':started,'prov:endTime':ended,'macro:status':status}},'used':used}
    if output_digest:
        entities[output]={'macro:sha256':output_digest}
        document['wasGeneratedBy']={'_:generation':{'prov:entity':output,'prov:activity':activity,'prov:time':ended}}
        document['wasDerivedFrom']=derived
    return document


def track_provenance(root:Path,manifest:Callable[[],InferenceManifest],serialize:Callable[[R],Any]) -> Callable[[Callable[P,R]],Callable[P,R]]:
    """Audit decorator; artifact identity is resolved before inference starts."""
    def decorate(function:Callable[P,R]) -> Callable[P,R]:
        @wraps(function)
        def wrapped(*args:P.args,**kwargs:P.kwargs) -> R:
            identity=uuid4().hex;frozen=manifest();frozen.validate();start=datetime.now(timezone.utc).isoformat()
            write_once(root/(identity+'.started.json'),{'manifest':asdict(frozen),'started':start})
            try:
                result=function(*args,**kwargs);output=digest(serialize(result))
            except Exception:
                write_once(root/(identity+'.prov.json'),prov_document(frozen,identifier=identity,started=start,ended=datetime.now(timezone.utc).isoformat(),output_digest=None,status='failed'))
                raise
            write_once(root/(identity+'.prov.json'),prov_document(frozen,identifier=identity,started=start,ended=datetime.now(timezone.utc).isoformat(),output_digest=output,status='completed'))
            return result
        return wrapped
    return decorate

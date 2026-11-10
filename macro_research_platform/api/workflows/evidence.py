"""Immutable capture envelopes and offline analysis; never infer publisher availability."""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
REPLAY_VERSION = 'captured-fcff-projection-v1'


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def instant(value):
    if not isinstance(value,str):raise ValueError('A timezone-qualified timestamp is required')
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:raise ValueError('Timestamp must include a timezone')
    return dt.astimezone(timezone.utc).isoformat()


def model_fingerprint():
    root=Path(__file__).resolve().parents[1]
    names=['marketdata/dcf.py','marketdata/dcf_fundamentals.py','marketdata/dcf_expectations.py','workflows/evidence.py']
    return hashlib.sha256(b''.join((root/n).read_bytes() for n in names)).hexdigest()


def envelope(record,received_at):
    data=record.get('payload') or {}
    if not isinstance(data,dict):raise ValueError('Observation payload must be an object')
    supplied=record.get('metadata') or {}
    if not isinstance(supplied,dict):raise ValueError('Metadata must be an object')
    fields={key:data.get(key,supplied.get(key)) for key in ('source','source_url','currency','financial_currency','units','as_of','period_end','published_at','filed','retrieved_at','transformation')}
    flags=[]
    for key in ('source','units','as_of'):
        if fields.get(key) is None:flags.append(f'{key}_not_supplied')
    if not fields.get('published_at') and not fields.get('filed'):flags.append('publisher_availability_unknown')
    if data.get('stale'):flags.append('stale_provider_response')
    return {'schema':SCHEMA,'provider_verification':'not independently verified; capture integrity only','raw_sha256':digest(data),'record_input_id':digest({k:v for k,v in record.items() if k!='_evidence'}),
            'server_received_at':received_at,'availability_basis':'server receipt; publisher dates are unverified metadata',
            'provider_metadata':fields,'quality_flags':flags,'model_fingerprint':model_fingerprint() if record.get('kind')=='valuation' else None,
            'replay_engine':REPLAY_VERSION if record.get('kind')=='valuation' else None}


def replay(record):
    data=record.get('payload') or {};e=record.get('_evidence') or {}
    if e.get('raw_sha256')!=digest(data):raise ValueError('Captured payload checksum is missing or does not match')
    if e.get('replay_engine')!=REPLAY_VERSION:raise ValueError('This capture has no supported pinned replay engine')
    primary=data.get('primary') or data.get('base') or data
    v=primary.get('valuation',primary)
    if v.get('model',data.get('model'))!='fcff':raise ValueError('Offline replay currently supports captured FCFF projections only')
    finite=lambda n:isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n)
    rows=v.get('projection') or []
    if not rows or not all(all(finite(r.get(k)) for k in ('nopat','reinvestment','discount_factor')) for r in rows):raise ValueError('Complete saved cash flows and discount factors are required')
    if not all(finite(v.get(k)) for k in ('pv_terminal','equity_value','enterprise_value','per_share')) or v['equity_value']==0:raise ValueError('Saved terminal and equity bridge values are required')
    ev=sum((r['nopat']-r['reinvestment'])*r['discount_factor'] for r in rows)+v['pv_terminal']
    bridge=v['equity_value']-v['enterprise_value'];units=v['per_share']/v['equity_value']
    price=(ev+bridge)*units;difference=price-v['per_share']
    return {'engine':REPLAY_VERSION,'replayed_per_share':price,'saved_per_share':v['per_share'],'difference':difference,
            'reconciled':abs(difference)<=max(1e-6,abs(v['per_share'])*1e-6),'payload_sha256':e['raw_sha256'],
            'captured_model_fingerprint':e.get('model_fingerprint'),'current_model_fingerprint':model_fingerprint(),
            'note':'Offline replay of saved projections, terminal value and equity/listing-unit bridge. No provider calls. This checks arithmetic reproducibility; it does not rerun the original forecasting algorithm or certify input accuracy.'}


def compare_fields(left,right,tolerance=.01):
    if not 0<=tolerance<=1:raise ValueError('Tolerance must be between zero and one')
    required=('field','period_end','currency','units','accounting_basis','observed_at')
    if any(left.get(k) is None or right.get(k) is None for k in required):
        return {'status':'incomparable','reason':'Both sources need field, period, currency, units, accounting basis and observation date'}
    if any(left[k]!=right[k] for k in required):return {'status':'incomparable','reason':'Dates, units, currencies, field or accounting bases differ'}
    for row in (left,right):
        if not isinstance(row.get('value'),(int,float)) or isinstance(row['value'],bool) or not math.isfinite(row['value']):raise ValueError('Finite values are required')
        if not row.get('source') or not row.get('source_url'):raise ValueError('Named sources and evidence URLs are required')
        valid_source_url(row['source_url'])
    diff=right['value']-left['value'];scale=max(abs(left['value']),abs(right['value']))
    same=abs(diff)<=scale*tolerance if scale else diff==0
    independent=left['source'].strip().casefold()!=right['source'].strip().casefold()
    return {'status':'within_tolerance' if same else 'discrepancy','difference':diff,'relative_difference':abs(diff)/scale if scale else 0,
            'independent_providers':independent,'independence_verified':False,'left':left,'right':right,'tolerance':tolerance,
            'note':'Matched-basis comparison; provider names do not prove source independence. No value is overwritten.'}


def valid_source_url(value):
    from urllib.parse import urlsplit
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in ('https','http') or not parsed.hostname:raise ValueError('Evidence requires an HTTP(S) URL with a hostname')
    except (TypeError,AttributeError):raise ValueError('Evidence requires an HTTP(S) URL')
    return value

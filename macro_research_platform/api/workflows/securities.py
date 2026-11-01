"""Provider-backed listing registry. Never merge issuers on name similarity."""
import json
from api.workflows import store


def connect():
    c=store.connect()
    c.executescript('''CREATE TABLE IF NOT EXISTS workflow_securities (id TEXT PRIMARY KEY,provider TEXT NOT NULL,symbol TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS workflow_aliases (alias TEXT PRIMARY KEY,security_id TEXT NOT NULL,evidence TEXT NOT NULL,verified_by TEXT NOT NULL,updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS workflow_alias_history (id INTEGER PRIMARY KEY AUTOINCREMENT,alias TEXT NOT NULL,security_id TEXT NOT NULL,evidence TEXT NOT NULL,verified_by TEXT NOT NULL,updated_at TEXT NOT NULL);''')
    return c


def resolve(symbol):
    s=symbol.strip().upper()
    with connect() as c:
        row=c.execute('SELECT s.payload FROM workflow_aliases a JOIN workflow_securities s ON a.security_id=s.id WHERE a.alias=?',(s,)).fetchone()
        if row:return {**json.loads(row['payload']),'resolved_alias':s}
    from api.marketdata.core import _info
    info=_info(s)
    provider_symbol=info.get('symbol') or s;exchange=info.get('exchange')
    if not exchange:raise ValueError('Provider exchange is missing; this listing cannot be assigned a verified identity.')
    key=f'yahoo:{exchange}:{provider_symbol}'
    out={'id':key,'provider':'Yahoo Finance','symbol':provider_symbol,'exchange':exchange,'exchange_name':info.get('fullExchangeName'),
         'name':info.get('longName') or info.get('shortName'),'currency':info.get('currency'),'financial_currency':info.get('financialCurrency'),
         'quote_type':info.get('quoteType'),'timezone':info.get('exchangeTimezoneName'),'isin':info.get('isin'),'cik':info.get('cik'),
         'adr_ratio':info.get('adrRatio'),'share_class':info.get('shareClass'),'observed_at':store.now(),
         'note':'Listing identity from provider symbol and exchange. Missing issuer identifiers, share classes or ADR ratios remain unknown. Cross-listings are not automatically merged.'}
    with connect() as c:c.execute('INSERT OR REPLACE INTO workflow_securities VALUES(?,?,?,?,?)',(key,'Yahoo Finance',provider_symbol,json.dumps(out),store.now()))
    return out


def alias(alias,security_id,evidence,username):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM workflow_securities WHERE id=?',(security_id,)).fetchone():raise ValueError('Resolve the target listing first')
        prior=c.execute('SELECT security_id FROM workflow_aliases WHERE alias=?',(alias,)).fetchone()
        if prior and prior['security_id']!=security_id:raise store.Conflict('Alias already points to another listing; no silent remapping is allowed.')
        stamp=store.now();values=(alias,security_id,evidence,username,stamp)
        c.execute('INSERT OR REPLACE INTO workflow_aliases VALUES(?,?,?,?,?)',values)
        c.execute('INSERT INTO workflow_alias_history(alias,security_id,evidence,verified_by,updated_at) VALUES(?,?,?,?,?)',values)
    return {'alias':alias,'security_id':security_id,'evidence':evidence,'verified_by':username}


def normalize(symbol):
    s=symbol.strip().upper()
    with connect() as c:
        row=c.execute('SELECT s.symbol FROM workflow_aliases a JOIN workflow_securities s ON a.security_id=s.id WHERE a.alias=?',(s,)).fetchone()
        return row['symbol'] if row else s

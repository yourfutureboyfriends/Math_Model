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
        if row:
            result=json.loads(row['payload']);return {**result,'resolved_alias':s,'identity_links':identity_history(result['id'])}
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
    return {**out,'identity_links':identity_history(key)}


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


def link_identity(security_id,issuer_id,share_class_id,valid_from,valid_to,evidence,username,identifiers=None):
    """Dated, explicit reference assertions; never merge an issuer by its name."""
    from datetime import date
    date.fromisoformat(valid_from)
    if valid_to and date.fromisoformat(valid_to)<=date.fromisoformat(valid_from):raise ValueError('End date must be after start date')
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workflow_identity_links (id INTEGER PRIMARY KEY AUTOINCREMENT,security_id TEXT,issuer_id TEXT,share_class_id TEXT,valid_from TEXT,valid_to TEXT,evidence TEXT,verified_by TEXT,recorded_at TEXT,identifiers TEXT)')
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM workflow_securities WHERE id=?',(security_id,)).fetchone():raise ValueError('Resolve the listing first')
        if c.execute("SELECT 1 FROM workflow_identity_links WHERE security_id=? AND valid_from<COALESCE(?,'9999-12-31') AND COALESCE(valid_to,'9999-12-31')>?",(security_id,valid_to,valid_from)).fetchone():raise store.Conflict('Identity intervals overlap; earlier assertions are immutable')
        stamp=store.now();c.execute('INSERT INTO workflow_identity_links(security_id,issuer_id,share_class_id,valid_from,valid_to,evidence,verified_by,recorded_at,identifiers) VALUES(?,?,?,?,?,?,?,?,?)',(security_id,issuer_id,share_class_id,valid_from,valid_to,evidence,username,stamp,json.dumps(identifiers or {},allow_nan=False)))
    return {'security_id':security_id,'issuer_id':issuer_id,'share_class_id':share_class_id,'valid_from':valid_from,'valid_to':valid_to,'evidence':evidence,'verification':'administrator assertion, not independent provider verification'}


def identity_history(security_id):
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workflow_identity_links (id INTEGER PRIMARY KEY AUTOINCREMENT,security_id TEXT,issuer_id TEXT,share_class_id TEXT,valid_from TEXT,valid_to TEXT,evidence TEXT,verified_by TEXT,recorded_at TEXT,identifiers TEXT)')
        return [{**dict(r),'identifiers':json.loads(r['identifiers'])} for r in c.execute('SELECT * FROM workflow_identity_links WHERE security_id=? ORDER BY valid_from,recorded_at',(security_id,))]


def group_exposures(positions,as_of):
    """Sum actual direct weights for explicitly linked issuers; never drop real holdings."""
    grouped={};unmapped=[]
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workflow_identity_links (id INTEGER PRIMARY KEY AUTOINCREMENT,security_id TEXT,issuer_id TEXT,share_class_id TEXT,valid_from TEXT,valid_to TEXT,evidence TEXT,verified_by TEXT,recorded_at TEXT,identifiers TEXT)')
        for p in positions:
            rows=c.execute("SELECT l.* FROM workflow_identity_links l JOIN workflow_securities s ON s.id=l.security_id WHERE s.symbol=? AND l.valid_from<=? AND (l.valid_to IS NULL OR l.valid_to>?)",(p.get('symbol'),as_of,as_of)).fetchall()
            issuers={r['issuer_id'] for r in rows}
            if len(issuers)!=1:unmapped.append(p.get('symbol'));continue
            issuer=next(iter(issuers));row=grouped.setdefault(issuer,{'issuer_id':issuer,'known_direct_weight':0.,'symbols':[],'weight_complete':True})
            w=p.get('weight_pct')
            if isinstance(w,(int,float)):row['known_direct_weight']+=w
            else:row['weight_complete']=False
            row['symbols'].append(p.get('symbol'))
    return {'issuers':list(grouped.values()),'unmapped_symbols':unmapped,'note':'Direct weights summed using explicit dated identity links; missing/unlinked holdings are not silently merged or discarded.'}


def corporate_event(security_id,event_type,effective_date,evidence,username,ratio=None,new_symbol=None):
    """Append-only reference ledger; adjusted prices are never adjusted a second time here."""
    from datetime import date
    import math
    from api.workflows.evidence import valid_source_url
    date.fromisoformat(effective_date);valid_source_url(evidence)
    if event_type not in ('split','adr_ratio','ticker_change','delisting'):raise ValueError('Unsupported corporate event')
    if event_type in ('split','adr_ratio') and (not isinstance(ratio,(int,float)) or isinstance(ratio,bool) or not math.isfinite(ratio) or ratio<=0):raise ValueError('A positive sourced ratio is required')
    if event_type=='ticker_change' and not new_symbol:raise ValueError('A new listing symbol is required')
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workflow_corporate_evidence (id INTEGER PRIMARY KEY AUTOINCREMENT,security_id TEXT,event_type TEXT,effective_date TEXT,ratio REAL,new_symbol TEXT,evidence TEXT,recorded_by TEXT,recorded_at TEXT,UNIQUE(security_id,event_type,effective_date))')
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM workflow_securities WHERE id=?',(security_id,)).fetchone():raise ValueError('Resolve the affected listing first')
        if c.execute('SELECT 1 FROM workflow_corporate_evidence WHERE security_id=? AND event_type=? AND effective_date=?',(security_id,event_type,effective_date)).fetchone():raise store.Conflict('Corporate event already recorded; no silent replacement')
        c.execute('INSERT INTO workflow_corporate_evidence(security_id,event_type,effective_date,ratio,new_symbol,evidence,recorded_by,recorded_at) VALUES(?,?,?,?,?,?,?,?)',(security_id,event_type,effective_date,ratio,new_symbol,evidence,username,store.now()))
    return {'security_id':security_id,'event_type':event_type,'effective_date':effective_date,'ratio':ratio,'new_symbol':new_symbol,'evidence':evidence,'note':'Reference event retained with its listing identity. Provider-adjusted prices and recorded trades are not modified or double-adjusted. Analyst verification is required before relying on this assertion.'}


def corporate_history(security_id):
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS workflow_corporate_evidence (id INTEGER PRIMARY KEY AUTOINCREMENT,security_id TEXT,event_type TEXT,effective_date TEXT,ratio REAL,new_symbol TEXT,evidence TEXT,recorded_by TEXT,recorded_at TEXT,UNIQUE(security_id,event_type,effective_date))')
        return [dict(r) for r in c.execute('SELECT * FROM workflow_corporate_evidence WHERE security_id=? ORDER BY effective_date,recorded_at',(security_id,))]

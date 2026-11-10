from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
import sqlite3
import uuid
import zlib
from contextlib import contextmanager
from .config import ConfigError,EngineConfig,canonical,digest
from .schema import utc

def encode_event(event):
    body=canonical(event)
    return b"OEZ1"+zlib.compress(body.encode(),3) if len(body)>16384 else body

def decode_event(body):
    if isinstance(body,bytes):
        if not body.startswith(b"OEZ1"):raise ConfigError("Unknown audit encoding")
        body=zlib.decompress(body[4:]).decode()
    return json.loads(body)

class ConflictError(RuntimeError):
    pass

class Registry:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS oe_configs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, approved_at TEXT, approved_by TEXT, evidence TEXT);
            CREATE TABLE IF NOT EXISTS oe_books (id TEXT PRIMARY KEY, owner TEXT NOT NULL, config_id TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS oe_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL, asof TEXT NOT NULL, body TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS oe_event_book ON oe_events(book_id,seq);""")
    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=30)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:yield db
        finally:db.close()
    def import_research(self,owner,raw):
        cfg=EngineConfig.from_dict(raw);key=cfg.config_id
        now=datetime.now(timezone.utc).isoformat()
        with self.connection() as db:
            old=db.execute("SELECT owner FROM oe_configs WHERE id=?",(key,)).fetchone()
            if old and old["owner"]!=owner:raise ConfigError("Identical configuration is owned by another user; use your own version identifier")
            db.execute("INSERT OR IGNORE INTO oe_configs(id,owner,body,status,created_at) VALUES(?,?,?,?,?)",(key,owner,canonical(cfg.to_dict()),"research",now))
        return self.get_config(key,owner)
    def get_config(self,key,owner,admin=False):
        with self.connection() as db:row=db.execute("SELECT * FROM oe_configs WHERE id=?",(key,)).fetchone()
        if row is None or not admin and row["owner"]!=owner:return None
        out=dict(row);out["config"]=json.loads(out.pop("body"));out["config_id"]=out.pop("id");out["scope"]="paper"
        if digest(out["config"])!=out["config_id"]:raise ConfigError("Stored configuration hash mismatch")
        out["evidence"]=json.loads(out["evidence"]) if out["evidence"] else None
        return out
    def approve(self,key,actor,evidence,acknowledge=False):
        if actor.get("role") not in ("pm","risk","admin") or not acknowledge:raise PermissionError("PM/risk acknowledgement required for paper approval")
        row=self.get_config(key,actor["username"],actor.get("role")=="admin")
        if not row:raise ConfigError("Unknown owned research configuration")
        cfg=EngineConfig.from_dict(row["config"])
        if not cfg.forecast.validated or cfg.data.allow_model_quotes:raise ConfigError("Paper approval needs validated forecast and observed quotes only")
        if not isinstance(evidence,dict) or not evidence.get("run_id") or evidence.get("config_id")!=key or evidence.get("validation_id")!=cfg.forecast.validation_id or not evidence.get("reviewed_by"):
            raise ConfigError("Quant Lab validation evidence/config hash missing")
        now=datetime.now(timezone.utc).isoformat()
        if utc(cfg.forecast.trained_through)>=utc(now):raise ConfigError("Training ends in future")
        if not evidence.get("validation_end") or utc(evidence["validation_end"])>=utc(now) or utc(evidence["validation_end"])<=utc(cfg.forecast.trained_through):raise ConfigError("Invalid validation period")
        with self.connection() as db:
            result=db.execute("UPDATE oe_configs SET status='approved',approved_at=?,approved_by=?,evidence=? WHERE id=? AND status='research'",(now,actor["username"],canonical(evidence),key))
            if result.rowcount!=1:raise ConflictError("Configuration is not an unapproved research version")
        return self.get_config(key,actor["username"],actor.get("role")=="admin")
    def revoke(self,key,actor,reason):
        if actor.get("role") not in ("pm","risk","admin") or not reason:raise PermissionError("Risk/PM reason required")
        row=self.get_config(key,actor["username"],actor.get("role")=="admin")
        if not row:raise ConfigError("Unknown configuration")
        with self.connection() as db:db.execute("UPDATE oe_configs SET status='revoked' WHERE id=?",(key,))
        return self.get_config(key,actor["username"],actor.get("role")=="admin")
    def create_book(self,owner,key,capital,mode):
        from .execution import PaperBook
        row=self.get_config(key,owner)
        if not row:raise ConfigError("Unknown owned configuration")
        if mode=="paper" and row["status"]!="approved":raise ConfigError("Configuration is not approved for paper")
        book=PaperBook(capital,key,mode);bid=uuid.uuid4().hex
        with self.connection() as db:db.execute("INSERT INTO oe_books(id,owner,config_id,state) VALUES(?,?,?,?)",(bid,owner,key,canonical(book.to_dict())))
        return self.get_book(bid,owner)
    def get_book(self,bid,owner,admin=False):
        with self.connection() as db:row=db.execute("SELECT * FROM oe_books WHERE id=?",(bid,)).fetchone()
        if row is None or not admin and row["owner"]!=owner:return None
        out=dict(row);out["state"]=json.loads(out["state"]);return out
    def commit_tick(self,bid,owner,revision,state,asof,events):
        with self.connection() as db:
            changed=db.execute("UPDATE oe_books SET state=?,revision=revision+1 WHERE id=? AND owner=? AND revision=?",(canonical(state),bid,owner,revision))
            if changed.rowcount!=1:raise ConflictError("Book changed concurrently; retry with current snapshot")
            db.executemany("INSERT INTO oe_events(book_id,asof,body) VALUES(?,?,?)",[(bid,asof,encode_event(e)) for e in events])
        return self.get_book(bid,owner)
    def events(self,bid,owner,after=0,limit=100,admin=False):
        if not self.get_book(bid,owner,admin):return None
        with self.connection() as db:rows=db.execute("SELECT * FROM oe_events WHERE book_id=? AND seq>? ORDER BY seq LIMIT ?",(bid,after,max(1,min(limit,1000)))).fetchall()
        return [{"seq":r["seq"],"asof":r["asof"],"event":decode_event(r["body"])} for r in rows]

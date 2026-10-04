"""
Account security: password policy, lockout, token revocation, user administration.

Schema additions to `users` (migrated in place):
  must_change_password  1 = the user must set a new password before using the app
  disabled              1 = cannot sign in; existing tokens stop working immediately
  failed_attempts       consecutive failed logins
  locked_until          epoch seconds; sign-in refused until then
  password_changed_at   epoch seconds; tokens issued earlier are rejected

Tokens carry `jti` (id) and `iat` (issued-at). A token is valid only if its user exists,
is enabled, it was issued after the last password change, and its jti is not revoked
(revocations are stored in the DB, so logout survives restarts).
"""
from __future__ import annotations

import re
import secrets
import sqlite3
import string
import threading
import time
from typing import Any, Dict, List, Optional

from api.core import auth as _auth

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
MIN_PASSWORD_LENGTH = 12
ROLES = ("admin", "pm", "risk", "analyst", "quant")

# Seeded development accounts and their well-known passwords (never acceptable for use).
DEFAULT_PASSWORDS = {"admin": "admin123", "pm": "pm123", "analyst": "analyst123",
                     "risk": "risk123", "quant": "quant123"}
_COMMON = {"password", "password1", "password123", "letmein", "welcome", "qwerty",
           "123456789", "admin", "changeme", *DEFAULT_PASSWORDS.values()}

_NEW_COLUMNS = {"must_change_password": "INTEGER DEFAULT 0", "disabled": "INTEGER DEFAULT 0",
                "failed_attempts": "INTEGER DEFAULT 0", "locked_until": "REAL",
                "password_changed_at": "REAL"}

_cache_lock = threading.Lock()
_user_cache: Dict[str, tuple] = {}      # username -> (fetched_at, row or None)
_revoked_cache: Dict[str, Any] = {"at": 0.0, "jtis": set()}
_CACHE_TTL = 5.0


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_auth.get_db_path(), timeout=5)
    c.row_factory = sqlite3.Row
    return c


def invalidate_cache(username: Optional[str] = None) -> None:
    with _cache_lock:
        if username:
            _user_cache.pop(username, None)
        else:
            _user_cache.clear()
        _revoked_cache["at"] = 0.0


def migrate() -> None:
    """Add security columns / revocation table; flag users still on a default password."""
    _auth.init_users_table()
    with _conn() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        for col, typ in _NEW_COLUMNS.items():
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        c.execute("CREATE TABLE IF NOT EXISTS revoked_tokens (jti TEXT PRIMARY KEY, exp REAL)")
        c.execute("DELETE FROM revoked_tokens WHERE exp < ?", (time.time(),))
        for r in c.execute("SELECT username, hashed_password FROM users").fetchall():
            default = DEFAULT_PASSWORDS.get(r["username"])
            if default and _auth.verify_password(default, r["hashed_password"]):
                c.execute("UPDATE users SET must_change_password = 1 WHERE username = ?", (r["username"],))
        c.commit()
    invalidate_cache()


def default_credentials_active() -> bool:
    with _conn() as c:
        rows = c.execute("SELECT username, hashed_password FROM users WHERE COALESCE(disabled,0)=0").fetchall()
    return any(DEFAULT_PASSWORDS.get(r["username"]) and
               _auth.verify_password(DEFAULT_PASSWORDS[r["username"]], r["hashed_password"]) for r in rows)


# ── Password policy ──────────────────────────────────────────────────────────
def password_problems(password: str, username: str = "") -> List[str]:
    p = password or ""
    problems = []
    if len(p) < MIN_PASSWORD_LENGTH:
        problems.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    classes = sum(bool(re.search(rx, p)) for rx in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        problems.append("at least 3 of: lowercase, uppercase, digit, symbol")
    if username and username.lower() in p.lower():
        problems.append("must not contain the username")
    if p.lower() in _COMMON:
        problems.append("too common / a known default")
    return problems


def generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(16))
        if not password_problems(pw):
            return pw


# ── Lookups (cached briefly; every request verifies its token) ───────────────
def get_user(username: str) -> Optional[Dict[str, Any]]:
    now = time.time()
    with _cache_lock:
        hit = _user_cache.get(username)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]
    with _conn() as c:
        r = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    row = dict(r) if r else None
    with _cache_lock:
        _user_cache[username] = (now, row)
    return row


def is_revoked(jti: Optional[str]) -> bool:
    if not jti:
        return False
    now = time.time()
    with _cache_lock:
        if now - _revoked_cache["at"] < _CACHE_TTL:
            return jti in _revoked_cache["jtis"]
    with _conn() as c:
        jtis = {r["jti"] for r in c.execute("SELECT jti FROM revoked_tokens WHERE exp >= ?", (now,))}
    with _cache_lock:
        _revoked_cache.update(at=now, jtis=jtis)
    return jti in jtis


def revoke(jti: Optional[str], exp: Optional[float]) -> None:
    if not jti:
        return
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO revoked_tokens(jti, exp) VALUES(?, ?)",
                  (jti, float(exp or time.time() + 86400)))
        c.commit()
    invalidate_cache()


# ── Login with lockout ───────────────────────────────────────────────────────
class LoginError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def check_login(username: str, password: str) -> Dict[str, Any]:
    """Verify credentials with lockout. Returns the user row or raises LoginError."""
    now = time.time()
    with _conn() as c:
        r = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not r:
            _auth.verify_password(password, _auth.get_password_hash("x"))  # similar timing
            raise LoginError(401, "Invalid username or password")
        u = dict(r)
        if u.get("disabled"):
            raise LoginError(403, "This account is disabled — contact an administrator")
        if u.get("locked_until") and u["locked_until"] > now:
            mins = int((u["locked_until"] - now) // 60) + 1
            raise LoginError(429, f"Too many failed attempts — try again in {mins} min")
        if not _auth.verify_password(password, u["hashed_password"]):
            fails = int(u.get("failed_attempts") or 0) + 1
            locked = now + LOCKOUT_SECONDS if fails >= MAX_FAILED_ATTEMPTS else None
            c.execute("UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                      (0 if locked else fails, locked, username))
            c.commit()
            invalidate_cache(username)
            if locked:
                raise LoginError(429, f"Too many failed attempts — account locked for {LOCKOUT_SECONDS // 60} min")
            raise LoginError(401, "Invalid username or password")
        c.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login = datetime('now') "
                  "WHERE username = ?", (username,))
        c.commit()
    invalidate_cache(username)
    return u


def issue_token(user: Dict[str, Any]) -> str:
    return _auth.create_access_token({"sub": user["username"], "role": user["role"],
                                      "jti": secrets.token_hex(16), "iat": time.time()})


def set_password(username: str, new_password: str, must_change: bool = False) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET hashed_password = ?, must_change_password = ?, password_changed_at = ?, "
                  "failed_attempts = 0, locked_until = NULL WHERE username = ?",
                  (_auth.get_password_hash(new_password), 1 if must_change else 0, time.time(), username))
        c.commit()
    invalidate_cache(username)


# ── Administration ───────────────────────────────────────────────────────────
def list_users() -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("SELECT username, role, display_name, created_at, last_login, "
                         "COALESCE(disabled,0) AS disabled, COALESCE(must_change_password,0) AS must_change_password, "
                         "locked_until FROM users ORDER BY username").fetchall()
    now = time.time()
    return [{**dict(r), "disabled": bool(r["disabled"]), "must_change_password": bool(r["must_change_password"]),
             "locked": bool(r["locked_until"] and r["locked_until"] > now)} for r in rows]


def _active_admins(c) -> int:
    return c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND COALESCE(disabled,0) = 0").fetchone()[0]


def create_user(username: str, role: str, display_name: str) -> str:
    """Create a user with a random temporary password (returned once; must be changed)."""
    if not re.fullmatch(r"[a-z][a-z0-9._-]{2,31}", username or ""):
        raise ValueError("username: 3-32 chars, lowercase letters/digits/._- , starting with a letter")
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    temp = generate_temp_password()
    with _conn() as c:
        if c.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise ValueError("username already exists")
        c.execute("INSERT INTO users (username, hashed_password, role, display_name, must_change_password, "
                  "password_changed_at) VALUES (?, ?, ?, ?, 1, ?)",
                  (username, _auth.get_password_hash(temp), role, display_name or username, time.time()))
        c.commit()
    invalidate_cache(username)
    return temp


def update_user(username: str, *, role: Optional[str] = None, disabled: Optional[bool] = None,
                acting_user: str = "") -> Dict[str, Any]:
    with _conn() as c:
        r = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not r:
            raise KeyError(username)
        if role is not None and role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        demoting = role is not None and r["role"] == "admin" and role != "admin"
        disabling = bool(disabled) and r["role"] == "admin" and not r["disabled"]
        if (demoting or disabling) and _active_admins(c) <= 1:
            raise ValueError("cannot remove the last active administrator")
        if disabled and username == acting_user:
            raise ValueError("you cannot disable your own account")
        if role is not None:
            c.execute("UPDATE users SET role = ? WHERE username = ?", (role, username))
        if disabled is not None:
            c.execute("UPDATE users SET disabled = ? WHERE username = ?", (1 if disabled else 0, username))
        if role is not None or disabled:
            # role changes / disabling apply now: invalidate the user's existing tokens
            c.execute("UPDATE users SET password_changed_at = ? WHERE username = ?", (time.time(), username))
        c.commit()
    invalidate_cache(username)
    return next(u for u in list_users() if u["username"] == username)


def reset_password(username: str) -> str:
    if not get_user(username):
        raise KeyError(username)
    temp = generate_temp_password()
    set_password(username, temp, must_change=True)
    return temp


def unlock(username: str) -> bool:
    with _conn() as c:
        n = c.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE username = ?",
                      (username,)).rowcount
        c.commit()
    invalidate_cache(username)
    return n > 0

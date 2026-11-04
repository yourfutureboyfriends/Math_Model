"""
Two-factor sign-in: time-based one-time passwords (TOTP, RFC 6238 — Google Authenticator, Microsoft Authenticator,
1Password, Authy …) plus single-use recovery codes.

* Secrets are stored encrypted (Fernet, key derived from the server's JWT secret) and never returned after set-up.
* Codes: 6 digits, 30-second steps, ±1 step of clock drift; a step already used cannot be replayed.
* A wrong code counts as a failed sign-in (the account lockout applies).
* Recovery codes: 8 one-time codes, stored as bcrypt hashes, shown once at enrolment.
* An administrator can require two-factor for every account: a user without it can then only enrol (all other API
  calls answer 403 mfa_enrollment_required), and can reset a user's two-factor when a device is lost.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from api.core import auth as _auth

ISSUER = "Macro Terminal"
STEP = 30
DIGITS = 6
_COLS = {"totp_secret": "TEXT", "totp_pending": "TEXT", "totp_enabled": "INTEGER DEFAULT 0",
         "totp_last_step": "INTEGER", "recovery_codes": "TEXT"}


def _conn():
    from api.core.accounts import _conn as c
    return c()


def migrate() -> None:
    """Add the two-factor columns to the users table and create the security-settings table (idempotent, safe under
    concurrent start-up).
    """
    with _conn() as c:
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        for col, typ in _COLS.items():
            if col not in cols:
                try:
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
                except Exception as e:                                         # noqa: BLE001 — concurrent migration
                    if "duplicate column" not in str(e):
                        raise
        c.execute("CREATE TABLE IF NOT EXISTS app_security (key TEXT PRIMARY KEY, value TEXT)")
        c.commit()


def _fernet():
    from cryptography.fernet import Fernet
    from api.config import JWT_SECRET
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("totp:" + JWT_SECRET).encode()).digest()))


def _enc(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def _dec(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def new_secret() -> str:
    """A new random 160-bit TOTP secret, base32-encoded (as authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, step: int) -> str:
    """The 6-digit TOTP code for a secret at a 30-second time step (RFC 6238, HMAC-SHA1).

    Args:
        secret: base32 secret (padding optional).
        step: Unix time // 30.
    """
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    n = (struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(n).zfill(DIGITS)


def _match(secret: str, code: str, last_step: Optional[int], now: Optional[float] = None) -> Optional[int]:
    """The matching time step (±1 for drift) not already used, or None."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != DIGITS:
        return None
    t = int((now if now is not None else time.time()) // STEP)
    for s in (t - 1, t, t + 1):
        if last_step is not None and s <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, s), code):
            return s
    return None


def _user(username: str) -> Optional[Dict[str, Any]]:
    migrate()
    with _conn() as c:
        r = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(r) if r else None


def enabled(username: str) -> bool:
    """Whether the account has two-factor sign-in turned on."""
    u = _user(username)
    return bool(u and u.get("totp_enabled"))


_REQ: Dict[str, Any] = {"at": 0.0, "v": False}


def required() -> bool:
    """Whether every account must use two-factor (cached for 5 s: it is read on every request)."""
    if time.time() - _REQ["at"] < 5:
        return _REQ["v"]
    try:
        with _conn() as c:
            r = c.execute("SELECT value FROM app_security WHERE key = 'require_mfa'").fetchone()
        v = bool(r and json.loads(r["value"]))
    except Exception:                                                          # noqa: BLE001 — table not migrated yet
        v = False
    _REQ.update(at=time.time(), v=v)
    return v


def set_required(on: bool) -> None:
    """Require (or stop requiring) two-factor sign-in for every account; takes effect within seconds."""
    migrate()
    with _conn() as c:
        c.execute("INSERT INTO app_security (key, value) VALUES ('require_mfa', ?) ON CONFLICT(key) DO UPDATE SET "
                  "value = excluded.value", (json.dumps(bool(on)),))
        c.commit()
    _REQ.update(at=0.0)


def status(username: str) -> Dict[str, Any]:
    """The account's two-factor state: enabled, set-up pending, recovery codes left, and whether it is required."""
    u = _user(username) or {}
    codes = json.loads(u.get("recovery_codes") or "[]")
    return {"enabled": bool(u.get("totp_enabled")), "pending": bool(u.get("totp_pending")),
            "recovery_codes_left": len(codes), "required": required()}


def begin_setup(username: str) -> Dict[str, Any]:
    """A new secret (pending until confirmed with a code): the otpauth URI for the authenticator app and the key
    for manual entry. Returned once."""
    secret = new_secret()
    with _conn() as c:
        c.execute("UPDATE users SET totp_pending = ? WHERE username = ?", (_enc(secret), username))
        c.commit()
    label = quote(f"{ISSUER}:{username}")
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&algorithm=SHA1&digits={DIGITS}&period={STEP}"
    return {"secret": secret, "otpauth_uri": uri, "issuer": ISSUER, "account": username}


def _recovery_codes() -> Tuple[List[str], List[str]]:
    plain = ["-".join(secrets.token_hex(2) for _ in range(3)) for _ in range(8)]
    return plain, [_auth.get_password_hash(p) for p in plain]


def confirm_setup(username: str, code: str) -> Dict[str, Any]:
    """Finish set-up with a code from the authenticator app: turn two-factor on and issue 8 single-use recovery codes.

    Returns:
        {"enabled": True, "recovery_codes": [...]} — the codes are shown once and stored only as hashes.

    Raises:
        ValueError: set-up was not started, or the code does not match.
    """
    u = _user(username)
    if not u or not u.get("totp_pending"):
        raise ValueError("start the set-up first")
    secret = _dec(u["totp_pending"])
    step = _match(secret, code, None)
    if step is None:
        raise ValueError("that code does not match — check the authenticator app's clock and try the current code")
    plain, hashed = _recovery_codes()
    with _conn() as c:
        c.execute("UPDATE users SET totp_secret = ?, totp_pending = NULL, totp_enabled = 1, totp_last_step = ?, "
                  "recovery_codes = ? WHERE username = ?", (u["totp_pending"], step, json.dumps(hashed), username))
        c.commit()
    from api.core.accounts import invalidate_cache
    invalidate_cache(username)
    return {"enabled": True, "recovery_codes": plain}


def verify(username: str, code: str) -> bool:
    """A current TOTP code (not replayed) or an unused recovery code; consumes what it uses."""
    u = _user(username)
    if not u or not u.get("totp_enabled") or not code:
        return False
    step = _match(_dec(u["totp_secret"]), code, u.get("totp_last_step"))
    if step is not None:
        with _conn() as c:
            c.execute("UPDATE users SET totp_last_step = ? WHERE username = ?", (step, username))
            c.commit()
        return True
    raw = str(code).strip().lower()
    if "-" in raw:
        codes = json.loads(u.get("recovery_codes") or "[]")
        for i, h in enumerate(codes):
            if _auth.verify_password(raw, h):
                codes.pop(i)
                with _conn() as c:
                    c.execute("UPDATE users SET recovery_codes = ? WHERE username = ?", (json.dumps(codes), username))
                    c.commit()
                return True
    return False


def disable(username: str) -> None:
    """Turn two-factor off and erase the secret and recovery codes (own request with a valid code, or an
    administrator's reset).
    """
    with _conn() as c:
        c.execute("UPDATE users SET totp_secret = NULL, totp_pending = NULL, totp_enabled = 0, totp_last_step = NULL, "
                  "recovery_codes = NULL WHERE username = ?", (username,))
        c.commit()
    from api.core.accounts import invalidate_cache
    invalidate_cache(username)

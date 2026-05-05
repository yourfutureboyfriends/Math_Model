"""Authentication utilities."""

import hashlib
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

try:
    from api.config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, ROLE_PERMISSIONS
    from api.models.auth import User, TokenData
except ImportError:
    from config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, ROLE_PERMISSIONS
    from models.auth import User, TokenData

logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
token_blacklist: set = set()


def prehash_password(password: str) -> str:
    """Pre-hash password to work within bcrypt's 72-byte limit."""
    return hashlib.sha256(password.encode()).hexdigest()[:32]


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt with pre-hashing."""
    prehashed = prehash_password(password)
    return bcrypt.hashpw(prehashed.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    prehashed = prehash_password(plain_password)
    return bcrypt.checkpw(prehashed.encode(), hashed_password.encode())


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_db_path() -> str:
    """Get absolute path to database file."""
    import os
    # Database is in api/ directory relative to this file
    db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(db_dir, "macro_terminal.db")


async def get_user_from_db(username: str) -> Optional[Dict[str, Any]]:
    """Fetch user from database."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT username, hashed_password, role, display_name FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "username": row[0],
                "hashed_password": row[1],
                "role": row[2],
                "display_name": row[3],
            }
        return None
    except Exception as e:
        logger.error(f"[AUTH] Failed to fetch user: {e}")
        return None


async def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate a user by username and password."""
    user = await get_user_from_db(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Get current user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token in token_blacklist:
        raise credentials_exception

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role", "analyst")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username, role=role)
    except JWTError:
        raise credentials_exception

    user = await get_user_from_db(token_data.username)
    if user is None:
        raise credentials_exception

    permissions = ROLE_PERMISSIONS.get(role, [])
    return User(
        username=user["username"],
        role=role,
        display_name=user["display_name"],
        permissions=permissions if permissions else [],
    )


def require_permission(permission: str):
    """Dependency factory to check if user has required permission."""
    async def permission_checker(current_user: User = Depends(get_current_user)):
        if "*" in current_user.permissions or permission in current_user.permissions:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission} required",
        )
    return permission_checker


def init_users_table():
    """Create users table and seed default users if empty."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                role TEXT NOT NULL,
                display_name TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                last_login TEXT
            )
        """
        )

        cursor = conn.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]

        if count == 0:
            default_users = [
                ("admin", get_password_hash("admin123"), "admin", "Administrator"),
                ("pm", get_password_hash("pm123"), "pm", "Portfolio Manager"),
                ("analyst", get_password_hash("analyst123"), "analyst", "Macro Analyst"),
                ("risk", get_password_hash("risk123"), "risk", "Risk Officer"),
                ("quant", get_password_hash("quant123"), "quant", "Quant Researcher"),
            ]
            conn.executemany(
                """
                INSERT INTO users (username, hashed_password, role, display_name)
                VALUES (?, ?, ?, ?)
            """,
                default_users,
            )
            conn.commit()
            logger.info("[AUTH] Seeded 5 default users")

        conn.close()
    except Exception as e:
        logger.warning(f"[AUTH] Users table init failed: {e}")

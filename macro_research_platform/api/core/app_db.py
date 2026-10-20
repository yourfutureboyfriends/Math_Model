"""The application database file (users, positions, trades, NAV, signal performance...).

One resolver for every module that opens it directly with sqlite3, so none can drift onto
a different file (the brokerage sync and signal-performance modules once hard-coded a stale
copy at the project root). DATABASE_URL (sqlite:///...) overrides; relative paths resolve
next to the api package, then its parent.
"""
import os


def app_db_path() -> str:
    from api.config import DATABASE_URL
    path = (DATABASE_URL or "sqlite:///macro_terminal.db").split("sqlite:///", 1)[-1]
    if os.path.isabs(path):
        return path
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))        # api/
    for base in (here, os.path.dirname(here)):
        candidate = os.path.normpath(os.path.join(base, path))
        if os.path.exists(candidate):
            return candidate
    return os.path.normpath(os.path.join(here, path))

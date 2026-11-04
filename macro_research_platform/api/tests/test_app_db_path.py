"""Every module that opens the application DB directly must open the same file."""
from pathlib import Path


def test_all_direct_sqlite_users_share_the_app_db():
    from api.core.app_db import app_db_path
    from api.performance import bootstrap, signal_tracker
    from api.brokerage import portfolio_sync
    target = Path(app_db_path()).resolve()
    for p in (bootstrap.DB_PATH, signal_tracker.DB_PATH, portfolio_sync.DB_PATH):   # (auth is patched to a temp DB by other tests)
        assert Path(p).resolve() == target, p

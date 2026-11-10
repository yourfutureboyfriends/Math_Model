"""
Shared fixtures for the regression suite.

These tests lock in bugs that were found and fixed across prior sessions so they can never
silently regress. They exercise the REAL endpoints in-process via FastAPI's TestClient, so
assertions are kept STRUCTURAL (ranges, field presence, label strings) rather than tied to a
specific live value.

The client is authenticated (admin JWT): writes and fund-sensitive reads require a token.

Run:  pytest api/tests/regression/ -v
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    # Users live in a throwaway DB so the suite never touches (or depends on) real accounts.
    import api.core.auth as auth
    from api.core import accounts
    path = str(tmp_path_factory.mktemp("users") / "users.db")
    mp = pytest.MonkeyPatch()
    mp.setattr(auth, "get_db_path", lambda: path)
    accounts.migrate()
    accounts.set_password("admin", "Regression-Admin-Pass-2026!")
    from api.main import app
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user('admin'))}"
        yield c
    mp.undo()
    accounts.invalidate_cache()

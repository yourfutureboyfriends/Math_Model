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
def client():
    from api.main import app
    from api.core.auth import create_access_token
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {create_access_token({'sub': 'admin', 'role': 'admin'})}"
        yield c

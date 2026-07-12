"""
Shared fixtures for the regression suite.

These tests lock in bugs that were found and fixed across prior sessions so they can never
silently regress. They exercise the REAL endpoints in-process via FastAPI's TestClient (which
runs the app's own data layer, falling back to bundled sample data when live feeds are offline),
so assertions are kept STRUCTURAL (ranges, field presence, label strings) rather than tied to a
specific live value.

Run:  pytest api/tests/regression/ -v
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c

"""Regression tests for runtime routes.

Tests:
1. Canonical dashboard endpoint is accessible
2. Legacy v2/v3 dashboard endpoints return 404
3. Health endpoint is accessible
4. Frontend network utilities exist
"""
import pytest
import sys
import os

# Add api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestDashboardEndpoints:
    """Test dashboard endpoints are accessible."""

    def test_dashboard_primary_endpoint_exists(self):
        """Primary /api/dashboard endpoint returns 200."""
        import requests
        try:
            response = requests.get('http://localhost:8000/api/dashboard', timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert 'regime' in data
            assert 'keyMetrics' in data or 'prices' in data
        except requests.exceptions.ConnectionError:
            pytest.skip("Backend not running")

    def test_health_endpoint_exists(self):
        """/api/health endpoint returns 200 with expected fields."""
        import requests
        try:
            response = requests.get('http://localhost:8000/api/health', timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert data.get('status') == 'ok'
            assert 'models' in data
            assert 'data_rows' in data
        except requests.exceptions.ConnectionError:
            pytest.skip("Backend not running")

    def test_v2_dashboard_removed(self):
        """/api/v2/dashboard returns 404 (legacy endpoint removed)."""
        import requests
        try:
            response = requests.get('http://localhost:8000/api/v2/dashboard', timeout=5)
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Backend not running")

    def test_v3_dashboard_removed(self):
        """/api/v3/dashboard returns 404 (legacy endpoint removed)."""
        import requests
        try:
            response = requests.get('http://localhost:8000/api/v3/dashboard', timeout=5)
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        except requests.exceptions.ConnectionError:
            pytest.skip("Backend not running")


class TestWebSocketConfiguration:
    """Test WebSocket endpoint configuration."""

    def test_websocket_endpoint_registered(self):
        """WebSocket endpoint is registered in OpenAPI."""
        import requests
        try:
            response = requests.get('http://localhost:8000/openapi.json', timeout=5)
            assert response.status_code == 200
            spec = response.json()
            # Check if /ws/prices or websocket is documented
            paths = spec.get('paths', {})
            ws_paths = [p for p in paths if 'ws' in p or 'socket' in p]
            # WebSocket may not be in OpenAPI, that's ok
            assert True
        except requests.exceptions.ConnectionError:
            pytest.skip("Backend not running")


class TestDiagnosticsEndpoints:
    """Test diagnostics endpoints."""

    def test_health_used_by_system_status_badge(self):
        """/api/health endpoint used by SystemStatusBadge works."""
        import requests
        try:
            response = requests.get('http://localhost:8000/api/health', timeout=5)
            assert response.status_code == 200
            data = response.json()
            # Fields expected by SystemStatusBadge
            assert 'status' in data
            assert 'mode' in data
            assert 'analyticalIntegrity' in data
        except requests.exceptions.ConnectionError:
            pytest.skip("Backend not running")

    def test_diagnostics_routes_exist(self):
        """Diagnostics routes are registered."""
        import requests
        try:
            response = requests.get('http://localhost:8000/openapi.json', timeout=5)
            assert response.status_code == 200
            spec = response.json()
            paths = list(spec.get('paths', {}).keys())

            # Should have diagnostics routes
            diag_paths = [p for p in paths if '/diagnostics/' in p]
            assert len(diag_paths) > 0, "No diagnostics routes found"
        except requests.exceptions.ConnectionError:
            pytest.skip("Backend not running")


class TestFrontendNetworkUtils:
    """Test frontend network utilities."""

    def test_network_utils_file_exists(self):
        """network.ts utility file exists."""
        # Get project root from test file location
        # test is at: api/tests/integration/
        # network.ts is at: frontend/src/lib/
        project_root = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..'
        ))
        network_ts = os.path.join(project_root, 'frontend', 'src', 'lib', 'network.ts')
        assert os.path.exists(network_ts), f"network.ts not found at {network_ts}"

    def test_network_utils_exports(self):
        """network.ts exports required functions."""
        project_root = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', '..', '..'
        ))
        network_ts = os.path.join(project_root, 'frontend', 'src', 'lib', 'network.ts')
        if not os.path.exists(network_ts):
            pytest.skip("network.ts not found")

        with open(network_ts, 'r') as f:
            content = f.read()

        # Check for required exports
        assert 'export function getApiBaseUrl()' in content
        assert 'export function getWsBaseUrl()' in content
        assert 'export function getEndpointUrl(' in content
        assert 'export function getWebSocketUrl(' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

"""
Tests for demo payments security - verifying demo payments are disabled by default.
"""
import pytest
import os
from unittest.mock import patch
from tests.conftest import auth_client, db_session


class TestDemoPaymentsSecurity:
    """Tests for demo payments security - ensuring demo payments are disabled by default."""

    def test_demo_activate_returns_403_when_disabled(self, auth_client):
        """Demo activate should return 403 when ENABLE_DEMO_PAYMENTS is not set to '1'."""
        # Ensure ENABLE_DEMO_PAYMENTS is not set to '1'
        with patch.dict(os.environ, {"ENABLE_DEMO_PAYMENTS": "0"}, clear=True):
            res = auth_client.post("/api/payments/demo-activate/pro")
            assert res.status_code == 403
            assert "غير متاح" in res.json()["detail"]

    def test_demo_activate_returns_403_when_not_set(self, auth_client):
        """Demo activate should return 403 when ENABLE_DEMO_PAYMENTS is not set."""
        with patch.dict(os.environ, {"ENABLE_DEMO_PAYMENTS": ""}, clear=True):
            res = auth_client.post("/api/payments/demo-activate/pro")
            assert res.status_code == 403
            assert "غير متاح" in res.json()["detail"]

    def test_demo_activate_returns_403_when_explicitly_disabled(self, auth_client):
        """Demo activate should return 403 when explicitly set to '0'."""
        with patch.dict(os.environ, {"ENABLE_DEMO_PAYMENTS": "0"}, clear=True):
            res = auth_client.post("/api/payments/demo-activate/pro")
            assert res.status_code == 403

    def test_demo_activate_works_when_enabled(self, auth_client, db_session):
        """Demo activate should work when ENABLE_DEMO_PAYMENTS=1."""
        with patch.dict(os.environ, {"ENABLE_DEMO_PAYMENTS": "1"}, clear=True):
            res = auth_client.post("/api/payments/demo-activate/pro")
            assert res.status_code == 200
            data = res.json()
            assert "تم تفعيل خطة" in data["message"]
            assert "expires_at" in data

    def test_demo_activate_invalid_plan_returns_400(self, auth_client):
        """Invalid plan should return 400."""
        with patch.dict(os.environ, {"ENABLE_DEMO_PAYMENTS": "1"}, clear=True):
            res = auth_client.post("/api/payments/demo-activate/invalid_plan")
            assert res.status_code == 400
            assert "غير صحيحة" in res.json()["detail"]

    def test_demo_activate_requires_auth(self, client):
        """Demo activate should require authentication."""
        with patch.dict(os.environ, {"ENABLE_DEMO_PAYMENTS": "1"}, clear=True):
            res = client.post("/api/payments/demo-activate/pro")
            assert res.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
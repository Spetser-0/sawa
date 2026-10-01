"""
Tests for share token security - verifying share tokens cannot be used for user authentication.
"""
import pytest
from app.auth import create_access_token, decode_token, create_share_token


class TestShareTokenSecurity:
    """Tests to ensure share tokens cannot be used for user authentication."""

    def test_share_token_cannot_access_me_endpoint(self, client):
        """Share token cannot be used to access /api/auth/me endpoint."""
        # First create a user and get a share token
        res = client.post("/api/auth/register", json={
            "name": "Test User",
            "email": "share_test@test.com",
            "password": "TestPass123!",
        })
        assert res.status_code == 201

        # Create a share token (video-bound)
        from app.auth import create_share_token
        from datetime import timedelta
        share_token = create_share_token("video123", timedelta(hours=1))

        # Clear cookies to ensure we're testing the Authorization header
        client.cookies.clear()

        # Try to use share token to access /api/auth/me
        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {share_token}"})
        # Should return 401 (unauthorized) because share token type is "share_access" not "access"
        assert res.status_code == 401

    def test_normal_access_token_still_works(self, client):
        """Normal access token still works for /api/auth/me."""
        res = client.post("/api/auth/register", json={
            "name": "Normal User",
            "email": "normal@test.com",
            "password": "NormalPass123!",
        })
        assert res.status_code == 201
        access_token = res.json()["access_token"]

        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert res.status_code == 200
        assert res.json()["email"] == "normal@test.com"

    def test_password_reset_token_cannot_access_me(self, client):
        """Password reset token cannot access /api/auth/me."""
        from app.auth import create_access_token
        reset_token = create_access_token({
            "sub": "user123",
            "type": "password_reset"
        })

        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {reset_token}"})
        assert res.status_code == 401

    def test_share_token_with_owner_sub_still_rejected(self, client):
        """Share token with owner_id as sub is still rejected for /api/auth/me."""
        from app.auth import create_access_token
        # Create a token that looks like a share token but has owner_id as sub
        token = create_access_token({
            "sub": "owner123",
            "type": "share_access",
            "video_id": "video123"
        })

        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401

    def test_share_token_cannot_access_protected_video_endpoints(self, client):
        """Share token cannot access protected video endpoints that require user auth."""
        from app.auth import create_share_token
        from datetime import timedelta
        share_token = create_share_token("video123", timedelta(hours=1))

        # Try to access a protected endpoint (e.g., /api/videos/my)
        res = client.get("/api/videos/my", headers={"Authorization": f"Bearer {share_token}"})
        assert res.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
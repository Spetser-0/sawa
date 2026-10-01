"""
Tests for JWT token type preservation in create_access_token.
"""
import pytest
from app.auth import create_access_token, decode_token, create_share_token, verify_share_token


class TestTokenTypePreservation:
    """Tests for JWT token type preservation in create_access_token."""

    def test_token_without_type_gets_default_access(self):
        """Token without explicit type gets default 'access' type."""
        token = create_access_token({"sub": "user123"})
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("type") == "access"
        assert payload.get("sub") == "user123"

    def test_token_with_explicit_access_type_keeps_it(self):
        """Token with explicit 'access' type keeps it."""
        token = create_access_token({"sub": "user123", "type": "access"})
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("type") == "access"

    def test_token_with_share_access_type_preserved(self):
        """Token with 'share_access' type keeps it (not overwritten to 'access')."""
        token = create_access_token({"sub": "user123", "type": "share_access"})
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("type") == "share_access"

    def test_token_with_password_reset_type_preserved(self):
        """Token with 'password_reset' type keeps it (not overwritten to 'access')."""
        token = create_access_token({"sub": "user123", "type": "password_reset"})
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("type") == "password_reset"

    def test_token_with_custom_type_preserved(self):
        """Token with any custom type keeps it (not overwritten to 'access')."""
        token = create_access_token({"sub": "user123", "type": "custom_type"})
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("type") == "custom_type"

    def test_token_with_empty_string_type_gets_default(self):
        """Token with empty string type gets default 'access' (setdefault behavior)."""
        token = create_access_token({"sub": "user123", "type": ""})
        payload = decode_token(token)
        assert payload is not None
        # Empty string is falsy but setdefault only sets if key missing
        # Since key exists with empty string, it keeps empty string
        assert payload.get("type") == ""

    def test_token_preserves_other_fields(self):
        """Token preserves other fields like sub, video_id, etc."""
        token = create_access_token({
            "sub": "user123",
            "type": "share_access",
            "video_id": "video123"
        })
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("sub") == "user123"
        assert payload.get("type") == "share_access"
        assert payload.get("video_id") == "video123"

    def test_exp_claim_is_set(self):
        """Token always has exp claim set."""
        token = create_access_token({"sub": "user123"})
        payload = decode_token(token)
        assert payload is not None
        assert "exp" in payload
        assert isinstance(payload["exp"], int)

    def test_expires_delta_respected(self):
        """Custom expires_delta is respected."""
        from datetime import timedelta
        token = create_access_token({"sub": "user123"}, expires_delta=timedelta(minutes=5))
        payload = decode_token(token)
        assert payload is not None
        assert "exp" in payload
        # exp should be approximately 5 minutes from now
        import time
        expected_exp = int(time.time()) + 5 * 60
        assert abs(payload["exp"] - expected_exp) < 10  # within 10 seconds


class TestShareTokenHelpers:
    """Tests for share token helper functions."""

    def test_create_share_token_creates_valid_token(self):
        """create_share_token creates a valid token with correct payload."""
        from datetime import timedelta
        token = create_share_token("video123", timedelta(hours=1))
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("type") == "share_access"
        assert payload.get("video_id") == "video123"
        assert payload.get("sub") == "share:video123"
        assert "exp" in payload

    def test_create_share_token_default_expiry(self):
        """create_share_token uses 1 hour default expiry."""
        import time
        token = create_share_token("video123")
        payload = decode_token(token)
        expected_exp = int(time.time()) + 3600  # 1 hour
        assert abs(payload["exp"] - expected_exp) < 10

    def test_create_share_token_custom_expiry(self):
        """create_share_token respects custom expires_delta."""
        from datetime import timedelta
        import time
        token = create_share_token("video123", timedelta(minutes=30))
        payload = decode_token(token)
        expected_exp = int(time.time()) + 1800  # 30 minutes
        assert abs(payload["exp"] - expected_exp) < 10

    def test_verify_share_token_valid(self):
        """verify_share_token returns True for matching valid token."""
        token = create_share_token("video123")
        assert verify_share_token(token, "video123") is True

    def test_verify_share_token_wrong_video_id(self):
        """verify_share_token returns False for different video_id."""
        token = create_share_token("video123")
        assert verify_share_token(token, "video456") is False

    def test_verify_share_token_invalid_type(self):
        """verify_share_token returns False for token with wrong type."""
        token = create_access_token({"sub": "user123", "type": "access"})
        assert verify_share_token(token, "video123") is False

    def test_verify_share_token_wrong_sub(self):
        """verify_share_token returns False for token with wrong sub."""
        token = create_access_token({"sub": "user123", "type": "share_access", "video_id": "video123"})
        assert verify_share_token(token, "video123") is False

    def test_verify_share_token_missing_video_id(self):
        """verify_share_token returns False for token missing video_id."""
        token = create_access_token({"sub": "share:video123", "type": "share_access"})
        assert verify_share_token(token, "video123") is False

    def test_verify_share_token_expired(self):
        """verify_share_token returns False for expired token."""
        from datetime import timedelta
        token = create_access_token(
            {"sub": "share:video123", "type": "share_access", "video_id": "video123"},
            expires_delta=timedelta(seconds=-1)
        )
        assert verify_share_token(token, "video123") is False

    def test_verify_share_token_malformed(self):
        """verify_share_token returns False for malformed token."""
        assert verify_share_token("invalid.token.string", "video123") is False

    def test_verify_share_token_access_token(self):
        """verify_share_token returns False for normal access token."""
        token = create_access_token({"sub": "user123", "type": "access"})
        assert verify_share_token(token, "video123") is False

    def test_verify_share_token_password_reset_token(self):
        """verify_share_token returns False for password reset token."""
        token = create_access_token({"sub": "user123", "type": "password_reset"})
        assert verify_share_token(token, "video123") is False

    def test_verify_share_token_with_owner_sub(self):
        """verify_share_token returns False for token with owner_id as sub."""
        token = create_access_token({
            "sub": "owner123",
            "type": "share_access",
            "video_id": "video123"
        })
        assert verify_share_token(token, "video123") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
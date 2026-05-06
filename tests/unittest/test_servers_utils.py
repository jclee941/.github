import hashlib
import hmac
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from pr_agent.servers.utils import verify_signature, DefaultDictWithTimeout, RateLimitExceeded


# =============================================================================
# Tests for verify_signature()
# =============================================================================

class TestVerifySignature:
    """Test suite for GitHub webhook signature verification."""

    def get_valid_signature(self, payload_body: bytes, secret_token: str) -> str:
        """Helper to generate a valid SHA256 signature."""
        hash_object = hmac.new(
            secret_token.encode("utf-8"),
            msg=payload_body,
            digestmod=hashlib.sha256,
        )
        return "sha256=" + hash_object.hexdigest()

    # -------------------------------------------------------------------------
    # Happy path
    # -------------------------------------------------------------------------

    def test_valid_signature_passes(self):
        """Valid HMAC-SHA256 signature should not raise."""
        payload = b'{"action":"opened"}'
        secret = "my-secret-token"
        signature = self.get_valid_signature(payload, secret)

        # Should not raise
        verify_signature(payload, secret, signature)

    def test_valid_signature_with_complex_payload(self):
        """Valid signature with a complex JSON payload."""
        payload = b'{"action":"opened","pull_request":{"number":123,"title":"Test PR"}}'
        secret = "webhook_secret_xyz"
        signature = self.get_valid_signature(payload, secret)

        verify_signature(payload, secret, signature)

    # -------------------------------------------------------------------------
    # Missing / malformed signature header
    # -------------------------------------------------------------------------

    def test_missing_signature_header_raises_403(self):
        """Missing x-hub-signature-256 header should return 403."""
        payload = b'{"action":"opened"}'
        secret = "my-secret-token"

        with pytest.raises(HTTPException) as exc_info:
            verify_signature(payload, secret, None)
        assert exc_info.value.status_code == 403
        assert "missing" in exc_info.value.detail.lower()

    def test_empty_signature_header_raises_403(self):
        """Empty signature header should return 403."""
        payload = b'{"action":"opened"}'
        secret = "my-secret-token"

        with pytest.raises(HTTPException) as exc_info:
            verify_signature(payload, secret, "")
        assert exc_info.value.status_code == 403

    # -------------------------------------------------------------------------
    # Signature mismatch
    # -------------------------------------------------------------------------

    def test_wrong_signature_raises_403(self):
        """Incorrect signature should return 403."""
        payload = b'{"action":"opened"}'
        secret = "my-secret-token"
        wrong_sig = "sha256=" + "a" * 64  # invalid hex

        with pytest.raises(HTTPException) as exc_info:
            verify_signature(payload, secret, wrong_sig)
        assert exc_info.value.status_code == 403
        assert "didn't match" in exc_info.value.detail.lower()

    def test_signature_with_wrong_prefix_raises_403(self):
        """Signature with wrong prefix (not sha256=) should return 403."""
        payload = b'{"action":"opened"}'
        secret = "my-secret-token"
        sig_without_prefix = self.get_valid_signature(payload, secret).replace("sha256=", "")

        with pytest.raises(HTTPException) as exc_info:
            verify_signature(payload, secret, sig_without_prefix)
        assert exc_info.value.status_code == 403

    def test_tampered_payload_fails_verification(self):
        """Tampering with payload after signing should fail."""
        original_payload = b'{"action":"opened"}'
        secret = "my-secret-token"
        signature = self.get_valid_signature(original_payload, secret)

        tampered_payload = b'{"action":"closed"}'

        with pytest.raises(HTTPException) as exc_info:
            verify_signature(tampered_payload, secret, signature)
        assert exc_info.value.status_code == 403

    def test_signature_with_wrong_secret_fails(self):
        """Signature computed with wrong secret should fail."""
        payload = b'{"action":"opened"}'
        correct_secret = "correct-secret"
        wrong_secret = "wrong-secret"
        signature = self.get_valid_signature(payload, correct_secret)

        with pytest.raises(HTTPException) as exc_info:
            verify_signature(payload, wrong_secret, signature)
        assert exc_info.value.status_code == 403

    # -------------------------------------------------------------------------
    # Edge cases
    # -------------------------------------------------------------------------

    def test_empty_payload(self):
        """Empty payload body should still verify correctly."""
        payload = b""
        secret = "my-secret-token"
        signature = self.get_valid_signature(payload, secret)

        verify_signature(payload, secret, signature)

    def test_unicode_secret(self):
        """Unicode characters in secret token should work."""
        payload = b'{"action":"opened"}'
        secret = "secret-with-unicode-\u4e2d\u6587"
        signature = self.get_valid_signature(payload, secret)

        verify_signature(payload, secret, signature)

    def test_binary_payload(self):
        """Binary payload should verify correctly."""
        payload = bytes([0, 1, 2, 3, 255, 254, 253])
        secret = "binary-secret"
        signature = self.get_valid_signature(payload, secret)

        verify_signature(payload, secret, signature)

    def test_timing_safe_comparison(self):
        """Uses hmac.compare_digest for timing-safe comparison."""
        payload = b'{"action":"opened"}'
        secret = "my-secret-token"
        almost_correct = self.get_valid_signature(payload, secret)
        wrong_sig = almost_correct[:-1] + ("a" if almost_correct[-1] != "a" else "b")

        with pytest.raises(HTTPException) as exc_info:
            verify_signature(payload, secret, wrong_sig)
        assert exc_info.value.status_code == 403


# =============================================================================
# Tests for DefaultDictWithTimeout
# =============================================================================

class TestDefaultDictWithTimeout:
    """Test suite for TTL-based defaultdict."""

    def test_basic_getitem_sets_default(self):
        """Accessing missing key should set and return default value."""
        d = DefaultDictWithTimeout(default_factory=list, ttl=10)
        result = d["missing"]
        assert result == []
        assert "missing" in d

    def test_setitem_updates_access_time(self):
        """Setting a key should update its access time."""
        d = DefaultDictWithTimeout(default_factory=int, ttl=10)
        d["key"] = 5
        assert d["key"] == 5

        # Override
        d["key"] = 10
        assert d["key"] == 10

    def test_delitem_removes_key_and_time(self):
        """Deleting a key should remove both the key and its timestamp."""
        d = DefaultDictWithTimeout(default_factory=int, ttl=10)
        d["key"] = 5
        del d["key"]

        assert "key" not in d

    def test_ttl_none_skips_eviction(self):
        """When ttl=None, refresh is a no-op and keys never expire."""
        d = DefaultDictWithTimeout(default_factory=int, ttl=None)
        d["key"] = 1

        # Even if refresh is called, it should be a no-op when ttl=None
        d._DefaultDictWithTimeout__refresh()

        assert "key" in d
        assert d["key"] == 1

    def test_update_key_time_on_get_true(self):
        """When update_key_time_on_get=True, get updates access time."""
        d = DefaultDictWithTimeout(default_factory=int, ttl=10, update_key_time_on_get=True)
        d["key"] = 1

        result = d["key"]
        assert result == 1
        assert "key" in d

    def test_update_key_time_on_get_false(self):
        """When update_key_time_on_get=False, get does NOT update access time."""
        d = DefaultDictWithTimeout(default_factory=int, ttl=10, update_key_time_on_get=False)
        d["key"] = 1

        result = d["key"]
        assert result == 1
        assert "key" in d

    def test_dict_behavior_preserved(self):
        """Standard dict operations should still work."""
        d = DefaultDictWithTimeout(default_factory=int, ttl=100)
        d["a"] = 1
        d["b"] = 2

        assert d["a"] == 1
        assert d["b"] == 2
        assert len(d) == 2

        d["a"] = 10
        assert d["a"] == 10

        del d["a"]
        assert "a" not in d

    def test_default_factory_per_missing_key(self):
        """Default factory should be called fresh for each missing key."""
        d = DefaultDictWithTimeout(default_factory=list, ttl=100)
        result1 = d["key1"]
        result2 = d["key2"]

        assert result1 == []
        assert result2 == []
        assert result1 is not result2  # different list instances

    def test_multiple_keys_behavior(self):
        """Multiple keys should coexist independently."""
        d = DefaultDictWithTimeout(default_factory=int, ttl=10)
        d["a"] = 1
        d["b"] = 2
        d["c"] = 3

        assert d["a"] == 1
        assert d["b"] == 2
        assert d["c"] == 3
        assert len(d) == 3

        del d["b"]
        assert "a" in d
        assert "b" not in d
        assert "c" in d


# =============================================================================
# Tests for RateLimitExceeded
# =============================================================================

class TestRateLimitExceeded:
    """Test suite for RateLimitExceeded exception."""

    def test_raise_and_catch(self):
        """Should be raisable and catchable as an Exception."""
        with pytest.raises(RateLimitExceeded):
            raise RateLimitExceeded("API rate limit exceeded")

    def test_message_preserved(self):
        """Exception message should be preserved."""
        msg = "GitHub API rate limit exceeded"
        try:
            raise RateLimitExceeded(msg)
        except RateLimitExceeded as e:
            assert str(e) == msg

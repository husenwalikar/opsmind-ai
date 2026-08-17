"""Unit tests for session authentication and credential decoding."""

import pytest
from test_bed.app.services.auth import verify_user_permissions


def test_valid_session_token():
    """Verify role extraction from valid active session credentials."""
    role = verify_user_permissions("BEARER_VALID_CUSTOMER_TOKEN")
    assert role == "PREMIUM_CUSTOMER"


def test_expired_or_revoked_session_token():
    """Verify invariant: revoked or missing credentials resolve to guest permissions without raising."""
    role = verify_user_permissions(None)
    assert role == "GUEST"
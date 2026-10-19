"""Unit tests for CAS token issuance and JWKS generation (T-XET-03)."""

import time

import pytest
from jwt.exceptions import ExpiredSignatureError, InvalidAudienceError

from ubuntubio.auth.cas_tokens import CasTokenManager


def test_jwks_structure() -> None:
    """Verify generated JWKS contains valid RSA key fields."""
    manager = CasTokenManager()
    jwks = manager.get_public_jwks()

    assert "keys" in jwks
    assert len(jwks["keys"]) == 1
    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["kid"] == "ubuntubio-cas-key-1"
    assert "n" in key and "e" in key


def test_token_issue_and_verify() -> None:
    """Verify that a signed token can be successfully verified and decoded."""
    manager = CasTokenManager(issuer="http://test-server:8000", audience="openxet")
    token = manager.issue_token(
        subject="orcid:0000-0002-1825-0097",
        repo_slug="cameroon-amr/klebsiella-yaounde",
        action="write",
    )

    claims = manager.verify_token(token)
    assert claims["iss"] == "http://test-server:8000"
    assert claims["aud"] == "openxet"
    assert claims["sub"] == "orcid:0000-0002-1825-0097"
    assert claims["repo"] == "cameroon-amr/klebsiella-yaounde"
    assert claims["action"] == "write"
    assert claims["exp"] > time.time()


def test_expired_token_rejected() -> None:
    """Verify that an expired token raises ExpiredSignatureError."""
    # Create manager with negative lifetime to simulate instant expiry
    manager = CasTokenManager(token_lifetime_seconds=-10)
    token = manager.issue_token(
        subject="orcid:0000-0001-0000-0000",
        repo_slug="org/dataset",
    )

    with pytest.raises(ExpiredSignatureError):
        manager.verify_token(token)


def test_invalid_audience_rejected() -> None:
    """Verify that token with mismatched audience is rejected."""
    manager = CasTokenManager(audience="openxet")
    token = manager.issue_token(
        subject="orcid:0000-0001-0000-0000",
        repo_slug="org/dataset",
    )

    verifier_different_aud = CasTokenManager(audience="other_service")
    # Share key for signature check
    verifier_different_aud._public_key = manager._public_key

    with pytest.raises(InvalidAudienceError):
        verifier_different_aud.verify_token(token)

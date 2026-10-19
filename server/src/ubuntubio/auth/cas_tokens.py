"""CAS token issuance and JWKS key management for OpenXet authentication."""

from __future__ import annotations

import time
from typing import Any, Literal

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ubuntubio.core.logging import get_logger

logger = get_logger("ubuntubio.auth.cas_tokens")


class CasTokenManager:
    """Manages RSA keys and signs short-lived JWTs for OpenXet CAS authentication."""

    def __init__(
        self,
        issuer: str = "http://localhost:8000",
        audience: str = "openxet",
        key_id: str = "ubuntubio-cas-key-1",
        token_lifetime_seconds: int = 900,  # 15 minutes
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.key_id = key_id
        self.token_lifetime = token_lifetime_seconds

        # Generate RSA private/public keypair
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._public_key = self._private_key.public_key()

    def get_public_jwks(self) -> dict[str, list[dict[str, Any]]]:
        """Generate JWKS (JSON Web Key Set) representation of the public key."""
        public_numbers = self._public_key.public_numbers()

        def int_to_base64url(val: int) -> str:
            byte_length = (val.bit_length() + 7) // 8
            val_bytes = val.to_bytes(byte_length, "big")
            return jwt.utils.base64url_encode(val_bytes).decode("ascii")

        jwk: dict[str, Any] = {
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": self.key_id,
            "n": int_to_base64url(public_numbers.n),
            "e": int_to_base64url(public_numbers.e),
        }
        return {"keys": [jwk]}

    def issue_token(
        self,
        subject: str,
        repo_slug: str,
        action: Literal["read", "write"] = "read",
        custom_claims: dict[str, Any] | None = None,
    ) -> str:
        """Sign a short-lived RS256 JWT scoped to a repository and access level."""
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "sub": subject,
            "aud": self.audience,
            "iat": now,
            "nbf": now,
            "exp": now + self.token_lifetime,
            "repo": repo_slug,
            "action": action,
        }
        if custom_claims:
            payload.update(custom_claims)

        pem_private = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        logger.info(
            "Issued short-lived CAS token",
            extra={
                "subject": subject,
                "repo_slug": repo_slug,
                "action": action,
                "lifetime_sec": self.token_lifetime,
            },
        )
        return jwt.encode(
            payload,
            pem_private,
            algorithm="RS256",
            headers={"kid": self.key_id},
        )

    def verify_token(self, token: str, expected_repo: str | None = None) -> dict[str, Any]:
        """Verify and decode a CAS token using the public key."""
        pem_public = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        decoded: dict[str, Any] = jwt.decode(
            token,
            pem_public,
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
        )
        if expected_repo and decoded.get("repo") != expected_repo:
            logger.warning(
                "CAS token verification failed: repo scope mismatch",
                extra={
                    "token_repo": decoded.get("repo"),
                    "expected_repo": expected_repo,
                },
            )
            raise ValueError(f"Token scoped to '{decoded.get('repo')}', expected '{expected_repo}'")
        return decoded

"""Personal Access Token (PAT) generation, verification, and revocation."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import PersonalAccessTokenModel, UserModel

logger = get_logger("ubuntubio.auth.pat")

TOKEN_PREFIX = "ubp_"


def generate_token_pair() -> tuple[str, str]:
    """Generate a raw secure token and its SHA-256 hash."""
    random_part = secrets.token_urlsafe(32)
    raw_token = f"{TOKEN_PREFIX}{random_part}"
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of a raw token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


async def create_personal_access_token(
    session: AsyncSession,
    user_id: str | None,
    name: str,
    scope: Literal["read", "write", "admin"] = "read",
    org_id: str | None = None,
    expires_in_days: int | None = 90,
) -> tuple[str, PersonalAccessTokenModel]:
    """Create and persist a new PAT, returning the raw token string once."""
    raw_token, token_hash = generate_token_pair()

    now = datetime.now(UTC)
    expires_at = now + timedelta(days=expires_in_days) if expires_in_days else None

    token_record = PersonalAccessTokenModel(
        token_hash=token_hash,
        name=name,
        scope=scope,
        user_id=user_id,
        org_id=org_id,
        expires_at=expires_at,
        created_at=now,
    )
    session.add(token_record)
    await session.commit()
    await session.refresh(token_record)

    logger.info(
        "Created Personal Access Token",
        extra={
            "token_id": token_record.id,
            "user_id": user_id,
            "token_name": name,
            "scope": scope,
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
    )

    return raw_token, token_record


async def authenticate_token(
    session: AsyncSession,
    raw_token: str,
) -> tuple[PersonalAccessTokenModel, UserModel | None] | None:
    """Authenticate an incoming raw token, returning the token record and associated user."""
    if not raw_token.startswith(TOKEN_PREFIX):
        return None

    thash = hash_token(raw_token)
    now = datetime.now(UTC)

    stmt = select(PersonalAccessTokenModel).where(
        PersonalAccessTokenModel.token_hash == thash,
        PersonalAccessTokenModel.revoked_at.is_(None),
    )
    result = await session.execute(stmt)
    token_record = result.scalar_one_or_none()

    if not token_record:
        return None

    # Check expiration
    if token_record.expires_at:
        exp = token_record.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp < now:
            return None

    user: UserModel | None = None
    if token_record.user_id:
        user_stmt = select(UserModel).where(UserModel.id == token_record.user_id)
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()

    return token_record, user


async def revoke_token(
    session: AsyncSession,
    token_id: str,
    user_id: str,
) -> bool:
    """Revoke a token belonging to the given user."""
    stmt = select(PersonalAccessTokenModel).where(
        PersonalAccessTokenModel.id == token_id,
        PersonalAccessTokenModel.user_id == user_id,
    )
    result = await session.execute(stmt)
    token = result.scalar_one_or_none()
    if not token:
        return False

    token.revoked_at = datetime.now(UTC)
    await session.commit()
    logger.info(
        "Revoked Personal Access Token",
        extra={"token_id": token_id, "user_id": user_id},
    )
    return True

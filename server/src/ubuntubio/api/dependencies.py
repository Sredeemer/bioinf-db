"""FastAPI dependencies for authentication, repository resolution, and session management."""

from __future__ import annotations

import base64
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.auth.pat import authenticate_token
from ubuntubio.db.models import RepositoryModel, UserModel
from ubuntubio.db.session import get_db_session


async def get_optional_user(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_db_session),
) -> UserModel | None:
    """Extract authenticated user from Bearer or Basic authorization header."""
    if not authorization:
        return None

    raw_token: str | None = None
    if authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()
    elif authorization.startswith("Basic "):
        try:
            encoded = authorization.removeprefix("Basic ").strip()
            decoded = base64.b64decode(encoded).decode("utf-8")
            # In Git basic auth, username may be user or token; password is the PAT
            if ":" in decoded:
                _, password = decoded.split(":", 1)
                raw_token = password.strip()
            else:
                raw_token = decoded.strip()
        except Exception:
            return None

    if not raw_token:
        return None

    auth_result = await authenticate_token(session, raw_token)
    if not auth_result:
        return None

    _token_record, user = auth_result
    return user


async def require_authenticated_user(
    user: UserModel | None = Depends(get_optional_user),
) -> UserModel:
    """Enforce that caller has a valid authenticated session or token."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_repository_by_slug(
    owner: str,
    name: str,
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryModel:
    """Fetch repository by owner slug and name, or 404."""
    clean_name = name.removesuffix(".git")
    slug = f"{owner}/{clean_name}"
    stmt = select(RepositoryModel).where(RepositoryModel.slug == slug)
    res = await session.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{slug}' not found.",
        )
    return repo

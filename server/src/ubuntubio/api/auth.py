"""Authentication and token management API routes (M1-03, M1-04)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.api.dependencies import require_authenticated_user
from ubuntubio.api.schemas import (
    CreateTokenRequest,
    DeviceCodeResponse,
    DeviceTokenRequest,
    DeviceVerifyRequest,
    TokenCreatedResponse,
)
from ubuntubio.auth.pat import create_personal_access_token, revoke_token
from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import DeviceAuthorizationModel, PersonalAccessTokenModel, UserModel
from ubuntubio.db.session import get_db_session

USER_CODE_CHARSET = "BCDFGHJKLMNPQRSTVWXYZ23456789"


def generate_user_code() -> str:
    """Generate a clean, unambiguous user code in UBIO-XXXX-XX format."""
    part1 = "".join(secrets.choice(USER_CODE_CHARSET) for _ in range(4))
    part2 = "".join(secrets.choice(USER_CODE_CHARSET) for _ in range(2))
    return f"UBIO-{part1}-{part2}"


router = APIRouter(prefix="/api/auth", tags=["Auth"])
logger = get_logger("ubuntubio.api.auth")


class TokenSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    scope: str
    expires_at: Any
    created_at: Any
    revoked_at: Any


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    orcid_id: str
    name: str
    email: str | None


class DevLoginRequest(BaseModel):
    orcid_id: str
    name: str
    email: str | None = None


@router.get("/whoami", response_model=UserResponse)
async def whoami(user: UserModel = Depends(require_authenticated_user)) -> UserResponse:
    """Return the profile of the authenticated caller."""
    return UserResponse.model_validate(user)


@router.post("/tokens", response_model=TokenCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_token(
    payload: CreateTokenRequest,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> TokenCreatedResponse:
    """Generate a new personal access token with requested scopes."""
    raw_token, token_record = await create_personal_access_token(
        session=session,
        user_id=user.id,
        name=payload.name,
        scope=payload.scope,
        expires_in_days=payload.expires_in_days,
    )
    return TokenCreatedResponse(
        id=token_record.id,
        name=token_record.name,
        scope=token_record.scope,
        raw_token=raw_token,
        expires_at=token_record.expires_at,
        created_at=token_record.created_at,
    )


@router.get("/tokens", response_model=list[TokenSummaryResponse])
async def list_tokens(
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[TokenSummaryResponse]:
    """List all active and revoked tokens owned by caller."""
    stmt = (
        select(PersonalAccessTokenModel)
        .where(PersonalAccessTokenModel.user_id == user.id)
        .order_by(PersonalAccessTokenModel.created_at.desc())
    )
    res = await session.execute(stmt)
    tokens = res.scalars().all()
    return [TokenSummaryResponse.model_validate(t) for t in tokens]


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_token(
    token_id: str,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Revoke an existing token."""
    revoked = await revoke_token(session, token_id, user.id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found or already revoked.",
        )


@router.get("/orcid/authorize")
async def orcid_authorize(
    request: Request,
    redirect_uri: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    """Redirect user agent to ORCID OAuth2 login dialog."""
    callback = (
        redirect_uri
        or (settings.ORCID_REDIRECT_URI if settings.ORCID_REDIRECT_URI else None)
        or f"{settings.API_URL}/api/auth/orcid/callback"
    )
    auth_url = (
        f"{settings.ORCID_AUTHORIZE_URL}?"
        f"client_id={settings.ORCID_CLIENT_ID}&"
        "response_type=code&"
        "scope=/authenticate&"
        f"redirect_uri={callback}"
    )
    if state:
        auth_url += f"&state={state}"
    return RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)


@router.get("/orcid/callback")
async def orcid_callback(
    code: str,
    request: Request,
    state: str | None = None,
    redirect_uri: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> Any:
    """Exchange ORCID authorization code for token, upsert user, and mint session PAT."""
    callback_uri = (
        redirect_uri
        or (settings.ORCID_REDIRECT_URI if settings.ORCID_REDIRECT_URI else None)
        or f"{settings.API_URL}/api/auth/orcid/callback"
    )
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            settings.ORCID_TOKEN_URL,
            data={
                "client_id": settings.ORCID_CLIENT_ID,
                "client_secret": settings.ORCID_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_uri,
            },
            headers={"Accept": "application/json"},
        )

    if token_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Failed to authenticate with ORCID: {token_resp.text}",
        )

    token_data = token_resp.json()
    orcid_id = token_data.get("orcid")
    name = token_data.get("name") or f"Researcher {orcid_id}"

    if not orcid_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ORCID response did not include an 'orcid' identifier.",
        )

    # Upsert user record
    stmt = select(UserModel).where(UserModel.orcid_id == orcid_id)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        user = UserModel(
            orcid_id=orcid_id,
            name=name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    # Mint session token
    raw_token, token_record = await create_personal_access_token(
        session=session,
        user_id=user.id,
        name="ORCID Web Session",
        scope="write",
        expires_in_days=30,
    )

    logger.info(
        "Processed ORCID OAuth login",
        extra={"orcid_id": orcid_id, "user_id": user.id},
    )

    # Check if login was initiated by CLI loopback
    if state and state.startswith("cli_port_"):
        port_num = state.split("_")[-1]
        loopback_url = f"http://127.0.0.1:{port_num}/callback?token={raw_token}"
        return RedirectResponse(url=loopback_url, status_code=status.HTTP_302_FOUND)

    # If caller is browser accepting HTML or state is set, redirect to web callback
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header or state:
        redirect_url = f"{settings.WEB_URL}/auth/callback?token={raw_token}"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)

    return TokenCreatedResponse(
        id=token_record.id,
        name=token_record.name,
        scope=token_record.scope,
        raw_token=raw_token,
        expires_at=token_record.expires_at,
        created_at=token_record.created_at,
    )


@router.post("/dev-login", response_model=TokenCreatedResponse)
async def dev_login(
    payload: DevLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenCreatedResponse:
    """Development/Sandbox helper: creates or retrieves user by ORCID and mints a PAT."""
    if settings.ENV != "development" and not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev-login is only enabled in development environments.",
        )

    stmt = select(UserModel).where(UserModel.orcid_id == payload.orcid_id)
    res = await session.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        user = UserModel(
            orcid_id=payload.orcid_id,
            name=payload.name,
            email=payload.email,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    raw_token, token_record = await create_personal_access_token(
        session=session,
        user_id=user.id,
        name="Dev Session Token",
        scope="admin",
        expires_in_days=30,
    )

    logger.info(
        "Processed dev login",
        extra={"orcid_id": payload.orcid_id, "user_id": user.id},
    )

    return TokenCreatedResponse(
        id=token_record.id,
        name=token_record.name,
        scope=token_record.scope,
        raw_token=raw_token,
        expires_at=token_record.expires_at,
        created_at=token_record.created_at,
    )


# -------------------------------------------------------------------------
# Device Authorization Grant (RFC 8628)
# -------------------------------------------------------------------------


@router.post("/device/code", response_model=DeviceCodeResponse)
async def request_device_code(
    session: AsyncSession = Depends(get_db_session),
) -> DeviceCodeResponse:
    """Initiate an OAuth 2.0 Device Authorization Grant flow (RFC 8628)."""
    device_code = secrets.token_urlsafe(32)
    user_code = generate_user_code()
    expires_in_seconds = 600  # 10 minutes
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)

    record = DeviceAuthorizationModel(
        device_code=device_code,
        user_code=user_code,
        status="pending",
        expires_at=expires_at,
    )
    session.add(record)
    await session.commit()

    base_web = (
        settings.WEB_URL.rstrip("/")
        if settings.ENV == "development"
        else "https://ubuntu-bio-web.vercel.app"
    )
    verification_uri = f"{base_web}/device"
    verification_uri_complete = f"{base_web}/device?user_code={user_code}&auto=1"

    logger.info("Created device authorization request", extra={"user_code": user_code})

    return DeviceCodeResponse(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_in=expires_in_seconds,
        interval=2,
    )


@router.post("/device/verify")
async def verify_device_code(
    payload: DeviceVerifyRequest,
    current_user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Verify and approve a pending device code from the browser."""
    clean_code = payload.user_code.strip().upper()
    if not clean_code.startswith("UBIO-"):
        parts = clean_code.replace("-", "")
        if len(parts) == 6:
            clean_code = f"UBIO-{parts[:4]}-{parts[4:]}"

    stmt = select(DeviceAuthorizationModel).where(DeviceAuthorizationModel.user_code == clean_code)
    res = await session.execute(stmt)
    record = res.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or unrecognized device code.",
        )

    now = datetime.now(UTC)
    rec_expires = (
        record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=UTC)
    )

    if now > rec_expires or record.status == "expired":
        record.status = "expired"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This device code has expired. Please run 'ubio login' again.",
        )

    if record.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This device code has already been processed.",
        )

    # Mint a Personal Access Token for the device
    raw_token, _ = await create_personal_access_token(
        session=session,
        user_id=current_user.id,
        name=f"CLI Terminal Session ({clean_code})",
        scope="write",
        expires_in_days=90,
    )

    record.status = "approved"
    record.user_id = current_user.id
    record.access_token = raw_token
    await session.commit()

    logger.info(
        "Approved device authorization request",
        extra={"user_code": clean_code, "user_id": current_user.id},
    )

    return {
        "success": True,
        "message": "Device successfully authorized! You can return to your terminal.",
    }


@router.post("/device/token")
async def exchange_device_token(
    payload: DeviceTokenRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Poll for approval and exchange approved device_code for access_token (RFC 8628)."""
    stmt = select(DeviceAuthorizationModel).where(
        DeviceAuthorizationModel.device_code == payload.device_code.strip()
    )
    res = await session.execute(stmt)
    record = res.scalar_one_or_none()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_grant",
        )

    now = datetime.now(UTC)
    rec_expires = (
        record.expires_at if record.expires_at.tzinfo else record.expires_at.replace(tzinfo=UTC)
    )

    if now > rec_expires or record.status == "expired":
        record.status = "expired"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expired_token",
        )

    if record.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="authorization_pending",
        )

    if record.status == "approved" and record.access_token:
        token = record.access_token
        # Delete the device authorization record upon exchange (single-use invariant)
        await session.delete(record)
        await session.commit()

        return {
            "access_token": token,
            "token_type": "Bearer",
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="access_denied",
    )

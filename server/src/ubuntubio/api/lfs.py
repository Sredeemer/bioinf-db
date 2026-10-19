"""Git LFS batch API, upload staging, and CAS download streaming (M1-14, M1-15)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.api.dependencies import get_optional_user, get_repository_by_slug
from ubuntubio.api.schemas import (
    LfsAction,
    LfsBatchRequest,
    LfsBatchResponse,
    LfsObjectResponse,
)
from ubuntubio.auth.authz import AuthorizationService, RepoAction
from ubuntubio.auth.cas_tokens import CasTokenManager
from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import (
    AuditLogModel,
    LfsObjectModel,
    RepositoryModel,
    UserModel,
    XetFileModel,
)
from ubuntubio.db.session import get_db_session

router = APIRouter(tags=["Git LFS"])
logger = get_logger("ubuntubio.api.lfs")
authz_service = AuthorizationService()
cas_token_manager = CasTokenManager(
    issuer=settings.API_URL,
    audience=settings.CAS_TOKEN_AUDIENCE,
    token_lifetime_seconds=settings.CAS_TOKEN_LIFETIME_SECONDS,
)


@router.post(
    "/{owner}/{name}.git/info/lfs/objects/batch",
    response_model=LfsBatchResponse,
)
async def git_lfs_batch(
    owner: str,
    name: str,
    payload: LfsBatchRequest,
    user: UserModel | None = Depends(get_optional_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> LfsBatchResponse:
    """Git LFS Batch API endpoint handling object transfer negotiation."""
    # Enforce basic transfer support
    if "basic" not in payload.transfers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="UbuntuBio Git LFS currently supports the 'basic' transfer adapter.",
        )

    if payload.operation == "download":
        can_read = await authz_service.can_perform_action(
            session, user, repo, RepoAction.DOWNLOAD_DATA
        )
        if not can_read:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED if not user else status.HTTP_403_FORBIDDEN,
                detail="Read access required to download LFS objects.",
                headers={"WWW-Authenticate": "Basic realm='UbuntuBio Git'"} if not user else None,
            )
    elif payload.operation == "upload":
        can_write = await authz_service.can_perform_action(
            session, user, repo, RepoAction.WRITE_COMMIT
        )
        if not can_write:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED if not user else status.HTTP_403_FORBIDDEN,
                detail="Write access required to upload LFS objects.",
                headers={"WWW-Authenticate": "Basic realm='UbuntuBio Git'"} if not user else None,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported LFS operation '{payload.operation}'.",
        )

    # Issue ephemeral CAS / LFS token for these objects
    sub = user.orcid_id if user else "anonymous"
    expires_dt = datetime.now(UTC) + timedelta(seconds=settings.CAS_TOKEN_LIFETIME_SECONDS)
    expires_iso = expires_dt.isoformat()

    lfs_objects: list[LfsObjectResponse] = []
    base_url = settings.API_URL.rstrip("/")

    for obj in payload.objects:
        token = cas_token_manager.issue_token(
            subject=sub,
            repo_slug=repo.slug,
            action="read" if payload.operation == "download" else "write",
            custom_claims={"oid": obj.oid, "size": obj.size},
        )

        actions: dict[str, LfsAction] = {}
        if payload.operation == "download":
            actions["download"] = LfsAction(
                href=f"{base_url}/api/repos/{owner}/{name}/lfs/{obj.oid}",
                header={"Authorization": f"Bearer {token}"},
                expires_at=expires_iso,
            )
        else:
            actions["upload"] = LfsAction(
                href=f"{base_url}/api/repos/{owner}/{name}/lfs/{obj.oid}",
                header={"Authorization": f"Bearer {token}"},
                expires_at=expires_iso,
            )

        lfs_objects.append(
            LfsObjectResponse(
                oid=obj.oid,
                size=obj.size,
                authenticated=True,
                actions=actions,
            )
        )

    logger.info(
        "Processed Git LFS batch request",
        extra={
            "repo_slug": repo.slug,
            "operation": payload.operation,
            "objects_count": len(payload.objects),
            "user_id": user.id if user else "anonymous",
        },
    )

    return LfsBatchResponse(
        transfer="basic",
        objects=lfs_objects,
        hash_algo=payload.hash_algo,
    )


@router.put("/api/repos/{owner}/{name}/lfs/{oid}", status_code=status.HTTP_200_OK)
async def upload_lfs_object(
    owner: str,
    name: str,
    oid: str,
    request: Request,
    authorization: str | None = Header(None),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Receive staged LFS object upload into repository tmp directory."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid Bearer token required for LFS upload.",
        )

    raw_token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = cas_token_manager.verify_token(raw_token, expected_repo=repo.slug)
        if claims.get("action") != "write":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token does not have write scope.",
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired CAS token: {exc}",
        ) from exc

    # Stream content to temporary file and calculate sha256
    settings.TMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_file = settings.TMP_ROOT / f"{oid}.tmp"
    hasher = hashlib.sha256()
    total_size = 0

    with open(temp_file, "wb") as f:
        async for chunk in request.stream():
            hasher.update(chunk)
            total_size += len(chunk)
            f.write(chunk)

    computed_oid = hasher.hexdigest()
    if computed_oid.lower() != oid.lower():
        if temp_file.exists():
            temp_file.unlink()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Checksum mismatch: expected '{oid}', computed '{computed_oid}'.",
        )

    # Register object in lfs_objects if not exists
    stmt = select(LfsObjectModel).where(
        LfsObjectModel.repo_id == repo.id,
        LfsObjectModel.oid == computed_oid,
    )
    res = await session.execute(stmt)
    if not res.scalar_one_or_none():
        lfs_entry = LfsObjectModel(
            repo_id=repo.id,
            oid=computed_oid,
            size_bytes=total_size,
        )
        session.add(lfs_entry)

    # Register in xet_files mapping
    xet_stmt = select(XetFileModel).where(XetFileModel.sha256 == computed_oid)
    xet_res = await session.execute(xet_stmt)
    if not xet_res.scalar_one_or_none():
        # Xet hash default maps to sha256 until chunking worker processes it
        xet_entry = XetFileModel(
            sha256=computed_oid,
            xet_hash=computed_oid,
            size_bytes=total_size,
        )
        session.add(xet_entry)

    await session.commit()
    return {"status": "uploaded", "oid": computed_oid, "size_bytes": str(total_size)}


@router.get("/api/repos/{owner}/{name}/lfs/{oid}")
async def download_lfs_object(
    owner: str,
    name: str,
    oid: str,
    request: Request,
    authorization: str | None = Header(None),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Download Git LFS object payload."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid Bearer token required for LFS download.",
        )

    raw_token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = cas_token_manager.verify_token(raw_token, expected_repo=repo.slug)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired CAS token: {exc}",
        ) from exc

    sub = claims.get("sub", "anonymous")

    # Check local tmp staged store first
    temp_file = settings.TMP_ROOT / f"{oid}.tmp"
    if not temp_file.exists():
        # Look in xet/ or cas
        xet_file = settings.DATA_ROOT / "xet" / f"{oid}.bin"
        if xet_file.exists():
            temp_file = xet_file
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LFS object '{oid}' not found in CAS storage.",
            )

    # Log audit entry if repository is gated
    if repo.access == "gated":
        ip_raw = request.client.host if request.client else "unknown"
        ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()
        audit = AuditLogModel(
            repo_id=repo.id,
            user_id=sub,
            action="lfs_download",
            resource_path=f"{repo.slug}:{oid}",
            ip_hash=ip_hash,
        )
        session.add(audit)
        await session.commit()

    return FileResponse(
        path=temp_file,
        media_type="application/octet-stream",
        filename=f"{oid}.bin",
    )

"""Gated dataset access requests, DUA acceptance, and audit logging (M1-16, M1-17)."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.api.dependencies import get_repository_by_slug, require_authenticated_user
from ubuntubio.api.schemas import (
    AccessRequestDecisionPayload,
    AccessRequestResponse,
    AuditLogResponse,
    CreateAccessRequestPayload,
    DuaAcceptanceResponse,
    DuaAcceptRequest,
)
from ubuntubio.auth.authz import AuthorizationService
from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import (
    AccessRequestModel,
    AuditLogModel,
    DuaAcceptanceModel,
    RepositoryModel,
    UserModel,
)
from ubuntubio.db.session import get_db_session

router = APIRouter(prefix="/api/repos/{owner}/{name}", tags=["Gated Access & Audit"])
logger = get_logger("ubuntubio.api.gated")
authz_service = AuthorizationService()


async def _require_repo_admin(
    session: AsyncSession,
    user: UserModel,
    repo: RepositoryModel,
) -> None:
    """Ensure caller is the repository owner or an admin of the owner organization."""
    is_owner = (repo.owner_type == "user" and repo.owner_id == user.id) or (
        repo.owner_type == "org"
        and (await authz_service.is_org_member(session, user.id, repo.owner_id)) == "admin"
    )
    if not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required to manage access requests or view audit logs.",
        )


@router.post(
    "/dua/accept",
    response_model=DuaAcceptanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_data_use_agreement(
    owner: str,
    name: str,
    payload: DuaAcceptRequest,
    request: Request,
    user: UserModel = Depends(require_authenticated_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> DuaAcceptanceResponse:
    """Record acceptance of Data Use Agreement (DUA) for gated or regulated dataset."""
    # Check if already accepted this version
    stmt = select(DuaAcceptanceModel).where(
        DuaAcceptanceModel.repo_id == repo.id,
        DuaAcceptanceModel.user_id == user.id,
        DuaAcceptanceModel.dua_version == payload.dua_version,
    )
    res = await session.execute(stmt)
    existing = res.scalar_one_or_none()

    if existing:
        return DuaAcceptanceResponse(
            id=existing.id,
            repo_slug=repo.slug,
            dua_version=existing.dua_version,
            accepted_at=existing.accepted_at,
        )

    acceptance = DuaAcceptanceModel(
        repo_id=repo.id,
        user_id=user.id,
        dua_version=payload.dua_version,
    )
    session.add(acceptance)

    # Log audit event
    ip_raw = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()
    audit = AuditLogModel(
        repo_id=repo.id,
        user_id=user.id,
        action="accept_dua",
        resource_path=f"{repo.slug}@{payload.dua_version}",
        ip_hash=ip_hash,
    )
    session.add(audit)
    await session.commit()
    await session.refresh(acceptance)

    logger.info(
        "Accepted Data Use Agreement (DUA)",
        extra={
            "repo_slug": repo.slug,
            "user_id": user.id,
            "dua_version": payload.dua_version,
        },
    )

    return DuaAcceptanceResponse(
        id=acceptance.id,
        repo_slug=repo.slug,
        dua_version=acceptance.dua_version,
        accepted_at=acceptance.accepted_at,
    )


@router.post(
    "/access-requests",
    response_model=AccessRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_gated_access(
    owner: str,
    name: str,
    payload: CreateAccessRequestPayload,
    request: Request,
    user: UserModel = Depends(require_authenticated_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> AccessRequestResponse:
    """Submit access justification for a gated dataset."""
    if repo.access != "gated":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository '{repo.slug}' access mode is '{repo.access}', not 'gated'.",
        )

    # Verify DUA has been accepted
    dua_stmt = select(DuaAcceptanceModel).where(
        DuaAcceptanceModel.repo_id == repo.id,
        DuaAcceptanceModel.user_id == user.id,
    )
    dua_res = await session.execute(dua_stmt)
    if not dua_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must accept the Data Use Agreement (DUA) before requesting access.",
        )

    # Check for pending or already approved requests
    req_stmt = select(AccessRequestModel).where(
        AccessRequestModel.repo_id == repo.id,
        AccessRequestModel.user_id == user.id,
    )
    req_res = await session.execute(req_stmt)
    existing_req = req_res.scalar_one_or_none()

    if existing_req:
        if existing_req.status == "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have approved access to this dataset.",
            )
        if existing_req.status == "pending":
            return AccessRequestResponse.model_validate(existing_req)

    # Create new access request
    access_req = AccessRequestModel(
        repo_id=repo.id,
        user_id=user.id,
        justification=payload.justification,
        status="pending",
    )
    session.add(access_req)

    ip_raw = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()
    audit = AuditLogModel(
        repo_id=repo.id,
        user_id=user.id,
        action="request_access",
        resource_path=repo.slug,
        ip_hash=ip_hash,
    )
    session.add(audit)
    await session.commit()
    await session.refresh(access_req)

    logger.info(
        "Submitted gated dataset access request",
        extra={
            "repo_slug": repo.slug,
            "user_id": user.id,
            "request_id": access_req.id,
        },
    )

    return AccessRequestResponse.model_validate(access_req)


@router.get("/access-requests", response_model=list[AccessRequestResponse])
async def list_access_requests(
    owner: str,
    name: str,
    user: UserModel = Depends(require_authenticated_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> list[AccessRequestResponse]:
    """List pending and decided access requests (dataset owner/admin only)."""
    await _require_repo_admin(session, user, repo)

    stmt = (
        select(AccessRequestModel)
        .where(AccessRequestModel.repo_id == repo.id)
        .order_by(AccessRequestModel.created_at.desc())
    )
    res = await session.execute(stmt)
    requests = res.scalars().all()
    return [AccessRequestResponse.model_validate(r) for r in requests]


@router.post("/access-requests/{req_id}/decision", response_model=AccessRequestResponse)
async def decide_access_request(
    owner: str,
    name: str,
    req_id: str,
    payload: AccessRequestDecisionPayload,
    request: Request,
    user: UserModel = Depends(require_authenticated_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> AccessRequestResponse:
    """Approve or reject a gated dataset access request (dataset owner/admin only)."""
    await _require_repo_admin(session, user, repo)

    stmt = select(AccessRequestModel).where(
        AccessRequestModel.id == req_id,
        AccessRequestModel.repo_id == repo.id,
    )
    res = await session.execute(stmt)
    req_obj = res.scalar_one_or_none()
    if not req_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Access request '{req_id}' not found.",
        )

    req_obj.status = payload.decision
    req_obj.reviewed_at = datetime.now(UTC)
    req_obj.reviewed_by = user.id

    ip_raw = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()
    audit = AuditLogModel(
        repo_id=repo.id,
        user_id=user.id,
        action=f"decision_{payload.decision}",
        resource_path=f"{repo.slug}:{req_obj.user_id}",
        ip_hash=ip_hash,
    )
    session.add(audit)
    await session.commit()
    await session.refresh(req_obj)

    logger.info(
        "Decided gated dataset access request",
        extra={
            "repo_slug": repo.slug,
            "request_id": req_id,
            "decision": payload.decision,
            "applicant_id": req_obj.user_id,
            "reviewer_id": user.id,
        },
    )

    return AccessRequestResponse.model_validate(req_obj)


@router.get("/audit-log")
async def get_audit_log(
    owner: str,
    name: str,
    output_format: Annotated[Literal["json", "csv"], Query(alias="format")] = "json",
    user: UserModel = Depends(require_authenticated_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Export compliance audit log of access events for gated dataset (owner/admin only)."""
    await _require_repo_admin(session, user, repo)

    stmt = (
        select(AuditLogModel)
        .where(AuditLogModel.repo_id == repo.id)
        .order_by(AuditLogModel.timestamp.desc())
    )
    res = await session.execute(stmt)
    entries = res.scalars().all()

    if output_format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["id", "timestamp", "user_id", "action", "resource_path", "ip_hash"])
        for e in entries:
            writer.writerow(
                [
                    e.id,
                    e.timestamp.isoformat() if e.timestamp else "",
                    e.user_id or "",
                    e.action,
                    e.resource_path,
                    e.ip_hash,
                ]
            )
        return Response(
            content=out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{repo.name}_audit_log.csv"'},
        )

    json_data = [AuditLogResponse.model_validate(e).model_dump(mode="json") for e in entries]
    import json

    return Response(
        content=json.dumps(json_data),
        media_type="application/json",
    )

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.api.dependencies import get_repository_by_slug, require_authenticated_user
from ubuntubio.api.schemas import CommitRequest, PreuploadRequest, PreuploadResponse
from ubuntubio.auth.authz import AuthorizationService, RepoAction
from ubuntubio.auth.cas_tokens import CasTokenManager
from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import LfsObjectModel, RepositoryModel, UserModel, XetFileModel
from ubuntubio.db.session import get_db_session
from ubuntubio.indexer.worker import index_repository

router = APIRouter(prefix="/api/repos/{owner}/{name}", tags=["CAS & Commits"])
logger = get_logger("ubuntubio.api.cas")
authz_service = AuthorizationService()
cas_token_manager = CasTokenManager(
    issuer=settings.API_URL,
    audience=settings.CAS_TOKEN_AUDIENCE,
    token_lifetime_seconds=settings.CAS_TOKEN_LIFETIME_SECONDS,
)


@router.post("/preupload", response_model=PreuploadResponse)
async def preupload_inquiry(
    owner: str,
    name: str,
    payload: PreuploadRequest,
    user: UserModel = Depends(require_authenticated_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> PreuploadResponse:
    """Authorize file pre-upload and issue short-lived CAS write token for OpenXet."""
    can_write = await authz_service.can_perform_action(session, user, repo, RepoAction.WRITE_COMMIT)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required to upload files to this repository.",
        )

    # Issue RS256 token scoped specifically to this repository slug
    token = cas_token_manager.issue_token(
        subject=user.orcid_id,
        repo_slug=repo.slug,
        action="write",
        custom_claims={"filenames": payload.filenames},
    )

    logger.info(
        "Generated CAS preupload token",
        extra={
            "repo_slug": repo.slug,
            "user_id": user.id,
            "filenames_count": len(payload.filenames),
        },
    )

    return PreuploadResponse(
        repo_slug=repo.slug,
        cas_url=settings.CAS_URL,
        cas_write_token=token,
        expires_in_seconds=settings.CAS_TOKEN_LIFETIME_SECONDS,
    )


@router.post("/commit", status_code=status.HTTP_201_CREATED)
async def commit_files(
    owner: str,
    name: str,
    payload: CommitRequest,
    user: UserModel = Depends(require_authenticated_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Register committed CAS files and Git LFS objects in repository."""
    can_write = await authz_service.can_perform_action(session, user, repo, RepoAction.WRITE_COMMIT)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required to commit to this repository.",
        )

    registered_files: list[str] = []

    for file_info in payload.files:
        # Upsert or register in xet_files
        xet_stmt = select(XetFileModel).where(XetFileModel.sha256 == file_info.sha256)
        xet_res = await session.execute(xet_stmt)
        existing_xet = xet_res.scalar_one_or_none()

        if not existing_xet:
            new_xet = XetFileModel(
                sha256=file_info.sha256,
                xet_hash=file_info.xet_hash,
                size_bytes=file_info.size_bytes,
            )
            session.add(new_xet)

        # Register in lfs_objects for this repo
        lfs_stmt = select(LfsObjectModel).where(
            LfsObjectModel.repo_id == repo.id,
            LfsObjectModel.oid == file_info.sha256,
        )
        lfs_res = await session.execute(lfs_stmt)
        if not lfs_res.scalar_one_or_none():
            lfs_obj = LfsObjectModel(
                repo_id=repo.id,
                oid=file_info.sha256,
                size_bytes=file_info.size_bytes,
            )
            session.add(lfs_obj)

        registered_files.append(file_info.path)

    await session.commit()

    # Automatically index repository metadata and samples
    with contextlib.suppress(Exception):
        await index_repository(session=session, repo_slug=repo.slug)

    logger.info(
        "Committed files to repository",
        extra={
            "repo_slug": repo.slug,
            "user_id": user.id,
            "branch": payload.branch,
            "committed_files_count": len(registered_files),
        },
    )

    return {
        "status": "committed",
        "repo_slug": repo.slug,
        "branch": payload.branch,
        "message": payload.message,
        "committed_files_count": len(registered_files),
        "files": registered_files,
    }

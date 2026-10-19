"""Git Smart-HTTP routing and authorization proxy (M1-08)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.api.dependencies import get_optional_user, get_repository_by_slug
from ubuntubio.auth.authz import AuthorizationService, RepoAction
from ubuntubio.db.models import RepositoryModel, UserModel
from ubuntubio.db.session import get_db_session
from ubuntubio.git.smart_http import GitSmartHttpHandler

router = APIRouter(tags=["Git Smart-HTTP"])
authz_service = AuthorizationService()
git_handler = GitSmartHttpHandler()


@router.get("/{owner}/{name}.git/info/refs")
async def git_info_refs(
    owner: str,
    name: str,
    request: Request,
    user: UserModel | None = Depends(get_optional_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Handle Git Smart-HTTP info/refs query."""
    service = request.query_params.get("service")
    if not service:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dumb HTTP protocol is disabled; 'service' query parameter is required.",
        )

    # Check permission based on service
    if service == "git-upload-pack":
        can_read = await authz_service.can_perform_action(
            session, user, repo, RepoAction.DOWNLOAD_DATA
        )
        if not can_read:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED if not user else status.HTTP_403_FORBIDDEN,
                detail="Read access required to clone this repository.",
                headers={"WWW-Authenticate": "Basic realm='UbuntuBio Git'"} if not user else None,
            )
    elif service == "git-receive-pack":
        can_write = await authz_service.can_perform_action(
            session, user, repo, RepoAction.WRITE_COMMIT
        )
        if not can_write:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED if not user else status.HTTP_403_FORBIDDEN,
                detail="Write access required to push to this repository.",
                headers={"WWW-Authenticate": "Basic realm='UbuntuBio Git'"} if not user else None,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported git service: {service}",
        )

    return await git_handler.handle_request(
        request=request,
        repo_subpath=f"{owner}/{name}.git/info/refs",
        user_id=user.orcid_id if user else None,
    )


@router.post("/{owner}/{name}.git/git-upload-pack")
async def git_upload_pack(
    owner: str,
    name: str,
    request: Request,
    user: UserModel | None = Depends(get_optional_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Handle Git Smart-HTTP clone/fetch pack streaming."""
    can_read = await authz_service.can_perform_action(session, user, repo, RepoAction.DOWNLOAD_DATA)
    if not can_read:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Read access required.",
        )

    return await git_handler.handle_request(
        request=request,
        repo_subpath=f"{owner}/{name}.git/git-upload-pack",
        user_id=user.orcid_id if user else None,
    )


@router.post("/{owner}/{name}.git/git-receive-pack")
async def git_receive_pack(
    owner: str,
    name: str,
    request: Request,
    user: UserModel | None = Depends(get_optional_user),
    repo: RepositoryModel = Depends(get_repository_by_slug),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Handle Git Smart-HTTP push pack streaming."""
    can_write = await authz_service.can_perform_action(session, user, repo, RepoAction.WRITE_COMMIT)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required.",
        )

    return await git_handler.handle_request(
        request=request,
        repo_subpath=f"{owner}/{name}.git/git-receive-pack",
        user_id=user.orcid_id if user else None,
    )

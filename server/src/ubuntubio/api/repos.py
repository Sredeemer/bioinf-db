"""Repository management API routes (M1-06, M1-13)."""

from __future__ import annotations

import contextlib
import json
import subprocess
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.api.dependencies import get_optional_user, require_authenticated_user
from ubuntubio.api.schemas import (
    CommitLogItem,
    CreateRepoRequest,
    RepoResponse,
    TreeItem,
    TreeResponse,
    UpdateRepoRequest,
)
from ubuntubio.auth.authz import AuthorizationService, RepoAction
from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import (
    DatasetSearchRecordModel,
    LfsObjectModel,
    OrganizationModel,
    RepositoryModel,
    UserModel,
)
from ubuntubio.db.session import get_db_session
from ubuntubio.git.repo_manager import GitRepoManager
from ubuntubio.indexer.fts import search_service

router = APIRouter(prefix="/api/repos", tags=["Repositories"])
logger = get_logger("ubuntubio.api.repos")
authz_service = AuthorizationService()
git_manager = GitRepoManager()


@router.post("", response_model=RepoResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(
    payload: CreateRepoRequest,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> RepoResponse:
    """Create a new dataset repository and initialize its bare Git repository on disk."""
    slug = f"{payload.owner_slug}/{payload.name}"

    # Check if slug already exists
    existing_stmt = select(RepositoryModel).where(RepositoryModel.slug == slug)
    res = await session.execute(existing_stmt)
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Repository '{slug}' already exists.",
        )

    # Validate ownership permissions and prevent namespace collision/squatting
    owner_id = user.id
    owner_type = payload.owner_type

    # 1. Prevent collision / impersonation of another registered researcher
    user_stmt = select(UserModel).where(
        (UserModel.username == payload.owner_slug) | (UserModel.orcid_id == payload.owner_slug)
    )
    user_res = await session.execute(user_stmt)
    target_user = user_res.scalar_one_or_none()

    if target_user and target_user.id != user.id:
        expected = user.username or user.orcid_id
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Cannot create repository under namespace '{payload.owner_slug}'. "
                "That handle belongs to another registered researcher. "
                f"Your namespace is '{expected}'."
            ),
        )

    # 2. Prevent unauthorized creation under existing organizations
    org_stmt = select(OrganizationModel).where(OrganizationModel.slug == payload.owner_slug)
    org_res = await session.execute(org_stmt)
    target_org = org_res.scalar_one_or_none()

    if target_org or payload.owner_type == "org":
        role = await authz_service.is_org_member(session, user.id, payload.owner_slug)
        if role not in ("admin", "write"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Write permission required in organization '{payload.owner_slug}'.",
            )
        owner_type = "org"
        owner_id = payload.owner_slug
    else:
        owner_type = "user"
        owner_id = user.id

    repo = RepositoryModel(
        slug=slug,
        name=payload.name,
        owner_type=owner_type,
        owner_id=owner_id,
        description=payload.description,
        domain=payload.domain,
        access=payload.access,
        license=payload.license,
        is_verified_african=False,
    )
    session.add(repo)
    await session.commit()
    await session.refresh(repo)

    # Initialize bare git repository on disk under single data folder
    git_manager.init_bare_repo(payload.owner_slug, payload.name)

    # Auto-index into SQLite FTS5 search engine for instant discovery
    try:
        await search_service.index_dataset(
            session=session,
            repo_id=repo.id,
            slug=repo.slug,
            name=repo.name,
            title=repo.name,
            description=repo.description,
            domain=repo.domain,
            access=repo.access,
            license=repo.license,
            countries=[],
            taxa=[],
            genera=[],
            families=[],
            is_verified_african=repo.is_verified_african,
            owner_type=repo.owner_type,
            owner_id=repo.owner_id,
            samples_count=0,
            benefit_sharing=None,
            created_at=repo.created_at,
            updated_at=repo.updated_at,
        )
        await session.commit()
    except Exception as exc:
        logger.warning(
            "Auto-indexing dataset in search failed",
            extra={"repo_slug": repo.slug, "error": str(exc)},
        )

    logger.info(
        "Created repository",
        extra={
            "repo_id": repo.id,
            "repo_slug": repo.slug,
            "access": repo.access,
            "user_id": user.id,
        },
    )
    return RepoResponse.model_validate(repo)


@router.get("/{owner}/{name}", response_model=RepoResponse)
async def get_repository(
    owner: str,
    name: str,
    user: UserModel | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> RepoResponse:
    """Fetch repository metadata if caller is authorized."""
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

    can_read = await authz_service.can_perform_action(session, user, repo, RepoAction.READ_METADATA)
    if not can_read:
        # Hide private repo existence from unauthorized callers
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{slug}' not found.",
        )

    countries: list[str] = []
    taxon_ids: list[int] = []
    genus: list[str] = []
    family: list[str] = []
    samples_count = 0

    search_stmt = select(DatasetSearchRecordModel).where(DatasetSearchRecordModel.repo_id == repo.id)
    search_res = await session.execute(search_stmt)
    search_rec = search_res.scalar_one_or_none()
    if search_rec:
        with contextlib.suppress(Exception):
            countries = json.loads(search_rec.countries_json)
        with contextlib.suppress(Exception):
            taxon_ids = json.loads(search_rec.taxa_json)
        with contextlib.suppress(Exception):
            genus = json.loads(search_rec.genus_json)
        with contextlib.suppress(Exception):
            family = json.loads(search_rec.family_json)
        samples_count = search_rec.samples_count

    lfs_stmt = select(
        func.count(LfsObjectModel.id),
        func.coalesce(func.sum(LfsObjectModel.size_bytes), 0),
    ).where(LfsObjectModel.repo_id == repo.id)
    lfs_res = await session.execute(lfs_stmt)
    f_count, t_bytes = lfs_res.one()

    return RepoResponse(
        id=repo.id,
        slug=repo.slug,
        name=repo.name,
        owner_type=repo.owner_type,
        owner_id=repo.owner_id,
        description=repo.description,
        domain=repo.domain,
        access=repo.access,
        license=repo.license,
        is_verified_african=repo.is_verified_african,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
        countries=countries,
        taxon_ids=taxon_ids,
        genus=genus,
        family=family,
        samples_count=samples_count,
        total_size_bytes=t_bytes or 0,
        files_count=f_count or 0,
    )


@router.patch("/{owner}/{name}", response_model=RepoResponse)
async def update_repository(
    owner: str,
    name: str,
    payload: UpdateRepoRequest,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> RepoResponse:
    """Update repository settings and access level (write/admin permission required)."""
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

    can_write = await authz_service.can_perform_action(session, user, repo, RepoAction.WRITE_COMMIT)
    if not can_write:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required to update repository settings.",
        )

    if payload.description is not None:
        repo.description = payload.description
    if payload.domain is not None:
        repo.domain = payload.domain
    if payload.access is not None:
        repo.access = payload.access
    if payload.license is not None:
        repo.license = payload.license

    await session.commit()
    await session.refresh(repo)
    logger.info(
        "Updated repository settings",
        extra={
            "repo_id": repo.id,
            "repo_slug": repo.slug,
            "access": repo.access,
            "user_id": user.id,
        },
    )
    return RepoResponse.model_validate(repo)


@router.delete("/{owner}/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    owner: str,
    name: str,
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a repository and its bare Git directory (admin permission required)."""
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

    is_owner = (repo.owner_type == "user" and repo.owner_id == user.id) or (
        repo.owner_type == "org"
        and (await authz_service.is_org_member(session, user.id, repo.owner_id)) == "admin"
    )
    if not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required to delete repository.",
        )

    # Delete bare repo directory on disk
    git_manager.delete_repo(owner, clean_name)

    # Delete record from database
    await session.delete(repo)
    await session.commit()
    logger.info(
        "Deleted repository",
        extra={"repo_id": repo.id, "repo_slug": slug, "user_id": user.id},
    )


@router.get("", response_model=list[RepoResponse])
async def list_repositories(
    domain: Annotated[str | None, Query(description="Filter by biological domain")] = None,
    user: UserModel | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[RepoResponse]:
    """List accessible repositories matching filter parameters."""
    stmt = select(RepositoryModel)
    if domain:
        stmt = stmt.where(RepositoryModel.domain == domain)

    res = await session.execute(stmt)
    all_repos = res.scalars().all()

    # Filter by user read permissions
    accessible: list[RepoResponse] = []
    for r in all_repos:
        if await authz_service.can_perform_action(session, user, r, RepoAction.READ_METADATA):
            accessible.append(RepoResponse.model_validate(r))

    return accessible


@router.get("/{owner}/{name}/commits", response_model=list[CommitLogItem])
async def get_commit_history(
    owner: str,
    name: str,
    ref: str = "HEAD",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    user: UserModel | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[CommitLogItem]:
    """Read commit log from bare Git repository."""
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

    can_read = await authz_service.can_perform_action(session, user, repo, RepoAction.READ_METADATA)
    if not can_read:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{slug}' not found.",
        )

    repo_path = git_manager.get_repo_path(owner, clean_name)
    if not repo_path.exists():
        return []

    # Run git log
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_path),
            "log",
            f"-n{limit}",
            "--pretty=format:%H%x09%an%x09%aI%x09%s",
            ref,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Might be an unborn branch with no commits yet
        return []

    items: list[CommitLogItem] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 3)
        if len(parts) == 4:
            items.append(
                CommitLogItem(
                    commit_hash=parts[0],
                    author=parts[1],
                    date=parts[2],
                    message=parts[3],
                )
            )
    return items


@router.get("/{owner}/{name}/tree/{ref:path}", response_model=TreeResponse)
async def get_tree_listing(
    owner: str,
    name: str,
    ref: str,
    user: UserModel | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> TreeResponse:
    """List directory tree contents at a specified Git ref."""
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

    can_read = await authz_service.can_perform_action(session, user, repo, RepoAction.READ_METADATA)
    if not can_read:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{slug}' not found.",
        )

    repo_path = git_manager.get_repo_path(owner, clean_name)
    if not repo_path.exists():
        return TreeResponse(ref=ref, items=[])

    # Run git ls-tree -r -l
    result = subprocess.run(
        ["git", "-C", str(repo_path), "ls-tree", "-r", "-l", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return TreeResponse(ref=ref, items=[])

    items: list[TreeItem] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        # Format: <mode> <type> <object> <size>\t<file>
        try:
            meta, path = line.split("\t", 1)
            meta_parts = meta.split()
            mode = meta_parts[0]
            obj_type = meta_parts[1]
            oid = meta_parts[2]
            size_str = meta_parts[3] if len(meta_parts) > 3 else None
            size = int(size_str) if size_str and size_str != "-" else None
            items.append(
                TreeItem(
                    mode=mode,
                    type=obj_type,
                    oid=oid,
                    size=size,
                    path=path,
                )
            )
        except Exception:
            continue

    return TreeResponse(ref=ref, items=items)


@router.get("/{owner}/{name}/raw/{ref}/{file_path:path}")
async def get_raw_file(
    owner: str,
    name: str,
    ref: str,
    file_path: str,
    user: UserModel | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """Fetch raw file content at specific ref/revision."""
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

    can_download = await authz_service.can_perform_action(
        session, user, repo, RepoAction.DOWNLOAD_DATA
    )
    if not can_download:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authorization required to download data from this repository.",
        )

    repo_path = git_manager.get_repo_path(owner, clean_name)
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show", f"{ref}:{file_path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_path}' not found at revision '{ref}'.",
        )

    return Response(content=result.stdout, media_type="application/octet-stream")

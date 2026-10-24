import contextlib
import os
import shutil
import subprocess
from typing import Any
import uuid

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
from ubuntubio.git.repo_manager import GitRepoManager
from ubuntubio.indexer.worker import index_repository

router = APIRouter(prefix="/api/repos/{owner}/{name}", tags=["CAS & Commits"])
logger = get_logger("ubuntubio.api.cas")
authz_service = AuthorizationService()
git_manager = GitRepoManager()
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
    readme_override: str | None = None
    samples_tsv_override: str | None = None

    repo_path = git_manager.get_repo_path(owner, repo.name)
    if not repo_path.exists():
        git_manager.init_bare_repo(owner, repo.name)

    temp_index = settings.TMP_ROOT / f"git_idx_{repo.id}_{uuid.uuid4().hex}"
    git_env = {**os.environ, "GIT_INDEX_FILE": str(temp_index)}

    # Check if branch already exists
    ref_check = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--verify", f"refs/heads/{payload.branch}"],
        capture_output=True,
        text=True,
        check=False,
    )
    parent_commit: str | None = None
    if ref_check.returncode == 0:
        parent_commit = ref_check.stdout.strip()
        subprocess.run(
            ["git", "-C", str(repo_path), "read-tree", parent_commit],
            env=git_env,
            capture_output=True,
            check=False,
        )

    for file_info in payload.files:
        staged_tmp = settings.TMP_ROOT / f"{file_info.sha256}.tmp"
        with contextlib.suppress(Exception):
            target_cas = settings.DATA_ROOT / "xet" / f"{file_info.sha256}.bin"
            target_cas.parent.mkdir(parents=True, exist_ok=True)
            if staged_tmp.exists():
                shutil.copy2(str(staged_tmp), str(target_cas))

        if staged_tmp.exists():
            if file_info.path == "README.md":
                with contextlib.suppress(Exception):
                    readme_override = staged_tmp.read_text(encoding="utf-8")
            elif file_info.path == "samples.tsv":
                with contextlib.suppress(Exception):
                    samples_tsv_override = staged_tmp.read_text(encoding="utf-8")

            hash_res = subprocess.run(
                ["git", "-C", str(repo_path), "hash-object", "-w", str(staged_tmp)],
                capture_output=True,
                text=True,
                check=False,
            )
            if hash_res.returncode == 0:
                blob_oid = hash_res.stdout.strip()
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(repo_path),
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        "100644",
                        blob_oid,
                        file_info.path,
                    ],
                    env=git_env,
                    capture_output=True,
                    check=False,
                )

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

    # Finalize Git commit
    try:
        tree_res = subprocess.run(
            ["git", "-C", str(repo_path), "write-tree"],
            env=git_env,
            capture_output=True,
            text=True,
            check=False,
        )
        if tree_res.returncode == 0:
            tree_oid = tree_res.stdout.strip()
            commit_cmd = ["git", "-C", str(repo_path), "commit-tree", tree_oid]
            if parent_commit:
                commit_cmd.extend(["-p", parent_commit])
            commit_cmd.extend(["-m", payload.message or "Commit files via UbuntuBio CAS"])
            commit_res = subprocess.run(
                commit_cmd,
                env=git_env,
                capture_output=True,
                text=True,
                check=False,
            )
            if commit_res.returncode == 0:
                commit_oid = commit_res.stdout.strip()
                subprocess.run(
                    ["git", "-C", str(repo_path), "update-ref", f"refs/heads/{payload.branch}", commit_oid],
                    capture_output=True,
                    check=False,
                )
    except Exception as exc:
        logger.warning(f"Failed to record Git commit for {repo.slug}: {exc}")
    finally:
        if temp_index.exists():
            with contextlib.suppress(Exception):
                temp_index.unlink()

    await session.commit()

    # Automatically index repository metadata and samples with overrides
    with contextlib.suppress(Exception):
        await index_repository(
            session=session,
            repo_slug=repo.slug,
            ref=payload.branch,
            readme_override=readme_override,
            samples_tsv_override=samples_tsv_override,
        )

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

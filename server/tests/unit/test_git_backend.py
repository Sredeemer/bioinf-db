"""Unit tests for Git repository lifecycle and smart-HTTP handler (T-GIT-01 to T-GIT-04)."""

import subprocess
from pathlib import Path

import pytest
from starlette.requests import Request

from ubuntubio.git.repo_manager import GitRepoManager
from ubuntubio.git.smart_http import GitSmartHttpHandler


def test_init_bare_repo_and_hooks(tmp_path: Path) -> None:
    """T-GIT-01: Verify bare repository creation and hook installation on disk."""
    manager = GitRepoManager(git_root=tmp_path)
    repo_path = manager.init_bare_repo(owner="pasteur-dakar", name="lassa-surveillance")

    assert repo_path.exists()
    assert (repo_path / "HEAD").exists()
    assert (repo_path / "config").exists()
    assert (repo_path / "hooks" / "pre-receive").exists()
    assert (repo_path / "hooks" / "post-receive").exists()

    # Check config
    result = subprocess.run(
        ["git", "-C", str(repo_path), "config", "--get", "http.receivepack"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "true"


@pytest.mark.asyncio
async def test_smart_http_info_refs_upload_pack(tmp_path: Path) -> None:
    """T-GIT-02: Verify git-upload-pack info/refs response."""
    manager = GitRepoManager(git_root=tmp_path)
    manager.init_bare_repo(owner="test-org", name="amr-klebsiella")

    handler = GitSmartHttpHandler(git_root=tmp_path)

    # Construct mock request for /test-org/amr-klebsiella.git/info/refs?service=git-upload-pack
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test-org/amr-klebsiella.git/info/refs",
        "query_string": b"service=git-upload-pack",
        "headers": [(b"host", b"localhost:8000")],
    }
    request = Request(scope)

    response = await handler.handle_request(
        request=request,
        repo_subpath="test-org/amr-klebsiella.git/info/refs",
    )

    assert response.status_code == 200
    assert "application/x-git-upload-pack-advertisement" in response.headers.get("content-type", "")
    assert b"# service=git-upload-pack" in response.body


def test_delete_repo(tmp_path: Path) -> None:
    """Verify bare repository deletion."""
    manager = GitRepoManager(git_root=tmp_path)
    repo_path = manager.init_bare_repo(owner="temp-org", name="delete-me")
    assert repo_path.exists()

    deleted = manager.delete_repo(owner="temp-org", name="delete-me")
    assert deleted is True
    assert not repo_path.exists()

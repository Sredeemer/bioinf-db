"""Unit tests for repository updates, deletion, and Git tree inspection (M1-06, M1-13)."""

import subprocess
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ubuntubio.config import settings
from ubuntubio.db.models import Base
from ubuntubio.db.session import get_db_session
from ubuntubio.git.repo_manager import GitRepoManager
from ubuntubio.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_client(tmp_path: Path) -> AsyncClient:  # type: ignore[misc]
    settings.GIT_ROOT = tmp_path / "git"
    settings.TMP_ROOT = tmp_path / "tmp"
    settings.GIT_ROOT.mkdir(parents=True, exist_ok=True)
    settings.TMP_ROOT.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncSession:  # type: ignore[misc]
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db_session] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_repo_update_and_delete(test_client: AsyncClient, tmp_path: Path) -> None:
    """Test updating repository metadata and deleting repository."""
    # Login
    login = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0003-3333-3333", "name": "Curator User"},
    )
    headers = {"Authorization": f"Bearer {login.json()['raw_token']}"}

    # Create repo
    create_resp = await test_client.post(
        "/api/repos",
        headers=headers,
        json={
            "owner_slug": "kfri",
            "name": "trypanosoma-2024",
            "domain": "parasite",
            "access": "public",
            "description": "Sleeping sickness isolates in Kenya",
        },
    )
    assert create_resp.status_code == 201

    # Update repo
    patch_resp = await test_client.patch(
        "/api/repos/kfri/trypanosoma-2024",
        headers=headers,
        json={
            "description": "Updated sleeping sickness surveillance",
            "access": "gated",
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["access"] == "gated"
    assert patch_resp.json()["description"] == "Updated sleeping sickness surveillance"

    # Delete repo
    del_resp = await test_client.delete("/api/repos/kfri/trypanosoma-2024", headers=headers)
    assert del_resp.status_code == 204

    # Verify 404 after deletion
    get_resp = await test_client.get("/api/repos/kfri/trypanosoma-2024")
    assert get_resp.status_code == 404

    # Verify bare git directory on disk was removed
    repo_path = GitRepoManager(git_root=settings.GIT_ROOT).get_repo_path("kfri", "trypanosoma-2024")
    assert not repo_path.exists()


@pytest.mark.asyncio
async def test_repo_tree_and_commit_inspection(test_client: AsyncClient, tmp_path: Path) -> None:
    """Test git commits log, tree listing, and raw file download on bare repository."""
    # Login & create repo
    login = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0004-4444-4444", "name": "Bioinformatics Dev"},
    )
    headers = {"Authorization": f"Bearer {login.json()['raw_token']}"}

    create_resp = await test_client.post(
        "/api/repos",
        headers=headers,
        json={
            "owner_slug": "nmimr",
            "name": "malaria-ghana",
            "domain": "parasite",
            "access": "public",
        },
    )
    assert create_resp.status_code == 201

    repo_path = GitRepoManager(git_root=settings.GIT_ROOT).get_repo_path("nmimr", "malaria-ghana")

    # Simulate creating a commit in the bare repo using git in a work tree
    work_tree = tmp_path / "work_tree"
    work_tree.mkdir()
    subprocess.run(
        ["git", "clone", str(repo_path), str(work_tree)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work_tree), "config", "user.email", "dev@nmimr.gh"], check=True
    )
    subprocess.run(
        ["git", "-C", str(work_tree), "config", "user.name", "Ghana Researcher"], check=True
    )

    readme_content = """---
title: "Plasmodium falciparum surveillance in Accra"
description: "Genomic survey of clinical isolates"
license: "cc-by-4.0"
domain: "parasite"
access: "public"
countries: ["GH"]
taxon_ids: [5833]
---
# Malaria Ghana
Sample malaria dataset from Accra.
"""
    (work_tree / "README.md").write_text(readme_content)

    samples_content = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\tlat\tlon\tadmin1\thost\tisolation_source\n"
        "GH_PF_001\t5833\tGH\t2023-05-12\t5.6037\t-0.1870\tAccra\tHomo sapiens\tblood\n"
    )

    (work_tree / "samples.tsv").write_text(samples_content)

    subprocess.run(["git", "-C", str(work_tree), "add", "README.md", "samples.tsv"], check=True)
    subprocess.run(
        ["git", "-C", str(work_tree), "commit", "-m", "Initial commit: README"], check=True
    )
    subprocess.run(["git", "-C", str(work_tree), "push", "origin", "main"], check=True)

    # 1. Inspect Commits
    commits_resp = await test_client.get("/api/repos/nmimr/malaria-ghana/commits?ref=main")
    assert commits_resp.status_code == 200
    commits = commits_resp.json()
    assert len(commits) == 1
    assert commits[0]["message"] == "Initial commit: README"
    assert commits[0]["author"] == "Ghana Researcher"

    # 2. Inspect Tree
    tree_resp = await test_client.get("/api/repos/nmimr/malaria-ghana/tree/main")
    assert tree_resp.status_code == 200
    tree_data = tree_resp.json()
    assert tree_data["ref"] == "main"
    assert any(item["path"] == "README.md" for item in tree_data["items"])

    # 3. Read Raw File
    raw_resp = await test_client.get("/api/repos/nmimr/malaria-ghana/raw/main/README.md")
    assert raw_resp.status_code == 200
    assert "Sample malaria dataset from Accra." in raw_resp.text

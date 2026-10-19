"""Integration tests for UbuntuBio FastAPI HTTP endpoints."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ubuntubio.config import settings
from ubuntubio.db.models import Base
from ubuntubio.db.session import get_db_session
from ubuntubio.git.repo_manager import GitRepoManager
from ubuntubio.indexer.fts import init_fts_tables
from ubuntubio.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_client(tmp_path: Path) -> AsyncClient:  # type: ignore[misc]
    """Provide an AsyncClient wired with in-memory database and temporary git storage."""
    # Override settings for test
    settings.GIT_ROOT = tmp_path / "git"
    settings.TMP_ROOT = tmp_path / "tmp"
    settings.GIT_ROOT.mkdir(parents=True, exist_ok=True)
    settings.TMP_ROOT.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await init_fts_tables(conn)

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
async def test_full_api_workflow(test_client: AsyncClient, tmp_path: Path) -> None:
    """Test full developer workflow: dev-login, repo creation, CAS token, and git refs."""

    # 1. Dev Login
    login_resp = await test_client.post(
        "/api/auth/dev-login",
        json={
            "orcid_id": "0000-0002-1825-0097",
            "name": "Dr. Amina Diallo",
            "email": "amina@pasteur.sn",
        },
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    token = login_data["raw_token"]
    assert token.startswith("ubp_")

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Whoami
    whoami_resp = await test_client.get("/api/auth/whoami", headers=headers)
    assert whoami_resp.status_code == 200
    assert whoami_resp.json()["orcid_id"] == "0000-0002-1825-0097"

    # 3. Create Repository
    create_resp = await test_client.post(
        "/api/repos",
        headers=headers,
        json={
            "owner_slug": "pasteur-dakar",
            "name": "lassa-isolate-2023",
            "domain": "virus",
            "access": "public",
            "description": "Lassa virus surveillance in West Africa",
        },
    )
    assert create_resp.status_code == 201
    repo_data = create_resp.json()
    assert repo_data["slug"] == "pasteur-dakar/lassa-isolate-2023"

    # Verify bare git repo was created on disk
    bare_path = GitRepoManager(git_root=settings.GIT_ROOT).get_repo_path(
        "pasteur-dakar", "lassa-isolate-2023"
    )
    assert bare_path.exists()

    # 4. Preupload Inquiry for OpenXet CAS
    preupload_resp = await test_client.post(
        "/api/repos/pasteur-dakar/lassa-isolate-2023/preupload",
        headers=headers,
        json={"filenames": ["assemblies/isolate_01.fasta"]},
    )
    assert preupload_resp.status_code == 200
    preupload_data = preupload_resp.json()
    assert "cas_write_token" in preupload_data
    assert preupload_data["repo_slug"] == "pasteur-dakar/lassa-isolate-2023"

    # 5. Commit Files
    commit_resp = await test_client.post(
        "/api/repos/pasteur-dakar/lassa-isolate-2023/commit",
        headers=headers,
        json={
            "branch": "main",
            "message": "Add initial isolate assembly",
            "files": [
                {
                    "path": "assemblies/isolate_01.fasta",
                    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                    "xet_hash": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
                    "size_bytes": 1024,
                }
            ],
        },
    )
    assert commit_resp.status_code == 201
    assert commit_resp.json()["status"] == "committed"

    # 6. Git Smart-HTTP Info/Refs
    git_resp = await test_client.get(
        "/pasteur-dakar/lassa-isolate-2023.git/info/refs?service=git-upload-pack",
        headers=headers,
    )
    assert git_resp.status_code == 200
    assert "application/x-git-upload-pack-advertisement" in git_resp.headers.get("content-type", "")

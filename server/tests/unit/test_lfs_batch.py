"""Unit tests for Git LFS Batch protocol and object transfer (M1-14, M1-15)."""

import hashlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ubuntubio.config import settings
from ubuntubio.db.models import Base
from ubuntubio.db.session import get_db_session
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
async def test_git_lfs_batch_and_object_transfer(test_client: AsyncClient) -> None:
    """Test full Git LFS batch negotiation, upload with sha256 checksum, and download."""
    # 1. Dev Login & Create Public Repo
    login = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0007-7777-7777", "name": "LFS Developer"},
    )
    headers = {"Authorization": f"Bearer {login.json()['raw_token']}"}

    create_resp = await test_client.post(
        "/api/repos",
        headers=headers,
        json={
            "owner_slug": "cphi",
            "name": "cholera-vibrio-raw",
            "domain": "bacteria",
            "access": "public",
        },
    )
    assert create_resp.status_code == 201

    payload_data = b">sample_vibrio_1\nATGCGATCGATCGATCGATC"
    payload_oid = hashlib.sha256(payload_data).hexdigest()
    payload_size = len(payload_data)

    # 2. Negotiate LFS Upload Batch
    lfs_batch_req = {
        "operation": "upload",
        "transfers": ["basic"],
        "objects": [{"oid": payload_oid, "size": payload_size}],
    }
    batch_resp = await test_client.post(
        "/cphi/cholera-vibrio-raw.git/info/lfs/objects/batch",
        headers=headers,
        json=lfs_batch_req,
    )
    assert batch_resp.status_code == 200
    batch_data = batch_resp.json()
    assert batch_data["transfer"] == "basic"
    assert len(batch_data["objects"]) == 1

    upload_action = batch_data["objects"][0]["actions"]["upload"]
    upload_href = upload_action["href"]
    upload_auth = upload_action["header"]["Authorization"]

    # 3. Perform LFS Upload PUT
    upload_path = upload_href.replace("http://localhost:8000", "")
    upload_put_resp = await test_client.put(
        upload_path,
        content=payload_data,
        headers={"Authorization": upload_auth},
    )
    assert upload_put_resp.status_code == 200
    assert upload_put_resp.json()["status"] == "uploaded"

    # 4. Negotiate LFS Download Batch
    lfs_download_req = {
        "operation": "download",
        "transfers": ["basic"],
        "objects": [{"oid": payload_oid, "size": payload_size}],
    }
    download_batch_resp = await test_client.post(
        "/cphi/cholera-vibrio-raw.git/info/lfs/objects/batch",
        headers=headers,
        json=lfs_download_req,
    )
    assert download_batch_resp.status_code == 200
    dl_data = download_batch_resp.json()
    download_action = dl_data["objects"][0]["actions"]["download"]
    download_href = download_action["href"]
    download_auth = download_action["header"]["Authorization"]

    # 5. Perform LFS Download GET
    download_path = download_href.replace("http://localhost:8000", "")
    download_get_resp = await test_client.get(
        download_path,
        headers={"Authorization": download_auth},
    )
    assert download_get_resp.status_code == 200
    assert download_get_resp.content == payload_data

"""Unit tests for researcher username handles and namespace collision prevention."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ubuntubio.auth.username import extract_orcid_suffix, slugify_researcher_name
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


def test_slugify_researcher_name() -> None:
    """Test researcher name cleaning and handle extraction."""
    assert slugify_researcher_name("Dr. Redeemer Okekale") == "redeemer-okekale"
    assert slugify_researcher_name("Prof. Amina Diallo") == "amina-diallo"
    assert slugify_researcher_name("John Smith Jr.") == "john-smith-jr"
    assert slugify_researcher_name("   ") == "researcher"


def test_extract_orcid_suffix() -> None:
    """Test extracting clean 4-char suffix from ORCID ID."""
    assert extract_orcid_suffix("0009-0000-2900-592X") == "592x"
    assert extract_orcid_suffix("0000-0002-1825-0097") == "0097"


@pytest.mark.asyncio
async def test_username_assigned_on_login(test_client: AsyncClient) -> None:
    """Verify that logging in via dev-login sets a unique username and returns it in whoami."""
    login_resp = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0009-0000-2900-592X", "name": "Redeemer Okekale"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["raw_token"]

    whoami_resp = await test_client.get(
        "/api/auth/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert whoami_resp.status_code == 200
    profile = whoami_resp.json()
    assert profile["username"] == "redeemer-okekale"


@pytest.mark.asyncio
async def test_namespace_impersonation_blocked(test_client: AsyncClient) -> None:
    """Verify that user A cannot create a repository under user B's username."""
    # User A registers as 'alice'
    login_a = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0001-1111-1111", "name": "Alice Researcher"},
    )
    assert login_a.status_code == 200

    # User B registers as 'bob'
    login_b = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0002-2222-2222", "name": "Bob Researcher"},
    )
    token_b = login_b.json()["raw_token"]

    # Bob attempts to create a dataset under Alice's namespace 'alice-researcher'
    resp = await test_client.post(
        "/api/repos",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "owner_slug": "alice-researcher",
            "name": "hijacked-dataset",
            "domain": "virus",
            "access": "public",
        },
    )
    assert resp.status_code == 403
    assert "That handle belongs to another registered researcher" in resp.json()["detail"]

    # Bob creates under his own namespace 'bob-researcher' -> Success
    success_resp = await test_client.post(
        "/api/repos",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "owner_slug": "bob-researcher",
            "name": "legit-dataset",
            "domain": "virus",
            "access": "public",
        },
    )
    assert success_resp.status_code == 201
    assert success_resp.json()["slug"] == "bob-researcher/legit-dataset"

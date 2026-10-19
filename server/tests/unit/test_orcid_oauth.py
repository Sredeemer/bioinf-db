"""Unit tests for ORCID OAuth2 login flow (M1-03)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient, Response
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
async def test_orcid_authorize_redirect(test_client: AsyncClient) -> None:
    """Test /api/auth/orcid/authorize generates proper ORCID OAuth URL."""
    resp = await test_client.get("/api/auth/orcid/authorize", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "sandbox.orcid.org/oauth/authorize" in location
    assert f"client_id={settings.ORCID_CLIENT_ID}" in location
    assert "scope=/authenticate" in location


@pytest.mark.asyncio
async def test_orcid_callback_success(test_client: AsyncClient) -> None:
    """Test /api/auth/orcid/callback exchanges authorization code for user and token."""
    mock_orcid_payload = {
        "access_token": "mock_orcid_access_token",
        "token_type": "bearer",
        "orcid": "0000-0003-9999-9999",
        "name": "Dr. Chidi Okonkwo",
    }
    mock_post = AsyncMock()
    mock_post.return_value = Response(200, json=mock_orcid_payload)

    with patch("httpx.AsyncClient.post", new=mock_post):
        resp = await test_client.get(
            "/api/auth/orcid/callback?code=mock_orcid_auth_code",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "raw_token" in data
        assert data["raw_token"].startswith("ubp_")
        assert data["scope"] == "write"

"""Unit tests for RFC 8628 Device Authorization Grant."""

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


@pytest.fixture
async def authenticated_researcher(test_client: AsyncClient) -> dict[str, str]:
    """Create a test user and personal access token for browser simulation."""
    # We can create user directly via db override or dev-login
    resp = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0002-1825-0097", "name": "Dr. Researcher"},
    )
    assert resp.status_code == 200
    data = resp.json()
    return {"token": data["raw_token"], "orcid": "0000-0002-1825-0097"}


@pytest.mark.asyncio
async def test_device_flow_complete_lifecycle(
    test_client: AsyncClient, authenticated_researcher: dict[str, str]
) -> None:
    """Test full device code grant: initiate -> poll (pending) -> verify -> exchange (200)."""
    # 1. Terminal initiates flow
    resp = await test_client.post("/api/auth/device/code")
    assert resp.status_code == 200
    code_data = resp.json()
    assert "device_code" in code_data
    assert "user_code" in code_data
    assert code_data["user_code"].startswith("UBIO-")
    assert code_data["interval"] == 2
    assert "verification_uri" in code_data

    device_code = code_data["device_code"]
    user_code = code_data["user_code"]

    # 2. Terminal polls before approval -> HTTP 400 authorization_pending
    poll_resp = await test_client.post(
        "/api/auth/device/token",
        json={"device_code": device_code},
    )
    assert poll_resp.status_code == 400
    assert poll_resp.json()["detail"] == "authorization_pending"

    # 3. Researcher approves in browser
    headers = {"Authorization": f"Bearer {authenticated_researcher['token']}"}
    verify_resp = await test_client.post(
        "/api/auth/device/verify",
        headers=headers,
        json={"user_code": user_code},
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["success"] is True

    # 4. Terminal polls again -> HTTP 200 with access_token
    token_resp = await test_client.post(
        "/api/auth/device/token",
        json={"device_code": device_code},
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    assert "access_token" in token_data
    assert token_data["access_token"].startswith("ubp_")
    assert token_data["token_type"] == "Bearer"

    # 5. Subsequent poll fails because device record is single-use and destroyed
    second_poll = await test_client.post(
        "/api/auth/device/token",
        json={"device_code": device_code},
    )
    assert second_poll.status_code == 400
    assert second_poll.json()["detail"] == "invalid_grant"


@pytest.mark.asyncio
async def test_device_verify_invalid_code(
    test_client: AsyncClient, authenticated_researcher: dict[str, str]
) -> None:
    """Verifying non-existent user code returns 404."""
    headers = {"Authorization": f"Bearer {authenticated_researcher['token']}"}
    resp = await test_client.post(
        "/api/auth/device/verify",
        headers=headers,
        json={"user_code": "UBIO-NONEXIST"},
    )
    assert resp.status_code == 404
    assert "Invalid or unrecognized" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_device_verify_requires_auth(test_client: AsyncClient) -> None:
    """Unauthenticated call to /device/verify is rejected."""
    resp = await test_client.post(
        "/api/auth/device/verify",
        json={"user_code": "UBIO-TEST-12"},
    )
    assert resp.status_code == 401

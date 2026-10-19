"""Unit tests for organization and membership management (M1-05)."""

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
async def test_org_creation_and_membership_lifecycle(test_client: AsyncClient) -> None:
    """Test creating an org, adding members with roles, and access control."""
    # 1. Dev login for Admin User
    admin_login = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0001-1111-1111", "name": "Admin Researcher"},
    )
    admin_token = admin_login.json()["raw_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Dev login for Regular User
    user_login = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0002-2222-2222", "name": "Bioinformatician User"},
    )
    user_token = user_login.json()["raw_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}
    user_whoami = (await test_client.get("/api/auth/whoami", headers=user_headers)).json()
    user_id = user_whoami["id"]

    # 3. Create Org as Admin User
    org_resp = await test_client.post(
        "/api/orgs",
        headers=admin_headers,
        json={
            "slug": "acegid",
            "name": "African Centre of Excellence for Genomics of Infectious Diseases",
            "description": "Genomics hub in Nigeria",
        },
    )
    assert org_resp.status_code == 201
    assert org_resp.json()["slug"] == "acegid"

    # 4. List members (admin should be automatically included as admin)
    members_resp = await test_client.get("/api/orgs/acegid/members", headers=admin_headers)
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["role"] == "admin"
    assert members[0]["user_name"] == "Admin Researcher"

    # 5. Non-member cannot list members
    forbidden_list = await test_client.get("/api/orgs/acegid/members", headers=user_headers)
    assert forbidden_list.status_code == 403

    # 6. Admin adds user as "write" member
    add_resp = await test_client.post(
        "/api/orgs/acegid/members",
        headers=admin_headers,
        json={"user_id": user_id, "role": "write"},
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["role"] == "write"

    # 7. User can now list members
    user_list = await test_client.get("/api/orgs/acegid/members", headers=user_headers)
    assert user_list.status_code == 200
    assert len(user_list.json()) == 2

    # 8. Non-admin cannot add or remove members
    fail_add = await test_client.post(
        "/api/orgs/acegid/members",
        headers=user_headers,
        json={"user_id": user_id, "role": "admin"},
    )
    assert fail_add.status_code == 403

    # 9. Admin removes user
    del_resp = await test_client.delete(
        f"/api/orgs/acegid/members/{user_id}", headers=admin_headers
    )
    assert del_resp.status_code == 204

    # 10. Attempting to delete sole admin fails with 400
    admin_id = (await test_client.get("/api/auth/whoami", headers=admin_headers)).json()["id"]
    sole_admin_del = await test_client.delete(
        f"/api/orgs/acegid/members/{admin_id}", headers=admin_headers
    )
    assert sole_admin_del.status_code == 400

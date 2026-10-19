"""Tests for gated access requests, DUA acceptance, and audit logging (M1-16, M1-17)."""

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
async def test_gated_dataset_workflow_and_audit_export(test_client: AsyncClient) -> None:
    """Test DUA acceptance, access request lifecycle (pending -> approved), and audit export."""
    # 1. Owner Login
    owner_login = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0005-5555-5555", "name": "Dr. Owner"},
    )
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['raw_token']}"}

    # 2. Requester Login
    req_login = await test_client.post(
        "/api/auth/dev-login",
        json={"orcid_id": "0000-0006-6666-6666", "name": "Dr. Requester"},
    )
    req_headers = {"Authorization": f"Bearer {req_login.json()['raw_token']}"}

    # 3. Create Gated Repository
    create_resp = await test_client.post(
        "/api/repos",
        headers=owner_headers,
        json={
            "owner_slug": "nicd",
            "name": "crimean-congo-safrica",
            "domain": "virus",
            "access": "gated",
            "description": "Sensitive viral hemorrhagic fever data",
        },
    )
    assert create_resp.status_code == 201

    # 4. Requester attempts access request without accepting DUA -> 400 Bad Request
    fail_req = await test_client.post(
        "/api/repos/nicd/crimean-congo-safrica/access-requests",
        headers=req_headers,
        json={"justification": "Academic research into tick-borne viral ecology"},
    )
    assert fail_req.status_code == 400
    assert "accept the Data Use Agreement" in fail_req.json()["detail"]

    # 5. Requester accepts DUA
    dua_resp = await test_client.post(
        "/api/repos/nicd/crimean-congo-safrica/dua/accept",
        headers=req_headers,
        json={"dua_version": "1.0"},
    )
    assert dua_resp.status_code == 201
    assert dua_resp.json()["dua_version"] == "1.0"

    # 6. Requester submits access request
    access_resp = await test_client.post(
        "/api/repos/nicd/crimean-congo-safrica/access-requests",
        headers=req_headers,
        json={"justification": "Academic research into tick-borne viral ecology"},
    )
    assert access_resp.status_code == 201
    req_data = access_resp.json()
    assert req_data["status"] == "pending"
    req_id = req_data["id"]

    # 7. Owner lists access requests
    list_resp = await test_client.get(
        "/api/repos/nicd/crimean-congo-safrica/access-requests",
        headers=owner_headers,
    )
    assert list_resp.status_code == 200
    requests = list_resp.json()
    assert len(requests) == 1
    assert requests[0]["id"] == req_id

    # 8. Owner approves access request
    decision_resp = await test_client.post(
        f"/api/repos/nicd/crimean-congo-safrica/access-requests/{req_id}/decision",
        headers=owner_headers,
        json={"decision": "approved", "reason": "Verified academic affiliation"},
    )
    assert decision_resp.status_code == 200
    assert decision_resp.json()["status"] == "approved"

    # 9. Export Audit Log (JSON format)
    audit_json = await test_client.get(
        "/api/repos/nicd/crimean-congo-safrica/audit-log?format=json",
        headers=owner_headers,
    )
    assert audit_json.status_code == 200
    events = audit_json.json()
    assert len(events) >= 3  # accept_dua, request_access, decision_approved
    actions = [e["action"] for e in events]
    assert "accept_dua" in actions
    assert "request_access" in actions
    assert "decision_approved" in actions

    # 10. Export Audit Log (CSV format)
    audit_csv = await test_client.get(
        "/api/repos/nicd/crimean-congo-safrica/audit-log?format=csv",
        headers=owner_headers,
    )
    assert audit_csv.status_code == 200
    assert "text/csv" in audit_csv.headers["content-type"]
    assert "id,timestamp,user_id,action,resource_path,ip_hash" in audit_csv.text
    assert "accept_dua" in audit_csv.text

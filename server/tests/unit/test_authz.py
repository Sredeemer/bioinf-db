"""Table-driven unit tests for the authorization matrix (T-ACC-01 to T-ACC-16)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ubuntubio.auth.authz import AuthorizationService, RepoAction
from ubuntubio.db.models import (
    AccessRequestModel,
    Base,
    DuaAcceptanceModel,
    MembershipModel,
    OrganizationModel,
    RepositoryModel,
    UserModel,
)

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def session() -> AsyncSession:  # type: ignore[misc]
    """Provide an isolated database session with full schema."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_public_repo_access(session: AsyncSession) -> None:
    """T-ACC-01..04: Anonymous and standard users on Public datasets."""
    authz = AuthorizationService()
    owner = UserModel(orcid_id="0000-0001-0000-0001", name="Owner")
    other_user = UserModel(orcid_id="0000-0002-0000-0002", name="Reader")
    session.add_all([owner, other_user])
    await session.commit()

    repo = RepositoryModel(
        slug="owner/public-dataset",
        name="public-dataset",
        owner_type="user",
        owner_id=owner.id,
        domain="bacteria",
        access="public",
        license="cc-by-4.0",
    )
    session.add(repo)
    await session.commit()

    # Anonymous user checks
    assert await authz.can_perform_action(session, None, repo, RepoAction.READ_METADATA)
    assert await authz.can_perform_action(session, None, repo, RepoAction.DOWNLOAD_DATA)
    assert not await authz.can_perform_action(session, None, repo, RepoAction.WRITE_COMMIT)
    assert not await authz.can_perform_action(session, None, repo, RepoAction.MANAGE_SETTINGS)

    # Other authenticated user checks
    assert await authz.can_perform_action(session, other_user, repo, RepoAction.READ_METADATA)
    assert await authz.can_perform_action(session, other_user, repo, RepoAction.DOWNLOAD_DATA)
    assert not await authz.can_perform_action(session, other_user, repo, RepoAction.WRITE_COMMIT)

    # Owner checks
    assert await authz.can_perform_action(session, owner, repo, RepoAction.WRITE_COMMIT)
    assert await authz.can_perform_action(session, owner, repo, RepoAction.MANAGE_SETTINGS)


@pytest.mark.asyncio
async def test_gated_repo_access(session: AsyncSession) -> None:
    """T-ACC-05..08: Access evaluation for Gated datasets with approval & DUA acceptance."""
    authz = AuthorizationService()
    owner = UserModel(orcid_id="0000-0001-0000-0001", name="Owner")
    requester = UserModel(orcid_id="0000-0003-0000-0003", name="Researcher")
    session.add_all([owner, requester])
    await session.commit()

    repo = RepositoryModel(
        slug="owner/gated-pathogen-data",
        name="gated-pathogen-data",
        owner_type="user",
        owner_id=owner.id,
        domain="virus",
        access="gated",
        license="custom-dua",
    )
    session.add(repo)
    await session.commit()

    # 1. Requester before applying: can read metadata, but cannot download
    assert await authz.can_perform_action(session, requester, repo, RepoAction.READ_METADATA)
    assert not await authz.can_perform_action(session, requester, repo, RepoAction.DOWNLOAD_DATA)

    # 2. Requester accepted DUA only: still cannot download without approval
    dua = DuaAcceptanceModel(repo_id=repo.id, user_id=requester.id, dua_version="v1.0")
    session.add(dua)
    await session.commit()
    assert not await authz.can_perform_action(session, requester, repo, RepoAction.DOWNLOAD_DATA)

    # 3. Requester receives approved request: can download!
    request = AccessRequestModel(
        repo_id=repo.id,
        user_id=requester.id,
        status="approved",
        justification="Surveillance analysis in West Africa",
    )
    session.add(request)
    await session.commit()
    assert await authz.can_perform_action(session, requester, repo, RepoAction.DOWNLOAD_DATA)


@pytest.mark.asyncio
async def test_private_repo_and_org_roles(session: AsyncSession) -> None:
    """T-ACC-09..12: Access control on Private datasets based on organization roles."""
    authz = AuthorizationService()
    admin_user = UserModel(orcid_id="0000-0001-0000-0010", name="Admin")
    writer_user = UserModel(orcid_id="0000-0001-0000-0020", name="Writer")
    reader_user = UserModel(orcid_id="0000-0001-0000-0030", name="Reader")
    external_user = UserModel(orcid_id="0000-0001-0000-0040", name="External")
    org = OrganizationModel(slug="kisi-consortium", name="KEMRI Consortium")
    session.add_all([admin_user, writer_user, reader_user, external_user, org])
    await session.commit()

    # Assign roles
    session.add_all(
        [
            MembershipModel(user_id=admin_user.id, org_id=org.id, role="admin"),
            MembershipModel(user_id=writer_user.id, org_id=org.id, role="write"),
            MembershipModel(user_id=reader_user.id, org_id=org.id, role="read"),
        ]
    )
    repo = RepositoryModel(
        slug="kisi-consortium/private-outbreak",
        name="private-outbreak",
        owner_type="org",
        owner_id=org.id,
        domain="virus",
        access="private",
        license="cc-by-nc-4.0",
    )
    session.add(repo)
    await session.commit()

    # External user has zero access
    ext_read = await authz.can_perform_action(
        session, external_user, repo, RepoAction.READ_METADATA
    )
    assert not ext_read
    ext_download = await authz.can_perform_action(
        session, external_user, repo, RepoAction.DOWNLOAD_DATA
    )
    assert not ext_download

    # Reader can read metadata and download data, but not write or manage
    assert await authz.can_perform_action(session, reader_user, repo, RepoAction.READ_METADATA)
    assert await authz.can_perform_action(session, reader_user, repo, RepoAction.DOWNLOAD_DATA)
    assert not await authz.can_perform_action(session, reader_user, repo, RepoAction.WRITE_COMMIT)

    # Writer can read, download, and write
    assert await authz.can_perform_action(session, writer_user, repo, RepoAction.WRITE_COMMIT)
    writer_manage = await authz.can_perform_action(
        session, writer_user, repo, RepoAction.MANAGE_SETTINGS
    )
    assert not writer_manage

    # Admin has full privileges
    assert await authz.can_perform_action(session, admin_user, repo, RepoAction.MANAGE_SETTINGS)
    assert await authz.can_perform_action(session, admin_user, repo, RepoAction.WRITE_COMMIT)

"""Unit tests for SQLAlchemy 2.0 database models and schema integrity."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select

from ubuntubio.db.models import (
    Base,
    MembershipModel,
    OrganizationModel,
    PersonalAccessTokenModel,
    RepositoryModel,
    UserModel,
)

# Test in-memory SQLite async engine
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_session() -> AsyncSession:  # type: ignore[misc]
    """Provide an isolated in-memory SQLite async session with all tables created."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_create_user_and_orcid_unique(test_session: AsyncSession) -> None:
    """Verify user creation and unique ORCID constraint."""
    user1 = UserModel(
        orcid_id="0000-0002-1825-0097",
        name="Dr. Amina Diallo",
        email="amina@pasteur.sn",
    )
    test_session.add(user1)
    await test_session.commit()

    # Query back
    stmt = select(UserModel).where(UserModel.orcid_id == "0000-0002-1825-0097")
    result = await test_session.execute(stmt)
    saved_user = result.scalar_one()
    assert saved_user.name == "Dr. Amina Diallo"
    assert saved_user.id is not None

    # Duplicate ORCID must fail
    user2 = UserModel(
        orcid_id="0000-0002-1825-0097",
        name="Duplicate User",
    )
    test_session.add(user2)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()


async def test_org_membership_and_roles(test_session: AsyncSession) -> None:
    """Verify organization creation, membership assignment, and cascading."""
    user = UserModel(orcid_id="0000-0001-2345-6789", name="Kofi Mensah")
    org = OrganizationModel(slug="nmimr-ghana", name="Noguchi Memorial Institute")
    test_session.add_all([user, org])
    await test_session.commit()

    membership = MembershipModel(
        user_id=user.id,
        org_id=org.id,
        role="admin",
    )
    test_session.add(membership)
    await test_session.commit()

    stmt = select(MembershipModel).where(MembershipModel.user_id == user.id)
    result = await test_session.execute(stmt)
    saved_membership = result.scalar_one()
    assert saved_membership.role == "admin"


async def test_personal_access_token_creation(test_session: AsyncSession) -> None:
    """Verify PAT token storage with hashing."""
    user = UserModel(orcid_id="0000-0003-9876-5432", name="Zainab Al-Mansoor")
    test_session.add(user)
    await test_session.commit()

    token = PersonalAccessTokenModel(
        token_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        name="Laptop CLI Token",
        scope="write",
        user_id=user.id,
    )
    test_session.add(token)
    await test_session.commit()

    stmt = select(PersonalAccessTokenModel).where(PersonalAccessTokenModel.user_id == user.id)
    res = await test_session.execute(stmt)
    saved_token = res.scalar_one()
    assert saved_token.name == "Laptop CLI Token"
    assert saved_token.scope == "write"


async def test_repository_creation(test_session: AsyncSession) -> None:
    """Verify repository creation with access tiers."""
    repo = RepositoryModel(
        slug="nmimr-ghana/vibrio-surveillance-2023",
        name="vibrio-surveillance-2023",
        owner_type="org",
        owner_id="org-uuid-1",
        domain="bacteria",
        access="gated",
        license="cc-by-4.0",
        is_verified_african=True,
    )
    test_session.add(repo)
    await test_session.commit()

    stmt = select(RepositoryModel).where(
        RepositoryModel.slug == "nmimr-ghana/vibrio-surveillance-2023"
    )
    res = await test_session.execute(stmt)
    saved_repo = res.scalar_one()
    assert saved_repo.access == "gated"
    assert saved_repo.is_verified_african is True

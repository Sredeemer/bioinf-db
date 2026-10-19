"""Unit and integration tests for SQLite aiosqlite WAL mode, PRAGMAs, and lifespan."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ubuntubio.db.models import Base, UserModel
from ubuntubio.db.session import create_app_engine


@pytest.mark.asyncio
async def test_sqlite_pragmas_and_wal_mode(tmp_path: Path) -> None:
    """Verify that SQLite engine initializes with foreign_keys=ON, WAL mode, and lock timeout."""
    db_file = tmp_path / "subfolder" / "test_wal.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    test_engine = create_app_engine(db_url)
    try:
        async with test_engine.connect() as conn:
            # Check foreign keys
            fk_res = await conn.execute(text("PRAGMA foreign_keys;"))
            assert fk_res.scalar() == 1

            # Check journal mode (WAL)
            jm_res = await conn.execute(text("PRAGMA journal_mode;"))
            assert str(jm_res.scalar()).lower() == "wal"

            # Check busy timeout
            bt_res = await conn.execute(text("PRAGMA busy_timeout;"))
            assert bt_res.scalar() == 10000
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_session_engine_auto_creates_parent_directory(tmp_path: Path) -> None:
    """Ensure create_app_engine automatically creates missing parent directory."""
    nested_dir = tmp_path / "deep" / "nested" / "path"
    assert not nested_dir.exists()

    db_file = nested_dir / "ubuntubio.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    eng = create_app_engine(db_url)
    assert nested_dir.exists()
    await eng.dispose()


@pytest.mark.asyncio
async def test_wal_concurrent_reads_during_uncommitted_write(tmp_path: Path) -> None:
    """Verify WAL mode allows concurrent readers to query DB during an active write transaction."""
    db_file = tmp_path / "wal_concurrency.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    engine_rw = create_app_engine(db_url)

    # Create tables
    async with engine_rw.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine_rw, class_=AsyncSession, expire_on_commit=False)

    # Initial seed
    async with session_maker() as s:
        user = UserModel(
            orcid_id="0000-0001-1111-2222",
            name="Initial User",
            email="initial@ubuntubio.org",
        )
        s.add(user)
        await s.commit()

    # Open uncommitted write transaction in writer session
    writer_session = session_maker()
    new_user = UserModel(
        orcid_id="0000-0002-2222-3333",
        name="Pending User",
        email="pending@ubuntubio.org",
    )
    writer_session.add(new_user)
    await writer_session.flush()

    # Reader session concurrently reads without blocking
    async with session_maker() as reader_session:
        res = await reader_session.execute(text("SELECT count(*) FROM users"))
        count = res.scalar()
        # In WAL isolation, reader sees the committed snapshot (1 user)
        assert count == 1

    # Now commit writer transaction
    await writer_session.commit()
    await writer_session.close()

    # Reader now sees updated count (2 users)
    async with session_maker() as reader_session:
        res = await reader_session.execute(text("SELECT count(*) FROM users"))
        assert res.scalar() == 2

    await engine_rw.dispose()


@pytest.mark.asyncio
async def test_lifespan_auto_creates_tables(tmp_path: Path) -> None:
    """Verify application lifespan creates all database tables."""
    from ubuntubio.db import session as db_session
    from ubuntubio.main import app, lifespan

    test_db = tmp_path / "lifespan.db"
    orig_engine = db_session.engine
    test_engine = create_app_engine(f"sqlite+aiosqlite:///{test_db}")
    db_session.engine = test_engine

    try:
        async with lifespan(app), test_engine.connect() as conn:
            res = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in res.fetchall()]
            assert "users" in tables
            assert "organizations" in tables
            assert "repositories" in tables
    finally:
        db_session.engine = orig_engine
        await test_engine.dispose()

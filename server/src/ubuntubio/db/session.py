"""Database engine and asynchronous session management."""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger

logger = get_logger("ubuntubio.db")


def create_app_engine(url_str: str | None = None) -> AsyncEngine:
    """Create a configured AsyncEngine with SQLite WAL mode, PRAGMAs, and directory creation."""
    db_url_str = url_str or settings.DATABASE_URL
    parsed_url = make_url(db_url_str)
    is_sqlite = parsed_url.get_backend_name() == "sqlite"

    logger.info(
        "Initializing database async engine",
        extra={
            "backend": parsed_url.get_backend_name(),
            "database": parsed_url.database,
        },
    )

    connect_args: dict[str, Any] = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False
        if parsed_url.database and parsed_url.database != ":memory:":
            db_path = Path(parsed_url.database).resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)

    eng = create_async_engine(
        db_url_str,
        echo=settings.DEBUG and settings.ENV == "development",
        future=True,
        pool_pre_ping=True,
        connect_args=connect_args,
    )

    if is_sqlite:

        @event.listens_for(eng.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            """Enforce strict relational integrity, WAL mode, and lock timeouts on SQLite."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()

    return eng


# Global async engine
engine: AsyncEngine = create_app_engine()

# Async session factory
AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for scoped asynchronous database sessions."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

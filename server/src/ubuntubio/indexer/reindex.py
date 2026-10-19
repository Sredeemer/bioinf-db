"""Admin reindexing functionality to rebuild Meilisearch indexes from database records."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.db.models import RepositoryModel
from ubuntubio.indexer.meili import DATASETS_INDEX, SAMPLES_INDEX, MeiliService, meili_service
from ubuntubio.indexer.worker import index_repository


async def reindex_all_repositories(
    session: AsyncSession,
    meili: MeiliService | None = None,
) -> dict[str, Any]:
    """Rebuild all Meilisearch datasets and samples indexes from PostgreSQL records."""
    active_meili = meili or meili_service

    # 1. Initialize clean index configurations
    await active_meili.init_indexes()

    # Clear current documents in mock mode
    if active_meili.mock_mode:
        active_meili._mock_indices[DATASETS_INDEX].clear()
        active_meili._mock_indices[SAMPLES_INDEX].clear()

    # 2. Fetch all repositories
    stmt = select(RepositoryModel).order_by(RepositoryModel.created_at.asc())
    res = await session.execute(stmt)
    repos = res.scalars().all()

    indexed_count = 0
    total_samples = 0
    results: list[dict[str, Any]] = []

    for r in repos:
        try:
            stats = await index_repository(session=session, repo_slug=r.slug, meili=active_meili)
            indexed_count += 1
            total_samples += stats.get("samples_count", 0)
            results.append(stats)
        except Exception as exc:
            results.append({"status": "failed", "repo_slug": r.slug, "error": str(exc)})

    return {
        "status": "completed",
        "repositories_processed": indexed_count,
        "total_samples": total_samples,
        "details": results,
    }

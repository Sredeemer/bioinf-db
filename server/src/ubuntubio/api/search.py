"""Search API endpoints with strict African bioinformatics access filtering using SQLite FTS5."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.api.dependencies import get_optional_user, require_authenticated_user
from ubuntubio.auth.authz import AuthorizationService
from ubuntubio.db.models import UserModel
from ubuntubio.db.session import get_db_session
from ubuntubio.indexer.fts import search_service
from ubuntubio.indexer.meili import meili_service
from ubuntubio.indexer.reindex import reindex_all_repositories

router = APIRouter(prefix="/api/search", tags=["Search"])
authz_service = AuthorizationService()


@router.get("", response_model=dict[str, Any])
@router.get("/datasets", response_model=dict[str, Any])
async def search_datasets(
    q: Annotated[str, Query(description="Keyword search across titles, descriptions, genera")] = "",
    domain: Annotated[str | None, Query(description="Biological domain filter")] = None,
    country: Annotated[str | None, Query(description="AU member state ISO-2 country code")] = None,
    taxon_id: Annotated[int | None, Query(description="NCBI Taxon ID filter")] = None,
    genus: Annotated[str | None, Query(description="Taxonomic genus filter")] = None,
    family: Annotated[str | None, Query(description="Taxonomic family filter")] = None,
    access: Annotated[str | None, Query(description="Access tier filter")] = None,
    is_verified_african: Annotated[bool | None, Query(description="Verified African flag")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: UserModel | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Search African bioinformatics datasets with BM25 relevance ranking and access filtering."""
    return await search_service.search_datasets(
        session=session,
        query=q,
        domain=domain,
        country=country,
        taxon_id=taxon_id,
        genus=genus,
        family=family,
        access=access,
        is_verified_african=is_verified_african,
        limit=limit,
        offset=offset,
        user=user,
    )


@router.get("/samples", response_model=dict[str, Any])
async def search_samples(
    q: Annotated[str, Query(description="Keyword search across sample IDs and hosts")] = "",
    country: Annotated[str | None, Query(description="AU member state ISO-2 country code")] = None,
    taxon_id: Annotated[int | None, Query(description="NCBI Taxon ID filter")] = None,
    genus: Annotated[str | None, Query(description="Taxonomic genus filter")] = None,
    host: Annotated[str | None, Query(description="Host organism filter")] = None,
    isolation_source: Annotated[str | None, Query(description="Isolation source filter")] = None,
    repo_slug: Annotated[str | None, Query(description="Repository slug filter")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: UserModel | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Search individual biological samples with geolocation, environmental filters,
    and BM25 ranking.
    """
    return await search_service.search_samples(
        session=session,
        query=q,
        country=country,
        taxon_id=taxon_id,
        genus=genus,
        host=host,
        isolation_source=isolation_source,
        repo_slug=repo_slug,
        limit=limit,
        offset=offset,
        user=user,
    )


admin_router = APIRouter(prefix="/api/admin", tags=["Admin"])


@admin_router.post("/reindex", response_model=dict[str, Any])
async def trigger_reindex(
    user: UserModel = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Rebuild all search indexes from database records."""
    res = await reindex_all_repositories(session=session)
    return res


__all__ = ["admin_router", "meili_service", "router", "search_service"]

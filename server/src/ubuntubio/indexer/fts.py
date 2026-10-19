"""Native SQLite FTS5 search engine with BM25 word-based ranking and faceted filtering."""

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from ubuntubio.auth.authz import AuthorizationService
from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import (
    DatasetSearchRecordModel,
    UserModel,
    utc_now,
)

logger = get_logger("ubuntubio.indexer.fts")
authz_service = AuthorizationService()


async def init_fts_tables(conn: AsyncConnection) -> None:
    """Create SQLite FTS5 virtual tables if they do not already exist."""
    logger.info("Ensuring SQLite FTS5 tables are initialized (datasets_fts, samples_fts)")
    await conn.execute(
        text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS datasets_fts USING fts5(
            repo_id UNINDEXED,
            slug,
            title,
            description,
            countries,
            genus,
            family,
            benefit_sharing,
            tokenize = 'porter unicode61'
        );
    """)
    )

    await conn.execute(
        text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS samples_fts USING fts5(
            sample_id_str UNINDEXED,
            repo_id UNINDEXED,
            sample_id,
            admin1,
            host,
            isolation_source,
            genus,
            family,
            country,
            tokenize = 'porter unicode61'
        );
    """)
    )


def sanitize_fts_query(query: str) -> str:
    """Sanitize user query for SQLite FTS5 word-based prefix and phrase matching."""
    stripped = query.strip()
    if not stripped:
        return ""

    # Check for exact quoted phrase
    if stripped.startswith('"') and stripped.endswith('"') and len(stripped) > 2:
        inner = re.sub(r'["\']', "", stripped[1:-1]).strip()
        words = re.findall(r"[\w-]+", inner)
        if words:
            return f'"{" ".join(words)}"'
        return ""

    tokens = re.findall(r"[\w-]+", stripped)
    if not tokens:
        return ""

    # Attach prefix wildcard to each token for live incremental autocomplete
    prefix_tokens = [f'"{t}"*' if not t.endswith("*") else f'"{t}"' for t in tokens]
    return " ".join(prefix_tokens)


class SqliteSearchService:
    """Embedded SQLite FTS5 full-text search and faceted filtering service."""

    async def index_dataset(
        self,
        session: AsyncSession,
        repo_id: str,
        slug: str,
        name: str,
        title: str,
        description: str | None,
        domain: str,
        access: str,
        license: str,
        countries: list[str],
        taxa: list[int],
        genera: list[str],
        families: list[str],
        is_verified_african: bool,
        owner_type: str,
        owner_id: str,
        samples_count: int,
        benefit_sharing: str | None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        """Upsert relational search summary and atomic FTS5 index document."""
        now = utc_now()
        created = created_at or now
        updated = updated_at or now

        # 1. Upsert dataset_search_records
        await session.execute(
            delete(DatasetSearchRecordModel).where(DatasetSearchRecordModel.repo_id == repo_id)
        )

        record = DatasetSearchRecordModel(
            repo_id=repo_id,
            slug=slug,
            name=name,
            title=title,
            description=description,
            domain=domain,
            access=access,
            license=license,
            countries_json=json.dumps(sorted(set(countries))),
            taxa_json=json.dumps(sorted(set(taxa))),
            genus_json=json.dumps(sorted(set(genera))),
            family_json=json.dumps(sorted(set(families))),
            is_verified_african=is_verified_african,
            owner_type=owner_type,
            owner_id=owner_id,
            samples_count=samples_count,
            benefit_sharing=benefit_sharing,
            created_at=created,
            updated_at=updated,
        )
        session.add(record)

        # 2. Re-index in FTS5
        await session.execute(
            text("DELETE FROM datasets_fts WHERE repo_id = :repo_id"),
            {"repo_id": repo_id},
        )

        await session.execute(
            text("""
                INSERT INTO datasets_fts(
                    repo_id, slug, title, description, countries, genus, family, benefit_sharing
                ) VALUES (
                    :repo_id, :slug, :title, :description, :countries, :genus, :family,
                    :benefit_sharing
                )
            """),
            {
                "repo_id": repo_id,
                "slug": slug,
                "title": title,
                "description": description or "",
                "countries": " ".join(sorted(set(countries))),
                "genus": " ".join(sorted(set(genera))),
                "family": " ".join(sorted(set(families))),
                "benefit_sharing": benefit_sharing or "",
            },
        )
        logger.info(
            "Indexed dataset in FTS5",
            extra={"repo_id": repo_id, "slug": slug, "title": title},
        )

    async def index_samples(
        self,
        session: AsyncSession,
        repo_id: str,
        sample_docs: list[dict[str, Any]],
    ) -> None:
        """Atomic upsert of sample full-text search rows."""
        await session.execute(
            text("DELETE FROM samples_fts WHERE repo_id = :repo_id"),
            {"repo_id": repo_id},
        )

        for s in sample_docs:
            await session.execute(
                text("""
                    INSERT INTO samples_fts(
                        sample_id_str, repo_id, sample_id, admin1, host, isolation_source,
                        genus, family, country
                    ) VALUES (
                        :sample_id_str, :repo_id, :sample_id, :admin1, :host, :isolation_source,
                        :genus, :family, :country
                    )
                """),
                {
                    "sample_id_str": str(s.get("id")),
                    "repo_id": repo_id,
                    "sample_id": str(s.get("sample_id", "")),
                    "admin1": str(s.get("admin1") or ""),
                    "host": str(s.get("host") or ""),
                    "isolation_source": str(s.get("isolation_source") or ""),
                    "genus": str(s.get("genus") or ""),
                    "family": str(s.get("family") or ""),
                    "country": str(s.get("country") or ""),
                },
            )

        logger.info(
            "Indexed samples in FTS5",
            extra={"repo_id": repo_id, "sample_count": len(sample_docs)},
        )

    async def delete_repo_samples(self, session: AsyncSession, repo_id: str) -> None:
        """Remove sample search entries for a repository."""
        await session.execute(
            text("DELETE FROM samples_fts WHERE repo_id = :repo_id"),
            {"repo_id": repo_id},
        )

    async def search_datasets(
        self,
        session: AsyncSession,
        query: str = "",
        domain: str | None = None,
        country: str | None = None,
        taxon_id: int | None = None,
        genus: str | None = None,
        family: str | None = None,
        access: str | None = None,
        is_verified_african: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        user: UserModel | None = None,
    ) -> dict[str, Any]:
        """Search datasets using FTS5 BM25 ranking, structured filters, and access controls."""
        fts_query = sanitize_fts_query(query)
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        where_clauses: list[str] = []

        # Access control
        if not user:
            where_clauses.append("r.access IN ('public', 'gated')")
        else:
            params["user_id"] = user.id
            where_clauses.append("""
                (
                    r.access IN ('public', 'gated')
                    OR r.owner_id = :user_id
                    OR (
                        r.owner_type = 'org'
                        AND r.owner_id IN (
                            SELECT org_id FROM memberships WHERE user_id = :user_id
                        )
                    )
                )
            """)

        # Structured Filters
        if domain:
            params["domain"] = domain
            where_clauses.append("r.domain = :domain")
        if access:
            params["access"] = access
            where_clauses.append("r.access = :access")
        if is_verified_african is not None:
            params["is_verified_african"] = 1 if is_verified_african else 0
            where_clauses.append("r.is_verified_african = :is_verified_african")
        if country:
            params["country"] = country.upper()
            where_clauses.append(
                "EXISTS (SELECT 1 FROM json_each(r.countries_json) WHERE UPPER(value) = :country)"
            )
        if taxon_id:
            params["taxon_id"] = taxon_id
            where_clauses.append(
                "EXISTS (SELECT 1 FROM json_each(r.taxa_json) WHERE value = :taxon_id)"
            )
        if genus:
            params["genus"] = genus.lower()
            where_clauses.append(
                "EXISTS (SELECT 1 FROM json_each(r.genus_json) WHERE LOWER(value) = :genus)"
            )
        if family:
            params["family"] = family.lower()
            where_clauses.append(
                "EXISTS (SELECT 1 FROM json_each(r.family_json) WHERE LOWER(value) = :family)"
            )

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        if fts_query:
            params["fts_query"] = fts_query
            sql = f"""
                SELECT
                    r.repo_id, r.slug, r.name, r.title, r.description, r.domain,
                    r.access, r.license, r.countries_json, r.taxa_json, r.genus_json,
                    r.family_json, r.is_verified_african, r.owner_type, r.owner_id,
                    r.samples_count, r.benefit_sharing, r.created_at, r.updated_at,
                    bm25(datasets_fts, 10.0, 5.0, 1.0, 3.0, 3.0, 2.0, 1.0) AS rank
                FROM dataset_search_records r
                JOIN datasets_fts ON datasets_fts.repo_id = r.repo_id
                WHERE datasets_fts MATCH :fts_query AND {where_sql}
                ORDER BY rank ASC, r.created_at DESC
                LIMIT :limit OFFSET :offset;
            """
            count_sql = f"""
                SELECT COUNT(*)
                FROM dataset_search_records r
                JOIN datasets_fts ON datasets_fts.repo_id = r.repo_id
                WHERE datasets_fts MATCH :fts_query AND {where_sql};
            """
        else:
            sql = f"""
                SELECT
                    r.repo_id, r.slug, r.name, r.title, r.description, r.domain,
                    r.access, r.license, r.countries_json, r.taxa_json, r.genus_json,
                    r.family_json, r.is_verified_african, r.owner_type, r.owner_id,
                    r.samples_count, r.benefit_sharing, r.created_at, r.updated_at,
                    0.0 AS rank
                FROM dataset_search_records r
                WHERE {where_sql}
                ORDER BY r.created_at DESC
                LIMIT :limit OFFSET :offset;
            """
            count_sql = f"""
                SELECT COUNT(*)
                FROM dataset_search_records r
                WHERE {where_sql};
            """

        result = await session.execute(text(sql), params)
        rows = result.fetchall()

        count_res = await session.execute(text(count_sql), params)
        total_count = count_res.scalar() or 0

        hits: list[dict[str, Any]] = []
        for row in rows:
            hits.append(
                {
                    "id": row[0],
                    "slug": row[1],
                    "name": row[2],
                    "title": row[3],
                    "description": row[4],
                    "domain": row[5],
                    "access": row[6],
                    "license": row[7],
                    "countries": json.loads(row[8]),
                    "taxon_ids": json.loads(row[9]),
                    "genus": json.loads(row[10]),
                    "family": json.loads(row[11]),
                    "is_verified_african": bool(row[12]),
                    "owner_type": row[13],
                    "owner_id": row[14],
                    "samples_count": row[15],
                    "benefit_sharing": row[16],
                    "created_at": (
                        row[17].isoformat() if hasattr(row[17], "isoformat") else str(row[17])
                    ),
                    "updated_at": (
                        row[18].isoformat() if hasattr(row[18], "isoformat") else str(row[18])
                    ),
                }
            )

        # Facet distributions
        facets = await self._compute_dataset_facets(session, fts_query, where_sql, params)

        logger.info(
            "Executed FTS5 dataset search",
            extra={
                "search_query": query,
                "hits_count": len(hits),
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
            },
        )

        return {
            "hits": hits,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "facet_distribution": facets,
        }

    async def _compute_dataset_facets(
        self,
        session: AsyncSession,
        fts_query: str,
        where_sql: str,
        base_params: dict[str, Any],
    ) -> dict[str, dict[str, int]]:
        """Compute faceted distribution counts for domain, countries, genus, family, access."""
        join_clause = (
            "JOIN datasets_fts ON datasets_fts.repo_id = r.repo_id" if fts_query else ""
        )
        fts_filter = "datasets_fts MATCH :fts_query AND " if fts_query else ""
        full_where = f"{fts_filter}{where_sql}"

        facet_queries = {
            "domain": f"""
                SELECT r.domain, COUNT(*)
                FROM dataset_search_records r {join_clause}
                WHERE {full_where}
                GROUP BY r.domain;
            """,
            "access": f"""
                SELECT r.access, COUNT(*)
                FROM dataset_search_records r {join_clause}
                WHERE {full_where}
                GROUP BY r.access;
            """,
            "is_verified_african": f"""
                SELECT r.is_verified_african, COUNT(*)
                FROM dataset_search_records r {join_clause}
                WHERE {full_where}
                GROUP BY r.is_verified_african;
            """,
            "countries": f"""
                SELECT j.value, COUNT(DISTINCT r.repo_id)
                FROM dataset_search_records r {join_clause},
                     json_each(r.countries_json) j
                WHERE {full_where}
                GROUP BY j.value;
            """,
            "genus": f"""
                SELECT j.value, COUNT(DISTINCT r.repo_id)
                FROM dataset_search_records r {join_clause},
                     json_each(r.genus_json) j
                WHERE {full_where}
                GROUP BY j.value;
            """,
            "family": f"""
                SELECT j.value, COUNT(DISTINCT r.repo_id)
                FROM dataset_search_records r {join_clause},
                     json_each(r.family_json) j
                WHERE {full_where}
                GROUP BY j.value;
            """,
        }

        distribution: dict[str, dict[str, int]] = {}
        for facet_name, q_sql in facet_queries.items():
            try:
                res = await session.execute(text(q_sql), base_params)
                facet_dict: dict[str, int] = {}
                for row in res.fetchall():
                    val = str(row[0])
                    if val.lower() == "true" or val == "1":
                        val = "true"
                    elif val.lower() == "false" or val == "0":
                        val = "false"
                    facet_dict[val] = int(row[1])
                distribution[facet_name] = facet_dict
            except Exception:
                distribution[facet_name] = {}

        return distribution

    async def search_samples(
        self,
        session: AsyncSession,
        query: str = "",
        country: str | None = None,
        taxon_id: int | None = None,
        genus: str | None = None,
        host: str | None = None,
        isolation_source: str | None = None,
        repo_slug: str | None = None,
        limit: int = 50,
        offset: int = 0,
        user: UserModel | None = None,
    ) -> dict[str, Any]:
        """Search samples with FTS5, metadata filters, and access controls."""
        fts_query = sanitize_fts_query(query)
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        where_clauses: list[str] = []

        # Access check through parent repository
        if not user:
            where_clauses.append("r.access IN ('public', 'gated')")
        else:
            params["user_id"] = user.id
            where_clauses.append("""
                (
                    r.access IN ('public', 'gated')
                    OR r.owner_id = :user_id
                    OR (
                        r.owner_type = 'org'
                        AND r.owner_id IN (
                            SELECT org_id FROM memberships WHERE user_id = :user_id
                        )
                    )
                )
            """)

        if country:
            params["country"] = country.upper()
            where_clauses.append("s.country = :country")
        if taxon_id:
            params["taxon_id"] = taxon_id
            where_clauses.append("s.taxon_id = :taxon_id")
        if genus:
            params["genus"] = genus.lower()
            where_clauses.append("LOWER(s.genus) = :genus")
        if host:
            params["host"] = host.lower()
            where_clauses.append("LOWER(s.host) = :host")
        if isolation_source:
            params["isolation_source"] = isolation_source.lower()
            where_clauses.append("LOWER(s.isolation_source) = :isolation_source")
        if repo_slug:
            params["repo_slug"] = repo_slug
            where_clauses.append("r.slug = :repo_slug")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        if fts_query:
            params["fts_query"] = fts_query
            sql = f"""
                SELECT
                    s.id, s.sample_id, s.repo_id, r.slug AS repo_slug, r.domain,
                    r.access, s.country, s.taxon_id, s.genus, s.family,
                    s.collection_date, s.admin1, s.host, s.isolation_source,
                    s.lat, s.lon, bm25(samples_fts) AS rank
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id
                JOIN samples_fts ON samples_fts.sample_id_str = s.id
                WHERE samples_fts MATCH :fts_query AND {where_sql}
                ORDER BY rank ASC, s.created_at DESC
                LIMIT :limit OFFSET :offset;
            """
            count_sql = f"""
                SELECT COUNT(*)
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id
                JOIN samples_fts ON samples_fts.sample_id_str = s.id
                WHERE samples_fts MATCH :fts_query AND {where_sql};
            """
        else:
            sql = f"""
                SELECT
                    s.id, s.sample_id, s.repo_id, r.slug AS repo_slug, r.domain,
                    r.access, s.country, s.taxon_id, s.genus, s.family,
                    s.collection_date, s.admin1, s.host, s.isolation_source,
                    s.lat, s.lon, 0.0 AS rank
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id
                WHERE {where_sql}
                ORDER BY s.created_at DESC
                LIMIT :limit OFFSET :offset;
            """
            count_sql = f"""
                SELECT COUNT(*)
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id
                WHERE {where_sql};
            """

        result = await session.execute(text(sql), params)
        rows = result.fetchall()

        count_res = await session.execute(text(count_sql), params)
        total_count = count_res.scalar() or 0

        hits: list[dict[str, Any]] = []
        for row in rows:
            lat_val = row[14]
            lon_val = row[15]
            geo_dict = (
                {"lat": lat_val, "lng": lon_val}
                if (lat_val is not None and lon_val is not None)
                else None
            )
            hits.append(
                {
                    "id": row[0],
                    "sample_id": row[1],
                    "repo_id": row[2],
                    "repo_slug": row[3],
                    "domain": row[4],
                    "access": row[5],
                    "country": row[6],
                    "taxon_id": row[7],
                    "genus": row[8],
                    "family": row[9],
                    "collection_date": row[10],
                    "admin1": row[11],
                    "host": row[12],
                    "isolation_source": row[13],
                    "_geo": geo_dict,
                }
            )

        # Facets
        facets = await self._compute_sample_facets(session, fts_query, where_sql, params)

        logger.info(
            "Executed FTS5 sample search",
            extra={
                "search_query": query,
                "hits_count": len(hits),
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
            },
        )

        return {
            "hits": hits,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "facet_distribution": facets,
        }

    async def _compute_sample_facets(
        self,
        session: AsyncSession,
        fts_query: str,
        where_sql: str,
        base_params: dict[str, Any],
    ) -> dict[str, dict[str, int]]:
        """Compute sample facet distributions."""
        join_clause = (
            "JOIN samples_fts ON samples_fts.sample_id_str = s.id" if fts_query else ""
        )
        fts_filter = "samples_fts MATCH :fts_query AND " if fts_query else ""
        full_where = f"{fts_filter}{where_sql}"

        facet_queries = {
            "country": f"""
                SELECT s.country, COUNT(*)
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id {join_clause}
                WHERE {full_where}
                GROUP BY s.country;
            """,
            "genus": f"""
                SELECT s.genus, COUNT(*)
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id {join_clause}
                WHERE {full_where} AND s.genus IS NOT NULL
                GROUP BY s.genus;
            """,
            "family": f"""
                SELECT s.family, COUNT(*)
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id {join_clause}
                WHERE {full_where} AND s.family IS NOT NULL
                GROUP BY s.family;
            """,
            "host": f"""
                SELECT s.host, COUNT(*)
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id {join_clause}
                WHERE {full_where} AND s.host IS NOT NULL
                GROUP BY s.host;
            """,
            "isolation_source": f"""
                SELECT s.isolation_source, COUNT(*)
                FROM samples s
                JOIN repositories r ON r.id = s.repo_id {join_clause}
                WHERE {full_where} AND s.isolation_source IS NOT NULL
                GROUP BY s.isolation_source;
            """,
        }

        distribution: dict[str, dict[str, int]] = {}
        for facet_name, q_sql in facet_queries.items():
            try:
                res = await session.execute(text(q_sql), base_params)
                distribution[facet_name] = {
                    str(row[0]): int(row[1]) for row in res.fetchall() if row[0]
                }
            except Exception:
                distribution[facet_name] = {}

        return distribution


search_service = SqliteSearchService()

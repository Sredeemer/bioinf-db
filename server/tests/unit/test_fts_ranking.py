"""Unit tests for SQLite FTS5 BM25 word-based ranking, column weights, and stemming."""

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ubuntubio.db.models import Base, RepositoryModel
from ubuntubio.indexer.fts import init_fts_tables, search_service
from ubuntubio.indexer.taxonomy import TaxonomyService
from ubuntubio.indexer.worker import index_repository

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an isolated SQLite database session with FTS5 initialized."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await init_fts_tables(conn)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_bm25_title_weight_ranks_higher_than_description(
    db_session: AsyncSession,
) -> None:
    """Verify BM25 ranking prioritizes title matches over description matches."""
    tax_service = TaxonomyService()

    # Repo A: keyword 'lassa' only in description
    repo_a = RepositoryModel(
        slug="lab/nigeria-pathogen-survey",
        name="nigeria-pathogen-survey",
        owner_type="user",
        owner_id="u1",
        domain="viral",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add(repo_a)
    await db_session.commit()

    readme_a = """---
title: West Africa Broad Pathogen Survey
domain: viral
license: cc-by-4.0
access: public
countries: [NG]
---
# Broad pathogen surveillance including background notes on Lassa virus transmission.
"""
    await index_repository(
        session=db_session,
        repo_slug=repo_a.slug,
        readme_override=readme_a,
        tax_service=tax_service,
    )

    # Repo B: keyword 'lassa' in the title
    repo_b = RepositoryModel(
        slug="lab/lassa-outbreak-genomics",
        name="lassa-outbreak-genomics",
        owner_type="user",
        owner_id="u1",
        domain="viral",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add(repo_b)
    await db_session.commit()

    readme_b = """---
title: Lassa Mammarenavirus Outbreak Genomics in Edo State
domain: viral
license: cc-by-4.0
access: public
countries: [NG]
---
# Targeted sequencing of viral genomes during seasonal outbreak.
"""
    await index_repository(
        session=db_session,
        repo_slug=repo_b.slug,
        readme_override=readme_b,
        tax_service=tax_service,
    )

    # Search for 'lassa'
    res = await search_service.search_datasets(session=db_session, query="lassa")
    hits = res["hits"]
    assert len(hits) == 2

    # Repo B (title match) MUST rank ahead of Repo A (description match)
    assert hits[0]["slug"] == "lab/lassa-outbreak-genomics"
    assert hits[1]["slug"] == "lab/nigeria-pathogen-survey"


@pytest.mark.asyncio
async def test_porter_stemming_matches_variations(db_session: AsyncSession) -> None:
    """Verify Porter stemmer matches word forms (pathogen -> pathogenic, sequencing -> sequence)."""
    tax_service = TaxonomyService()

    repo = RepositoryModel(
        slug="lab/bacterial-pathogens",
        name="bacterial-pathogens",
        owner_type="user",
        owner_id="u1",
        domain="bacteria",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add(repo)
    await db_session.commit()

    readme = """---
title: Genomic Sequencing of Pathogenic Bacteria
domain: bacteria
license: cc-by-4.0
access: public
countries: [GH]
---
# High throughput sequences of clinical isolates.
"""
    await index_repository(
        session=db_session,
        repo_slug=repo.slug,
        readme_override=readme,
        tax_service=tax_service,
    )

    # Search for root 'pathogen' should match 'pathogenic'
    res1 = await search_service.search_datasets(session=db_session, query="pathogen")
    assert len(res1["hits"]) == 1
    assert res1["hits"][0]["slug"] == "lab/bacterial-pathogens"

    # Search for 'sequence' should match 'sequencing'
    res2 = await search_service.search_datasets(session=db_session, query="sequence")
    assert len(res2["hits"]) == 1


@pytest.mark.asyncio
async def test_prefix_matching_and_facets(db_session: AsyncSession) -> None:
    """Verify prefix matching (e.g. 'ebol*') and facet distribution calculation."""
    tax_service = TaxonomyService()

    repo = RepositoryModel(
        slug="acegid/ebola-filovirus",
        name="ebola-filovirus",
        owner_type="org",
        owner_id="org1",
        domain="viral",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add(repo)
    await db_session.commit()

    readme = """---
title: Ebolavirus Surveillance in Sierra Leone
domain: viral
license: cc-by-4.0
access: public
countries: [SL]
taxon_ids: [186538]
---
# Full length viral genomes.
"""
    await index_repository(
        session=db_session,
        repo_slug=repo.slug,
        readme_override=readme,
        tax_service=tax_service,
    )

    # Prefix match 'ebol' matches Ebolavirus
    res = await search_service.search_datasets(session=db_session, query="ebol")
    assert len(res["hits"]) == 1
    assert res["hits"][0]["slug"] == "acegid/ebola-filovirus"

    # Check facet distribution
    facets = res["facet_distribution"]
    assert facets["domain"]["viral"] == 1
    assert facets["countries"]["SL"] == 1
    assert facets["access"]["public"] == 1

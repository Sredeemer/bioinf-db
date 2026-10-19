"""Unit tests for Indexer Worker, Taxonomy Enrichment, and Search API (M3).

Covers:
- T-SRCH-01: Indexer creates N sample rows from an N-row TSV.
- T-SRCH-02: New commit replaces old sample rows (no duplicates).
- T-SRCH-03: Facet counts and distributions are correct.
- T-SRCH-04: Private dataset hidden from anonymous search.
- T-SRCH-05: Gated datasets show metadata only.
- T-SRCH-06: Reindex reproduces identical results.
- T-SRCH-07: Taxonomy enrichment enables genus-level query ("Klebsiella").
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ubuntubio.auth.pat import create_personal_access_token
from ubuntubio.db.models import (
    Base,
    RepositoryModel,
    SampleModel,
    UserModel,
)
from ubuntubio.db.session import get_db_session
from ubuntubio.indexer.fts import init_fts_tables
from ubuntubio.indexer.meili import DATASETS_INDEX, SAMPLES_INDEX, MeiliService
from ubuntubio.indexer.reindex import reindex_all_repositories
from ubuntubio.indexer.taxonomy import TaxonomyService
from ubuntubio.indexer.worker import index_repository
from ubuntubio.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an isolated SQLite database session."""
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


@pytest.fixture
def mock_meili() -> MeiliService:
    """Provide a mock Meilisearch service for fast, deterministic unit testing."""
    service = MeiliService(mock_mode=True)
    return service


@pytest.fixture
def test_tax_service() -> TaxonomyService:
    """Provide a clean TaxonomyService instance."""
    return TaxonomyService()


async def test_tsrch_01_indexer_creates_n_sample_rows(
    db_session: AsyncSession,
    mock_meili: MeiliService,
    test_tax_service: TaxonomyService,
) -> None:
    """T-SRCH-01: Indexer creates N sample rows from an N-row TSV."""
    # 1. Create Repository
    repo = RepositoryModel(
        slug="pasteur/klebsiella-surveillance",
        name="klebsiella-surveillance",
        owner_type="org",
        owner_id="org-pasteur",
        domain="bacteria",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add(repo)
    await db_session.commit()

    readme_content = """---
title: Klebsiella AMR Surveillance in Dakar
domain: bacteria
license: cc-by-4.0
access: public
countries: [SN]
taxon_ids: [573]
---
# Dataset Description
"""
    # 3-row samples TSV
    samples_tsv = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\tlat\tlon\tadmin1\thost\tisolation_source\n"
        "SMP_001\t573\tSN\t2023-01-15\t14.6928\t-17.4467\tDakar\tHomo sapiens\tblood\n"
        "SMP_002\t573\tSN\t2023-02-10\t14.6928\t-17.4467\tDakar\tHomo sapiens\tsputum\n"
        "SMP_003\t573\tSN\t2023-03-05\t14.6928\t-17.4467\tDakar\tHomo sapiens\turine\n"
    )

    stats = await index_repository(
        session=db_session,
        repo_slug=repo.slug,
        readme_override=readme_content,
        samples_tsv_override=samples_tsv,
        meili=mock_meili,
        tax_service=test_tax_service,
    )

    assert stats["samples_count"] == 3
    assert stats["countries"] == ["SN"]
    assert 573 in stats["taxa"]
    assert "Klebsiella" in stats["genera"]

    # Verify rows in PostgreSQL
    stmt = select(SampleModel).where(SampleModel.repo_id == repo.id)
    res = await db_session.execute(stmt)
    rows = res.scalars().all()
    assert len(rows) == 3
    assert {r.sample_id for r in rows} == {"SMP_001", "SMP_002", "SMP_003"}
    assert all(r.genus == "Klebsiella" for r in rows)
    assert all(r.family == "Enterobacteriaceae" for r in rows)


async def test_tsrch_02_new_commit_replaces_old_sample_rows(
    db_session: AsyncSession,
    mock_meili: MeiliService,
    test_tax_service: TaxonomyService,
) -> None:
    """T-SRCH-02: A new commit replaces old sample rows (no duplicates)."""
    repo = RepositoryModel(
        slug="kemer/cholera-kenya",
        name="cholera-kenya",
        owner_type="org",
        owner_id="org-kemer",
        domain="bacteria",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add(repo)
    await db_session.commit()

    initial_tsv = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\n"
        "CHOL_01\t666\tKE\t2023-01-01\n"
        "CHOL_02\t666\tKE\t2023-01-02\n"
    )
    await index_repository(
        session=db_session,
        repo_slug=repo.slug,
        samples_tsv_override=initial_tsv,
        meili=mock_meili,
        tax_service=test_tax_service,
    )

    stmt = select(SampleModel).where(SampleModel.repo_id == repo.id)
    res = await db_session.execute(stmt)
    assert len(res.scalars().all()) == 2

    # New commit updates TSV to 4 new samples (CHOL_03, CHOL_04, CHOL_05, CHOL_06)
    new_tsv = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\n"
        "CHOL_03\t666\tKE\t2023-02-01\n"
        "CHOL_04\t666\tKE\t2023-02-02\n"
        "CHOL_05\t666\tKE\t2023-02-03\n"
        "CHOL_06\t666\tKE\t2023-02-04\n"
    )
    stats2 = await index_repository(
        session=db_session,
        repo_slug=repo.slug,
        samples_tsv_override=new_tsv,
        meili=mock_meili,
        tax_service=test_tax_service,
    )

    assert stats2["samples_count"] == 4

    # Verify old rows are completely replaced without duplicates
    res2 = await db_session.execute(stmt)
    rows2 = res2.scalars().all()
    assert len(rows2) == 4
    sample_ids = {r.sample_id for r in rows2}
    assert sample_ids == {"CHOL_03", "CHOL_04", "CHOL_05", "CHOL_06"}
    assert "CHOL_01" not in sample_ids


async def test_tsrch_03_meili_facet_counts_are_correct(
    db_session: AsyncSession,
    mock_meili: MeiliService,
    test_tax_service: TaxonomyService,
) -> None:
    """T-SRCH-03: Facet counts and distributions are correct."""
    # Index two repositories: one in Senegal (bacteria), one in Nigeria (virus)
    r1 = RepositoryModel(
        slug="pasteur/tb-senegal",
        name="tb-senegal",
        owner_type="org",
        owner_id="org-pasteur",
        domain="bacteria",
        access="public",
        license="cc-by-4.0",
    )
    r2 = RepositoryModel(
        slug="acegid/lassa-nigeria",
        name="lassa-nigeria",
        owner_type="org",
        owner_id="org-acegid",
        domain="virus",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add_all([r1, r2])
    await db_session.commit()

    tsv_tb = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\n"
        "TB_01\t1773\tSN\t2023-01-01\n"
        "TB_02\t1773\tSN\t2023-01-02\n"
    )
    tsv_lassa = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\n"
        "LASSA_01\t11620\tNG\t2023-01-01\n"
        "LASSA_02\t11620\tNG\t2023-01-02\n"
        "LASSA_03\t11620\tNG\t2023-01-03\n"
    )

    await index_repository(
        session=db_session,
        repo_slug=r1.slug,
        samples_tsv_override=tsv_tb,
        meili=mock_meili,
        tax_service=test_tax_service,
    )
    await index_repository(
        session=db_session,
        repo_slug=r2.slug,
        samples_tsv_override=tsv_lassa,
        meili=mock_meili,
        tax_service=test_tax_service,
    )

    # Search datasets facets
    res = await mock_meili.search(
        index_name=DATASETS_INDEX,
        query="",
        facets=["domain", "countries"],
    )
    facets = res.get("facetDistribution", {})
    assert facets["domain"]["bacteria"] == 1
    assert facets["domain"]["virus"] == 1
    assert facets["countries"]["SN"] == 1
    assert facets["countries"]["NG"] == 1

    # Search samples facets
    sample_res = await mock_meili.search(
        index_name=SAMPLES_INDEX,
        query="",
        facets=["country", "genus"],
    )
    s_facets = sample_res.get("facetDistribution", {})
    assert s_facets["country"]["SN"] == 2
    assert s_facets["country"]["NG"] == 3
    assert s_facets["genus"]["Mycobacterium"] == 2
    assert s_facets["genus"]["Mammarenavirus"] == 3


async def test_tsrch_04_private_dataset_hidden_from_anonymous_search(
    db_session: AsyncSession,
    mock_meili: MeiliService,
    test_tax_service: TaxonomyService,
) -> None:
    """T-SRCH-04: Private dataset is hidden from anonymous search, visible to authorized user."""
    # Create private dataset owned by user1
    user1 = UserModel(
        orcid_id="0000-0002-1825-0001",
        name="Private Researcher",
        email="researcher@lab.org",
    )
    user2 = UserModel(
        orcid_id="0000-0002-1825-0002",
        name="Other Researcher",
        email="other@lab.org",
    )
    db_session.add_all([user1, user2])
    await db_session.commit()

    priv_repo = RepositoryModel(
        slug=f"{user1.id}/confidential-pathogen",
        name="confidential-pathogen",
        owner_type="user",
        owner_id=user1.id,
        domain="bacteria",
        access="private",
        license="proprietary",
    )
    pub_repo = RepositoryModel(
        slug="open/public-study",
        name="public-study",
        owner_type="user",
        owner_id=user2.id,
        domain="bacteria",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add_all([priv_repo, pub_repo])
    await db_session.commit()

    # Index both
    await index_repository(
        session=db_session,
        repo_slug=priv_repo.slug,
        meili=mock_meili,
        tax_service=test_tax_service,
    )
    await index_repository(
        session=db_session,
        repo_slug=pub_repo.slug,
        meili=mock_meili,
        tax_service=test_tax_service,
    )

    # Wire FastAPI test client overriding get_db_session and meili
    app.dependency_overrides[get_db_session] = lambda: db_session

    from ubuntubio.api import search as search_module

    orig_meili = search_module.meili_service
    search_module.meili_service = mock_meili

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Anonymous search: must NOT return private dataset
            anon_resp = await client.get("/api/search")
            assert anon_resp.status_code == 200
            anon_data = anon_resp.json()
            anon_slugs = [hit["slug"] for hit in anon_data["hits"]]
            assert pub_repo.slug in anon_slugs
            assert priv_repo.slug not in anon_slugs

            # 2. Other user search: must NOT return private dataset
            user2_token, _ = await create_personal_access_token(db_session, user2.id, "u2_token")
            user2_resp = await client.get(
                "/api/search", headers={"Authorization": f"Bearer {user2_token}"}
            )
            assert user2_resp.status_code == 200
            user2_slugs = [hit["slug"] for hit in user2_resp.json()["hits"]]
            assert priv_repo.slug not in user2_slugs

            # 3. Owner user search: MUST return private dataset
            user1_token, _ = await create_personal_access_token(db_session, user1.id, "u1_token")
            owner_resp = await client.get(
                "/api/search", headers={"Authorization": f"Bearer {user1_token}"}
            )
            assert owner_resp.status_code == 200
            owner_slugs = [hit["slug"] for hit in owner_resp.json()["hits"]]
            assert priv_repo.slug in owner_slugs
            assert pub_repo.slug in owner_slugs
    finally:
        app.dependency_overrides.clear()
        search_module.meili_service = orig_meili


async def test_tsrch_05_gated_dataset_shows_metadata_only(
    db_session: AsyncSession,
    mock_meili: MeiliService,
    test_tax_service: TaxonomyService,
) -> None:
    """T-SRCH-05: Gated datasets show catalog metadata only in search."""
    gated_repo = RepositoryModel(
        slug="consortium/gated-amr-study",
        name="gated-amr-study",
        owner_type="org",
        owner_id="org-consortium",
        domain="bacteria",
        access="gated",
        license="cc-by-nc-4.0",
        description="Gated hospital AMR collection requiring DUA agreement.",
    )
    db_session.add(gated_repo)
    await db_session.commit()

    await index_repository(
        session=db_session,
        repo_slug=gated_repo.slug,
        meili=mock_meili,
        tax_service=test_tax_service,
    )

    app.dependency_overrides[get_db_session] = lambda: db_session
    from ubuntubio.api import search as search_module

    orig_meili = search_module.meili_service
    search_module.meili_service = mock_meili

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/search?access=gated")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["hits"]) == 1
            hit = data["hits"][0]
            assert hit["slug"] == "consortium/gated-amr-study"
            assert hit["access"] == "gated"
            assert hit["description"] is not None
    finally:
        app.dependency_overrides.clear()
        search_module.meili_service = orig_meili


async def test_tsrch_06_reindex_reproduces_identical_results(
    db_session: AsyncSession,
    mock_meili: MeiliService,
    test_tax_service: TaxonomyService,
) -> None:
    """T-SRCH-06: Reindex admin operation reproduces identical results."""
    repo = RepositoryModel(
        slug="nimr/cholera-lagos",
        name="cholera-lagos",
        owner_type="org",
        owner_id="org-nimr",
        domain="bacteria",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add(repo)
    await db_session.commit()

    tsv_data = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\n"
        "LAG_01\t666\tNG\t2023-01-01\n"
        "LAG_02\t666\tNG\t2023-01-02\n"
    )

    # Initial index
    await index_repository(
        session=db_session,
        repo_slug=repo.slug,
        samples_tsv_override=tsv_data,
        meili=mock_meili,
        tax_service=test_tax_service,
    )

    initial_search = await mock_meili.search(DATASETS_INDEX, query="cholera")
    assert initial_search["estimatedTotalHits"] == 1

    # Run complete reindex
    reindex_res = await reindex_all_repositories(session=db_session, meili=mock_meili)
    assert reindex_res["status"] == "completed"
    assert reindex_res["repositories_processed"] >= 1

    # Search again and verify identical result
    second_search = await mock_meili.search(DATASETS_INDEX, query="cholera")
    assert second_search["estimatedTotalHits"] == initial_search["estimatedTotalHits"]
    assert second_search["hits"][0]["slug"] == initial_search["hits"][0]["slug"]


async def test_tsrch_07_taxonomy_enrichment_genus_query(
    db_session: AsyncSession,
    mock_meili: MeiliService,
    test_tax_service: TaxonomyService,
) -> None:
    """T-SRCH-07: A 'Klebsiella' query matches genus-level facets and taxon."""
    repo = RepositoryModel(
        slug="pasteur/k-pneumo-dakar",
        name="k-pneumo-dakar",
        owner_type="org",
        owner_id="org-pasteur",
        domain="bacteria",
        access="public",
        license="cc-by-4.0",
    )
    db_session.add(repo)
    await db_session.commit()

    tsv_data = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\n"
        "KP_01\t573\tSN\t2023-01-01\n"
        "KP_02\t573\tSN\t2023-01-02\n"
    )

    await index_repository(
        session=db_session,
        repo_slug=repo.slug,
        samples_tsv_override=tsv_data,
        meili=mock_meili,
        tax_service=test_tax_service,
    )

    # Verify genus enrichment
    enriched = test_tax_service.enrich_taxon(573)
    assert enriched["genus"] == "Klebsiella"
    assert enriched["family"] == "Enterobacteriaceae"
    assert test_tax_service.matches_genus(573, "Klebsiella")

    # Search for "Klebsiella"
    res = await mock_meili.search(
        index_name=DATASETS_INDEX,
        query="Klebsiella",
        facets=["genus"],
    )
    assert res["estimatedTotalHits"] == 1
    assert res["hits"][0]["slug"] == "pasteur/k-pneumo-dakar"
    assert "Klebsiella" in res["hits"][0]["genus"]
    assert res["facetDistribution"]["genus"]["Klebsiella"] == 1

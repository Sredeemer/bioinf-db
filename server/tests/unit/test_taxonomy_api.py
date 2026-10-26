"""Unit tests for NCBI Taxonomy enrichment, suggestion API, and local taxdump integration."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ubuntubio.indexer.taxonomy import TaxonomyService
from ubuntubio.main import app


@pytest.fixture
def mock_taxdump_dir(tmp_path: Path) -> Path:
    """Create a temporary mock NCBI taxdump directory with nodes.dmp and names.dmp."""
    nodes_file = tmp_path / "nodes.dmp"
    names_file = tmp_path / "names.dmp"

    # Format: tax_id \t|\t parent_tax_id \t|\t rank \t|
    nodes_content = (
        "1\t|\t1\t|\tno rank\t|\n"
        "2\t|\t1\t|\tsuperkingdom\t|\n"
        "12345\t|\t2\t|\tgenus\t|\n"
        "99999\t|\t12345\t|\tspecies\t|\n"
    )
    nodes_file.write_text(nodes_content, encoding="utf-8")

    # Format: tax_id \t|\t name_txt \t|\t unique_name \t|\t name_class \t|
    names_content = (
        "1\t|\troot\t|\t\t|\tscientific name\t|\n"
        "2\t|\tBacteria\t|\t\t|\tscientific name\t|\n"
        "12345\t|\tAfrobacter\t|\t\t|\tscientific name\t|\n"
        "99999\t|\tAfrobacter saharae\t|\t\t|\tscientific name\t|\n"
        "99999\t|\tSahara microbe\t|\t\t|\tcommon name\t|\n"
        "99999\t|\tAS-01 isolate\t|\t\t|\tsynonym\t|\n"
    )
    names_file.write_text(names_content, encoding="utf-8")

    return tmp_path


def test_taxonomy_service_load_taxdump(mock_taxdump_dir: Path) -> None:
    """Verify local taxdump parser populates taxa cache and synonyms."""
    service = TaxonomyService(taxdump_dir=mock_taxdump_dir)

    assert 99999 in service.taxa_cache
    info = service.taxa_cache[99999]
    assert info.scientific_name == "Afrobacter saharae"
    assert info.rank == "species"
    assert info.genus == "Afrobacter"

    # Check suggestion with mock taxdump
    res = service.suggest("sahara")
    assert len(res) >= 1
    assert res[0]["taxon_id"] == 99999
    assert res[0]["scientific_name"] == "Afrobacter saharae"


@pytest.mark.asyncio
async def test_api_taxonomy_suggest_defaults() -> None:
    """Verify default taxonomy suggestions return African priority organisms."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/taxonomy/suggest")
        assert resp.status_code == 200
        data = resp.json()

        assert "taxa" in data
        assert len(data["taxa"]) > 0
        tids = [t["taxon_id"] for t in data["taxa"]]

        # Default results must include priority African pathogens
        assert 10244 in tids  # Mpox
        assert 11620 in tids  # Lassa
        assert 666 in tids  # Cholera

        # 9606 (human) must not be in default suggestions
        assert 9606 not in tids


@pytest.mark.asyncio
async def test_api_taxonomy_suggest_by_name() -> None:
    """Verify searching by common or scientific name returns ranked matches."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/taxonomy/suggest?q=cholera")
        assert resp.status_code == 200
        data = resp.json()

        assert data["count"] >= 1
        top_match = data["taxa"][0]
        assert top_match["taxon_id"] == 666
        assert top_match["scientific_name"] == "Vibrio cholerae"
        assert top_match["is_prohibited"] is False


@pytest.mark.asyncio
async def test_api_taxonomy_suggest_by_id() -> None:
    """Verify numeric ID query resolves directly."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/taxonomy/suggest?q=562")
        assert resp.status_code == 200
        data = resp.json()

        assert data["count"] >= 1
        top_match = data["taxa"][0]
        assert top_match["taxon_id"] == 562
        assert "Escherichia coli" in top_match["scientific_name"]


@pytest.mark.asyncio
async def test_api_taxonomy_human_flagged_prohibited() -> None:
    """Verify querying human or 9606 returns taxon with is_prohibited=True."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/taxonomy/suggest?q=9606")
        assert resp.status_code == 200
        data = resp.json()

        assert data["count"] >= 1
        human_match = next(t for t in data["taxa"] if t["taxon_id"] == 9606)
        assert human_match["scientific_name"] == "Homo sapiens"
        assert human_match["is_prohibited"] is True


@pytest.mark.asyncio
async def test_api_taxonomy_get_by_id() -> None:
    """Verify fetching single taxon by ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/taxonomy/666")
        assert resp.status_code == 200
        data = resp.json()
        assert data["taxon_id"] == 666
        assert data["genus"] == "Vibrio"
        assert data["is_prohibited"] is False

        # 404 on invalid taxon ID
        resp_404 = await client.get("/api/taxonomy/999999999")
        assert resp_404.status_code == 404

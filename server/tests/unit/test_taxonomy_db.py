"""Unit tests for the embedded SQLite FTS5 NCBI taxonomy engine."""

from pathlib import Path

import pytest

from ubuntubio.indexer.taxonomy import TaxonomyService
from ubuntubio.indexer.taxonomy_db import TaxonomyDbEngine


@pytest.fixture
def mock_taxdump_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with minimal names.dmp and nodes.dmp."""
    names_content = (
        "666\t|\tVibrio cholerae\t|\t\t|\tscientific name\t|\n"
        "666\t|\tcholera vibrio\t|\t\t|\tcommon name\t|\n"
        "1773\t|\tMycobacterium tuberculosis\t|\t\t|\tscientific name\t|\n"
        "1773\t|\tKoch's bacillus\t|\t\t|\tsynonym\t|\n"
        "9606\t|\tHomo sapiens\t|\t\t|\tscientific name\t|\n"
        "9606\t|\thuman\t|\t\t|\tgenbank common name\t|\n"
        "5833\t|\tPlasmodium falciparum\t|\t\t|\tscientific name\t|\n"
        "5833\t|\tmalaria parasite\t|\t\t|\tcommon name\t|\n"
    )
    nodes_content = (
        "666\t|\t662\t|\tspecies\t|\t\t|\t\t|\n"
        "1773\t|\t1763\t|\tspecies\t|\t\t|\t\t|\n"
        "9606\t|\t9605\t|\tspecies\t|\t\t|\t\t|\n"
        "5833\t|\t5820\t|\tspecies\t|\t\t|\t\t|\n"
    )

    (tmp_path / "names.dmp").write_text(names_content, encoding="utf-8")
    (tmp_path / "nodes.dmp").write_text(nodes_content, encoding="utf-8")
    return tmp_path


def test_taxonomy_db_build_and_search(mock_taxdump_dir: Path, tmp_path: Path) -> None:
    """Test building SQLite FTS5 database from taxdump and executing queries."""
    db_file = tmp_path / "test_taxonomy.db"
    engine = TaxonomyDbEngine(db_path=db_file)

    assert not engine.exists()

    count = engine.build_from_dump(mock_taxdump_dir, target_db_path=db_file)
    assert count == 4
    assert engine.exists()

    # 1. Exact tax_id lookup
    rec = engine.get_by_tax_id(666)
    assert rec is not None
    assert rec["scientific_name"] == "Vibrio cholerae"
    assert rec["is_prohibited"] is False
    assert rec["rank"] == "species"

    # 2. Human prohibition invariant check
    human_rec = engine.get_by_tax_id(9606)
    assert human_rec is not None
    assert human_rec["is_prohibited"] is True
    assert "strictly prohibited" in human_rec["prohibition_reason"]

    # 3. Numeric search
    num_results = engine.search("666", limit=5)
    assert len(num_results) >= 1
    assert num_results[0]["tax_id"] == 666

    # 4. Scientific name prefix search
    vibrio_results = engine.search("Vibrio", limit=5)
    assert len(vibrio_results) >= 1
    assert vibrio_results[0]["scientific_name"] == "Vibrio cholerae"

    # 5. Synonym / Common name search
    malaria_results = engine.search("malaria", limit=5)
    assert len(malaria_results) >= 1
    assert malaria_results[0]["tax_id"] == 5833
    assert malaria_results[0]["scientific_name"] == "Plasmodium falciparum"

    # 6. Service integration test with custom engine
    service = TaxonomyService()
    # Temporarily monkeypatch global engine
    import ubuntubio.indexer.taxonomy as tax_module

    orig_engine = tax_module.taxonomy_db_engine
    try:
        tax_module.taxonomy_db_engine = engine
        suggestions = service.suggest("cholera", limit=5)
        assert len(suggestions) >= 1
        assert suggestions[0]["taxon_id"] == 666

        # Human search flags invariant
        human_sug = service.suggest("human", limit=5)
        assert any(s["taxon_id"] == 9606 and s["is_prohibited"] is True for s in human_sug)
    finally:
        tax_module.taxonomy_db_engine = orig_engine
        engine.close()

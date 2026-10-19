"""Tests for DomainConfigManager and AU country resolution."""

from ubuntubio_curation.config import DomainConfigManager


def test_au_country_validation() -> None:
    mgr = DomainConfigManager()
    assert mgr.is_valid_au_country("NG") is True
    assert mgr.is_valid_au_country("SN") is True
    assert mgr.is_valid_au_country("ZA") is True
    assert mgr.is_valid_au_country("KE") is True
    assert mgr.is_valid_au_country("US") is False
    assert mgr.is_valid_au_country("FR") is False
    assert mgr.is_valid_au_country("CN") is False


def test_country_string_normalization() -> None:
    mgr = DomainConfigManager()
    # Complex strings commonly found in ENA/NCBI
    assert mgr.resolve_country_to_iso("Senegal: Dakar") == "SN"
    assert mgr.resolve_country_to_iso("Nigeria: Lagos State") == "NG"
    assert mgr.resolve_country_to_iso("Kenya, Kisumu") == "KE"
    assert mgr.resolve_country_to_iso("South Africa") == "ZA"
    assert mgr.resolve_country_to_iso("Democratic Republic of the Congo") == "CD"
    assert mgr.resolve_country_to_iso("Côte d'Ivoire") == "CI"
    assert mgr.resolve_country_to_iso("France") is None
    assert mgr.resolve_country_to_iso("") is None


def test_get_taxa_for_domain() -> None:
    mgr = DomainConfigManager()
    viral_taxa = mgr.get_taxa_for_domain("viruses")
    assert len(viral_taxa) > 0
    taxon_ids = [t["taxon_id"] for t in viral_taxa]
    assert 11620 in taxon_ids  # Lassa
    assert 186538 in taxon_ids  # Ebola
    assert 9606 not in taxon_ids  # Human strictly absent

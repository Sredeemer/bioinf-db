"""Tests for HarvestWatermark and BadgeVerifier."""

from pathlib import Path

from ubuntubio_curation.badge import BadgeVerifier
from ubuntubio_curation.models import CuratedProjectManifest, NormalizedSample
from ubuntubio_curation.watermark import HarvestWatermark


def test_harvest_watermark_persistence(tmp_path: Path) -> None:
    state_file = tmp_path / "watermark.json"
    wm = HarvestWatermark(state_file=state_file)

    assert wm.is_study_harvested("PRJEB123") is False

    wm.record_harvested_study("PRJEB123", "lassa-prjeb123", 42)
    wm.save()

    # Reload from disk
    wm_reloaded = HarvestWatermark(state_file=state_file)
    assert wm_reloaded.is_study_harvested("PRJEB123") is True
    assert wm_reloaded.state["harvested_studies"]["PRJEB123"]["sample_count"] == 42


def test_badge_verifier_african_valid() -> None:
    verifier = BadgeVerifier()
    manifest = CuratedProjectManifest(
        repo_name="lassa-test",
        title="Lassa virus test",
        domain="viruses",
        countries=["NG", "SN"],
        taxon_ids=[11620],
        source_study="PRJEB123",
        samples=[
            NormalizedSample(
                sample_id="S1",
                taxon_id=11620,
                country="NG",
                collection_date="2024-01-01",
            )
        ],
    )
    result = verifier.assess_manifest(manifest)
    assert result["verified_african"] is True
    assert result["badge"] == "Verified African"
    assert len(result["issues"]) == 0


def test_badge_verifier_detects_prohibited_human_taxon() -> None:
    verifier = BadgeVerifier()
    manifest = CuratedProjectManifest(
        repo_name="invalid-human",
        title="Invalid human",
        domain="viruses",
        countries=["NG"],
        taxon_ids=[9606],  # Human Taxon
        source_study="PRJEB999",
        samples=[],
    )
    result = verifier.assess_manifest(manifest)
    assert result["verified_african"] is False
    assert any("Taxon ID 9606" in iss for iss in result["issues"])

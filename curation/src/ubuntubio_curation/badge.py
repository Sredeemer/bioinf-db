"""Provenance and "Verified African" badge assessment service."""

from typing import Any

from .config import DomainConfigManager
from .models import CuratedProjectManifest


class BadgeVerifier:
    """Evaluates whether a dataset repository meets the 'Verified African' standard."""

    def __init__(self, config_mgr: DomainConfigManager | None = None) -> None:
        self.config_mgr = config_mgr or DomainConfigManager()

    def assess_manifest(self, manifest: CuratedProjectManifest) -> dict[str, Any]:
        """Assess a curated manifest for the 'Verified African' badge."""
        issues: list[str] = []

        # 1. Non-human check
        if 9606 in manifest.taxon_ids:
            issues.append("Banned human Taxon ID 9606 detected in manifest taxon_ids")

        for sample in manifest.samples:
            if sample.taxon_id == 9606:
                issues.append(f"Sample {sample.sample_id} has prohibited human Taxon 9606")
                break

        # 2. AU country membership check
        if not manifest.countries:
            issues.append("Manifest contains no declared countries")

        invalid_countries = [
            c for c in manifest.countries if not self.config_mgr.is_valid_au_country(c)
        ]
        if invalid_countries:
            issues.append(f"Contains non-AU country codes: {invalid_countries}")

        # 3. Minimum sample count
        if not manifest.samples:
            issues.append("Manifest contains 0 samples")

        is_verified = len(issues) == 0

        return {
            "verified_african": is_verified,
            "badge": "Verified African" if is_verified else "Unverified",
            "country_codes": manifest.countries,
            "taxa": manifest.taxon_ids,
            "sample_count": len(manifest.samples),
            "issues": issues,
            "provenance_study": manifest.source_study,
        }

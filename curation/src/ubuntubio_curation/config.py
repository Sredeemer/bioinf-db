"""Domain configuration loader and African geographic normalizer."""

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "domains.yaml"


class DomainConfigManager:
    """Manages African taxonomy domains and AU country code resolution."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._raw_data: dict[str, Any] = self._load()
        self.au_countries: dict[str, str] = self._raw_data.get("au_countries", {})
        self.domains: dict[str, Any] = self._raw_data.get("domains", {})

        # Build reverse lookup map: lowercase name -> ISO-2
        self._name_to_iso: dict[str, str] = {}
        for iso, name in self.au_countries.items():
            self._name_to_iso[name.lower()] = iso
            self._name_to_iso[iso.lower()] = iso

        # Common aliases & ENA string variations
        self._name_to_iso.update(
            {
                "cote d'ivoire": "CI",
                "ivory coast": "CI",
                "drc": "CD",
                "dr congo": "CD",
                "congo, democratic republic of the": "CD",
                "congo-kinshasa": "CD",
                "congo, republic of the": "CG",
                "congo-brazzaville": "CG",
                "tanzania, united republic of": "TZ",
                "cape verde": "CV",
                "swaziland": "SZ",
            }
        )

    def _load(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}

    def is_valid_au_country(self, code: str) -> bool:
        """Check if an ISO-2 code is one of the 54 African Union member states."""
        return code.strip().upper() in self.au_countries

    def resolve_country_to_iso(self, raw_country: str) -> str | None:
        """Resolve arbitrary ENA/NCBI country strings to an ISO-2 AU country code.

        Examples:
            "Senegal: Dakar" -> "SN"
            "Nigeria" -> "NG"
            "KE" -> "KE"
            "France" -> None (Rejected - Non-AU)
        """
        if not raw_country:
            return None

        # Clean string, strip geographic sub-divisions like ": Dakar" or ", Lagos"
        clean = raw_country.split(":")[0].split(",")[0].strip().lower()

        if clean in self._name_to_iso:
            return self._name_to_iso[clean]

        # Check two-letter ISO direct match
        upper_code = raw_country.strip().upper()
        if len(upper_code) == 2 and upper_code in self.au_countries:
            return upper_code

        return None

    def get_taxa_for_domain(self, domain_key: str) -> list[dict[str, Any]]:
        """Return list of target taxa for a domain key (e.g., 'viruses')."""
        domain_info = self.domains.get(domain_key, {})
        taxa = domain_info.get("taxa", [])
        return taxa if isinstance(taxa, list) else []

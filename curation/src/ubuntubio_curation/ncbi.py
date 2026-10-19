"""NCBI Datasets API Harvester.

Fetches isolate assemblies, reference genomes, and metadata for African pathogen taxa.
"""

from typing import Any

import httpx

from .config import DomainConfigManager

NCBI_DATASETS_BASE = "https://api.ncbi.nlm.nih.gov/datasets/v2alpha"


class NcbiDatasetsClient:
    """Async client for the NCBI Datasets API."""

    def __init__(
        self,
        config_mgr: DomainConfigManager | None = None,
        http_client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
    ) -> None:
        self.config_mgr = config_mgr or DomainConfigManager()
        self.api_key = api_key
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        self.http_client = http_client or httpx.AsyncClient(timeout=30.0, headers=headers)

    async def get_genome_summary_by_taxon(
        self,
        tax_id: int,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch genome assembly summaries for a specific taxon ID."""
        if tax_id == 9606:
            raise ValueError("Human Taxon 9606 cannot be harvested")

        url = f"{NCBI_DATASETS_BASE}/genome/taxon/{tax_id}/dataset_report"
        params = {"page_size": page_size}

        response = await self.http_client.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        reports = data.get("reports", [])
        return reports if isinstance(reports, list) else []

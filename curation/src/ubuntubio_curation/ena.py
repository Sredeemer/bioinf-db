"""European Nucleotide Archive (ENA) Portal API Harvester.

Fetches public sequencing runs, sample metadata, and FASTQ download URLs
for targeted African pathogen taxa while enforcing the 54 AU country boundary.
"""

import httpx

from .config import DomainConfigManager
from .models import EnaRunRecord

ENA_SEARCH_URL = "https://www.ebi.ac.uk/ena/portal/api/search"

ENA_FIELDS = [
    "run_accession",
    "sample_accession",
    "study_accession",
    "experiment_accession",
    "tax_id",
    "scientific_name",
    "instrument_platform",
    "instrument_model",
    "fastq_ftp",
    "fastq_md5",
    "fastq_bytes",
    "country",
    "collection_date",
    "host",
    "isolation_source",
    "lat",
    "lon",
]


class EnaPortalClient:
    """Async client for the ENA Portal API."""

    def __init__(
        self,
        config_mgr: DomainConfigManager | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config_mgr = config_mgr or DomainConfigManager()
        self.http_client = http_client or httpx.AsyncClient(timeout=30.0)

    async def search_runs_by_taxon(
        self,
        tax_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EnaRunRecord]:
        """Search ENA for read_run records for a specific taxon ID."""
        # Never harvest human data
        if tax_id == 9606:
            raise ValueError("Human Taxon 9606 cannot be harvested")

        query = f"tax_tree({tax_id})"
        params: dict[str, str | int] = {
            "result": "read_run",
            "query": query,
            "fields": ",".join(ENA_FIELDS),
            "format": "json",
            "limit": limit,
            "offset": offset,
        }

        response = await self.http_client.get(ENA_SEARCH_URL, params=params)
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            return []

        results: list[EnaRunRecord] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            # Safe conversion of numeric fields
            lat_val = float(item["lat"]) if item.get("lat") else None
            lon_val = float(item["lon"]) if item.get("lon") else None
            tax_id_val = int(item.get("tax_id", tax_id))

            record = EnaRunRecord(
                run_accession=item.get("run_accession", ""),
                sample_accession=item.get("sample_accession", ""),
                study_accession=item.get("study_accession", ""),
                experiment_accession=item.get("experiment_accession", ""),
                tax_id=tax_id_val,
                scientific_name=item.get("scientific_name", ""),
                instrument_platform=item.get("instrument_platform", ""),
                instrument_model=item.get("instrument_model", ""),
                fastq_ftp=item.get("fastq_ftp", ""),
                fastq_md5=item.get("fastq_md5", ""),
                fastq_bytes=item.get("fastq_bytes", ""),
                country=item.get("country", ""),
                collection_date=item.get("collection_date", ""),
                host=item.get("host", ""),
                isolation_source=item.get("isolation_source", ""),
                lat=lat_val,
                lon=lon_val,
            )
            results.append(record)

        return results

    def filter_african_records(
        self, records: list[EnaRunRecord]
    ) -> tuple[list[EnaRunRecord], dict[str, str]]:
        """Filter records to those originating from the 54 AU member states.

        Returns:
            Tuple of (valid_records, map_of_run_to_iso_country)
        """
        valid_records: list[EnaRunRecord] = []
        run_to_iso: dict[str, str] = {}

        for rec in records:
            iso = self.config_mgr.resolve_country_to_iso(rec.country)
            if iso and self.config_mgr.is_valid_au_country(iso):
                valid_records.append(rec)
                run_to_iso[rec.run_accession] = iso

        return valid_records, run_to_iso

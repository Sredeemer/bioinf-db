"""Tests for EnaPortalClient with mocked HTTP responses."""

import pytest
import respx

from ubuntubio_curation.ena import ENA_SEARCH_URL, EnaPortalClient


@pytest.mark.asyncio
async def test_ena_client_blocks_human_harvest() -> None:
    client = EnaPortalClient()
    with pytest.raises(ValueError, match="Human Taxon 9606 cannot be harvested"):
        await client.search_runs_by_taxon(tax_id=9606)


@pytest.mark.asyncio
@respx.mock
async def test_ena_client_search_and_filter_african_runs() -> None:
    mock_payload = [
        {
            "run_accession": "ERR1001",
            "sample_accession": "SAMEA101",
            "study_accession": "PRJEB5000",
            "tax_id": "11620",
            "scientific_name": "Lassa mammarenavirus",
            "country": "Senegal: Dakar",
            "collection_date": "2024-03-10",
            "fastq_ftp": "ftp.sra.ebi.ac.uk/vol1/ERR1001.fastq.gz",
            "fastq_md5": "abc1234567890",
            "fastq_bytes": "104857600",
            "lat": "14.6928",
            "lon": "-17.4467",
        },
        {
            "run_accession": "ERR1002",
            "sample_accession": "SAMEA102",
            "study_accession": "PRJEB5000",
            "tax_id": "11620",
            "scientific_name": "Lassa mammarenavirus",
            "country": "Germany: Berlin",  # Non-African sample to be filtered
            "collection_date": "2024-03-11",
        },
    ]

    respx.get(ENA_SEARCH_URL).respond(status_code=200, json=mock_payload)

    client = EnaPortalClient()
    runs = await client.search_runs_by_taxon(tax_id=11620, limit=10)
    assert len(runs) == 2

    # Filter against 54 AU countries
    african_runs, run_to_iso = client.filter_african_records(runs)
    assert len(african_runs) == 1
    assert african_runs[0].run_accession == "ERR1001"
    assert run_to_iso["ERR1001"] == "SN"
    assert "ERR1002" not in run_to_iso

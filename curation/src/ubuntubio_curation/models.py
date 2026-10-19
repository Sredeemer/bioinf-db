"""Pydantic data models for ENA/NCBI harvesting and MIxS sample normalization."""

from pydantic import BaseModel, Field, field_validator


class EnaRunRecord(BaseModel):
    """Raw read_run record returned from ENA Portal API."""

    run_accession: str
    sample_accession: str
    study_accession: str
    experiment_accession: str = ""
    tax_id: int
    scientific_name: str
    instrument_platform: str = ""
    instrument_model: str = ""
    fastq_ftp: str = ""
    fastq_md5: str = ""
    fastq_bytes: str = ""
    country: str = ""
    collection_date: str = ""
    host: str = ""
    isolation_source: str = ""
    lat: float | None = None
    lon: float | None = None


class NormalizedSample(BaseModel):
    """Normalized sample row meeting UbuntuBio MIxS requirements."""

    sample_id: str
    taxon_id: int
    country: str
    collection_date: str
    lat: float | None = None
    lon: float | None = None
    admin1: str = ""
    host: str = "Homo sapiens"
    isolation_source: str = "clinical isolate"
    bio_sample_accession: str = ""
    sequencing_platform: str = ""

    @field_validator("taxon_id")
    @classmethod
    def validate_non_human(cls, v: int) -> int:
        if v == 9606:
            raise ValueError("Human Taxon 9606 is strictly prohibited in UbuntuBio v1")
        return v

    @field_validator("country")
    @classmethod
    def validate_country_len(cls, v: str) -> str:
        clean = v.strip().upper()
        if len(clean) != 2:
            raise ValueError(f"Country code must be ISO-3166-1 alpha-2, got: {v}")
        return clean


class RemoteFileEntry(BaseModel):
    """Entry in remote_files.tsv for external FASTQ reads."""

    path: str
    url: str
    size: int
    md5: str
    sha256: str = ""


class CuratedProjectManifest(BaseModel):
    """Metadata for a curated UbuntuBio repository."""

    repo_name: str
    title: str
    domain: str
    license: str = "cc-by-4.0"
    access: str = "public"
    countries: list[str]
    taxon_ids: list[int]
    data_types: list[str] = Field(default_factory=lambda: ["reads"])
    source_study: str
    publication_doi: str | None = None
    benefit_sharing: str = (
        "Compiled under the Nagoya Protocol on Access and Benefit Sharing. "
        "Commercial and derivative use requires provenance attribution."
    )
    samples: list[NormalizedSample]
    remote_files: list[RemoteFileEntry] = Field(default_factory=list)

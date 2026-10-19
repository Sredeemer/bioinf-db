"""Pydantic validation schemas for UbuntuBio repository metadata."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ubuntubio.validator.constants import (
    AFRICA_LAT_MAX,
    AFRICA_LAT_MIN,
    AFRICA_LON_MAX,
    AFRICA_LON_MIN,
    AU_COUNTRY_CODES,
    PROHIBITED_TAXA,
    VALID_DOMAINS,
)

# ISO-8601 Date regex: YYYY, YYYY-MM, or YYYY-MM-DD
DATE_REGEX = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
MD5_REGEX = re.compile(r"^[a-fA-F0-9]{32}$")


class DatasetCard(BaseModel):
    """YAML front-matter specification for repository README.md."""

    model_config = ConfigDict(strict=True, frozen=True, extra="allow")

    title: str = Field(..., min_length=5, max_length=120)
    domain: str
    access: Literal["public", "gated", "private"]
    license: str = Field(..., min_length=2, max_length=64)
    countries: list[str] = Field(..., min_length=1)
    taxon_ids: list[int] = Field(..., min_length=1)
    data_types: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)
    benefit_sharing: str | None = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        domain_normalized = v.strip().lower()
        if domain_normalized not in VALID_DOMAINS:
            raise ValueError(f"Invalid domain '{v}'. Permitted domains: {sorted(VALID_DOMAINS)}")
        return domain_normalized

    @field_validator("countries")
    @classmethod
    def validate_countries(cls, v: list[str]) -> list[str]:
        cleaned = [c.strip().upper() for c in v]
        invalid = [c for c in cleaned if c not in AU_COUNTRY_CODES]
        if invalid:
            raise ValueError(
                f"Country codes must belong to the 54 African Union member states. "
                f"Invalid codes found: {invalid}"
            )
        return cleaned

    @field_validator("taxon_ids")
    @classmethod
    def validate_taxa(cls, v: list[int]) -> list[int]:
        for taxon in v:
            if taxon in PROHIBITED_TAXA:
                raise ValueError(
                    f"Human genomic data (Taxon ID {taxon}) is strictly prohibited in UbuntuBio v1."
                )
            if taxon <= 0:
                raise ValueError(f"Taxon ID must be a positive integer, got {taxon}")
        return v

    @model_validator(mode="after")
    def validate_license_and_access(self) -> DatasetCard:
        lic_clean = self.license.strip().lower()
        if lic_clean in ("custom", "custom-dua", "dua") and self.access == "public":
            raise ValueError(
                "Datasets with custom Data Use Agreements (DUA) must use 'gated' access."
            )
        return self


class SampleRecord(BaseModel):
    """Single sample record from samples.tsv."""

    model_config = ConfigDict(strict=True, frozen=True)

    sample_id: str = Field(..., min_length=1, max_length=128)
    taxon_id: int
    country: str
    collection_date: str
    lat: float | None = None
    lon: float | None = None
    admin1: str | None = None
    host: str
    isolation_source: str
    extra_fields: dict[str, str] = Field(default_factory=dict)

    @field_validator("country")
    @classmethod
    def validate_sample_country(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in AU_COUNTRY_CODES:
            raise ValueError(f"Sample country '{v}' is not an African Union member state.")
        return clean

    @field_validator("taxon_id")
    @classmethod
    def validate_sample_taxon(cls, v: int) -> int:
        if v in PROHIBITED_TAXA:
            raise ValueError(
                f"Sample taxon {v} (Homo sapiens) is prohibited in UbuntuBio v1. "
                f"Set pathogen taxon in 'taxon_id' and 'Homo sapiens' in 'host'."
            )
        if v <= 0:
            raise ValueError(f"Taxon ID must be positive, got {v}")
        return v

    @field_validator("collection_date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        clean = v.strip()
        if not DATE_REGEX.match(clean):
            raise ValueError(
                f"Invalid collection_date '{v}'. Must be ISO-8601 (YYYY, YYYY-MM, or YYYY-MM-DD)."
            )
        return clean

    @model_validator(mode="after")
    def validate_geolocation(self) -> SampleRecord:
        # If lat/lon are supplied, check bounding box
        if self.lat is not None and self.lon is not None:
            if not (AFRICA_LAT_MIN <= self.lat <= AFRICA_LAT_MAX):
                raise ValueError(
                    f"Latitude {self.lat} is outside the African geographical boundary "
                    f"[{AFRICA_LAT_MIN}, {AFRICA_LAT_MAX}]."
                )
            if not (AFRICA_LON_MIN <= self.lon <= AFRICA_LON_MAX):
                raise ValueError(
                    f"Longitude {self.lon} is outside the African geographical boundary "
                    f"[{AFRICA_LON_MIN}, {AFRICA_LON_MAX}]."
                )
        elif self.lat is not None or self.lon is not None:
            raise ValueError("Both lat and lon must be provided together, or both omitted.")
        return self


class RemoteFileRecord(BaseModel):
    """Record representing a remote external file in remote_files.tsv."""

    model_config = ConfigDict(strict=True, frozen=True)

    filename: str = Field(..., min_length=1)
    url: str
    md5: str
    size_bytes: int

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        clean = v.strip()
        if not (
            clean.startswith("https://")
            or clean.startswith("ftp://")
            or clean.startswith("http://")
        ):
            raise ValueError(f"URL must start with https:// or ftp://. Got: {v}")
        return clean

    @field_validator("md5")
    @classmethod
    def validate_md5(cls, v: str) -> str:
        clean = v.strip().lower()
        if not MD5_REGEX.match(clean):
            raise ValueError(f"Invalid MD5 hash '{v}'. Expected 32-character hexadecimal string.")
        return clean

    @field_validator("size_bytes")
    @classmethod
    def validate_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"size_bytes must be a positive integer, got {v}")
        return v


class ValidationIssue(BaseModel):
    """An individual warning or error identified during validation."""

    model_config = ConfigDict(strict=True, frozen=True)

    file: str
    line: int | None = None
    column: str | None = None
    message: str
    severity: Literal["error", "warning"] = "error"


class ValidationResult(BaseModel):
    """Aggregated validation output for a repository revision."""

    model_config = ConfigDict(strict=True, frozen=True)

    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)
    dataset_card: DatasetCard | None = None
    sample_count: int = 0
    remote_file_count: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

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
    VALID_FILE_TYPES,
    VALID_PLATFORMS,
    VALID_SELECTIONS,
    VALID_SOURCES,
    VALID_STRATEGIES,
)

# ISO-8601 Date regex: YYYY, YYYY-MM, or YYYY-MM-DD
DATE_REGEX = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")
MD5_REGEX = re.compile(r"^[a-fA-F0-9]{32}$")


class SequencingLibraryRecord(BaseModel):
    """Record describing an individual sequenced library and its data files."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    library_id: str = Field(..., min_length=1, max_length=64)
    sample_name: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=5, max_length=200)
    file_type: str
    filenames: list[str] = Field(..., min_length=1)

    @field_validator("file_type")
    @classmethod
    def validate_file_type(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in VALID_FILE_TYPES:
            raise ValueError(
                f"Invalid file_type '{v}'. Permitted types: {sorted(VALID_FILE_TYPES)}"
            )
        return clean

    @field_validator("filenames")
    @classmethod
    def validate_filenames(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Library must specify at least one filename.")
        cleaned: list[str] = []
        for fn in v:
            fn_clean = fn.strip()
            if not fn_clean:
                raise ValueError("Filename cannot be empty.")
            if fn_clean.startswith("/") or ".." in fn_clean.split("/"):
                raise ValueError(
                    f"Path traversal or absolute paths not permitted in filename: '{fn}'"
                )
            cleaned.append(fn_clean)
        if len(cleaned) != len(set(cleaned)):
            raise ValueError(f"Duplicate filenames found in library: {cleaned}")
        return cleaned


class SequencingExperiment(BaseModel):
    """Sequencing experiment and platform metadata in README.md."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    platform: str
    instrument_model: str = Field(..., min_length=1, max_length=120)
    library_strategy: str
    library_source: str
    library_selection: str
    library_layout: Literal["paired", "single"]
    nominal_length: int | None = None
    demultiplexed: bool = True
    design_description: str | None = None
    libraries: list[SequencingLibraryRecord] = Field(default_factory=list)

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in VALID_PLATFORMS:
            raise ValueError(
                f"Invalid platform '{v}'. Permitted platforms: {sorted(VALID_PLATFORMS)}"
            )
        return clean

    @field_validator("library_strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in VALID_STRATEGIES:
            raise ValueError(
                f"Invalid library_strategy '{v}'. Permitted strategies: {sorted(VALID_STRATEGIES)}"
            )
        return clean

    @field_validator("library_source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in VALID_SOURCES:
            raise ValueError(
                f"Invalid library_source '{v}'. Permitted sources: {sorted(VALID_SOURCES)}"
            )
        return clean

    @field_validator("library_selection")
    @classmethod
    def validate_selection(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in VALID_SELECTIONS:
            raise ValueError(
                f"Invalid library_selection '{v}'. Permitted selections: {sorted(VALID_SELECTIONS)}"
            )
        return clean

    @model_validator(mode="after")
    def validate_layout_and_libraries(self) -> SequencingExperiment:
        if self.library_layout == "paired":
            if self.nominal_length is None or self.nominal_length <= 0:
                raise ValueError(
                    "nominal_length must be a positive integer when library_layout is 'paired'."
                )
            for lib in self.libraries:
                if len(lib.filenames) != 2:
                    raise ValueError(
                        f"Library '{lib.library_id}' has layout 'paired' but specifies "
                        f"{len(lib.filenames)} filenames. Exactly 2 filenames are required "
                        f"for paired-end sequencing."
                    )
        elif self.library_layout == "single":
            for lib in self.libraries:
                if len(lib.filenames) != 1:
                    raise ValueError(
                        f"Library '{lib.library_id}' has layout 'single' but specifies "
                        f"{len(lib.filenames)} filenames. Exactly 1 filename is required "
                        f"for single-end sequencing."
                    )

        lib_ids = [lib.library_id for lib in self.libraries]
        if len(lib_ids) != len(set(lib_ids)):
            raise ValueError(f"Duplicate library_id values found: {lib_ids}")

        return self


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
    sequencing: SequencingExperiment | None = None

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
    library_count: int = 0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

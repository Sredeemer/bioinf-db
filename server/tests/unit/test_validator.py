"""Unit and property-based test suite for UbuntuBio validator (T-VAL-01 to T-VAL-10)."""

from hypothesis import given
from hypothesis import strategies as st

from ubuntubio.validator import (
    AU_COUNTRY_CODES,
    SampleRecord,
    parse_dataset_card,
    parse_remote_files_tsv,
    parse_samples_tsv,
    validate_repository,
)

VALID_CARD_YAML = """---
title: Klebsiella pneumoniae isolates from Lagos clinical surveillance
domain: bacteria
access: public
license: cc-by-4.0
countries: [NG]
taxon_ids: [573]
data_types: [assembly, reads]
source:
  ena_project: PRJEB12345
---
# Dataset Description
This is a high quality AMR surveillance dataset.
"""

SAMPLE_HEADER = (
    "sample_id\ttaxon_id\tcountry\tcollection_date\tlat\tlon\tadmin1\thost\tisolation_source\n"
)
VALID_SAMPLES_TSV = (
    SAMPLE_HEADER
    + "SAMN001\t573\tNG\t2023-05-14\t6.5244\t3.3792\tLagos\tHomo sapiens\tblood\n"
    + "SAMN002\t573\tNG\t2023-06-20\t6.4500\t3.4000\tLagos\tHomo sapiens\tsputum\n"
)

VALID_REMOTE_FILES_TSV = (
    "filename\turl\tmd5\tsize_bytes\n"
    "reads/ERR123_1.fastq.gz\t"
    "https://ftp.sra.ebi.ac.uk/vol1/fastq/ERR123_1.fastq.gz\t"
    "d41d8cd98f00b204e9800998ecf8427e\t245892104\n"
)


def test_t_val_01_valid_repository_passes() -> None:
    """T-VAL-01: Valid card, samples.tsv, and remote_files.tsv passes validation."""
    result = validate_repository(
        readme_content=VALID_CARD_YAML,
        samples_tsv_content=VALID_SAMPLES_TSV,
        remote_files_content=VALID_REMOTE_FILES_TSV,
    )
    assert result.is_valid is True
    assert len(result.errors) == 0
    assert result.sample_count == 2
    assert result.remote_file_count == 1
    assert result.dataset_card is not None
    assert result.dataset_card.title.startswith("Klebsiella pneumoniae")


def test_t_val_02_non_au_country_rejected() -> None:
    """T-VAL-02: Non-AU country code (FR) is rejected."""
    bad_yaml = VALID_CARD_YAML.replace("countries: [NG]", "countries: [FR]")
    card, issues = parse_dataset_card(bad_yaml)
    assert card is None
    assert any("54 African Union member states" in i.message for i in issues)


def test_t_val_03_human_taxon_rejected() -> None:
    """T-VAL-03: Taxon ID 9606 (Homo sapiens) in card or sample is rejected."""
    bad_yaml = VALID_CARD_YAML.replace("taxon_ids: [573]", "taxon_ids: [9606]")
    card, issues = parse_dataset_card(bad_yaml)
    assert card is None
    assert any("Taxon ID 9606" in i.message for i in issues)


def test_t_val_04_missing_required_column_rejected() -> None:
    """T-VAL-04: Missing required column 'collection_date' in samples.tsv is rejected."""
    bad_tsv = (
        "sample_id\ttaxon_id\tcountry\tlat\tlon\tadmin1\thost\tisolation_source\n"
        "SAMN01\t573\tNG\t6.5\t3.3\tLagos\tHuman\tblood\n"
    )
    records, issues = parse_samples_tsv(bad_tsv)
    assert len(records) == 0
    assert any(
        "missing mandatory columns" in i.message and "collection_date" in i.message for i in issues
    )


def test_t_val_05_invalid_date_format_rejected() -> None:
    """T-VAL-05: Non-ISO date (2023-13-01 or bad month) is rejected."""
    bad_tsv = VALID_SAMPLES_TSV.replace("2023-05-14", "2023-13-01")
    _records, issues = parse_samples_tsv(bad_tsv)
    assert any("Invalid collection_date" in i.message for i in issues)


def test_t_val_06_coordinates_outside_africa_rejected() -> None:
    """T-VAL-06: Coordinates outside Africa bounding box are rejected."""
    # Paris coordinates: Lat 48.8566, Lon 2.3522 (Latitude > 38.0)
    bad_tsv = VALID_SAMPLES_TSV.replace("6.5244\t3.3792", "48.8566\t2.3522")
    _records, issues = parse_samples_tsv(bad_tsv)
    assert any("outside the African geographical boundary" in i.message for i in issues)


def test_t_val_07_sample_country_mismatch_with_card_rejected() -> None:
    """T-VAL-07: Sample country (KE) not declared in card countries [NG] is rejected."""
    bad_tsv = VALID_SAMPLES_TSV.replace("NG\t2023-05-14", "KE\t2023-05-14")
    card, _ = parse_dataset_card(VALID_CARD_YAML)
    assert card is not None
    _records, issues = parse_samples_tsv(bad_tsv, card=card)
    assert any("not listed in README.md countries" in i.message for i in issues)


def test_t_val_08_custom_dua_with_public_access_rejected() -> None:
    """T-VAL-08: license 'custom-dua' with 'access: public' must be rejected."""
    bad_yaml = VALID_CARD_YAML.replace("license: cc-by-4.0", "license: custom-dua")
    card, issues = parse_dataset_card(bad_yaml)
    assert card is None
    assert any("must use 'gated' access" in i.message for i in issues)


def test_t_val_09_remote_files_invalid_md5_or_url_rejected() -> None:
    """T-VAL-09: remote_files.tsv with invalid MD5 or non-HTTP/FTP url is rejected."""
    # Bad MD5 length
    bad_md5 = VALID_REMOTE_FILES_TSV.replace("d41d8cd98f00b204e9800998ecf8427e", "short_md5")
    _records, issues = parse_remote_files_tsv(bad_md5)
    assert any("Invalid MD5 hash" in i.message for i in issues)

    # Bad protocol
    bad_proto = VALID_REMOTE_FILES_TSV.replace("https://", "s3://")
    _records2, issues2 = parse_remote_files_tsv(bad_proto)
    assert any("URL must start with https:// or ftp://" in i.message for i in issues2)


@given(
    st.text(min_size=1, max_size=50),
    st.integers(min_value=1, max_value=100000),
    st.sampled_from(sorted(AU_COUNTRY_CODES)),
    st.sampled_from(["2020", "2021-06", "2022-12-31"]),
    st.floats(min_value=-30.0, max_value=30.0),
    st.floats(min_value=-15.0, max_value=45.0),
)
def test_t_val_10_sample_record_fuzzing_valid_inputs(
    sample_id: str,
    taxon_id: int,
    country: str,
    date_str: str,
    lat: float,
    lon: float,
) -> None:
    """T-VAL-10: Property-based fuzzing of valid sample records always constructs safely."""
    if taxon_id == 9606:
        return
    rec = SampleRecord(
        sample_id=sample_id,
        taxon_id=taxon_id,
        country=country,
        collection_date=date_str,
        lat=lat,
        lon=lon,
        admin1="Region",
        host="Cattle",
        isolation_source="Nasal swab",
    )
    assert rec.country == country
    assert rec.taxon_id == taxon_id

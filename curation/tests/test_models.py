"""Tests for curation Pydantic models."""

import pytest
from pydantic import ValidationError

from ubuntubio_curation.models import NormalizedSample


def test_normalized_sample_valid() -> None:
    sample = NormalizedSample(
        sample_id="SAMN123456",
        taxon_id=11620,
        country="SN",
        collection_date="2024-05-12",
        lat=14.7167,
        lon=-17.4677,
        host="Homo sapiens",
        isolation_source="blood serum",
    )
    assert sample.taxon_id == 11620
    assert sample.country == "SN"


def test_normalized_sample_prohibits_human_taxon_9606() -> None:
    with pytest.raises(ValidationError, match="Human Taxon 9606 is strictly prohibited"):
        NormalizedSample(
            sample_id="SAMN999999",
            taxon_id=9606,
            country="NG",
            collection_date="2024-01-01",
        )


def test_normalized_sample_requires_iso2_country() -> None:
    with pytest.raises(ValidationError, match="must be ISO-3166-1 alpha-2"):
        NormalizedSample(
            sample_id="SAMN888888",
            taxon_id=11620,
            country="SEN",
            collection_date="2024-01-01",
        )

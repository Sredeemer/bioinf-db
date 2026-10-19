"""Tests for RepoBuilder."""

from pathlib import Path

from ubuntubio_curation.builder import RepoBuilder
from ubuntubio_curation.models import EnaRunRecord


def test_builder_groups_and_writes_repository(tmp_path: Path) -> None:
    builder = RepoBuilder()

    runs = [
        EnaRunRecord(
            run_accession="ERR2001",
            sample_accession="SAMEA201",
            study_accession="PRJEB9900",
            tax_id=11620,
            scientific_name="Lassa mammarenavirus",
            country="Nigeria: Edo",
            collection_date="2024-04-01",
            fastq_ftp="ftp.sra.ebi.ac.uk/vol1/ERR2001_1.fastq.gz;ftp.sra.ebi.ac.uk/vol1/ERR2001_2.fastq.gz",
            fastq_md5="md5one;md5two",
            fastq_bytes="50000;50000",
        ),
        EnaRunRecord(
            run_accession="ERR2002",
            sample_accession="SAMEA202",
            study_accession="PRJEB9900",
            tax_id=11620,
            scientific_name="Lassa mammarenavirus",
            country="Nigeria: Ondo",
            collection_date="2024-04-02",
        ),
    ]
    run_to_iso = {"ERR2001": "NG", "ERR2002": "NG"}

    manifests = builder.group_runs_by_study(runs, run_to_iso, domain="viruses")
    assert len(manifests) == 1
    manifest = manifests[0]

    assert manifest.source_study == "PRJEB9900"
    assert manifest.countries == ["NG"]
    assert manifest.taxon_ids == [11620]
    assert len(manifest.samples) == 2
    assert len(manifest.remote_files) == 2

    # Write to disk
    repo_dir = builder.write_repository_to_disk(manifest, tmp_path)
    assert (repo_dir / "README.md").exists()
    assert (repo_dir / "samples.tsv").exists()
    assert (repo_dir / "remote_files.tsv").exists()

    # Verify content
    readme_content = (repo_dir / "README.md").read_text(encoding="utf-8")
    assert "ena_project: PRJEB9900" in readme_content
    assert "countries:\n- NG" in readme_content

    samples_content = (repo_dir / "samples.tsv").read_text(encoding="utf-8")
    lines = samples_content.strip().split("\n")
    assert len(lines) == 3  # header + 2 samples
    assert "SAMEA201\t11620\tNG" in lines[1]

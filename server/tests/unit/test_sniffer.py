"""Unit tests for server-side sequence format sniffer and biological quality screening."""

from __future__ import annotations

import gzip
from pathlib import Path

from ubuntubio.validator.constants import BAM_MAGIC
from ubuntubio.validator.sniffer import (
    SequenceSniffResult,
    sniff_magic_bytes,
    sniff_sequence_file,
)


def test_server_sniff_magic_bytes(tmp_path: Path) -> None:
    """Test identifying magic bytes across gzip, raw fastq, raw fasta, and bam."""
    fq_path = tmp_path / "sample.fastq"
    fq_path.write_text("@read_1\nACGT\n+\nIIII\n", encoding="utf-8")
    fmt, comp, _ = sniff_magic_bytes(fq_path)
    assert fmt == "FASTQ"
    assert comp == "RAW"

    gz_path = tmp_path / "sample.fastq.gz"
    with gzip.open(gz_path, "wt", encoding="utf-8") as f:
        f.write("@read_1\nACGT\n+\nIIII\n")
    fmt_gz, comp_gz, _ = sniff_magic_bytes(gz_path)
    assert fmt_gz == "GZIP"
    assert comp_gz == "GZIP"

    bam_path = tmp_path / "sample.bam"
    bam_path.write_bytes(BAM_MAGIC + b"\x00\x00")
    fmt_bam, comp_bam, _ = sniff_magic_bytes(bam_path)
    assert fmt_bam == "BAM"
    assert comp_bam == "NONE"


def test_server_sniff_valid_raw_fastq(tmp_path: Path) -> None:
    """Test sniffing a valid raw FASTQ with Sanger Phred+33 scores."""
    fq = tmp_path / "reads.fastq"
    content = (
        "@ERR001.1 instrument_run_1/1\n"
        "GCATGCATGCATGCAT\n"
        "+\n"
        "IIIIIIIIIIIIIIII\n"
        "@ERR001.2 instrument_run_1/2\n"
        "GGGGCCCCAAAATTTT\n"
        "+\n"
        "JJJJJJJJJJJJJJJJ\n"
    )
    fq.write_text(content, encoding="utf-8")

    result: SequenceSniffResult = sniff_sequence_file(fq)
    assert result.format == "FASTQ"
    assert result.compression == "RAW"
    assert result.is_valid is True
    assert result.reads_sampled == 2
    assert result.mean_read_length == 16.0
    assert result.gc_percent == 50.0
    assert result.phred_encoding == "Phred+33"
    assert len(result.errors) == 0


def test_server_sniff_fastq_length_mismatch(tmp_path: Path) -> None:
    """Test flagging FASTQ record where sequence length does not match quality length."""
    fq = tmp_path / "corrupt.fastq"
    content = (
        "@bad_read_1\n"
        "ACGTACGTACGT\n"  # 12 bp
        "+\n"
        "IIII\n"  # 4 chars -> mismatch
    )
    fq.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fq)
    assert result.is_valid is False
    assert len(result.errors) > 0
    assert any("length mismatch" in e.message for e in result.errors)


def test_server_sniff_fastq_legacy_phred64_warning(tmp_path: Path) -> None:
    """Test detecting legacy Illumina 1.3/1.5 Phred+64 quality encoding."""
    fq = tmp_path / "legacy.fastq"
    content = (
        "@legacy_read_1\n"
        "ACGTACGT\n"
        "+\n"
        "ghghghgh\n"  # ASCII 103, 104 -> Phred+64
        "@legacy_read_2\n"
        "ACGTACGT\n"
        "+\n"
        "BBBBBBBB\n"
    )
    fq.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fq)
    assert result.phred_encoding == "Phred+64"
    assert len(result.warnings) > 0
    assert any("Phred+64" in w.message for w in result.warnings)


def test_server_sniff_empty_sequence_file(tmp_path: Path) -> None:
    """Test sniffing a 0-byte sequence file emits a warning."""
    empty = tmp_path / "empty.fastq"
    empty.touch()

    result = sniff_sequence_file(empty)
    assert result.format == "EMPTY"
    assert result.is_valid is True
    assert any("empty (0 bytes)" in w.message for w in result.warnings)


def test_server_sniff_corrupted_gzip_file(tmp_path: Path) -> None:
    """Test sniffing a file with a corrupt gzip stream fails cleanly."""
    corrupt_gz = tmp_path / "corrupt.fastq.gz"
    corrupt_gz.write_bytes(b"\x1f\x8b\x08\x00garbage_data_that_cannot_decompress")

    result = sniff_sequence_file(corrupt_gz)
    assert result.is_valid is False
    assert any("Corrupted gzip" in e.message for e in result.errors)


def test_server_sniff_valid_fasta(tmp_path: Path) -> None:
    """Test sniffing a valid FASTA contig file."""
    fa = tmp_path / "contigs.fasta"
    content = (
        ">isolate_1 Cholera vibrio contig 1\n"
        "GCATGCATGCAT\n"
        "GCATGCATGCAT\n"
        ">isolate_2 Cholera vibrio contig 2\n"
        "ATATATATATAT\n"
    )
    fa.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fa)
    assert result.format == "FASTA"
    assert result.is_valid is True
    assert result.reads_sampled == 2
    assert result.mean_read_length == 18.0


def test_server_sniff_fasta_human_chromosome_rejection(tmp_path: Path) -> None:
    """Test detecting human chromosome headers in FASTA records."""
    fa = tmp_path / "human_contig.fasta"
    content = ">chr1 Homo sapiens chromosome 1, GRCh38.p14 primary assembly\nACGTACGTACGT\n"
    fa.write_text(content, encoding="utf-8")

    result = sniff_sequence_file(fa)
    assert result.human_markers_detected is True
    assert any("Human reference" in e.message for e in result.errors)

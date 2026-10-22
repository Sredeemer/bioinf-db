"""Parsing and holistic validation for UbuntuBio repository files."""

from __future__ import annotations

import csv
import io
import logging
from typing import Any

import yaml
from pydantic import ValidationError

from ubuntubio.validator.constants import (
    MANDATORY_REMOTE_FILE_COLUMNS,
    MANDATORY_SAMPLE_COLUMNS,
    SEQUENCE_FILE_EXTENSIONS,
)
from ubuntubio.validator.models import (
    DatasetCard,
    RemoteFileRecord,
    SampleRecord,
    ValidationIssue,
    ValidationResult,
)

logger = logging.getLogger("ubuntubio.validator")


def extract_frontmatter(readme_content: str) -> tuple[dict[str, Any] | None, list[ValidationIssue]]:
    """Extract YAML front-matter enclosed between leading '---' markers."""
    issues: list[ValidationIssue] = []
    lines = readme_content.splitlines()

    if not lines or lines[0].strip() != "---":
        issues.append(
            ValidationIssue(
                file="README.md",
                line=1,
                message="README.md must begin with a '---' YAML front-matter boundary.",
                severity="error",
            )
        )
        return None, issues

    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx == -1:
        issues.append(
            ValidationIssue(
                file="README.md",
                line=len(lines),
                message="Unterminated YAML front-matter in README.md; missing closing '---'.",
                severity="error",
            )
        )
        return None, issues

    yaml_text = "\n".join(lines[1:end_idx])
    try:
        parsed = yaml.safe_load(yaml_text)
        if not isinstance(parsed, dict):
            issues.append(
                ValidationIssue(
                    file="README.md",
                    line=1,
                    message="YAML front-matter must be a key-value mapping.",
                    severity="error",
                )
            )
            return None, issues
        return parsed, issues
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 2 if mark else 1
        issues.append(
            ValidationIssue(
                file="README.md",
                line=line,
                message=f"YAML syntax error: {exc}",
                severity="error",
            )
        )
        return None, issues


def parse_dataset_card(readme_content: str) -> tuple[DatasetCard | None, list[ValidationIssue]]:
    """Parse and validate dataset card front-matter from README.md."""
    raw_data, issues = extract_frontmatter(readme_content)
    if raw_data is None:
        return None, issues

    try:
        card = DatasetCard.model_validate(raw_data)
        return card, issues
    except ValidationError as err:
        for pydantic_err in err.errors():
            loc = ".".join(str(elem) for elem in pydantic_err["loc"])
            issues.append(
                ValidationIssue(
                    file="README.md",
                    column=loc,
                    message=f"Dataset card validation error in '{loc}': {pydantic_err['msg']}",
                    severity="error",
                )
            )
        return None, issues


def parse_samples_tsv(
    tsv_content: str,
    card: DatasetCard | None = None,
) -> tuple[list[SampleRecord], list[ValidationIssue]]:
    """Parse and validate samples.tsv with cross-field and card consistency checks."""
    issues: list[ValidationIssue] = []
    records: list[SampleRecord] = []

    reader = csv.reader(io.StringIO(tsv_content), delimiter="\t")
    header = next(reader, None)

    if header is None:
        issues.append(
            ValidationIssue(
                file="samples.tsv",
                line=1,
                message="samples.tsv is empty; header row required.",
                severity="error",
            )
        )
        return [], issues

    # Clean headers
    cleaned_header = [col.strip() for col in header]

    # Check for missing mandatory columns
    missing_cols = [col for col in MANDATORY_SAMPLE_COLUMNS if col not in cleaned_header]
    if missing_cols:
        issues.append(
            ValidationIssue(
                file="samples.tsv",
                line=1,
                message=f"samples.tsv is missing mandatory columns: {missing_cols}",
                severity="error",
            )
        )
        return [], issues

    col_indices = {col: idx for idx, col in enumerate(cleaned_header)}
    seen_sample_ids: set[str] = set()

    for line_num, row in enumerate(reader, start=2):
        if not row or all(not cell.strip() for cell in row):
            continue  # skip blank lines

        row_dict: dict[str, Any] = {}
        for col_name, idx in col_indices.items():
            val = row[idx].strip() if idx < len(row) else ""
            row_dict[col_name] = val

        sample_id = row_dict.get("sample_id", "")
        if sample_id in seen_sample_ids:
            issues.append(
                ValidationIssue(
                    file="samples.tsv",
                    line=line_num,
                    column="sample_id",
                    message=f"Duplicate sample_id '{sample_id}' found.",
                    severity="error",
                )
            )
        seen_sample_ids.add(sample_id)

        # Parse numeric types with safe conversions
        taxon_id_raw = row_dict.get("taxon_id", "")
        try:
            taxon_id_int = int(taxon_id_raw)
        except ValueError:
            issues.append(
                ValidationIssue(
                    file="samples.tsv",
                    line=line_num,
                    column="taxon_id",
                    message=f"Invalid taxon_id '{taxon_id_raw}', must be an integer.",
                    severity="error",
                )
            )
            continue

        lat_raw = row_dict.get("lat", "")
        lon_raw = row_dict.get("lon", "")
        lat_val: float | None = None
        lon_val: float | None = None

        if lat_raw:
            try:
                lat_val = float(lat_raw)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        file="samples.tsv",
                        line=line_num,
                        column="lat",
                        message=f"Invalid latitude '{lat_raw}', must be float.",
                        severity="error",
                    )
                )

        if lon_raw:
            try:
                lon_val = float(lon_raw)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        file="samples.tsv",
                        line=line_num,
                        column="lon",
                        message=f"Invalid longitude '{lon_raw}', must be float.",
                        severity="error",
                    )
                )

        sample_payload: dict[str, Any] = {
            "sample_id": sample_id,
            "taxon_id": taxon_id_int,
            "country": row_dict.get("country", ""),
            "collection_date": row_dict.get("collection_date", ""),
            "lat": lat_val,
            "lon": lon_val,
            "admin1": row_dict.get("admin1") or None,
            "host": row_dict.get("host", ""),
            "isolation_source": row_dict.get("isolation_source", ""),
            "extra_fields": {k: row_dict[k] for k in row_dict if k not in MANDATORY_SAMPLE_COLUMNS},
        }

        try:
            record = SampleRecord.model_validate(sample_payload)
            # Cross-reference with card countries if card is present
            if card is not None and record.country not in card.countries:
                issues.append(
                    ValidationIssue(
                        file="samples.tsv",
                        line=line_num,
                        column="country",
                        message=(
                            f"Sample country '{record.country}' not listed in "
                            f"README.md countries: {card.countries}"
                        ),
                        severity="error",
                    )
                )
            records.append(record)
        except ValidationError as err:
            for pydantic_err in err.errors():
                col = ".".join(str(e) for e in pydantic_err["loc"])
                issues.append(
                    ValidationIssue(
                        file="samples.tsv",
                        line=line_num,
                        column=col,
                        message=f"Sample validation error in '{col}': {pydantic_err['msg']}",
                        severity="error",
                    )
                )

    return records, issues


def parse_remote_files_tsv(
    tsv_content: str,
) -> tuple[list[RemoteFileRecord], list[ValidationIssue]]:
    """Parse and validate remote_files.tsv."""
    issues: list[ValidationIssue] = []
    records: list[RemoteFileRecord] = []

    reader = csv.reader(io.StringIO(tsv_content), delimiter="\t")
    header = next(reader, None)

    if header is None:
        return [], issues  # optional file may be empty

    cleaned_header = [col.strip() for col in header]
    missing_cols = [col for col in MANDATORY_REMOTE_FILE_COLUMNS if col not in cleaned_header]
    if missing_cols:
        issues.append(
            ValidationIssue(
                file="remote_files.tsv",
                line=1,
                message=f"remote_files.tsv is missing mandatory columns: {missing_cols}",
                severity="error",
            )
        )
        return [], issues

    col_indices = {col: idx for idx, col in enumerate(cleaned_header)}

    for line_num, row in enumerate(reader, start=2):
        if not row or all(not cell.strip() for cell in row):
            continue

        idx_fn = col_indices["filename"]
        idx_url = col_indices["url"]
        idx_md5 = col_indices["md5"]
        idx_sz = col_indices["size_bytes"]

        filename = row[idx_fn].strip() if idx_fn < len(row) else ""
        url = row[idx_url].strip() if idx_url < len(row) else ""
        md5 = row[idx_md5].strip() if idx_md5 < len(row) else ""
        size_raw = row[idx_sz].strip() if idx_sz < len(row) else ""

        try:
            size_int = int(size_raw)
        except ValueError:
            issues.append(
                ValidationIssue(
                    file="remote_files.tsv",
                    line=line_num,
                    column="size_bytes",
                    message=f"Invalid size_bytes '{size_raw}', must be integer.",
                    severity="error",
                )
            )
            continue

        try:
            rec = RemoteFileRecord.model_validate(
                {"filename": filename, "url": url, "md5": md5, "size_bytes": size_int}
            )
            records.append(rec)
        except ValidationError as err:
            for pydantic_err in err.errors():
                col = ".".join(str(e) for e in pydantic_err["loc"])
                issues.append(
                    ValidationIssue(
                        file="remote_files.tsv",
                        line=line_num,
                        column=col,
                        message=f"Remote file error in '{col}': {pydantic_err['msg']}",
                        severity="error",
                    )
                )

    return records, issues


def verify_file_parity(
    card: DatasetCard,
    samples: list[SampleRecord] | None,
    remote_files: list[RemoteFileRecord] | None,
    discovered_files: set[str] | list[str] | None,
) -> list[ValidationIssue]:
    """Perform two-way parity checks between declared libraries, samples, and files on disk.

    1. Checks that every library's sample_name matches a valid sample_id in samples.tsv.
    2. Checks that every declared library file exists either in discovered_files or
       remote_files.tsv.
    3. Checks that every sequence file (.fastq.gz, .fasta, .bam, etc.) discovered on disk
       is accounted for in declared libraries or remote_files.tsv (orphan check).
    """
    issues: list[ValidationIssue] = []

    if not card.sequencing or not card.sequencing.libraries:
        return issues

    known_sample_ids = {s.sample_id for s in samples} if samples else set()
    remote_filenames = {rf.filename for rf in remote_files} if remote_files else set()
    discovered_set = (
        set(discovered_files)
        if discovered_files is not None and not isinstance(discovered_files, set)
        else (discovered_files or set())
    )

    declared_sequence_files: set[str] = set()

    for lib in card.sequencing.libraries:
        # Check 1: Sample linkage
        if samples is not None and lib.sample_name not in known_sample_ids:
            issues.append(
                ValidationIssue(
                    file="README.md",
                    column=f"sequencing.libraries[{lib.library_id}].sample_name",
                    message=(
                        f"Library '{lib.library_id}' references sample_name '{lib.sample_name}', "
                        f"which does not exist in samples.tsv."
                    ),
                    severity="error",
                )
            )

        # Check 2: Missing declared files (if discovered_files is provided)
        for fn in lib.filenames:
            declared_sequence_files.add(fn)
            if (
                discovered_files is not None
                and fn not in discovered_set
                and fn not in remote_filenames
            ):
                issues.append(
                    ValidationIssue(
                        file="README.md",
                        column=f"sequencing.libraries[{lib.library_id}].filenames",
                        message=(
                            f"Missing declared sequence file '{fn}' for library "
                            f"'{lib.library_id}'. File was not found in repository or "
                            f"remote_files.tsv."
                        ),
                        severity="error",
                    )
                )

    # Check 3: Orphan check on discovered sequence files
    if discovered_files is not None:
        for path in discovered_set:
            path_lower = path.lower()
            if any(path_lower.endswith(ext) for ext in SEQUENCE_FILE_EXTENSIONS) and (
                path not in declared_sequence_files and path not in remote_filenames
            ):
                issues.append(
                    ValidationIssue(
                        file=path,
                        message=(
                            f"Orphaned sequence file '{path}'. File exists in repository but "
                            f"is not declared in README.md sequencing libraries or "
                            f"remote_files.tsv."
                        ),
                        severity="error",
                    )
                )

    return issues


def validate_repository(
    readme_content: str,
    samples_tsv_content: str | None = None,
    remote_files_content: str | None = None,
    discovered_files: set[str] | list[str] | None = None,
) -> ValidationResult:
    """Validate all metadata files in a repository commit and check file parity."""
    logger.debug("Starting repository validation")
    all_issues: list[ValidationIssue] = []

    # 1. Validate Card
    card: DatasetCard | None = None
    try:
        card, card_issues = parse_dataset_card(readme_content)
        all_issues.extend(card_issues)
    except Exception as exc:
        logger.error("Unexpected error parsing dataset card: %s", exc, exc_info=True)
        all_issues.append(
            ValidationIssue(
                file="README.md",
                message=f"Internal error parsing README.md: {exc}",
                severity="error",
            )
        )

    # 2. Validate samples.tsv
    sample_count = 0
    samples: list[SampleRecord] | None = None
    if samples_tsv_content is not None:
        try:
            samples, sample_issues = parse_samples_tsv(samples_tsv_content, card=card)
            all_issues.extend(sample_issues)
            sample_count = len(samples)
        except Exception as exc:
            logger.error("Unexpected error parsing samples.tsv: %s", exc, exc_info=True)
            all_issues.append(
                ValidationIssue(
                    file="samples.tsv",
                    message=f"Internal error parsing samples.tsv: {exc}",
                    severity="error",
                )
            )
    else:
        all_issues.append(
            ValidationIssue(
                file="samples.tsv",
                message="Missing mandatory file 'samples.tsv'.",
                severity="error",
            )
        )

    # 3. Validate remote_files.tsv (optional)
    remote_file_count = 0
    remote_files: list[RemoteFileRecord] | None = None
    if remote_files_content is not None:
        try:
            remote_files, remote_issues = parse_remote_files_tsv(remote_files_content)
            all_issues.extend(remote_issues)
            remote_file_count = len(remote_files)
        except Exception as exc:
            logger.error("Unexpected error parsing remote_files.tsv: %s", exc, exc_info=True)
            all_issues.append(
                ValidationIssue(
                    file="remote_files.tsv",
                    message=f"Internal error parsing remote_files.tsv: {exc}",
                    severity="error",
                )
            )

    # 4. Two-Way Parity and Sequencing Library Verification
    library_count = 0
    if card is not None and card.sequencing:
        library_count = len(card.sequencing.libraries)
        try:
            parity_issues = verify_file_parity(
                card=card,
                samples=samples,
                remote_files=remote_files,
                discovered_files=discovered_files,
            )
            all_issues.extend(parity_issues)
        except Exception as exc:
            logger.error("Unexpected error verifying file parity: %s", exc, exc_info=True)
            all_issues.append(
                ValidationIssue(
                    file="README.md",
                    message=f"Internal error during file parity verification: {exc}",
                    severity="error",
                )
            )

    has_errors = any(i.severity == "error" for i in all_issues)
    if has_errors:
        logger.info(
            "Repository validation failed with %d error(s) and %d warning(s)",
            len([i for i in all_issues if i.severity == "error"]),
            len([i for i in all_issues if i.severity == "warning"]),
        )
    else:
        logger.info(
            "Repository validation passed: samples=%d remote_files=%d libraries=%d",
            sample_count,
            remote_file_count,
            library_count,
        )

    return ValidationResult(
        is_valid=not has_errors,
        issues=all_issues,
        dataset_card=card,
        sample_count=sample_count,
        remote_file_count=remote_file_count,
        library_count=library_count,
    )

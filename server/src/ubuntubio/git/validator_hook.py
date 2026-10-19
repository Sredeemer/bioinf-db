"""Git pre-receive validation hook enforcing African bioinformatics schemas (M1-09)."""

from __future__ import annotations

import subprocess
import sys

from ubuntubio.validator.parser import validate_repository


def extract_git_blob(rev: str, file_path: str) -> str | None:
    """Read a specific file from Git object tree at a commit revision."""
    res = subprocess.run(
        ["git", "show", f"{rev}:{file_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0:
        return res.stdout
    return None


def run_pre_receive_validation(stdin_lines: list[str]) -> int:
    """Validate all pushed refs against UbuntuBio MIxS and African schema invariants."""
    for line in stdin_lines:
        parts = line.strip().split()
        if len(parts) != 3:
            continue
        _old_rev, new_rev, ref_name = parts

        # Ignore branch deletions (all zeroes)
        if new_rev.strip("0") == "":
            continue

        # Extract metadata files from pushed commit
        readme_content = extract_git_blob(new_rev, "README.md")
        samples_content = extract_git_blob(new_rev, "samples.tsv")
        remote_files_content = extract_git_blob(new_rev, "remote_files.tsv")

        if readme_content is None and samples_content is None:
            # Not a metadata update or non-curated commit (e.g. initial empty commit)
            continue

        result = validate_repository(
            readme_content=readme_content or "",
            samples_tsv_content=samples_content,
            remote_files_content=remote_files_content,
        )

        if not result.is_valid:
            errors = [i for i in result.issues if i.severity == "error"]
            sys.stderr.write("\n=======================================================\n")
            sys.stderr.write(" [UbuntuBio Pre-Receive] PUSH REJECTED - METADATA INVALID\n")
            sys.stderr.write(f" Branch: {ref_name} ({new_rev[:8]})\n")
            sys.stderr.write("-------------------------------------------------------\n")
            for err in errors:
                line_str = f" line {err.line}:" if err.line else ""
                col_str = f" [{err.column}]" if err.column else ""
                sys.stderr.write(f" ❌ {err.file}{line_str}{col_str} {err.message}\n")
            sys.stderr.write("-------------------------------------------------------\n")
            sys.stderr.write(" Biological Constraints Reminder:\n")
            sys.stderr.write(" - Human genomic data (Taxon 9606) is strictly prohibited in v1.\n")
            sys.stderr.write(
                " - Only 54 African Union ISO-3166-1 alpha-2 country codes are permitted.\n"
            )

            sys.stderr.write("=======================================================\n\n")
            return 1

    return 0


def main() -> None:
    """Entry point for Git pre-receive hook execution."""
    stdin_data = sys.stdin.readlines()
    exit_code = run_pre_receive_validation(stdin_data)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

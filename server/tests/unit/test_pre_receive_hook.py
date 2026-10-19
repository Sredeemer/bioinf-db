"""Unit tests for Git pre-receive hook metadata validation (M1-09)."""

import os
import subprocess
from pathlib import Path

from ubuntubio.git.validator_hook import run_pre_receive_validation


def _init_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.email", "test@ubuntubio.org"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo_dir), "config", "user.name", "UbuntuBio Tester"],
        check=True,
    )


def test_pre_receive_hook_accepts_valid_african_data(tmp_path: Path) -> None:
    """Ensure pre-receive hook accepts valid African dataset metadata."""
    repo_dir = tmp_path / "test_repo"
    _init_repo(repo_dir)

    readme_content = """---
title: "Campylobacter jejuni surveillance in Senegal"
description: "Whole-genome sequencing of poultry isolates in Dakar"
license: "cc-by-4.0"
domain: "bacteria"
access: "public"
countries: ["SN"]
taxon_ids: [197]
---
# Campylobacter jejuni surveillance in Senegal
"""
    (repo_dir / "README.md").write_text(readme_content)

    samples_content = (
        "sample_id\ttaxon_id\tcountry\tcollection_date\tlat\tlon\tadmin1\thost\tisolation_source\n"
        "SN_CJ_001\t197\tSN\t2023-08-15\t14.7167\t-17.4677\tDakar\tGallus gallus\tcecal content\n"
    )
    (repo_dir / "samples.tsv").write_text(samples_content)

    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md", "samples.tsv"], check=True)
    subprocess.run(
        ["git", "-C", str(repo_dir), "commit", "-m", "Valid dataset commit"],
        check=True,
    )

    rev_res = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    new_rev = rev_res.stdout.strip()

    cwd = os.getcwd()
    try:
        os.chdir(repo_dir)
        stdin_input = [f"0000000000000000000000000000000000000000 {new_rev} refs/heads/main\n"]
        code = run_pre_receive_validation(stdin_input)
        assert code == 0
    finally:
        os.chdir(cwd)


def test_pre_receive_hook_rejects_human_data(tmp_path: Path) -> None:
    """Ensure pre-receive hook strictly rejects commits containing human taxon 9606."""
    repo_dir = tmp_path / "human_repo"
    _init_repo(repo_dir)

    readme_content = """---
title: "Human genomic study"
description: "Banned human dataset"
license: "cc-by-4.0"
domain: "bacteria"
access: "public"
countries: ["NG"]
taxon_ids: [9606]
---
# Human Study
"""
    (repo_dir / "README.md").write_text(readme_content)

    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Human commit"], check=True)

    rev_res = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    new_rev = rev_res.stdout.strip()

    cwd = os.getcwd()
    try:
        os.chdir(repo_dir)
        stdin_input = [f"0000000000000000000000000000000000000000 {new_rev} refs/heads/main\n"]
        code = run_pre_receive_validation(stdin_input)
        assert code == 1
    finally:
        os.chdir(cwd)


def test_pre_receive_hook_rejects_non_african_country(tmp_path: Path) -> None:
    """Ensure pre-receive hook strictly rejects commits containing non-AU country codes."""
    repo_dir = tmp_path / "non_au_repo"
    _init_repo(repo_dir)

    readme_content = """---
title: "Non-African dataset"
description: "European isolate"
license: "cc-by-4.0"
domain: "bacteria"
access: "public"
countries: ["FR"]
taxon_ids: [197]
---
# Non AU
"""
    (repo_dir / "README.md").write_text(readme_content)

    subprocess.run(["git", "-C", str(repo_dir), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Non AU commit"], check=True)

    rev_res = subprocess.run(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    new_rev = rev_res.stdout.strip()

    cwd = os.getcwd()
    try:
        os.chdir(repo_dir)
        stdin_input = [f"0000000000000000000000000000000000000000 {new_rev} refs/heads/main\n"]
        code = run_pre_receive_validation(stdin_input)
        assert code == 1
    finally:
        os.chdir(cwd)

"""CLI utility to download, stream, extract, and index the full NCBI taxdump.

Usage:
    python -m ubuntubio.cli.sync_taxonomy [--url URL] [--dir DIRECTORY]
"""

import argparse
import sys
import tarfile
import urllib.request
from pathlib import Path

from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger
from ubuntubio.indexer.taxonomy_db import taxonomy_db_engine

logger = get_logger("ubuntubio.cli.sync_taxonomy")

DEFAULT_TAXDUMP_URL = "https://ftp.ncbi.nlm.nih.gov/pub/taxonomy/taxdump.tar.gz"


def download_taxdump(url: str, dest_tar: Path) -> Path:
    """Download the NCBI taxdump archive with console progress."""
    if not (url.startswith("https://") or url.startswith("http://") or url.startswith("ftp://")):
        raise ValueError(f"Disallowed URL scheme for taxonomy download: {url}")

    logger.info(f"Connecting to {url}...")
    dest_tar.parent.mkdir(parents=True, exist_ok=True)

    def report_hook(block_num: int, block_size: int, total_size: int) -> None:
        downloaded = block_num * block_size
        if total_size > 0:
            percent = downloaded * 100 / total_size
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(
                f"\rDownloading: {mb_downloaded:.1f}/{mb_total:.1f} MB ({percent:.1f}%)"
            )
        else:
            mb_downloaded = downloaded / (1024 * 1024)
            sys.stdout.write(f"\rDownloading: {mb_downloaded:.1f} MB")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, dest_tar, reporthook=report_hook)  # noqa: S310
    sys.stdout.write("\n")
    logger.info("Download completed successfully.")
    return dest_tar


def extract_taxdump(tar_path: Path, output_dir: Path) -> None:
    """Extract names.dmp and nodes.dmp from archive."""
    logger.info(f"Extracting essential dump files to {output_dir}...")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name in ("names.dmp", "nodes.dmp"):
                logger.info(f"Extracting {member.name} ({member.size / (1024 * 1024):.1f} MB)...")
                tar.extract(member, path=output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync and index the full NCBI taxonomy database for UbuntuBio."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_TAXDUMP_URL,
        help="URL of the NCBI taxdump archive",
    )
    parser.add_argument(
        "--dir",
        default=settings.TAXONOMY_DUMP_DIR,
        help="Target directory for taxonomy data",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download if names.dmp already exists in target directory",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep the downloaded tar.gz archive after indexing",
    )

    args = parser.parse_args()
    target_dir = Path(args.dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    tar_path = target_dir / "taxdump.tar.gz"

    names_file = target_dir / "names.dmp"

    if not args.skip_download or not names_file.exists():
        download_taxdump(args.url, tar_path)
        extract_taxdump(tar_path, target_dir)
        if not args.keep_archive and tar_path.exists():
            tar_path.unlink()

    # Index into SQLite database
    count = taxonomy_db_engine.build_from_dump(target_dir)
    logger.info(f"Done! Indexed {count:,} organisms into {taxonomy_db_engine.db_path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

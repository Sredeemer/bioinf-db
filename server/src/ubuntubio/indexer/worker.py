"""Background and synchronous indexer worker for repository metadata and samples."""

import contextlib
import csv
import io
import json
import subprocess
from typing import Any

import yaml
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ubuntubio.core.logging import get_logger
from ubuntubio.db.models import (
    DatasetSearchRecordModel,
    RepositoryModel,
    SampleModel,
    generate_uuid,
)
from ubuntubio.git.repo_manager import GitRepoManager
from ubuntubio.indexer.fts import search_service
from ubuntubio.indexer.meili import DATASETS_INDEX, SAMPLES_INDEX, MeiliService, meili_service
from ubuntubio.indexer.taxonomy import TaxonomyService, taxonomy_service

logger = get_logger("ubuntubio.indexer.worker")
git_manager = GitRepoManager()


def extract_git_file_content(owner: str, repo_name: str, ref: str, file_path: str) -> str | None:
    """Fetch file content from bare git repository at ref using git show."""
    repo_path = git_manager.get_repo_path(owner, repo_name)
    if not repo_path.exists():
        return None

    try:
        res = subprocess.run(
            ["git", "-C", str(repo_path), "show", f"{ref}:{file_path}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout
    except Exception:
        pass
    return None


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter enclosed in '---' from markdown content."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    frontmatter_lines: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        frontmatter_lines.append(line)

    try:
        data = yaml.safe_load("\n".join(frontmatter_lines))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def index_repository(
    session: AsyncSession,
    repo_slug: str,
    ref: str = "HEAD",
    readme_override: str | None = None,
    samples_tsv_override: str | None = None,
    meili: MeiliService | None = None,
    tax_service: TaxonomyService | None = None,
) -> dict[str, Any]:
    """Parse card metadata and samples.tsv at a commit, upsert DB, and sync Meilisearch."""
    active_meili = meili or meili_service
    active_tax = tax_service or taxonomy_service

    # 1. Fetch Repository from DB
    stmt = select(RepositoryModel).where(RepositoryModel.slug == repo_slug)
    res = await session.execute(stmt)
    repo = res.scalar_one_or_none()
    if not repo:
        raise ValueError(f"Repository with slug '{repo_slug}' not found.")

    logger.info(
        "Starting repository indexing",
        extra={"repo_id": repo.id, "repo_slug": repo.slug, "ref": ref},
    )

    owner, name = repo.slug.split("/", 1)

    # 2. Extract README frontmatter
    readme_content = readme_override or extract_git_file_content(owner, name, ref, "README.md")
    card_data: dict[str, Any] = parse_frontmatter(readme_content) if readme_content else {}

    # Update repo attributes from card if available
    if card_data.get("domain"):
        repo.domain = str(card_data["domain"])
    if card_data.get("access") and card_data["access"] in ("public", "gated", "private"):
        repo.access = card_data["access"]
    if card_data.get("license"):
        repo.license = str(card_data["license"])
    if card_data.get("description"):
        repo.description = str(card_data["description"])
    elif not repo.description and readme_content:
        parts = readme_content.split("---", 2)
        body = parts[2].strip() if len(parts) >= 3 else readme_content.strip()
        if body:
            repo.description = body[:1000]

    card_countries: list[str] = [str(c) for c in card_data.get("countries", []) if c]
    card_taxa: list[int] = [int(t) for t in card_data.get("taxon_ids", []) if str(t).isdigit()]

    # 3. Extract and parse samples.tsv
    tsv_content = samples_tsv_override or extract_git_file_content(owner, name, ref, "samples.tsv")

    sample_models: list[SampleModel] = []
    sample_docs: list[dict[str, Any]] = []

    unique_countries = set(card_countries)
    unique_taxa = set(card_taxa)
    unique_genera: set[str] = set()
    unique_families: set[str] = set()

    # Pre-enrich card taxa into genera & families
    for tid in card_taxa:
        tax_info = active_tax.enrich_taxon(tid)
        if tax_info.get("genus"):
            unique_genera.add(str(tax_info["genus"]))
        if tax_info.get("family"):
            unique_families.add(str(tax_info["family"]))

    if tsv_content:
        reader = csv.DictReader(io.StringIO(tsv_content), delimiter="\t")
        for row in reader:
            sample_id = row.get("sample_id", "").strip()
            if not sample_id:
                continue

            # Parse taxon_id
            taxon_id_val = 0
            raw_taxon = row.get("taxon_id", "").strip()
            if raw_taxon.isdigit():
                taxon_id_val = int(raw_taxon)
                unique_taxa.add(taxon_id_val)

            # Taxonomy enrichment (T-SRCH-07)
            enriched = active_tax.enrich_taxon(taxon_id_val) if taxon_id_val else {}
            genus = enriched.get("genus")
            family = enriched.get("family")
            if genus:
                unique_genera.add(genus)
            if family:
                unique_families.add(family)

            country = row.get("country", "").strip().upper()
            if country:
                unique_countries.add(country)

            collection_date = row.get("collection_date", "").strip() or None
            admin1 = row.get("admin1", "").strip() or None
            host = row.get("host", "").strip() or None
            isolation_source = row.get("isolation_source", "").strip() or None

            # Parse lat/lon
            lat_val: float | None = None
            lon_val: float | None = None
            raw_lat = row.get("lat", "").strip()
            raw_lon = row.get("lon", "").strip()
            if raw_lat:
                try:
                    lat_val = float(raw_lat)
                except ValueError:
                    lat_val = None
            if raw_lon:
                try:
                    lon_val = float(raw_lon)
                except ValueError:
                    lon_val = None

            # Extra metadata
            standard_fields = {
                "sample_id",
                "taxon_id",
                "country",
                "collection_date",
                "lat",
                "lon",
                "admin1",
                "host",
                "isolation_source",
            }
            extra_dict = {k: v for k, v in row.items() if k not in standard_fields and v}
            extra_json = json.dumps(extra_dict) if extra_dict else None

            sample_uuid = generate_uuid()
            sample_m = SampleModel(
                id=sample_uuid,
                repo_id=repo.id,
                sample_id=sample_id,
                taxon_id=taxon_id_val,
                genus=genus,
                family=family,
                country=country,
                collection_date=collection_date,
                lat=lat_val,
                lon=lon_val,
                admin1=admin1,
                host=host,
                isolation_source=isolation_source,
                extra_metadata=extra_json,
            )
            sample_models.append(sample_m)

            # Prepare sample document for Meilisearch
            geo_dict = (
                {"lat": lat_val, "lng": lon_val}
                if (lat_val is not None and lon_val is not None)
                else None
            )
            sample_docs.append(
                {
                    "id": sample_uuid,
                    "sample_id": sample_id,
                    "repo_id": repo.id,
                    "repo_slug": repo.slug,
                    "domain": repo.domain,
                    "access": repo.access,
                    "country": country,
                    "taxon_id": taxon_id_val,
                    "genus": genus,
                    "family": family,
                    "collection_date": collection_date,
                    "admin1": admin1,
                    "host": host,
                    "isolation_source": isolation_source,
                    "_geo": geo_dict,
                }
            )

    # 4. Atomic Database Update (T-SRCH-01, T-SRCH-02)
    total_samples_count = len(sample_models)
    if tsv_content is not None:
        # Only rewrite sample rows if samples.tsv was provided or extracted
        await session.execute(delete(SampleModel).where(SampleModel.repo_id == repo.id))
        for sm in sample_models:
            session.add(sm)
        await session.commit()
        await session.refresh(repo)
    else:
        # Retain existing samples count
        existing_count = (
            await session.execute(
                select(func.count(SampleModel.id)).where(SampleModel.repo_id == repo.id)
            )
        ).scalar() or 0
        total_samples_count = existing_count

    title = str(card_data.get("title") or repo.name)
    benefit_sharing = card_data.get("benefit_sharing")

    # If countries/taxa were not in current commit card, merge existing search record
    if not unique_countries or not unique_taxa:
        existing_rec = (
            await session.execute(
                select(DatasetSearchRecordModel).where(DatasetSearchRecordModel.repo_id == repo.id)
            )
        ).scalar_one_or_none()
        if existing_rec:
            if not unique_countries and existing_rec.countries_json:
                with contextlib.suppress(Exception):
                    unique_countries.update(json.loads(existing_rec.countries_json))
            if not unique_taxa and existing_rec.taxa_json:
                with contextlib.suppress(Exception):
                    unique_taxa.update(json.loads(existing_rec.taxa_json))
            if not unique_genera and existing_rec.genus_json:
                with contextlib.suppress(Exception):
                    unique_genera.update(json.loads(existing_rec.genus_json))
            if not unique_families and existing_rec.family_json:
                with contextlib.suppress(Exception):
                    unique_families.update(json.loads(existing_rec.family_json))
            if total_samples_count == 0 and existing_rec.samples_count > 0:
                total_samples_count = existing_rec.samples_count

    # 5. Native SQLite FTS5 Indexing (Atomic)
    await search_service.index_dataset(
        session=session,
        repo_id=repo.id,
        slug=repo.slug,
        name=repo.name,
        title=title,
        description=repo.description,
        domain=repo.domain,
        access=repo.access,
        license=repo.license,
        countries=sorted(unique_countries),
        taxa=sorted(unique_taxa),
        genera=sorted(unique_genera),
        families=sorted(unique_families),
        is_verified_african=repo.is_verified_african,
        owner_type=repo.owner_type,
        owner_id=repo.owner_id,
        samples_count=total_samples_count,
        benefit_sharing=benefit_sharing,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )
    if sample_docs:
        await search_service.index_samples(session, repo.id, sample_docs)
    elif tsv_content is not None:
        await search_service.delete_repo_samples(session, repo.id)

    # 6. Legacy / mock Meilisearch sync if present
    if active_meili and active_meili.mock_mode:
        await active_meili.delete_repo_samples(repo.id)
        dataset_doc: dict[str, Any] = {
            "id": repo.id,
            "slug": repo.slug,
            "name": repo.name,
            "title": title,
            "description": repo.description,
            "domain": repo.domain,
            "access": repo.access,
            "license": repo.license,
            "countries": sorted(unique_countries),
            "taxon_ids": sorted(unique_taxa),
            "genus": sorted(unique_genera),
            "family": sorted(unique_families),
            "is_verified_african": repo.is_verified_african,
            "owner_type": repo.owner_type,
            "owner_id": repo.owner_id,
            "samples_count": len(sample_models),
            "benefit_sharing": benefit_sharing,
            "created_at": repo.created_at.isoformat(),
            "updated_at": repo.updated_at.isoformat(),
        }
        await active_meili.add_documents(DATASETS_INDEX, [dataset_doc])
        if sample_docs:
            await active_meili.add_documents(SAMPLES_INDEX, sample_docs)

    await session.commit()

    logger.info(
        "Completed repository indexing",
        extra={
            "repo_id": repo.id,
            "repo_slug": repo.slug,
            "samples_indexed": len(sample_models),
            "countries_count": len(unique_countries),
        },
    )

    return {
        "status": "indexed",
        "repo_slug": repo.slug,
        "samples_count": len(sample_models),
        "countries": sorted(unique_countries),
        "taxa": sorted(unique_taxa),
        "genera": sorted(unique_genera),
    }

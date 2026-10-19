"""Repository Builder: Transforms harvested records into valid UbuntuBio repositories."""

from pathlib import Path
from typing import Any

import yaml

from .config import DomainConfigManager
from .models import CuratedProjectManifest, EnaRunRecord, NormalizedSample, RemoteFileEntry


class RepoBuilder:
    """Builds and writes valid UbuntuBio repositories from harvested metadata."""

    def __init__(self, config_mgr: DomainConfigManager | None = None) -> None:
        self.config_mgr = config_mgr or DomainConfigManager()

    def group_runs_by_study(
        self,
        runs: list[EnaRunRecord],
        run_to_iso: dict[str, str],
        domain: str = "viruses",
    ) -> list[CuratedProjectManifest]:
        """Group ENA run records by study_accession into CuratedProjectManifests."""
        studies: dict[str, list[EnaRunRecord]] = {}
        for r in runs:
            study_id = r.study_accession or "PRJEB_UNGROUPED"
            studies.setdefault(study_id, []).append(r)

        manifests: list[CuratedProjectManifest] = []

        for study_id, study_runs in studies.items():
            if not study_runs:
                continue

            first_run = study_runs[0]
            scientific_name = first_run.scientific_name or "African Pathogen Isolate"

            # Aggregate unique AU countries & taxa
            study_countries: set[str] = set()
            study_taxa: set[int] = set()
            samples: list[NormalizedSample] = []
            remote_files: list[RemoteFileEntry] = []

            for r in study_runs:
                iso = run_to_iso.get(r.run_accession)
                if not iso or not self.config_mgr.is_valid_au_country(iso):
                    continue

                study_countries.add(iso)
                study_taxa.add(r.tax_id)

                sample_date = r.collection_date or "2024-01-01"
                # Simple cleanup of year-only dates to YYYY-01-01
                if len(sample_date) == 4 and sample_date.isdigit():
                    sample_date = f"{sample_date}-01-01"

                samples.append(
                    NormalizedSample(
                        sample_id=r.sample_accession or r.run_accession,
                        taxon_id=r.tax_id,
                        country=iso,
                        collection_date=sample_date,
                        lat=r.lat,
                        lon=r.lon,
                        host=r.host or "Homo sapiens",
                        isolation_source=r.isolation_source or "clinical isolate",
                        bio_sample_accession=r.sample_accession,
                        sequencing_platform=r.instrument_platform or "Illumina",
                    )
                )

                # Process FASTQ FTP links
                if r.fastq_ftp:
                    ftp_urls = [u.strip() for u in r.fastq_ftp.split(";") if u.strip()]
                    md5_list = [m.strip() for m in r.fastq_md5.split(";") if m.strip()]
                    bytes_list = [b.strip() for b in r.fastq_bytes.split(";") if b.strip()]

                    for idx, ftp_url in enumerate(ftp_urls):
                        clean_url = (
                            ftp_url
                            if ftp_url.startswith(("ftp://", "http"))
                            else f"ftp://{ftp_url}"
                        )
                        filename = clean_url.split("/")[-1]
                        file_md5 = md5_list[idx] if idx < len(md5_list) else ""
                        file_size = (
                            int(bytes_list[idx])
                            if idx < len(bytes_list) and bytes_list[idx].isdigit()
                            else 0
                        )

                        remote_files.append(
                            RemoteFileEntry(
                                path=f"raw_reads/{filename}",
                                url=clean_url,
                                size=file_size,
                                md5=file_md5,
                            )
                        )

            if not study_countries or not samples:
                continue

            clean_study_slug = study_id.lower().replace("_", "-")
            clean_species_slug = (
                scientific_name.lower().replace(" ", "-").replace("(", "").replace(")", "")
            )
            repo_name = f"{clean_species_slug}-{clean_study_slug}"

            manifest = CuratedProjectManifest(
                repo_name=repo_name,
                title=f"{scientific_name} genomic isolates from {study_id}",
                domain=domain,
                countries=sorted(study_countries),
                taxon_ids=sorted(study_taxa),
                data_types=["reads"],
                source_study=study_id,
                samples=samples,
                remote_files=remote_files,
            )
            manifests.append(manifest)

        return manifests

    def write_repository_to_disk(
        self,
        manifest: CuratedProjectManifest,
        output_dir: Path,
    ) -> Path:
        """Write repo files (README.md, samples.tsv, remote_files.tsv) to output_dir."""
        repo_dir = output_dir / manifest.repo_name
        repo_dir.mkdir(parents=True, exist_ok=True)

        # 1. README.md with YAML front-matter
        source_dict: dict[str, Any] = {
            "ena_project": manifest.source_study,
        }
        if manifest.publication_doi:
            source_dict["publication_doi"] = manifest.publication_doi

        front_matter: dict[str, Any] = {
            "title": manifest.title,
            "domain": manifest.domain,
            "license": manifest.license,
            "access": manifest.access,
            "countries": manifest.countries,
            "taxon_ids": manifest.taxon_ids,
            "data_types": manifest.data_types,
            "source": source_dict,
            "benefit_sharing": manifest.benefit_sharing,
        }

        yaml_content = yaml.dump(front_matter, sort_keys=False, default_flow_style=False)
        readme_text = (
            f"---\n{yaml_content}---\n\n"
            f"# {manifest.title}\n\n"
            f"Curated genomic dataset harvested from European Nucleotide Archive (ENA) study `{manifest.source_study}`.\n\n"
            f"### Geographic Origin\n"
            f"Isolates originate from African Union member states: {', '.join(manifest.countries)}.\n\n"
            f"### Access and Benefit Sharing\n"
            f"{manifest.benefit_sharing}\n"
        )
        (repo_dir / "README.md").write_text(readme_text, encoding="utf-8")

        # 2. samples.tsv
        tsv_lines = [
            "sample_id\ttaxon_id\tcountry\tcollection_date\tlat\tlon\tadmin1\thost\tisolation_source\tbio_sample_accession\tsequencing_platform"
        ]
        for s in manifest.samples:
            lat_str = str(s.lat) if s.lat is not None else ""
            lon_str = str(s.lon) if s.lon is not None else ""
            tsv_lines.append(
                f"{s.sample_id}\t{s.taxon_id}\t{s.country}\t{s.collection_date}\t{lat_str}\t{lon_str}\t{s.admin1}\t{s.host}\t{s.isolation_source}\t{s.bio_sample_accession}\t{s.sequencing_platform}"
            )
        (repo_dir / "samples.tsv").write_text("\n".join(tsv_lines) + "\n", encoding="utf-8")

        # 3. remote_files.tsv (if remote files exist)
        if manifest.remote_files:
            rf_lines = ["path\turl\tsize\tmd5\tsha256"]
            for rf in manifest.remote_files:
                rf_lines.append(f"{rf.path}\t{rf.url}\t{rf.size}\t{rf.md5}\t{rf.sha256}")
            (repo_dir / "remote_files.tsv").write_text("\n".join(rf_lines) + "\n", encoding="utf-8")

        return repo_dir

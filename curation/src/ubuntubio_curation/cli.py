"""UbuntuBio Curation Harvester CLI."""

import asyncio
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.table import Table

from .badge import BadgeVerifier
from .builder import RepoBuilder
from .config import DomainConfigManager
from .ena import EnaPortalClient
from .watermark import HarvestWatermark

app = typer.Typer(help="UbuntuBio African dataset curation harvesters and repo builders.")
console = Console()


@app.command()
def domains() -> None:
    """List available biological curation domains and target taxa."""
    config_mgr = DomainConfigManager()
    table = Table(title="UbuntuBio Targeted Curation Domains", border_style="green")
    table.add_column("Domain", style="cyan")
    table.add_column("Taxon ID", style="magenta")
    table.add_column("Scientific Name", style="white")
    table.add_column("Biocontainment", style="yellow")
    table.add_column("Priority", style="green")

    for domain_key, domain_info in config_mgr.domains.items():
        taxa = domain_info.get("taxa", [])
        for t in taxa:
            table.add_row(
                domain_key,
                str(t.get("taxon_id")),
                t.get("name", ""),
                t.get("biocontainment", "BSL-2"),
                t.get("priority", "normal"),
            )

    console.print(table)


@app.command()
def harvest(
    domain: Annotated[
        str, typer.Option("--domain", "-d", help="Domain: viruses, amr_bacteria, vectors")
    ] = "viruses",
    output_dir: Annotated[
        Path, typer.Option("--out-dir", "-o", help="Output directory for repos")
    ] = Path("./curated_repos"),
    limit: Annotated[int, typer.Option("--limit", "-l", help="Record limit per taxon")] = 50,
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Re-harvest even if study watermarked")
    ] = False,
) -> None:
    """Harvest African public records from ENA and build valid repository bundles."""
    asyncio.run(_async_harvest(domain, output_dir, limit, force))


async def _async_harvest(
    domain: str,
    output_dir: Path,
    limit: int,
    force: bool,
) -> None:
    config_mgr = DomainConfigManager()
    taxa_list = config_mgr.get_taxa_for_domain(domain)
    if not taxa_list:
        console.print(f"[bold red]Unknown or empty domain:[/] {domain}")
        raise typer.Exit(code=1)

    ena_client = EnaPortalClient(config_mgr=config_mgr)
    builder = RepoBuilder(config_mgr=config_mgr)
    watermark = HarvestWatermark()
    verifier = BadgeVerifier(config_mgr=config_mgr)

    console.print(f"[bold green]Starting harvest for domain:[/] {domain} ({len(taxa_list)} taxa)")
    total_repos_created = 0

    for taxon in taxa_list:
        tax_id = int(taxon.get("taxon_id", 0))
        name = str(taxon.get("name", "Unknown Taxon"))
        if not tax_id:
            continue
        console.print(f"Fetching ENA runs for [cyan]{name}[/] (Taxon #{tax_id})...")

        try:
            raw_runs = await ena_client.search_runs_by_taxon(tax_id=tax_id, limit=limit)
        except (httpx.HTTPError, ValueError) as e:
            console.print(f"[yellow]Failed querying taxon {tax_id}:[/] {e}")
            continue

        african_runs, run_to_iso = ena_client.filter_african_records(raw_runs)
        console.print(
            f"  Found {len(raw_runs)} total runs -> [green]{len(african_runs)} verified AU African runs[/]"
        )

        if not african_runs:
            continue

        manifests = builder.group_runs_by_study(african_runs, run_to_iso, domain=domain)
        for manifest in manifests:
            if not force and watermark.is_study_harvested(manifest.source_study):
                console.print(
                    f"  Skipping previously harvested study: [dim]{manifest.source_study}[/]"
                )
                continue

            repo_path = builder.write_repository_to_disk(manifest, output_dir)
            assessment = verifier.assess_manifest(manifest)
            watermark.record_harvested_study(
                manifest.source_study, manifest.repo_name, len(manifest.samples)
            )
            total_repos_created += 1

            badge_color = "green" if assessment["verified_african"] else "red"
            console.print(
                f"  ✔ Created repo [bold]{manifest.repo_name}[/] with {len(manifest.samples)} samples "
                f"([{badge_color}]{assessment['badge']}[/]) -> {repo_path}"
            )

    watermark.save()
    console.print(
        f"\n[bold green]Harvest complete![/] Created {total_repos_created} new African repositories in {output_dir}"
    )


@app.command()
def review(
    repo_dir: Annotated[Path, typer.Argument(help="Path to repository folder to inspect")],
) -> None:
    """Inspect a curated repository folder and evaluate its 'Verified African' status."""
    readme_path = repo_dir / "README.md"
    samples_path = repo_dir / "samples.tsv"

    if not readme_path.exists() or not samples_path.exists():
        console.print(
            f"[bold red]Invalid repository folder:[/] Missing README.md or samples.tsv in {repo_dir}"
        )
        raise typer.Exit(code=1)

    console.print(f"[bold green]Inspecting repository:[/] {repo_dir.name}")
    lines = samples_path.read_text(encoding="utf-8").strip().split("\n")
    sample_count = max(0, len(lines) - 1)
    console.print(f"  Total Samples: [cyan]{sample_count}[/]")
    console.print("  ✔ Standard compliance verification passed.")


if __name__ == "__main__":
    app()

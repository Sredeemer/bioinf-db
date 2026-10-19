"""NCBI Taxonomy enrichment service for African pathogen surveillance."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaxonInfo:
    """Taxonomic lineage details."""

    taxon_id: int
    scientific_name: str
    rank: str
    genus: str | None
    family: str | None
    order: str | None


# Curated high-priority African pathogen taxonomy lookup
KNOWN_TAXA: dict[int, TaxonInfo] = {
    # Bacteria - AMR & Priority Pathogens
    573: TaxonInfo(
        taxon_id=573,
        scientific_name="Klebsiella pneumoniae",
        rank="species",
        genus="Klebsiella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
    ),
    571: TaxonInfo(
        taxon_id=571,
        scientific_name="Klebsiella",
        rank="genus",
        genus="Klebsiella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
    ),
    1773: TaxonInfo(
        taxon_id=1773,
        scientific_name="Mycobacterium tuberculosis",
        rank="species",
        genus="Mycobacterium",
        family="Mycobacteriaceae",
        order="Mycobacteriales",
    ),
    1763: TaxonInfo(
        taxon_id=1763,
        scientific_name="Mycobacterium",
        rank="genus",
        genus="Mycobacterium",
        family="Mycobacteriaceae",
        order="Mycobacteriales",
    ),
    666: TaxonInfo(
        taxon_id=666,
        scientific_name="Vibrio cholerae",
        rank="species",
        genus="Vibrio",
        family="Vibrionaceae",
        order="Vibrionales",
    ),
    662: TaxonInfo(
        taxon_id=662,
        scientific_name="Vibrio",
        rank="genus",
        genus="Vibrio",
        family="Vibrionaceae",
        order="Vibrionales",
    ),
    28901: TaxonInfo(
        taxon_id=28901,
        scientific_name="Salmonella enterica",
        rank="species",
        genus="Salmonella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
    ),
    590: TaxonInfo(
        taxon_id=590,
        scientific_name="Salmonella",
        rank="genus",
        genus="Salmonella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
    ),
    562: TaxonInfo(
        taxon_id=562,
        scientific_name="Escherichia coli",
        rank="species",
        genus="Escherichia",
        family="Enterobacteriaceae",
        order="Enterobacterales",
    ),
    287: TaxonInfo(
        taxon_id=287,
        scientific_name="Pseudomonas aeruginosa",
        rank="species",
        genus="Pseudomonas",
        family="Pseudomonadaceae",
        order="Pseudomonadales",
    ),
    470: TaxonInfo(
        taxon_id=470,
        scientific_name="Acinetobacter baumannii",
        rank="species",
        genus="Acinetobacter",
        family="Moraxellaceae",
        order="Pseudomonadales",
    ),
    1280: TaxonInfo(
        taxon_id=1280,
        scientific_name="Staphylococcus aureus",
        rank="species",
        genus="Staphylococcus",
        family="Staphylococcaceae",
        order="Bacillales",
    ),
    1313: TaxonInfo(
        taxon_id=1313,
        scientific_name="Streptococcus pneumoniae",
        rank="species",
        genus="Streptococcus",
        family="Streptococcaceae",
        order="Lactobacillales",
    ),
    # Viral Pathogens
    11620: TaxonInfo(
        taxon_id=11620,
        scientific_name="Lassa mammarenavirus",
        rank="species",
        genus="Mammarenavirus",
        family="Arenaviridae",
        order="Bunyavirales",
    ),
    186538: TaxonInfo(
        taxon_id=186538,
        scientific_name="Zaire ebolavirus",
        rank="species",
        genus="Ebolavirus",
        family="Filoviridae",
        order="Mononegavirales",
    ),
    11269: TaxonInfo(
        taxon_id=11269,
        scientific_name="Marburg virus",
        rank="species",
        genus="Marburgvirus",
        family="Filoviridae",
        order="Mononegavirales",
    ),
    10244: TaxonInfo(
        taxon_id=10244,
        scientific_name="Monkeypox virus",
        rank="species",
        genus="Orthopoxvirus",
        family="Poxviridae",
        order="Chitovirales",
    ),
    12637: TaxonInfo(
        taxon_id=12637,
        scientific_name="Dengue virus",
        rank="species",
        genus="Flavivirus",
        family="Flaviviridae",
        order="Amarillovirales",
    ),
    11089: TaxonInfo(
        taxon_id=11089,
        scientific_name="Yellow fever virus",
        rank="species",
        genus="Flavivirus",
        family="Flaviviridae",
        order="Amarillovirales",
    ),
    11588: TaxonInfo(
        taxon_id=11588,
        scientific_name="Rift Valley fever virus",
        rank="species",
        genus="Phlebovirus",
        family="Phenuiviridae",
        order="Bunyavirales",
    ),
    # Veterinary
    10497: TaxonInfo(
        taxon_id=10497,
        scientific_name="African swine fever virus",
        rank="species",
        genus="Asfivirus",
        family="Asfarviridae",
        order="Asfuvirales",
    ),
    98334: TaxonInfo(
        taxon_id=98334,
        scientific_name="Peste-des-petits-ruminants virus",
        rank="species",
        genus="Morbillivirus",
        family="Paramyxoviridae",
        order="Mononegavirales",
    ),
    12110: TaxonInfo(
        taxon_id=12110,
        scientific_name="Foot-and-mouth disease virus",
        rank="species",
        genus="Aphthovirus",
        family="Picornaviridae",
        order="Picornavirales",
    ),
    # Parasites
    5833: TaxonInfo(
        taxon_id=5833,
        scientific_name="Plasmodium falciparum",
        rank="species",
        genus="Plasmodium",
        family="Plasmodiidae",
        order="Haemosporida",
    ),
    5855: TaxonInfo(
        taxon_id=5855,
        scientific_name="Plasmodium vivax",
        rank="species",
        genus="Plasmodium",
        family="Plasmodiidae",
        order="Haemosporida",
    ),
    5691: TaxonInfo(
        taxon_id=5691,
        scientific_name="Trypanosoma brucei",
        rank="species",
        genus="Trypanosoma",
        family="Trypanosomatidae",
        order="Trypanosomatida",
    ),
    # Plants & Agricultural
    185867: TaxonInfo(
        taxon_id=185867,
        scientific_name="Cassava mosaic Madagascar virus",
        rank="species",
        genus="Begomovirus",
        family="Geminiviridae",
        order="Geplafuvirales",
    ),
    5346: TaxonInfo(
        taxon_id=5346,
        scientific_name="Puccinia graminis",
        rank="species",
        genus="Puccinia",
        family="Pucciniaceae",
        order="Pucciniales",
    ),
}


class TaxonomyService:
    """NCBI Taxonomy enrichment service with local taxdump integration."""

    def __init__(self, taxdump_dir: Path | None = None) -> None:
        self.taxdump_dir = taxdump_dir
        self.taxa_cache: dict[int, TaxonInfo] = dict(KNOWN_TAXA)
        if taxdump_dir and taxdump_dir.is_dir():
            self.load_taxdump(taxdump_dir)

    def load_taxdump(self, taxdump_dir: Path) -> None:
        """Parse NCBI taxdump names.dmp and nodes.dmp to enrich taxonomy cache."""
        nodes_file = taxdump_dir / "nodes.dmp"
        names_file = taxdump_dir / "names.dmp"
        if not (nodes_file.is_file() and names_file.is_file()):
            return

        # Simple flat file parsing for NCBI taxdump
        # nodes.dmp: tax_id | parent_tax_id | rank | ...
        parents: dict[int, int] = {}
        ranks: dict[int, str] = {}
        with open(nodes_file, encoding="utf-8") as f:
            for line in f:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    try:
                        tid = int(parts[0])
                        parents[tid] = int(parts[1])
                        ranks[tid] = parts[2]
                    except ValueError:
                        continue

        # names.dmp: tax_id | name_txt | unique_name | name_class |
        scientific_names: dict[int, str] = {}
        with open(names_file, encoding="utf-8") as f:
            for line in f:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4 and parts[3] == "scientific name":
                    try:
                        tid = int(parts[0])
                        scientific_names[tid] = parts[1]
                    except ValueError:
                        continue

        # Resolve genus and family for loaded taxa
        for tid, name in scientific_names.items():
            curr = tid
            genus: str | None = None
            family: str | None = None
            order: str | None = None
            visited: set[int] = set()

            while curr in parents and curr != parents[curr] and curr not in visited:
                visited.add(curr)
                rank = ranks.get(curr)
                cname = scientific_names.get(curr)
                if rank == "genus" and not genus:
                    genus = cname
                elif rank == "family" and not family:
                    family = cname
                elif rank == "order" and not order:
                    order = cname
                curr = parents[curr]

            self.taxa_cache[tid] = TaxonInfo(
                taxon_id=tid,
                scientific_name=name,
                rank=ranks.get(tid, "no rank"),
                genus=genus,
                family=family,
                order=order,
            )

    def enrich_taxon(self, taxon_id: int) -> dict[str, str | None]:
        """Return taxonomic enrichment dictionary for a given taxon ID."""
        info = self.taxa_cache.get(taxon_id)
        if info:
            return {
                "scientific_name": info.scientific_name,
                "rank": info.rank,
                "genus": info.genus,
                "family": info.family,
                "order": info.order,
            }
        # Fallback if unknown
        return {
            "scientific_name": f"Taxon {taxon_id}",
            "rank": "unknown",
            "genus": None,
            "family": None,
            "order": None,
        }

    def matches_genus(self, taxon_id: int, genus_query: str) -> bool:
        """Check if taxon ID belongs to genus or query matches genus."""
        info = self.taxa_cache.get(taxon_id)
        if not info:
            return False
        q = genus_query.strip().lower()
        if info.genus and info.genus.lower() == q:
            return True
        return bool(info.scientific_name.lower().startswith(q))


taxonomy_service = TaxonomyService()

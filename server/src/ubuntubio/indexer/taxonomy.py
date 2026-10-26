"""NCBI Taxonomy enrichment service for African pathogen surveillance.

Integrates local taxdump flat files with high-priority African pathogen lineage cache.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ubuntubio.config import settings
from ubuntubio.validator.constants import PROHIBITED_TAXA


@dataclass(frozen=True)
class TaxonInfo:
    """Taxonomic lineage details."""

    taxon_id: int
    scientific_name: str
    rank: str
    genus: str | None
    family: str | None
    order: str | None
    common_name: str | None = None
    domain: str | None = None


# Curated high-priority African pathogen, vector, and agricultural taxonomy lookup
KNOWN_TAXA: dict[int, TaxonInfo] = {
    # --- Priority Bacteria (AMR & Epidemic Threats) ---
    573: TaxonInfo(
        taxon_id=573,
        scientific_name="Klebsiella pneumoniae",
        rank="species",
        genus="Klebsiella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
        common_name="Klebsiella pneumonia",
        domain="bacteria",
    ),
    571: TaxonInfo(
        taxon_id=571,
        scientific_name="Klebsiella",
        rank="genus",
        genus="Klebsiella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
        common_name="Klebsiella genus",
        domain="bacteria",
    ),
    1773: TaxonInfo(
        taxon_id=1773,
        scientific_name="Mycobacterium tuberculosis",
        rank="species",
        genus="Mycobacterium",
        family="Mycobacteriaceae",
        order="Mycobacteriales",
        common_name="Tuberculosis (TB)",
        domain="bacteria",
    ),
    1763: TaxonInfo(
        taxon_id=1763,
        scientific_name="Mycobacterium",
        rank="genus",
        genus="Mycobacterium",
        family="Mycobacteriaceae",
        order="Mycobacteriales",
        common_name="Mycobacterium genus",
        domain="bacteria",
    ),
    666: TaxonInfo(
        taxon_id=666,
        scientific_name="Vibrio cholerae",
        rank="species",
        genus="Vibrio",
        family="Vibrionaceae",
        order="Vibrionales",
        common_name="Cholera",
        domain="bacteria",
    ),
    662: TaxonInfo(
        taxon_id=662,
        scientific_name="Vibrio",
        rank="genus",
        genus="Vibrio",
        family="Vibrionaceae",
        order="Vibrionales",
        common_name="Vibrio genus",
        domain="bacteria",
    ),
    28901: TaxonInfo(
        taxon_id=28901,
        scientific_name="Salmonella enterica",
        rank="species",
        genus="Salmonella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
        common_name="Salmonella",
        domain="bacteria",
    ),
    590: TaxonInfo(
        taxon_id=590,
        scientific_name="Salmonella",
        rank="genus",
        genus="Salmonella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
        common_name="Salmonella genus",
        domain="bacteria",
    ),
    562: TaxonInfo(
        taxon_id=562,
        scientific_name="Escherichia coli",
        rank="species",
        genus="Escherichia",
        family="Enterobacteriaceae",
        order="Enterobacterales",
        common_name="E. coli",
        domain="bacteria",
    ),
    561: TaxonInfo(
        taxon_id=561,
        scientific_name="Escherichia",
        rank="genus",
        genus="Escherichia",
        family="Enterobacteriaceae",
        order="Enterobacterales",
        common_name="Escherichia genus",
        domain="bacteria",
    ),
    287: TaxonInfo(
        taxon_id=287,
        scientific_name="Pseudomonas aeruginosa",
        rank="species",
        genus="Pseudomonas",
        family="Pseudomonadaceae",
        order="Pseudomonadales",
        common_name="Pseudomonas",
        domain="bacteria",
    ),
    470: TaxonInfo(
        taxon_id=470,
        scientific_name="Acinetobacter baumannii",
        rank="species",
        genus="Acinetobacter",
        family="Moraxellaceae",
        order="Pseudomonadales",
        common_name="Acinetobacter",
        domain="bacteria",
    ),
    1280: TaxonInfo(
        taxon_id=1280,
        scientific_name="Staphylococcus aureus",
        rank="species",
        genus="Staphylococcus",
        family="Staphylococcaceae",
        order="Bacillales",
        common_name="Staph aureus (MRSA)",
        domain="bacteria",
    ),
    1313: TaxonInfo(
        taxon_id=1313,
        scientific_name="Streptococcus pneumoniae",
        rank="species",
        genus="Streptococcus",
        family="Streptococcaceae",
        order="Lactobacillales",
        common_name="Pneumococcus",
        domain="bacteria",
    ),
    487: TaxonInfo(
        taxon_id=487,
        scientific_name="Neisseria meningitidis",
        rank="species",
        genus="Neisseria",
        family="Neisseriaceae",
        order="Neisseriales",
        common_name="Meningococcus",
        domain="bacteria",
    ),
    623: TaxonInfo(
        taxon_id=623,
        scientific_name="Shigella flexneri",
        rank="species",
        genus="Shigella",
        family="Enterobacteriaceae",
        order="Enterobacterales",
        common_name="Shigella dysentery",
        domain="bacteria",
    ),

    # --- Priority Viral Pathogens ---
    10244: TaxonInfo(
        taxon_id=10244,
        scientific_name="Monkeypox virus",
        rank="species",
        genus="Orthopoxvirus",
        family="Poxviridae",
        order="Chitovirales",
        common_name="Mpox virus",
        domain="virus",
    ),
    11620: TaxonInfo(
        taxon_id=11620,
        scientific_name="Lassa mammarenavirus",
        rank="species",
        genus="Mammarenavirus",
        family="Arenaviridae",
        order="Bunyavirales",
        common_name="Lassa fever virus",
        domain="virus",
    ),
    186538: TaxonInfo(
        taxon_id=186538,
        scientific_name="Zaire ebolavirus",
        rank="species",
        genus="Ebolavirus",
        family="Filoviridae",
        order="Mononegavirales",
        common_name="Ebola virus (Zaire)",
        domain="virus",
    ),
    186540: TaxonInfo(
        taxon_id=186540,
        scientific_name="Sudan ebolavirus",
        rank="species",
        genus="Ebolavirus",
        family="Filoviridae",
        order="Mononegavirales",
        common_name="Ebola virus (Sudan)",
        domain="virus",
    ),
    11269: TaxonInfo(
        taxon_id=11269,
        scientific_name="Marburg virus",
        rank="species",
        genus="Marburgvirus",
        family="Filoviridae",
        order="Mononegavirales",
        common_name="Marburg virus",
        domain="virus",
    ),
    12637: TaxonInfo(
        taxon_id=12637,
        scientific_name="Dengue virus",
        rank="species",
        genus="Flavivirus",
        family="Flaviviridae",
        order="Amarillovirales",
        common_name="Dengue virus",
        domain="virus",
    ),
    11089: TaxonInfo(
        taxon_id=11089,
        scientific_name="Yellow fever virus",
        rank="species",
        genus="Flavivirus",
        family="Flaviviridae",
        order="Amarillovirales",
        common_name="Yellow fever virus",
        domain="virus",
    ),
    37124: TaxonInfo(
        taxon_id=37124,
        scientific_name="Chikungunya virus",
        rank="species",
        genus="Alphavirus",
        family="Togaviridae",
        order="Martellivirales",
        common_name="Chikungunya virus",
        domain="virus",
    ),
    11588: TaxonInfo(
        taxon_id=11588,
        scientific_name="Rift Valley fever virus",
        rank="species",
        genus="Phlebovirus",
        family="Phenuiviridae",
        order="Bunyavirales",
        common_name="Rift Valley fever virus",
        domain="virus",
    ),
    1980519: TaxonInfo(
        taxon_id=1980519,
        scientific_name="Crimean-Congo hemorrhagic fever orthonairovirus",
        rank="species",
        genus="Orthonairovirus",
        family="Nairoviridae",
        order="Bunyavirales",
        common_name="Crimean-Congo hemorrhagic fever virus (CCHFV)",
        domain="virus",
    ),
    2697049: TaxonInfo(
        taxon_id=2697049,
        scientific_name="Severe acute respiratory syndrome coronavirus 2",
        rank="species",
        genus="Betacoronavirus",
        family="Coronaviridae",
        order="Nidovirales",
        common_name="SARS-CoV-2 / COVID-19",
        domain="virus",
    ),
    11676: TaxonInfo(
        taxon_id=11676,
        scientific_name="Human immunodeficiency virus 1",
        rank="species",
        genus="Lentivirus",
        family="Retroviridae",
        order="Ortervirales",
        common_name="HIV-1",
        domain="virus",
    ),
    11709: TaxonInfo(
        taxon_id=11709,
        scientific_name="Human immunodeficiency virus 2",
        rank="species",
        genus="Lentivirus",
        family="Retroviridae",
        order="Ortervirales",
        common_name="HIV-2",
        domain="virus",
    ),

    # --- Priority Veterinary Pathogens ---
    10497: TaxonInfo(
        taxon_id=10497,
        scientific_name="African swine fever virus",
        rank="species",
        genus="Asfivirus",
        family="Asfarviridae",
        order="Asfuvirales",
        common_name="African swine fever virus (ASFV)",
        domain="veterinary",
    ),
    98334: TaxonInfo(
        taxon_id=98334,
        scientific_name="Peste-des-petits-ruminants virus",
        rank="species",
        genus="Morbillivirus",
        family="Paramyxoviridae",
        order="Mononegavirales",
        common_name="Peste des petits ruminants virus (PPRV)",
        domain="veterinary",
    ),
    12110: TaxonInfo(
        taxon_id=12110,
        scientific_name="Foot-and-mouth disease virus",
        rank="species",
        genus="Aphthovirus",
        family="Picornaviridae",
        order="Picornavirales",
        common_name="Foot-and-mouth disease virus (FMDV)",
        domain="veterinary",
    ),
    11292: TaxonInfo(
        taxon_id=11292,
        scientific_name="Rabies lyssavirus",
        rank="species",
        genus="Lyssavirus",
        family="Rhabdoviridae",
        order="Mononegavirales",
        common_name="Rabies virus",
        domain="veterinary",
    ),

    # --- Priority Parasites & Vectors ---
    5833: TaxonInfo(
        taxon_id=5833,
        scientific_name="Plasmodium falciparum",
        rank="species",
        genus="Plasmodium",
        family="Plasmodiidae",
        order="Haemosporida",
        common_name="Malaria parasite (falciparum)",
        domain="parasite",
    ),
    5855: TaxonInfo(
        taxon_id=5855,
        scientific_name="Plasmodium vivax",
        rank="species",
        genus="Plasmodium",
        family="Plasmodiidae",
        order="Haemosporida",
        common_name="Malaria parasite (vivax)",
        domain="parasite",
    ),
    5858: TaxonInfo(
        taxon_id=5858,
        scientific_name="Plasmodium ovale",
        rank="species",
        genus="Plasmodium",
        family="Plasmodiidae",
        order="Haemosporida",
        common_name="Malaria parasite (ovale)",
        domain="parasite",
    ),
    5850: TaxonInfo(
        taxon_id=5850,
        scientific_name="Plasmodium malariae",
        rank="species",
        genus="Plasmodium",
        family="Plasmodiidae",
        order="Haemosporida",
        common_name="Malaria parasite (malariae)",
        domain="parasite",
    ),
    5691: TaxonInfo(
        taxon_id=5691,
        scientific_name="Trypanosoma brucei",
        rank="species",
        genus="Trypanosoma",
        family="Trypanosomatidae",
        order="Trypanosomatida",
        common_name="African sleeping sickness parasite",
        domain="parasite",
    ),
    5692: TaxonInfo(
        taxon_id=5692,
        scientific_name="Trypanosoma congolense",
        rank="species",
        genus="Trypanosoma",
        family="Trypanosomatidae",
        order="Trypanosomatida",
        common_name="Nagana cattle trypanosome",
        domain="veterinary",
    ),
    5875: TaxonInfo(
        taxon_id=5875,
        scientific_name="Theileria parva",
        rank="species",
        genus="Theileria",
        family="Theileriidae",
        order="Piroplasmida",
        common_name="East Coast fever parasite",
        domain="veterinary",
    ),
    6183: TaxonInfo(
        taxon_id=6183,
        scientific_name="Schistosoma mansoni",
        rank="species",
        genus="Schistosoma",
        family="Schistosomatidae",
        order="Diplostomida",
        common_name="Intestinal schistosomiasis / Bilharzia",
        domain="parasite",
    ),
    6185: TaxonInfo(
        taxon_id=6185,
        scientific_name="Schistosoma haematobium",
        rank="species",
        genus="Schistosoma",
        family="Schistosomatidae",
        order="Diplostomida",
        common_name="Urogenital schistosomiasis / Bilharzia",
        domain="parasite",
    ),
    6282: TaxonInfo(
        taxon_id=6282,
        scientific_name="Onchocerca volvulus",
        rank="species",
        genus="Onchocerca",
        family="Onchocercidae",
        order="Rhabditida",
        common_name="River blindness parasite",
        domain="parasite",
    ),
    7165: TaxonInfo(
        taxon_id=7165,
        scientific_name="Anopheles gambiae",
        rank="species",
        genus="Anopheles",
        family="Culicidae",
        order="Diptera",
        common_name="African malaria mosquito",
        domain="parasite",
    ),
    7159: TaxonInfo(
        taxon_id=7159,
        scientific_name="Aedes aegypti",
        rank="species",
        genus="Aedes",
        family="Culicidae",
        order="Diptera",
        common_name="Yellow fever / Dengue mosquito",
        domain="parasite",
    ),
    7394: TaxonInfo(
        taxon_id=7394,
        scientific_name="Glossina morsitans",
        rank="species",
        genus="Glossina",
        family="Glossinidae",
        order="Diptera",
        common_name="Tsetse fly",
        domain="parasite",
    ),

    # --- Priority African Crops & Plant Pathogens ---
    185867: TaxonInfo(
        taxon_id=185867,
        scientific_name="Cassava mosaic Madagascar virus",
        rank="species",
        genus="Begomovirus",
        family="Geminiviridae",
        order="Geplafuvirales",
        common_name="Cassava mosaic virus",
        domain="plant",
    ),
    181163: TaxonInfo(
        taxon_id=181163,
        scientific_name="Cassava brown streak virus",
        rank="species",
        genus="Ipomovirus",
        family="Potyviridae",
        order="Picornavirales",
        common_name="Cassava brown streak virus",
        domain="plant",
    ),
    223344: TaxonInfo(
        taxon_id=223344,
        scientific_name="African cassava mosaic virus",
        rank="species",
        genus="Begomovirus",
        family="Geminiviridae",
        order="Geplafuvirales",
        common_name="African cassava mosaic virus",
        domain="plant",
    ),
    10826: TaxonInfo(
        taxon_id=10826,
        scientific_name="Maize streak virus",
        rank="species",
        genus="Mastrevirus",
        family="Geminiviridae",
        order="Geplafuvirales",
        common_name="Maize streak virus",
        domain="plant",
    ),
    5346: TaxonInfo(
        taxon_id=5346,
        scientific_name="Puccinia graminis",
        rank="species",
        genus="Puccinia",
        family="Pucciniaceae",
        order="Pucciniales",
        common_name="Wheat stem rust (Ug99)",
        domain="plant",
    ),
    3983: TaxonInfo(
        taxon_id=3983,
        scientific_name="Manihot esculenta",
        rank="species",
        genus="Manihot",
        family="Euphorbiaceae",
        order="Malpighiales",
        common_name="Cassava",
        domain="plant",
    ),
    4558: TaxonInfo(
        taxon_id=4558,
        scientific_name="Sorghum bicolor",
        rank="species",
        genus="Sorghum",
        family="Poaceae",
        order="Poales",
        common_name="Sorghum",
        domain="plant",
    ),
    4577: TaxonInfo(
        taxon_id=4577,
        scientific_name="Zea mays",
        rank="species",
        genus="Zea",
        family="Poaceae",
        order="Poales",
        common_name="Maize / Corn",
        domain="plant",
    ),
    55573: TaxonInfo(
        taxon_id=55573,
        scientific_name="Dioscorea alata",
        rank="species",
        genus="Dioscorea",
        family="Dioscoreaceae",
        order="Dioscoreales",
        common_name="White yam",
        domain="plant",
    ),
    4530: TaxonInfo(
        taxon_id=4530,
        scientific_name="Oryza glaberrima",
        rank="species",
        genus="Oryza",
        family="Poaceae",
        order="Poales",
        common_name="African rice",
        domain="plant",
    ),
    3888: TaxonInfo(
        taxon_id=3888,
        scientific_name="Vigna unguiculata",
        rank="species",
        genus="Vigna",
        family="Fabaceae",
        order="Fabales",
        common_name="Cowpea",
        domain="plant",
    ),
    4538: TaxonInfo(
        taxon_id=4538,
        scientific_name="Eragrostis tef",
        rank="species",
        genus="Eragrostis",
        family="Poaceae",
        order="Poales",
        common_name="Teff",
        domain="plant",
    ),

    # --- Strictly Prohibited Human Taxon (Catalogued for Clear Blocking & Explanations) ---
    9606: TaxonInfo(
        taxon_id=9606,
        scientific_name="Homo sapiens",
        rank="species",
        genus="Homo",
        family="Hominidae",
        order="Primates",
        common_name="Human",
        domain="human",
    ),
}


class TaxonomyService:
    """NCBI Taxonomy enrichment and suggestion service with local taxdump integration."""

    def __init__(self, taxdump_dir: Path | None = None) -> None:
        if taxdump_dir is None:
            taxdump_dir = getattr(settings, "TAXONOMY_DUMP_DIR", None)
        self.taxdump_dir = taxdump_dir
        self.taxa_cache: dict[int, TaxonInfo] = dict(KNOWN_TAXA)
        self.synonyms: dict[int, set[str]] = {}

        # Populate synonyms from KNOWN_TAXA common names
        for tid, info in self.taxa_cache.items():
            if info.common_name:
                self.synonyms.setdefault(tid, set()).add(info.common_name.lower())

        if self.taxdump_dir and self.taxdump_dir.is_dir():
            self.load_taxdump(self.taxdump_dir)

    def load_taxdump(self, taxdump_dir: Path) -> None:
        """Parse NCBI taxdump names.dmp and nodes.dmp to enrich local taxonomy cache."""
        nodes_file = taxdump_dir / "nodes.dmp"
        names_file = taxdump_dir / "names.dmp"
        if not (nodes_file.is_file() and names_file.is_file()):
            return

        # Flat file parsing for NCBI taxdump nodes.dmp
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
                if len(parts) >= 4:
                    try:
                        tid = int(parts[0])
                        name_txt = parts[1]
                        name_class = parts[3].lower()

                        if name_class == "scientific name":
                            scientific_names[tid] = name_txt
                        elif name_class in (
                            "common name",
                            "genbank common name",
                            "synonym",
                            "blast name",
                        ):
                            self.synonyms.setdefault(tid, set()).add(name_txt.lower())
                    except ValueError:
                        continue

        # Resolve genus, family, order for loaded taxa
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

            existing = self.taxa_cache.get(tid)
            common = existing.common_name if existing else None
            domain = existing.domain if existing else None

            self.taxa_cache[tid] = TaxonInfo(
                taxon_id=tid,
                scientific_name=name,
                rank=ranks.get(tid, "no rank"),
                genus=genus,
                family=family,
                order=order,
                common_name=common,
                domain=domain,
            )

    def enrich_taxon(self, taxon_id: int) -> dict[str, Any]:
        """Return taxonomic enrichment dictionary for a given taxon ID."""
        info = self.taxa_cache.get(taxon_id)
        is_prohibited = (taxon_id in PROHIBITED_TAXA) or (
            info is not None and info.scientific_name == "Homo sapiens"
        )
        if info:
            return {
                "taxon_id": info.taxon_id,
                "scientific_name": info.scientific_name,
                "common_name": info.common_name,
                "rank": info.rank,
                "genus": info.genus,
                "family": info.family,
                "order": info.order,
                "domain": info.domain,
                "is_prohibited": is_prohibited,
            }
        # Fallback if unknown
        return {
            "taxon_id": taxon_id,
            "scientific_name": f"Taxon {taxon_id}",
            "common_name": None,
            "rank": "unknown",
            "genus": None,
            "family": None,
            "order": None,
            "domain": None,
            "is_prohibited": is_prohibited,
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

    def suggest(self, query: str = "", limit: int = 10) -> list[dict[str, Any]]:
        """Search and rank taxonomy suggestions from local taxdump and curated database.

        Filters out prohibited taxa (e.g. human 9606) from default suggestions, but flags them
        with `is_prohibited=True` if specifically queried so the UI can explain the invariant.
        """
        q = query.strip().lower()
        limit = max(1, min(limit, 50))

        # Default suggestions when query is empty: prominent African pathogens and crops
        # (excluding 9606)
        if not q:
            default_tids = [
                10244,   # Monkeypox virus
                11620,   # Lassa mammarenavirus
                666,     # Vibrio cholerae
                1773,    # Mycobacterium tuberculosis
                5833,    # Plasmodium falciparum
                562,     # Escherichia coli
                28901,   # Salmonella enterica
                186538,  # Zaire ebolavirus
                11269,   # Marburg virus
                10497,   # African swine fever virus
                3983,    # Manihot esculenta (Cassava)
                4558,    # Sorghum bicolor
            ]
            results: list[dict[str, Any]] = []
            for tid in default_tids[:limit]:
                results.append(self.enrich_taxon(tid))
            return results

        matches: list[tuple[int, TaxonInfo]] = []

        is_numeric = q.isdigit()
        query_int = int(q) if is_numeric else None

        for tid, info in self.taxa_cache.items():
            score = 0
            s_name = info.scientific_name.lower()
            c_name = info.common_name.lower() if info.common_name else ""
            genus = info.genus.lower() if info.genus else ""
            family = info.family.lower() if info.family else ""
            syns = self.synonyms.get(tid, set())

            # 1. Taxon ID matching
            if is_numeric and query_int is not None:
                if tid == query_int:
                    score = 200
                elif str(tid).startswith(q):
                    score = 120
                elif q in str(tid):
                    score = 80

            # 2. Exact name matches
            elif s_name == q or c_name == q:
                score = 150
            # 3. Starts with query
            elif s_name.startswith(q):
                score = 100
            elif c_name.startswith(q):
                score = 90
            elif genus.startswith(q):
                score = 80
            # 4. Word boundary match
            elif any(word.startswith(q) for word in s_name.split()):
                score = 75
            elif any(word.startswith(q) for word in c_name.split()):
                score = 70
            # 5. Synonym match
            elif any(syn.startswith(q) or q in syn for syn in syns):
                score = 65
            # 6. Substring match
            elif q in s_name:
                score = 50
            elif q in c_name:
                score = 45
            elif q in genus or q in family:
                score = 40

            if score > 0:
                # Rank species higher than genus or higher ranks when tied
                if info.rank == "species":
                    score += 5
                matches.append((score, info))

        # Sort matches by score descending, then scientific name ascending
        matches.sort(key=lambda item: (-item[0], item[1].scientific_name))

        suggestions: list[dict[str, Any]] = []
        for _, info in matches[:limit]:
            suggestions.append(self.enrich_taxon(info.taxon_id))

        return suggestions


taxonomy_service = TaxonomyService()

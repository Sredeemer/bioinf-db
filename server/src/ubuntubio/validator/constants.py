"""Domain constants for UbuntuBio metadata validation."""

from typing import Final

# 54 African Union (AU) member states (ISO-3166-1 alpha-2)
AU_COUNTRY_CODES: Final[frozenset[str]] = frozenset(
    {
        "DZ",  # Algeria
        "AO",  # Angola
        "BJ",  # Benin
        "BW",  # Botswana
        "BF",  # Burkina Faso
        "BI",  # Burundi
        "CV",  # Cabo Verde
        "CM",  # Cameroon
        "CF",  # Central African Republic
        "TD",  # Chad
        "KM",  # Comoros
        "CG",  # Congo
        "CD",  # Democratic Republic of the Congo
        "CI",  # Côte d'Ivoire
        "DJ",  # Djibouti
        "EG",  # Egypt
        "GQ",  # Equatorial Guinea
        "ER",  # Eritrea
        "SZ",  # Eswatini
        "ET",  # Ethiopia
        "GA",  # Gabon
        "GM",  # Gambia
        "GH",  # Ghana
        "GN",  # Guinea
        "GW",  # Guinea-Bissau
        "KE",  # Kenya
        "LS",  # Lesotho
        "LR",  # Liberia
        "LY",  # Libya
        "MG",  # Madagascar
        "MW",  # Malawi
        "ML",  # Mali
        "MR",  # Mauritania
        "MU",  # Mauritius
        "MA",  # Morocco
        "MZ",  # Mozambique
        "NA",  # Namibia
        "NE",  # Niger
        "NG",  # Nigeria
        "RW",  # Rwanda
        "ST",  # Sao Tome and Principe
        "SN",  # Senegal
        "SC",  # Seychelles
        "SL",  # Sierra Leone
        "SO",  # Somalia
        "ZA",  # South Africa
        "SS",  # South Sudan
        "SD",  # Sudan
        "TZ",  # Tanzania
        "TG",  # Togo
        "TN",  # Tunisia
        "UG",  # Uganda
        "ZM",  # Zambia
        "ZW",  # Zimbabwe
    }
)

# Strictly prohibited taxa (human genomic data is forbidden in v1)
PROHIBITED_TAXA: Final[frozenset[int]] = frozenset(
    {
        9606,  # Homo sapiens
    }
)

# Valid scientific domains
VALID_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "bacteria",
        "virus",
        "veterinary",
        "plant",
        "parasite",
        "metagenome",
    }
)

# Access control tiers
VALID_ACCESS_TIERS: Final[frozenset[str]] = frozenset(
    {
        "public",
        "gated",
        "private",
    }
)

# Approximate geographical bounding box for the African continental plate & islands
AFRICA_LAT_MIN: Final[float] = -35.5
AFRICA_LAT_MAX: Final[float] = 38.0
AFRICA_LON_MIN: Final[float] = -26.0
AFRICA_LON_MAX: Final[float] = 52.0

# Mandatory columns for samples.tsv
MANDATORY_SAMPLE_COLUMNS: Final[tuple[str, ...]] = (
    "sample_id",
    "taxon_id",
    "country",
    "collection_date",
    "lat",
    "lon",
    "admin1",
    "host",
    "isolation_source",
)

# Mandatory columns for remote_files.tsv
MANDATORY_REMOTE_FILE_COLUMNS: Final[tuple[str, ...]] = (
    "filename",
    "url",
    "md5",
    "size_bytes",
)

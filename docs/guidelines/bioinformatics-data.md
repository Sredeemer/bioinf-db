# Bioinformatics Data & Governance Standards

This document establishes the scientific data integrity standards, metadata schemas, African data sovereignty policies, and verification criteria for datasets hosted on the hub.

---

## 1. Scope & Targeted Biological Domains

The hub exclusively stores and indexes **African bioinformatics datasets** across six primary scientific domains:

1. **Bacterial Pathogens & Antimicrobial Resistance (AMR)**: (e.g., *Klebsiella pneumoniae*, *Salmonella enterica*, *Mycobacterium tuberculosis*, *Vibrio cholerae*, *Escherichia coli*).
2. **Viruses of Public Health Concern**: (e.g., Lassa virus, Ebola virus, Mpox, Dengue, Rift Valley fever virus, HIV, SARS-CoV-2 from African clinical/surveillance isolates).
3. **Veterinary & One Health**: (e.g., African Swine Fever [ASFV], Peste des Petits Ruminants [PPR], Foot-and-Mouth Disease [FMD], zoonotic pathogens).
4. **Plant Pathogens & Agricultural Genomics**: (e.g., Cassava mosaic virus, Wheat stem rust [*Puccinia graminis*], maize lethal necrosis).
5. **Parasitic Diseases**: (e.g., *Plasmodium falciparum*, *Trypanosoma brucei*).
6. **Environmental & Metagenomics**: (e.g., soil, water, and livestock microbiomes collected within the African continent).

---

## 2. Strict Prohibition: Human Genomic Data

> [!CAUTION]
> **Human genomic data (NCBI Taxon ID 9606) is strictly prohibited in v1.**
> The hub does not currently possess the specialized HIPAA/GDPR clinical consent verification and managed-access infrastructure required for human germline or somatic genomic sequencing.

- The metadata validator rejects any push containing `taxon_ids: [9606]` or individual sample rows with human taxonomy.
- If a dataset studies human-associated pathogens, the taxon ID must represent the **pathogen** (e.g. `562` for *E. coli*, `666` for *V. cholerae*, `1773` for *M. tuberculosis*), and the `host` column must record human status (`Homo sapiens` or Taxon `9606`).
- **Self-Hosted NCBI Taxonomy Suggestion Service**: The hub exposes an air-gapped, sovereign suggestion service (`GET /api/v1/taxonomy/suggest` and `GET /api/v1/taxonomy/{taxon_id}`) backed by local NCBI taxdump flat files under `/srv/ubuntubio/data/taxonomy/` (`names.dmp`, `nodes.dmp`), completely eliminating external third-party calls to NCBI.

---

## 3. Geographic Boundary & African Union Country Validation

To maintain the hub's mission, every dataset must originate from the African continent.

### Country Code Requirements
- The `countries` list in `README.md` and the `country` column in `samples.tsv` must use **ISO-3166-1 alpha-2** country codes.
- Every code must belong to the **54 African Union (AU) member states**:
  ```text
  DZ, AO, BJ, BW, BF, BI, CV, CM, CF, TD, KM, CG, CD, CI, DJ,
  EG, GQ, ER, SZ, ET, GA, GM, GH, GN, GW, KE, LS, LR, LY, MG,
  MW, ML, MR, MU, MA, MZ, NA, NE, NG, RW, ST, SN, SC, SL, SO,
  ZA, SS, SD, TZ, TG, TN, UG, ZM, ZW
  ```
- Any non-African country code triggers an automatic validation rejection.

### Geospatial Coordinates
- Sample coordinates (`lat`, `lon`) must fall within the continental African landmass and associated island states (approximate bounding box: Latitude `[-35.0, 38.0]`, Longitude `[-26.0, 52.0]`).
- Future releases will enforce strict point-in-polygon checks against Natural Earth African boundary shapefiles.

---

## 4. Metadata Schema: MIxS Compliance

Every repository must contain:
1. `README.md` with YAML front-matter.
2. `samples.tsv` tab-separated file with record-level metadata.

### `README.md` Front-Matter Specification
```yaml
---
title: Klebsiella pneumoniae isolates from clinical surveillance in Lagos
domain: bacteria
license: cc-by-4.0
access: public # public | gated | private
countries: [NG]
taxon_ids: [573]
data_types: [assembly, reads]
source:
  ena_project: PRJEB12345
  publication_doi: 10.1016/j.ebiom.2023.104567
benefit_sharing: "Commercial use requires prior notification and data-transfer agreement with submitting consortium."
---
```

### `samples.tsv` Minimum Information (MIxS Subset)
The file must be tab-delimited (`\t`), UTF-8 encoded, and contain the following mandatory columns:

| Column | Type | Example | Description |
|---|---|---|---|
| `sample_id` | String | `SAMN12345678` | Unique sample identifier within this repository |
| `taxon_id` | Integer | `573` | NCBI Taxonomy ID for the organism |
| `country` | String (ISO-2) | `NG` | Country of isolation/collection |
| `collection_date`| String (ISO-8601)| `2023-05-14` | Date of collection (`YYYY-MM-DD` or `YYYY-MM`) |
| `lat` | Float (or empty) | `6.5244` | Decimal latitude (WGS84) |
| `lon` | Float (or empty) | `3.3792` | Decimal longitude (WGS84) |
| `admin1` | String (or empty) | `Lagos State` | State / Region / Province |
| `host` | String | `Homo sapiens` | Host organism or environment |
| `isolation_source`| String | `blood` | Anatomical site or environmental matrix |

*Optional recommended columns:* `amr_genotypes`, `lineage`, `serotype`, `sequencing_platform`, `bio_sample_accession`.

---

## 5. File Integrity & Tri-Level Hashing

Integrity verification is enforced across three distinct hashing mechanisms:

1. **SHA-256**: Calculated for Git LFS pointers and local client verification (`ubio download`).
2. **Blake3**: Calculated across content-defined chunks (Gearhash 64 KiB CDC) in the OpenXet CAS layer for global deduplication.
3. **MD5**: Stored in `remote_files.tsv` for linked raw sequencing reads hosted on external FTP/HTTP mirrors (e.g., ENA FASTQ runs):
   ```tsv
   filename	url	md5	size_bytes
   reads/ERR123_1.fastq.gz	ftp://ftp.sra.ebi.ac.uk/vol1/fastq/ERR123/ERR123_1.fastq.gz	d41d8cd98f00b204e9800998ecf8427e	245892104
   ```

---

## 6. Data Ingestion Pathways & Sizing Tiers

To accommodate varying institutional compute infrastructure and internet connectivity across African research centers, the hub enforces a dual-path ingestion architecture:

### Web Browser Ingestion (Cohorts &le; 500 MB)
- **Compulsory File Upload**: In web submission mode, researchers must select/drop at least one sequence read file (`.fastq.gz`, `.fasta.gz`, `.bam`, `.cram`).
- **Zero-Network Client-Side Preflight**: Uses Web Streams to decompress the first 64 KB locally, verifying record integrity, Phred quality scores, and enforcing zero human contamination (rejection of NCBI Taxon ID 9606).
- **Progress Tracking**: Real-time multi-stage streaming progress indicator showing CAS chunking, hashing, and Git tree registration.
- **Size Limit**: Hard-capped at 500 MB to prevent browser memory exhaustion, connection timeouts, and upload aborts over high-latency networks.

### Command-Line Ingestion (`ubio push`) (Cohorts &gt; 500 MB)
- **High-Throughput & HPC Support**: Mandatory for large whole-genome sequencing (WGS), metagenomic cohorts, and automated sequencing facility drops.
- **OpenXet Content-Addressed Storage (CAS)**: Uses Gearhash content-defined chunking (64 KiB CDC) and Blake3 deduplication to minimize network payload.
- **Resumable Transfers**: Uninterrupted recovery from intermittent connection failures.
- **HPC Cluster Declaration**: The web wizard allows researchers to pre-register metadata manifests for remote files and generates the exact `ubio push` command to execute directly on institutional compute clusters.

---

## 7. African Data Sovereignty & Nagoya Protocol Alignment

To counteract historical "helicopter research" and respect the **Nagoya Protocol on Access to Genetic Resources and Benefit-Sharing**:

1. **Data Provenance**: Datasets must credit the African researchers, institutes, and sample collectors who originated the biological samples.
2. **Access Tiers**:
   - **Public**: Open science download without restriction.
   - **Gated**: Users must authenticate via ORCID, accept the dataset's specific Data Use Agreement (DUA) and benefit-sharing terms, and receive explicit repository owner approval before download tokens are minted.
   - **Private**: Restricted exclusively to organization members.
3. **Audit Trails**: All gated access requests and downloads are recorded in an immutable audit log, enabling African institutions to track and report downstream utilization of their genomic data assets.

---

## 8. "Verified African" Badge Criteria

Datasets exhibiting high scientific and metadata quality may be awarded the **"Verified African"** badge by a hub curator. Criteria include:
- [ ] Confirmed biological collection site within the 54 AU member states.
- [ ] Direct institutional affiliation of the submitter or lead author with an African research body, university, or national public health institute (NPHI).
- [ ] Complete MIxS metadata table with valid dates, geolocation, and host information.
- [ ] Verified checksum integrity for all assemblies and read manifests.

# UbuntuBio Curation Pipelines (`/curation`)

Automated and AI-augmented dataset curation for African bioinformatics.

## Components
1. **Deterministic Harvesters**:
   - `ena/`: ENA Portal API client harvesting public African projects across AU member states.
   - `ncbi/`: NCBI Datasets client for downloading reference and isolate assemblies.
2. **Deep Agents (M6)**:
   - `agents/`: LangChain Deep Agents for metadata entity extraction, geographic resolution (Nominatim), and "Verified African" badge evidence reporting.
   - `eval/`: Gold standard evaluation datasets and regression suites.

## Directory Structure
```text
curation/
├── configs/          # YAML domain configs (taxa, filtering parameters)
├── harvesters/       # Deterministic API crawlers (ENA, NCBI)
├── agents/           # LangChain Deep Agent workflows (M6)
└── tests/            # Curation tests and recorded fixtures (vcrpy)
```

# Contributing to the African Bioinformatics Data Hub

Welcome! We are building open-source data infrastructure for African bioinformatics, enabling researchers, public health institutes, and consortia to publish, version, discover, and stream genomic datasets with chunk-level deduplication.

Whether you are fixing a typo, improving metadata validation, writing harvesters for pathogen data, or enhancing the Next.js frontend, thank you for contributing.

---

## Code of Conduct

All contributors are expected to uphold the [Code of Conduct](CODE_OF_CONDUCT.md). Please report any violations to maintainers promptly.

---

## Getting Started

### 1. Monorepo Organization

The project is structured logically across core packages and components:

```text
bioinf-db/
├── server/           # FastAPI backend hub, Git Smart-HTTP, LFS bridge, CAS token issuer
├── web/              # Next.js 15+ App Router web frontend & MapLibre visualization
├── xet/              # Pinned OpenXet Rust CAS server integration
├── curation/         # ENA / NCBI harvesters and LangChain Deep Agent workflows
├── deploy/           # Docker Compose single-folder deployment and Caddy configs
├── docs/             # Architecture decision records (ADRs) and engineering guidelines
│   └── guidelines/   # Coding standards for Python, TypeScript, Rust, Git, and Bio Data
└── .agents/          # AI agent workspace rules and workflow specifications
```

*(Note: The Python client library `afrihub` lives in a companion repository published to PyPI, following identical Python and Git standards).*

### 2. Local Environment Requirements

- **Git** with `git-lfs` installed
- **Docker** and **Docker Compose** (v2+)
- **Python 3.12+** (managed via `uv` or `pyenv`)
- **Node.js 20+ LTS** (or `bun`)
- **Rust 1.80+ stable** (with `cargo` and `rustfmt`)
- **pre-commit** (`pip install pre-commit && pre-commit install`)

---

## Coding Standards & Guidelines

Before writing code, please review the dedicated guidelines in [`docs/guidelines/`](docs/guidelines/):

- **[General Software Engineering Standards](docs/guidelines/software-engineering.md)**: Clean architecture, SOLID, error handling, defensive programming.
- **[Python Standards](docs/guidelines/python.md)**: Python 3.12+, Ruff, strict Mypy, Pydantic v2, FastAPI async conventions, and Pytest.
- **[TypeScript & Next.js Standards](docs/guidelines/typescript.md)**: Next.js App Router, React Server/Client Components, Vanilla CSS design tokens, WCAG 2.1 AA a11y.
- **[Rust Standards](docs/guidelines/rust.md)**: Idiomatic Rust, Clippy strictness, `thiserror`/`anyhow`, async Tokio/Axum patterns, CAS memory safety.
- **[Git & Commit Conventions](docs/guidelines/git-and-commits.md)**: Conventional Commits 1.0.0, branch naming, and semantic versioning.
- **[Bioinformatics Data & Governance](docs/guidelines/bioinformatics-data.md)**: FAIR data principles, MIxS metadata requirements, African regional validation, and Nagoya Protocol benefit-sharing terms.

---

## Contribution Workflow

### Step 1: Issue First
Before beginning work on major features or architectural changes, open an issue to discuss your proposal. For small bug fixes and documentation improvements, feel free to submit a pull request directly.

### Step 2: Branch Naming
Create a feature branch from `main`:
- `feat/dataset-map-clustering`
- `fix/ena-harvest-date-parse`
- `docs/add-api-tokens-guide`
- `refactor/cas-token-claims`
- `test/validator-fuzz-tests`

### Step 3: Conventional Commit Messages
Commit messages **MUST** follow the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/) specification:

```text
feat(validator): add validation for AU country ISO-3166 codes
fix(lfs): prevent premature closing of CAS chunk streams
docs(guidelines): add Rust unsafe and FFI standards
test(api): add table-driven authorization tests for gated datasets
```

Breaking changes must include `!` or a `BREAKING CHANGE:` footer.

### Step 4: Pre-Commit Checks & Tests
Always run formatting, linting, and tests locally before pushing:

```bash
# Run pre-commit hooks across all staged files
pre-commit run --all-files

# Backend tests
cd server && uv run pytest

# Frontend tests & lint
cd web && npm run lint && npm test

# Rust tests & clippy
cd xet && cargo fmt --check && cargo clippy --all-targets -- -D warnings
```

### Step 5: Submitting a Pull Request
1. Open a PR against `main`.
2. Fill out the PR template with:
   - Summary of changes and rationale
   - Related issue number (`Closes #123`)
   - Test results (unit, integration, or manual verification steps)
   - Screenshots or terminal outputs for visual or CLI modifications
3. Ensure CI passes on all jobs.
4. Address review comments respectfully and squash fixup commits if requested.

---

## Definition of Done (DoD)

A PR is ready to merge only when:
- [ ] Code adheres to the respective language guidelines in `docs/guidelines/`
- [ ] Automated tests cover all newly added paths and edge cases
- [ ] Linting and type checks pass with zero warnings (`ruff`, `mypy --strict`, `eslint`, `cargo clippy`)
- [ ] Documentation and API schemas (`docs/`, docstrings, OpenAPI) are updated
- [ ] No secrets or sensitive test fixtures are committed
- [ ] At least one maintainer has reviewed and approved the pull request

---

## Licensing & Developer Certificate of Origin (DCO)

All contributions to this repository are released under the terms of the project's open-source licenses:
- Code files are licensed under **MIT** or **Apache-2.0** as indicated in the headers and the repository [LICENSE](LICENSE).
- By submitting a pull request, you certify that you wrote the code or have the right to submit it under the project's open-source licenses.

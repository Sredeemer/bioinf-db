# AI Coding Agent Instructions & Repository Rules

This file provides system instructions and architectural invariants for AI coding assistants (including Antigravity, Cursor, Copilot, and subagents) operating in this repository.

---

## 1. Non-Negotiable Core Rules

1. **Adhere to the Engineering Guidelines**: All generated code, tests, and configurations must strictly follow the guidelines located in [`docs/guidelines/`](docs/guidelines/):
   - [`software-engineering.md`](docs/guidelines/software-engineering.md) (Architecture, Clean Code, Error Handling)
   - [`python.md`](docs/guidelines/python.md) (Python 3.12+, Ruff, strict Mypy, Pydantic v2, FastAPI)
   - [`typescript.md`](docs/guidelines/typescript.md) (TypeScript strict, Next.js App Router, Vanilla CSS, a11y)
   - [`rust.md`](docs/guidelines/rust.md) (Rust 2021, Clippy strict, thiserror/anyhow, memory safety)
   - [`git-and-commits.md`](docs/guidelines/git-and-commits.md) (Conventional Commits 1.0.0, branch conventions)
   - [`bioinformatics-data.md`](docs/guidelines/bioinformatics-data.md) (MIxS metadata, AU country validation, no human data)

2. **Open-Source Only**:
   - Never introduce proprietary software dependencies, closed API services, or commercial cloud-vendor lock-in.
   - Valkey instead of proprietary Redis features.
   - MapLibre GL + self-hosted PMTiles instead of Mapbox.
   - Langfuse (self-hosted) instead of LangSmith.
   - Self-hosted open-weight LLMs (vLLM / Ollama) instead of closed commercial APIs.

3. **Storage & Single-Folder Architecture**:
   - All state in v1 must reside under the single root directory `/srv/afrihub/data/` (with subdirectories `xet/`, `git/`, `postgres/`, `meili/`, `tmp/`).
   - Do not write scattered runtime state across arbitrary host paths.

4. **Security & Authorization Invariants**:
   - Access control checks must never be bypassed.
   - Never mint CAS read tokens or presigned URLs for Gated or Private datasets without explicit, verified authorization.
   - Never commit secrets, tokens, or private keys to the repository.

5. **Test-Driven & Verification Obligation**:
   - Never claim a task or feature is complete without adding corresponding tests.
   - Run the respective test runner before declaring success:
     - Python: `pytest`
     - TypeScript: `npm test` or `vitest`
     - Rust: `cargo test` and `cargo clippy -- -D warnings`

6. **Bioinformatics Domain Constraints**:
   - **Strict prohibition**: Human genomic data (NCBI Taxon ID 9606) is prohibited in v1. Always enforce this in validation logic.
   - **African Union Member States**: Only the 54 AU member state ISO-3166-1 alpha-2 country codes are permitted.

# Repository Coding Standards & Architectural Invariants

Refer to [docs/guidelines/](file:///Users/redeemersalamiokekale/Desktop/Workspace/bioinf-db/docs/guidelines/) for full specifications.

## Key Directives:
1. **Open-Source Only**: Strictly open-source packages (Valkey, MapLibre GL, Langfuse, OpenXet, FastAPI, Next.js).
2. **Single-Folder Storage**: All local data state under `/srv/afrihub/data/` (`xet/`, `git/`, `postgres/`, `meili/`).
3. **Language Rules**:
   - Python: Python 3.12+, Ruff, strict Mypy, Pydantic v2, async FastAPI, Pytest.
   - TypeScript: Strict TS, Next.js App Router (RSC by default), Vanilla CSS design tokens, WCAG 2.1 AA a11y.
   - Rust: Rust 2021, Clippy strict (`-D warnings`), thiserror/anyhow, safe async with Tokio/Axum.
4. **Commits**: Conventional Commits 1.0.0 (`feat:`, `fix:`, `docs:`, etc.).
5. **Domain Invariants**:
   - African Union 54 member states only (ISO-3166-1 alpha-2).
   - Human genomic data (Taxon ID 9606) strictly prohibited in v1.
   - Deny by default for Gated and Private datasets.

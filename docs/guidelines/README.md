# Engineering Guidelines & Standards

This directory contains the engineering standards, architecture rules, and coding conventions for the African Bioinformatics Data Hub project. All contributors (human developers and AI coding agents) are expected to adhere to these rules across every pull request.

---

## Directory Index

| Document | Target Area | Core Standards Enforced |
|---|---|---|
| **[Software Engineering Handbook](software-engineering.md)** | All components | SOLID principles, Clean Architecture, defensive coding, error handling, logging, testing pyramid, API contract design |
| **[Python Coding Standards](python.md)** | `server/`, `curation/`, `client-py/` | Python 3.12+, Ruff, strict Mypy, Pydantic v2, FastAPI async patterns, Pytest conventions |
| **[TypeScript & Frontend Standards](typescript.md)** | `web/` | Next.js 15+ App Router, React 19, strict TypeScript, Vanilla CSS design tokens, WCAG 2.1 AA accessibility |
| **[Rust Coding Standards](rust.md)** | `xet/` | Rust 2021/2024, Clippy lints (`-D warnings`), `thiserror`/`anyhow`, Tokio/Axum async, CAS streaming & safety |
| **[Git & Commit Conventions](git-and-commits.md)** | Version control & CI | Conventional Commits 1.0.0, branch naming strategy, PR descriptions, SemVer 2.0.0 |
| **[Bioinformatics Data & Governance](bioinformatics-data.md)** | Dataset curation & validation | FAIR data principles, MIxS metadata schema, African Union country filtering, human genome rejection, Nagoya Protocol compliance |

---

## Quick Reference: Toolchain & Enforcement

| Language / Area | Formatter | Linter | Type Checker | Test Runner |
|---|---|---|---|---|
| **Python** | `ruff format` | `ruff check` | `mypy --strict` | `pytest` |
| **TypeScript** | `prettier` / `eslint` | `eslint` | `tsc --noEmit` | `vitest` / `playwright` |
| **Rust** | `cargo fmt` | `cargo clippy -- -D warnings` | `cargo check` | `cargo test` |
| **Markdown / Docs** | `markdownlint` | `markdownlint` | N/A | Link verification |
| **Git Commits** | `commitlint` | `commitlint` | N/A | Conventional Commit check in CI |

---

## AI Assistant Compliance

If you are an AI coding assistant (Antigravity, Cursor, Copilot, etc.), you **MUST** consult these files before proposing or writing code. Summarized instructions for AI agents are defined in the root **[`AGENTS.md`](../../AGENTS.md)**.

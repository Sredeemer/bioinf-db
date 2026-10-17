# Git & Commit Conventions

This document specifies our version control workflows, branch naming conventions, Conventional Commit standards, and pull request review policies.

---

## 1. Branch Strategy (Trunk-Based Development)

We practice trunk-based development with short-lived feature branches merged into `main` through pull requests.

### Branch Naming Convention
Branches must be named using the pattern:
```text
<type>/<kebab-case-short-description>
```

| Type | Purpose | Example |
|---|---|---|
| `feat/` | New user-facing feature or API capability | `feat/cas-token-claims` |
| `fix/` | Bug fix in server, web, client, or worker | `fix/tsv-date-parsing` |
| `refactor/` | Code refactoring without changing behavior | `refactor/extract-authz-matrix` |
| `perf/` | Performance optimization | `perf/meilisearch-facet-caching` |
| `test/` | Adding or improving tests | `test/validator-fuzz-suite` |
| `docs/` | Documentation additions or edits | `docs/architecture-overview` |
| `ci/` | CI/CD pipeline or GitHub Actions changes | `ci/add-cargo-clippy-job` |
| `chore/` | Dependency upgrades, tooling configurations | `chore/update-pydantic-v2` |

---

## 2. Conventional Commits 1.0.0 Specification

All commit messages **MUST** adhere to the [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) standard. This allows automated changelog generation and deterministic semantic versioning.

### Commit Format
```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Approved Commit Types
- **`feat`**: A new feature (correlates with `MINOR` in SemVer).
- **`fix`**: A bug fix (correlates with `PATCH` in SemVer).
- **`docs`**: Documentation only changes.
- **`style`**: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons).
- **`refactor`**: A code change that neither fixes a bug nor adds a feature.
- **`perf`**: A code change that improves performance.
- **`test`**: Adding missing tests or correcting existing tests.
- **`build`**: Changes that affect the build system or external dependencies (e.g., Cargo, uv, npm).
- **`ci`**: Changes to our CI configuration files and scripts.
- **`chore`**: Maintenance tasks that do not modify `src` or test files.

### Standard Scopes
Scopes must specify the component or subsystem affected:
- `(server)`: FastAPI backend hub
- `(web)`: Next.js frontend
- `(client)`: Python PyPI client (`afrihub`)
- `(xet)`: OpenXet CAS server and Rust crates
- `(curation)`: ENA / NCBI harvesters and dataset seed scripts
- `(agents)`: LangChain Deep Agents workflows
- `(validator)`: Metadata card and TSV validation schemas
- `(auth)`: ORCID login, PATs, and CAS token signing
- `(deploy)`: Docker compose, Caddy, and cluster infrastructure

### Breaking Changes
Indicate breaking changes with a `!` after the type/scope and an explicit `BREAKING CHANGE:` footer:
```text
feat(api)!: require repository ID in CAS token claims

BREAKING CHANGE: CAS write tokens now require an explicit `repo_id` claim.
Old client versions prior to v0.2.0 must upgrade.
```

### Subject Line Rules
1. **Imperative mood**: Use "add", "fix", "change", not "added", "fixes", "changing".
2. **Lowercase start**: Do not capitalize the first letter after the colon.
3. **No trailing period**: Keep the subject clean and concise.
4. **Length limit**: Maximum 72 characters for the subject line.

---

## 3. Pull Request Guidelines

### Structure of a Good PR
- **Single Concern**: A PR should address one issue or logical change. Avoid combining unrelated fixes into a feature branch.
- **Size**: Aim for PRs under 400 lines of diff (excluding generated lockfiles or test data fixtures). Smaller PRs are reviewed faster and merge with fewer conflicts.
- **Title**: The PR title must also follow the Conventional Commit format (e.g., `feat(web): add interactive Africa cluster map`).

### PR Description Template
```markdown
## Summary
Brief explanation of what this change does and why it is needed.

## Changes
- Added X to component Y
- Refactored Z for performance

## Related Issues
Closes #123

## Test Plan
- [x] Unit tests added in `server/tests/...`
- [x] Integration test verified against local Docker Compose
- [x] Manual verification: pushed test Klebsiella dataset and verified map pin
```

---

## 4. Semantic Versioning (SemVer 2.0.0)

All published packages (especially the PyPI client `afrihub`) follow strict Semantic Versioning (`MAJOR.MINOR.PATCH`):

- **MAJOR** (`X.0.0`): Incompatible API changes, modified wire protocols, or schema-breaking changes.
- **MINOR** (`0.X.0`): Backwards-compatible new functionality (new CLI commands, additional search filters, new dataset card fields).
- **PATCH** (`0.0.X`): Backwards-compatible bug fixes and security patches.

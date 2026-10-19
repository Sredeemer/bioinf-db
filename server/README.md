# UbuntuBio Server (`/server`)

FastAPI backend hub for UbuntuBio, providing:
- Dataset repository management and authorization
- Git Smart-HTTP proxy and LFS bridge
- CAS JWT token issuer for OpenXet (OIDC/JWKS)
- MIxS metadata validation (`README.md`, `samples.tsv`, `remote_files.tsv`)
- Meilisearch synchronization and search APIs

## Development Setup

```bash
# Sync virtualenv using Python 3.12 via uv
uv sync --all-extras

# Run tests
uv run pytest

# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src tests
```

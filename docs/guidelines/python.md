# Python Coding Standards

This guide defines the Python standards for all backend services (`/server`), CLI & client libraries (`/client-py`), and data curation pipelines (`/curation`).

---

## 1. Environment & Language Version

- **Target Version**: **Python 3.12+** (incorporates modern type parameter syntax [PEP 695], type unions `X | Y`, and performance improvements).
- **Package & Environment Manager**: **[`uv`](https://github.com/astral-sh/uv)** is the preferred tool for virtual environments and dependency locking.
- **Dependency Specification**: All dependencies must be pinned via `pyproject.toml` with strict lockfiles (`uv.lock`).

---

## 2. Formatting, Linting & Type Checking

### Toolchain
- **Formatter & Linter**: **[`Ruff`](https://docs.astral.sh/ruff/)** handles formatting, import sorting, and linting in one fast pass.
- **Static Type Checker**: **[`Mypy`](https://mypy.readthedocs.io/)** configured in **strict mode** (`--strict`).

### Ruff Configuration Guidelines
Add to `pyproject.toml`:
```toml
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort (import sorting)
    "B",    # flake8-bugbear (common bug patterns)
    "UP",   # pyupgrade (enforce modern Python 3.12 syntax)
    "S",    # flake8-bandit (security checks)
    "C4",   # flake8-comprehensions
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "RUF",  # Ruff-specific rules
]
ignore = [
    "S101", # Allow assert in tests
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### Strict Type Annotations
Every public and private function, method, and class attribute must be explicitly typed. Untyped code will fail CI:

```python
# Bad
def calculate_checksum(path, chunk_size=65536):
    ...

# Good
from pathlib import Path

def calculate_checksum(file_path: Path, chunk_size: int = 65_536) -> str:
    ...
```

---

## 3. FastAPI & Async Engineering Standards

### Async vs. Sync Route Execution
- **Use `async def`** **ONLY** when awaiting non-blocking asynchronous calls (e.g., `await db.execute()`, `await http_client.get()`).
- **Use standard `def`** for blocking, CPU-bound, or synchronous operations (e.g., `pygit2` repository actions, disk reads, CPU hashing). FastAPI automatically runs standard `def` routes in an external threadpool, preventing the main event loop from stalling.

```python
# Good: Async IO
@router.get("/repos/{owner}/{name}", response_model=RepoResponse)
async def get_repo(
    owner: str,
    name: str,
    db: AsyncSession = Depends(get_db_session),
    current_user: User | None = Depends(get_optional_user),
) -> RepoResponse:
    repo = await repo_service.get_by_slug(db, owner, name)
    ...

# Good: Synchronous disk / git operations
@router.post("/repos/{owner}/{name}/smart-http")
def git_smart_http_backend(
    owner: str,
    name: str,
    request: Request,
) -> StreamingResponse:
    # pygit2 / git http-backend calls run in worker thread
    return git_service.handle_smart_http(owner, name, request)
```

### Dependency Injection (DI)
Never instantiate database sessions, configuration objects, or authorization checkers globally inside routes. Use FastAPI's `Depends`:

```python
async def require_repo_writer(
    repo: Repo = Depends(get_target_repo),
    user: User = Depends(require_authenticated_user),
    authz: AuthService = Depends(get_auth_service),
) -> Repo:
    if not authz.can_write_repo(user, repo):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required for this repository.",
        )
    return repo
```

---

## 4. Pydantic v2 Schema Design

- Use `model_config = ConfigDict(strict=True)` to reject silent type coercions.
- Use `ConfigDict(frozen=True)` for domain models and value objects to enforce immutability.
- Use explicit field validators (`@field_validator`) for scientific business rules:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class DatasetFrontmatter(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    title: str = Field(..., min_length=5, max_length=120)
    domain: str
    countries: list[str] = Field(..., min_length=1)
    taxon_ids: list[int] = Field(..., min_length=1)
    license: str

    @field_validator("countries")
    @classmethod
    def validate_african_countries(cls, v: list[str]) -> list[str]:
        invalid = [c for c in v if c not in AU_COUNTRY_CODES]
        if invalid:
            raise ValueError(
                f"Countries must belong to African Union member states. Invalid codes: {invalid}"
            )
        return v

    @field_validator("taxon_ids")
    @classmethod
    def reject_human_taxa(cls, v: list[int]) -> list[int]:
        if 9606 in v:
            raise ValueError("Human genomic data (Taxon ID 9606) is prohibited in v1.")
        return v
```

---

## 5. SQLAlchemy 2.0+ Persistence Patterns

- Always use the modern 2.0 declarative style with `Mapped[...]` and `mapped_column(...)`.
- Always specify relationship loading explicitly (`selectinload` or `joinedload`) to prevent async lazy-loading greenlet errors.

```python
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class RepositoryModel(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    owner: Mapped["UserModel"] = relationship(back_populates="repositories")
```

---

## 6. Testing with Pytest

- **Async Support**: Use `pytest-asyncio` with `asyncio_mode = "auto"`.
- **Table-Driven Tests**: Use `@pytest.mark.parametrize` for clean input-output matrix verification:

```python
import pytest

@pytest.mark.parametrize(
    ("countries", "expected_valid"),
    [
        (["NG", "KE", "ZA"], True),
        (["EG"], True),
        (["US"], False),
        (["NG", "GB"], False),
        ([], False),
    ],
)
def test_african_country_validation(countries: list[str], expected_valid: bool) -> None:
    if expected_valid:
        schema = DatasetFrontmatter(
            title="Valid Title",
            domain="bacteria",
            countries=countries,
            taxon_ids=[573],
            license="cc-by-4.0",
        )
        assert schema.countries == countries
    else:
        with pytest.raises(ValueError):
            DatasetFrontmatter(
                title="Valid Title",
                domain="bacteria",
                countries=countries,
                taxon_ids=[573],
                license="cc-by-4.0",
            )
```

- **File Path Handling**: Always use `pathlib.Path`, never string operations (`os.path.join`).
- **No Leftover State**: Pytest fixtures creating test repositories or temporary directories must yield the resource and clean up unconditionally in a `finally` block or use pytest's `tmp_path`.

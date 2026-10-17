# Software Engineering Handbook

This handbook defines the foundational software engineering principles, design patterns, testing standards, and operational guidelines observed across all services in the African Bioinformatics Data Hub.

---

## 1. Core Engineering Philosophy

1. **Scientific Reproducibility First**: A bioinformatics data hub is only as good as its provenance and versioning. Data mutations must be explicit, immutable, and checksum-verified.
2. **Simplicity Over Cleverness (KISS & YAGNI)**: Favor straightforward, readable code over hyper-abstracted architectures. Do not build speculative features until concrete requirements exist.
3. **Explicit Over Implicit**: Explicit arguments, explicit schema definitions, explicit error handling, and explicit dependency injection. No "magic" global state.
4. **Defense in Depth**: Security and validation must not rely solely on frontend checks. All boundaries (HTTP API, Git hooks, worker ingestion) must validate inputs independently.
5. **Open Source & Open Standards**: Use open protocols (Git, HTTP, REST, Blake3, Gearhash CDC, OIDC) and permissive, verified open-source tooling.

---

## 2. Architectural Design & Separation of Concerns

All backend services follow a clean layered architecture to isolate business rules from transport mechanisms and database engines:

```text
┌────────────────────────────────────────────────────────┐
│               Presentation / Transport                 │
│         (FastAPI Routers, Git Smart-HTTP, CLI)         │
└───────────────────────────┬────────────────────────────┘
                            │ Calls
┌───────────────────────────▼────────────────────────────┐
│                    Domain Services                     │
│    (Authorization, Repo Manager, Commit Orchestrator)   │
└───────────────────────────┬────────────────────────────┘
                            │ Depends on Interfaces
┌───────────────────────────▼────────────────────────────┐
│                Data Access & Repositories              │
│       (PostgreSQL / SQLAlchemy, PyGit2, OpenXet CAS)   │
└────────────────────────────────────────────────────────┘
```

### Layer Rules
- **Domain logic is pure and framework-agnostic**: The business logic determining whether a user has access to a dataset must not depend on HTTP request objects or frontend types.
- **Dependency Injection**: Pass database sessions, storage clients, and authorization checkers as dependencies (e.g., FastAPI's `Depends` or constructor injection).
- **Single Source of Truth for Schemas**: Pydantic v2 schemas and JSON Schemas define the API contracts. Never accept raw unvalidated dictionaries at controller endpoints.

---

## 3. SOLID & Clean Code Standards

### Single Responsibility Principle (SRP)
- Each module, class, or function must have one reason to change.
- *Anti-pattern:* An API handler that parses multipart files, calculates Blake3 hashes, writes Git commits, updates Postgres, and triggers search re-indexing in one 300-line function.
- *Pattern:* The handler coordinates dedicated service classes (`UploadService`, `CommitService`, `IndexingDispatcher`).

### Open-Closed Principle (OCP)
- Systems should be open for extension, closed for modification.
- When adding support for new curation sources (e.g., NCBI Datasets vs. ENA Portal), write a new harvester adapter adhering to a common `Harvester` interface rather than inserting sprawling `if-elif` blocks into existing pipelines.

### Don't Repeat Yourself (DRY) vs. Premature Abstraction
- Unify business rules and domain logic (e.g., country code validation).
- Accept minor code duplication across completely decoupled domains if premature abstraction would create unnatural coupling (the "Rule of Three").

---

## 4. Error Handling & Fail-Fast Principles

1. **Domain-Specific Exceptions**: Define custom exception classes in domain modules:
   ```python
   class RepositoryError(Exception):
       """Base domain error for repository operations."""

   class DatasetAccessDeniedError(RepositoryError):
       def __init__(self, repo_id: str, user_id: str | None, reason: str):
           super().__init__(f"User {user_id or 'anonymous'} denied access to {repo_id}: {reason}")
           self.repo_id = repo_id
           self.user_id = user_id
           self.reason = reason
   ```
2. **Translate at the Boundary**: Catch domain exceptions at the presentation layer (FastAPI exception handlers) and convert them to standard RFC 7807 problem details or clean JSON responses with appropriate HTTP status codes.
3. **Never Swallow Exceptions**: Never write bare `except:` or `catch (_) {}` blocks that discard stack traces.
4. **Actionable Errors**: Error messages returned to users must state **what failed**, **why it failed**, and **how to fix it**:
   - *Bad:* `"Invalid metadata"`
   - *Good:* `"Metadata validation error in README.md front-matter: 'countries' must contain valid ISO-3166 alpha-2 codes belonging to African Union member states. Found: ['FR']."`

---

## 5. Logging & Observability

- **Structured JSON Logging**: All application logs must be output in structured JSON format in production.
- **Contextual Correlation**: Every log statement emitted during an HTTP request must include a `request_id`, and when authenticated, the `user_orcid` and `repo_id`.
- **Log Levels**:
  - `DEBUG`: Verbose diagnostics (payload chunks, cache hits). Disabled in production.
  - `INFO`: Normal operational milestones (dataset created, commit finalized, worker job completed).
  - `WARNING`: Recoverable unexpected events (rate-limit warning, transient ENA API retry, deprecated format notice).
  - `ERROR`: Unhandled exceptions, failed commits, external service outages requiring developer attention.
  - `CRITICAL`: System-level failures (database connection pool exhausted, storage disk full).
- **Zero Credential Leakage**: Never log authorization headers, PAT tokens, session cookies, or raw secret keys.

---

## 6. Testing Strategy & Pyramid

Every component must provide automated test coverage adhering to the testing pyramid:

```text
         ▲
        / \     E2E Tests (5-10%)
       /   \    - Full browser flows via Playwright
      /─────\   - Push/pull round-trip via CLI
     /       \  Integration Tests (15-20%)
    /         \ - Real Postgres, Valkey, Meili, OpenXet in Docker
   /───────────\- Real Git Smart-HTTP & LFS bridges
  /             \ Unit & Property Tests (70-80%)
 /               \- Pure functions, validators, token claims
/─────────────────\- Fast, isolated, zero external network
```

### Testing Rules
1. **No External Network in Unit Tests**: Unit tests must never make real HTTP calls to ENA, NCBI, or ORCID. Use recorded fixtures (`vcrpy`), mock transport adapters, or local test doubles.
2. **Idempotency Testing**: Any API or worker operation that processes uploads or commits must be tested for idempotency (running twice produces the same state with zero orphaned records).
3. **Property-Based Testing**: Use property/fuzz testing (e.g., `hypothesis` in Python) to validate parsers, checksum verifiers, and coordinate boundary checkers against unexpected edge cases.
4. **Deterministic Fixtures**: Avoid non-deterministic values (such as `datetime.now()` without mocking) in test assertions.

---

## 7. Security by Design

- **Deny by Default**: If an authorization check encounters an unknown permission state, access must be denied (`403 Forbidden`).
- **Least Privilege**: Service-account tokens and internal API credentials must only grant the specific scopes required for their tasks.
- **Input Sanitization**: Treat all external inputs (including dataset filenames, git branch names, and FASTA headers) as untrusted. Prevent path traversal (`../`) and shell injection when interacting with bare git repositories or local storage paths.
- **Data Integrity via Content-Addressing**: Large files are stored and verified by content hashes (Blake3 in OpenXet, SHA-256 in Git LFS). Never trust file size alone for integrity.

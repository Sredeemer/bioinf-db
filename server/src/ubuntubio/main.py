import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.types import ASGIApp, Receive, Scope, Send

from ubuntubio import __version__
from ubuntubio.api import auth, cas, gated, git, lfs, orgs, repos, search, taxonomy
from ubuntubio.auth.cas_tokens import CasTokenManager
from ubuntubio.auth.username import extract_orcid_suffix, slugify_researcher_name
from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger, request_id_ctx, setup_logging
from ubuntubio.db import session as db_session
from ubuntubio.db.models import Base
from ubuntubio.indexer.fts import init_fts_tables

# Initialize structured logging globally
setup_logging()
logger = get_logger("ubuntubio.main")


class RequestLoggingMiddleware:
    """Pure ASGI middleware injecting request_id correlation context and logging HTTP requests."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract or generate correlation ID
        headers_dict = dict(scope.get("headers", []))
        req_id_bytes = headers_dict.get(b"x-request-id")
        req_id = (
            req_id_bytes.decode("ascii", errors="ignore") if req_id_bytes else uuid.uuid4().hex[:16]
        )
        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Any) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                # Inject X-Request-ID into outgoing response headers
                raw_headers = list(message.get("headers", []))
                raw_headers.append((b"x-request-id", req_id.encode("ascii")))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            elapsed = time.perf_counter() - start_time
            logger.exception(
                f"{scope.get('method')} {scope.get('path')} failed with unhandled exception",
                extra={
                    "http_method": scope.get("method"),
                    "http_path": scope.get("path"),
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
            raise
        else:
            elapsed = time.perf_counter() - start_time
            logger.info(
                f"{scope.get('method')} {scope.get('path')} -> {status_code}",
                extra={
                    "http_method": scope.get("method"),
                    "http_path": scope.get("path"),
                    "status_code": status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )
        finally:
            request_id_ctx.reset(token)


async def migrate_users_table(conn: Any) -> None:
    """Ensure username column exists on users table and backfill existing users."""
    res = await conn.execute(text("PRAGMA table_info(users)"))
    columns = [row[1] for row in res.fetchall()]
    if "username" not in columns:
        await conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(64)"))
        logger.info("Added username column to users table")

    users_res = await conn.execute(
        text("SELECT id, name, orcid_id FROM users WHERE username IS NULL")
    )
    for user_row in users_res.fetchall():
        uid, name, orcid_id = user_row[0], user_row[1], user_row[2]
        base_slug = slugify_researcher_name(name)
        orcid_suffix = extract_orcid_suffix(orcid_id)
        chk = await conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": base_slug})
        chosen = base_slug if chk.scalar_one_or_none() is None else f"{base_slug}-{orcid_suffix}"
        await conn.execute(
            text("UPDATE users SET username = :u WHERE id = :id"),
            {"u": chosen, "id": uid},
        )
        logger.info("Backfilled username for user", extra={"user_id": uid, "username": chosen})


async def backfill_search_index(conn: Any) -> None:
    """Ensure all existing repositories are indexed into FTS5 on startup."""
    repos_res = await conn.execute(
        text("""
            SELECT r.id, r.slug, r.name, r.description, r.domain, r.access, r.license,
                   r.is_verified_african, r.owner_type, r.owner_id, r.created_at, r.updated_at
            FROM repositories r
            LEFT JOIN dataset_search_records s ON r.id = s.repo_id
            WHERE s.repo_id IS NULL
        """)
    )
    for row in repos_res.fetchall():
        repo_id, slug, name, description = row[0], row[1], row[2], row[3]
        domain, access, lic, is_verified = row[4], row[5], row[6], bool(row[7])
        owner_type, owner_id = row[8], row[9]
        created_at, updated_at = row[10], row[11]

        await conn.execute(
            text("""
                INSERT OR REPLACE INTO dataset_search_records(
                    repo_id, slug, name, title, description, domain, access, license,
                    countries_json, taxa_json, genus_json, family_json,
                    is_verified_african, owner_type, owner_id, samples_count,
                    benefit_sharing, created_at, updated_at
                ) VALUES (
                    :repo_id, :slug, :name, :title, :description, :domain, :access, :license,
                    '[]', '[]', '[]', '[]',
                    :is_verified_african, :owner_type, :owner_id, 0,
                    NULL, :created_at, :updated_at
                )
            """),
            {
                "repo_id": repo_id,
                "slug": slug,
                "name": name,
                "title": name,
                "description": description or "",
                "domain": domain,
                "access": access,
                "license": lic,
                "is_verified_african": is_verified,
                "owner_type": owner_type,
                "owner_id": owner_id,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        await conn.execute(
            text("DELETE FROM datasets_fts WHERE repo_id = :repo_id"),
            {"repo_id": repo_id},
        )
        await conn.execute(
            text("""
                INSERT INTO datasets_fts(
                    repo_id, slug, title, description, countries, genus, family, benefit_sharing
                ) VALUES (
                    :repo_id, :slug, :title, :description, '', '', '', ''
                )
            """),
            {
                "repo_id": repo_id,
                "slug": slug,
                "title": name,
                "description": description or "",
            },
        )
        logger.info("Backfilled search index for repository", extra={"slug": slug})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager for schema initialization and cleanup."""
    logger.info(
        "Initializing UbuntuBio Hub API server",
        extra={"version": __version__, "env": settings.ENV},
    )
    # Auto-provision relational tables, migrations, and FTS5 search indexes
    async with db_session.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_users_table(conn)
        await init_fts_tables(conn)
        await backfill_search_index(conn)
    logger.info("Database schemas and FTS5 search tables initialized successfully")
    yield
    logger.info("Shutting down UbuntuBio Hub API server")
    await db_session.engine.dispose()


app = FastAPI(
    title="UbuntuBio Hub API",
    description="African Bioinformatics Data Hub API",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global CAS token manager instance
cas_token_manager = CasTokenManager(
    issuer=settings.API_URL,
    audience=settings.CAS_TOKEN_AUDIENCE,
    token_lifetime_seconds=settings.CAS_TOKEN_LIFETIME_SECONDS,
)

# Mount API Routers
app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(repos.router)
app.include_router(cas.router)
app.include_router(gated.router)
app.include_router(git.router)
app.include_router(lfs.router)
app.include_router(search.router)
app.include_router(search.admin_router)
app.include_router(taxonomy.router)
app.include_router(taxonomy.v1_router)


@app.get("/healthz", tags=["Ops"])
async def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok", "version": __version__}


@app.get("/", tags=["Info"])
async def root_info() -> dict[str, Any]:
    """UbuntuBio Hub service information."""
    return {
        "service": "UbuntuBio Hub",
        "description": "African Bioinformatics Data Repository & CAS",
        "version": __version__,
        "documentation": "/docs",
    }


@app.get("/.well-known/jwks.json", tags=["Auth"])
async def get_jwks() -> dict[str, Any]:
    """JWKS endpoint for OpenXet and external services to verify CAS tokens."""
    return cas_token_manager.get_public_jwks()


@app.get("/.well-known/openid-configuration", tags=["Auth"])
async def get_openid_configuration() -> dict[str, Any]:
    """OIDC discovery document for OpenXet authentication validation."""
    base_url = cas_token_manager.issuer
    return {
        "issuer": base_url,
        "jwks_uri": f"{base_url}/.well-known/jwks.json",
        "response_types_supported": ["token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }

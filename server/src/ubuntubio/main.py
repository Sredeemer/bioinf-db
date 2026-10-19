import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from ubuntubio import __version__
from ubuntubio.api import auth, cas, gated, git, lfs, orgs, repos, search
from ubuntubio.auth.cas_tokens import CasTokenManager
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager for schema initialization and cleanup."""
    logger.info(
        "Initializing UbuntuBio Hub API server",
        extra={"version": __version__, "env": settings.ENV},
    )
    # Auto-provision relational tables and FTS5 search indexes
    async with db_session.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await init_fts_tables(conn)
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

"""Application factory: wires settings, database, service, middleware and static files."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .ai_review import Reviewer, build_reviewer
from .auth import GoogleVerifier, TokenInfoVerifier
from .config import Settings, get_settings
from .db import make_engine
from .emailer import Emailer, build_emailer
from .repository import Repository
from .routes import router
from .seed import seed_database, sync_places
from .service import BiteTraceService, ReportRejected
from .timeutil import utcnow

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=()",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: https://tile.openstreetmap.org; "
        "style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style; "
        "script-src 'self' https://accounts.google.com/gsi/client; "
        "connect-src 'self' https://accounts.google.com/gsi/; "
        "frame-src https://accounts.google.com/gsi/; frame-ancestors 'none'; base-uri 'self'"
    ),
}
DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


def create_app(
    settings: Settings | None = None,
    *,
    reviewer: Reviewer | None = None,
    emailer: Emailer | None = None,
    clock: Callable[[], datetime] = utcnow,
    verifier: GoogleVerifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    repo = Repository(make_engine(settings.database_url))
    repo.init_schema()
    seed_database(repo, settings.secret_salt, clock())
    sync_places(repo, clock())

    app = FastAPI(
        title="BiteTrace API",
        version="1.0.0",
        description="Crowdsourced space-time outbreak detection for street food illness.",
    )
    app.state.service = BiteTraceService(
        repo,
        settings,
        reviewer or build_reviewer(settings),
        emailer or build_emailer(settings),
        clock=clock,
        verifier=verifier or (TokenInfoVerifier(settings.google_client_id) if settings.google_client_id else None),
    )

    app.add_middleware(GZipMiddleware, minimum_size=800)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith(DOC_PATHS):  # Swagger UI needs its CDN assets
            for key, value in SECURITY_HEADERS.items():
                response.headers.setdefault(key, value)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ReportRejected)
    async def rejected(_: Request, exc: ReportRejected) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "detail": exc.message, "reasons": exc.reasons},
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        reasons = [
            f"{'.'.join(str(p) for p in e['loc'][1:]) or 'request'}: {e['msg']}" for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_input", "detail": "Invalid input.", "reasons": reasons},
        )

    app.include_router(router)
    if PUBLIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="public")
    return app

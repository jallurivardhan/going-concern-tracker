from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from gct.config import settings
from gct.routes.companies import router as companies_router
from gct.routes.filings import router as filings_router
from gct.routes.flags import router as flags_router
from gct.routes.health import router as health_router
from gct.routes.methodology import router as methodology_router
from gct.routes.search import router as search_router
from gct.routes.stats import router as stats_router
from gct.routes.pipeline import router as pipeline_router
from gct.routes.subscriptions import router as subscriptions_router

app = FastAPI(
    title="Going Concern Tracker API",
    description=(
        "Detects going-concern opinions in SEC 10-K filings and surfaces them with "
        "cited auditor language, character offsets, and filing URLs. "
        "See /api/methodology for accuracy metrics and scope documentation."
    ),
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

_allowed_origins = [
    "http://localhost:3000",          # Next.js dev server
    settings.frontend_url,            # Set FRONTEND_URL env var to actual Vercel URL after deploy
    "https://going-concern-tracker.vercel.app",  # Vercel production URL (update after deploy)
]
# De-duplicate while preserving order
_seen: set[str] = set()
_unique_origins: list[str] = []
for _o in _allowed_origins:
    if _o not in _seen:
        _seen.add(_o)
        _unique_origins.append(_o)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_unique_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PREFIX = "/api"
app.include_router(health_router, prefix=_PREFIX)
app.include_router(flags_router, prefix=_PREFIX)
app.include_router(companies_router, prefix=_PREFIX)
app.include_router(filings_router, prefix=_PREFIX)
app.include_router(search_router, prefix=_PREFIX)
app.include_router(methodology_router, prefix=_PREFIX)
app.include_router(stats_router, prefix=_PREFIX)
app.include_router(subscriptions_router, prefix=_PREFIX)
app.include_router(pipeline_router, prefix=_PREFIX)


@app.get("/", include_in_schema=False)
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/api/docs")

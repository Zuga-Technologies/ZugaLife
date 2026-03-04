"""ZugaLife standalone backend — food truck mode.

Run: cd ZugaLife/backend && python -m uvicorn main:app --port 8001
"""

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure ZugaLife/backend is on sys.path so 'core' resolves via symlink
sys.path.insert(0, str(Path(__file__).parent))

from config import settings  # noqa: E402

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Standalone startup and shutdown."""

    logger.info("Starting %s (standalone)", settings.app_name)

    # Initialize database
    from core.database.session import init_engine, init_db

    init_engine(settings.database_url, echo=settings.debug)
    await init_db()
    logger.info("Database initialized")

    # Load ZugaLife plugin to register models and get router
    from plugin import ZugaLifePlugin

    plugin = ZugaLifePlugin()
    app.include_router(plugin.router)
    await plugin.on_startup()
    logger.info("ZugaLife plugin loaded (v%s)", plugin.version)

    logger.info("%s ready on %s:%d", settings.app_name, settings.host, settings.port)

    yield

    # Shutdown
    logger.info("Shutting down %s", settings.app_name)
    from core.database.session import close_db

    await close_db()
    logger.info("Database connections closed")


def create_app() -> FastAPI:
    """Create the standalone FastAPI application."""

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth routes from shared core
    from core.auth.routes import router as auth_router

    app.include_router(auth_router)

    # Health check
    @app.get("/api/health/live")
    async def health_live():
        return {"status": "ok", "service": settings.app_name, "mode": "standalone"}

    return app


app = create_app()

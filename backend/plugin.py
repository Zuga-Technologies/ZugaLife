"""ZugaLife studio plugin — emoji-based mood logging."""

import importlib.util
import logging
import sys
from pathlib import Path

from fastapi import APIRouter

from plugins.interface import StudioPlugin

logger = logging.getLogger(__name__)

_plugin_dir = Path(__file__).parent


def _load_sibling(name: str):
    """Load a sibling module from this plugin's directory.

    Registers in sys.modules with a 'zugalife.' prefix so that later
    siblings (e.g. routes.py) can access earlier ones (models, schemas)
    via sys.modules at import time.
    """
    qualified = f"zugalife.{name}"
    if qualified in sys.modules:
        return sys.modules[qualified]
    spec = importlib.util.spec_from_file_location(
        qualified, _plugin_dir / f"{name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


# Load siblings in dependency order: models → schemas → routes
_models = _load_sibling("models")
_schemas = _load_sibling("schemas")
_routes = _load_sibling("routes")


class ZugaLifePlugin(StudioPlugin):

    @property
    def name(self) -> str:
        return "life"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def router(self) -> APIRouter:
        return _routes.router

    @property
    def models(self) -> list:
        return [_models.MoodEntry]

    async def on_startup(self) -> None:
        """Create mood_entries table if it doesn't exist.

        init_db() runs BEFORE plugins load (lifespan.py), so our model
        isn't in Base.metadata yet at that point. We handle our own
        table creation here. create_all is idempotent — it skips tables
        that already exist.
        """
        from core.database.base import Base
        from core.database.session import engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("ZugaLife tables initialized")

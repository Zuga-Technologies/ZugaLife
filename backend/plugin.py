"""ZugaLife studio plugin — mood, journal, habits, goals, and meditation."""

import importlib.util
import logging
import sys
from pathlib import Path

from fastapi import APIRouter

from core.plugins.interface import StudioPlugin

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


def _load_submodule(package: str, name: str):
    """Load a module from a sub-package directory (e.g. journal/).

    Works the same as _load_sibling but reaches into a subdirectory.
    Registers as 'zugalife.{package}.{name}' in sys.modules.
    """
    qualified = f"zugalife.{package}.{name}"
    if qualified in sys.modules:
        return sys.modules[qualified]
    file_path = _plugin_dir / package / f"{name}.py"
    spec = importlib.util.spec_from_file_location(qualified, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


# Load mood siblings in dependency order: models → schemas → routes
_models = _load_sibling("models")
_schemas = _load_sibling("schemas")
_routes = _load_sibling("routes")

# Load journal submodule: models → schemas → prompts → routes
_j_models = _load_submodule("journal", "models")
_j_schemas = _load_submodule("journal", "schemas")
_j_prompts = _load_submodule("journal", "prompts")
_j_routes = _load_submodule("journal", "routes")

# Load habits submodule: models → schemas → prompts → routes
_h_models = _load_submodule("habits", "models")
_h_schemas = _load_submodule("habits", "schemas")
_h_prompts = _load_submodule("habits", "prompts")
_h_routes = _load_submodule("habits", "routes")

# Load goals submodule: models → schemas → routes (no prompts — no AI features in v1)
_g_models = _load_submodule("goals", "models")
_g_schemas = _load_submodule("goals", "schemas")
_g_routes = _load_submodule("goals", "routes")

# Load meditation submodule: models → schemas → prompts → routes
_m_models = _load_submodule("meditation", "models")
_m_schemas = _load_submodule("meditation", "schemas")
_m_prompts = _load_submodule("meditation", "prompts")
_m_routes = _load_submodule("meditation", "routes")

# Merge all routers into a single combined router
_combined_router = APIRouter()
_combined_router.include_router(_routes.router)
_combined_router.include_router(_j_routes.router)
_combined_router.include_router(_h_routes.router)
_combined_router.include_router(_g_routes.router)
_combined_router.include_router(_m_routes.router)


class ZugaLifePlugin(StudioPlugin):

    @property
    def name(self) -> str:
        return "life"

    @property
    def version(self) -> str:
        return "0.5.0"

    @property
    def router(self) -> APIRouter:
        return _combined_router

    @property
    def models(self) -> list:
        return [
            _models.MoodEntry,
            _j_models.JournalEntry, _j_models.JournalReflection,
            _h_models.HabitDefinition, _h_models.HabitLog, _h_models.HabitInsight,
            _g_models.GoalDefinition, _g_models.GoalMilestone,
            _m_models.MeditationSession,
        ]

    async def on_startup(self) -> None:
        """Create all ZugaLife tables if they don't exist.

        init_db() runs BEFORE plugins load (lifespan.py), so our models
        aren't in Base.metadata yet at that point. We handle our own
        table creation here. create_all is idempotent — it skips tables
        that already exist.
        """
        from core.database.base import Base
        from core.database.session import get_engine

        async with get_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("ZugaLife tables initialized (mood + journal + habits + goals + meditation)")

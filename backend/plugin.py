"""ZugaLife studio plugin — mood, journal, habits, goals, meditation, and therapist."""

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


# Load settings siblings first — other modules reference settings_helpers at request time
_s_models = _load_sibling("settings_models")
_s_schemas = _load_sibling("settings_schemas")
_s_helpers = _load_sibling("settings_helpers")
_s_routes = _load_sibling("settings_routes")

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

# Load goals submodule: models → schemas → templates → routes
_g_models = _load_submodule("goals", "models")
_g_schemas = _load_submodule("goals", "schemas")
_g_templates = _load_submodule("goals", "templates")
_g_routes = _load_submodule("goals", "routes")

# Load meditation submodule: models → schemas → prompts → routes
_m_models = _load_submodule("meditation", "models")
_m_schemas = _load_submodule("meditation", "schemas")
_m_prompts = _load_submodule("meditation", "prompts")
_m_routes = _load_submodule("meditation", "routes")

# Load therapist submodule: models → schemas → safety → prompts → context → routes
# SECURITY: therapist data flows ONE WAY — other modules read INTO therapist context,
# but therapist notes NEVER flow out to other modules.
_t_models = _load_submodule("therapist", "models")
_t_schemas = _load_submodule("therapist", "schemas")
_t_safety = _load_submodule("therapist", "safety")
_t_prompts = _load_submodule("therapist", "prompts")
_t_context = _load_submodule("therapist", "context")
_t_routes = _load_submodule("therapist", "routes")

# Load forecasting submodule: engine → schemas → context → routes
_f_engine = _load_submodule("forecasting", "engine")
_f_schemas = _load_submodule("forecasting", "schemas")
_f_context = _load_submodule("forecasting", "context")
_f_routes = _load_submodule("forecasting", "routes")

# Load gamification submodule: models → schemas → engine → ai_challenges → routes
# engine must come after schemas (build_badge_response resolves BadgeResponse via sys.modules)
_gam_models = _load_submodule("gamification", "models")
_gam_schemas = _load_submodule("gamification", "schemas")
_gam_engine = _load_submodule("gamification", "engine")
_gam_ai = _load_submodule("gamification", "ai_challenges")
_gam_routes = _load_submodule("gamification", "routes")

# Load data management (reset endpoints) — must come after all domain modules
_data_mgmt = _load_sibling("data_management")

# Load dashboard AFTER all modules — it reads from sys.modules at request time
_dashboard = _load_sibling("dashboard")

# Merge all routers into a single combined router
_combined_router = APIRouter()
_combined_router.include_router(_routes.router)
_combined_router.include_router(_j_routes.router)
_combined_router.include_router(_h_routes.router)
_combined_router.include_router(_g_routes.router)
_combined_router.include_router(_m_routes.router)
_combined_router.include_router(_t_routes.router)
_combined_router.include_router(_s_routes.router)
_combined_router.include_router(_f_routes.router)
_combined_router.include_router(_gam_routes.router)
_combined_router.include_router(_data_mgmt.router)
_combined_router.include_router(_dashboard.router)


class ZugaLifePlugin(StudioPlugin):

    @property
    def name(self) -> str:
        return "life"

    @property
    def version(self) -> str:
        return "0.8.0"

    @property
    def router(self) -> APIRouter:
        return _combined_router

    @property
    def event_catalog(self) -> list[dict]:
        return [
            {
                "type": "life:mood_logged",
                "description": "User logged their mood",
                "data_schema": {"emoji": "string", "label": "string", "note": "string (optional)", "streak": "integer"},
            },
            {
                "type": "life:habit_completed",
                "description": "User completed a habit",
                "data_schema": {"habit_id": "integer", "habit_name": "string", "log_date": "date"},
            },
            {
                "type": "life:journal_created",
                "description": "User wrote a journal entry",
                "data_schema": {"entry_id": "integer", "title": "string", "mood_emoji": "string (optional)"},
            },
            {
                "type": "life:goal_completed",
                "description": "User completed a goal",
                "data_schema": {"goal_id": "integer", "title": "string"},
            },
            {
                "type": "life:meditation_completed",
                "description": "User completed a meditation session",
                "data_schema": {"session_id": "integer", "focus": "string", "duration_seconds": "integer"},
            },
        ]

    @property
    def models(self) -> list:
        return [
            _models.MoodEntry,
            _s_models.LifeUserSettings,
            _j_models.JournalEntry, _j_models.JournalReflection,
            _h_models.HabitDefinition, _h_models.HabitLog, _h_models.HabitInsight,
            _g_models.GoalDefinition, _g_models.GoalMilestone, _g_models.GoalHabitLink,
            _m_models.MeditationSession,
            _t_models.TherapistSessionNote,
            _gam_models.UserXP, _gam_models.XPTransaction,
            _gam_models.UserBadge, _gam_models.DailyChallenge,
            _gam_models.WeeklyQuest,
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

            # Migrate existing tables: add new columns that create_all can't add
            # to already-existing tables.  Each ALTER is wrapped in try/except
            # so it's safe to run repeatedly (idempotent).
            migrations = [
                "ALTER TABLE life_user_settings ADD COLUMN med_length VARCHAR(10) DEFAULT 'medium'",
                "ALTER TABLE meditation_sessions ADD COLUMN length VARCHAR(10) DEFAULT 'medium'",
                "ALTER TABLE meditation_sessions ADD COLUMN duration_seconds INTEGER DEFAULT 0",
                "ALTER TABLE meditation_sessions ADD COLUMN status VARCHAR(20) DEFAULT 'ready'",
                "ALTER TABLE meditation_sessions ADD COLUMN error_message VARCHAR(500)",
                # Drop legacy column that blocks inserts (NOT NULL, no default, not in model)
                "ALTER TABLE meditation_sessions DROP COLUMN duration_minutes",
                # Gamification: AI challenges + auto-completion
                "ALTER TABLE life_daily_challenges ADD COLUMN is_ai_generated BOOLEAN DEFAULT FALSE",
                "ALTER TABLE life_daily_challenges ADD COLUMN completion_source VARCHAR(50)",
                # Gamification: prestige system
                "ALTER TABLE life_user_xp ADD COLUMN prestige_level INTEGER DEFAULT 0",
                # Onboarding state
                "ALTER TABLE life_user_settings ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE",
            ]
            for sql in migrations:
                try:
                    await conn.execute(__import__("sqlalchemy").text(sql))
                except Exception:
                    pass  # column already exists

        logger.info("ZugaLife tables initialized (mood + settings + journal + habits + goals + meditation + therapist + gamification)")

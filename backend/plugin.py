"""ZugaLife studio plugin — mood, journal, habits, goals, meditation, and therapist."""

import asyncio
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


# Load journal submodule: models → schemas → prompts → prompt_library → routes
_j_models = _load_submodule("journal", "models")
_j_schemas = _load_submodule("journal", "schemas")
_j_prompts = _load_submodule("journal", "prompts")
_j_prompt_lib = _load_submodule("journal", "prompt_library")
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

# Load therapist submodule: models → schemas → safety → prompts → context → routes → speech
# SECURITY: therapist data flows ONE WAY — other modules read INTO therapist context,
# but therapist notes NEVER flow out to other modules.
# speech MUST load after schemas (speech.py reads TherapistSpeakRequest from sys.modules
# at import time; schemas must already be registered as "zugalife.therapist.schemas").
_t_models = _load_submodule("therapist", "models")
_t_schemas = _load_submodule("therapist", "schemas")
_t_safety = _load_submodule("therapist", "safety")
_t_prompts = _load_submodule("therapist", "prompts")
_t_context = _load_submodule("therapist", "context")
_t_routes = _load_submodule("therapist", "routes")
_t_speech = _load_submodule("therapist", "speech")

# Load forecasting submodule: models → engine → schemas → context → narrative → routes
_f_models = _load_submodule("forecasting", "models")
_f_engine = _load_submodule("forecasting", "engine")
_f_schemas = _load_submodule("forecasting", "schemas")
_f_context = _load_submodule("forecasting", "context")
_f_narrative = _load_submodule("forecasting", "narrative")
_f_routes = _load_submodule("forecasting", "routes")

# Load gamification submodule: models → schemas → engine → ai_challenges → insights → routes
# engine must come after schemas (build_badge_response resolves BadgeResponse via sys.modules)
_gam_models = _load_submodule("gamification", "models")
_gam_schemas = _load_submodule("gamification", "schemas")
_gam_engine = _load_submodule("gamification", "engine")
_gam_ai = _load_submodule("gamification", "ai_challenges")
_gam_insights = _load_submodule("gamification", "insights")
_gam_routes = _load_submodule("gamification", "routes")
_gam_notif = _load_submodule("gamification", "notifications")
_gam_notif_routes = _load_submodule("gamification", "notification_routes")
_gam_prewarm = _load_submodule("gamification", "prewarm")

# Themes are now a Forge creation type (type=widget). Retired from ZugaLife
# 2026-04-17 via γ cutover — existing data migrated to forge_* tables via
# ZugaApp /api/forge/internal/migrate-zugalife-themes; callers point at
# /api/forge/*.

# Load ecosystem integration (cross-studio signals)
_ecosystem = _load_sibling("ecosystem")

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
_combined_router.include_router(_t_speech.router)
_combined_router.include_router(_s_routes.router)
_combined_router.include_router(_f_routes.router)
_combined_router.include_router(_gam_routes.router)
_combined_router.include_router(_gam_notif_routes.router)
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
            _gam_models.WeeklyQuest, _gam_models.UserInsight,
            _f_models.WeeklyNarrative,
            _ecosystem.CrossStudioSignal,
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

            # Additive ALTERs — idempotent. SQLite raises "duplicate column"
            # when the column already exists; that's the only expected
            # exception. Alembic migration queued post-baseline.
            additive_migrations = [
                "ALTER TABLE life_user_settings ADD COLUMN med_length VARCHAR(10) DEFAULT 'medium'",
                "ALTER TABLE meditation_sessions ADD COLUMN length VARCHAR(10) DEFAULT 'medium'",
                "ALTER TABLE meditation_sessions ADD COLUMN duration_seconds INTEGER DEFAULT 0",
                "ALTER TABLE meditation_sessions ADD COLUMN status VARCHAR(20) DEFAULT 'ready'",
                "ALTER TABLE meditation_sessions ADD COLUMN error_message VARCHAR(500)",
                # Gamification: AI challenges + auto-completion
                "ALTER TABLE life_daily_challenges ADD COLUMN is_ai_generated BOOLEAN DEFAULT FALSE",
                "ALTER TABLE life_daily_challenges ADD COLUMN completion_source VARCHAR(50)",
                # Gamification: prestige system
                "ALTER TABLE life_user_xp ADD COLUMN prestige_level INTEGER DEFAULT 0",
                # Onboarding state
                "ALTER TABLE life_user_settings ADD COLUMN onboarding_completed BOOLEAN DEFAULT FALSE",
                # WOOP goal psychology fields (Phase 2)
                "ALTER TABLE goal_definitions ADD COLUMN identity_statement VARCHAR(500)",
                "ALTER TABLE goal_definitions ADD COLUMN obstacle VARCHAR(500)",
                "ALTER TABLE goal_definitions ADD COLUMN implementation_plan TEXT",
                "ALTER TABLE goal_definitions ADD COLUMN approach_reframe VARCHAR(500)",
                # Goal-connected daily challenges (Phase 2)
                "ALTER TABLE life_daily_challenges ADD COLUMN goal_connection VARCHAR(200)",
                # Zugabot personalization layer (Phase 4)
                "ALTER TABLE life_user_settings ADD COLUMN player_type VARCHAR(20) DEFAULT 'achiever'",
                "ALTER TABLE life_user_settings ADD COLUMN challenge_difficulty VARCHAR(10) DEFAULT 'medium'",
                "ALTER TABLE life_user_settings ADD COLUMN gamification_emphasis FLOAT DEFAULT 0.7",
                "ALTER TABLE life_user_settings ADD COLUMN personalization_source VARCHAR(10) DEFAULT 'system'",
                # Theme preset system (color scheme + typography + mood icons)
                "ALTER TABLE life_user_settings ADD COLUMN theme_preset VARCHAR(30) DEFAULT 'default'",
                # Journal activity tags (added 2026-04-02 in dc3fa70; migration
                # was missed in that commit — stale DBs created before then
                # would 500 on journal create. Railway fresh-create has this
                # column; MM stale DBs will pick it up on next boot.)
                "ALTER TABLE journal_entries ADD COLUMN tags VARCHAR(500)",
                # Habit implementation-intention trigger (added in 4d2dcf7;
                # migration was missed. `_ensure_presets` omits the kwarg so
                # preset-seeding still worked, but `create_habit` explicitly
                # sets trigger=None and would 500 on stale DBs.)
                "ALTER TABLE habit_definitions ADD COLUMN trigger VARCHAR(200)",
                # Session 4 cross-module migration sweep (2026-04-19). Five
                # additive ALTERs surfaced by a disciplined model-vs-live
                # PRAGMA diff across all 24 ZugaLife domain tables. Same
                # class of drift as the journal.tags + habits.trigger misses
                # from Session 3 — feature model edits landed without the
                # matching migration, so stale DBs would 500 on the next
                # INSERT that touches the column. Railway fresh-create
                # already has them; MM stale DBs pick them up on next boot.
                "ALTER TABLE life_user_settings ADD COLUMN custom_colors TEXT",
                "ALTER TABLE therapist_session_notes ADD COLUMN mood_before VARCHAR(32)",
                "ALTER TABLE therapist_session_notes ADD COLUMN mood_after VARCHAR(32)",
                "ALTER TABLE therapist_session_notes ADD COLUMN rating INTEGER",
                "ALTER TABLE life_weekly_quests ADD COLUMN completion_source VARCHAR(50)",
                # Daily breath cold-open cross-device gate (2026-04-26)
                "ALTER TABLE life_user_settings ADD COLUMN last_breath_date VARCHAR(10)",
            ]
            for sql in additive_migrations:
                try:
                    await conn.execute(__import__("sqlalchemy").text(sql))
                except Exception:
                    pass  # column already exists

            # LEGACY ONE-SHOT DROP (2026-03) — destructive, isolated on purpose.
            # Originally removed because `duration_minutes` was NOT NULL, had no
            # default, and was not in the SQLAlchemy model, so inserts failed.
            # Now replaced by `duration_seconds` everywhere.
            #
            # ⚠ FOOTGUN: because this runs every startup inside try/except, if a
            # future migration ever reintroduces a column named `duration_minutes`
            # for a different purpose, this DROP will execute and silently destroy
            # that column on every prod boot. Rename the new column or remove
            # this block first.
            try:
                await conn.execute(__import__("sqlalchemy").text(
                    "ALTER TABLE meditation_sessions DROP COLUMN duration_minutes"
                ))
            except Exception:
                pass  # already dropped (expected on all prod DBs since 2026-03)

        logger.info("ZugaLife tables initialized (mood + settings + journal + habits + goals + meditation + therapist + gamification)")

        # Register ecosystem event handler for cross-studio signals
        if _ecosystem and hasattr(_ecosystem, "register_event_handler"):
            _ecosystem.register_event_handler()

        # Register webhook event catalog. ImportError is swallowed for
        # standalone (food-truck) topology where ZugaApp's event_bus is absent.
        try:
            from core.events.bus import event_bus
            event_bus.register_catalog("life", [
                {
                    "type": "life:habit_completed",
                    "description": "User completed a tracked habit",
                    "data_schema": {
                        "habit_id": "int",
                        "habit_name": "str",
                        "log_date": "str",
                    },
                },
                {
                    "type": "life:goal_completed",
                    "description": "User marked a goal complete",
                    "data_schema": {
                        "goal_id": "int",
                        "title": "str",
                    },
                },
                {
                    "type": "life:mood_logged",
                    "description": "User logged a mood entry",
                    "data_schema": {
                        "emoji": "str",
                        "label": "str",
                        "note": "str",
                        "streak": "int",
                    },
                },
                {
                    "type": "life:journal_created",
                    "description": "User created a journal entry",
                    "data_schema": {
                        "entry_id": "int",
                        "title": "str",
                        "mood_emoji": "str",
                    },
                },
            ])
        except ImportError:
            pass

        # Arm the daily challenge / weekly quest pre-warm scheduler so the
        # dashboard read path no longer triggers LLM generation on the first
        # request of the day. Task handle is stashed for on_shutdown cancel.
        self._prewarm_task = _gam_prewarm.start_scheduler_task()

    async def on_shutdown(self) -> None:
        """Cancel the prewarm scheduler cleanly so uvicorn shuts down fast."""
        task = getattr(self, "_prewarm_task", None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

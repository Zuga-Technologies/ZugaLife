# ZugaLife

A personal wellness and life-tracking app built with **Vue 3** and **FastAPI**. Track your mood, journal with AI insights, build habits, set goals, meditate with guided sessions, and talk to an AI therapist.

<!-- Add a screenshot here: ![ZugaLife Dashboard](docs/screenshot.png) -->

## Features

| Tab | What it does |
|-----|-------------|
| **Dashboard** | Daily overview — mood trends, habit streaks, goal progress, meditation stats |
| **Journal** | Write journal entries with optional AI-powered reflection and insights |
| **Habits** | Define habits, track daily completions, view streaks and completion rates |
| **Goals** | Set goals with milestones, track progress, link habits to goals |
| **Meditate** | Guided meditation with ambient sounds, breathing exercises, session logging |
| **Therapist** | AI conversational therapy with safety guardrails and session history |

## Quick Start

```bash
git clone https://github.com/Zuga-Technologies/ZugaLife.git
cd ZugaLife
bash setup.sh    # pulls ZugaCore, installs deps, creates .env
bash start.sh    # starts backend + frontend
```

Open **http://localhost:5174** and log in with any email (dev mode).

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** (with npm)
- **Git** (for submodule support)

## Architecture

```
┌─────────────────────────────────┐
│         Vue 3 Frontend          │  Port 5174
│  Tailwind CSS + Lucide Icons    │
│  Pinia (state) + Vue Router     │
└──────────────┬──────────────────┘
               │ /api/* (Vite proxy)
┌──────────────▼──────────────────┐
│        FastAPI Backend          │  Port 8001
│  SQLite (async) + SQLAlchemy    │
│  Venice AI (optional)           │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│     ZugaCore (git submodule)    │
│  Auth · Database · Credits      │
│  Theme · API Client · Plugins   │
└─────────────────────────────────┘
```

**ZugaCore** is the shared foundation layer providing authentication, database management, a Tailwind theme system, and the API client. It lives as a git submodule at `./core/` and is used by both frontend and backend.

## Configuration

All configuration is in `.env` (created from `.env.example` during setup):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VENICE_API_KEY` | No | _(empty)_ | Venice AI API key — enables therapist, journal insights, meditation guidance |
| `AUTH_MODE` | No | `dev` | `dev` = any email works, `production` = email verification required |
| `CREDIT_FAIL_MODE` | No | `open` | `open` = unlimited AI calls, `enforce` = credit-tracked |
| `ZUGAAPP_CREDITS_URL` | No | _(empty)_ | Credit server URL (only for ZugaApp integration) |
| `STUDIO_SERVICE_KEY` | No | _(empty)_ | Service-to-service key (only for ZugaApp integration) |

**Standalone mode** works with zero configuration. AI features (therapist, journal insights) require a Venice API key.

## Project Structure

```
ZugaLife/
├── core/                      # ZugaCore submodule (auth, DB, theme)
├── backend/
│   ├── main.py                # FastAPI entry point
│   ├── config.py              # Settings (Pydantic)
│   ├── plugin.py              # Studio plugin loader
│   ├── models.py              # Mood models
│   ├── routes.py              # Mood endpoints
│   ├── dashboard.py           # Dashboard aggregation
│   ├── journal/               # Journal module (models, routes, AI prompts)
│   ├── habits/                # Habits module (definitions, tracking, streaks)
│   ├── goals/                 # Goals module (milestones, habit linking)
│   ├── meditation/            # Meditation module (sessions, guided audio)
│   ├── therapist/             # AI therapist (safety, context, sessions)
│   ├── forecasting/           # Mood forecasting engine
│   ├── core/                  # Symlinks to ZugaCore (created by setup.sh)
│   │   ├── ai/               # Local — Venice AI gateway + providers
│   │   ├── auth -> ../core/auth
│   │   ├── database -> ../core/database
│   │   ├── plugins -> ../core/plugins
│   │   └── credits -> ../core/credits
│   └── requirements.txt
├── frontend/
│   ├── index.html             # Entry point
│   ├── main.ts                # Vue app init + router
│   ├── App.vue                # Root component (auth + nav)
│   ├── LifeView.vue           # Main app (all 6 tabs)
│   ├── AnalyticsDashboard.vue # Advanced mood analytics
│   ├── SettingsPanel.vue      # Wallpaper/theme picker
│   ├── BackgroundTheme.vue    # Animated backgrounds
│   ├── plugin.ts              # ZugaApp plugin export
│   ├── ambience.ts            # Ambient sound player
│   ├── background-themes.ts   # Theme presets
│   └── package.json
├── docs/
│   ├── MEDITATION_SPEC.md     # Meditation system spec
│   └── AI_THERAPIST_RESEARCH.md
├── setup.sh                   # One-command setup
├── start.sh                   # One-command start
├── .env.example               # Environment template
└── LICENSE                    # MIT
```

## Development

### Standalone Mode

This is the default. The app runs on its own with SQLite and dev auth:

```bash
bash start.sh
# Backend: http://localhost:8001
# Frontend: http://localhost:5174
```

### ZugaApp Plugin Mode

ZugaLife can also run as a plugin inside [ZugaApp](https://github.com/Zuga-Technologies/ZugaApp), where it shares authentication, a Postgres database, and the credit system with other studios. The `plugin.ts` (frontend) and `plugin.py` (backend) files define the integration points.

### Running Separately

If you prefer to start the backend and frontend independently:

```bash
# Terminal 1 — Backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2 — Frontend
cd frontend
npm run dev
```

## Tech Stack

- **Frontend**: Vue 3, TypeScript, Tailwind CSS, Pinia, Vue Router, Lucide Icons
- **Backend**: FastAPI, SQLAlchemy (async), SQLite, Pydantic
- **AI**: Venice AI (optional — therapist, journal, meditation)
- **Shared**: ZugaCore (auth, database, theme, API client)

## License

[MIT](LICENSE) - Zuga Technologies

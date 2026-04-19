# ZugaLife Baseline Session 6 — Frontend Smoke + Cross-Repo Regression Caught

**Date:** 2026-04-19 (Sunday, late evening)
**Environment:** zugabot.ai live (Railway `zugaapp-v3`, production)
**Scope:** 4 critical user paths. No code changes planned.
**Actual outcome:** 4/4 paths verified. 1 live production regression caught + fixed cross-repo. Baseline audit CLOSED at 100%.

## Results

| # | Path | Verdict | Evidence |
|---|---|---|---|
| 1 | Goal create | PASS | WOOP fields live in `frontend/components/WoopGoalWizard.vue` (5-step Identity → Outcome → Visualize → Obstacle → Plan); `GoalsTab.vue:119` exposes 4 modes `'none' \| 'templates' \| 'custom' \| 'woop'`. Smoke initially used Custom mode (no WOOP prompts); WOOP wizard is a separate entry. Goal save worked. |
| 2 | Journal reflect | **PASS — after fix** | Pre-fix: backend surfaced `UnknownTaskError: Unknown task 'chat'` → 502 to user. **ROOT CAUSE**: Moonshot retirement (`31856d45` 2026-04-18) pruned `"chat"` and `"summarization"` from `ZugaApp/backend/core/ai/gateway.py:_ROUTING` on the assumption no callers remained; 6 ZugaLife embedded-mode callers were missed. **FIX**: commit `4433ef2` on ZugaApp restored both tasks routed to Venice (kimi-k2-5) + generalized `_estimate_call_cost` Venice ternary from hardcoded `task=="therapist"` to `provider_fn is call_venice`. Railway deploy via `railway up --detach` (GitHub webhook stalled per Session 4 precedent). Post-fix: first retry hit real Venice 429 (rate limit, non-regression), second retry returned 200 with a new reflection rendered. |
| 3 | Habit log | PASS | Streak incremented + XP toast fired per smoke operator. (AI insight path at `habits/routes.py:856 task="chat"` was NOT triggered — 7-day cooldown. Now fixed alongside journal reflect by the same commit.) |
| 4 | Meditation (Cartesia) | PASS — technical artifact captured | Railway log excerpt: `[MEDITATION] 26 TTS done, 9497747 bytes, provider=cartesia` + `[MEDITATION] 26 READY: body_scan medium 593s $0.1217 'The Calm Embrace of Night'`. `provider=cartesia` is emitted by `meditation/routes.py` itself — not inference. Generation survived a re-login mid-flight. Unaffected by the gateway regression because meditation uses `task="creative"|"creative_long"` which remained in `_ROUTING` post-0418. |

## Cross-repo regression full blast radius

Every ZugaLife `ai_call` using a task name pruned by Moonshot retirement was silently broken on Railway for ~24 hours (Apr 18 → Apr 19 evening):

| Call site | Task | User-visible? | Fix by this commit? |
|---|---|---|---|
| `journal/routes.py:66` (mood inference) | `chat` | Silent (mood stays null) | YES |
| `journal/routes.py:581` (reflect) | `chat` | Yes — Service Unavailable modal | YES (verified above) |
| `goals/routes.py:628` (AI Insight button) | `chat` | Yes — button error | YES |
| `habits/routes.py:856` (7-day cron insight) | `chat` | Delayed (cron hadn't fired) | YES |
| `forecasting/narrative.py:95` (weekly narrative) | `summarization` | Silent (fallback to empty/cached) | YES |
| `gamification/ai_challenges.py:335` (daily challenge) | `summarization` | Silent (fallback to static `CHALLENGE_POOL`) | YES |

Unaffected paths (verified in smoke): meditation outline/script (`creative`/`creative_long`), therapist chat (`therapist`).

## Observations queued for Session 7+

1. **Journal reflect has no retry/backoff on Venice 429.** Post-fix smoke exposed this directly — one successful reflect required two clicks because the first hit a real Venice rate limit. Gamification's `ai_challenges.py:333` has a 300s circuit breaker + `asyncio.wait_for` already; port that pattern to the 4 user-facing `task="chat"` sites (journal reflect + journal mood + goals AI Insight + habits insight) so transient Venice 429s self-heal instead of surfacing as errors.
2. **Cross-repo caller audit after provider retirement.** The `31856d45` retirement grep-audited ZugaApp callers only; ZugaLife callers were missed because ZugaLife sits in a separate repo but imports ZugaApp's gateway at Railway runtime. Generalize: retire a task from `_ROUTING` only after grepping BOTH `ZugaApp/` AND every studio repo that the Dockerfile bakes in (`ZugaLife`, `ZugaMotion`, `ZugaAudio`, etc.) for that task name. Added to memory as `feedback_cross_repo_caller_audit_after_retirement.md`.
3. Original Session 5 queue items carry forward: latent `(user_id, week_start)` race fixes; coordinated gateway dead-except cleanup; therapist docstring reconciliation; 11 MM pre-existing stashes triage; Railway GitHub webhook diagnosis; GITHUB_TOKEN Dockerfile leak; CrisisAuditLog model location.

## Baseline audit status at close of Session 6

- **9/11 folders SEALED** (themes cleaned + core/lifecycle + goals + journal + habits + therapist + meditation + forecasting + gamification)
- **2/11 TOURED** (core/ai, root entrypoints)
- **1/11 CLEANED** (themes ghost)
- **Frontend SMOKED** (this session)
- **1 cross-repo regression caught + shipped** (`ZugaApp 4433ef2`)
- **100% of ZugaLife LOC covered.** Next ZugaLife session is feature work, not baseline.

## Commits this session

- `ZugaApp 4433ef2` — `fix(core/ai): restore chat + summarization tasks routed to Venice`
- `ZugaLife <this commit>` — `chore(life/docs): session 6 smoke + regression capture`

## Entry-gate parity at close

- Railway deploy: `4433ef2` live, health 200, UnknownTaskError count post-restart = 0.
- ZugaApp Windows + origin/master symmetric at `4433ef2`.
- ZugaLife Windows + MM symmetric at `<this commit>`. 11 MM pre-existing stashes UNTOUCHED (unchanged since Session 3). Cartesia regression guard green. Active meditations: 0.
- MM standalone ZugaLife unaffected (uses its own local gateway, not ZugaApp's). No MM backend touch required for this fix.

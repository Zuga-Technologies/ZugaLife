# ZugaLife v0.5 — Meditation & Mindfulness

## What It Is

AI-generated personalized guided meditations with audio playback.
The system writes a meditation script based on the user's current state
(mood, habits, journal data), converts it to spoken audio via TTS,
layers ambient background sound, and plays it in-app.

## What It Is NOT (v1 Boundaries)

- NOT real-time adaptive (doesn't change mid-session based on biometrics)
- NOT a therapy tool (framed as "skill-building", never "treatment")
- NOT a library of pre-made recordings (every session is generated fresh)
- NOT multi-voice (single calm narrator voice per session)
- NOT music generation (ambient backgrounds are pre-made loops, not AI-generated)

---

## User Flow

```
1. User opens Meditation tab in ZugaLife
2. Sees remaining sessions badge ("3 of 3 remaining today")
3. Step 1 — Configure:
   - Pick meditation type (6 cards)
   - Pick duration (3 / 5 / 10 / 15 min)
   - Pick ambience (rain / ocean / forest / bowls / silence)
   - Pick voice (Shimmer or Nova)
   - Optional: type a focus area ("work stress", "can't sleep", etc.)
4. Step 2 — Preview & Confirm:
   - Summary card shows: type, duration, ambience, voice, focus
   - Personalization note: "Based on your recent moods and journal..."
   - "Generate Meditation" button + "Back" to edit
5. Loading state: "Creating your meditation..." (3-8 seconds)
6. Player view:
   - Play/pause button
   - Progress bar + time remaining
   - Session title (AI-generated, e.g. "Evening Body Scan for Tension Release")
   - Meditation type badge + duration
   - Live transcript (GPT Voice-style — text appears/scrolls as narration plays)
   - Star icon to favorite
   - Ambient sound volume control
7. User listens
8. After completion: optional mood check-in ("How do you feel now?" — can skip)
9. Session saved to history
```

---

## Meditation Types (6)

Each type has a clinically-grounded prompt template.

| # | Type | Description | Best For | Duration Range |
|---|------|-------------|----------|---------------|
| 1 | Mindful Breathing | Focus on breath rhythm, anchor to present moment | Anxiety, beginners, quick resets | 3-10 min |
| 2 | Body Scan | Progressive attention from toes to head | Tension, stress, sleep prep | 5-15 min |
| 3 | Loving-Kindness (Metta) | Send compassion to self, then others | Self-criticism, anger, loneliness | 5-10 min |
| 4 | Guided Visualization | Imagine a peaceful scene in detail | Relaxation, creativity | 5-10 min |
| 5 | Gratitude Reflection | Guided reflection on things you're thankful for | Low mood, perspective shift | 3-8 min |
| 6 | Stress Relief (MBSR-inspired) | Combines breathing + body awareness + letting go | Chronic stress, overwhelm | 5-15 min |

---

## Duration Options

- Quick: 3 minutes
- Short: 5 minutes
- Medium: 10 minutes
- Long: 15 minutes

---

## Personalization — The Edge

The AI script generator pulls context from the user's ZugaLife data:

| Data Source | How It's Used |
|-------------|---------------|
| Recent moods (last 3 days) | Tailors tone — anxious moods get grounding cues, sad moods get warmth |
| Journal entries (last 3) | Picks up themes — "work stress", "relationship", "health worry" |
| Habit streaks | Positive reinforcement — "You've meditated 3 days in a row" |
| Time of day | Morning = energizing, Evening = calming, Night = sleep-oriented |
| Session history | Avoids repetition — varies techniques and imagery |

If no data exists (new user), falls back to a general-purpose session.

---

## Clinical Psychology Grounding

### Language Rules (baked into all prompts)

DO use:
- Observation language: "notice", "be aware of", "observe", "allow"
- Permission language: "you might", "if you'd like", "when you're ready"
- Non-directive cues: "whatever comes up is okay"

DO NOT use:
- Directive language: "you should feel", "let go of your pain", "stop thinking"
- Diagnosing language: "your anxiety", "your depression"
- Invalidating phrases: "just relax", "don't worry", "clear your mind completely"

### Technique-Specific Structure

Each meditation type follows its validated clinical structure:
- Body Scan: MBSR protocol (toes -> feet -> legs -> hips -> torso -> hands -> arms -> shoulders -> neck -> face -> crown)
- Loving-Kindness: Traditional Metta progression (self -> loved one -> neutral person -> difficult person -> all beings)
- Breathing: 4-count cycles with natural pauses
- MBSR: Kabat-Zinn framework (awareness -> acceptance -> non-judgment)

### Safety

- Disclaimer on first use: "This is a wellness tool, not a substitute for professional mental health care."
- Body scan includes option to skip areas (for trauma/pain sensitivity) — FUTURE, not v1
- No sessions claim to "cure" or "treat" anything

---

## Technical Architecture

### Pipeline

```
User clicks "Generate"
        |
        v
[1] AI Script Generation (LLM)
    - Input: meditation type, duration, user context (mood/journal/habits)
    - Output: meditation script text with pause markers
    - Provider: Kimi K2.5 (cheap) or Claude (premium)
    - Cost: ~$0.001-0.005 per script
        |
        v
[2] Text-to-Speech (TTS)
    - Input: script text + voice instructions
    - Output: audio file (mp3)
    - Provider: OpenAI gpt-4o-mini-tts
    - Voice instruction: "Speak in a calm, gentle, soothing tone with slow pacing and natural pauses"
    - Cost: ~$0.01-0.02 per session
        |
        v
[3] Audio Assembly
    - Combine: TTS narration + ambient background loop
    - Background options: rain, ocean, forest, silence, singing bowls
    - Method: frontend audio layering (two <audio> elements, narration on top of ambience)
    - No server-side mixing needed in v1
        |
        v
[4] Playback + Save
    - Stream/serve audio to frontend player
    - Save session metadata to DB (type, duration, transcript, audio path)
```

### Backend — New Files

```
ZugaLife/backend/meditation/
    __init__.py          -- empty
    models.py            -- MeditationSession table
    schemas.py           -- request/response schemas
    prompts.py           -- 6 meditation prompt templates + personalization builder
    routes.py            -- endpoints
```

### Endpoints

| Method | Path | What | Auth | Status |
|--------|------|------|------|--------|
| POST | /api/life/meditation/generate | Generate a new meditation session | Yes | 201 |
| GET | /api/life/meditation/sessions | List past sessions | Yes | 200 |
| GET | /api/life/meditation/sessions/:id | Get session detail + audio URL | Yes | 200 |
| PATCH | /api/life/meditation/sessions/:id/favorite | Toggle favorite | Yes | 200 |
| PATCH | /api/life/meditation/sessions/:id/mood | Set post-session mood | Yes | 200 |
| DELETE | /api/life/meditation/sessions/:id | Delete a session | Yes | 204 |
| GET | /api/life/meditation/audio/:filename | Serve audio file | Yes | 200 |
| GET | /api/life/meditation/remaining | Get remaining sessions today | Yes | 200 |

### POST /generate Request Body

```json
{
    "type": "body_scan",          // one of 6 types
    "duration_minutes": 10,       // 3, 5, 10, or 15
    "ambience": "rain",           // rain, ocean, forest, bowls, silence
    "voice": "shimmer",           // shimmer (default) or nova
    "focus": "work stress"        // optional free-text focus area
}
```

### Database — MeditationSession

| Column | Type | Notes |
|--------|------|-------|
| id | int | PK |
| user_id | str | indexed |
| type | str | breathing, body_scan, loving_kindness, visualization, gratitude, stress_relief |
| duration_minutes | int | 3, 5, 10, 15 |
| ambience | str | rain, ocean, forest, bowls, silence |
| focus | str | nullable, user-provided focus area |
| title | str | AI-generated session title |
| transcript | text | full meditation script |
| audio_filename | str | path to generated audio file |
| model_used | str | which LLM wrote the script |
| tts_model | str | which TTS model voiced it |
| cost | float | total cost (script + TTS) |
| mood_before | str | nullable, emoji if user logged mood before |
| mood_after | str | nullable, emoji if user logged mood after |
| is_favorite | bool | default false, favorited sessions keep audio permanently |
| voice | str | "shimmer" or "nova" |
| created_at | datetime | timestamp |

### Rate Limit

- 3 sessions per day per user
- Enforced server-side (count sessions with created_at >= today)
- Returns 429 with "You've used all 3 meditation sessions today. Come back tomorrow."

### Budget

- Every generation goes through AI gateway (can_spend / record_spend)
- Estimated cost per session: $0.01-0.03 (script + TTS combined)
- At 3 sessions/day: max $0.09/day per user

---

## Frontend — Meditation Tab

Fourth tab in LifeView.vue (Journal | Habits | Goals | Meditate)

### Sub-views

1. **New Session** (default)
   - Remaining sessions badge ("2 of 3 remaining today")
   - Step 1 — Configure:
     - Type picker (6 cards with icons + short descriptions)
     - Duration button group (3 / 5 / 10 / 15 min)
     - Ambience picker (5 options with icons)
     - Voice toggle (Shimmer / Nova)
     - Optional focus text input
     - "Preview" button
   - Step 2 — Preview & Confirm:
     - Summary card (type, duration, ambience, voice, focus, personalization note)
     - "Generate Meditation" button + "Back" to edit
   - Loading state: calming animation + "Creating your meditation..."

2. **Player** (appears after generation)
   - Session title (AI-generated)
   - Play/pause button, progress bar, time elapsed / remaining
   - Live transcript (GPT Voice-style — text scrolls as narration plays)
   - Ambient sound volume slider
   - Star/favorite toggle icon
   - On completion: optional mood check-in overlay (emoji picker + skip button)

3. **History**
   - List of past sessions (date, type, duration, title, favorite star)
   - Filter: All / Favorites
   - Tap to replay (audio file served from backend)
   - Delete option (with confirmation)
   - Favorited sessions protected from auto-cleanup

---

## Ambient Sound Files

Pre-made ambient loops stored in `ZugaLife/frontend/assets/ambience/`:
- rain.mp3 (~2-3 MB, seamless loop)
- ocean.mp3
- forest.mp3
- bowls.mp3 (singing bowls)
- silence (no file needed)

These are NOT AI-generated. We source royalty-free ambient loops once.
Frontend layers them under the TTS narration at lower volume.

---

## Audio Storage

- Generated TTS audio saved as .mp3 files on the server
- Path: `ZugaLife/backend/data/meditation_audio/{user_id}/{session_id}.mp3`
- Served via `/api/life/meditation/audio/{filename}` endpoint
- Cleanup: sessions older than 30 days auto-delete audio files (FUTURE)

---

## Implementation Order

1. Backend: models + schemas + prompts (6 templates)
2. Backend: routes (generate + CRUD + audio serve)
3. Backend: OpenAI TTS integration in AI gateway
4. Plugin.py: wire meditation submodule, bump to v0.5.0
5. Source ambient sound files (royalty-free)
6. SCP to Mac Mini, restart, test via curl
7. Frontend: Meditation tab (type picker + player + history)
8. SCP frontend, test in browser
9. Commit + push + pull
10. Read Before You Ship walkthrough

---

## Decisions (Locked)

1. **Two-step generate**: Pick type + settings -> See preview summary -> Confirm & generate
2. **Post-session mood check-in**: Optional (prompt appears, user can skip)
3. **Favorites**: Yes — star icon on sessions, favorited sessions keep audio permanently
4. **Transcript**: Visible during playback, GPT Voice-style (text scrolls/highlights as narration plays)
5. **Voice**: Two options — Shimmer (gentle, default) and Nova (bright, alternative). User can pick.
6. **Remaining sessions**: Yes — show "2 of 3 remaining today" badge on the Meditate tab

---

## Future (NOT v0.5)

- Biometric integration (heart rate, breathing rate)
- Real-time adaptive sessions (adjusts mid-meditation)
- Custom voice cloning (user's own calming voice)
- Streaks + gamification ("7-day meditation streak!")
- Scheduled meditations (daily reminder at specific time)
- Multi-language support
- Body scan area skipping (trauma sensitivity)
- Audio cleanup (delete old files automatically)
- Offline mode (cache recent sessions)

---

*Spec version: 0.1 — Draft for review*
*Date: 2026-03-05*

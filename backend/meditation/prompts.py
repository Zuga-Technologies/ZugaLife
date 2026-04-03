"""ZugaLife meditation script AI prompt builder.

Builds prompts for the AI to generate personalized guided meditation scripts.
Each meditation type has a clinically-grounded template based on published
mindfulness research (MBSR, Metta, body scan protocols).

Content modes rotate to ensure variety across sessions:
  classic, story, science, metaphor, nature, wisdom

Language rules enforced across ALL templates:
  DO: "notice", "be aware of", "observe", "allow", "you might", "when you're ready"
  DO NOT: "you should feel", "let go of your pain", "just relax", "clear your mind"
"""

import random
from datetime import datetime

DAILY_SESSION_LIMIT = 3

# Emoji labels for mood context (reused from journal/habits)
_EMOJI_LABELS: dict[str, str] = {
    "\U0001f60a": "Happy", "\U0001f622": "Sad", "\U0001f620": "Angry",
    "\U0001f630": "Anxious", "\U0001f634": "Tired", "\U0001f929": "Excited",
    "\U0001f610": "Neutral", "\U0001f970": "Loved", "\U0001f624": "Frustrated",
    "\U0001f914": "Thoughtful", "\U0001f60c": "Calm", "\U0001f4aa": "Motivated",
}

# Word targets by length category (min, max).
# Calibrated against OpenAI TTS at speed 0.9 (~140 wpm effective).
# Hard ceiling prevents LLM from overshooting.
_WORD_TARGETS = {
    "quick": (200, 350),     # ~1-2 min
    "short": (500, 800),     # ~3-5 min
    "medium": (1200, 1800),  # ~8-10 min
    "long": (2500, 3500),    # ~15-20 min
}

_MAX_TOKENS = {
    "quick": 600,
    "short": 1400,
    "medium": 3000,
    "long": 4096,
}

_LENGTH_LABELS = {
    "quick": "1 to 2 minutes",
    "short": "3 to 5 minutes",
    "medium": "8 to 10 minutes",
    "long": "15 to 20 minutes",
}

# --- Content modes for variety ---

_CONTENT_MODES = {
    "classic": """CONTENT APPROACH — Classic Guided Meditation:
Focus on pure mindfulness technique. Guide the listener through the practice with
clear, patient instructions. Let silence do the work. This is traditional,
straightforward meditation guidance.""",

    "story": """CONTENT APPROACH — Story Journey (inspired by The Honest Guys):
Weave a gentle narrative journey throughout the meditation. Create a vivid, specific
setting — an enchanted forest with glowing fireflies, an ancient stone temple on a
mountainside, a starlit garden with a reflecting pool, a cozy cabin during a snowfall.
Guide the listener THROUGH the story with rich sensory details. The story IS the
meditation — relaxation happens through immersion, not instruction. Include small
discoveries along the way (a hidden path, a warm light, a gentle sound).""",

    "science": """CONTENT APPROACH — Science-Informed Meditation:
Naturally weave 2-3 neuroscience or psychology facts into the guidance. Examples you
may draw from (use naturally, don't lecture):
- "As you breathe slowly, your vagus nerve — the longest nerve in your body — signals
  your heart to slow down, activating your body's natural calm response..."
- "With each deep exhale, cortisol levels in your bloodstream begin to drop..."
- "Research shows that just eight weeks of regular practice can increase gray matter
  in the brain regions linked to memory and emotional regulation..."
- "Your brain can't easily tell the difference between a vividly imagined experience
  and reality — which is why this kind of focused attention is so powerful..."
Make facts feel like gentle revelations woven into the meditation, not a science class.""",

    "metaphor": """CONTENT APPROACH — Metaphor-Rich Meditation (inspired by ACT/Headspace):
Build the entire meditation around ONE central metaphor. Develop it slowly, return to
it throughout, and let it deepen. Choose from metaphors like:
- Thoughts as clouds drifting across a vast, open sky — you are the sky, not the clouds
- Your mind as a deep, still lake — ripples on the surface don't disturb the depths
- Stress as heavy stones in a backpack — notice each one, set them down one by one
- Breath as ocean waves — each inhale a wave arriving, each exhale a wave retreating
- Your body as an ancient tree — roots deep in the earth, branches open to the sky
- Emotions as weather — storms pass, sun returns, you are the landscape that endures
Paint the metaphor with vivid imagery. Let the listener FEEL it, not just understand it.""",

    "nature": """CONTENT APPROACH — Nature Immersion (inspired by Calm):
Create an extraordinarily vivid natural environment using ALL five senses in precise
detail. Choose ONE specific setting and make the listener FEEL they are there:
- A misty rainforest at dawn — droplets on fern leaves, distant bird calls, rich earth
- An alpine meadow in golden hour — wildflowers, cool breeze, distant peaks glowing
- A desert night under infinite stars — warm sand, cool air, absolute silence
- Coastal cliffs at sunset — salt spray, crashing waves, orange light on stone
- A Japanese garden in autumn — red maple leaves, koi pond, wooden bridge, bamboo
Focus on MICRO-DETAILS — the exact texture of bark, the temperature shift between
sun and shade, the specific bird species singing. Make it cinematic and immersive.""",

    "wisdom": """CONTENT APPROACH — Philosophical Wisdom Meditation:
Draw from ONE tradition of contemplative wisdom and let a single teaching guide the
session. Introduce the idea gently and let the meditation embody it:
- Buddhist: impermanence ("everything changes, and that's okay"), non-attachment,
  the guest house of emotions, beginner's mind
- Stoic: focus on what you can control, amor fati (love of fate), the view from above
  (imagining yourself from a great height, seeing how small worries are)
- Taoist: wu wei (effortless action), flowing like water around obstacles, balance
- Rumi/Sufi: "The wound is the place where the light enters you", the guest house poem
- Indigenous/Nature wisdom: interconnection of all things, sitting with ancestors
Share the wisdom as a brief story or parable, then let the meditation explore it.""",
}

# --- Technique-specific instructions ---

_TECHNIQUE_INSTRUCTIONS = {
    "breathing": """Generate a mindful breathing meditation.

Structure:
1. Opening: settle in, notice your body's contact with the surface beneath you
2. Bring attention to the natural rhythm of the breath — do NOT force any pattern
3. Guide several breath cycles with slow, patient counting
4. When the mind wanders (it will), gently guide attention back without judgment
5. Vary the breath awareness: nostrils, chest rising, belly expanding, full body
6. Gradually widen awareness from breath to the whole body
7. Closing: slowly return attention to the room

Include [PAUSE 3s] markers between transitions. Include [PAUSE 5s] for breath cycles.
Spend significant time in the breathing sections — don't rush through them.""",

    "body_scan": """Generate a body scan meditation following MBSR protocol.

Structure (progressive attention — do NOT skip regions):
1. Opening: settle in, take three deep breaths
2. Toes and feet — notice sensations without changing them
3. Lower legs and knees
4. Upper legs and hips
5. Lower back and abdomen
6. Upper back and chest
7. Hands and fingers
8. Arms and shoulders
9. Neck and throat
10. Face (jaw, cheeks, eyes, forehead)
11. Crown of the head
12. Whole body awareness
13. Closing: gently return to the room

For each region: "Bring your attention to [region]. Notice whatever sensations are
there — warmth, coolness, tingling, pressure, or nothing at all. Whatever you find
is okay." Spend TIME with each region — describe possible sensations, invite curiosity.

Include [PAUSE 5s] between body regions. Include [PAUSE 3s] within regions.""",

    "loving_kindness": """Generate a loving-kindness (Metta) meditation.

Structure (traditional Metta progression):
1. Opening: settle in, bring attention to the heart area
2. Self: direct warmth and compassion toward yourself
   - "May I be happy. May I be healthy. May I be safe. May I live with ease."
3. Loved one: picture someone you care about, send them the same wishes
4. Neutral person: someone you neither like nor dislike (a neighbor, cashier)
5. Difficult person: someone you have tension with (start small)
6. All beings: expand to everyone, everywhere
7. Closing: return to yourself, notice how you feel

For each stage, repeat the four phrases naturally (not robotically). Add color
and context — help the listener PICTURE each person, FEEL the warmth.
Use "you might" language — never force emotions.
Include [PAUSE 5s] between stages. Include [PAUSE 3s] between phrases.""",

    "visualization": """Generate a guided visualization meditation.

Structure:
1. Opening: close eyes, take three slow breaths
2. Set the scene: describe a peaceful setting in extraordinarily vivid sensory detail
3. Walk through the scene using all five senses, one at a time:
   - What do you see? (colors, light, movement, textures)
   - What do you hear? (water, birds, wind, leaves, distant sounds)
   - What do you feel? (warmth, breeze, ground underfoot, temperature)
   - What do you smell? (earth, flowers, salt air, pine, rain)
4. Find a resting place in the scene — sit or lie down
5. Spend time simply being present in this place — notice small details
6. Closing: slowly let the scene fade, return to your body in the room

Use rich, unhurried, CINEMATIC language. Paint the picture slowly. Each sense
gets its own dedicated section with multiple details.
Include [PAUSE 5s] after setting each sense. Include [PAUSE 3s] between details.""",

    "gratitude": """Generate a gratitude reflection meditation.

Structure:
1. Opening: settle in, place a hand on your heart if comfortable
2. Start with something small: a simple pleasure from today or this week
   - Guide them to notice the FEELING of gratitude, not just the thought
   - Describe what gratitude might feel like in the body (warmth, lightness)
3. Move to a person: someone whose presence you appreciate
   - Help them recall a SPECIFIC moment with this person
4. Move to yourself: something about yourself you're thankful for
   - This is often the hardest — give permission to struggle with it
5. Wider gratitude: something about being alive that you don't usually notice
   - The miracle of breath, of sight, of being here at all
6. Closing: sit with the accumulated warmth for a long moment

Never prescribe what to feel grateful for — use prompts like "you might think of..."
Include [PAUSE 5s] after each gratitude prompt (give time to think).
Include [PAUSE 3s] for transitions.""",

    "stress_relief": """Generate a stress relief meditation inspired by MBSR.

Structure:
1. Opening: acknowledge that stress is present without fighting it
   - "You don't need to fix anything right now. You're here. That's enough."
2. Three grounding breaths — feel the body's weight against the surface
3. Body check: scan for where stress lives in the body (jaw, shoulders, stomach)
   - Don't try to release it — just notice it with curiosity and kindness
   - Describe what stress might feel like (tightness, heat, buzzing)
4. Breathing with awareness: each exhale as an opportunity to soften (not force)
   - Guide several slow breath cycles here
5. Cognitive defusion: notice thoughts as thoughts, not facts
   - "If a worried thought appears, you might silently label it 'thinking'..."
   - "Imagine placing that thought on a leaf and watching it float downstream..."
6. Self-compassion moment: acknowledge this is hard, you're doing your best
7. Closing: three breaths, gentle return to the room

This meditation acknowledges difficulty rather than bypassing it.
Include [PAUSE 5s] during body check and thought observation.
Include [PAUSE 3s] between breath cycles.""",
}


def build_meditation_prompt(
    meditation_type: str,
    length: str,
    focus: str | None = None,
    mood_context: str | None = None,
    habit_context: str | None = None,
    journal_context: str | None = None,
    previous_titles: list[str] | None = None,
) -> str:
    """Build the full meditation script generation prompt."""
    word_min, word_max = _WORD_TARGETS.get(length, (1200, 1800))
    length_label = _LENGTH_LABELS.get(length, "8 to 10 minutes")
    technique = _TECHNIQUE_INSTRUCTIONS.get(
        meditation_type, _TECHNIQUE_INSTRUCTIONS["breathing"],
    )

    time_of_day = _get_time_context()
    content_mode = _pick_content_mode(previous_titles)

    personalization = _build_personalization(
        focus=focus,
        mood_context=mood_context,
        habit_context=habit_context,
        journal_context=journal_context,
        time_of_day=time_of_day,
    )

    anti_repetition = ""
    if previous_titles:
        titles = ", ".join(f'"{t}"' for t in previous_titles[-5:])
        anti_repetition = (
            f"\n\nPrevious session titles (create something COMPLETELY DIFFERENT "
            f"in tone, theme, and approach): {titles}"
        )

    return f"""You are a meditation guide creating a personalized guided meditation script. Your script will be converted to audio via text-to-speech, so write exactly what should be spoken aloud.

CRITICAL LANGUAGE RULES:
- Use observation language: "notice", "be aware of", "observe", "allow", "you might"
- Use permission language: "if you'd like", "when you're ready", "whatever feels right"
- NEVER use: "you should feel", "let go of your pain", "just relax", "clear your mind completely", "stop thinking"
- NEVER diagnose: "your anxiety", "your depression"
- NEVER give medical/therapeutic advice
- This is a wellness skill-building tool, NOT therapy

{content_mode}

PAUSE MARKERS:
- Include [PAUSE 3s] for short pauses (transitions, between sentences)
- Include [PAUSE 5s] for longer pauses (between sections, during breath cycles, reflection time)
- Use them VERY generously — a good meditation is 40% silence. Include at LEAST one pause marker every 2-3 sentences.

PACING (CRITICAL — this will be read aloud by TTS at slow speed):
- Write short sentences (8-15 words max). Let each thought breathe.
- Use "..." within sentences for natural hesitation: "And as you breathe in... notice..."
- When counting (breath cycles, etc.), write EACH number as a SEPARATE word with its own pause marker between them:
  CORRECT: "Breathe in... one... [PAUSE 3s] two... [PAUSE 3s] three... [PAUSE 3s] four..."
  WRONG: "1, 2, 3, 4" or "one two three four" or "one...two...three"
  Each number MUST have a [PAUSE 3s] between it and the next number.
- NEVER write bare digits (1, 2, 3). Always spell out: one, two, three, four, five, six.

LENGTH REQUIREMENT (CRITICAL — STRICTLY ENFORCED):
- This is a {length_label} meditation. Write EXACTLY {word_min} to {word_max} words of spoken content.
- Do NOT exceed {word_max} words. Going over is just as bad as going under.
- The word count includes spoken text only — pause markers [PAUSE Xs] do not count.
- If you reach {word_max} words, STOP and write the closing.

FORMAT:
- Write in second person ("you")
- Warm but not saccharine — genuine, calm, grounded
- First line must be the session TITLE (a short, evocative name — max 8 words)
- Second line must be empty
- Then the meditation script begins
{personalization}{anti_repetition}

TECHNIQUE:
{technique}

Write the meditation script now. Remember: title on line 1, blank line, then the script. This is a {length_label} meditation — stay within {word_min}-{word_max} words."""


def _pick_content_mode(previous_titles: list[str] | None = None) -> str:
    """Pick a content mode, avoiding the same mode too often."""
    modes = list(_CONTENT_MODES.keys())
    # Weighted random — favor variety, but any mode can appear
    mode = random.choice(modes)
    return _CONTENT_MODES[mode]


def _get_time_context() -> str:
    """Get time-of-day context for tone adjustment."""
    hour = datetime.now().hour
    if hour < 6:
        return "late night (very gentle, sleep-oriented tone)"
    elif hour < 12:
        return "morning (gentle awakening energy, setting intentions)"
    elif hour < 17:
        return "afternoon (grounding, midday reset)"
    elif hour < 21:
        return "evening (winding down, releasing the day)"
    else:
        return "night (very calm, preparing for sleep)"


def _build_personalization(
    focus: str | None = None,
    mood_context: str | None = None,
    habit_context: str | None = None,
    journal_context: str | None = None,
    time_of_day: str | None = None,
) -> str:
    """Build the personalization section of the prompt."""
    parts = []

    if time_of_day:
        parts.append(f"Time of day: {time_of_day}")

    if focus:
        parts.append(f"User's stated focus: \"{focus}\" — weave this theme naturally into the meditation")

    if mood_context:
        parts.append(f"Recent mood patterns:\n{mood_context}")

    if habit_context:
        parts.append(f"Recent habit patterns:\n{habit_context}")

    if journal_context:
        parts.append(f"Recent journal themes:\n{journal_context}")

    if not parts:
        return ""

    block = "\n".join(f"- {p}" for p in parts)
    return f"""

PERSONALIZATION CONTEXT (use subtly — don't explicitly reference data, just let it inform tone and themes):
{block}"""


def build_outline_prompt(
    meditation_type: str,
    length: str,
    focus: str | None = None,
    mood_context: str | None = None,
    habit_context: str | None = None,
    journal_context: str | None = None,
    previous_titles: list[str] | None = None,
) -> str:
    """Build a prompt for pass 1: structured outline for long meditations.

    Returns a prompt that asks the LLM to produce a detailed section-by-section
    outline with timing, content notes, and key phrases — but NOT the full script.
    """
    technique = _TECHNIQUE_INSTRUCTIONS.get(
        meditation_type, _TECHNIQUE_INSTRUCTIONS["breathing"],
    )
    time_of_day = _get_time_context()
    content_mode = _pick_content_mode(previous_titles)
    personalization = _build_personalization(
        focus=focus,
        mood_context=mood_context,
        habit_context=habit_context,
        journal_context=journal_context,
        time_of_day=time_of_day,
    )

    anti_repetition = ""
    if previous_titles:
        titles = ", ".join(f'"{t}"' for t in previous_titles[-5:])
        anti_repetition = (
            f"\n\nPrevious session titles (create something COMPLETELY DIFFERENT "
            f"in tone, theme, and approach): {titles}"
        )

    return f"""You are a meditation guide designing a detailed OUTLINE for a 15-to-20-minute guided meditation. This outline will be expanded into a full script in a second step.

{content_mode}

TECHNIQUE:
{technique}
{personalization}{anti_repetition}

Create a structured outline with exactly 6-8 sections. For each section, provide:

1. **TITLE**: A short name for the section (e.g., "Arrival & Settling")
2. **DURATION**: Target duration in minutes (total must equal 15-20 minutes)
3. **WORD TARGET**: How many words the expanded script should have for this section (total must be 3500+)
4. **CONTENT NOTES**: 3-5 bullet points describing exactly what happens — key imagery, specific phrases to use, sensory details, which pause markers go where
5. **TONE**: How this section should feel (e.g., "very slow and grounding", "gently uplifting")

FORMAT your outline EXACTLY like this:
Line 1: SESSION TITLE (a short, evocative name — max 8 words)
Line 2: (empty)
Line 3+: The outline sections

Example section format:
## Section 1: Arrival & Settling (3 min, ~500 words)
- Guide listener to find comfortable position
- Notice contact points: back against chair, feet on floor
- Three deep breaths with [PAUSE 5s] between each
- Tone: very slow, grounding, permission-giving

Make the outline DETAILED enough that a writer could expand each section independently. Include specific imagery, metaphors, and phrases — not just vague instructions.

The total meditation must fill 15-20 minutes when read aloud at a slow TTS pace (~165 words per minute). Plan for generous silence (40% of the meditation is pause markers)."""


def build_expansion_prompt(outline: str, section_count: int) -> str:
    """Build a prompt for pass 2: expand outline into full meditation script.

    Takes the outline from pass 1 and asks the LLM to write the complete
    spoken script with all pause markers, sensory details, and pacing.
    """
    return f"""You are a meditation guide. Below is a detailed outline for a 15-to-20-minute guided meditation. Your job is to expand it into the COMPLETE spoken script.

OUTLINE:
{outline}

CRITICAL RULES:
1. Write EVERYTHING that should be spoken aloud. This goes directly to text-to-speech.
2. Do NOT include section headers, notes, or metadata — only the spoken meditation.
3. The title from the outline's first line must be your first line too.
4. Second line must be empty, then the script begins.

LANGUAGE RULES:
- Use observation language: "notice", "be aware of", "observe", "allow", "you might"
- Use permission language: "if you'd like", "when you're ready", "whatever feels right"
- NEVER use: "you should feel", "let go of your pain", "just relax", "clear your mind completely"
- NEVER diagnose or give medical advice
- Write in second person ("you")
- Warm but not saccharine — genuine, calm, grounded

PAUSE MARKERS (use VERY generously — 40% of the meditation should be silence):
- [PAUSE 3s] for short pauses (transitions, between sentences) — every 2-3 sentences
- [PAUSE 5s] for longer pauses (between sections, during breath cycles, reflection)

PACING (this will be read aloud by TTS at slow speed):
- Write short sentences (8-15 words max)
- Use "..." for natural hesitation: "And as you breathe in... notice..."
- Spell out all numbers: one, two, three (NEVER 1, 2, 3)
- When counting breath cycles, each number gets its own [PAUSE 3s]

LENGTH (NON-NEGOTIABLE):
- You MUST write at least 3500 words of spoken content.
- The outline has {section_count} sections — expand EVERY section fully.
- Do not summarize or abbreviate ANY section. Each section must hit its word target from the outline.
- If you finish and it feels short, go back and add more sensory detail, more pauses, more gentle repetition.

Write the complete meditation script now. Title on line 1, blank line, then the full spoken script."""


def build_title_system_instruction() -> str:
    """TTS voice instruction for meditation narration."""
    return (
        "Speak in a calm, gentle, soothing tone with slow pacing. "
        "Leave natural pauses between sentences. "
        "This is a guided meditation — the listener has their eyes closed. "
        "Speak as if you are sitting quietly beside someone, guiding them gently."
    )

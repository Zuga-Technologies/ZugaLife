"""ZugaLife journal CRUD + AI reflection endpoints."""

import asyncio
import io
import logging
import sys
import zipfile
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import asc, desc, func, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.journal.models"]
_schemas = sys.modules["zugalife.journal.schemas"]
_prompts = sys.modules["zugalife.journal.prompts"]

# Pull into globals for FastAPI annotation resolution
JournalEntry = _models.JournalEntry
JournalReflection = _models.JournalReflection
JournalCreateRequest = _schemas.JournalCreateRequest
JournalEntryResponse = _schemas.JournalEntryResponse
JournalEntryBrief = _schemas.JournalEntryBrief
JournalListResponse = _schemas.JournalListResponse
JournalReflectResponse = _schemas.JournalReflectResponse

# Reuse mood emoji → label mapping from prompts
_EMOJI_LABELS = _prompts._EMOJI_LABELS
MAX_REFLECTIONS = _prompts.MAX_REFLECTIONS_PER_ENTRY

def _get_gam_engine():
    """Lazy lookup — gamification loads after journal in plugin.py."""
    return sys.modules.get("zugalife.gamification.engine")

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/life/journal", tags=["life-journal"])


async def _infer_mood(entry_id: int, content: str, user_id: str = "", user_email: str = "") -> None:
    """Background task: classify journal mood via AI and update the entry."""
    try:
        from core.ai.gateway import ai_call
    except ImportError:
        return  # Standalone mode — no AI available

    prompt = _prompts.build_mood_inference_prompt(content)

    try:
        ai_response = await ai_call(
            prompt, task="chat", max_tokens=256,
            user_id=user_id or None, user_email=user_email or None,
        )
    except Exception:
        log.warning("Mood inference failed for entry %d", entry_id)
        return

    # Parse: response should be a single emoji character
    emoji = ai_response.content.strip()
    label = _EMOJI_LABELS.get(emoji)
    if not label:
        log.warning("Mood inference returned invalid emoji %r for entry %d", emoji, entry_id)
        return

    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry and entry.mood_emoji is None:
            entry.mood_emoji = emoji
            entry.mood_label = label


@router.post("", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(
    body: JournalCreateRequest,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new journal entry."""
    mood_label = None
    if body.mood_emoji:
        mood_label = _EMOJI_LABELS.get(body.mood_emoji)
        if not mood_label:
            raise HTTPException(status_code=422, detail="Invalid mood emoji")

    async with get_session() as session:
        entry = JournalEntry(
            user_id=user.id,
            title=body.title,
            content=body.content,
            mood_emoji=body.mood_emoji,
            mood_label=mood_label,
            tags=",".join(body.tags) if body.tags else None,
        )
        session.add(entry)
        await session.flush()
        await session.refresh(entry)
        response = JournalEntryResponse.model_validate(entry)
        entry_id = entry.id

        # Emit webhook event (fire-and-forget)
        try:
            from core.events.bus import event_bus
            asyncio.create_task(event_bus.emit("life:journal_created", {
                "entry_id": entry.id,
                "title": body.title or "Untitled",
                "mood_emoji": body.mood_emoji,
            }, user_id=user.id))
        except Exception:
            pass

        gam = _get_gam_engine()
        if gam:
            try:
                await gam.award_xp(
                    session, user_id=user.id,
                    source="journal_entry",
                    description=f"Wrote: {(body.title or 'Untitled')[:50]}",
                )
            except Exception:
                log.warning("XP award failed for %s", user.id, exc_info=True)

    # Fire background mood inference if user didn't tag manually
    if not body.mood_emoji:
        background_tasks.add_task(_infer_mood, entry_id, body.content, user.id, user.email)

    return response


@router.get("", response_model=JournalListResponse)
async def list_journal_entries(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user),
):
    """List journal entries with pagination. Returns brief previews."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with get_session() as session:
        # Get total count
        count_result = await session.execute(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.user_id == user.id,
                JournalEntry.created_at >= since,
            )
        )
        total = count_result.scalar_one()

        # Get entries
        result = await session.execute(
            select(JournalEntry)
            .where(
                JournalEntry.user_id == user.id,
                JournalEntry.created_at >= since,
            )
            .order_by(desc(JournalEntry.created_at))
            .offset(offset)
            .limit(limit)
        )
        entries = result.scalars().all()

        briefs = [
            JournalEntryBrief(
                id=e.id,
                title=e.title,
                content_preview=e.content[:200],
                mood_emoji=e.mood_emoji,
                mood_label=e.mood_label,
                tags=[t.strip() for t in e.tags.split(",") if t.strip()] if e.tags else [],
                reflection_count=len(e.reflections),
                created_at=e.created_at,
            )
            for e in entries
        ]

    return JournalListResponse(entries=briefs, total=total)


# ---------------------------------------------------------------------------
# Export (MUST be before /{entry_id} to avoid route shadowing)
# ---------------------------------------------------------------------------

def _entry_to_markdown(entry: "JournalEntry") -> str:
    """Convert a JournalEntry to a markdown string with YAML frontmatter."""
    created = entry.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = entry.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build frontmatter
    lines = ["---"]
    if entry.title:
        safe_title = entry.title.replace('"', '\\"')
        lines.append(f'title: "{safe_title}"')
    lines.append(f"date: {created}")
    lines.append(f"updated: {updated}")
    if entry.mood_emoji:
        lines.append(f'mood: "{entry.mood_emoji}"')
    if entry.mood_label:
        lines.append(f'mood_label: "{entry.mood_label}"')
    lines.append("tags: [journal, zugalife]")
    lines.append("source: zugalife")
    lines.append(f"entry_id: {entry.id}")
    lines.append("---")
    lines.append("")

    if entry.title:
        lines.append(f"# {entry.title}")
        lines.append("")

    lines.append(entry.content)

    if entry.reflections:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## AI Reflections")
        lines.append("")
        for i, ref in enumerate(entry.reflections, 1):
            if len(entry.reflections) > 1:
                lines.append(f"### Reflection {i}")
                lines.append("")
            lines.append(ref.content)
            ref_date = ref.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append("")
            lines.append(f"*Generated {ref_date} · {ref.model_used}*")
            lines.append("")

    return "\n".join(lines)


def _entry_to_obsidian(entry: "JournalEntry") -> str:
    """Convert a JournalEntry to Obsidian-native markdown with Properties."""
    created = entry.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = entry.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_short = entry.created_at.strftime("%Y-%m-%d")

    lines = ["---"]
    if entry.title:
        safe_title = entry.title.replace('"', '\\"')
        lines.append(f'title: "{safe_title}"')
    lines.append(f"date: {date_short}")
    lines.append(f"created: {created}")
    lines.append(f"updated: {updated}")

    # Obsidian Properties: mood as dedicated fields
    if entry.mood_emoji:
        lines.append(f'mood: "{entry.mood_emoji}"')
    if entry.mood_label:
        lines.append(f'mood_label: "{entry.mood_label}"')

    # Tags as YAML list (Obsidian reads these into its tag index)
    tags = ["journal", "zugalife"]
    if hasattr(entry, "tags") and entry.tags:
        raw = entry.tags if isinstance(entry.tags, list) else entry.tags.split(",")
        for t in raw:
            clean = t.strip().lower().replace(" ", "-")
            if clean and clean not in tags:
                tags.append(clean)
    lines.append("tags:")
    for t in tags:
        lines.append(f"  - {t}")

    lines.append("source: zugalife")
    lines.append(f"entry_id: {entry.id}")
    lines.append("---")
    lines.append("")

    if entry.title:
        lines.append(f"# {entry.title}")
        lines.append("")

    lines.append(entry.content)

    if entry.reflections:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## AI Reflections")
        lines.append("")
        for i, ref in enumerate(entry.reflections, 1):
            if len(entry.reflections) > 1:
                lines.append(f"### Reflection {i}")
                lines.append("")
            lines.append(ref.content)
            ref_date = ref.created_at.strftime("%Y-%m-%d %H:%M")
            lines.append("")
            lines.append(f"*Generated {ref_date} · {ref.model_used}*")
            lines.append("")

    return "\n".join(lines)


def _safe_filename(title: str | None, date: datetime, entry_id: int) -> str:
    """Generate a filesystem-safe filename for an entry."""
    date_str = date.strftime("%Y-%m-%d")
    if title:
        safe = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
        safe = safe.strip()[:60]
        if safe:
            return f"{date_str} - {safe}.md"
    return f"{date_str} - entry-{entry_id}.md"


@router.get("/export")
async def export_journal(
    format: str = Query("markdown", pattern="^(markdown|json|obsidian)$"),
    start: str | None = Query(None, description="Start date YYYY-MM-DD"),
    end: str | None = Query(None, description="End date YYYY-MM-DD"),
    user: CurrentUser = Depends(get_current_user),
):
    """Export journal entries as a ZIP of markdown files or JSON."""
    since = None
    until = None
    if start:
        try:
            since = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(400, "Invalid start date — use YYYY-MM-DD")
    if end:
        try:
            until = datetime.strptime(end, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc,
            )
        except ValueError:
            raise HTTPException(400, "Invalid end date — use YYYY-MM-DD")

    async with get_session() as session:
        stmt = (
            select(JournalEntry)
            .where(JournalEntry.user_id == user.id)
            .order_by(asc(JournalEntry.created_at))
        )
        if since:
            stmt = stmt.where(JournalEntry.created_at >= since)
        if until:
            stmt = stmt.where(JournalEntry.created_at <= until)

        result = await session.execute(stmt)
        entries = result.scalars().all()

        if not entries:
            raise HTTPException(404, "No journal entries found for the given range")

        if format == "json":
            import json as json_lib

            data = []
            for e in entries:
                data.append({
                    "id": e.id,
                    "title": e.title,
                    "content": e.content,
                    "mood_emoji": e.mood_emoji,
                    "mood_label": e.mood_label,
                    "created_at": e.created_at.isoformat(),
                    "updated_at": e.updated_at.isoformat(),
                    "reflections": [
                        {
                            "content": r.content,
                            "model_used": r.model_used,
                            "created_at": r.created_at.isoformat(),
                        }
                        for r in e.reflections
                    ],
                })

            json_bytes = json_lib.dumps(data, indent=2, ensure_ascii=False).encode()
            return StreamingResponse(
                io.BytesIO(json_bytes),
                media_type="application/json",
                headers={
                    "Content-Disposition": "attachment; filename=zugalife-journal.json",
                },
            )

        # Obsidian vault export — YYYY/MM/ folder structure with Obsidian Properties
        if format == "obsidian":
            buf = io.BytesIO()
            seen_filenames: set[str] = set()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for entry in entries:
                    md_content = _entry_to_obsidian(entry)
                    year = entry.created_at.strftime("%Y")
                    month = entry.created_at.strftime("%m")
                    filename = _safe_filename(entry.title, entry.created_at, entry.id)

                    full_path = f"ZugaLife Journal/{year}/{month}/{filename}"
                    if full_path in seen_filenames:
                        base = filename.rsplit(".md", 1)[0]
                        full_path = f"ZugaLife Journal/{year}/{month}/{base} ({entry.id}).md"
                    seen_filenames.add(full_path)

                    zf.writestr(full_path, md_content)

            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type="application/zip",
                headers={
                    "Content-Disposition": "attachment; filename=zugalife-obsidian-vault.zip",
                },
            )

        buf = io.BytesIO()
        seen_filenames_md: set[str] = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry in entries:
                md_content = _entry_to_markdown(entry)
                filename = _safe_filename(entry.title, entry.created_at, entry.id)

                if filename in seen_filenames_md:
                    base = filename.rsplit(".md", 1)[0]
                    filename = f"{base} ({entry.id}).md"
                seen_filenames_md.add(filename)

                zf.writestr(f"zugalife-journal/{filename}", md_content)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=zugalife-journal.zip",
        },
    )


@router.get("/{entry_id}/export")
async def export_single_entry(
    entry_id: int,
    format: str = Query("markdown", pattern="^(markdown|json|obsidian)$"),
    user: CurrentUser = Depends(get_current_user),
):
    """Export a single journal entry as Markdown (.md) or JSON file."""
    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if not entry or entry.user_id != user.id:
            raise HTTPException(status_code=404, detail="Entry not found")

        if format == "json":
            import json as json_lib

            data = {
                "id": entry.id,
                "title": entry.title,
                "content": entry.content,
                "mood_emoji": entry.mood_emoji,
                "mood_label": entry.mood_label,
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat(),
                "reflections": [
                    {
                        "content": r.content,
                        "model_used": r.model_used,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in entry.reflections
                ],
            }
            json_bytes = json_lib.dumps(data, indent=2, ensure_ascii=False).encode()
            filename = _safe_filename(entry.title, entry.created_at, entry.id).replace(".md", ".json")
            return StreamingResponse(
                io.BytesIO(json_bytes),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )

        # Obsidian or standard Markdown
        if format == "obsidian":
            md_content = _entry_to_obsidian(entry)
        else:
            md_content = _entry_to_markdown(entry)
    filename = _safe_filename(entry.title, entry.created_at, entry.id)
    return StreamingResponse(
        io.BytesIO(md_content.encode()),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Get a single journal entry with all reflections."""
    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if not entry or entry.user_id != user.id:
            raise HTTPException(status_code=404, detail="Entry not found")

        return JournalEntryResponse.model_validate(entry)


@router.post(
    "/{entry_id}/reflect",
    response_model=JournalReflectResponse,
)
async def reflect_on_entry(
    entry_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate an AI reflection on a journal entry. Costs credits."""
    try:
        from core.ai.gateway import BudgetExhaustedError, PromptBlockedError, ai_call
    except ImportError:
        raise HTTPException(
            status_code=503, detail="AI reflections not available in standalone mode",
        )

    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if not entry or entry.user_id != user.id:
            raise HTTPException(status_code=404, detail="Entry not found")

        if len(entry.reflections) >= MAX_REFLECTIONS:
            raise HTTPException(
                status_code=429,
                detail=f"Maximum {MAX_REFLECTIONS} reflections per entry",
            )

        # Build prompt with anti-repetition context
        previous = [r.content for r in entry.reflections]
        prompt = _prompts.build_reflection_prompt(
            journal_content=entry.content,
            title=entry.title,
            mood_emoji=entry.mood_emoji,
            previous_reflections=previous if previous else None,
        )

        # AI call — task="chat" routes to Kimi K2.5 (cheapest)
        from core.ai.gateway import CreditBlockedError
        try:
            ai_response = await ai_call(
                prompt, task="chat", max_tokens=2048,
                user_id=user.id, user_email=user.email,
            )
        except (BudgetExhaustedError, CreditBlockedError):
            raise HTTPException(
                status_code=402, detail="Daily AI budget exhausted",
            )
        except PromptBlockedError:
            raise HTTPException(
                status_code=400, detail="Content blocked by security filter",
            )

        reflection = JournalReflection(
            journal_entry_id=entry.id,
            content=ai_response.content,
            model_used=ai_response.model,
            cost=ai_response.cost,
        )
        session.add(reflection)
        await session.flush()
        await session.refresh(reflection)

        # Award XP + check daily challenge completion for reflections
        gam = _get_gam_engine()
        if gam:
            try:
                await gam.award_xp(
                    session, user_id=user.id,
                    source="journal_entry",
                    description=f"AI reflection on: {(entry.title or 'Untitled')[:50]}",
                )
            except Exception:
                log.warning("XP award failed for reflection %s", user.id, exc_info=True)

        new_total = len(entry.reflections) + 1  # +1 for the one just created
        remaining = MAX_REFLECTIONS - new_total

        return JournalReflectResponse(
            reflection=_schemas.JournalReflectionResponse.model_validate(
                reflection,
            ),
            remaining=remaining,
        )


@router.delete("/{entry_id}", status_code=204)
async def delete_journal_entry(
    entry_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a journal entry and all its reflections (cascade)."""
    async with get_session() as session:
        result = await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()

        if not entry or entry.user_id != user.id:
            raise HTTPException(status_code=404, detail="Entry not found")

        await session.delete(entry)

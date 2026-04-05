"""ZugaLife life goals endpoints."""

import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.goals.models"]
_schemas = sys.modules["zugalife.goals.schemas"]
_templates_mod = sys.modules["zugalife.goals.templates"]

# Pull into globals for FastAPI annotation resolution
GoalDefinition = _models.GoalDefinition
GoalMilestone = _models.GoalMilestone
GoalHabitLink = _models.GoalHabitLink

GoalCreateRequest = _schemas.GoalCreateRequest
GoalFromTemplateRequest = _schemas.GoalFromTemplateRequest
GoalUpdateRequest = _schemas.GoalUpdateRequest
MilestoneCreateRequest = _schemas.MilestoneCreateRequest
MilestoneUpdateRequest = _schemas.MilestoneUpdateRequest
HabitLinkRequest = _schemas.HabitLinkRequest
GoalResponse = _schemas.GoalResponse
GoalListResponse = _schemas.GoalListResponse
MilestoneResponse = _schemas.MilestoneResponse
LinkedHabitResponse = _schemas.LinkedHabitResponse
GoalTemplateResponse = _schemas.GoalTemplateResponse

GOAL_TEMPLATES = _templates_mod.GOAL_TEMPLATES

def _get_gam_engine():
    """Lazy lookup — gamification loads after goals in plugin.py."""
    return sys.modules.get("zugalife.gamification.engine")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/life/goals", tags=["life-goals"])


# --- Habit model access (lazy, avoids circular imports) ---

def _get_habit_models():
    """Get habit models from sys.modules (loaded by plugin.py)."""
    return sys.modules["zugalife.habits.models"]


async def _build_linked_habits(
    session, goal: GoalDefinition, user_id: str,
) -> list[LinkedHabitResponse]:
    """Build linked habit responses with last 7 days completion data."""
    links = goal.habit_links or []
    if not links:
        return []

    habit_mod = _get_habit_models()
    HabitDefinition = habit_mod.HabitDefinition
    HabitLog = habit_mod.HabitLog

    habit_ids = [link.habit_id for link in links]
    since = date.today() - timedelta(days=6)  # 7 days including today

    # Fetch habit definitions
    habits_result = await session.execute(
        select(HabitDefinition).where(
            HabitDefinition.id.in_(habit_ids),
            HabitDefinition.user_id == user_id,
        )
    )
    habits_by_id = {h.id: h for h in habits_result.scalars().all()}

    # Fetch completion counts for last 7 days
    logs_result = await session.execute(
        select(HabitLog.habit_id, func.count(HabitLog.id))
        .where(
            HabitLog.habit_id.in_(habit_ids),
            HabitLog.user_id == user_id,
            HabitLog.log_date >= since,
            HabitLog.completed == True,
        )
        .group_by(HabitLog.habit_id)
    )
    completions = dict(logs_result.all())

    result = []
    for link in links:
        habit = habits_by_id.get(link.habit_id)
        if not habit:
            continue
        result.append(LinkedHabitResponse(
            habit_id=habit.id,
            habit_name=habit.name,
            habit_emoji=habit.emoji,
            days_completed=completions.get(habit.id, 0),
            days_total=7,
        ))
    return result


async def _goal_to_response(
    session, goal: GoalDefinition, user_id: str,
) -> GoalResponse:
    """Convert a GoalDefinition ORM instance to a response with milestone counts and linked habits."""
    # Deduplicate milestones by ID — selectin loading with async sessions
    # can occasionally return duplicates when multiple eager relationships exist.
    seen_ids: set[int] = set()
    milestones = []
    for m in (goal.milestones or []):
        if m.id not in seen_ids:
            seen_ids.add(m.id)
            milestones.append(m)
    linked_habits = await _build_linked_habits(session, goal, user_id)

    return GoalResponse(
        id=goal.id,
        title=goal.title,
        description=goal.description,
        deadline=goal.deadline,
        is_completed=goal.is_completed,
        sort_order=goal.sort_order,
        completed_at=goal.completed_at,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
        template_key=goal.template_key,
        milestones=[MilestoneResponse.model_validate(m) for m in milestones],
        milestone_count=len(milestones),
        milestone_done=sum(1 for m in milestones if m.is_completed),
        linked_habits=linked_habits,
    )


# --- Templates ---


@router.get("/templates", response_model=list[GoalTemplateResponse])
async def list_templates(
    user: CurrentUser = Depends(get_current_user),
):
    """List available goal templates, marking which ones are already adopted."""
    async with get_session() as session:
        result = await session.execute(
            select(GoalDefinition.template_key)
            .where(
                GoalDefinition.user_id == user.id,
                GoalDefinition.template_key.isnot(None),
            )
        )
        adopted_keys = {row for row in result.scalars().all()}

    templates = []
    for key, tmpl in GOAL_TEMPLATES.items():
        templates.append(GoalTemplateResponse(
            key=key,
            title=tmpl["title"],
            description=tmpl["description"],
            suggested_habits=tmpl["suggested_habits"],
            already_adopted=key in adopted_keys,
        ))
    return templates


@router.post("/from-template", response_model=GoalResponse, status_code=201)
async def create_from_template(
    body: GoalFromTemplateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a goal from a template, auto-link matching habits, and seed milestones."""
    tmpl = GOAL_TEMPLATES.get(body.template_key)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    async with get_session() as session:
        # Check if already adopted
        existing = await session.execute(
            select(GoalDefinition.id).where(
                GoalDefinition.user_id == user.id,
                GoalDefinition.template_key == body.template_key,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Template already adopted")

        # Place at end of list
        max_order = await session.execute(
            select(func.max(GoalDefinition.sort_order))
            .where(GoalDefinition.user_id == user.id)
        )
        next_order = (max_order.scalar_one() or 0) + 1

        # Build milestones from template
        seed_milestones = [
            GoalMilestone(title=ms_title, sort_order=i)
            for i, ms_title in enumerate(tmpl.get("milestones", []))
        ]

        goal = GoalDefinition(
            user_id=user.id,
            title=tmpl["title"],
            description=tmpl["description"],
            template_key=body.template_key,
            sort_order=next_order,
            milestones=seed_milestones,
        )
        session.add(goal)
        await session.flush()

        # Auto-link matching habits
        habit_mod = _get_habit_models()
        HabitDefinition = habit_mod.HabitDefinition
        habits_result = await session.execute(
            select(HabitDefinition).where(
                HabitDefinition.user_id == user.id,
                HabitDefinition.name.in_(tmpl["suggested_habits"]),
                HabitDefinition.is_active == True,
            )
        )
        for habit in habits_result.scalars().all():
            goal.habit_links.append(GoalHabitLink(habit_id=habit.id))

        await session.flush()

        return await _goal_to_response(session, goal, user.id)


# --- Goal CRUD ---


@router.get("", response_model=GoalListResponse)
async def list_goals(
    user: CurrentUser = Depends(get_current_user),
):
    """List all goals split into active and completed, with milestones and linked habits."""
    async with get_session() as session:
        result = await session.execute(
            select(GoalDefinition)
            .where(GoalDefinition.user_id == user.id)
            .order_by(GoalDefinition.sort_order, GoalDefinition.id)
        )
        goals = result.scalars().all()

        active = []
        completed = []
        for g in goals:
            resp = await _goal_to_response(session, g, user.id)
            if g.is_completed:
                completed.append(resp)
            else:
                active.append(resp)

    return GoalListResponse(active=active, completed=completed)


@router.post("", response_model=GoalResponse, status_code=201)
async def create_goal(
    body: GoalCreateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new custom life goal."""
    async with get_session() as session:
        max_order = await session.execute(
            select(func.max(GoalDefinition.sort_order))
            .where(GoalDefinition.user_id == user.id)
        )
        next_order = (max_order.scalar_one() or 0) + 1

        goal = GoalDefinition(
            user_id=user.id,
            title=body.title,
            description=body.description,
            deadline=body.deadline,
            sort_order=next_order,
        )
        session.add(goal)
        await session.flush()
        await session.refresh(goal)

        return await _goal_to_response(session, goal, user.id)


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: int,
    body: GoalUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update goal fields (title, description, deadline, sort_order)."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)

        if "title" in body.model_fields_set and body.title is not None:
            goal.title = body.title
        if "description" in body.model_fields_set:
            goal.description = body.description
        if "deadline" in body.model_fields_set:
            goal.deadline = body.deadline
        if body.sort_order is not None:
            goal.sort_order = body.sort_order

        await session.flush()
        await session.refresh(goal)

        return await _goal_to_response(session, goal, user.id)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a goal and cascade-delete its milestones and habit links."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)
        await session.delete(goal)


@router.patch("/{goal_id}/complete", response_model=GoalResponse)
async def toggle_goal_complete(
    goal_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Toggle a goal's completed status."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)

        goal.is_completed = not goal.is_completed
        goal.completed_at = (
            datetime.now(timezone.utc) if goal.is_completed else None
        )

        await session.flush()
        await session.refresh(goal)

        # Emit webhook event for goal completion (fire-and-forget)
        if goal.is_completed:
            try:
                from core.events.bus import event_bus
                asyncio.create_task(event_bus.emit("life:goal_completed", {
                    "goal_id": goal.id,
                    "title": goal.title,
                }, user_id=user.id))
            except Exception:
                pass

        if goal.is_completed and _get_gam_engine():
            try:
                await _get_gam_engine().award_xp(
                    session, user_id=user.id,
                    source="goal_milestone",
                    description=f"Completed goal: {goal.title[:50]}",
                )
            except Exception:
                logger.warning("XP award failed for %s", user.id, exc_info=True)

        return await _goal_to_response(session, goal, user.id)


# --- Habit Links ---


@router.post("/{goal_id}/habits", response_model=GoalResponse, status_code=201)
async def link_habit(
    goal_id: int,
    body: HabitLinkRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Link a habit to a goal."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)

        # Verify habit belongs to user
        habit_mod = _get_habit_models()
        HabitDefinition = habit_mod.HabitDefinition
        habit_result = await session.execute(
            select(HabitDefinition).where(
                HabitDefinition.id == body.habit_id,
                HabitDefinition.user_id == user.id,
            )
        )
        if not habit_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Habit not found")

        # Check if already linked
        existing = await session.execute(
            select(GoalHabitLink.id).where(
                GoalHabitLink.goal_id == goal.id,
                GoalHabitLink.habit_id == body.habit_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Habit already linked")

        link = GoalHabitLink(goal_id=goal.id, habit_id=body.habit_id)
        session.add(link)
        await session.flush()
        await session.refresh(goal)

        return await _goal_to_response(session, goal, user.id)


@router.delete("/{goal_id}/habits/{habit_id}", status_code=204)
async def unlink_habit(
    goal_id: int,
    habit_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Unlink a habit from a goal."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)

        result = await session.execute(
            select(GoalHabitLink).where(
                GoalHabitLink.goal_id == goal.id,
                GoalHabitLink.habit_id == habit_id,
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            raise HTTPException(status_code=404, detail="Habit link not found")

        await session.delete(link)


# --- Milestone CRUD ---


@router.post("/{goal_id}/milestones", response_model=MilestoneResponse, status_code=201)
async def create_milestone(
    goal_id: int,
    body: MilestoneCreateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Add a milestone to a goal."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)

        max_order = await session.execute(
            select(func.max(GoalMilestone.sort_order))
            .where(GoalMilestone.goal_id == goal.id)
        )
        next_order = (max_order.scalar_one() or 0) + 1

        milestone = GoalMilestone(
            goal_id=goal.id,
            title=body.title,
            sort_order=next_order,
        )
        session.add(milestone)
        await session.flush()
        await session.refresh(milestone)

    return MilestoneResponse.model_validate(milestone)


@router.patch("/{goal_id}/milestones/{milestone_id}", response_model=MilestoneResponse)
async def update_milestone(
    goal_id: int,
    milestone_id: int,
    body: MilestoneUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Update or toggle a milestone."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)
        milestone = await _get_milestone(session, milestone_id, goal.id)

        if "title" in body.model_fields_set and body.title is not None:
            milestone.title = body.title
        if body.sort_order is not None:
            milestone.sort_order = body.sort_order

        if body.is_completed is not None:
            milestone.is_completed = body.is_completed
            milestone.completed_at = (
                datetime.now(timezone.utc) if body.is_completed else None
            )

        await session.flush()
        await session.refresh(milestone)

        if body.is_completed and _get_gam_engine():
            try:
                await _get_gam_engine().award_xp(
                    session, user_id=user.id,
                    source="goal_milestone",
                    description=f"Completed milestone: {milestone.title[:50]}",
                )
            except Exception:
                logger.warning("XP award failed for %s", user.id, exc_info=True)

    return MilestoneResponse.model_validate(milestone)


@router.delete("/{goal_id}/milestones/{milestone_id}", status_code=204)
async def delete_milestone(
    goal_id: int,
    milestone_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a milestone."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)
        milestone = await _get_milestone(session, milestone_id, goal.id)
        await session.delete(milestone)


# --- Recommit (missed deadline) ---


from pydantic import BaseModel as _BaseModel

class RecommitRequest(_BaseModel):
    new_deadline: date | None = None


@router.post("/{goal_id}/recommit", response_model=GoalResponse)
async def recommit_goal(
    goal_id: int,
    body: RecommitRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Recommit to a goal — push deadline forward after missing it."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)
        if goal.is_completed:
            raise HTTPException(status_code=400, detail="Goal is already completed")

        if body.new_deadline:
            goal.deadline = body.new_deadline
        else:
            # Default: push 30 days from today
            goal.deadline = date.today() + timedelta(days=30)

        await session.flush()
        await session.refresh(goal)
        return await _goal_to_response(session, goal, user.id)


# --- AI Goal Insights ---


@router.post("/{goal_id}/insight")
async def goal_insight(
    goal_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate an AI insight for a specific goal based on milestone and habit data."""
    async with get_session() as session:
        goal = await _get_user_goal(session, goal_id, user.id)
        linked = await _build_linked_habits(session, goal, user_id=user.id)

        milestones = goal.milestones or []
        done = sum(1 for m in milestones if m.is_completed)
        total = len(milestones)

        # Build context
        habit_summary = "\n".join(
            f"- {lh.habit_name}: {lh.days_completed}/{lh.days_total} days this week"
            for lh in linked
        ) or "No linked habits"

        milestone_summary = "\n".join(
            f"- {'[x]' if m.is_completed else '[ ]'} {m.title}"
            for m in milestones
        ) or "No milestones"

        deadline_info = ""
        if goal.deadline:
            days_left = (goal.deadline - date.today()).days
            if days_left > 0:
                deadline_info = f"Deadline: {goal.deadline} ({days_left} days remaining)"
            elif days_left == 0:
                deadline_info = f"Deadline: TODAY ({goal.deadline})"
            else:
                deadline_info = f"Deadline: OVERDUE by {abs(days_left)} days (was {goal.deadline})"

        created_days_ago = (date.today() - goal.created_at.date()).days
        pct = round(done / total * 100) if total > 0 else 0

        prompt = f"""Analyze this goal and give a brief, actionable insight (2-3 sentences max).

Goal: {goal.title}
Description: {goal.description or 'None'}
Created: {created_days_ago} days ago
Progress: {done}/{total} milestones ({pct}%)
{deadline_info}

Milestones:
{milestone_summary}

Linked habit performance (last 7 days):
{habit_summary}

Based on milestone completion rate and habit consistency, tell the user:
1. Whether they're on pace to hit the deadline (if set)
2. One specific, actionable suggestion
Be direct and specific. Use the actual numbers."""

    try:
        from core.ai.gateway import ai_call, CreditBlockedError
        result = await ai_call(
            messages=[
                {"role": "system", "content": "You are a concise goal coach. Be direct, use data, no fluff."},
                {"role": "user", "content": prompt},
            ],
            task="chat",
            user_id=user.id,
            user_email=user.email,
            max_tokens=200,
        )
        return {"insight": result.content, "cost": result.cost}
    except CreditBlockedError:
        raise HTTPException(status_code=402, detail="Insufficient ZugaTokens")
    except Exception as e:
        # Fallback: generate a simple rule-based insight
        if total == 0:
            fallback = "Add milestones to break this goal into trackable steps — goals with milestones have 75% higher completion rates."
        elif pct == 0:
            fallback = "You haven't completed any milestones yet. Focus on the first one — momentum builds from small wins."
        elif goal.deadline and (goal.deadline - date.today()).days < 7 and pct < 50:
            fallback = f"Deadline is close but you're only {pct}% done. Consider extending the deadline or breaking remaining milestones into smaller steps."
        else:
            fallback = f"You're {pct}% through your milestones. {'Linked habits look consistent — keep it up.' if any(lh.days_completed >= 4 for lh in linked) else 'Try improving your linked habit consistency to build momentum.'}"
        return {"insight": fallback, "cost": 0}


# --- Private helpers ---


async def _get_user_goal(session, goal_id: int, user_id: str) -> GoalDefinition:
    """Fetch a goal ensuring it belongs to the user. Raises 404 if not found."""
    result = await session.execute(
        select(GoalDefinition).where(GoalDefinition.id == goal_id)
    )
    goal = result.scalar_one_or_none()
    if not goal or goal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


async def _get_milestone(session, milestone_id: int, goal_id: int) -> GoalMilestone:
    """Fetch a milestone ensuring it belongs to the goal. Raises 404 if not found."""
    result = await session.execute(
        select(GoalMilestone).where(
            GoalMilestone.id == milestone_id,
            GoalMilestone.goal_id == goal_id,
        )
    )
    milestone = result.scalar_one_or_none()
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return milestone

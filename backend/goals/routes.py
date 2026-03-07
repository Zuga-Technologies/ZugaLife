"""ZugaLife life goals endpoints."""

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
    milestones = goal.milestones or []
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

        goal = GoalDefinition(
            user_id=user.id,
            title=tmpl["title"],
            description=tmpl["description"],
            template_key=body.template_key,
            sort_order=next_order,
        )
        session.add(goal)
        await session.flush()

        # Seed milestones from template
        for i, ms_title in enumerate(tmpl.get("milestones", [])):
            milestone = GoalMilestone(
                goal_id=goal.id,
                title=ms_title,
                sort_order=i,
            )
            session.add(milestone)

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
            link = GoalHabitLink(goal_id=goal.id, habit_id=habit.id)
            session.add(link)

        await session.flush()
        await session.refresh(goal)

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

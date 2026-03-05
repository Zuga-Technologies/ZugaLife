"""ZugaLife life goals endpoints."""

import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

# Sibling modules pre-loaded by plugin.py into sys.modules
_models = sys.modules["zugalife.goals.models"]
_schemas = sys.modules["zugalife.goals.schemas"]

# Pull into globals for FastAPI annotation resolution
GoalDefinition = _models.GoalDefinition
GoalMilestone = _models.GoalMilestone

GoalCreateRequest = _schemas.GoalCreateRequest
GoalUpdateRequest = _schemas.GoalUpdateRequest
MilestoneCreateRequest = _schemas.MilestoneCreateRequest
MilestoneUpdateRequest = _schemas.MilestoneUpdateRequest
GoalResponse = _schemas.GoalResponse
GoalListResponse = _schemas.GoalListResponse
MilestoneResponse = _schemas.MilestoneResponse

router = APIRouter(prefix="/api/life/goals", tags=["life-goals"])


def _goal_to_response(goal: GoalDefinition) -> GoalResponse:
    """Convert a GoalDefinition ORM instance to a response with milestone counts."""
    milestones = goal.milestones or []
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
        milestones=[MilestoneResponse.model_validate(m) for m in milestones],
        milestone_count=len(milestones),
        milestone_done=sum(1 for m in milestones if m.is_completed),
    )


# --- Goal CRUD ---


@router.get("", response_model=GoalListResponse)
async def list_goals(
    user: CurrentUser = Depends(get_current_user),
):
    """List all goals split into active and completed, with milestones."""
    async with get_session() as session:
        result = await session.execute(
            select(GoalDefinition)
            .where(GoalDefinition.user_id == user.id)
            .order_by(GoalDefinition.sort_order, GoalDefinition.id)
        )
        goals = result.scalars().all()

    active = [_goal_to_response(g) for g in goals if not g.is_completed]
    completed = [_goal_to_response(g) for g in goals if g.is_completed]
    return GoalListResponse(active=active, completed=completed)


@router.post("", response_model=GoalResponse, status_code=201)
async def create_goal(
    body: GoalCreateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Create a new life goal."""
    async with get_session() as session:
        # Place at end of list
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

    return _goal_to_response(goal)


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

    return _goal_to_response(goal)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: int,
    user: CurrentUser = Depends(get_current_user),
):
    """Delete a goal and cascade-delete its milestones."""
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

    return _goal_to_response(goal)


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

        # Place at end
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

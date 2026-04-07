"""ZugaThemes API endpoints — CRUD, install, state, marketplace."""

import json
import logging
import sys
import uuid
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError

from core.auth.middleware import get_current_user
from core.auth.models import CurrentUser
from core.database.session import get_session

_models = sys.modules["zugalife.themes.models"]
_schemas = sys.modules["zugalife.themes.schemas"]

logger = logging.getLogger(__name__)

Theme = _models.Theme
ThemeInstall = _models.ThemeInstall
ThemeState = _models.ThemeState
ThemePurchase = _models.ThemePurchase
ThemeReview = _models.ThemeReview

ThemeCreateRequest = _schemas.ThemeCreateRequest
ThemeUpdateRequest = _schemas.ThemeUpdateRequest
ThemePublishRequest = _schemas.ThemePublishRequest
ThemeInstallRequest = _schemas.ThemeInstallRequest
ThemePositionUpdate = _schemas.ThemePositionUpdate
ThemeStateUpdate = _schemas.ThemeStateUpdate
ThemeReviewCreate = _schemas.ThemeReviewCreate

# Limits
MAX_THEMES_PER_USER = 50
MAX_INSTALLS_PER_STUDIO = 20
PLATFORM_CUT_PERCENT = 10
PAGE_SIZE = 20

# Valid studios that support themes
VALID_STUDIOS = {"life"}  # Expand as we add bridge APIs to other studios

# Valid categories
VALID_CATEGORIES = {"widget", "dashboard", "tracker", "visualization", "tool", "game"}

router = APIRouter(prefix="/api/life/themes", tags=["life-themes"])


# ---------------------------------------------------------------------------
# Theme CRUD
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
async def create_theme(body: ThemeCreateRequest, user: CurrentUser = Depends(get_current_user)):
    """Create a new theme (draft). Called by a2ui_theme_create or directly."""
    if body.studio not in VALID_STUDIOS:
        raise HTTPException(400, f"Studio '{body.studio}' does not support themes yet")

    if body.category and body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Invalid category: {body.category}")

    # Check user's theme count
    async with get_session() as session:
        count_q = await session.execute(
            select(func.count()).select_from(Theme).where(Theme.creator_id == user.id)
        )
        if count_q.scalar_one() >= MAX_THEMES_PER_USER:
            raise HTTPException(400, f"Maximum {MAX_THEMES_PER_USER} themes per user")

        theme_id = str(uuid.uuid4())
        theme = Theme(
            id=theme_id,
            creator_id=user.id,
            studio=body.studio,
            title=body.title,
            description=body.description,
            category=body.category or "widget",
            tags=json.dumps(body.tags) if body.tags else "[]",
            html=body.html,
            css=body.css,
            js=body.js,
            permissions=json.dumps([p.model_dump() for p in body.permissions]),
            status="draft",
        )
        session.add(theme)
        await session.commit()

        result = _theme_to_dict(theme)

    # Auto-install if position was provided
    if body.position:
        async with get_session() as session:
            install_id = str(uuid.uuid4())
            install = ThemeInstall(
                id=install_id,
                user_id=user.id,
                theme_id=theme_id,
                studio=body.studio,
                pos_x=body.position.x,
                pos_y=body.position.y,
                pos_w=body.position.w,
                pos_h=body.position.h,
            )
            session.add(install)
            await session.commit()
            result["install_id"] = install_id
            result["position"] = body.position.model_dump()

    return result


@router.get("/{theme_id}")
async def get_theme(theme_id: str, user: CurrentUser = Depends(get_current_user)):
    """Get a single theme by ID."""
    async with get_session() as session:
        theme = await _get_theme_or_404(session, theme_id)
        # Allow access if: creator, installed, or published+approved
        if theme.creator_id != user.id and not theme.published:
            raise HTTPException(404, "Theme not found")
        return _theme_to_dict(theme)


@router.put("/{theme_id}")
async def update_theme(theme_id: str, body: ThemeUpdateRequest, user: CurrentUser = Depends(get_current_user)):
    """Update a theme's code or metadata. Only creator can update."""
    async with get_session() as session:
        theme = await _get_theme_or_404(session, theme_id)
        if theme.creator_id != user.id:
            raise HTTPException(403, "Not your theme")

        if body.title is not None:
            theme.title = body.title
        if body.description is not None:
            theme.description = body.description
        if body.category is not None:
            if body.category not in VALID_CATEGORIES:
                raise HTTPException(400, f"Invalid category: {body.category}")
            theme.category = body.category
        if body.tags is not None:
            theme.tags = json.dumps(body.tags)
        if body.html is not None:
            theme.html = body.html
        if body.css is not None:
            theme.css = body.css
        if body.js is not None:
            theme.js = body.js
        if body.permissions is not None:
            theme.permissions = json.dumps([p.model_dump() for p in body.permissions])

        # Bump version on code changes
        if any(v is not None for v in [body.html, body.css, body.js]):
            theme.version += 1

        await session.commit()
        return _theme_to_dict(theme)


@router.delete("/{theme_id}", status_code=204)
async def delete_theme(theme_id: str, user: CurrentUser = Depends(get_current_user)):
    """Delete a theme. Only creator can delete. Cannot delete if others have installed."""
    async with get_session() as session:
        theme = await _get_theme_or_404(session, theme_id)
        if theme.creator_id != user.id:
            raise HTTPException(403, "Not your theme")

        # Check if others have installed it
        if theme.published and theme.install_count > 0:
            others = await session.execute(
                select(func.count()).select_from(ThemeInstall)
                .where(and_(ThemeInstall.theme_id == theme_id, ThemeInstall.user_id != user.id))
            )
            if others.scalar_one() > 0:
                raise HTTPException(400, "Cannot delete a published theme with active installs. Unpublish first.")

        # Delete related records
        await session.execute(
            ThemeInstall.__table__.delete().where(ThemeInstall.theme_id == theme_id)
        )
        await session.execute(
            ThemeState.__table__.delete().where(ThemeState.theme_id == theme_id)
        )
        await session.delete(theme)
        await session.commit()


# ---------------------------------------------------------------------------
# My Themes
# ---------------------------------------------------------------------------

@router.get("/my/created")
async def list_my_themes(user: CurrentUser = Depends(get_current_user)):
    """List themes created by the current user."""
    async with get_session() as session:
        result = await session.execute(
            select(Theme).where(Theme.creator_id == user.id).order_by(desc(Theme.created_at))
        )
        themes = result.scalars().all()
        return [_theme_to_list_item(t) for t in themes]


@router.get("/my/installed")
async def list_my_installed(
    studio: str = Query("life"),
    user: CurrentUser = Depends(get_current_user),
):
    """List themes installed by the current user in a studio."""
    async with get_session() as session:
        result = await session.execute(
            select(ThemeInstall, Theme)
            .join(Theme, ThemeInstall.theme_id == Theme.id)
            .where(and_(ThemeInstall.user_id == user.id, ThemeInstall.studio == studio))
            .order_by(ThemeInstall.pos_y, ThemeInstall.pos_x)
        )
        rows = result.all()
        return [_install_to_dict(install, theme) for install, theme in rows]


# ---------------------------------------------------------------------------
# Install / Uninstall
# ---------------------------------------------------------------------------

@router.post("/{theme_id}/install", status_code=201)
async def install_theme(
    theme_id: str,
    body: ThemeInstallRequest = ThemeInstallRequest(),
    user: CurrentUser = Depends(get_current_user),
):
    """Install a theme into the user's studio grid."""
    async with get_session() as session:
        theme = await _get_theme_or_404(session, theme_id)

        # Must be own theme or published+approved
        if theme.creator_id != user.id:
            if not theme.published or theme.status != "approved":
                raise HTTPException(404, "Theme not found")

        # Check install limit per studio
        count_q = await session.execute(
            select(func.count()).select_from(ThemeInstall)
            .where(and_(ThemeInstall.user_id == user.id, ThemeInstall.studio == theme.studio))
        )
        if count_q.scalar_one() >= MAX_INSTALLS_PER_STUDIO:
            raise HTTPException(400, f"Maximum {MAX_INSTALLS_PER_STUDIO} themes per studio")

        install_id = str(uuid.uuid4())
        install = ThemeInstall(
            id=install_id,
            user_id=user.id,
            theme_id=theme_id,
            studio=theme.studio,
            pos_x=body.position.x,
            pos_y=body.position.y,
            pos_w=body.position.w,
            pos_h=body.position.h,
        )
        try:
            session.add(install)
            # Bump install count
            theme.install_count += 1
            await session.commit()
        except IntegrityError:
            raise HTTPException(409, "Theme already installed")

        return _install_to_dict(install, theme)


@router.delete("/install/{install_id}", status_code=204)
async def uninstall_theme(install_id: str, user: CurrentUser = Depends(get_current_user)):
    """Remove a theme from the user's studio."""
    async with get_session() as session:
        result = await session.execute(
            select(ThemeInstall).where(
                and_(ThemeInstall.id == install_id, ThemeInstall.user_id == user.id)
            )
        )
        install = result.scalar_one_or_none()
        if not install:
            raise HTTPException(404, "Install not found")

        # Decrement install count on theme
        theme_result = await session.execute(
            select(Theme).where(Theme.id == install.theme_id)
        )
        theme = theme_result.scalar_one_or_none()
        if theme and theme.install_count > 0:
            theme.install_count -= 1

        await session.delete(install)
        await session.commit()


@router.put("/install/{install_id}/position")
async def update_install_position(
    install_id: str, body: ThemePositionUpdate, user: CurrentUser = Depends(get_current_user)
):
    """Update an installed theme's grid position."""
    async with get_session() as session:
        result = await session.execute(
            select(ThemeInstall).where(
                and_(ThemeInstall.id == install_id, ThemeInstall.user_id == user.id)
            )
        )
        install = result.scalar_one_or_none()
        if not install:
            raise HTTPException(404, "Install not found")

        install.pos_x = body.x
        install.pos_y = body.y
        install.pos_w = body.w
        install.pos_h = body.h
        await session.commit()
        return {"ok": True}


@router.put("/install/{install_id}/toggle")
async def toggle_install(install_id: str, user: CurrentUser = Depends(get_current_user)):
    """Enable/disable an installed theme."""
    async with get_session() as session:
        result = await session.execute(
            select(ThemeInstall).where(
                and_(ThemeInstall.id == install_id, ThemeInstall.user_id == user.id)
            )
        )
        install = result.scalar_one_or_none()
        if not install:
            raise HTTPException(404, "Install not found")

        install.enabled = not install.enabled
        await session.commit()
        return {"enabled": install.enabled}


# ---------------------------------------------------------------------------
# Theme State (per-user, per-theme persistent storage)
# ---------------------------------------------------------------------------

@router.get("/state/{theme_id}")
async def get_theme_state(theme_id: str, user: CurrentUser = Depends(get_current_user)):
    """Read theme-private persistent state."""
    async with get_session() as session:
        result = await session.execute(
            select(ThemeState).where(
                and_(ThemeState.user_id == user.id, ThemeState.theme_id == theme_id)
            )
        )
        state = result.scalar_one_or_none()
        if not state:
            return {}
        try:
            return json.loads(state.state)
        except json.JSONDecodeError:
            return {}


@router.put("/state/{theme_id}")
async def set_theme_state(
    theme_id: str, body: ThemeStateUpdate, user: CurrentUser = Depends(get_current_user)
):
    """Write theme-private persistent state. Max 100KB."""
    state_str = json.dumps(body.state)
    if len(state_str) > 102_400:
        raise HTTPException(400, "State exceeds 100KB limit")

    async with get_session() as session:
        result = await session.execute(
            select(ThemeState).where(
                and_(ThemeState.user_id == user.id, ThemeState.theme_id == theme_id)
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.state = state_str
        else:
            session.add(ThemeState(
                user_id=user.id,
                theme_id=theme_id,
                state=state_str,
            ))
        await session.commit()
        return {"ok": True}


# ---------------------------------------------------------------------------
# Publish / Marketplace (Phase 3 prep — basic endpoints now)
# ---------------------------------------------------------------------------

@router.post("/{theme_id}/publish")
async def publish_theme(
    theme_id: str, body: ThemePublishRequest, user: CurrentUser = Depends(get_current_user)
):
    """Submit a theme for marketplace review."""
    async with get_session() as session:
        theme = await _get_theme_or_404(session, theme_id)
        if theme.creator_id != user.id:
            raise HTTPException(403, "Not your theme")
        if theme.published:
            raise HTTPException(400, "Already published")

        theme.price_tokens = body.price_tokens
        theme.status = "approved"  # Auto-approve for now (Phase 3 adds review)
        theme.published = True
        await session.commit()
        return {"published": True, "price_tokens": body.price_tokens}


@router.get("/marketplace/browse")
async def browse_marketplace(
    studio: str = Query("life"),
    category: str | None = None,
    sort: str = Query("popular"),
    price: str = Query("all"),
    q: str | None = None,
    page: int = Query(1, ge=1),
    user: CurrentUser = Depends(get_current_user),
):
    """Browse published themes in the marketplace."""
    async with get_session() as session:
        query = select(Theme).where(
            and_(Theme.published == True, Theme.status == "approved", Theme.studio == studio)  # noqa: E712
        )

        if category:
            query = query.where(Theme.category == category)

        if price == "free":
            query = query.where(Theme.price_tokens == 0)
        elif price == "paid":
            query = query.where(Theme.price_tokens > 0)

        if q:
            pattern = f"%{q}%"
            query = query.where(
                or_(Theme.title.ilike(pattern), Theme.description.ilike(pattern))
            )

        # Count total
        count_q = select(func.count()).select_from(query.subquery())
        total = (await session.execute(count_q)).scalar_one()

        # Sort
        if sort == "newest":
            query = query.order_by(desc(Theme.created_at))
        elif sort == "top_rated":
            query = query.order_by(desc(Theme.rating_sum / func.nullif(Theme.rating_count, 0)))
        elif sort == "price_low":
            query = query.order_by(Theme.price_tokens)
        elif sort == "price_high":
            query = query.order_by(desc(Theme.price_tokens))
        else:  # popular
            query = query.order_by(desc(Theme.install_count))

        # Paginate
        offset = (page - 1) * PAGE_SIZE
        query = query.offset(offset).limit(PAGE_SIZE)
        result = await session.execute(query)
        themes = result.scalars().all()

        return {
            "themes": [_theme_to_list_item(t) for t in themes],
            "total": total,
            "page": page,
            "has_more": offset + PAGE_SIZE < total,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_theme_or_404(session, theme_id: str) -> Theme:
    result = await session.execute(select(Theme).where(Theme.id == theme_id))
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(404, "Theme not found")
    return theme


def _parse_json_field(val: str | None, default=None):
    if not val:
        return default or []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return default or []


def _theme_to_dict(theme: Theme) -> dict:
    return {
        "id": theme.id,
        "creator_id": theme.creator_id,
        "studio": theme.studio,
        "title": theme.title,
        "description": theme.description,
        "category": theme.category,
        "tags": _parse_json_field(theme.tags),
        "html": theme.html,
        "css": theme.css,
        "js": theme.js,
        "permissions": _parse_json_field(theme.permissions),
        "version": theme.version,
        "published": theme.published,
        "price_tokens": theme.price_tokens,
        "install_count": theme.install_count,
        "rating_avg": round(theme.rating_sum / theme.rating_count, 1) if theme.rating_count else 0,
        "rating_count": theme.rating_count,
        "status": theme.status,
        "thumbnail_url": theme.thumbnail_url,
        "created_at": theme.created_at.isoformat() if theme.created_at else None,
        "updated_at": theme.updated_at.isoformat() if theme.updated_at else None,
    }


def _theme_to_list_item(theme: Theme) -> dict:
    """Lightweight version without code."""
    return {
        "id": theme.id,
        "creator_id": theme.creator_id,
        "studio": theme.studio,
        "title": theme.title,
        "description": theme.description,
        "category": theme.category,
        "tags": _parse_json_field(theme.tags),
        "permissions": _parse_json_field(theme.permissions),
        "version": theme.version,
        "published": theme.published,
        "price_tokens": theme.price_tokens,
        "install_count": theme.install_count,
        "rating_avg": round(theme.rating_sum / theme.rating_count, 1) if theme.rating_count else 0,
        "rating_count": theme.rating_count,
        "status": theme.status,
        "thumbnail_url": theme.thumbnail_url,
        "created_at": theme.created_at.isoformat() if theme.created_at else None,
    }


def _install_to_dict(install: ThemeInstall, theme: Theme) -> dict:
    return {
        "id": install.id,
        "theme_id": install.theme_id,
        "studio": install.studio,
        "pos_x": install.pos_x,
        "pos_y": install.pos_y,
        "pos_w": install.pos_w,
        "pos_h": install.pos_h,
        "enabled": install.enabled,
        "theme": _theme_to_dict(theme),
        "created_at": install.created_at.isoformat() if install.created_at else None,
    }

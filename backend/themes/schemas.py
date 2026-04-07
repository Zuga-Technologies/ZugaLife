"""ZugaThemes Pydantic request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


# --- Shared types ---

class ThemePermission(BaseModel):
    key: str
    type: str  # read, write, action
    description: str


class GridPosition(BaseModel):
    x: int = Field(0, ge=0, le=11)
    y: int = Field(0, ge=0)
    w: int = Field(6, ge=2, le=12)
    h: int = Field(4, ge=2, le=20)


# --- Create / Update ---

class ThemeCreateRequest(BaseModel):
    studio: str = Field(..., max_length=50)
    title: str = Field(..., min_length=1, max_length=60)
    description: str | None = Field(None, max_length=200)
    category: str = Field("widget", max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=5)
    html: str = Field(..., max_length=51200)   # 50KB
    css: str | None = Field(None, max_length=20480)  # 20KB
    js: str = Field(..., max_length=51200)     # 50KB
    permissions: list[ThemePermission]
    position: GridPosition | None = None


class ThemeUpdateRequest(BaseModel):
    title: str | None = Field(None, max_length=60)
    description: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=30)
    tags: list[str] | None = Field(None, max_length=5)
    html: str | None = Field(None, max_length=51200)
    css: str | None = Field(None, max_length=20480)
    js: str | None = Field(None, max_length=51200)
    permissions: list[ThemePermission] | None = None


class ThemePublishRequest(BaseModel):
    price_tokens: int = Field(0, ge=0, le=10000)


# --- Install / Position ---

class ThemeInstallRequest(BaseModel):
    position: GridPosition = Field(default_factory=GridPosition)


class ThemePositionUpdate(BaseModel):
    x: int = Field(..., ge=0, le=11)
    y: int = Field(..., ge=0)
    w: int = Field(..., ge=2, le=12)
    h: int = Field(..., ge=2, le=20)


# --- State ---

class ThemeStateUpdate(BaseModel):
    state: dict  # arbitrary JSON, max 100KB enforced in route


# --- Responses ---

class ThemeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    creator_id: str
    studio: str
    title: str
    description: str | None
    category: str
    tags: list[str] = []
    html: str
    css: str | None
    js: str
    permissions: list[ThemePermission] = []
    version: int
    published: bool
    price_tokens: int
    install_count: int
    rating_avg: float = 0.0
    rating_count: int
    status: str
    created_at: datetime
    updated_at: datetime


class ThemeListItem(BaseModel):
    """Lightweight theme for browse/list views (no code)."""
    model_config = {"from_attributes": True}

    id: str
    creator_id: str
    studio: str
    title: str
    description: str | None
    category: str
    tags: list[str] = []
    permissions: list[ThemePermission] = []
    version: int
    published: bool
    price_tokens: int
    install_count: int
    rating_avg: float = 0.0
    rating_count: int
    status: str
    thumbnail_url: str | None = None
    created_at: datetime


class ThemeInstallResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    theme_id: str
    studio: str
    pos_x: int
    pos_y: int
    pos_w: int
    pos_h: int
    enabled: bool
    theme: ThemeResponse  # Denormalized for offline rendering
    created_at: datetime


class MarketplaceResponse(BaseModel):
    themes: list[ThemeListItem]
    total: int
    page: int
    has_more: bool


class ThemeReviewResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    user_id: str
    theme_id: str
    rating: int
    review_text: str | None
    created_at: datetime


class ThemeReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    review_text: str | None = Field(None, max_length=500)

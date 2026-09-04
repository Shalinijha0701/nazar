from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import authenticated_user
from app.config import get_settings
from app.demo import REPLAY_EVALUATED_THROUGH, SESSION_START, recorded_demo_catchup
from app.repository import WatchlistRepository


settings = get_settings()
replay_watermarks: dict[tuple[str, str], datetime] = {}
app = FastAPI(
    title="Nazar API",
    version="0.1.0",
    description="Explainable market catch-up signals. No predictions or trade advice.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["DELETE", "GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": settings.mode,
        "market_provider": settings.market_provider,
        "persistence": settings.persistence,
        "auth_mode": settings.auth_mode,
    }


@app.get("/ready")
async def ready() -> dict[str, str]:
    if settings.persistence == "supabase":
        try:
            WatchlistRepository().get_watermark("readiness-check", "readiness-check", REPLAY_EVALUATED_THROUGH)
        except PermissionError:
            pass
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Supabase is not configured") from exc
    return {"status": "ready"}


class WatchlistCreate(BaseModel):
    name: str = Field(default="My watchlist", min_length=1, max_length=80)


class WatchlistItemCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    company_name: str = Field(min_length=1, max_length=120)
    sector_index: str = Field(min_length=1, max_length=40)


class RuleCreate(BaseModel):
    rule_type: str = Field(pattern="^(price_above|price_below|volume_pace)$")
    threshold: float = Field(gt=0)


class AcknowledgeRequest(BaseModel):
    watchlist_id: str
    evaluated_through: datetime


@app.post("/api/watchlists")
async def create_watchlist(
    payload: WatchlistCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user(authorization, settings)
    if settings.persistence == "memory":
        return {"watchlist_id": "primary", "name": payload.name}
    try:
        watchlist_id = WatchlistRepository().create_watchlist(user_id, payload.name)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Persistence is not configured") from exc
    return {"watchlist_id": watchlist_id, "name": payload.name}


@app.post("/api/watchlists/{watchlist_id}/items")
async def add_item(
    watchlist_id: str,
    payload: WatchlistItemCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user(authorization, settings)
    if settings.persistence == "memory":
        return {"item_id": f"{watchlist_id}:{payload.symbol}", "status": "added"}
    try:
        item_id = WatchlistRepository().add_item(
            user_id, watchlist_id, payload.symbol, payload.company_name, payload.sector_index
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Watchlist not found") from exc
    return {"item_id": item_id, "status": "added"}


@app.delete("/api/watchlists/items/{item_id}")
async def remove_item(
    item_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user(authorization, settings)
    if settings.persistence != "memory":
        try:
            WatchlistRepository().remove_item(user_id, item_id)
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Watchlist item not found") from exc
    return {"status": "removed"}


@app.post("/api/watchlists/items/{item_id}/rules")
async def add_rule(
    item_id: str,
    payload: RuleCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user(authorization, settings)
    if settings.persistence == "memory":
        return {"rule_id": f"{item_id}:{payload.rule_type}", "status": "saved"}
    try:
        rule_id = WatchlistRepository().add_rule(
            user_id, item_id, payload.rule_type, payload.threshold
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Watchlist item not found") from exc
    return {"rule_id": rule_id, "status": "saved"}


@app.get("/api/watchlists/me/catchup")
async def catchup(
    watchlist_id: str = "primary",
    authorization: str | None = Header(default=None),
) -> dict:
    user_id = authenticated_user(authorization, settings)
    if settings.market_provider == "replay":
        evaluated = REPLAY_EVALUATED_THROUGH
        default_reviewed = SESSION_START
    else:
        evaluated = datetime.now(UTC).replace(second=0, microsecond=0)
        default_reviewed = evaluated - timedelta(hours=4)
    if settings.market_provider == "replay":
        reviewed = replay_watermarks.get((user_id, watchlist_id), default_reviewed)
    else:
        try:
            reviewed = WatchlistRepository().get_watermark(user_id, watchlist_id, default_reviewed)
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Watchlist not found") from exc
    if settings.market_provider == "replay":
        return recorded_demo_catchup(reviewed, evaluated)
    raise HTTPException(status_code=501, detail="Live aggregation worker is not enabled")


@app.post("/api/watchlists/me/acknowledge")
async def acknowledge(
    payload: AcknowledgeRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user(authorization, settings)
    if settings.persistence == "memory":
        key = (user_id, payload.watchlist_id)
        replay_watermarks[key] = max(
            replay_watermarks.get(key, payload.evaluated_through), payload.evaluated_through
        )
        return {"reviewed_through": replay_watermarks[key].isoformat()}
    try:
        final_watermark = WatchlistRepository().acknowledge(
            user_id,
            payload.watchlist_id,
            payload.evaluated_through,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Watchlist not found") from exc
    return {"reviewed_through": final_watermark.isoformat()}

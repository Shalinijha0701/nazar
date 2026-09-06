import logging
import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import authenticated_user
from app.config import Settings, get_settings
from app.demo import DEMO_END, DEMO_START, recorded_demo_catchup
from app.providers.groww import GrowwProvider
from app.repository import MemoryWatchlistRepository, SupabaseWatchlistRepository, WatchlistStore
from app.services.live import live_market_catchup
from app.services.signals import SUPPORTED_HORIZONS
from app.services.trading_time import trading_minutes_between


logger = logging.getLogger("nazar")


class ProviderUnavailableError(RuntimeError):
    """Raised when the upstream market-data provider cannot serve the request."""


class WatchlistCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(default="My watchlist", min_length=1, max_length=80)


class WatchlistItemCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    symbol: str = Field(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9&._-]+$")
    company_name: str = Field(min_length=1, max_length=120)
    sector_index: str = Field(min_length=1, max_length=40)


class RuleCreate(BaseModel):
    rule_type: str = Field(pattern=r"^(price_above|price_below|volume_pace)$")
    threshold: float = Field(gt=0, le=10_000_000)


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    watchlist_id: str = Field(min_length=1, max_length=80)
    evaluated_through: datetime

    @field_validator("evaluated_through")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("evaluated_through must include a timezone")
        return value


@lru_cache
def memory_repository() -> MemoryWatchlistRepository:
    return MemoryWatchlistRepository()


def repository(settings: Settings) -> WatchlistStore:
    if settings.persistence_backend == "supabase":
        return SupabaseWatchlistRepository()
    return memory_repository()


def default_live_watermark(evaluated: datetime) -> datetime:
    """Walk back until the window covers the largest supported horizon in trading
    minutes (about five NSE sessions), bounded to 14 calendar days."""
    candidate = evaluated - timedelta(days=1)
    earliest = evaluated - timedelta(days=14)
    while (
        trading_minutes_between(candidate, evaluated) < SUPPORTED_HORIZONS[-1]
        and candidate > earliest
    ):
        candidate -= timedelta(days=1)
    return candidate


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or get_settings()
    runtime.validate_runtime()
    logging.basicConfig(level=logging.INFO)
    if runtime.persistence_backend == "memory" and os.environ.get("VERCEL"):
        logger.warning(
            "Memory persistence is running on Vercel serverless: state is per-instance "
            "and will not survive cold starts. Configure NAZAR_PERSISTENCE_BACKEND=supabase "
            "for the deployed demo."
        )
    app = FastAPI(
        title="Nazar API",
        version="1.0.0",
        description="Explainable market catch-up signals without predictions or trade advice.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.origins,
        allow_credentials=True,
        allow_methods=["DELETE", "GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(ProviderUnavailableError)
    async def provider_unavailable(request: Request, exc: ProviderUnavailableError) -> JSONResponse:
        logger.warning("Provider unavailable for %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "The market-data provider is unavailable. Try again shortly."},
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error for %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred."},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/watchlists")
    async def create_watchlist(
        payload: WatchlistCreate,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authenticated_user(authorization, runtime)
        try:
            watchlist_id = repository(runtime).create_watchlist(user_id, payload.name.strip())
        except ValueError as exc:
            raise HTTPException(status_code=429, detail="Watchlist limit reached") from exc
        return {"watchlist_id": watchlist_id, "name": payload.name.strip()}

    @app.post("/api/watchlists/{watchlist_id}/items")
    async def add_item(
        watchlist_id: str,
        payload: WatchlistItemCreate,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authenticated_user(authorization, runtime)
        try:
            item_id = repository(runtime).add_item(
                user_id,
                watchlist_id,
                payload.symbol,
                payload.company_name,
                payload.sector_index,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Watchlist not found") from exc
        return {"item_id": item_id, "status": "added"}

    @app.delete("/api/watchlists/items/{item_id}")
    async def remove_item(
        item_id: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authenticated_user(authorization, runtime)
        try:
            repository(runtime).remove_item(user_id, item_id)
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Watchlist item not found") from exc
        return {"status": "removed"}

    @app.post("/api/watchlists/items/{item_id}/rules")
    async def add_rule(
        item_id: str,
        payload: RuleCreate,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authenticated_user(authorization, runtime)
        try:
            rule_id = repository(runtime).add_rule(
                user_id,
                item_id,
                payload.rule_type,
                payload.threshold,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Watchlist item not found") from exc
        return {"rule_id": rule_id, "status": "saved"}

    @app.get("/api/watchlists/me/catchup")
    async def catchup(
        watchlist_id: str | None = None,
        authorization: str | None = Header(default=None),
    ) -> dict:
        user_id = authenticated_user(authorization, runtime)
        store = repository(runtime)
        try:
            resolved_id = store.get_or_create_watchlist(user_id, watchlist_id)
            items = store.list_items(user_id, resolved_id)
            rules = store.list_rules(user_id, resolved_id)
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Watchlist not found") from exc

        if runtime.market_provider == "replay":
            reviewed = store.get_watermark(user_id, resolved_id, DEMO_START)
            confirmed_events = store.list_confirmed_path_events(user_id, resolved_id, reviewed)
            return await recorded_demo_catchup(
                resolved_id,
                items,
                rules,
                reviewed,
                DEMO_END,
                confirmed_events,
            )

        evaluated = datetime.now(UTC).replace(second=0, microsecond=0)
        reviewed = store.get_watermark(user_id, resolved_id, default_live_watermark(evaluated))
        confirmed_events = store.list_confirmed_path_events(user_id, resolved_id, reviewed)
        try:
            provider = GrowwProvider(runtime.groww_access_token or "")
            return await live_market_catchup(
                resolved_id,
                items,
                rules,
                reviewed,
                evaluated,
                provider,
                confirmed_events,
            )
        except Exception as exc:
            raise ProviderUnavailableError(str(exc)) from exc

    @app.post("/api/watchlists/me/acknowledge")
    async def acknowledge(
        payload: AcknowledgeRequest,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        user_id = authenticated_user(authorization, runtime)
        upper_bound = DEMO_END if runtime.market_provider == "replay" else datetime.now(UTC) + timedelta(minutes=1)
        if payload.evaluated_through > upper_bound:
            raise HTTPException(status_code=422, detail="Acknowledgement cannot exceed evaluated data")
        try:
            final_watermark = repository(runtime).acknowledge(
                user_id,
                payload.watchlist_id,
                payload.evaluated_through,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Watchlist not found") from exc
        return {"reviewed_through": final_watermark.isoformat()}

    return app


app = create_app()

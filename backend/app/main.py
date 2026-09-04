from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.auth import authenticated_user
from app.config import get_settings
from app.demo import recorded_demo_catchup
from app.repository import WatchlistRepository


settings = get_settings()
app = FastAPI(
    title="Nazar API",
    version="0.1.0",
    description="Explainable market catch-up signals. No predictions or trade advice.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": settings.mode}


@app.get("/api/watchlists/me/catchup")
async def catchup(authorization: str | None = Header(default=None)) -> dict:
    authenticated_user(authorization, settings)
    evaluated = datetime.now(UTC).replace(second=0, microsecond=0)
    reviewed = evaluated - timedelta(hours=4)
    if settings.mode == "replay":
        return recorded_demo_catchup(reviewed, evaluated)
    raise HTTPException(status_code=501, detail="Live aggregation worker is not enabled")


@app.post("/api/watchlists/me/acknowledge")
async def acknowledge(
    watchlist_id: str,
    evaluated_through: datetime,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user(authorization, settings)
    if settings.mode == "replay":
        return {"reviewed_through": evaluated_through.isoformat()}
    try:
        final_watermark = WatchlistRepository().acknowledge(
            user_id,
            watchlist_id,
            evaluated_through,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Watchlist not found") from exc
    return {"reviewed_through": final_watermark.isoformat()}

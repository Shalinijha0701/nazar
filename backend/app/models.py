from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DataState(StrEnum):
    FRESH = "fresh"
    MARKET_CLOSED = "market_closed"
    UNAVAILABLE = "unavailable"


class SignalKind(StrEnum):
    PERSONAL_RULE = "personal_rule"
    SECTOR_SURPRISE = "sector_surprise"
    PATH_EVENT = "path_event"


class Candle(BaseModel):
    symbol: str
    interval_start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = Field(ge=0)


class Signal(BaseModel):
    kind: SignalKind
    label: str
    occurred_at: datetime | None = None
    percentile: float | None = Field(default=None, ge=0, le=100)
    observation_count: int | None = None
    direction: str | None = None
    evidence: dict[str, float | str] = Field(default_factory=dict)


class CatchupCard(BaseModel):
    symbol: str
    company_name: str
    current_price: float | None
    change_since_review_percent: float | None
    data_state: DataState
    last_updated_at: datetime | None
    signals: list[Signal]


class CatchupResponse(BaseModel):
    watchlist_id: str
    reviewed_through: datetime
    evaluated_through: datetime
    trading_minutes: int
    coverage: str
    counts: dict[str, int]
    attention: list[CatchupCard]
    normal: list[CatchupCard]
    data_unavailable: list[CatchupCard]

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DataState(StrEnum):
    FRESH = "fresh"
    MARKET_CLOSED = "market_closed"
    UNAVAILABLE = "unavailable"
    LIMITED_HISTORY = "limited_history"


class SignalKind(StrEnum):
    PERSONAL_RULE = "personal_rule"
    SECTOR_SURPRISE = "sector_surprise"
    PATH_EVENT = "path_event"


class Candle(BaseModel):
    symbol: str
    interval_start: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Candle":
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be the greatest OHLC value")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be the smallest OHLC value")
        if self.interval_start.tzinfo is None:
            raise ValueError("interval_start must be timezone-aware")
        return self


class ChartPoint(BaseModel):
    timestamp: datetime
    price: float = Field(gt=0)


EvidenceValue = float | int | str | bool | None


class Signal(BaseModel):
    kind: SignalKind
    label: str
    occurred_at: datetime | None = None
    percentile: float | None = Field(default=None, ge=0, le=100)
    observation_count: int | None = Field(default=None, ge=0)
    direction: str | None = None
    evidence: dict[str, EvidenceValue] = Field(default_factory=dict)


class CatchupCard(BaseModel):
    item_id: str | None = None
    symbol: str
    company_name: str
    sector_index: str
    current_price: float | None
    baseline_price: float | None
    change_since_review_percent: float | None
    data_state: DataState
    last_updated_at: datetime | None
    narrative: str
    chart: list[ChartPoint]
    signals: list[Signal]


class CatchupResponse(BaseModel):
    watchlist_id: str
    source: Literal["replay", "groww"]
    reviewed_through: datetime
    evaluated_through: datetime
    trading_minutes: int
    horizon_minutes: int | None
    coverage: str
    counts: dict[str, int]
    attention: list[CatchupCard]
    normal: list[CatchupCard]
    data_unavailable: list[CatchupCard]

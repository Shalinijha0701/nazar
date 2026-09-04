from datetime import datetime
from typing import Protocol, Sequence

from app.models import Candle


class MarketDataProvider(Protocol):
    async def candles(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        interval: str = "1minute",
    ) -> dict[str, list[Candle]]:
        """Return normalized candles keyed by exchange symbol."""

    async def latest_prices(self, symbols: Sequence[str]) -> dict[str, float]:
        """Return the latest known price for every available symbol."""

from collections.abc import Sequence
from datetime import datetime

from app.models import Candle


class ReplayProvider:
    """Deterministic provider used for weekend demos and automated tests."""

    def __init__(self, candles_by_symbol: dict[str, list[Candle]]):
        self._candles = candles_by_symbol

    async def candles(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        interval: str = "1minute",
    ) -> dict[str, list[Candle]]:
        return {
            symbol: [
                candle
                for candle in self._candles.get(symbol, [])
                if start <= candle.interval_start <= end
            ]
            for symbol in symbols
        }

    async def latest_prices(self, symbols: Sequence[str]) -> dict[str, float]:
        return {
            symbol: self._candles[symbol][-1].close
            for symbol in symbols
            if self._candles.get(symbol)
        }

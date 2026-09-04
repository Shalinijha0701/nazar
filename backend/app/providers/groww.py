import asyncio
from datetime import UTC, datetime
from functools import partial
import logging
from typing import Sequence
from zoneinfo import ZoneInfo

from growwapi import GrowwAPI

from app.models import Candle


INDIA_TZ = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)


class GrowwProvider:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise ValueError("Groww access token is required")
        self._client = GrowwAPI(access_token)

    async def latest_prices(self, symbols: Sequence[str]) -> dict[str, float]:
        prices: dict[str, float] = {}
        for offset in range(0, len(symbols), 50):
            batch = symbols[offset : offset + 50]
            exchange_symbols = tuple(f"NSE_{self._trading_symbol(symbol)}" for symbol in batch)
            payload = await asyncio.to_thread(
                partial(
                    self._client.get_ltp,
                    segment=self._client.SEGMENT_CASH,
                    exchange_trading_symbols=exchange_symbols,
                )
            )
            for symbol in batch:
                value = payload.get(f"NSE_{self._trading_symbol(symbol)}")
                if value is not None:
                    prices[symbol] = float(value)
        return prices

    async def candles(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        interval: str = "1minute",
    ) -> dict[str, list[Candle]]:
        interval_map = {
            "1minute": self._client.CANDLE_INTERVAL_MIN_1,
            "5minute": self._client.CANDLE_INTERVAL_MIN_5,
            "15minute": self._client.CANDLE_INTERVAL_MIN_15,
            "30minute": self._client.CANDLE_INTERVAL_MIN_30,
        }
        if interval not in interval_map:
            raise ValueError(f"Unsupported candle interval: {interval}")

        semaphore = asyncio.Semaphore(8)

        async def load(symbol: str) -> tuple[str, list[Candle]]:
            async with semaphore:
                try:
                    payload = await asyncio.to_thread(
                        partial(
                            self._client.get_historical_candles,
                            exchange=self._client.EXCHANGE_NSE,
                            segment=self._client.SEGMENT_CASH,
                            groww_symbol=f"NSE-{self._trading_symbol(symbol)}",
                            start_time=self._format_time(start),
                            end_time=self._format_time(end),
                            candle_interval=interval_map[interval],
                        )
                    )
                except Exception:
                    logger.warning("Groww candle request failed for %s", symbol, exc_info=True)
                    return symbol, []

                by_timestamp: dict[datetime, Candle] = {}
                for row in payload.get("candles", []):
                    timestamp = self._parse_timestamp(row[0])
                    by_timestamp[timestamp] = Candle(
                        symbol=symbol,
                        interval_start=timestamp,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=int(row[5] or 0),
                    )
                return symbol, [by_timestamp[key] for key in sorted(by_timestamp)]

        loaded = await asyncio.gather(*(load(symbol) for symbol in symbols))
        return dict(loaded)

    @staticmethod
    def _trading_symbol(symbol: str) -> str:
        aliases = {
            "NIFTY50": "NIFTY",
            "NIFTY_BANK": "BANKNIFTY",
            "NIFTY_IT": "NIFTYIT",
        }
        return aliases.get(symbol, symbol)

    @staticmethod
    def _format_time(value: datetime) -> str:
        localized = value.astimezone(INDIA_TZ)
        return localized.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _parse_timestamp(raw: object) -> datetime:
        if isinstance(raw, (int, float)):
            seconds = float(raw) / 1000 if float(raw) > 10_000_000_000 else float(raw)
            return datetime.fromtimestamp(seconds, tz=UTC)
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=INDIA_TZ)
        return parsed.astimezone(UTC)

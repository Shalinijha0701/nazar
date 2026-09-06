import asyncio
import unittest
from datetime import UTC, datetime, timedelta

from app.main import default_live_watermark
from app.models import Candle
from app.repository import RuleRecord, WatchlistItemRecord
from app.services.live import live_market_catchup
from app.services.signals import SUPPORTED_HORIZONS
from app.services.trading_time import trading_minutes_between


# Friday 2026-09-04 during NSE hours; evaluation on Saturday (market closed),
# so the staleness branch does not reclassify fresh Friday candles.
REVIEWED = datetime(2026, 9, 4, 4, 0, tzinfo=UTC)
EVALUATED = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)


class StubProvider:
    def __init__(self, candles_by_symbol: dict[str, list[Candle]]) -> None:
        self._candles = candles_by_symbol

    async def candles(self, symbols, start, end, interval="1minute"):
        return {symbol: self._candles.get(symbol, []) for symbol in symbols}

    async def latest_prices(self, symbols):
        return {}


def _candle(symbol: str, at: datetime, close: float, high: float | None = None, low: float | None = None) -> Candle:
    return Candle(
        symbol=symbol,
        interval_start=at,
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=1000,
    )


def _item(symbol: str) -> WatchlistItemRecord:
    return WatchlistItemRecord(
        id=f"primary:{symbol}",
        symbol=symbol,
        company_name=f"{symbol} Ltd",
        sector_index="NIFTY50",
    )


class LiveCatchupTests(unittest.TestCase):
    def run_catchup(self, items, rules, candles):
        return asyncio.run(
            live_market_catchup(
                "primary",
                items,
                rules,
                REVIEWED,
                EVALUATED,
                StubProvider(candles),
                [],
            )
        )

    def test_symbol_without_candles_is_unavailable(self) -> None:
        payload = self.run_catchup([_item("AAA")], [], {})
        self.assertEqual(payload["counts"], {"attention": 0, "normal": 0, "data_unavailable": 1})
        self.assertEqual(payload["data_unavailable"][0]["data_state"], "unavailable")

    def test_price_rule_crossing_moves_card_to_attention(self) -> None:
        candles = {
            "AAA": [
                _candle("AAA", REVIEWED + timedelta(minutes=60), 100.0),
                _candle("AAA", REVIEWED + timedelta(minutes=75), 105.5, high=106.0, low=100.0),
            ]
        }
        rules = [RuleRecord("r1", "primary:AAA", "price_above", 105.0)]
        payload = self.run_catchup([_item("AAA")], rules, candles)

        self.assertEqual(payload["counts"]["attention"], 1)
        card = payload["attention"][0]
        kinds = {signal["kind"] for signal in card["signals"]}
        self.assertEqual(kinds, {"personal_rule"})
        self.assertEqual(card["data_state"], "market_closed")

    def test_volume_rule_reported_as_unevaluated(self) -> None:
        candles = {
            "AAA": [
                _candle("AAA", REVIEWED + timedelta(minutes=60), 100.0),
                _candle("AAA", REVIEWED + timedelta(minutes=75), 100.2, high=100.4, low=99.9),
            ]
        }
        rules = [RuleRecord("r1", "primary:AAA", "volume_pace", 1.8)]
        payload = self.run_catchup([_item("AAA")], rules, candles)

        self.assertEqual(payload["counts"]["normal"], 1)
        narrative = payload["normal"][0]["narrative"]
        self.assertIn("volume-pace rule was not evaluated", narrative)

    def test_narrative_is_unchanged_without_volume_rules(self) -> None:
        candles = {
            "AAA": [
                _candle("AAA", REVIEWED + timedelta(minutes=60), 100.0),
                _candle("AAA", REVIEWED + timedelta(minutes=75), 100.2, high=100.4, low=99.9),
            ]
        }
        payload = self.run_catchup([_item("AAA")], [], candles)
        self.assertNotIn("volume-pace", payload["normal"][0]["narrative"])


class DefaultLiveWatermarkTests(unittest.TestCase):
    def test_window_covers_largest_horizon(self) -> None:
        evaluated = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)  # Wednesday
        watermark = default_live_watermark(evaluated)
        self.assertGreaterEqual(
            trading_minutes_between(watermark, evaluated),
            SUPPORTED_HORIZONS[-1],
        )

    def test_window_never_exceeds_fourteen_days(self) -> None:
        evaluated = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
        watermark = default_live_watermark(evaluated)
        self.assertGreaterEqual(watermark, evaluated - timedelta(days=14))


if __name__ == "__main__":
    unittest.main()

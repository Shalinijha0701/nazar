from datetime import UTC, datetime, timedelta
import math
import unittest

from app.models import Candle
from app.services.distributions import (
    deviation_breakpoints,
    percentile_breakpoints,
    sector_relative_observations,
)
from app.services.signals import (
    crossed_above,
    empirical_percentile,
    first_volume_pace_crossing,
    path_metrics,
    sector_surprise,
    select_horizon,
    volume_pace,
    _align_by_timestamp,
)
from app.services.trading_time import is_market_open, trading_minutes_between


BASE_DT = datetime(2026, 9, 4, 9, 15, tzinfo=UTC)


def candle(
    minute: int,
    high: float,
    low: float,
    close: float,
    symbol: str = "TEST",
    volume: int = 1000,
) -> Candle:
    return Candle(
        symbol=symbol,
        interval_start=BASE_DT + timedelta(minutes=minute),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class HorizonSelectionTests(unittest.TestCase):
    def test_ceiling_applied(self) -> None:
        self.assertEqual(select_horizon(61), (240, "full"))

    def test_insufficient_interval(self) -> None:
        self.assertEqual(select_horizon(10), (None, "insufficient_interval"))

    def test_beyond_max_returns_partial(self) -> None:
        self.assertEqual(select_horizon(2000), (1875, "partial_coverage"))

    def test_exact_boundary_uses_that_bucket(self) -> None:
        self.assertEqual(select_horizon(60), (60, "full"))


class PriceCrossingTests(unittest.TestCase):
    def test_crossed_above_detects_via_high(self) -> None:
        candles = [candle(0, 99.8, 99.2, 99.5), candle(1, 100.2, 99.6, 100.1)]
        self.assertTrue(crossed_above(candles, baseline=99.0, threshold=100.0))

    def test_not_triggered_when_baseline_already_above(self) -> None:
        candles = [candle(0, 101.0, 100.0, 100.5)]
        self.assertFalse(crossed_above(candles, baseline=101.5, threshold=100.0))

    def test_not_triggered_when_high_never_reaches_threshold(self) -> None:
        candles = [candle(0, 99.9, 99.0, 99.5)]
        self.assertFalse(crossed_above(candles, baseline=99.0, threshold=100.0))


class SectorSurpriseTests(unittest.TestCase):
    def _make_paired(
        self,
        stock_close: float,
        sector_close: float,
        stock_baseline: float = 100.0,
        sector_baseline: float = 1000.0,
        n_history: int = 252,
    ):
        sc = [candle(0, stock_close + 0.5, stock_close - 0.5, stock_close, symbol="STOCK")]
        se = [candle(0, sector_close + 5, sector_close - 5, sector_close, symbol="SEC")]
        half = n_history // 2
        step = 0.012 / half
        history = [(i - half) * step for i in range(n_history)]
        return sc, se, stock_baseline, sector_baseline, history

    def test_minimum_history_required(self) -> None:
        sc, se, sb, secb, history = self._make_paired(102.4, 1004.0, n_history=119)
        self.assertIsNone(sector_surprise(sc, se, sb, secb, history))

    def test_positive_surprise_triggers(self) -> None:
        sc, se, sb, secb, history = self._make_paired(102.4, 1004.0)
        result = sector_surprise(sc, se, sb, secb, history)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreaterEqual(result.percentile, 95)
        self.assertGreater(result.deviation, 0)

    def test_negative_surprise_also_triggers(self) -> None:
        sc, se, sb, secb, history = self._make_paired(98.0, 1004.0)
        result = sector_surprise(sc, se, sb, secb, history)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreaterEqual(result.percentile, 95)
        self.assertLess(result.deviation, 0)

    def test_timestamp_mismatch_returns_none(self) -> None:
        sc = [candle(0, 102.0, 101.0, 101.5, symbol="STOCK")]
        se = [candle(5, 1005.0, 995.0, 1000.0, symbol="SEC")]
        history = [0.0] * 252
        result = sector_surprise(sc, se, 100.0, 1000.0, history)
        self.assertIsNone(result)


class PathMetricsTests(unittest.TestCase):
    def test_disappearing_reversal_captured(self) -> None:
        candles = [
            candle(0, 1000, 998, 1000),
            candle(1, 1060, 1040, 1050),
            candle(2, 1020, 1008, 1010),
        ]
        pm = path_metrics(candles, baseline_price=1000.0)
        self.assertTrue(math.isclose(pm.upward_excursion, 0.06))
        expected_ptt = (1060 - 1008) / 1060
        self.assertTrue(math.isclose(pm.peak_to_trough_reversal, expected_ptt))

    def test_no_reversal_when_monotone_up(self) -> None:
        candles = [candle(m, 100 + m, 99 + m, 100 + m) for m in range(5)]
        pm = path_metrics(candles, baseline_price=100.0)
        self.assertAlmostEqual(pm.peak_to_trough_reversal, 0.0)

    def test_same_candle_does_not_invent_intraminute_order(self) -> None:
        pm = path_metrics([candle(0, 110, 90, 100)], baseline_price=100.0)
        self.assertEqual(pm.peak_to_trough_reversal, 0.0)
        self.assertEqual(pm.trough_to_peak_reversal, 0.0)


class VolumePaceTests(unittest.TestCase):
    def test_pace_above_threshold(self) -> None:
        medians = [1_000_000.0] * 20
        pace = volume_pace(1_850_000, medians)
        self.assertIsNotNone(pace)
        assert pace is not None
        self.assertAlmostEqual(pace, 1.85)

    def test_fewer_than_20_sessions_returns_none(self) -> None:
        self.assertIsNone(volume_pace(1_850_000, [1_000_000.0] * 19))

    def test_zero_median_returns_none(self) -> None:
        self.assertIsNone(volume_pace(1_000, [0.0] * 20))

    def test_crossing_requires_a_prior_value_below_threshold(self) -> None:
        history = [1_000_000.0] * 20
        samples = [
            (BASE_DT, 1_760_000, history),
            (BASE_DT + timedelta(minutes=1), 1_850_000, history),
        ]
        result = first_volume_pace_crossing(samples, 1.8)
        self.assertEqual(result, (BASE_DT + timedelta(minutes=1), 1.85))


class EmpiricalPercentileTests(unittest.TestCase):
    def test_inclusive_boundary(self) -> None:
        self.assertEqual(empirical_percentile(3, [1, 2, 3, 4]), 75.0)

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            empirical_percentile(1.0, [])


class TimestampAlignmentTests(unittest.TestCase):
    def test_drops_stock_candle_with_no_sector_match(self) -> None:
        stock = [candle(0, 101, 99, 100, "S"), candle(5, 102, 100, 101, "S")]
        sector = [candle(0, 1001, 999, 1000, "I")]
        aligned_s, aligned_i = _align_by_timestamp(stock, sector)
        self.assertEqual(len(aligned_s), 1)
        self.assertEqual(len(aligned_i), 1)
        self.assertEqual(aligned_s[0].interval_start, BASE_DT)

    def test_empty_when_no_overlap(self) -> None:
        stock = [candle(0, 101, 99, 100, "S")]
        sector = [candle(5, 1001, 999, 1000, "I")]
        aligned_s, aligned_i = _align_by_timestamp(stock, sector)
        self.assertEqual(len(aligned_s), 0)
        self.assertEqual(len(aligned_i), 0)


class DistributionBuilderTests(unittest.TestCase):
    def test_nearest_rank_breakpoints(self) -> None:
        result = percentile_breakpoints(range(1, 101))
        self.assertEqual(result["p50"], 50.0)
        self.assertEqual(result["p95"], 95.0)
        self.assertEqual(result["p97.5"], 98.0)

    def test_sector_relative_windows(self) -> None:
        stock = [100, 102, 104, 106]
        sector = [100, 101, 102, 103]
        values = sector_relative_observations(stock, sector, 2)
        self.assertEqual(len(values), 2)
        self.assertAlmostEqual(values[0], 0.02)

    def test_deviation_breakpoints_include_center(self) -> None:
        result = deviation_breakpoints([-0.02, -0.01, 0.0, 0.01, 0.02])
        self.assertEqual(result["median"], 0.0)
        self.assertEqual(result["p50"], 0.01)


class TradingTimeTests(unittest.TestCase):
    def test_weekend_minutes_are_excluded(self) -> None:
        friday = datetime(2026, 9, 4, 9, 30, tzinfo=UTC)
        monday = datetime(2026, 9, 7, 4, 30, tzinfo=UTC)
        self.assertEqual(trading_minutes_between(friday, monday), 75)

    def test_closed_market_interval_is_zero(self) -> None:
        start = datetime(2026, 9, 4, 11, 0, tzinfo=UTC)
        end = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
        self.assertEqual(trading_minutes_between(start, end), 0)

    def test_market_open_uses_exchange_timezone(self) -> None:
        self.assertTrue(is_market_open(datetime(2026, 9, 4, 5, 0, tzinfo=UTC)))
        self.assertFalse(is_market_open(datetime(2026, 9, 4, 11, 0, tzinfo=UTC)))


if __name__ == "__main__":
    unittest.main()

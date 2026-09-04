from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Mapping, Sequence

from app.models import Candle


SUPPORTED_HORIZONS = (15, 60, 240, 375, 750, 1875)
MINIMUM_OBSERVATIONS = 120
SURPRISE_TRIGGER = 95.0


@dataclass(frozen=True)
class PercentileResult:
    percentile: float
    observation_count: int
    deviation: float


@dataclass(frozen=True)
class PathMetrics:
    upward_excursion: float
    downward_excursion: float
    peak_to_trough_reversal: float
    trough_to_peak_reversal: float
    upward_at: datetime
    downward_at: datetime
    peak_to_trough_at: datetime | None
    trough_to_peak_at: datetime | None


@dataclass(frozen=True)
class PathSignalResult:
    event_type: str
    magnitude: float
    percentile: float
    observation_count: int
    occurred_at: datetime


def select_horizon(trading_minutes: int) -> tuple[int | None, str]:
    if trading_minutes < SUPPORTED_HORIZONS[0]:
        return None, "insufficient_interval"
    for horizon in SUPPORTED_HORIZONS:
        if trading_minutes <= horizon:
            return horizon, "full"
    return SUPPORTED_HORIZONS[-1], "partial_coverage"


def empirical_percentile(value: float, observations: Sequence[float]) -> float:
    if not observations:
        raise ValueError("at least one observation is required")
    return 100.0 * sum(observation <= value for observation in observations) / len(observations)


def _align_by_timestamp(
    stock_candles: Sequence[Candle],
    sector_candles: Sequence[Candle],
) -> tuple[list[Candle], list[Candle]]:
    sector_by_time = {candle.interval_start: candle for candle in sector_candles}
    pairs = [
        (candle, sector_by_time[candle.interval_start])
        for candle in stock_candles
        if candle.interval_start in sector_by_time
    ]
    pairs.sort(key=lambda pair: pair[0].interval_start)
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def candle_return(candles: Sequence[Candle], baseline_price: float) -> float | None:
    if not candles or baseline_price <= 0:
        return None
    ordered = sorted(candles, key=lambda candle: candle.interval_start)
    return (ordered[-1].close - baseline_price) / baseline_price


def sector_surprise(
    stock_candles: Sequence[Candle],
    sector_candles: Sequence[Candle],
    stock_baseline: float,
    sector_baseline: float,
    historical_relative_returns: Sequence[float],
) -> PercentileResult | None:
    if len(historical_relative_returns) < MINIMUM_OBSERVATIONS:
        return None

    aligned_stock, aligned_sector = _align_by_timestamp(stock_candles, sector_candles)
    if not aligned_stock:
        return None

    stock_return = candle_return(aligned_stock, stock_baseline)
    sector_return = candle_return(aligned_sector, sector_baseline)
    if stock_return is None or sector_return is None:
        return None

    relative_return = stock_return - sector_return
    historical_median = median(historical_relative_returns)
    historical_deviations = [
        abs(value - historical_median) for value in historical_relative_returns
    ]
    deviation = relative_return - historical_median
    return PercentileResult(
        percentile=empirical_percentile(abs(deviation), historical_deviations),
        observation_count=len(historical_relative_returns),
        deviation=deviation,
    )


def volume_pace(
    cumulative_session_volume: int,
    historical_same_minute_volumes: Sequence[float],
) -> float | None:
    if len(historical_same_minute_volumes) < 20:
        return None
    historical_median = median(historical_same_minute_volumes)
    if historical_median <= 0:
        return None
    return cumulative_session_volume / historical_median


def first_volume_pace_crossing(
    samples: Sequence[tuple[datetime, int, Sequence[float]]],
    threshold: float,
) -> tuple[datetime, float] | None:
    previous: float | None = None
    for timestamp, cumulative_volume, historical_volumes in sorted(samples):
        pace = volume_pace(cumulative_volume, historical_volumes)
        if pace is None:
            previous = None
            continue
        if previous is not None and previous < threshold <= pace:
            return timestamp, pace
        previous = pace
    return None


def path_metrics(candles: Sequence[Candle], baseline_price: float) -> PathMetrics:
    if not candles:
        raise ValueError("candles are required")
    if baseline_price <= 0:
        raise ValueError("baseline price must be positive")

    ordered = sorted(candles, key=lambda candle: candle.interval_start)
    upward_candle = max(ordered, key=lambda candle: candle.high)
    downward_candle = min(ordered, key=lambda candle: candle.low)

    highest_prior = ordered[0].high
    lowest_prior = ordered[0].low
    peak_to_trough = 0.0
    trough_to_peak = 0.0
    peak_to_trough_at: datetime | None = None
    trough_to_peak_at: datetime | None = None

    for candle in ordered[1:]:
        decline = (highest_prior - candle.low) / highest_prior
        recovery = (candle.high - lowest_prior) / lowest_prior
        if decline > peak_to_trough:
            peak_to_trough = decline
            peak_to_trough_at = candle.interval_start
        if recovery > trough_to_peak:
            trough_to_peak = recovery
            trough_to_peak_at = candle.interval_start
        highest_prior = max(highest_prior, candle.high)
        lowest_prior = min(lowest_prior, candle.low)

    return PathMetrics(
        upward_excursion=max(0.0, upward_candle.high / baseline_price - 1),
        downward_excursion=max(0.0, 1 - downward_candle.low / baseline_price),
        peak_to_trough_reversal=peak_to_trough,
        trough_to_peak_reversal=trough_to_peak,
        upward_at=upward_candle.interval_start,
        downward_at=downward_candle.interval_start,
        peak_to_trough_at=peak_to_trough_at,
        trough_to_peak_at=trough_to_peak_at,
    )


def most_unusual_path(
    metrics: PathMetrics,
    distributions: Mapping[str, Sequence[float]],
) -> PathSignalResult | None:
    values = {
        "upward_excursion": (metrics.upward_excursion, metrics.upward_at),
        "downward_excursion": (metrics.downward_excursion, metrics.downward_at),
        "peak_to_trough": (metrics.peak_to_trough_reversal, metrics.peak_to_trough_at),
        "trough_to_peak": (metrics.trough_to_peak_reversal, metrics.trough_to_peak_at),
    }
    candidates: list[PathSignalResult] = []
    for event_type, (magnitude, occurred_at) in values.items():
        history = distributions.get(event_type, ())
        if occurred_at is None or len(history) < MINIMUM_OBSERVATIONS:
            continue
        historical_median = median(history)
        deviations = [abs(value - historical_median) for value in history]
        percentile = empirical_percentile(abs(magnitude - historical_median), deviations)
        candidates.append(
            PathSignalResult(
                event_type=event_type,
                magnitude=magnitude,
                percentile=percentile,
                observation_count=len(history),
                occurred_at=occurred_at,
            )
        )

    if not candidates:
        return None
    result = max(candidates, key=lambda candidate: candidate.percentile)
    return result if result.percentile >= SURPRISE_TRIGGER else None


def first_crossed_above(
    candles: Sequence[Candle], baseline: float, threshold: float
) -> datetime | None:
    if baseline >= threshold:
        return None
    for candle in sorted(candles, key=lambda item: item.interval_start):
        if candle.high >= threshold:
            return candle.interval_start
    return None


def first_crossed_below(
    candles: Sequence[Candle], baseline: float, threshold: float
) -> datetime | None:
    if baseline <= threshold:
        return None
    for candle in sorted(candles, key=lambda item: item.interval_start):
        if candle.low <= threshold:
            return candle.interval_start
    return None


def crossed_above(candles: Sequence[Candle], baseline: float, threshold: float) -> bool:
    return first_crossed_above(candles, baseline, threshold) is not None


def crossed_below(candles: Sequence[Candle], baseline: float, threshold: float) -> bool:
    return first_crossed_below(candles, baseline, threshold) is not None

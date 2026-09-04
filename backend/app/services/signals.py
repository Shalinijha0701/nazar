from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Sequence

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


def select_horizon(trading_minutes: int) -> tuple[int | None, str]:
    """Choose a conservative ceiling bucket for the observed interval.

    Uses the smallest supported bucket >= trading_minutes so a shorter
    observed move is compared against a distribution that had at least
    as much time to develop.  Returns (None, "insufficient_interval")
    when fewer than 15 trading minutes have elapsed.
    """
    if trading_minutes < SUPPORTED_HORIZONS[0]:
        return None, "insufficient_interval"
    for horizon in SUPPORTED_HORIZONS:
        if trading_minutes <= horizon:
            return horizon, "full"
    return SUPPORTED_HORIZONS[-1], "partial_coverage"


def empirical_percentile(value: float, observations: Sequence[float]) -> float:
    """Fraction of observations <= value, expressed as 0–100."""
    if not observations:
        raise ValueError("at least one observation is required")
    less_or_equal = sum(observation <= value for observation in observations)
    return 100.0 * less_or_equal / len(observations)


# ---------------------------------------------------------------------------
# Timestamp-aligned sector surprise
# ---------------------------------------------------------------------------

def _align_by_timestamp(
    stock_candles: Sequence[Candle],
    sector_candles: Sequence[Candle],
) -> tuple[list[Candle], list[Candle]]:
    """Return only candles whose interval_start exists in both sequences.

    Illiquid stocks may be missing minute candles that the sector index
    has.  Index-by-index alignment would corrupt the return calculation
    if the lengths differ.  This function joins on the exact timestamp
    so both lists are the same length and correspond to the same moments.

    Trade-off (documented): the join discards unmatched minutes, so the
    stock return is computed over the intersection window only.  This is
    conservative and noted in the README.
    """
    sector_by_ts: dict[datetime, Candle] = {c.interval_start: c for c in sector_candles}
    aligned_stock: list[Candle] = []
    aligned_sector: list[Candle] = []
    for candle in stock_candles:
        match = sector_by_ts.get(candle.interval_start)
        if match is not None:
            aligned_stock.append(candle)
            aligned_sector.append(match)
    return aligned_stock, aligned_sector


def candle_return(candles: Sequence[Candle], baseline_price: float) -> float | None:
    """Log-free percentage return from baseline to the last candle close.

    Returns None if there are no candles or baseline is not positive.
    """
    if not candles or baseline_price <= 0:
        return None
    return (candles[-1].close - baseline_price) / baseline_price


def sector_surprise(
    stock_candles: Sequence[Candle],
    sector_candles: Sequence[Candle],
    stock_baseline: float,
    sector_baseline: float,
    historical_relative_returns: Sequence[float],
) -> PercentileResult | None:
    """Two-sided sector-relative surprise using timestamp-aligned candles.

    Formula (from functional spec):
        x_now = stock_return(t0,t1) - sector_return(t0,t1)
        d_now = abs(x_now - median(historical_relative_returns))
        percentile = empirical_percentile(d_now, historical_deviations)

    Both positive and negative deviations trigger when >= SURPRISE_TRIGGER.
    Direction must be inferred by the caller from (x_now - median) sign.

    Returns None when:
    - fewer than MINIMUM_OBSERVATIONS historical returns are available
    - candle alignment leaves no shared timestamps
    - either baseline is non-positive
    """
    if len(historical_relative_returns) < MINIMUM_OBSERVATIONS:
        return None

    aligned_stock, aligned_sector = _align_by_timestamp(stock_candles, sector_candles)
    if not aligned_stock:
        return None

    r_stock = candle_return(aligned_stock, stock_baseline)
    r_sector = candle_return(aligned_sector, sector_baseline)
    if r_stock is None or r_sector is None:
        return None

    x_now = r_stock - r_sector
    center = median(historical_relative_returns)
    historical_deviations = [abs(v - center) for v in historical_relative_returns]
    d_now = abs(x_now - center)

    return PercentileResult(
        percentile=empirical_percentile(d_now, historical_deviations),
        observation_count=len(historical_relative_returns),
        deviation=x_now - center,  # signed; caller reads direction from sign
    )


# ---------------------------------------------------------------------------
# Volume pace (same-time-of-day median, not raw volume)
# ---------------------------------------------------------------------------

def volume_pace(
    cumulative_session_volume: int,
    historical_same_minute_medians: Sequence[float],
) -> float | None:
    """Return V(m) / median(historical same-minute cumulative volumes).

    Uses the same-time-of-day historical median so early-session minutes
    are not penalised for having lower raw volume than midday minutes.

    Returns None when fewer than 20 historical sessions exist or the
    historical median is zero (no meaningful baseline).

    Trigger threshold is the caller's responsibility (the personal rule).
    """
    if len(historical_same_minute_medians) < 20:
        return None
    hist_median = median(historical_same_minute_medians)
    if hist_median <= 0:
        return None
    return cumulative_session_volume / hist_median


# ---------------------------------------------------------------------------
# Path metrics (excursion and reversal from minute candles)
# ---------------------------------------------------------------------------

def path_metrics(candles: Sequence[Candle], baseline_price: float) -> PathMetrics:
    """Compute excursion and reversal magnitudes over a candle sequence.

    All four metrics use the historical excursion/reversal distribution
    for the same trading-time horizon to determine whether the event is
    statistically unusual (caller compares against distribution).

    Baseline price is the last confirmed price at reviewed_through (t0).
    """
    if not candles:
        raise ValueError("candles are required")
    if baseline_price <= 0:
        raise ValueError("baseline price must be positive")

    upward = max(candle.high / baseline_price - 1 for candle in candles)
    downward = max(1 - candle.low / baseline_price for candle in candles)

    highest_seen = candles[0].high
    lowest_seen = candles[0].low
    peak_to_trough = 0.0
    trough_to_peak = 0.0

    for candle in candles[1:]:
        # OHLC data does not reveal whether a candle's high or low came first.
        # Compare only an earlier completed candle with a later candle.
        peak_to_trough = max(
            peak_to_trough,
            (highest_seen - candle.low) / highest_seen,
        )
        trough_to_peak = max(
            trough_to_peak,
            (candle.high - lowest_seen) / lowest_seen,
        )
        highest_seen = max(highest_seen, candle.high)
        lowest_seen = min(lowest_seen, candle.low)

    return PathMetrics(
        upward_excursion=max(0.0, upward),
        downward_excursion=max(0.0, downward),
        peak_to_trough_reversal=peak_to_trough,
        trough_to_peak_reversal=trough_to_peak,
    )


# ---------------------------------------------------------------------------
# Personal rule: price crossing (raw threshold check on candle highs/lows)
# ---------------------------------------------------------------------------

def crossed_above(candles: Sequence[Candle], baseline: float, threshold: float) -> bool:
    """True when baseline was below threshold and a candle high reached it."""
    return baseline < threshold and any(candle.high >= threshold for candle in candles)


def crossed_below(candles: Sequence[Candle], baseline: float, threshold: float) -> bool:
    """True when baseline was above threshold and a candle low reached it."""
    return baseline > threshold and any(candle.low <= threshold for candle in candles)

from math import ceil
from statistics import median
from typing import Sequence

from app.models import Candle
from app.services.signals import path_metrics


PERCENTILE_LEVELS = (50.0, 75.0, 90.0, 95.0, 97.5, 99.0)


def percentile_breakpoints(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise ValueError("at least one observation is required")
    ordered = sorted(float(value) for value in values)
    result: dict[str, float] = {}
    for level in PERCENTILE_LEVELS:
        index = max(0, ceil(level / 100 * len(ordered)) - 1)
        result[f"p{level:g}"] = ordered[index]
    return result


def sector_relative_observations(
    stock_closes: Sequence[float],
    sector_closes: Sequence[float],
    horizon_steps: int,
) -> list[float]:
    if horizon_steps <= 0:
        raise ValueError("horizon_steps must be positive")
    count = min(len(stock_closes), len(sector_closes))
    observations: list[float] = []
    stride = max(1, horizon_steps // 4)
    for start in range(0, count - horizon_steps, stride):
        end = start + horizon_steps
        stock_return = stock_closes[end] / stock_closes[start] - 1
        sector_return = sector_closes[end] / sector_closes[start] - 1
        observations.append(stock_return - sector_return)
    return observations


def path_observations(
    candles: Sequence[Candle],
    horizon_steps: int,
) -> dict[str, list[float]]:
    if horizon_steps <= 0:
        raise ValueError("horizon_steps must be positive")
    distributions = {
        "upward_excursion": [],
        "downward_excursion": [],
        "peak_to_trough": [],
        "trough_to_peak": [],
    }
    ordered = sorted(candles, key=lambda candle: candle.interval_start)
    stride = max(1, horizon_steps // 4)
    for start in range(0, len(ordered) - horizon_steps, stride):
        window = ordered[start : start + horizon_steps + 1]
        metrics = path_metrics(window, window[0].close)
        distributions["upward_excursion"].append(metrics.upward_excursion)
        distributions["downward_excursion"].append(metrics.downward_excursion)
        distributions["peak_to_trough"].append(metrics.peak_to_trough_reversal)
        distributions["trough_to_peak"].append(metrics.trough_to_peak_reversal)
    return distributions


def deviation_breakpoints(values: Sequence[float]) -> dict[str, float]:
    center = median(values)
    return {
        "median": center,
        **percentile_breakpoints([abs(value - center) for value in values]),
    }

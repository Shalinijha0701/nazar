import argparse
from datetime import datetime

from app.auth import supabase_client
from app.models import Candle
from app.services.distributions import (
    deviation_breakpoints,
    path_observations,
    percentile_breakpoints,
    sector_relative_observations,
)
from app.services.signals import MINIMUM_OBSERVATIONS, SUPPORTED_HORIZONS


def load_candles(symbol: str) -> list[Candle]:
    client = supabase_client()
    rows: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        result = (
            client.table("market_candles")
            .select("symbol,interval_start,open,high,low,close,volume")
            .eq("symbol", symbol)
            .eq("interval", "1m")
            .order("interval_start")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows.extend(result.data)
        if len(result.data) < page_size:
            break
        offset += page_size
    return [Candle(**row) for row in rows]


def aligned_candles(
    stock: list[Candle],
    sector: list[Candle],
) -> tuple[list[Candle], list[Candle]]:
    sector_by_time = {candle.interval_start: candle for candle in sector}
    pairs = [
        (candle, sector_by_time[candle.interval_start])
        for candle in stock
        if candle.interval_start in sector_by_time
    ]
    return [pair[0] for pair in pairs], [pair[1] for pair in pairs]


def rebuild(symbol: str, sector_index: str) -> int:
    stock, sector = aligned_candles(load_candles(symbol), load_candles(sector_index))
    if not stock:
        raise RuntimeError("No aligned one-minute candles found")

    rows: list[dict] = []
    for horizon in SUPPORTED_HORIZONS:
        relative = sector_relative_observations(
            [candle.close for candle in stock],
            [candle.close for candle in sector],
            horizon,
        )
        if len(relative) < MINIMUM_OBSERVATIONS:
            continue

        common = {
            "symbol": symbol,
            "horizon_minutes": horizon,
            "observation_count": len(relative),
            "lookback_start": stock[0].interval_start.isoformat(),
            "lookback_end": stock[-1].interval_start.isoformat(),
            "session_offset_minutes": None,
            "method_version": "rolling-overlap-v1",
        }
        rows.append(
            {
                **common,
                "distribution_type": "sector_relative_deviation",
                "sector_index_used": sector_index,
                "percentile_breakpoints": deviation_breakpoints(relative),
            }
        )
        for event_type, values in path_observations(stock, horizon).items():
            rows.append(
                {
                    **common,
                    "distribution_type": event_type,
                    "sector_index_used": None,
                    "percentile_breakpoints": percentile_breakpoints(values),
                }
            )

    if rows:
        (
            supabase_client()
            .table("stock_distributions")
            .upsert(rows, on_conflict="symbol,horizon_minutes,distribution_type")
            .execute()
        )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--sector", required=True)
    args = parser.parse_args()
    updated = rebuild(args.symbol.upper(), args.sector.upper())
    print(f"Updated {updated} distributions at {datetime.now().isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()

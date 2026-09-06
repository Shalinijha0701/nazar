from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models import Candle, CatchupCard, CatchupResponse, ChartPoint, DataState, Signal, SignalKind
from app.providers.replay import ReplayProvider
from app.repository import PathEventRecord, RuleRecord, WatchlistItemRecord
from app.services.events import confirmed_path_signals
from app.services.signals import (
    SURPRISE_TRIGGER,
    first_crossed_above,
    first_crossed_below,
    first_volume_pace_crossing,
    most_unusual_path,
    path_metrics,
    sector_surprise,
    select_horizon,
)
from app.services.trading_time import trading_minutes_between


DEMO_START = datetime(2026, 9, 4, 5, 45, tzinfo=UTC)
DEMO_END = datetime(2026, 9, 4, 8, 30, tzinfo=UTC)
VOLUME_EVENT_AT = datetime(2026, 9, 4, 7, 30, tzinfo=UTC)


@dataclass(frozen=True)
class DemoInstrument:
    company_name: str
    sector_index: str
    prices: tuple[float, ...]
    data_state: DataState
    narrative: str


INSTRUMENTS = {
    "RELIANCE": DemoInstrument(
        "Reliance Industries",
        "NIFTY50",
        (2789.2, 2794.4, 2801.1, 2810.8, 2822.5, 2834.7, 2849.4, 2868.1, 2857.6, 2848.9, 2844.2, 2847.9),
        DataState.FRESH,
        "Reliance separated from the broad market and retained most of its move.",
    ),
    "INFY": DemoInstrument(
        "Infosys",
        "NIFTY_IT",
        (1762.4, 1771.6, 1788.2, 1810.4, 1820.0, 1802.8, 1789.6, 1778.1, 1768.5, 1764.9, 1763.8, 1764.2),
        DataState.FRESH,
        "The closing price looks quiet, but the interval contained a rare spike and reversal.",
    ),
    "HDFCBANK": DemoInstrument(
        "HDFC Bank",
        "NIFTY_BANK",
        (1688.1, 1689.4, 1692.8, 1695.3, 1698.7, 1701.8, 1705.2, 1708.4, 1710.3, 1711.1, 1711.4, 1711.6),
        DataState.FRESH,
        "Price remained orderly while volume accelerated beyond its usual time-of-day pace.",
    ),
    "TCS": DemoInstrument(
        "Tata Consultancy Services",
        "NIFTY_IT",
        (4210.6, 4214.0, 4218.7, 4220.1, 4224.8, 4228.3, 4231.0, 4234.5, 4236.2, 4238.1, 4240.0, 4241.2),
        DataState.FRESH,
        "The move remained inside TCS's normal sector-adjusted range.",
    ),
    "MARUTI": DemoInstrument(
        "Maruti Suzuki",
        "NIFTY_AUTO",
        (12754.0, 12731.0, 12742.0, 12750.0, 12768.0, 12761.0, 12772.0, 12785.0, 12780.0, 12792.0, 12789.0, 12795.0),
        DataState.FRESH,
        "No personal condition or unusual sector-relative movement was detected.",
    ),
    "SUNPHARMA": DemoInstrument(
        "Sun Pharmaceutical",
        "NIFTY_PHARMA",
        (1812.5, 1811.2, 1814.8, 1816.3, 1815.9, 1817.1, 1819.3, 1818.4, 1819.0, 1820.2, 1819.6, 1821.1),
        DataState.MARKET_CLOSED,
        "The completed session is available and is not treated as stale.",
    ),
    "ITC": DemoInstrument(
        "ITC",
        "NIFTY_FMCG",
        (498.4, 498.8, 499.2, 498.9, 499.4, 499.7, 500.1, 499.8, 500.0, 500.2, 500.4, 500.3),
        DataState.FRESH,
        "The move closely followed its sector and remained normal noise.",
    ),
    "TATAMOTORS": DemoInstrument(
        "Tata Motors",
        "NIFTY_AUTO",
        (1032.2, 1030.1, 1034.2, 1036.0, 1034.7, 1037.1, 1035.9, 1038.2, 1039.0, 1038.6, 1040.1, 1040.4),
        DataState.FRESH,
        "Price and path remained inside the expected automobile-sector range.",
    ),
    "IRCTC": DemoInstrument(
        "Indian Railway Catering & Tourism",
        "NIFTY500",
        (948.6, 949.1, 950.3, 951.0, 950.6, 951.2),
        DataState.UNAVAILABLE,
        "The provider stopped updating this symbol, so no new signal was inferred.",
    ),
    "ZOMATO": DemoInstrument(
        "Eternal",
        "NIFTY_CONSUMER",
        (268.2, 269.0, 269.4, 270.1, 271.0, 270.8),
        DataState.UNAVAILABLE,
        "Current market data is unavailable and the stock is excluded from attention ranking.",
    ),
    "LTIM": DemoInstrument(
        "LTIMindtree",
        "NIFTY_IT",
        (5874.2,) * 12,
        DataState.LIMITED_HISTORY,
        "Tracking has started; a completed interval is required before statistical scoring.",
    ),
    "BAJFINANCE": DemoInstrument(
        "Bajaj Finance",
        "NIFTY_FIN_SERVICE",
        (7324.6,) * 12,
        DataState.LIMITED_HISTORY,
        "Tracking has started; a completed interval is required before statistical scoring.",
    ),
    "TITAN": DemoInstrument(
        "Titan Company",
        "NIFTY_CONSUMER",
        (3618.4,) * 12,
        DataState.LIMITED_HISTORY,
        "Tracking has started; a completed interval is required before statistical scoring.",
    ),
}


INDEX_PRICES = {
    "NIFTY50": (24200.0, 24208.0, 24214.0, 24219.0, 24225.0, 24229.0, 24234.0, 24239.0, 24236.0, 24232.0, 24229.0, 24231.0),
    "NIFTY_IT": (18400.0, 18412.0, 18425.0, 18441.0, 18458.0, 18471.0, 18483.0, 18497.0, 18511.0, 18528.0, 18540.0, 18585.0),
}


def _candles(symbol: str, prices: tuple[float, ...]) -> list[Candle]:
    candles: list[Candle] = []
    previous = prices[0]
    for index, close in enumerate(prices):
        candles.append(
            Candle(
                symbol=symbol,
                interval_start=DEMO_START + timedelta(minutes=index * 15),
                open=previous,
                high=max(previous, close),
                low=min(previous, close),
                close=close,
                volume=100_000 + index * 8_000,
            )
        )
        previous = close
    return candles


DEMO_CANDLES = {
    **{symbol: _candles(symbol, instrument.prices) for symbol, instrument in INSTRUMENTS.items()},
    **{symbol: _candles(symbol, prices) for symbol, prices in INDEX_PRICES.items()},
}


def _sector_history() -> list[float]:
    inner = [0.018 * (index + 1) / 123 for index in range(123)]
    tails = [0.025, 0.027, 0.03]
    return [-value for value in reversed([*inner, *tails])] + [*inner, *tails]


SECTOR_HISTORY = {
    "RELIANCE": _sector_history(),
}


INFY_PATH_HISTORY = {
    "peak_to_trough": [0.001 + index * 0.024 / 245 for index in range(246)]
    + [0.04, 0.041, 0.042, 0.043, 0.044, 0.045],
}


HDFC_SAME_MINUTE_VOLUMES = [800_000.0] * 20
HDFC_VOLUME_SAMPLES = [
    (VOLUME_EVENT_AT - timedelta(minutes=15), 1_408_000, HDFC_SAME_MINUTE_VOLUMES),
    (VOLUME_EVENT_AT, 1_488_000, HDFC_SAME_MINUTE_VOLUMES),
]


def _interval(candles: list[Candle], reviewed: datetime, evaluated: datetime) -> tuple[Candle, list[Candle]]:
    ordered = sorted(candles, key=lambda candle: candle.interval_start)
    baseline = max(
        (candle for candle in ordered if candle.interval_start <= reviewed),
        key=lambda candle: candle.interval_start,
        default=ordered[0],
    )
    active = [
        candle
        for candle in ordered
        if reviewed < candle.interval_start <= evaluated
    ]
    return baseline, active


def _price_signal(rule: RuleRecord, baseline: float, candles: list[Candle]) -> Signal | None:
    crossed_at = (
        first_crossed_above(candles, baseline, rule.threshold)
        if rule.rule_type == "price_above"
        else first_crossed_below(candles, baseline, rule.threshold)
    )
    if crossed_at is None:
        return None
    direction = "above" if rule.rule_type == "price_above" else "below"
    return Signal(
        kind=SignalKind.PERSONAL_RULE,
        label=f"Crossed {direction} your ₹{rule.threshold:,.2f} level",
        occurred_at=crossed_at,
        direction=direction,
        evidence={"threshold": rule.threshold},
    )


def _signals_for_item(
    item: WatchlistItemRecord,
    rules: list[RuleRecord],
    candles_by_symbol: dict[str, list[Candle]],
    reviewed: datetime,
    evaluated: datetime,
    horizon: int | None,
) -> list[Signal]:
    instrument = INSTRUMENTS.get(item.symbol)
    if not instrument or instrument.data_state in {DataState.UNAVAILABLE, DataState.LIMITED_HISTORY}:
        return []

    stock_baseline, active_stock = _interval(candles_by_symbol[item.symbol], reviewed, evaluated)
    if not active_stock:
        return []

    signals: list[Signal] = []
    for rule in rules:
        if not rule.armed or rule.watchlist_item_id != item.id:
            continue
        if rule.rule_type in {"price_above", "price_below"}:
            signal = _price_signal(rule, stock_baseline.close, active_stock)
            if signal:
                signals.append(signal)
        elif (
            rule.rule_type == "volume_pace"
            and item.symbol == "HDFCBANK"
            and reviewed < VOLUME_EVENT_AT <= evaluated
        ):
            crossing = first_volume_pace_crossing(HDFC_VOLUME_SAMPLES, rule.threshold)
            if crossing:
                crossed_at, pace = crossing
                signals.append(
                    Signal(
                        kind=SignalKind.PERSONAL_RULE,
                        label=f"Volume pace crossed {rule.threshold:.1f}×",
                        occurred_at=crossed_at,
                        direction="above",
                        evidence={
                            "volume_pace": round(pace, 2),
                            "comparison_sessions": len(HDFC_SAME_MINUTE_VOLUMES),
                        },
                    )
                )

    if horizon is None:
        return signals

    sector_history = SECTOR_HISTORY.get(item.symbol)
    sector_candles = candles_by_symbol.get(item.sector_index)
    if sector_history and sector_candles:
        sector_baseline, active_sector = _interval(sector_candles, reviewed, evaluated)
        result = sector_surprise(
            [stock_baseline, *active_stock],
            [sector_baseline, *active_sector],
            stock_baseline.close,
            sector_baseline.close,
            sector_history,
        )
        if result and result.percentile >= SURPRISE_TRIGGER:
            direction = "above_sector" if result.deviation > 0 else "below_sector"
            signals.append(
                Signal(
                    kind=SignalKind.SECTOR_SURPRISE,
                    label=f"{result.percentile:.1f}th percentile relative to sector",
                    occurred_at=active_stock[-1].interval_start,
                    percentile=round(result.percentile, 1),
                    observation_count=result.observation_count,
                    direction=direction,
                    evidence={
                        "deviation_percent": round(result.deviation * 100, 2),
                        "horizon_minutes": horizon,
                        "lookback_start": "2025-09-01",
                        "lookback_end": "2026-08-31",
                    },
                )
            )

    if item.symbol == "INFY":
        metrics = path_metrics([stock_baseline, *active_stock], stock_baseline.close)
        result = most_unusual_path(metrics, INFY_PATH_HISTORY)
        if result:
            signals.append(
                Signal(
                    kind=SignalKind.PATH_EVENT,
                    label="Spike reversed before the interval ended",
                    occurred_at=result.occurred_at,
                    percentile=round(result.percentile, 1),
                    observation_count=result.observation_count,
                    direction=result.event_type,
                    evidence={
                        "magnitude_percent": round(result.magnitude * 100, 2),
                        "peak_price": max(candle.high for candle in active_stock),
                        "horizon_minutes": horizon,
                    },
                )
            )
    return signals


async def recorded_demo_catchup(
    watchlist_id: str,
    items: list[WatchlistItemRecord],
    rules: list[RuleRecord],
    reviewed: datetime,
    evaluated: datetime = DEMO_END,
    confirmed_events: list[PathEventRecord] | None = None,
) -> dict:
    evaluated = min(evaluated, DEMO_END)
    reviewed = min(reviewed, evaluated)
    trading_minutes = trading_minutes_between(max(reviewed, DEMO_START), evaluated)
    horizon, coverage = select_horizon(trading_minutes)

    provider = ReplayProvider(DEMO_CANDLES)
    requested_symbols = {item.symbol for item in items}
    requested_symbols.update(item.sector_index for item in items)
    candles_by_symbol = await provider.candles(
        sorted(requested_symbols),
        DEMO_START,
        evaluated,
    )

    attention: list[CatchupCard] = []
    normal: list[CatchupCard] = []
    unavailable: list[CatchupCard] = []

    for item in items:
        instrument = INSTRUMENTS.get(item.symbol)
        candles = candles_by_symbol.get(item.symbol, [])
        state = instrument.data_state if instrument else DataState.LIMITED_HISTORY
        narrative = instrument.narrative if instrument else "Tracking has started; more data is required."
        has_unevaluated_volume_rule = item.symbol != "HDFCBANK" and any(
            rule.armed and rule.rule_type == "volume_pace" and rule.watchlist_item_id == item.id
            for rule in rules
        )
        if has_unevaluated_volume_rule:
            narrative += (
                " Your volume-pace rule was not evaluated: the recorded replay demo"
                " only includes volume history for HDFCBANK."
            )
        if candles:
            baseline, _ = _interval(candles, reviewed, evaluated)
            current = candles[-1].close
            change = (current - baseline.close) / baseline.close * 100
            chart = [ChartPoint(timestamp=candle.interval_start, price=candle.close) for candle in candles]
            last_updated = candles[-1].interval_start
            baseline_price = baseline.close
        else:
            current = None
            baseline_price = None
            change = None
            chart = []
            last_updated = None

        signals = _signals_for_item(
            item,
            rules,
            candles_by_symbol,
            reviewed,
            evaluated,
            horizon,
        )
        if state == DataState.UNAVAILABLE:
            signals.extend(confirmed_path_signals(confirmed_events or [], item.symbol))
        card = CatchupCard(
            item_id=item.id,
            symbol=item.symbol,
            company_name=item.company_name,
            sector_index=item.sector_index,
            current_price=current,
            baseline_price=baseline_price,
            change_since_review_percent=round(change, 2) if change is not None else None,
            data_state=state,
            last_updated_at=last_updated,
            narrative=narrative,
            chart=chart,
            signals=signals,
        )
        if state == DataState.UNAVAILABLE:
            unavailable.append(card)
        elif signals:
            attention.append(card)
        else:
            normal.append(card)

    response = CatchupResponse(
        watchlist_id=watchlist_id,
        source="replay",
        reviewed_through=reviewed,
        evaluated_through=evaluated,
        trading_minutes=trading_minutes,
        horizon_minutes=horizon,
        coverage=coverage,
        counts={
            "attention": len(attention),
            "normal": len(normal),
            "data_unavailable": len(unavailable),
        },
        attention=attention,
        normal=normal,
        data_unavailable=unavailable,
    )
    return response.model_dump(mode="json")

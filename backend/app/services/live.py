from datetime import datetime, timedelta

from app.models import CatchupCard, CatchupResponse, ChartPoint, DataState, Signal, SignalKind
from app.providers.base import MarketDataProvider
from app.repository import PathEventRecord, RuleRecord, WatchlistItemRecord
from app.services.events import confirmed_path_signals
from app.services.signals import first_crossed_above, first_crossed_below, select_horizon
from app.services.trading_time import is_market_open, trading_minutes_between


async def live_market_catchup(
    watchlist_id: str,
    items: list[WatchlistItemRecord],
    rules: list[RuleRecord],
    reviewed: datetime,
    evaluated: datetime,
    provider: MarketDataProvider,
    confirmed_events: list[PathEventRecord] | None = None,
) -> dict:
    trading_minutes = trading_minutes_between(reviewed, evaluated)
    horizon, coverage = select_horizon(trading_minutes)
    symbols = [item.symbol for item in items]
    candles_by_symbol = await provider.candles(
        symbols,
        reviewed - timedelta(minutes=1),
        evaluated,
    )

    rules_by_item: dict[str, list[RuleRecord]] = {}
    for rule in rules:
        rules_by_item.setdefault(rule.watchlist_item_id, []).append(rule)

    attention: list[CatchupCard] = []
    normal: list[CatchupCard] = []
    unavailable: list[CatchupCard] = []

    for item in items:
        candles = sorted(candles_by_symbol.get(item.symbol, []), key=lambda candle: candle.interval_start)
        if not candles:
            unavailable.append(
                CatchupCard(
                    item_id=item.id,
                    symbol=item.symbol,
                    company_name=item.company_name,
                    sector_index=item.sector_index,
                    current_price=None,
                    baseline_price=None,
                    change_since_review_percent=None,
                    data_state=DataState.UNAVAILABLE,
                    last_updated_at=None,
                    narrative="The provider returned no fresh candles for this interval.",
                    chart=[],
                    signals=confirmed_path_signals(confirmed_events or [], item.symbol),
                )
            )
            continue

        latest_at = candles[-1].interval_start
        if is_market_open(evaluated) and evaluated - latest_at > timedelta(minutes=3):
            unavailable.append(
                CatchupCard(
                    item_id=item.id,
                    symbol=item.symbol,
                    company_name=item.company_name,
                    sector_index=item.sector_index,
                    current_price=candles[-1].close,
                    baseline_price=candles[0].close,
                    change_since_review_percent=None,
                    data_state=DataState.UNAVAILABLE,
                    last_updated_at=latest_at,
                    narrative="The latest candle is stale, so no new signal was calculated.",
                    chart=[ChartPoint(timestamp=candle.interval_start, price=candle.close) for candle in candles],
                    signals=confirmed_path_signals(confirmed_events or [], item.symbol),
                )
            )
            continue

        baseline = candles[0].close
        active = [candle for candle in candles if candle.interval_start > reviewed]
        signals: list[Signal] = []
        item_rules = rules_by_item.get(item.id, [])
        has_unevaluated_volume_rule = any(
            rule.armed and rule.rule_type == "volume_pace" for rule in item_rules
        )
        for rule in item_rules:
            if not rule.armed or rule.rule_type == "volume_pace":
                continue
            crossed_at = (
                first_crossed_above(active, baseline, rule.threshold)
                if rule.rule_type == "price_above"
                else first_crossed_below(active, baseline, rule.threshold)
            )
            if crossed_at:
                direction = "above" if rule.rule_type == "price_above" else "below"
                signals.append(
                    Signal(
                        kind=SignalKind.PERSONAL_RULE,
                        label=f"Crossed {direction} your ₹{rule.threshold:,.2f} level",
                        occurred_at=crossed_at,
                        direction=direction,
                        evidence={"threshold": rule.threshold},
                    )
                )

        narrative = "Live price and personal price rules are available; statistical distributions are not loaded."
        if has_unevaluated_volume_rule:
            narrative += (
                " Your volume-pace rule was not evaluated because historical same-minute"
                " volume data is not available in live mode yet."
            )

        current = candles[-1].close
        card = CatchupCard(
            item_id=item.id,
            symbol=item.symbol,
            company_name=item.company_name,
            sector_index=item.sector_index,
            current_price=current,
            baseline_price=baseline,
            change_since_review_percent=round((current - baseline) / baseline * 100, 2),
            data_state=DataState.LIMITED_HISTORY if is_market_open(evaluated) else DataState.MARKET_CLOSED,
            last_updated_at=candles[-1].interval_start,
            narrative=narrative,
            chart=[ChartPoint(timestamp=candle.interval_start, price=candle.close) for candle in candles],
            signals=signals,
        )
        (attention if signals else normal).append(card)

    response = CatchupResponse(
        watchlist_id=watchlist_id,
        source="groww",
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

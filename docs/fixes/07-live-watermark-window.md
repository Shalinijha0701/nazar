# Fix G7 — Live catch-up window capped at 4 hours

**Severity:** High · **Status:** Fixed

## Problem

The product premise is "a watchlist that remembers what happened while you were away" — days away included. But in live mode, a user who had never acknowledged got a default watermark of only 4 wall-clock hours back:

```python
# backend/app/main.py (before)
evaluated = datetime.now(UTC).replace(second=0, microsecond=0)
reviewed = store.get_watermark(user_id, resolved_id, evaluated - timedelta(hours=4))
```

Two issues:

1. A first-time (or long-absent, never-acknowledged) user's catch-up covered at most 4 hours, hiding everything earlier.
2. Four **wall-clock** hours often contain zero **trading** minutes (evenings, weekends), producing `coverage="insufficient_interval"` and an empty-feeling product exactly when a returning user opens it.

The signal engine itself supports much longer windows: `SUPPORTED_HORIZONS` in `backend/app/services/signals.py` goes up to 1875 trading minutes (5 full NSE sessions of 375 minutes).

## Fix (implemented)

The default lookback now walks back far enough to cover the largest supported horizon in *trading* minutes, using the existing `trading_minutes_between` helper:

```python
# backend/app/main.py (after)
def default_live_watermark(evaluated: datetime) -> datetime:
    """Walk back until the window covers the largest supported horizon in trading minutes."""
    candidate = evaluated - timedelta(days=1)
    earliest = evaluated - timedelta(days=14)
    while (
        trading_minutes_between(candidate, evaluated) < SUPPORTED_HORIZONS[-1]
        and candidate > earliest
    ):
        candidate -= timedelta(days=1)
    return candidate
```

used as:

```python
reviewed = store.get_watermark(user_id, resolved_id, default_live_watermark(evaluated))
```

Properties:

- Covers ≥ 1875 trading minutes (≈ 5 sessions) whenever the calendar allows, so `select_horizon` can use every supported horizon and a returning user sees a real interval.
- The 14-day floor bounds the candle fetch even across long exchange holidays.
- Users who *have* acknowledged are untouched — the stored watermark still wins.

## Related consideration (not changed)

`GrowwProvider.candles` is called with the full `[reviewed, evaluated]` range at 1-minute granularity — for a 5-session window that is ~1875 candles per symbol, batched under an 8-way semaphore, which the provider already handles. If provider rate limits become a problem, fetch `5minute` candles for windows above one session; the signal functions are interval-agnostic.

## Verification

`backend/tests/test_live.py` (added) asserts that `default_live_watermark`:

- returns a watermark whose trading-minute span to `evaluated` is ≥ 1875 for a mid-week evaluation time;
- never walks back more than 14 days;
- leaves an explicitly stored watermark in control (endpoint uses `get_watermark(..., default=...)` semantics unchanged).

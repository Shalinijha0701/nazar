# Fix G4 — Volume-pace rules silently ignored in live mode

**Severity:** High · **Status:** Partially fixed (honest reporting implemented; full evaluation is guide only)

## Problem

The product lets users create `volume_pace` rules end to end — the rule dialog in `app/nazar-dashboard.tsx` offers "Volume pace exceeds", `POST /api/watchlists/items/{id}/rules` accepts and stores it — but the live signal path dropped them without a trace:

```python
# backend/app/services/live.py (before)
for rule in rules_by_item.get(item.id, []):
    if not rule.armed or rule.rule_type == "volume_pace":
        continue
```

A user who saved a volume-pace rule in live mode got no signal, no error, and a narrative implying their rules were being watched ("Live price and personal rules are available…"). That is a silent product lie.

## Implemented fix — honest narrative

`live_market_catchup` now tracks whether an item has volume-pace rules that could not be evaluated and says so on the card:

```python
has_unevaluated_volume_rule = any(
    rule.armed and rule.rule_type == "volume_pace"
    for rule in rules_by_item.get(item.id, [])
)
...
narrative = (
    "Live price and personal price rules are available; statistical distributions are not loaded."
)
if has_unevaluated_volume_rule:
    narrative += (
        " Your volume-pace rule was not evaluated because historical same-minute"
        " volume data is not available in live mode yet."
    )
```

This keeps the evidence-first promise: the UI never implies a rule was checked when it was not.

## Full fix — evaluate volume pace live

`app/services/signals.py` already contains the pure functions (`volume_pace`, `first_volume_pace_crossing`); what is missing is the data: cumulative session volume per minute, and the historical distribution of same-time-of-day cumulative volume.

1. **Ingest 1-minute candles** into `market_candles` (schema exists in `supabase/schema.sql`) via a scheduled job calling `GrowwProvider.candles(...)` per tracked symbol.

2. **Build same-minute historical volumes.** For each symbol and each session-minute offset `m`, collect the cumulative volume from session open through `m` across the last N (≥ 20) sessions:

   ```python
   def same_minute_cumulative_volumes(
       candles: Sequence[Candle], session_offset_minutes: int, sessions: int = 20
   ) -> list[float]:
       by_day: dict[date, list[Candle]] = {}
       for candle in candles:
           local = candle.interval_start.astimezone(INDIA_TZ)
           by_day.setdefault(local.date(), []).append(candle)
       observations = []
       for day, day_candles in sorted(by_day.items())[-sessions:]:
           open_dt = datetime.combine(day, SESSION_OPEN, INDIA_TZ)
           cutoff = open_dt + timedelta(minutes=session_offset_minutes)
           cumulative = sum(c.volume for c in day_candles if c.interval_start.astimezone(INDIA_TZ) <= cutoff)
           if cumulative > 0:
               observations.append(float(cumulative))
       return observations
   ```

   Store these per (symbol, session_offset) in `stock_distributions` with `distribution_type='volume_pace'` and `session_offset_minutes` set — the column already exists.

3. **Evaluate in `live_market_catchup`.** For each minute in the interval, build `(timestamp, cumulative_session_volume, historical_volumes)` samples from the fetched candles plus stored distributions and call the existing `first_volume_pace_crossing(samples, rule.threshold)`. Emit the same `Signal(kind=PERSONAL_RULE, ...)` shape the replay path produces in `app/demo.py` (`volume_pace` / `comparison_sessions` evidence keys), so the frontend `signalDetail` mapper works unchanged.

4. Once implemented, remove the "was not evaluated" narrative branch.

## Verification

- Implemented part: create a `volume_pace` rule with `NAZAR_MARKET_PROVIDER=groww` and confirm the card narrative names the unevaluated rule; `backend/tests/test_live.py::test_volume_rule_reported_as_unevaluated` (added) covers it deterministically with a stub provider.
- Full fix: unit-test `same_minute_cumulative_volumes` against synthetic multi-session candles; integration-test that a cumulative volume ≥ threshold × median produces a `personal_rule` signal with `volume_pace` evidence.

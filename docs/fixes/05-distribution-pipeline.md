# Fix G5 — Dead distribution pipeline: `stock_distributions` is written but never read

**Severity:** High · **Status:** Guide only (requires a populated Supabase instance)

## Problem

The repository ships a complete write path for historical distributions:

- `backend/app/jobs/rebuild_distributions.py` computes sector-relative and path distributions per horizon and upserts them into `stock_distributions`.
- `supabase/schema.sql` defines the table, including `percentile_breakpoints jsonb`, `observation_count`, and lookback metadata.
- The README documents running the job.

But **nothing reads the table**. `live_market_catchup` (`backend/app/services/live.py`) hardcodes:

```python
narrative="Live price and personal rules are available; statistical distributions are not loaded.",
```

and never attempts sector-surprise or path-event scoring. The signal functions in `app/services/signals.py` are only exercised by the replay path (`app/demo.py`) using in-memory demo data. So the product's two headline statistical signals are unreachable in live mode even after operators run the rebuild job — the pipeline is a dead end.

## Fix — load distributions and score live intervals

### 1. Store raw observations alongside breakpoints

`sector_surprise()` and `most_unusual_path()` need the observation list (they compute empirical percentiles), while the job currently stores only breakpoints. Extend the job's rows with the raw values (they are small — a few hundred floats):

```python
# rebuild_distributions.py, inside rebuild()
rows.append(
    {
        **common,
        "distribution_type": "sector_relative_deviation",
        "sector_index_used": sector_index,
        "percentile_breakpoints": deviation_breakpoints(relative),
        "observations": relative,          # new
    }
)
```

with a schema migration:

```sql
alter table public.stock_distributions
  add column if not exists observations jsonb not null default '[]'::jsonb;
```

(Alternative: keep only breakpoints and interpolate percentiles from them — smaller rows, but changes the documented empirical-percentile formula in `docs/functional-spec.md`. Storing observations is the faithful option.)

### 2. Add a distribution loader

New `backend/app/services/distribution_store.py`:

```python
from app.auth import supabase_client

def load_distributions(symbol: str, horizon_minutes: int) -> dict[str, list[float]]:
    """Return {distribution_type: observations} for one symbol and horizon."""
    result = (
        supabase_client()
        .table("stock_distributions")
        .select("distribution_type,observations")
        .eq("symbol", symbol)
        .eq("horizon_minutes", horizon_minutes)
        .execute()
    )
    return {
        str(row["distribution_type"]): [float(v) for v in row["observations"]]
        for row in result.data
    }
```

### 3. Wire it into `live_market_catchup`

After computing `horizon`, and per item with fresh candles:

```python
distributions = load_distributions(item.symbol, horizon) if horizon else {}

# Sector surprise — mirrors app/demo.py:_signals_for_item
history = distributions.get("sector_relative_deviation")
sector_candles = candles_by_symbol.get(item.sector_index, [])
if history and sector_candles:
    result = sector_surprise(candles, sector_candles, baseline, sector_candles[0].close, history)
    if result and result.percentile >= SURPRISE_TRIGGER:
        signals.append(Signal(kind=SignalKind.SECTOR_SURPRISE, ...))

# Path events
path_history = {k: v for k, v in distributions.items() if k in PATH_EVENT_TYPES}
if path_history:
    metrics = path_metrics(candles, baseline)
    result = most_unusual_path(metrics, path_history)
    if result:
        signals.append(Signal(kind=SignalKind.PATH_EVENT, ...))
```

Copy the exact `Signal(...)` field population from `app/demo.py:_signals_for_item` (lines 277–314) — the frontend mapper (`lib/nazar/catchup-mapper.ts:signalDetail`) depends on the `deviation_percent`, `magnitude_percent`, and `horizon_minutes` evidence keys.

Also fetch **sector index candles** in live mode: `live_market_catchup` currently requests only stock symbols. Mirror the replay path:

```python
requested = {item.symbol for item in items} | {item.sector_index for item in items}
candles_by_symbol = await provider.candles(sorted(requested), ...)
```

(`GrowwProvider._trading_symbol` already maps `NIFTY50`/`NIFTY_BANK`/`NIFTY_IT` aliases.)

### 4. Honest degradation

When `load_distributions` returns fewer than `MINIMUM_OBSERVATIONS` for a type, keep today's behavior: no signal, `LIMITED_HISTORY` data state, and a narrative saying distributions are not loaded. That is exactly the "limited history instead of fabricating evidence" contract in the README — this fix only removes the case where distributions *do* exist and are still ignored.

## Operational note

Distributions go stale. Schedule `python -m app.jobs.rebuild_distributions --symbol X --sector Y` per tracked symbol (nightly cron / GitHub Actions schedule / Supabase edge function), and consider recording `computed_at` freshness in the card evidence.

## Verification

- Unit: stub `load_distributions` to return ≥120 synthetic observations and assert `live_market_catchup` emits `sector_surprise` when the live relative return sits in the tail, and nothing when it is median.
- Integration: run the rebuild job against a Supabase instance seeded with a year of 1-minute candles, hit live catchup, and confirm percentile/observation counts on the card match a hand computation for one case (golden case as in `docs/functional-spec.md`).

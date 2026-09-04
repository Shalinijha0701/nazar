# Nazar

Nazar is a market catch-up watchlist. It does not predict prices or recommend
trades. It tells a returning user whether a personal condition was crossed,
whether a stock moved unusually relative to its sector, or whether a meaningful
spike or reversal happened while the user was away.

The deployed interface runs a deterministic recorded-demo provider so the
entire judging flow remains available while Indian markets are closed. Values
are illustrative and are labelled as demo data. `GrowwProvider` is isolated
behind the same market-data interface and activates only when valid credentials
are supplied.

## Product contract

Three signal families remain independent:

1. **Personal rule:** a price level or historical same-time volume-pace multiple
   was crossed after `reviewed_through`. Volume pace uses the same-time-of-day
   historical median, not raw volume, so early-session minutes are not penalised.
2. **Sector surprise:** the absolute deviation of stock-minus-sector return is
   ranked against the stock's own comparable historical observations. Stock and
   sector candles are joined by exact timestamp before computing returns, so
   illiquid stocks that skip minute candles cannot corrupt the calculation.
3. **Path event:** minute candles preserve unusual excursions and reversals that
   a current-price-only watchlist would lose. Both positive and negative
   excursions are detected; direction is reported separately.

There is no combined score. A stale observation cannot create a new signal.
Previously confirmed events retain their original timestamp. The complete
formula and golden test cases live in `docs/functional-spec.md`.

## Demo ↔ signals.py connection

`backend/app/demo.py` builds its catch-up response by calling the same pure
functions used in production (`signals.py`). The Infosys candle series
reproduces the Friday replay visible in the UI so judges can trace the
calculation end-to-end:

```
INFY replay candles → path_metrics() → peak_to_trough_reversal
                    → empirical_percentile(reversal, INFY_REVERSAL_HISTORY)
                    → PathEvent signal with actual percentile
```

No signal value in the demo response is hardcoded. Historical distribution
arrays are seeded deterministically; the signal arithmetic is live.

## Repository layout

- `app/` — Next.js-compatible Nazar dashboard deployed through Sites.
- `lib/nazar/` — typed demo data and presentation-domain projection.
- `backend/app/` — FastAPI modular monolith with market-provider adapters and
  pure signal functions.
- `backend/tests/` — 16 focused golden-path tests for the signal mathematics,
  including timestamp-alignment and two-sided surprise detection.
- `supabase/schema.sql` — PostgreSQL tables, ownership policies, indexes, and
  the atomic monotonic watermark function.
- `docs/functional-spec.md` — frozen behaviour before implementation.

## Run the interface

```bash
npm install
npm run dev
```

## Run the API

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Run backend tests (16 cases):

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```

## Live setup

1. Apply `supabase/schema.sql` to a Supabase project.
2. Fill the `NAZAR_SUPABASE_*` values in `backend/.env`.
3. Add a Groww market-data token as `NAZAR_GROWW_ACCESS_TOKEN`.
4. Set `NAZAR_MODE=live` only after the provider health check succeeds.

Secrets are never committed. The API obtains the user from the Authorization
header and does not accept a caller-supplied user ID in watchlist routes
(prevents IDOR).

## Deliberate trade-offs

| Decision | Trade-off | Rationale |
|---|---|---|
| Conservative ceiling horizon | A 61-minute absence uses the 240-minute bucket | Avoids overstating surprise in a shorter window |
| Timestamp join for sector surprise | Drops unmatched minutes | Correctness over coverage; illiquid candle gaps cannot corrupt the return |
| 120-observation minimum | Scoring skipped below | 95th percentile on fewer points is statistically unreliable |
| Overlapping historical windows | Percentile is descriptive, not an independent-sample probability | Disclosed; acceptable for a 72-hour MVP |
| Seeded demo distributions | Not a live database query | Architecture contract is production-ready; seeding is the only MVP limit |
| Five-session statistical horizon max | Longer catch-ups use `partial_coverage` label | Avoids silent degradation for multi-day absences |

## Scaling considerations

- **Shared ingestion:** market candles and sector indices are ingested once per
  symbol, not per user. Per-user storage is limited to watchlist items, personal
  rules and a monotonic reviewed-through watermark.
- **market_candles partitioning:** next step is PostgreSQL range-partitioning
  by month on `interval_start` to maintain query speed as candle volume grows.
- **Trading-minute calculation:** the current demo uses calendar minutes.
  Production must filter using the NSE holiday calendar to exclude weekends,
  public holidays and pre/post-market minutes from `h`. A comment in
  `signals.py` marks this boundary explicitly.
- **Distribution pre-computation:** `stock_distributions` table and a background
  worker (scaffolded in `worker/`) would replace the seeded arrays. The
  `select_horizon` / `sector_surprise` / `path_metrics` contract is unchanged.

## What Nazar does not do

- No price prediction or buy/sell advice.
- No combined weighted score — signals are independent facts.
- No sentiment or social-media signals.
- No Kafka, Redis, or microservices in the MVP.

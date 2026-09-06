# Nazar — Application Documentation

Nazar is an explainable market catch-up watchlist: it tells a user what *mattered* in the market while they were away, with evidence attached to every claim, and deliberately makes no predictions and gives no trading advice. This document describes the whole application as built. Companion documents: [workflow.md](workflow.md) (how a request flows through the system), [decisions.md](decisions.md) (decision log), [bugs.md](bugs.md) (known issues), [functional-spec.md](functional-spec.md) (frozen formulas), and per-gap fix guides in [fixes/](fixes/).

## 1. Product concept

A returning user does not need every price move — they need the few moves that meant something. Nazar surfaces exactly three kinds of signal, each independently computed and each carrying its own evidence (timestamp, comparison horizon, percentile, observation count):

| Signal | Meaning | Example receipt |
| --- | --- | --- |
| **Personal rule** | A price crossed the user's own threshold, or same-time-of-day volume pace exceeded their multiple | "Crossed above your ₹2,800.00 level — first confirmed at 11:45 am IST" |
| **Sector surprise** | The stock's sector-relative return sits in the tail of its own historical distribution | "97.6th percentile relative to sector · 1.98% above sector · 252 observations" |
| **Path event** | A spike, drop, or reversal that the closing price hides | "Spike reversed before the interval ended · Peak ₹1,820 · 3.09% move · 97.6th percentile" |

Two supporting concepts keep the product honest:

- **Review watermark** — the moment the user last acknowledged their catch-up. It advances only on explicit acknowledgement, only forward (monotonic), so acknowledged events never reappear.
- **Data-quality states** — `fresh`, `market_closed`, `limited_history`, `stale/unavailable`. Stocks with degraded data are excluded from attention ranking and say so, instead of fabricating evidence.

Stocks are grouped into **Attention** (has signals), **Normal noise** (moved within expected range), and **Data unavailable**.

## 2. Technology stack

| Layer | Technology | Notes |
| --- | --- | --- |
| Frontend | Next.js 16 (App Router, Turbopack), React 19, TypeScript 5.9 | Single-page dashboard, client-rendered |
| UI | Tailwind CSS 4, shadcn-style components over Radix UI, Recharts, Sonner (toasts), Lucide icons | Vendored shadcn CSS in `vendor/` |
| Backend | FastAPI (Python 3.12), Pydantic v2, pydantic-settings | Modular monolith |
| Market data | `growwapi` SDK (live NSE data) or deterministic in-process replay | Provider interface in `backend/app/providers/` |
| Persistence | In-memory (demo) or Supabase/PostgreSQL | Schema with RLS in `supabase/schema.sql` |
| Auth | Shared demo bearer token, or Supabase Auth JWTs | `backend/app/auth.py` |
| Testing | Python `unittest` (52 tests), Node test runner + tsx (frontend units), Playwright (E2E, ad hoc) | |
| CI/CD | GitHub Actions (lint/test/build both stacks), Vercel (two projects) | `.github/workflows/ci.yml` |

## 3. Repository layout

```text
app/                     Next.js app router: layout, page, dashboard, error/loading routes
components/nazar/        Product components: StockCard, SignalBadge, DataBadge
components/ui/           shadcn-style primitives (button, dialog, sheet, tabs, ...)
lib/nazar/               Frontend domain logic (see §5)
lib/utils.ts             cn() class-merge helper
backend/app/main.py      FastAPI app factory, endpoints, error handlers
backend/app/config.py    Settings (NAZAR_* env vars) and runtime validation
backend/app/auth.py      Demo-token / Supabase JWT authentication
backend/app/repository.py  WatchlistStore protocol + Memory and Supabase implementations
backend/app/demo.py      Recorded replay dataset and replay catch-up engine
backend/app/models.py    Pydantic response models (Candle, Signal, CatchupCard, ...)
backend/app/providers/   MarketDataProvider protocol, ReplayProvider, GrowwProvider
backend/app/services/    signals.py (pure formulas), live.py, events.py,
                         trading_time.py, distributions.py
backend/app/jobs/        rebuild_distributions.py (historical distribution builder)
backend/tests/           test_signals, test_api, test_live, test_repository
supabase/schema.sql      Tables, indexes, RLS policies, acknowledge RPC
docs/                    This documentation, functional spec, fix guides
tests/                   Frontend unit tests (mapper, projection)
vercel.json              Dashboard project config + /api/* rewrite to the API
backend/vercel.json      API project config (@vercel/python)
```

## 4. Backend

### 4.1 API surface

All `/api/*` endpoints require `Authorization: Bearer <token>`. Errors use `{"detail": string}`.

| Method & path | Purpose | Notable responses |
| --- | --- | --- |
| `GET /health` | Liveness | `{"status": "ok"}` |
| `GET /api/watchlists/me/catchup?watchlist_id=` | The core endpoint: full catch-up feed since the watermark | 200 `CatchupResponse`; 404 unknown watchlist; 502 provider outage (live mode) |
| `POST /api/watchlists` | Create a watchlist (`{name}`) | 200 `{watchlist_id, name}`; 429 per-user limit (20) |
| `POST /api/watchlists/{id}/items` | Track a stock (`{symbol, company_name, sector_index}`) | 200 `{item_id}`; idempotent per symbol |
| `DELETE /api/watchlists/items/{item_id}` | Untrack a stock (cascades its rules) | 200 / 404 |
| `POST /api/watchlists/items/{item_id}/rules` | Add a personal rule (`{rule_type, threshold}`) | 200 `{rule_id}`; 422 invalid type/threshold |
| `POST /api/watchlists/me/acknowledge` | Advance the review watermark (`{watchlist_id, evaluated_through}`) | 200 `{reviewed_through}` (monotonic); 422 future or naive timestamp |

`CatchupResponse` (see `backend/app/models.py`): `watchlist_id`, `source` (`replay`/`groww`), `reviewed_through`, `evaluated_through`, `trading_minutes`, `horizon_minutes`, `coverage`, `counts`, and three card arrays (`attention`, `normal`, `data_unavailable`). Each `CatchupCard` carries prices, change-%, `data_state`, a narrative sentence, the chart series, and its `signals` with structured `evidence`.

### 4.2 Signal engine (`services/signals.py`)

Pure, deterministic functions shared by replay and live modes (formulas frozen in `functional-spec.md`):

- `select_horizon(trading_minutes)` — maps the review interval to one of the supported horizons (15, 60, 240, 375, 750, 1875 trading minutes) with a `coverage` label.
- `first_crossed_above/below(candles, baseline, threshold)` — price-rule crossings, using candle highs/lows, requiring the baseline to start on the other side.
- `volume_pace` / `first_volume_pace_crossing` — cumulative session volume vs. the median of ≥20 same-minute historical sessions.
- `sector_surprise(...)` — stock-vs-sector relative return placed on the empirical distribution of historical relative returns (≥120 observations required); percentile of the absolute deviation from the historical median.
- `path_metrics` / `most_unusual_path` — upward/downward excursions and peak-to-trough / trough-to-peak reversals within the interval, scored against per-type historical distributions; only the single most unusual event ≥ the 95th percentile is reported.

### 4.3 Modes

- **Replay (default)** — `demo.py` holds a recorded 2¾-hour NSE session (12 instruments + 2 sector indices) plus hand-built histories; the same signal functions run over it. Deterministic, works outside market hours, needs no credentials.
- **Live (Groww)** — `services/live.py` fetches 1-minute candles via `GrowwProvider`, evaluates price rules, tracks staleness (candle older than 3 minutes during market hours → unavailable), and honestly reports that statistical distributions are not loaded and that volume-pace rules were not evaluated. Sector/path signals in live mode await the distribution pipeline (fix guide 05).

### 4.4 Persistence and auth

`WatchlistStore` protocol with two implementations. **Memory**: all state keyed by `(user_id, watchlist_id)` under a lock, default watchlist seeded with 10 stocks and 2 rules, per-user watchlist cap of 20 — demo-grade, resets on process restart (must not run on serverless; a startup warning fires if it does). **Supabase**: tables from `schema.sql`, ownership checks per query, RLS as defense in depth, monotonic acknowledgement via the `acknowledge_watchlist` RPC (`GREATEST(existing, new)`). Auth is either the shared demo token (constant-time compared; maps to `demo-user`) or Supabase JWT verification. Config invariants (`config.py`): Supabase persistence and auth must be enabled together; the Groww provider requires its token.

## 5. Frontend

Single client component tree under `app/nazar-dashboard.tsx`:

- **`lib/nazar/use-catchup.ts`** — `useCatchup()` fetches the catch-up feed with the demo bearer token (abortable, `refresh()` bumps a version counter); `nazarApi()` is the shared mutation helper.
- **`lib/nazar/catchup-mapper.ts`** — maps the API payload to display records: formats IST times, builds per-signal detail strings from structured evidence, computes each signal's `triggerIndex` (the chart position where it becomes visible during replay).
- **`lib/nazar/signal-engine.ts`** — `projectStock(stock, replayIndex)`: pure projection of a stock to a replay position (price at that index, signals visible only once their trigger index is reached, group recomputed). This is what makes the replay slider work — the UI scrubs through time and signals appear when they occurred.
- **Dashboard state** — search query, tab filter, replay position/playing, selected stock (evidence sheet), dialogs (add stock, add rule), and `acknowledgedThrough` (derived "reviewed" state: the button disables when the current response's `evaluated_through` has been acknowledged).
- **Key screens** — hero with counts + replay controls (play/pause/reset/slider); grouped card sections (Attention / collapsible Normal noise / Unavailable); evidence sheet per stock (Recharts line chart with baseline reference, narrative, signal receipts, percentile progress bar, remove button); add-stock and add-rule dialogs; error banner with retry; `error.tsx` boundary and `loading.tsx` skeleton.

All numbers on screen come from the backend response — the frontend computes no market evidence, only projects it onto the replay timeline.

## 6. Configuration

Backend (`NAZAR_` prefix, `.env` supported — see `backend/.env.example`): `MARKET_PROVIDER` (replay/groww), `PERSISTENCE_BACKEND` (memory/supabase), `AUTH_MODE` (demo/supabase), `DEMO_TOKEN`, `ALLOWED_ORIGINS` (comma-separated CORS origins; default localhost only), `GROWW_ACCESS_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (API-side only, never exposed to the frontend).

Frontend (`.env.local` — see `.env.example`): `NEXT_PUBLIC_API_BASE` (empty in production to use the Vercel rewrite; `http://localhost:8000` locally), `NEXT_PUBLIC_DEMO_TOKEN`.

## 7. Running, testing, deploying

**Local:** `cd backend && uvicorn app.main:app --reload --port 8000` (after `pip install -r requirements.txt`), then `npm install && npm run dev`; open `http://localhost:3000`.

**Tests:** `python -m unittest discover -s tests -v` in `backend/` (52 tests: formulas, API, live mode, repository); `npm run lint && npm test && npm run build` at the root. CI runs all of it on push/PR.

**Deployment:** two Vercel projects from one repo — the dashboard (root, Next.js; `vercel.json` rewrites `/api/*` server-side to the API project so the browser stays same-origin) and the API (`backend/` root directory, `@vercel/python`, entry `backend/api/index.py`). Memory persistence is unsuitable on serverless (state is per-instance); production should use Supabase persistence + auth. See fix guides 01 and 10 for the deployment hardening path, and bugs.md BUG-8 for the deployment-protection issue on the current demo URL.

## 8. Deliberate scope limits

No predictions, recommendations, sentiment, or combined scores; replay mode is the complete, presentation-ready experience; live mode currently covers price rules with honest degradation of everything else; corporate actions are represented in the schema (splits/bonuses) with statistical scoring paused around other action types; the app is an engineering prototype, not investment advice.

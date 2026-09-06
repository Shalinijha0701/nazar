# Application Workflow — How the Technology Fits Together

End-to-end description of how data and control flow through Nazar, from a browser opening the dashboard to a signal appearing with its evidence. Companion to [application.md](application.md) (what each part is); this document is about *how the parts move*.

## 1. System topology

```mermaid
flowchart LR
  B[Browser<br/>Next.js dashboard] -->|"Bearer demo-token<br/>fetch /api/*"| P{Path}
  P -->|"production: same-origin<br/>Vercel rewrite"| API
  P -->|"local dev: NEXT_PUBLIC_API_BASE<br/>cross-origin + CORS"| API[FastAPI<br/>modular monolith]
  API --> AUTH[auth.py<br/>demo token / Supabase JWT]
  API --> REPO[(WatchlistStore<br/>memory or Supabase)]
  API --> ENGINE[signal engine<br/>services/signals.py]
  ENGINE --> PROV{Market provider}
  PROV -->|replay| REPLAY[ReplayProvider<br/>recorded candles in demo.py]
  PROV -->|groww| GROWW[GrowwProvider<br/>NSE 1-minute candles]
  REPO -.->|supabase mode| PG[(PostgreSQL<br/>RLS + acknowledge RPC)]
```

Two request paths reach the API: in production the dashboard calls its **own origin** and Vercel's rewrite (`vercel.json`) proxies `/api/*` server-side to the API project (no CORS involved); in local dev the browser calls `http://localhost:8000` directly and the API's CORS middleware allows the localhost origin.

## 2. The core loop: catch-up request

What happens on every dashboard load and refresh (`GET /api/watchlists/me/catchup`):

```mermaid
sequenceDiagram
  participant UI as Dashboard (useCatchup)
  participant API as FastAPI main.py
  participant R as Repository
  participant E as Catch-up engine
  participant M as Market provider

  UI->>API: GET /api/watchlists/me/catchup (Bearer token)
  API->>API: authenticated_user() → user_id
  API->>R: get_or_create_watchlist(user_id)
  Note over R: first call seeds the demo watchlist<br/>(10 stocks, 2 rules)
  API->>R: list_items, list_rules, get_watermark
  Note over API: reviewed = stored watermark, else default<br/>(replay: DEMO_START · live: ~5 trading sessions back)
  API->>E: recorded_demo_catchup / live_market_catchup
  E->>E: trading_minutes_between(reviewed, evaluated)<br/>select_horizon → 15…1875 min + coverage
  E->>M: candles(symbols + sector indices, interval)
  loop each watchlist item
    E->>E: data-quality state (fresh / closed / stale / limited)
    E->>E: price-rule crossings · volume pace ·<br/>sector surprise · path events
    E->>E: card → attention (has signals) / normal / unavailable
  end
  E-->>API: CatchupResponse (counts, cards, signals+evidence)
  API-->>UI: 200 JSON
  UI->>UI: mapCatchupResponse → display records<br/>(IST times, detail strings, trigger indices)
```

Key properties: shared market evidence is computed **per symbol**, per-user state is only membership + rules + watermark; every signal carries `occurred_at`, percentile, observation count, and evidence keys the UI renders verbatim; degraded data lands in `data_unavailable` instead of being ranked.

## 3. Signal computation pipeline

For each stock in the interval `(reviewed, evaluated]`:

1. **Baseline** — last candle at or before `reviewed`; all change-% and crossings measure from it.
2. **Personal rules** — `first_crossed_above/below` scan candle highs/lows for the first threshold crossing (a rule already satisfied at baseline can never fire); volume rules compare cumulative session volume to the median of ≥20 same-minute historical sessions and report the first crossing of the user's multiple.
3. **Sector surprise** — stock and sector candles are aligned by timestamp; `relative return = stock return − sector return` over the selected horizon; placed on the empirical distribution of ≥120 historical relative returns; reported only at ≥95th percentile of absolute deviation from the historical median.
4. **Path events** — running peak/trough scan produces upward/downward excursions and both reversal magnitudes with the timestamp where each extreme completed; each is scored against its own historical distribution; only the single most unusual event ≥95th percentile is reported. A path event **confirmed from fresh data before a feed outage** is preserved and still shown on an unavailable card (`services/events.py`).
5. **Grouping** — any signal ⇒ Attention; none ⇒ Normal; degraded data ⇒ Unavailable (with any preserved confirmed events).

Replay and live modes run the *same* functions; they differ only in where candles and histories come from (recorded dataset vs. Groww + Supabase distributions — the latter pipeline is built but not yet wired, see fixes/05).

## 4. Replay projection (frontend time travel)

The replay slider never refetches. The mapper stamps each signal with a `triggerIndex` — the chart position where its `occurred_at` falls. `projectStock(stock, replayIndex)` then projects every card to a moment in time: price at that index, only signals with `triggerIndex ≤ replayIndex` visible, and the Attention/Normal grouping recomputed from the visible set. Play mode advances the index every 700 ms and stops at the end. This is why scrubbing the slider makes signals appear exactly when they happened — the UI replays the backend's evidence rather than recomputing it.

## 5. Acknowledge (review watermark) flow

```mermaid
sequenceDiagram
  participant UI as Dashboard
  participant API as FastAPI
  participant R as Repository

  UI->>API: POST /acknowledge {watchlist_id, evaluated_through}
  API->>API: reject naive or future timestamps (422)
  API->>R: acknowledge(user, watchlist, evaluated_through)
  Note over R: watermark = max(current, requested)<br/>memory: under lock · supabase: RPC GREATEST(...)
  R-->>API: final reviewed_through
  API-->>UI: 200 {reviewed_through}
  UI->>UI: remember acknowledgedThrough → button disables
  UI->>API: refresh → GET catchup
  Note over API: trading_minutes now 0 →<br/>attention empty, acknowledged events never repeat
```

Monotonicity is enforced at the storage layer (`max`/`GREATEST`), so replayed or out-of-order acknowledgements can never move the watermark backward — the same guarantee across devices in Supabase mode.

## 6. Mutation flows

Add stock, add rule, and remove stock share one shape: dialog/button → `nazarApi()` POST/DELETE with the bearer token → repository ownership check (`PermissionError` → 404) → success toast → `refresh()` refetches the catch-up so the backend re-groups everything (e.g. a new price rule that already crossed moves its stock into Attention on the next response). Failures surface the backend `detail` in an error toast; the error banner with Retry covers total API outage.

## 7. Live-mode specifics

- **Default window:** first-time users get a watermark ~5 trading sessions back (`default_live_watermark`, trading-minute aware, 14-day cap) instead of a fixed 4 hours.
- **Staleness:** during market hours, a latest candle older than 3 minutes moves the stock to Unavailable with an explicit narrative.
- **Honest degradation:** cards state that statistical distributions are not loaded, and name any volume-pace rule that could not be evaluated.
- **Failure mapping:** any provider-layer failure becomes a 502 with a retry-shortly message (never a raw 500), logged server-side.
- **Data pipeline (built, awaiting wiring):** 1-minute candles → `market_candles` → `jobs/rebuild_distributions.py` computes per-horizon sector-relative and path distributions → `stock_distributions`. Once live mode reads that table (fixes/05), sector-surprise and path signals switch on outside replay.

## 8. Development and delivery workflow

```mermaid
flowchart LR
  DEV[Local dev<br/>uvicorn :8000 + next dev :3000] --> TESTS[backend: 52 unittest<br/>frontend: node --test + lint + build]
  TESTS --> PUSH[git push main]
  PUSH --> CI[GitHub Actions<br/>frontend job + backend job]
  PUSH --> V1[Vercel: dashboard project<br/>root, Next.js, /api rewrite]
  PUSH --> V2[Vercel: API project<br/>backend/, @vercel/python]
  V2 --> ENV[NAZAR_* env vars<br/>origins, provider, persistence]
```

Local setup, env variables, and test commands are in [application.md §6–7](application.md). Deployment hardening (Supabase persistence for serverless, removing deployment protection from the demo URL, env-driven rewrite) is tracked in the fix guides and [bugs.md](bugs.md).

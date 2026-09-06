# Fix G9 + G11 — API hygiene: GET side effects, health disclosure, rate limiting

**Severity:** Medium · **Status:** Partially fixed (health trimmed, watchlist cap added; GET side-effect removal and middleware rate limiting are guide only)

## Problems

1. **GET with a side effect (G9).** `GET /api/watchlists/me/catchup` calls `store.get_or_create_watchlist(...)` — a read endpoint that creates a watchlist (and, in memory mode, seeds ten default items and two rules). This violates HTTP semantics: a cache, prefetcher, or monitoring probe hitting the URL mutates state.
2. **Config disclosure (G9).** `/health` returned `market_provider`, `persistence`, and `auth` mode to unauthenticated callers — useful reconnaissance (e.g. learning the API runs demo auth).
3. **No abuse protection (G11).** `POST /api/watchlists` was unbounded: anyone with the (public, see G2) demo token could create unlimited watchlists, each seeding default state — a trivial memory-exhaustion vector in memory mode.

## Implemented

### Health trimmed

```python
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

Operators who need the mode information get it from deployment env vars or logs, not from an unauthenticated endpoint.

### Per-user watchlist cap

`MemoryWatchlistRepository.create_watchlist` now enforces `MAX_WATCHLISTS_PER_USER = 20` and raises `ValueError`; the endpoint maps it to **429**:

```python
try:
    watchlist_id = repository(runtime).create_watchlist(user_id, payload.name.strip())
except ValueError as exc:
    raise HTTPException(status_code=429, detail="Watchlist limit reached") from exc
```

(Supabase mode is not memory-bound; add the same guard there if desired by counting `watchlists` rows for the owner before insert.)

## Guide — remove the GET side effect

The demo flow depends on lazy seeding (first page load must show the ten-stock watchlist), so this is a product-affecting change. Two clean options:

**Option A — bootstrap on first mutation only.** `catchup` uses a read-only resolver; if the user has no watchlist, it returns an empty response with a `watchlist_id: null` and the frontend shows an explicit "Create watchlist" call to action that POSTs `/api/watchlists`. Purest semantics; requires a small UI state.

**Option B — explicit bootstrap endpoint.** Add `POST /api/watchlists/bootstrap` that runs today's `get_or_create_watchlist` seeding, and have the frontend call it once (on first load when catchup 404s). `GET catchup` then raises 404 for missing watchlists like the other endpoints:

```python
resolved_id = store.resolve_watchlist(user_id, watchlist_id)  # read-only; PermissionError -> 404
```

Option B preserves the demo experience with one extra request and no UX change.

## Guide — middleware rate limiting

The watchlist cap bounds one resource; a general limiter bounds request volume. [slowapi](https://github.com/laurentS/slowapi) fits FastAPI:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
```

with a tighter decorator on mutations (`@limiter.limit("10/minute")` on `create_watchlist`, `acknowledge`). Add `slowapi==0.1.9` to `backend/requirements.txt`. Note Vercel serverless keeps limiter state per instance — for a hard guarantee use Vercel's WAF rules or a shared store (Redis) as the slowapi backend.

### Security headers

For the API (JSON-only), the valuable ones are:

```python
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response
```

The Next.js dashboard should set its own CSP/frame headers via `headers()` in `next.config.ts`.

## Verification

- `test_api.py::test_health_reports_only_status` (added) asserts the trimmed payload.
- `test_repository.py` (added) asserts the 21st `create_watchlist` raises; an API-level test asserts 429.
- After the GET fix: a `GET catchup` for a brand-new user creates no rows/keys (assert repository state unchanged), and the bootstrap path recreates today's behavior.

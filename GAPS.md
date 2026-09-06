# Nazar — Gap Analysis

A deep review of the repository (backend FastAPI app, Next.js dashboard, Supabase schema, CI, and deployment configuration) surfaced the gaps below. Each gap links to a fix guide in [`docs/fixes/`](docs/fixes/). Gaps marked **Fixed** have been implemented in this repository; gaps marked **Guide only** require external infrastructure (Supabase project, Groww credentials, Vercel environment changes) or a product decision, and their guides contain ready-to-apply code.

## Severity summary

| Severity | Count | IDs |
| --- | --- | --- |
| Critical | 3 | G1, G2, G3 |
| High | 5 | G4, G5, G6, G7, G8 |
| Medium | 7 | G9, G10, G11, G12, G13, G14, G15 |
| Low | 1 | G16 |

## Gap register

### Critical

| ID | Gap | Where | Status | Fix guide |
| --- | --- | --- | --- | --- |
| G1 | In-memory persistence on Vercel serverless loses state between lambda instances and cold starts. "Mark reviewed" watermarks, added stocks, and rules silently vanish or flip between requests, so the README demo step "refresh and verify acknowledged events do not repeat" is unreliable on the deployed demo. | `backend/app/main.py` (`memory_repository` behind `@lru_cache`), Vercel deployment | Partially fixed — startup warning added when memory persistence runs on Vercel; full fix (Supabase persistence) is guide only | [01-serverless-persistence.md](docs/fixes/01-serverless-persistence.md) |
| G2 | Write-capable bearer token ships in the public JS bundle (`NEXT_PUBLIC_DEMO_TOKEN`), and every visitor authenticates as the same `demo-user`. Any visitor of the public URL can mutate the shared watchlist (add/remove items, add rules, advance the review watermark) for everyone. | `lib/nazar/use-catchup.ts:9`, `backend/app/auth.py` | Guide only (product decision: demo isolation model) | [02-demo-token-isolation.md](docs/fixes/02-demo-token-isolation.md) |
| G3 | Memory repository keys `_items`/`_rules` by `watchlist_id` alone while `_watchlists` is keyed by `(user_id, watchlist_id)`. Two users with watchlist id `primary` would share and overwrite each other's items. Latent today (demo mode has a single user) but a landmine for any multi-user auth mode. | `backend/app/repository.py` | **Fixed** | [03-memory-repo-user-keying.md](docs/fixes/03-memory-repo-user-keying.md) |

### High

| ID | Gap | Where | Status | Fix guide |
| --- | --- | --- | --- | --- |
| G4 | Volume-pace rules are silently ignored in live (Groww) mode. The UI offers the rule type, the API accepts and stores it, but the live signal path skips it with no feedback to the user. | `backend/app/services/live.py`, `app/nazar-dashboard.tsx` (rule dialog) | Partially fixed — live cards now state when volume-pace rules could not be evaluated; full evaluation is guide only (needs historical volume data) | [04-volume-pace-live.md](docs/fixes/04-volume-pace-live.md) |
| G5 | Dead distribution pipeline: `rebuild_distributions.py` writes `stock_distributions` to Supabase, but no code path ever reads that table. Live mode never produces sector-surprise or path-event signals even after distributions are built. | `backend/app/jobs/rebuild_distributions.py`, `backend/app/services/live.py` | Guide only (needs a populated Supabase instance) | [05-distribution-pipeline.md](docs/fixes/05-distribution-pipeline.md) |
| G6 | Missing CRUD surface: no endpoints to list watchlists, list/delete rules, or delete/rename watchlists; rules accumulate forever with no way to remove them (API or UI). The frontend "Add stock" dialog is limited to 3 hardcoded symbols. | `backend/app/main.py`, `lib/nazar/stock-catalog.ts` | Guide only (API + UI feature work) | [06-crud-endpoints.md](docs/fixes/06-crud-endpoints.md) |
| G7 | Live catch-up window was capped at 4 hours: the default watermark was `evaluated - timedelta(hours=4)`, contradicting the "returned after being away" product premise (a week away produced a 4-hour catch-up). | `backend/app/main.py` | **Fixed** — default lookback now spans the largest supported horizon (1875 trading minutes ≈ 5 sessions) | [07-live-watermark-window.md](docs/fixes/07-live-watermark-window.md) |
| G8 | No global error handling or observability: unhandled Supabase/network errors surfaced as raw 500s with stack traces, there was no request logging, and only the Groww provider had a logger. | `backend/app/main.py` | **Fixed** — global exception handler with safe JSON body, provider failures map to 502, logging configured in `create_app()` | [08-error-handling-observability.md](docs/fixes/08-error-handling-observability.md) |

### Medium

| ID | Gap | Where | Status | Fix guide |
| --- | --- | --- | --- | --- |
| G9 | `GET /api/watchlists/me/catchup` has a side effect: it creates a watchlist via `get_or_create_watchlist`. `/health` also disclosed provider/persistence/auth configuration. | `backend/app/main.py` | Partially fixed — `/health` trimmed to `{"status": "ok"}`; GET side-effect removal is guide only (the demo flow depends on lazy creation) | [09-api-hygiene.md](docs/fixes/09-api-hygiene.md) |
| G10 | Hardcoded deployment URLs committed to the repo: a specific Vercel preview URL in the CORS default, and a personal backend URL in the frontend rewrite. | `backend/app/config.py`, `vercel.json` | Partially fixed — hardcoded origin removed from `config.py` default; `vercel.json` rewrite is guide only (Vercel project setting) | [10-config-hardcoding.md](docs/fixes/10-config-hardcoding.md) |
| G11 | No rate limiting or abuse protection: unbounded `POST /api/watchlists` fills server memory; no security headers. | `backend/app/main.py`, `backend/app/repository.py` | Partially fixed — per-user watchlist cap in the memory repository; middleware-based rate limiting is guide only | [09-api-hygiene.md](docs/fixes/09-api-hygiene.md) |
| G12 | Frontend/backend type contract is duplicated by hand (TS types mirror pydantic models with no OpenAPI codegen — drift risk). `saveRule` fell back to `ruleStock.symbol` as an item id, which always 404s. | `lib/nazar/catchup-mapper.ts`, `app/nazar-dashboard.tsx` | Partially fixed — `saveRule` fallback bug fixed and rule dialog gated on `itemId`; OpenAPI codegen is guide only | [11-type-contract.md](docs/fixes/11-type-contract.md) |
| G13 | Test coverage holes: `live.py`, `GrowwProvider`, `SupabaseWatchlistRepository`, and `trading_time.py` edge cases untested; no frontend component tests; CI has no backend lint/type-check or coverage reporting. | `backend/tests/`, `.github/workflows/ci.yml` | Partially fixed — regression tests added for the repository keying fix and threshold bound; broader suite and CI additions are guide only | [12-testing-ci.md](docs/fixes/12-testing-ci.md) |
| G14 | Frontend robustness: hardcoded "Last reviewed · 11:15" label and "11:15" replay-time fallback; no Next.js `error.tsx`/`loading.tsx`; the "Mark reviewed" button never re-enables after new data arrives; no auto-refresh in live mode. | `app/nazar-dashboard.tsx` | Partially fixed — reviewed label and replay time derived from the API response, `app/error.tsx` and `app/loading.tsx` added, reviewed state resets on new data; live polling is guide only | [13-frontend-robustness.md](docs/fixes/13-frontend-robustness.md) |
| G15 | Thread-safety gap: `MemoryWatchlistRepository._owned_item` iterated `_items` without holding the lock while writers mutate under it. | `backend/app/repository.py` | **Fixed** (with G3) | [03-memory-repo-user-keying.md](docs/fixes/03-memory-repo-user-keying.md) |

### Low

| ID | Gap | Where | Status | Fix guide |
| --- | --- | --- | --- | --- |
| G16 | Repo hygiene: `.vscode/` untracked and not gitignored; no LICENSE file; demo token compared with `!=` instead of a constant-time comparison; rule threshold had no upper bound (accepted `1e308`). | `.gitignore`, `backend/app/auth.py`, `backend/app/main.py` | **Fixed** | [14-repo-hygiene.md](docs/fixes/14-repo-hygiene.md) |

## Reading order

If you address the guide-only items, the highest-leverage order is:

1. **G1 + G2 together** — move the deployed demo to Supabase persistence with isolated demo identities; this makes the public demo correct and safe.
2. **G5** — wire stored distributions into live mode; this turns the product's headline signals on outside replay.
3. **G6** — CRUD endpoints and rule management; removes the "rules accumulate forever" trap.
4. **G12 / G13** — OpenAPI codegen and CI hardening keep the rest from regressing.

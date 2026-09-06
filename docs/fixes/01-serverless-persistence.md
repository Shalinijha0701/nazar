# Fix G1 — In-memory persistence is broken on Vercel serverless

**Severity:** Critical · **Status:** Partially fixed (startup warning implemented; Supabase migration is the full fix)

## Problem

`backend/app/main.py` serves the deployed demo with `MemoryWatchlistRepository` cached via `@lru_cache`:

```python
@lru_cache
def memory_repository() -> MemoryWatchlistRepository:
    return MemoryWatchlistRepository()
```

On Vercel, each serverless invocation may land on a different lambda instance, and instances are recycled on cold starts. Every instance builds its own private `MemoryWatchlistRepository`, so:

- The review watermark set by `POST /api/watchlists/me/acknowledge` exists only on the instance that handled the request. The next `GET /api/watchlists/me/catchup` may hit a fresh instance where the watermark is back at `DEMO_START`.
- Stocks and rules added through the UI disappear at random.
- The README demo flow — *"Click Mark reviewed, refresh, and verify that acknowledged events do not repeat"* — fails nondeterministically on the live deployment.

## Implemented mitigation

`create_app()` now logs a prominent warning when memory persistence runs in a Vercel environment (Vercel sets `VERCEL=1`):

```python
if runtime.persistence_backend == "memory" and os.environ.get("VERCEL"):
    logger.warning(
        "Memory persistence is running on Vercel serverless: state is per-instance "
        "and will not survive cold starts. Configure NAZAR_PERSISTENCE_BACKEND=supabase "
        "for the deployed demo."
    )
```

This makes the failure mode visible in deployment logs instead of silent.

## Full fix — run the deployed API on Supabase persistence

The Supabase repository and schema already exist (`backend/app/repository.py` → `SupabaseWatchlistRepository`, `supabase/schema.sql`). The remaining work is deployment configuration:

1. Create a Supabase project and apply the schema:

   ```bash
   psql "$SUPABASE_DB_URL" -f supabase/schema.sql
   ```

2. In the Vercel **API project** environment, set:

   ```text
   NAZAR_PERSISTENCE_BACKEND=supabase
   NAZAR_AUTH_MODE=supabase
   NAZAR_SUPABASE_URL=https://<project>.supabase.co
   NAZAR_SUPABASE_SERVICE_ROLE_KEY=<service role key — API project only, never the dashboard project>
   ```

   `Settings.validate_runtime()` (`backend/app/config.py`) already enforces that Supabase persistence and auth move together and that both credentials are present.

3. The demo bearer token no longer authenticates once `auth_mode=supabase`; pair this change with the demo-identity model in [02-demo-token-isolation.md](02-demo-token-isolation.md) so the public demo still works.

### If you must keep memory mode for a hosted replay demo

Pin the API to a single always-on instance instead of serverless — e.g. run `uvicorn app.main:app` on Fly.io/Railway/Render (one machine), where a single process holds the state for its lifetime. Document that a restart resets the demo, which is acceptable for replay mode.

## Verification

- Deploy with the Supabase variables set; `GET /health` returns 200 (startup validation passed).
- Add a stock, mark reviewed, then force new lambdas (redeploy or wait out the idle timeout) and refresh: the watermark and items persist.
- With memory mode on Vercel, confirm the warning appears in the deployment function logs.

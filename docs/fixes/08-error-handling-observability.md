# Fix G8 — No global error handling or observability

**Severity:** High · **Status:** Fixed (baseline); structured logging/tracing options documented below

## Problem

- No exception handler: any unhandled error (Supabase network failure, Groww SDK error outside the one guarded call, a `datetime.fromisoformat` on malformed data in `SupabaseWatchlistRepository`) surfaced as FastAPI's default 500 — in debug setups with a stack trace.
- No logging in the application layer: `backend/app/providers/groww.py` had the only logger in the codebase. A failing deployment produced empty logs.
- Provider outages were indistinguishable from application bugs in the response (both 500).

## Fix (implemented)

`backend/app/main.py` now configures logging and installs two handlers in `create_app()`:

```python
logger = logging.getLogger("nazar")

class ProviderUnavailableError(RuntimeError):
    """Raised when the upstream market-data provider cannot serve the request."""

def create_app(settings: Settings | None = None) -> FastAPI:
    ...
    logging.basicConfig(level=logging.INFO)

    @app.exception_handler(ProviderUnavailableError)
    async def provider_unavailable(request: Request, exc: ProviderUnavailableError) -> JSONResponse:
        logger.warning("Provider unavailable for %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=502,
            content={"detail": "The market-data provider is unavailable. Try again shortly."},
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error for %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred."},
        )
```

The live catchup endpoint wraps its provider call so upstream failures map to 502 instead of 500:

```python
try:
    return await live_market_catchup(...)
except Exception as exc:  # provider/network layer
    raise ProviderUnavailableError(str(exc)) from exc
```

The frontend already renders backend `detail` strings in its error banner and toasts (`lib/nazar/use-catchup.ts`), so the safe messages flow straight to the UI.

Notes:

- Response bodies never include exception text; details go to logs only.
- CORS caveat: the `ProviderUnavailableError` handler runs inside Starlette's `ExceptionMiddleware` (inside CORS), so 502 responses carry CORS headers. The bare `Exception` handler runs in the outermost `ServerErrorMiddleware`, **outside** CORS — browsers will report a CORS error instead of the 500 body. That is acceptable (the frontend shows its generic failure banner either way); if you want CORS on 500s too, catch exceptions in a custom `@app.middleware("http")` instead of the `Exception` handler.
- `TestClient` in tests raises server exceptions by default; the added tests use `TestClient(app, raise_server_exceptions=False)` to assert the JSON body.

## Going further (guide)

1. **Request logging middleware** — one line per request with latency:

   ```python
   @app.middleware("http")
   async def access_log(request: Request, call_next):
       started = time.perf_counter()
       response = await call_next(request)
       logger.info(
           "%s %s -> %d in %.0fms",
           request.method, request.url.path, response.status_code,
           (time.perf_counter() - started) * 1000,
       )
       return response
   ```

   Skip `/health` to keep uptime checks out of the logs.

2. **Structured logs** — swap `basicConfig` for JSON logs so Vercel/Datadog can index fields: `logging.config.dictConfig` with a JSON formatter, or `structlog`. Keep the logger name `nazar` so app logs are filterable from framework noise.

3. **Error tracking** — Sentry's FastAPI integration is two lines (`sentry_sdk.init(dsn=..., integrations=[FastApiIntegration()])`) and captures the same exceptions the global handler logs. Gate it on an env var so local dev stays clean.

4. **Narrow the Supabase failure surface** — `SupabaseWatchlistRepository` methods currently let `httpx`/postgrest exceptions bubble to the global handler. If you want 503 + "persistence unavailable" instead of generic 500, wrap `supabase_client()` calls in a small `try/except` decorator that raises a `PersistenceUnavailableError`, and register a handler for it exactly like `ProviderUnavailableError`.

## Verification

`backend/tests/test_api.py` (added cases):

- A stub provider that raises makes `GET /api/watchlists/me/catchup` in groww mode return **502** with the safe detail string.
- A forced repository exception returns **500** with `{"detail": "An internal error occurred."}` and no traceback content in the body.

Run: `cd backend && python -m unittest discover -s tests -v`.

# Fix G2 — Public write-capable demo token with shared identity

**Severity:** Critical · **Status:** Guide only (product decision required)

## Problem

Two compounding issues:

1. **The token is public.** `lib/nazar/use-catchup.ts` embeds it in the client bundle:

   ```ts
   const demoToken = process.env.NEXT_PUBLIC_DEMO_TOKEN ?? "demo-token";
   ```

   Anything prefixed `NEXT_PUBLIC_` ships to every browser. Anyone can read it from the page source and call the API directly.

2. **Everyone is the same user.** `backend/app/auth.py` maps every valid demo token to one identity:

   ```python
   if settings.auth_mode == "demo":
       if token != settings.demo_token:
           raise HTTPException(status_code=401, detail="Invalid demo token")
       return "demo-user"
   ```

Combined: any visitor of the public URL can add/remove stocks, add rules, and advance the review watermark **for every other visitor**. A single `POST /api/watchlists/me/acknowledge` with `evaluated_through = DEMO_END` permanently clears the demo's attention signals for everyone (memory instance permitting, see G1).

Note the constant-time comparison part of this gap is already fixed (`secrets.compare_digest`, see [14-repo-hygiene.md](14-repo-hygiene.md)).

## Recommended fix — per-visitor demo identity

Keep the shared demo token (it only gates access to replay data, which is not sensitive), but stop sharing *state* between visitors by deriving a per-visitor user id. The repository layer is already keyed by `user_id` everywhere, so this is a small auth change.

### Backend: accept a client-generated session id

`backend/app/auth.py`:

```python
import re

DEMO_SESSION_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

def authenticated_user(
    authorization: str | None,
    settings: Settings,
    demo_session: str | None = None,
) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization.removeprefix("Bearer ").strip()
    if settings.auth_mode == "demo":
        if not secrets.compare_digest(token, settings.demo_token):
            raise HTTPException(status_code=401, detail="Invalid demo token")
        if demo_session and DEMO_SESSION_PATTERN.fullmatch(demo_session):
            return f"demo:{demo_session}"
        return "demo-user"
    ...
```

Each endpoint in `backend/app/main.py` passes the header through:

```python
@app.get("/api/watchlists/me/catchup")
async def catchup(
    watchlist_id: str | None = None,
    authorization: str | None = Header(default=None),
    x_demo_session: str | None = Header(default=None),
) -> dict:
    user_id = authenticated_user(authorization, runtime, x_demo_session)
    ...
```

Add `X-Demo-Session` to the CORS allow-list in `create_app()`:

```python
allow_headers=["Authorization", "Content-Type", "X-Demo-Session"],
```

### Frontend: generate and persist the session id

`lib/nazar/use-catchup.ts`:

```ts
function demoSession(): string {
  if (typeof window === "undefined") return "server";
  try {
    const existing = window.localStorage.getItem("nazar-demo-session");
    if (existing) return existing;
    const created = crypto.randomUUID().replaceAll("-", "");
    window.localStorage.setItem("nazar-demo-session", created);
    return created;
  } catch {
    return "ephemeral";
  }
}
```

and send it with every request:

```ts
headers: {
  Authorization: "Bearer " + demoToken,
  "X-Demo-Session": demoSession(),
  ...
}
```

Result: each browser gets an isolated watchlist, rules, and watermark. No visitor can disturb another's demo. Because ids are namespaced `demo:<session>`, they can never collide with Supabase UUID user ids.

## Alternative — read-only demo mode

If demo isolation is not worth the state growth, make the demo token read-only and reject mutations:

```python
READ_ONLY_DETAIL = "The public demo is read-only. Run the API locally to modify the watchlist."

def require_writable(user_id: str, settings: Settings) -> None:
    if settings.auth_mode == "demo" and settings.demo_read_only:
        raise HTTPException(status_code=403, detail=READ_ONLY_DETAIL)
```

Call it at the top of `create_watchlist`, `add_item`, `remove_item`, `add_rule`, and `acknowledge`, and add `demo_read_only: bool = False` to `Settings`. The frontend already surfaces backend `detail` strings in its error toasts, so no UI change is required beyond disabled buttons if desired.

## For real users

Neither variant replaces real accounts. For persistent multi-user operation, use `NAZAR_AUTH_MODE=supabase` (Supabase Auth JWTs, already implemented in `auth.py`) together with Supabase persistence — see [01-serverless-persistence.md](01-serverless-persistence.md).

## Verification

- Open the demo in two browsers (or one normal + one private window); add a stock in one — the other must not see it.
- `test_api.py`: add a test sending two different `X-Demo-Session` headers and assert the second session's catchup does not include the first session's added item.
- With `demo_read_only=true`, every POST/DELETE returns 403 with the explanatory detail; GET catchup still works.

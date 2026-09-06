# Fix G6 — Missing CRUD surface (rules, watchlists, free-form stock add)

**Severity:** High · **Status:** Guide only (API + UI feature work)

## Problem

The API is write-mostly with no way back out:

- **Rules can never be listed or deleted.** `POST /api/watchlists/items/{item_id}/rules` exists; nothing else does. Rules accumulate forever — in Supabase mode they pile up in `personal_rules` (the unique constraint only dedupes exact `(item, type, threshold)` triples), and the UI has no management surface at all.
- **Watchlists can be created but never listed, renamed, or deleted.** `POST /api/watchlists` returns an id; there is no `GET /api/watchlists`, so a client cannot even rediscover what it created. Combined with the memory cap (G11) this eventually locks a user out of creating more.
- **The frontend can only add 3 stocks.** `lib/nazar/stock-catalog.ts` hardcodes LTIM, BAJFINANCE, TITAN, while the backend accepts any symbol matching `^[A-Za-z0-9&._-]+$`.

## Fix — backend endpoints

Add to `backend/app/main.py` (all follow the existing patterns: `authenticated_user`, `PermissionError` → 404):

```python
@app.get("/api/watchlists")
async def list_watchlists(authorization: str | None = Header(default=None)) -> dict:
    user_id = authenticated_user(authorization, runtime)
    return {"watchlists": repository(runtime).list_watchlists(user_id)}

@app.get("/api/watchlists/{watchlist_id}/rules")
async def list_rules(
    watchlist_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    user_id = authenticated_user(authorization, runtime)
    try:
        rules = repository(runtime).list_rules(user_id, watchlist_id)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Watchlist not found") from exc
    return {"rules": [rule.__dict__ for rule in rules]}

@app.delete("/api/watchlists/rules/{rule_id}")
async def remove_rule(
    rule_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user(authorization, runtime)
    try:
        repository(runtime).remove_rule(user_id, rule_id)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Rule not found") from exc
    return {"status": "removed"}

@app.delete("/api/watchlists/{watchlist_id}")
async def remove_watchlist(
    watchlist_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id = authenticated_user(authorization, runtime)
    try:
        repository(runtime).remove_watchlist(user_id, watchlist_id)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Watchlist not found") from exc
    return {"status": "removed"}
```

### Repository additions

Extend the `WatchlistStore` protocol (`backend/app/repository.py`) with `list_watchlists`, `remove_rule`, `remove_watchlist`, then implement:

**Memory** (state is keyed by `(user_id, watchlist_id)` after the G3 fix):

```python
def list_watchlists(self, user_id: str) -> list[dict[str, str]]:
    with self._lock:
        return [
            {"id": watchlist_id, "name": name}
            for (owner_id, watchlist_id), name in self._watchlists.items()
            if owner_id == user_id
        ]

def remove_rule(self, user_id: str, rule_id: str) -> None:
    with self._lock:
        for key, rules in self._rules.items():
            if key[0] != user_id:
                continue
            if any(rule.id == rule_id for rule in rules):
                self._rules[key] = [r for r in rules if r.id != rule_id]
                return
    raise PermissionError("rule not found")

def remove_watchlist(self, user_id: str, watchlist_id: str) -> None:
    key = (user_id, watchlist_id)
    with self._lock:
        if key not in self._watchlists:
            raise PermissionError("watchlist not found")
        del self._watchlists[key]
        self._items.pop(key, None)
        self._rules.pop(key, None)
        self._watermarks.pop(key, None)
```

**Supabase** — ownership check then delete; cascades in `supabase/schema.sql` already clean up items, rules, and watermarks on watchlist delete:

```python
def remove_rule(self, user_id: str, rule_id: str) -> None:
    result = (
        supabase_client()
        .table("personal_rules")
        .select("id,watchlist_items!inner(watchlists!inner(owner_id))")
        .eq("id", rule_id)
        .eq("watchlist_items.watchlists.owner_id", user_id)
        .maybe_single()
        .execute()
    )
    if not result or not result.data:
        raise PermissionError("rule not found")
    supabase_client().table("personal_rules").delete().eq("id", rule_id).execute()

def remove_watchlist(self, user_id: str, watchlist_id: str) -> None:
    self._owned_watchlist(user_id, watchlist_id)
    supabase_client().table("watchlists").delete().eq("id", watchlist_id).execute()
```

## Fix — frontend

1. **Rule management:** the catchup payload does not include rules today. Either add them to `CatchupCard` (`backend/app/models.py`) or call the new `GET .../rules` from the detail sheet. Render each rule with a delete button calling `nazarApi("/api/watchlists/rules/" + rule.id, { method: "DELETE" })`, then `refresh()`.
2. **Free-form add:** replace the fixed list in the add dialog (`app/nazar-dashboard.tsx`) with an input for symbol + company + sector select (the NIFTY sector indices used across the app), validating the symbol against the backend pattern `^[A-Za-z0-9&._-]{1,20}$`. Keep `addableStocks` as suggestions above the form rather than the only options.

## Verification

- API round trip test in `backend/tests/test_api.py`: create rule → `GET rules` shows it → `DELETE` → gone from both the rules listing and the next catchup's signals.
- Watchlist delete test: create, delete, then `GET /api/watchlists` no longer lists it, and catchup with its id returns 404.
- UI: add a rule from the sheet, see it listed, delete it, and confirm the attention grouping updates after refresh.

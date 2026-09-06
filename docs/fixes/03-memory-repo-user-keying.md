# Fix G3 + G15 — Memory repository cross-user keying and thread safety

**Severity:** Critical (G3), Medium (G15) · **Status:** Fixed

## Problem

### G3 — items and rules keyed by watchlist id alone

In `backend/app/repository.py`, `MemoryWatchlistRepository` kept ownership in one map but data in another with a weaker key:

```python
self._watchlists: dict[tuple[str, str], str] = {}   # keyed by (user_id, watchlist_id)
self._items: dict[str, list[WatchlistItemRecord]] = {}  # keyed by watchlist_id only
self._rules: dict[str, list[RuleRecord]] = {}           # keyed by watchlist_id only
```

`get_or_create_watchlist` defaults the id to the literal `"primary"` for every user. With any multi-user auth (e.g. the per-session demo identity from [02-demo-token-isolation.md](02-demo-token-isolation.md), or a future auth mode combined with memory persistence), the second user to call `get_or_create_watchlist` **reset `self._items["primary"]` to the default ten stocks**, wiping the first user's modifications, and both users then shared the same item and rule lists. Ownership checks passed for both users because each had their own `(user_id, "primary")` entry in `_watchlists`.

It was latent only because demo mode maps every request to the single `"demo-user"`.

### G15 — reads outside the lock

`_owned_item` iterated `self._items.items()` without holding `self._lock`, racing against writers (`add_item`, `remove_item`, `add_rule`) that mutate those lists under the lock. Same for `list_items`, `list_rules`, and `get_watermark`.

## Fix (implemented)

All per-watchlist state is now keyed by `(user_id, watchlist_id)`, and every read of shared dictionaries happens under the lock:

```python
class MemoryWatchlistRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        self._watchlists: dict[tuple[str, str], str] = {}
        self._items: dict[tuple[str, str], list[WatchlistItemRecord]] = {}
        self._rules: dict[tuple[str, str], list[RuleRecord]] = {}
        self._watermarks: dict[tuple[str, str], datetime] = {}
        ...

    def get_or_create_watchlist(self, user_id: str, watchlist_id: str | None) -> str:
        candidate = watchlist_id or "primary"
        key = (user_id, candidate)
        with self._lock:
            if key not in self._watchlists:
                self._watchlists[key] = "My watchlist"
                self._items[key] = [...defaults...]
                self._rules[key] = [...defaults...]
        return candidate
```

`_owned_item` now resolves ownership under the lock and only scans the calling user's own watchlists:

```python
    def _owned_item(self, user_id: str, item_id: str) -> str:
        with self._lock:
            for (owner_id, watchlist_id), items in self._items.items():
                if owner_id == user_id and any(item.id == item_id for item in items):
                    return watchlist_id
        raise PermissionError("watchlist item not found")
```

A side benefit: because item lookups are now scoped to the caller, a user can no longer probe other users' item ids through `remove_item`/`add_rule` (previously the ownership check happened only after the global scan found the item).

The same change added the G11 watchlist cap — `create_watchlist` refuses to create more than `MAX_WATCHLISTS_PER_USER` (20) watchlists per user, raising `ValueError`, which `POST /api/watchlists` maps to HTTP 429.

## Verification

`backend/tests/test_repository.py` (added) covers:

- Two users with the default `"primary"` watchlist get independent item lists; user B's `get_or_create_watchlist` does not reset user A's items.
- `remove_item` by user B against user A's item id raises `PermissionError`.
- The 21st `create_watchlist` for one user raises `ValueError` while another user can still create watchlists.

Run:

```bash
cd backend
python -m unittest discover -s tests -v
```

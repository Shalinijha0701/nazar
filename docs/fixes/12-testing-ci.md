# Fix G13 — Test coverage holes and CI hardening

**Severity:** Medium · **Status:** Partially fixed (regression tests added for repository keying, live-mode behavior, health, threshold bound); broader suite and CI additions are guide only

## Problem

What was tested: signal formulas (`backend/tests/test_signals.py`, thorough) and the replay API surface (`backend/tests/test_api.py`), plus two small frontend unit tests (`tests/*.test.mjs` covering the mapper and projection).

What was not:

- `backend/app/services/live.py` — **zero** coverage of the live grouping/staleness/rule logic.
- `backend/app/services/trading_time.py` — no tests for weekends, session boundaries, or multi-day spans.
- `backend/app/providers/replay.py` and `groww.py` — untested (replay is trivially testable; Groww at least deserves `_parse_timestamp`/`_format_time`/alias tests, which are pure).
- `SupabaseWatchlistRepository` — untested (acceptable to leave to integration tests, but worth stating).
- Frontend components — no tests for `nazar-dashboard.tsx` flows (mark reviewed, add stock, error banner).
- CI (`.github/workflows/ci.yml`) runs frontend lint but **no backend lint or type check**, and neither job reports coverage.

## Implemented

New `backend/tests/test_repository.py`:

- per-user isolation of the default `primary` watchlist (regression for G3);
- cross-user `remove_item` denial;
- the `MAX_WATCHLISTS_PER_USER` cap (G11).

New `backend/tests/test_live.py` (uses a stub provider — no network):

- symbols with no candles land in `data_unavailable`;
- a `price_above` rule crossing produces a `personal_rule` signal and attention grouping;
- an armed `volume_pace` rule yields the "not evaluated" narrative (G4);
- `default_live_watermark` spans ≥ 1875 trading minutes and respects the 14-day floor (G7).

Extended `backend/tests/test_api.py`:

- `/health` exposes only `{"status": "ok"}` (G9);
- rule threshold above the upper bound is rejected with 422 (G16);
- provider failure in groww mode returns 502 with a safe body; an internal error returns the generic 500 body (G8).

## Guide — remaining work

### Backend: lint + type check in CI

```yaml
# .github/workflows/ci.yml, backend job, after pip install
- run: pip install ruff mypy
- run: ruff check app tests
- run: ruff format --check app tests
- run: mypy app --ignore-missing-imports
```

with a minimal `backend/pyproject.toml`:

```toml
[tool.ruff]
line-length = 110
target-version = "py312"

[tool.mypy]
python_version = "3.12"
warn_unused_ignores = true
```

Expect a short cleanup pass the first time (import order, a few annotations). `--ignore-missing-imports` covers `growwapi`/`supabase` which ship no stubs.

### Backend: coverage gate

```yaml
- run: pip install coverage
- run: coverage run -m unittest discover -s tests && coverage report --fail-under=80
```

`live.py` and `repository.py` are now covered; the biggest remaining gap the report will show is `SupabaseWatchlistRepository` — either exclude it (`# pragma: no cover` on the class, honest since it needs an integration environment) or add a contract test using a mocked `supabase_client`.

### trading_time edge cases worth pinning

```python
def test_weekend_has_zero_trading_minutes(self): ...        # Sat 10:00 -> Sun 14:00 == 0
def test_full_session_is_375_minutes(self): ...             # 09:15 -> 15:30 IST
def test_span_across_week_boundary(self): ...               # Fri 15:00 -> Mon 09:30 == 45
def test_open_boundary_inclusive_close_exclusive(self): ... # is_market_open at 09:15 True, 15:30 False
```

(NSE holidays are not modeled — trading_minutes treats holidays as trading days. If that matters for live percentile quality, add a holiday calendar table and subtract those days; note it in `docs/functional-spec.md` either way.)

### Frontend: component tests

The current `node --test` + tsx setup cannot render components. Two options:

- **Vitest + Testing Library** (recommended): `npm i -D vitest @testing-library/react @testing-library/user-event jsdom`, move the two existing `.mjs` tests to vitest (they run unchanged), then add tests for: error banner renders on fetch failure and Retry calls refresh; "Mark reviewed" disables after success; add-stock dialog disables already-tracked symbols.
- **Playwright e2e** against `next dev` + the replay backend: highest fidelity for the demo flow (steps 2–5 of the README), at the cost of CI time; the deterministic replay feed makes assertions stable.

## Verification

```bash
cd backend && python -m unittest discover -s tests -v   # all green, including new files
npm run lint && npm test && npm run build               # unchanged frontend suite green
```

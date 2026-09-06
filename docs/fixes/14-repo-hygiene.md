# Fix G16 — Repository hygiene

**Severity:** Low · **Status:** Fixed

## Problems and fixes

### 1. Demo token compared with `!=`

`backend/app/auth.py` compared the bearer token with a plain inequality, which short-circuits on the first mismatched byte and is in principle timing-observable. Fixed with a constant-time comparison:

```python
import secrets

if not secrets.compare_digest(token, settings.demo_token):
    raise HTTPException(status_code=401, detail="Invalid demo token")
```

Low practical risk for a public demo token (see G2 — the token is deliberately public), but it is the correct idiom and costs nothing; it also stays correct if the token ever becomes secret.

### 2. Rule threshold had no upper bound

`RuleCreate.threshold` was `Field(gt=0)` — `1e308` was a valid threshold, which then flows into price formatting (`₹{rule.threshold:,.2f}`) and comparisons. Bounded to a generous but sane ceiling:

```python
class RuleCreate(BaseModel):
    rule_type: str = Field(pattern=r"^(price_above|price_below|volume_pace)$")
    threshold: float = Field(gt=0, le=10_000_000)
```

No NSE equity price or reasonable volume-pace multiple approaches 10⁷; the API now rejects absurd values with a 422 instead of storing them.

### 3. `.vscode/` untracked and not ignored

Editor configuration is per-developer; added to `.gitignore`:

```gitignore
# editors
.vscode/
```

(If the team later wants shared launch configs, whitelist specific files: `!.vscode/launch.json`.)

### 4. No LICENSE

The repo had a license for the vendored shadcn CSS (`vendor/shadcn-tailwind-4.13.0.LICENSE.md`) but none for the project itself — meaning, legally, all rights reserved: nobody may copy or reuse the code, which is presumably not the intent for a hackathon project. Added an MIT `LICENSE` at the root (held by "Nazar contributors" — replace with the actual copyright holder's name if preferred).

## Verification

- `git status` shows `.vscode/` no longer as untracked noise.
- `POST /api/watchlists/items/{id}/rules` with `threshold: 1e308` returns 422 (`backend/tests/test_api.py::test_rule_threshold_upper_bound`).
- Auth behavior unchanged: valid token 200, invalid 401 (existing tests still pass).

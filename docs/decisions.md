# Decision Log

Decisions taken during the gap-analysis, hardening, and testing engagement (September 2026), with rationale. Format loosely follows ADR practice: context → decision → consequences. Related: [GAPS.md](../GAPS.md), fix guides in [fixes/](fixes/), [bugs.md](bugs.md).

## D1 — Split gaps into "implemented" vs. "guide only" by external dependency

**Context:** 16 gaps found; the user asked for fix documentation *and* implemented fixes.
**Decision:** implement every fix that is self-contained and verifiable by the local test suites; ship the rest (Supabase migration, demo-identity model, distribution pipeline, CRUD expansion, CI additions) as ready-to-apply guides with exact code.
**Why:** fixes requiring a Supabase project, Groww credentials, Vercel env changes, or a product decision cannot be verified from this machine; landing them blind risks breaking the deployed demo. Every guide names its verification steps so any of them can be picked up later.

## D2 — Key the memory repository by `(user_id, watchlist_id)` rather than adding a per-user wrapper

**Context:** items/rules were keyed by watchlist id alone while ownership was per-user (gap G3).
**Decision:** change the dictionary keys themselves and move every read under the existing lock; add `_owned_item_locked` scoped to the calling user.
**Why:** the smallest change that makes cross-user collision *structurally impossible* instead of policed; it also closed the G15 race and stopped cross-user item-id probing as a side effect. Consequence: `_items`/`_rules` shapes changed — covered by new regression tests.

## D3 — Cap watchlists per user in the repository, not with middleware

**Context:** unbounded `POST /api/watchlists` was a memory-exhaustion vector (G11).
**Decision:** `MAX_WATCHLISTS_PER_USER = 20` enforced in `create_watchlist`, surfaced as HTTP 429; middleware rate limiting (slowapi) documented but not added.
**Why:** the repository cap bounds the actual resource without a new dependency, and works identically under tests. Per-instance middleware limits are weak on serverless anyway (state per lambda); the guide points at WAF/shared-store options for a hard guarantee.

## D4 — Map live-provider failures to 502 via a dedicated exception, keep a generic 500 handler for the rest

**Context:** no global error handling (G8); provider outages looked identical to code bugs.
**Decision:** wrap the live-mode provider call, translating any failure into `ProviderUnavailableError` → 502 with a safe, actionable message; register a catch-all `Exception` handler returning a generic 500 JSON body; log details server-side only.
**Why:** the frontend surfaces `detail` strings directly, so status/message quality is user-visible. Trade-off: the wrap treats *any* exception inside `live_market_catchup` as a provider failure — acceptable because the provider is that path's dominant failure mode, and the alternative (enumerating SDK exception types) couples us to `growwapi` internals. Known caveat documented: the generic 500 handler runs outside the CORS middleware, so 500s lack CORS headers; the browser still shows the failure banner.

## D5 — Widen the default live lookback by walking back over *trading* minutes, capped at 14 days

**Context:** the 4-wall-clock-hour default contradicted the "returned after being away" premise (G7); 4 evening/weekend hours often contain zero trading minutes.
**Decision:** `default_live_watermark()` walks back day by day until the window covers the largest supported horizon (1875 trading minutes ≈ 5 NSE sessions), never more than 14 calendar days. A stored watermark always wins.
**Why:** 1875 is the engine's own maximum meaningful horizon — going further back adds fetch cost without adding signal; the 14-day floor bounds provider load across long holidays. Trading-minute (not wall-clock) accounting reuses the existing `trading_minutes_between`.

## D6 — Make live mode *say* volume-pace rules were not evaluated instead of half-implementing them

**Context:** volume rules were silently skipped in live mode (G4); full evaluation needs same-minute historical volume data that does not exist yet.
**Decision:** append an explicit sentence to the card narrative when an armed volume rule could not be evaluated; keep full evaluation as a guide (data pipeline required).
**Why:** the product's core promise is evidence-first honesty; a truthful "not evaluated" preserves it at near-zero cost, while a rushed evaluator without real historical volumes would fabricate the very evidence the product refuses to fake.

## D7 — Trim `/health` but keep the GET-catchup side effect (documented, not removed)

**Context:** `/health` leaked provider/persistence/auth config; `GET catchup` lazily creates the seeded demo watchlist (G9).
**Decision:** `/health` → `{"status": "ok"}` now; lazy creation stays, with two removal designs (read-only resolver + explicit bootstrap POST) documented.
**Why:** the health trim is free. The lazy seed is what makes the demo's first page load show a populated watchlist — removing it changes product behavior and the demo script, which is the owner's call, not a hardening detail.

## D8 — Remove the hardcoded CORS origin even though it touches the deployed setup

**Context:** a personal Vercel preview URL was baked into `config.py` defaults (G10).
**Decision:** default to `http://localhost:3000` only; deployed origins must come from `NAZAR_ALLOWED_ORIGINS`. Flagged the deployment dependency in the summary, then **verified against the live API** (CORS preflight probes) that the env var was already set and behavior was unchanged before/after the deploy.
**Why:** committed deployment URLs leak into every fork and rot when previews rotate. Verification-first: the probe showed the live API already rejected the hardcoded origin, proving the env override was in control — so the change was a no-op in production.

## D9 — Derive the "reviewed" button state instead of resetting a flag in an effect

**Context:** the reviewed flag never reset (G14); the obvious fix (`useEffect(() => setReviewed(false), [catchup])`) was rejected by the `react-hooks/set-state-in-effect` lint rule.
**Decision:** store `acknowledgedThrough` (which evaluation point was acknowledged) and derive `reviewed = acknowledgedThrough === catchup.evaluated_through`.
**Why:** derived state is semantically better, not just lint-appeasing: in replay mode the button correctly *stays* disabled after acknowledging (the evaluation point is fixed; there is nothing new), while in live mode each refetch advances `evaluated_through` and re-enables it exactly when new data exists. The fix guide was updated to match what shipped.

## D10 — Gate rule creation on a real `item_id`; delete the symbol fallback

**Context:** `saveRule` fell back to using the stock symbol as an item id — a guaranteed 404 dressed as a fallback (G12).
**Decision:** remove the fallback, guard `saveRule` with a clear toast, and hide the card's "Add personal rule" button when `itemId` is absent.
**Why:** a code path that can only fail should not exist; failing fast with an explanation beats a mysterious "Could not save rule".

## D11 — Documentation-only for OpenAPI codegen, CRUD endpoints, and demo-identity isolation

**Why each:** codegen (G12) needs a `package.json`/CI workflow decision and touches the type layer broadly; CRUD (G6) is feature work with UI surface the owner should shape; demo isolation (G2) is a product choice between per-session state growth and a read-only demo. All three guides contain complete, tested-shape code so the decision is the only remaining work.

## D12 — Test through the real browser with Playwright driving Edge, not downloaded Chromium

**Context:** `npx playwright install chromium` failed (network-restricted download); the user asked for Playwright testing and visible-browser verification.
**Decision:** `playwright` npm package installed with `--no-save` (repo untouched) launching the system Edge via `channel: "msedge"`; headed + slowMo for the demonstration run, headless for the 45-check full suite. The Playwright MCP server was added to Claude Code config for future sessions (`claude mcp add playwright -- npx -y @playwright/mcp@latest`).
**Why:** Edge is guaranteed present on Windows 11 and is Chromium — identical engine, zero download. `--no-save` keeps test tooling out of the app's dependency tree until the owner adopts an E2E framework properly (fix guide 12 covers that).

## D13 — Verify deployment facts behaviorally instead of trusting configuration assumptions

**Context:** needed to know whether `NAZAR_ALLOWED_ORIGINS` was set in Vercel (no CLI auth available) and whether the demo URL was public.
**Decision:** probe the live API with CORS preflights from three origins and interpret the allow/deny pattern against the known code defaults; open the demo URL in a real browser.
**Why:** the old deployed code's built-in default *included* the dashboard origin, so a rejection of that origin was proof the env var overrides it — a conclusion no amount of config reading could give without dashboard access. The same browser run surfaced BUG-8 (Vercel SSO blocking the demo), which pure API probing had only hinted at.

## D14 — Keep Next.js-generated `AGENTS.md`/`CLAUDE.md` untracked, and leave `.env.local` in place

**Context:** `next dev` (Next 16) auto-generates agent-rules files; testing required a `.env.local`.
**Decision:** leave both as-is — the generated files regenerate anyway and the env file matches the README's own local-setup instructions and is gitignored.
**Why:** deleting regenerating files is churn; committing them is the owner's call.

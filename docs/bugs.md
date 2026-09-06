# Bug Report — Playwright End-to-End Testing

Full-application test run against the local stack (FastAPI replay backend on `:8000`, Next.js dashboard on `:3000`), driven with Playwright on Microsoft Edge. **45 checks: 37 passed, 2 failed, 6 observations.** The suite covered: load and layout, search and tabs, replay controls, all evidence-sheet variants, adding stocks, creating price and volume rules, invalid input, removing stocks, the acknowledge/watermark round trip, reload persistence, backend-failure recovery, and a 375 px mobile viewport.

## Confirmed bugs

### BUG-1 — Backend validation errors render as `[object Object]` (High)

**Repro:** Add a personal rule with threshold `0` (passes the client check, rejected by the backend's `Field(gt=0)`).
**Observed:** the error toast literally reads **`[object Object]`**.
**Root cause:** `lib/nazar/use-catchup.ts` assumes the error `detail` is a string:

```ts
const payload = await response.json().catch(() => null);
throw new Error(payload?.detail ?? "Nazar API request failed");
```

FastAPI returns *validation* errors (HTTP 422) with `detail` as an **array of error objects** (`[{type, loc, msg, ...}]`), which stringifies to `[object Object]`. Manual `HTTPException` details are strings, so only validation errors are affected.
**Fix:**

```ts
if (!response.ok) {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail;
  const message = typeof detail === "string"
    ? detail
    : Array.isArray(detail)
      ? detail.map((entry) => entry?.msg ?? "Invalid input").join("; ")
      : "Nazar API request failed";
  throw new Error(message);
}
```

Apply the same handling to the identical block in `useCatchup`'s fetch. Additionally, the rule dialog's client check (`app/nazar-dashboard.tsx`) should reject non-positive values before the request: `if (!(value > 0)) { toast.error("Threshold must be greater than zero"); return; }`.

### BUG-2 — 4 px horizontal overflow at mobile width (Low)

**Repro:** load the dashboard at a 375×812 viewport.
**Observed:** `document.documentElement.scrollWidth` exceeds the client width by 4 px, so the page can be nudged sideways on phones. Everything else on mobile is correct (desktop sidebar hidden, cards stack, dialogs fit).
**Likely area:** an element in the hero section or header escaping its container by a few pixels at narrow widths (the decorative circles are inside `overflow-hidden`, so the first suspects are the header's flex row or the replay-control panel padding).
**Fix approach:** reproduce at 375 px in devtools, find the element whose `getBoundingClientRect().right` exceeds the viewport, and constrain it (`min-w-0` on the flex children or `overflow-x-clip` on `<main>`). Add a regression check (the Playwright assertion used here: `scrollWidth - clientWidth <= 0`).

## Product-behavior findings (not crashes, but user-visible inconsistencies)

### BUG-3 — Header "trading minutes shown" reflects the replay slider, not the review interval (Medium)

The subtitle renders `Since your last review · {replayIndex * 15} trading minutes shown`. That number is the **replay slider position**, not the API's `trading_minutes`. After acknowledging and reloading, the API reports `trading_minutes: 0`, but the header shows "165 trading minutes shown" again because the slider defaults to the end of the full-day chart. The chart intentionally shows the whole session, so the label should either use `catchup.trading_minutes` or say "replay position" instead of implying it is the review interval.

### BUG-4 — Volume-pace rules accepted in replay mode but never evaluated for most stocks (Medium)

Saving a volume-pace rule on ITC succeeds ("Rule saved · The backend recalculated this review interval") but no signal can ever appear: the replay engine only evaluates volume pace for the hardcoded HDFCBANK event (`backend/app/demo.py`). The success toast implies evaluation happened. Live mode now states this honestly on the card (fix G4); the replay path should do the same, or the rule dialog should say volume rules are demo-limited to HDFCBANK.

### BUG-5 — Price rules that can never trigger are accepted silently (Low)

A `price_above` rule with a threshold already below the baseline price (or `price_below` above it) is stored and evaluated, but by definition can never fire (`first_crossed_above` requires `baseline < threshold`). The user gets "Rule saved" and then permanent silence. Suggest a warning at creation time comparing the threshold to the current price the UI already displays.

### BUG-6 — "Mark reviewed" re-enables after reload with nothing to review (Low)

After acknowledging and reloading, the button is enabled again even though `trading_minutes` is 0 and re-acknowledging is a no-op (the backend watermark is monotonic, so this is harmless but misleading). Suggest disabling when `catchup.trading_minutes === 0`.

### BUG-7 — Sidebar caps at 8 stocks with no indicator (Low)

`projected.slice(0, 8)` in `app/nazar-dashboard.tsx` limits the sidebar list; with the 10 default stocks (plus any added), the remainder are silently absent. Either remove the cap (the container already scrolls: `overflow-y-auto`) or add a "+N more" row.

## Deployment finding (from browser testing of the live URL)

### BUG-8 — The README's live-demo URL is behind Vercel SSO (Critical for the demo's purpose)

Playwright confirmed `https://nazar-8lczelyeh-shalinijha1008s-projects.vercel.app/` redirects to `vercel.com/login` — Vercel Deployment Protection is on, so judges or anyone without the owner's Vercel account **cannot open the demo at all**. Fix: Vercel dashboard → project → Settings → Deployment Protection → disable Vercel Authentication (or link the unprotected production domain in the README). The backend URL (`backend-plum-mu-21.vercel.app`) is publicly reachable, so only the dashboard project needs the change.

## What passed (verified working)

- Load: title, replay badge, 3/5/2 grouping chips, attention + unavailable cards visible, "Normal noise" collapsible expands to all 10.
- Search filters by symbol/company; empty state renders; all four tabs filter correctly.
- Replay: reset returns to 11:15 am IST, play advances and auto-stops at 02:00 pm IST.
- Evidence sheets: RELIANCE (personal rule + sector surprise + percentile progress), HDFCBANK (volume pace "crossed 1.8×" with 20 comparison sessions), INFY (path event, 97.6th percentile across 252 observations), IRCTC (unavailable state with preserved confirmed path event).
- Add stock: LTIM added via API, appears with limited-history state, disabled in the catalog once tracked.
- Rules: valid price rule on TCS moves it to Attention with the correct receipt.
- Remove stock: MARUTI removed and stays gone.
- Acknowledge: attention → 0, "Last reviewed" label advances 11:15 am → 02:00 pm IST, button disables, and **acknowledged events do not repeat after reload** (the README's core demo claim).
- Failure handling: API outage shows the error banner with Retry; Retry recovers once the API returns.
- No unexpected console errors (the two captured were the deliberate 422 and the deliberately aborted request).

## Recommended fix order

1. BUG-1 (one small function, user-facing garbage text)
2. BUG-8 (blocks the demo's entire audience)
3. BUG-3 and BUG-4 (evidence-first product showing misleading labels)
4. BUG-2, BUG-5, BUG-6, BUG-7 (polish)

# Fix G14 — Frontend robustness: hardcoded times, missing error/loading routes, stuck reviewed state

**Severity:** Medium · **Status:** Partially fixed (labels, error/loading routes, reviewed reset); live polling is guide only

## Problems

All in `app/nazar-dashboard.tsx` unless noted:

1. **Hardcoded review times.** The replay-time fallback was a literal `"11:15"` and the slider footer showed a literal `Last reviewed · 11:15` — even in live mode, and even in replay mode after acknowledging (when the real watermark is later). The evidence-first product printed made-up timestamps.
2. **No route-level error/loading UI.** The app directory had no `error.tsx` or `loading.tsx`; a render error produced Next's default blank error screen.
3. **Stuck "Reviewed" button.** `markReviewed` set `reviewed=true` and nothing ever reset it: after `refresh()` brought new data (or in live mode, after new trading minutes accumulated), the button stayed disabled until a full page reload.
4. **No auto-refresh in live mode** — the dashboard shows a "Live connected" badge but only fetches once.

## Implemented

### 1. Times derived from the API response

```tsx
const reviewedLabel = catchup
  ? new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })
      .format(new Date(catchup.reviewed_through))
  : "—";
const replayTime = stocks[0]?.times[Math.min(replayIndex, maxReplayIndex)] ?? reviewedLabel;
```

and the slider footer renders `Last reviewed · {reviewedLabel}`. Both now track `reviewed_through` from the backend — correct in replay and live modes, before and after acknowledgement.

### 2. Route-level error and loading UI

- `app/error.tsx` — client error boundary with the same visual language as the in-page error banner, plus a "Try again" button wired to Next's `reset()`.
- `app/loading.tsx` — lightweight skeleton so first paint isn't a blank page while the client bundle hydrates.

### 3. Reviewed state derived from the acknowledged response

The stored `reviewed` boolean is replaced with derived state — the component remembers *which* evaluation point was acknowledged and compares it to the current response:

```tsx
const [acknowledgedThrough, setAcknowledgedThrough] = useState<string | null>(null);
const reviewed = !!catchup && acknowledgedThrough === catchup.evaluated_through;
```

`markReviewed` sets `acknowledgedThrough(catchup.evaluated_through)`; `resetReplay` clears it. In replay mode the button stays correctly disabled after acknowledging (the evaluation point is fixed at `DEMO_END`, and there is nothing more to review); in live mode each refetch advances `evaluated_through`, so the button re-enables exactly when there is genuinely new data to acknowledge. This also satisfies the `react-hooks/set-state-in-effect` lint rule, which rejects the naive "reset a flag in an effect" approach.

## Guide — live-mode polling

Add an interval refetch to `useCatchup` (`lib/nazar/use-catchup.ts`), active only when the current data says the source is live:

```ts
useEffect(() => {
  if (data?.source !== "groww") return;
  const timer = window.setInterval(() => {
    setRequestVersion((version) => version + 1);
  }, 60_000);
  return () => window.clearInterval(timer);
}, [data?.source]);
```

One minute matches the candle granularity. Refinements worth adding at the same time:

- Pause when the tab is hidden (`document.visibilityState !== "visible"`) to save provider quota.
- Keep the previous data on refetch errors (the hook already does — `setError` doesn't clear `data`), and render the banner alongside stale data rather than replacing it.
- Show `last_updated_at` freshness on cards so a stalled poll is visible (the API already sends it; `DataBadge` displays state, not age).

## Verification

- Replay mode: acknowledge, refresh — the footer's "Last reviewed" changes from 11:15 IST to 14:00 IST (the demo end), matching `reviewed_through` in devtools.
- Throw inside the dashboard component in dev: the styled error boundary renders with a working "Try again".
- Mark reviewed → button disables; in replay mode it stays disabled (nothing new to review at the fixed demo end), in live mode it re-enables once a refetch advances `evaluated_through`.
- `npm run lint && npm test && npm run build` pass.

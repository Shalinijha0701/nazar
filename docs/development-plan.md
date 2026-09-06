# Nazar — Development Plan & Task Tracker

Phased overhaul of the application: fix all reported bugs, improve the workflow, and redesign the UI/UX (dark glass · claymorphism · minimalist). **Every task is verified by a named Playwright test before its box is ticked.** A box `[ ]` becomes `[x]` only when that task's test passes in `npm run test:e2e` (plus backend `unittest` where noted).

**Design system (applies to all Phase 3 work):** one font (Inter, weights 400/600/800); exactly two text sizes (14 px base, 20 px large — hierarchy via weight and color); 4 px spacing grid; exactly two corner radii (20 px surfaces, 12 px controls); glassmorphism for surfaces (translucent white on `#0b1020`, backdrop blur, thin border); claymorphism for interactive elements (soft dual shadows); single lime accent `#b8ff65`; rose reserved for errors/unavailable.

**Git cadence:** one commit + push per completed phase.

---

## Phase 0 — Development plan & Playwright harness

- [x] **0.1** Write this development plan with every phase/task as a checkbox — ticked only when its test passes
- [x] **0.2** Test harness: `@playwright/test` + `concurrently` devDependencies, `playwright.config.ts` (Edge channel, `workers: 1`, auto-started backend `:8000` + frontend `:3000`), `e2e/` folder, `npm run test:e2e` + `npm run dev:all` scripts, gitignore test artifacts — *verified by the harness executing 0.3*
- [x] **0.3** Smoke spec: dashboard loads, replay badge, 3/5/2 group counts, `/health` returns ok — `e2e/00-smoke.spec.ts` (2/2 passed)
- [x] **0.4** Phase 0 boxes ticked, commit + push — "Phase 0: development plan and Playwright harness"

## Phase 1 — Fix all bugs (from docs/bugs.md)

- [ ] **1.1** BUG-1 (High): human-readable API errors — shared `apiErrorMessage()` handles string *and* array `detail` in `nazarApi`/`useCatchup`; rule dialog validates `value > 0` client-side — `e2e/10-bugs.spec.ts` › "invalid threshold shows a readable error"
- [ ] **1.2** BUG-3 (Medium): header shows the API's `trading_minutes`, replay position labeled separately — `e2e/10-bugs.spec.ts` › "header reports the API review interval" (+ re-checked after acknowledge in `40-regression`)
- [ ] **1.3** BUG-4 (Medium): replay mode names unevaluated volume-pace rules in the card narrative (mirror of live-mode honesty) + note in the rule dialog — `e2e/10-bugs.spec.ts` › "volume rule reports it was not evaluated"
- [ ] **1.4** BUG-5 (Low): warning when a price rule can never trigger (threshold on the wrong side of the current price) — `e2e/10-bugs.spec.ts` › "never-triggerable rule warns"
- [ ] **1.5** BUG-6 (Low): "Mark reviewed" disabled when `trading_minutes === 0` — asserted in `e2e/40-regression.spec.ts` acknowledge flow
- [ ] **1.6** BUG-7 (Low): sidebar lists **all** tracked stocks (remove the 8-item cap) — `e2e/10-bugs.spec.ts` › "sidebar lists every tracked stock"
- [ ] **1.7** BUG-2 (Low): zero horizontal overflow at 375 px — `e2e/10-bugs.spec.ts` › "no horizontal scroll on mobile"
- [ ] **1.8** BUG-8 (Critical, **manual — owner action**): disable Vercel Deployment Protection on the dashboard project so the public demo opens; runbook in `docs/fixes/15-deployment-protection.md` — *cannot be automated or ticked from code*
- [ ] **1.9** Backend suite still green (`python -m unittest discover -s tests`), Phase 1 boxes ticked, commit + push — "Phase 1: fix all reported bugs"

## Phase 2 — Workflow improvements

- [ ] **2.1** Rules CRUD backend: `GET /api/watchlists/{id}/rules` + `DELETE /api/watchlists/rules/{rule_id}`, `remove_rule` in both repositories, unittest coverage — backend `unittest` + exercised by 2.2's e2e
- [ ] **2.2** Rule management UI: evidence sheet lists the stock's rules with a delete action — `e2e/20-workflow.spec.ts` › "rule can be listed and deleted from the sheet"
- [ ] **2.3** Free-form add stock: symbol input (validated `^[A-Za-z0-9&._-]{1,20}$`) + company + sector select, catalog becomes suggestions — `e2e/20-workflow.spec.ts` › "any symbol can be added"
- [ ] **2.4** Data-layer resilience: refetch errors keep stale data visible under the banner; friendly 429 handling — `e2e/20-workflow.spec.ts` › "stale data survives a failed refresh"
- [ ] **2.5** Live-mode polling behind `NEXT_PUBLIC_POLL_MS` (default 60 s, only when `source === "groww"`) — `e2e/20-workflow.spec.ts` › "live source polls for fresh data"
- [ ] **2.6** Backend suite green, Phase 2 boxes ticked, commit + push — "Phase 2: rules management, free-form add, resilient data layer"

## Phase 3 — UI/UX redesign (dark glass · clay · minimalist)

- [ ] **3.1** Design tokens + typography: Inter via `next/font`, CSS variables for the two sizes / two radii / spacing / glass / clay recipes in `app/globals.css`, dark `#0b1020` body — `e2e/30-design.spec.ts` › "single font and two text sizes"
- [ ] **3.2** App shell: glass sticky header + glass sidebar (backdrop blur, thin border), clay header buttons — `e2e/30-design.spec.ts` › "shell surfaces are glass"
- [ ] **3.3** Hero + replay panel: one glass panel, clay play/reset controls, restyled slider, counts as glass chips — `e2e/30-design.spec.ts` › "replay controls work in the new hero"
- [ ] **3.4** Stock cards: glass cards, clay hover, unified glass signal chips (icon-differentiated), rose only for unavailable — `e2e/30-design.spec.ts` › "cards render grouped with signal chips"
- [ ] **3.5** Sheet + dialogs: glass surfaces, clay actions, 20 px radius, consistent forms — `e2e/30-design.spec.ts` › "sheet and dialogs round-trip"
- [ ] **3.6** States: token-styled loading skeleton, error banner, empty-search state — `e2e/30-design.spec.ts` › "error and empty states use the design system"
- [ ] **3.7** Responsive: 375 / 768 / 1440 with zero horizontal overflow — `e2e/30-design.spec.ts` › "no overflow at three breakpoints"
- [ ] **3.8** Accessibility: visible focus rings, aria-labels on icon buttons, Escape closes overlays, readable contrast on glass — `e2e/30-design.spec.ts` › "keyboard and aria basics"
- [ ] **3.9** Phase 3 boxes ticked, commit + push — "Phase 3: dark-glass minimalist redesign"

## Phase 4 — Full regression, docs, ship

- [ ] **4.1** Full regression suite ported to `e2e/40-regression.spec.ts` (the 45-check flow updated to the new UI; acknowledge runs last) — entire `npm run test:e2e` green
- [ ] **4.2** Whole-repo gates: backend `unittest`, `npm run lint`, `npm test`, `npm run build` all green
- [ ] **4.3** Docs sync: this file fully ticked (except 1.8 owner action), bug statuses updated in `docs/bugs.md`, design system documented in `docs/application.md`, new decisions in `docs/decisions.md`
- [ ] **4.4** Final commit + push — GitHub Actions CI green

---

## Status log

| Date | Event |
| --- | --- |
| 2026-09-07 | Plan created; Phase 0 started |
| 2026-09-07 | Phase 0 complete — harness green (2/2 smoke tests) |

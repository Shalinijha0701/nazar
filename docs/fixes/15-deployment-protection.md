# Fix BUG-8 — Public demo blocked by Vercel Deployment Protection (owner runbook)

**Severity:** Critical for the demo's purpose · **Status:** Manual — requires the Vercel account owner; cannot be fixed from the repository.

## Problem

The README's live-demo link (`https://nazar-8lczelyeh-shalinijha1008s-projects.vercel.app/`) redirects to `vercel.com/login`. Vercel **Deployment Protection (Vercel Authentication)** is enabled on the dashboard project, so only members of the Vercel team can open the page. Judges, recruiters, or anyone else hitting the link sees a Vercel login wall — verified with a real browser (Playwright): HTTP 200 → client redirect to the SSO login.

The API project is *not* affected (`backend-plum-mu-21.vercel.app` responds publicly).

## Fix (5 minutes, Vercel dashboard)

1. Log in to Vercel and open the **dashboard project** (the Next.js one, root of this repo).
2. **Settings → Deployment Protection**.
3. Under **Vercel Authentication**, switch from "Standard Protection" (or "All Deployments") to **Disabled** — or, if you want previews protected, choose **Only Preview Deployments** so Production stays public.
4. Save. No redeploy needed; the change is immediate.

## Then fix the link

The URL in the README is a *deployment/team-scoped* URL (`…-projects.vercel.app`), which is the most protection-prone form. Prefer the project's **production domain**:

1. Project → **Settings → Domains** — note the `<project>.vercel.app` production domain (or add a custom one).
2. Update `README.md` (two places: the "Live demo" link at the top and the "Hackathon demo flow" step 1) to that production URL.

## Verify

From a logged-out/private browser window (or `curl -sI <url>`):

- The dashboard URL returns the app (HTTP 200 with the Nazar page, no redirect to `vercel.com`).
- The demo flow works end to end: cards load, "Mark reviewed" succeeds.

Optional: re-run the e2e check used to catch this — a Playwright `page.goto(<url>)` asserting the final URL does not contain `vercel.com/login`.

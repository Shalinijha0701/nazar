# Fix G10 — Hardcoded deployment URLs committed to the repository

**Severity:** Medium · **Status:** Partially fixed (CORS default cleaned; `vercel.json` rewrite is a deployment setting)

## Problem

Deployment-specific URLs were baked into source:

1. `backend/app/config.py` shipped a personal Vercel preview URL as a **default**:

   ```python
   allowed_origins: str = (
       "http://localhost:3000,"
       "https://nazar-8lczelyeh-shalinijha1008s-projects.vercel.app"
   )
   ```

   Consequences: every fork/deployment of this code silently grants CORS to that stranger's origin; rotating the deployment URL requires a code change; and preview-deployment URLs are unstable by design.

2. `vercel.json` proxies the dashboard's `/api/*` to a hardcoded personal backend:

   ```json
   "destination": "https://backend-plum-mu-21.vercel.app/api/:path*"
   ```

   Anyone deploying the repo unknowingly ships their users' traffic to that backend.

## Implemented

`config.py` now defaults to localhost only:

```python
allowed_origins: str = "http://localhost:3000"
```

Deployed origins belong in the environment (`NAZAR_ALLOWED_ORIGINS`), which the README and `backend/.env.example` already document:

```text
NAZAR_ALLOWED_ORIGINS=http://localhost:3000,https://<your-dashboard>.vercel.app
```

**Deployment action required:** the existing Vercel API project must set `NAZAR_ALLOWED_ORIGINS` to include the dashboard origin, otherwise the deployed dashboard will hit CORS failures after this change. (It very likely already does per the README deployment steps; verify before shipping.)

## Guide — the `vercel.json` rewrite

Vercel does not substitute env vars inside `vercel.json`, so choose one of:

**Option A (recommended): move the rewrite into `next.config.ts`,** which *does* run at build time and can read env:

```ts
// next.config.ts
import type { NextConfig } from "next";

const backendOrigin = process.env.BACKEND_ORIGIN; // set in Vercel project env

const nextConfig: NextConfig = {
  async rewrites() {
    if (!backendOrigin) return [];
    return [
      { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` },
    ];
  },
};

export default nextConfig;
```

Then delete the `rewrites` block from `vercel.json` and set `BACKEND_ORIGIN` in the dashboard project's Vercel environment. Local dev is unaffected: `NEXT_PUBLIC_API_BASE=http://localhost:8000` already routes calls directly (`lib/nazar/use-catchup.ts` prefixes it), bypassing rewrites.

**Option B: drop the proxy entirely** and always call the API cross-origin via `NEXT_PUBLIC_API_BASE` set to the deployed API URL. Simpler (one mechanism for dev and prod), at the cost of exposing the API origin to the browser and requiring correct CORS (which the backend supports).

Either way, no personal URL remains in git.

## Verification

- `git grep -n "vercel.app" -- ':!README.md' ':!GAPS.md' ':!docs'` returns nothing (README keeps the demo link, which is fine — it is documentation, not configuration).
- Local: backend + `npm run dev` still work (localhost origin default).
- Deployed: dashboard loads data with `NAZAR_ALLOWED_ORIGINS` (and `BACKEND_ORIGIN`, if Option A) set in Vercel.

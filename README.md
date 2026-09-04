# Nazar

Nazar is a smart market watchlist that explains what changed while a user was away. It treats personal rules, sector-relative surprise, and intraday path events as independent signals, so every alert has a clear reason instead of an opaque score.

## Product model

- **Personal rule:** detects a price crossing or unusual same-time-of-day volume pace.
- **Sector surprise:** ranks the stock's sector-relative return against its own historical distribution.
- **Path event:** preserves a rare spike or reversal even when the closing price hides it.
- **Review watermark:** advances only after a successful catch-up and explicit acknowledgement.
- **Data quality:** keeps stale, closed-market, and limited-history states separate from ranked attention.

The replay feed is deterministic and uses the same signal functions as the API. It is the recommended judging mode because it works outside market hours and does not require private credentials.

## Architecture

```text
Next.js dashboard
       │
       ▼
FastAPI modular monolith
       ├── watchlist and rule repository
       ├── signal engine
       └── market-data provider interface
              ├── replay provider
              └── Groww provider
       │
       ▼
PostgreSQL / Supabase
```

Shared market evidence is computed per symbol. Per-user state contains only watchlist membership, personal rules, and the monotonic `reviewed_through` watermark.

## Repository layout

```text
app/                    Next.js application
components/nazar/       Product UI
lib/nazar/              Typed API mapping and replay projection
backend/app/            FastAPI application and signal engine
backend/main.py         Vercel entry point
backend/tests/          Unit and API integration tests
supabase/schema.sql     PostgreSQL schema, indexes, RLS, and acknowledgement RPC
docs/functional-spec.md Frozen formulas, edge cases, and golden cases
```

## Local setup

Requirements: Node.js 22 and Python 3.12.

Start the API:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

Start the dashboard in a second terminal:

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The default token is intentionally limited to local replay mode.

## Configuration

Backend variables use the `NAZAR_` prefix.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NAZAR_MARKET_PROVIDER` | `replay` | `replay` or `groww` |
| `NAZAR_PERSISTENCE_BACKEND` | `memory` | `memory` or `supabase` |
| `NAZAR_AUTH_MODE` | `demo` | `demo` or `supabase` |
| `NAZAR_DEMO_TOKEN` | `demo-token` | Replay-only bearer token |
| `NAZAR_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |
| `NAZAR_GROWW_ACCESS_TOKEN` | — | Required for the Groww provider |
| `NAZAR_SUPABASE_URL` | — | Required for Supabase modes |
| `NAZAR_SUPABASE_SERVICE_ROLE_KEY` | — | Server-only key; never expose in Next.js |

Frontend variables:

| Variable | Example |
| --- | --- |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` |
| `NEXT_PUBLIC_DEMO_TOKEN` | `demo-token` |

## Verification

```bash
npm run lint
npm test
npm run build

cd backend
python -m unittest discover -s tests -v
```

The backend suite includes deterministic formula tests and full API tests for authentication, grouping, rule creation, item removal, and monotonic acknowledgement.

After one-minute candles have been ingested into Supabase, rebuild stored distributions with:

```bash
cd backend
python -m app.jobs.rebuild_distributions --symbol RELIANCE --sector NIFTY50
```

## Deployment

Deploy two Vercel projects from this repository:

1. **Dashboard:** repository root, Next.js preset. Set `NEXT_PUBLIC_API_BASE` to the API deployment URL and `NEXT_PUBLIC_DEMO_TOKEN` to the same demo token used by the API.
2. **API:** set the project Root Directory to `backend`. Configure the `NAZAR_*` variables and add the dashboard origin to `NAZAR_ALLOWED_ORIGINS`.

For persistent multi-user operation, apply `supabase/schema.sql`, enable Supabase persistence and authentication together, and keep the service-role key only in the API environment. The included Groww adapter supports live price-rule evaluation. Sector and path statistics remain disabled in live mode until historical distributions have been populated; the UI reports this as limited history instead of fabricating evidence.

## Deliberate scope

- No prediction, recommendation, sentiment model, or combined weighted score.
- Replay mode is complete and presentation-ready.
- Live Groww price rules and an on-demand historical-distribution rebuild job are implemented; production scheduling is deployment-specific.
- Split and bonus adjustments are represented in the schema. Other corporate-action intervals pause statistical scoring.
- The application is an engineering prototype, not investment advice.

## 100-word pitch

Nazar is a market watchlist that remembers what happened while you were away. Instead of ranking every price move, it surfaces three independent, explainable signals: a personal price or volume rule, a historically rare sector-relative move, and a spike or reversal that disappeared before you returned. Each alert carries its timestamp, comparison horizon, observation count, and data-quality state. Review watermarks advance only after acknowledgement and remain monotonic across devices. Shared market evidence is computed once per symbol, while stale data and corporate actions are isolated from ranking. The result is a focused catch-up, not another noisy watchlist or prediction engine.

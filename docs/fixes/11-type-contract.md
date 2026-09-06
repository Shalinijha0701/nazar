# Fix G12 — Hand-duplicated API types and the `saveRule` item-id bug

**Severity:** Medium · **Status:** Partially fixed (`saveRule` bug fixed; OpenAPI codegen is guide only)

## Problems

1. **Duplicated contract.** The TypeScript shapes in `lib/nazar/catchup-mapper.ts` (`CatchupCard`, `CatchupResponse`, `CatchupSignal`) are hand-written mirrors of the pydantic models in `backend/app/models.py`. Nothing enforces they stay in sync — adding a field or changing a nullable on one side silently breaks the other at runtime, not at build time.

2. **`saveRule` fallback bug.** `app/nazar-dashboard.tsx` posted rules to:

   ```ts
   await nazarApi(`/api/watchlists/items/${ruleStock.itemId ?? ruleStock.symbol}/rules`, ...)
   ```

   When a card had no `itemId` (possible for `item_id: null` in the payload — the model allows it), the request used the **symbol** as an item id, which the backend can never resolve → guaranteed 404 presented as "Could not save rule" with no hint. Dead code path pretending to be a fallback.

## Implemented — `saveRule` gating

The fallback is gone; the rule dialog can only be opened for stocks that have a real item id, and `saveRule` guards explicitly:

```ts
async function saveRule() {
    if (!ruleStock?.itemId) {
      toast.error("This stock cannot accept rules yet", {
        description: "It has no watchlist item id from the backend.",
      });
      return;
    }
    ...
    await nazarApi(`/api/watchlists/items/${encodeURIComponent(ruleStock.itemId)}/rules`, ...
```

and the per-card "Add rule" affordance is disabled when `itemId` is missing.

## Guide — generate the client types from OpenAPI

FastAPI publishes the schema for free at `/openapi.json`. Use [`openapi-typescript`](https://github.com/openapi-ts/openapi-typescript) to turn it into the single source of truth:

1. Install and script it:

   ```bash
   npm install --save-dev openapi-typescript
   ```

   ```jsonc
   // package.json scripts
   "generate:api": "openapi-typescript http://localhost:8000/openapi.json -o lib/nazar/api-schema.d.ts"
   ```

2. Make the response models explicit so the schema is complete. The endpoints currently return `-> dict`, which OpenAPI types as a free-form object. Declare them:

   ```python
   @app.get("/api/watchlists/me/catchup", response_model=CatchupResponse)
   async def catchup(...) -> CatchupResponse: ...
   ```

   (`CatchupResponse` already exists in `backend/app/models.py`; returning the model instead of `model_dump(mode="json")` lets FastAPI serialize it and document it.)

3. Replace the hand-written types:

   ```ts
   // lib/nazar/catchup-mapper.ts
   import type { components } from "./api-schema";

   export type CatchupResponse = components["schemas"]["CatchupResponse"];
   export type CatchupCard = components["schemas"]["CatchupCard"];
   export type CatchupSignal = components["schemas"]["Signal"];
   ```

   The mapper (`mapCatchupResponse`) keeps working; only the type declarations change.

4. Guard against drift in CI: regenerate and diff.

   ```yaml
   # .github/workflows/ci.yml — after starting the backend
   - run: pip install -r backend/requirements.txt
   - run: python -c "import json; from app.main import create_app; print(json.dumps(create_app().openapi()))" > openapi.json
     working-directory: backend
   - run: npx openapi-typescript backend/openapi.json -o lib/nazar/api-schema.d.ts
   - run: git diff --exit-code lib/nazar/api-schema.d.ts
   ```

   Note the schema can be generated without running a server, as shown — `create_app().openapi()` is pure.

## Verification

- After codegen: `npm run build` fails if a backend model change is not reflected in the frontend (that is the feature).
- The `saveRule` fix: with a card lacking `itemId`, the rule action is disabled/toasts immediately instead of firing a doomed request (visible in devtools network tab: no POST occurs).

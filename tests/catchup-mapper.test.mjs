import assert from "node:assert/strict";
import test from "node:test";

import { mapCatchupResponse } from "../lib/nazar/catchup-mapper.ts";


const response = {
  watchlist_id: "primary",
  source: "replay",
  reviewed_through: "2026-09-04T05:45:00Z",
  evaluated_through: "2026-09-04T06:15:00Z",
  trading_minutes: 30,
  horizon_minutes: 60,
  coverage: "full",
  counts: { attention: 1, normal: 0, data_unavailable: 0 },
  attention: [
    {
      item_id: "primary:RELIANCE",
      symbol: "RELIANCE",
      company_name: "Reliance Industries",
      sector_index: "NIFTY50",
      current_price: 102,
      baseline_price: 100,
      change_since_review_percent: 2,
      data_state: "fresh",
      last_updated_at: "2026-09-04T06:15:00Z",
      narrative: "Unusual move",
      chart: [
        { timestamp: "2026-09-04T05:45:00Z", price: 100 },
        { timestamp: "2026-09-04T06:00:00Z", price: 101 },
        { timestamp: "2026-09-04T06:15:00Z", price: 102 },
      ],
      signals: [
        {
          kind: "sector_surprise",
          label: "97.6th percentile relative to sector",
          occurred_at: "2026-09-04T06:00:00Z",
          percentile: 97.6,
          observation_count: 252,
          direction: "above_sector",
          evidence: { horizon_minutes: 60 },
        },
      ],
    },
  ],
  normal: [],
  data_unavailable: [],
};


test("API evidence is preserved without hardcoded UI values", () => {
  const [stock] = mapCatchupResponse(response);

  assert.equal(stock.itemId, "primary:RELIANCE");
  assert.deepEqual(stock.series, [100, 101, 102]);
  assert.equal(stock.signals[0].percentile, 97.6);
  assert.equal(stock.signals[0].observationCount, 252);
  assert.equal(stock.signals[0].triggerIndex, 1);
  assert.match(stock.signals[0].detail, /97\.6th percentile across 252 observations/);
});

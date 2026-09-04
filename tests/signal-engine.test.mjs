import assert from "node:assert/strict";
import test from "node:test";

import { formatChange, projectStock } from "../lib/nazar/signal-engine.ts";


const stock = {
  symbol: "TEST",
  company: "Test Limited",
  sector: "Technology",
  sectorIndex: "NIFTY IT",
  baseline: 100,
  series: [100, 102, 101],
  times: ["11:15", "11:30", "11:45"],
  dataState: "fresh",
  lastUpdated: "11:45",
  signals: [
    {
      id: "late-signal",
      kind: "path_event",
      label: "Reversal",
      detail: "Observed in interval",
      tone: "amber",
      triggerIndex: 2,
    },
  ],
  narrative: "Test interval",
};


test("projectStock reveals signals only after their event", () => {
  const before = projectStock(stock, 1);
  const after = projectStock(stock, 2);

  assert.equal(before.visibleSignals.length, 0);
  assert.equal(before.group, "normal");
  assert.equal(after.visibleSignals.length, 1);
  assert.equal(after.group, "attention");
});


test("projectStock safely handles a zero baseline", () => {
  const projected = projectStock({ ...stock, baseline: 0 }, 2);
  assert.equal(projected.changePercent, 0);
});


test("formatChange preserves direction", () => {
  assert.equal(formatChange(1.25), "+1.25%");
  assert.equal(formatChange(-0.5), "-0.50%");
});

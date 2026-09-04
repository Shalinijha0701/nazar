import type { DisplayStock, StockRecord } from "./types";

export function projectStock(stock: StockRecord, replayIndex: number): DisplayStock {
  const boundedIndex = Math.max(0, Math.min(replayIndex, stock.series.length - 1));
  const currentPrice = stock.series[boundedIndex];
  const changePercent = stock.baseline > 0
    ? ((currentPrice - stock.baseline) / stock.baseline) * 100
    : 0;
  const visibleSignals = stock.signals.filter(
    (signal) => signal.triggerIndex <= boundedIndex,
  );

  const group =
    stock.dataState === "unavailable"
      ? "unavailable"
      : visibleSignals.length > 0
        ? "attention"
        : "normal";

  return {
    ...stock,
    currentPrice,
    changePercent,
    visibleSignals,
    group,
  };
}

export function formatPrice(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatChange(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

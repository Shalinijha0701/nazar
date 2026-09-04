import type { DataState, Signal, StockRecord } from "./types";

export type CatchupSignal = {
  kind: Signal["kind"];
  label: string;
  occurred_at?: string | null;
  percentile?: number | null;
  observation_count?: number | null;
  direction?: string | null;
  evidence?: Record<string, number | string | boolean | null>;
};

export type CatchupCard = {
  item_id?: string | null;
  symbol: string;
  company_name: string;
  sector_index: string;
  current_price: number | null;
  baseline_price: number | null;
  change_since_review_percent: number | null;
  data_state: DataState;
  last_updated_at: string | null;
  narrative: string;
  chart: Array<{ timestamp: string; price: number }>;
  signals: CatchupSignal[];
};

export type CatchupResponse = {
  watchlist_id: string;
  source: "replay" | "groww";
  reviewed_through: string;
  evaluated_through: string;
  trading_minutes: number;
  horizon_minutes: number | null;
  coverage: string;
  counts: Record<string, number>;
  attention: CatchupCard[];
  normal: CatchupCard[];
  data_unavailable: CatchupCard[];
};

function formatTime(value: string | null) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function findTriggerIndex(signal: CatchupSignal, timestamps: string[]) {
  if (!signal.occurred_at || timestamps.length === 0) return Math.max(0, timestamps.length - 1);
  const occurred = new Date(signal.occurred_at).getTime();
  const index = timestamps.findIndex((timestamp) => new Date(timestamp).getTime() >= occurred);
  return index >= 0 ? index : timestamps.length - 1;
}

function signalDetail(signal: CatchupSignal) {
  const evidence = signal.evidence ?? {};
  if (signal.kind === "path_event" && typeof evidence.magnitude_percent === "number") {
    const peak = typeof evidence.peak_price === "number"
      ? "Peak ₹" + evidence.peak_price.toLocaleString("en-IN") + " · "
      : "";
    return peak + evidence.magnitude_percent.toFixed(2) + "% move · "
      + (signal.percentile?.toFixed(1) ?? "—") + "th percentile across "
      + (signal.observation_count ?? "available") + " observations";
  }
  if (signal.kind === "sector_surprise" && typeof evidence.deviation_percent === "number") {
    const relation = signal.direction === "below_sector" ? "below" : "above";
    return Math.abs(evidence.deviation_percent).toFixed(2) + "% " + relation
      + " sector · " + (signal.percentile?.toFixed(1) ?? "—") + "th percentile across "
      + (signal.observation_count ?? "available") + " observations";
  }
  if (signal.kind === "personal_rule" && typeof evidence.volume_pace === "number") {
    return evidence.volume_pace.toFixed(2) + "× same-time volume pace across "
      + (evidence.comparison_sessions ?? "available") + " sessions";
  }
  if (signal.percentile != null) {
    const observations = signal.observation_count
      ? " across " + signal.observation_count + " observations"
      : "";
    return signal.percentile.toFixed(1) + "th percentile" + observations;
  }
  if (signal.occurred_at) return "First confirmed at " + formatTime(signal.occurred_at) + " IST";
  return "Confirmed from fresh interval data";
}

export function mapCatchupResponse(data: CatchupResponse): StockRecord[] {
  const cards = [...data.attention, ...data.normal, ...data.data_unavailable];
  return cards.map((card) => {
    const timestamps = card.chart.map((point) => point.timestamp);
    const series = card.chart.length
      ? card.chart.map((point) => point.price)
      : [card.baseline_price ?? card.current_price ?? 1];
    const times = card.chart.length
      ? timestamps.map((timestamp) => formatTime(timestamp))
      : ["Unknown"];
    const baseline = card.baseline_price ?? series[0] ?? 1;

    return {
      itemId: card.item_id ?? undefined,
      symbol: card.symbol,
      company: card.company_name,
      sector: "Tracked security",
      sectorIndex: card.sector_index.replaceAll("_", " "),
      baseline,
      series,
      times,
      dataState: card.data_state,
      lastUpdated: formatTime(card.last_updated_at),
      signals: card.signals.map((signal, index) => ({
        id: card.symbol + "-" + signal.kind + "-" + index,
        kind: signal.kind,
        label: signal.label,
        detail: signalDetail(signal),
        tone: signal.kind === "personal_rule"
          ? "violet"
          : signal.kind === "sector_surprise"
            ? "blue"
            : "amber",
        triggerIndex: findTriggerIndex(signal, timestamps),
        occurredAt: signal.occurred_at,
        percentile: signal.percentile,
        observationCount: signal.observation_count,
        direction: signal.direction,
      })),
      narrative: card.narrative,
      source: data.source,
    };
  });
}

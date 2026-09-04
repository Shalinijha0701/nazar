export type SignalKind = "personal_rule" | "sector_surprise" | "path_event";

export type DataState = "fresh" | "market_closed" | "unavailable" | "limited_history";

export type Signal = {
  id: string;
  kind: SignalKind;
  label: string;
  detail: string;
  tone: "violet" | "blue" | "amber";
  triggerIndex: number;
  occurredAt?: string | null;
  percentile?: number | null;
  observationCount?: number | null;
  direction?: string | null;
};

export type StockRecord = {
  itemId?: string;
  symbol: string;
  company: string;
  sector: string;
  sectorIndex: string;
  baseline: number;
  series: number[];
  times: string[];
  dataState: DataState;
  lastUpdated: string;
  signals: Signal[];
  narrative: string;
  source?: "replay" | "groww";
};

export type WatchlistGroup = "attention" | "normal" | "unavailable";

export type DisplayStock = StockRecord & {
  currentPrice: number;
  changePercent: number;
  visibleSignals: Signal[];
  group: WatchlistGroup;
};

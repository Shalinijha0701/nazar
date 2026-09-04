export type SignalKind = "personal_rule" | "sector_surprise" | "path_event";

export type DataState = "fresh" | "market_closed" | "unavailable";

export type Signal = {
  id: string;
  kind: SignalKind;
  label: string;
  detail: string;
  tone: "violet" | "blue" | "amber";
  triggerIndex: number;
};

export type StockRecord = {
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
};

export type WatchlistGroup = "attention" | "normal" | "unavailable";

export type DisplayStock = StockRecord & {
  currentPrice: number;
  changePercent: number;
  visibleSignals: Signal[];
  group: WatchlistGroup;
};

"use client";

import { useEffect, useState } from "react";

import { demoStocks } from "./demo-data";
import type { DataState, Signal, StockRecord } from "./types";

type CatchupSignal = {
  kind: Signal["kind"];
  label: string;
  occurred_at?: string | null;
  percentile?: number | null;
  evidence?: Record<string, number | string>;
};

type CatchupCard = {
  symbol: string;
  company_name: string;
  current_price: number | null;
  change_since_review_percent: number | null;
  data_state: DataState;
  last_updated_at: string | null;
  signals: CatchupSignal[];
};

export type CatchupResponse = {
  watchlist_id: string;
  reviewed_through: string;
  evaluated_through: string;
  counts: Record<string, number>;
  attention: CatchupCard[];
  normal: CatchupCard[];
  data_unavailable: CatchupCard[];
};

const apiBase = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

export function mapCatchupResponseToStockRecords(data: CatchupResponse): StockRecord[] {
  const cards = [...data.attention, ...data.normal, ...data.data_unavailable];
  return cards.map((card) => {
    const fallback = demoStocks.find((stock) => stock.symbol === card.symbol);
    const baseline = fallback?.baseline ?? card.current_price ?? 0;
    const current = card.current_price ?? baseline;
    const series = fallback?.series ?? [baseline, current];
    const nextSeries = [...series];
    nextSeries[nextSeries.length - 1] = current;

    return {
      symbol: card.symbol,
      company: card.company_name,
      sector: fallback?.sector ?? card.symbol,
      sectorIndex: fallback?.sectorIndex ?? "NIFTY 50",
      baseline,
      series: nextSeries,
      times: fallback?.times ?? ["Review", "Now"],
      dataState: card.data_state,
      lastUpdated: card.last_updated_at ? new Date(card.last_updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Unknown",
      signals: card.signals.map((signal, index) => ({
        id: `${card.symbol}-${signal.kind}-${index}`,
        kind: signal.kind,
        label: signal.label,
        detail: signal.percentile != null
          ? `${signal.percentile.toFixed(1)}th percentile${signal.evidence?.observation_count ? ` across ${signal.evidence.observation_count} observations` : ""}`
          : "Confirmed from the backend signal pipeline",
        tone: signal.kind === "personal_rule" ? "violet" : signal.kind === "sector_surprise" ? "blue" : "amber",
        triggerIndex: fallback?.signals.find((item) => item.kind === signal.kind)?.triggerIndex ?? nextSeries.length - 1,
      })),
      narrative: fallback?.narrative ?? "The backend returned this watchlist observation.",
    };
  });
}

export function useCatchup(watchlistId = "primary") {
  const [data, setData] = useState<CatchupResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${apiBase}/api/watchlists/me/catchup?watchlist_id=${encodeURIComponent(watchlistId)}`, {
      headers: { Authorization: "Bearer demo-token" },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("backend unavailable");
        return response.json() as Promise<CatchupResponse>;
      })
      .then(setData)
      .catch((cause: Error) => {
        if (cause.name !== "AbortError") setError(cause.message);
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [watchlistId]);

  return { data, error, loading };
}

export async function nazarApi(path: string, init?: RequestInit) {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      Authorization: "Bearer demo-token",
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? "Nazar API request failed");
  return response.json();
}

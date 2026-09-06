"use client";

import { useCallback, useEffect, useState } from "react";

import type { CatchupResponse } from "./catchup-mapper";


const apiBase = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");
const demoToken = process.env.NEXT_PUBLIC_DEMO_TOKEN ?? "demo-token";


export function apiErrorMessage(payload: unknown, fallback: string): string {
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((entry) => (entry && typeof entry === "object" && typeof (entry as { msg?: unknown }).msg === "string"
        ? (entry as { msg: string }).msg
        : null))
      .filter((msg): msg is string => msg !== null);
    if (messages.length > 0) return messages.join("; ");
  }
  return fallback;
}


export function useCatchup(watchlistId?: string | null) {
  const [data, setData] = useState<CatchupResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [requestVersion, setRequestVersion] = useState(0);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    setRequestVersion((version) => version + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const query = watchlistId ? "?watchlist_id=" + encodeURIComponent(watchlistId) : "";
    fetch(apiBase + "/api/watchlists/me/catchup" + query, {
      headers: { Authorization: "Bearer " + demoToken },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json().catch(() => null);
          throw new Error(apiErrorMessage(payload, "Backend unavailable"));
        }
        return response.json() as Promise<CatchupResponse>;
      })
      .then(setData)
      .catch((cause: Error) => {
        if (cause.name !== "AbortError") setError(cause.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [requestVersion, watchlistId]);

  return { data, error, loading, refresh };
}


export async function nazarApi<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiBase + path, {
    ...init,
    headers: {
      Authorization: "Bearer " + demoToken,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(apiErrorMessage(payload, "Nazar API request failed"));
  }
  return response.json() as Promise<T>;
}

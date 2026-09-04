import { ArrowDownRight, ArrowUpRight, CircleAlert, ShieldCheck } from "lucide-react";

import { DataBadge } from "@/components/nazar/data-badge";
import { SignalBadge } from "@/components/nazar/signal-badge";
import { formatChange, formatPrice } from "@/lib/nazar/signal-engine";
import type { DisplayStock } from "@/lib/nazar/types";


type StockCardProps = {
  stock: DisplayStock;
  onInspect: (stock: DisplayStock) => void;
  onAddRule: (stock: DisplayStock) => void;
};

export function StockCard({ stock, onInspect, onAddRule }: StockCardProps) {
  const positive = stock.changePercent >= 0;

  return (
    <article className="group overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_10px_32px_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-[0_16px_42px_rgba(15,23,42,0.07)]">
      <button
        className="w-full p-5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-500"
        onClick={() => onInspect(stock)}
        aria-label={`Inspect ${stock.company}`}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-bold tracking-tight text-slate-950">{stock.symbol}</h3>
              <span className="text-xs font-medium text-slate-400">{stock.sectorIndex}</span>
            </div>
            <p className="mt-1 text-sm text-slate-500">{stock.company}</p>
          </div>
          <div className="text-right">
            <p className="text-base font-bold tabular-nums text-slate-950">
              {formatPrice(stock.currentPrice)}
            </p>
            <p className={`mt-1 inline-flex items-center text-sm font-semibold tabular-nums ${positive ? "text-emerald-600" : "text-rose-600"}`}>
              {positive ? <ArrowUpRight className="size-4" /> : <ArrowDownRight className="size-4" />}
              {formatChange(stock.changePercent)}
            </p>
          </div>
        </div>

        {stock.visibleSignals.length > 0 ? (
          <div className="mt-5 grid gap-2">
            {stock.visibleSignals.map((signal) => (
              <SignalBadge key={signal.id} signal={signal} />
            ))}
          </div>
        ) : (
          <div className="mt-5 flex items-center gap-2 rounded-xl bg-slate-50 px-3.5 py-3 text-sm text-slate-500">
            {stock.group === "unavailable" ? (
              <CircleAlert className="size-4 text-rose-500" />
            ) : (
              <ShieldCheck className="size-4 text-emerald-600" />
            )}
            {stock.group === "unavailable"
              ? "No new signals calculated from cached data"
              : "Movement remains inside its expected range"}
          </div>
        )}

        <div className="mt-4 flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-2">
            <DataBadge stock={stock} />
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-slate-400 sm:inline">
              Since Fri 11:15 IST
            </span>
            <span className="text-xs font-semibold text-slate-400 transition group-hover:text-slate-700">
              View evidence →
            </span>
          </div>
        </div>
      </button>

      {stock.group !== "unavailable" && (
        <div className="border-t border-slate-100 bg-slate-50/70 px-5 py-2.5">
          <button
            className="text-xs font-semibold text-slate-500 hover:text-violet-700"
            onClick={() => onAddRule(stock)}
          >
            + Add personal rule
          </button>
        </div>
      )}
    </article>
  );
}

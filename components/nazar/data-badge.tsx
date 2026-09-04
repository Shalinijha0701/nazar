import { Badge } from "@/components/ui/badge";
import type { DisplayStock } from "@/lib/nazar/types";


export function DataBadge({ stock }: { stock: DisplayStock }) {
  if (stock.dataState === "unavailable") {
    return (
      <Badge variant="outline" className="border-rose-200 bg-rose-50 text-rose-700">
        Unavailable · {stock.lastUpdated}
      </Badge>
    );
  }

  if (stock.dataState === "market_closed") {
    return (
      <Badge variant="outline" className="border-slate-200 bg-slate-50 text-slate-600">
        Market closed · {stock.lastUpdated}
      </Badge>
    );
  }

  if (stock.dataState === "limited_history") {
    return (
      <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
        Limited history
      </Badge>
    );
  }

  return (
    <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
      {stock.source === "replay" ? "Replay" : "Fresh"} · {stock.lastUpdated}
    </Badge>
  );
}

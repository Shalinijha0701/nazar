import { Badge } from "@/components/ui/badge";
import type { DisplayStock } from "@/lib/nazar/types";


export function DataBadge({ stock }: { stock: DisplayStock }) {
  if (stock.dataState === "unavailable") {
    return (
      <Badge variant="outline" className="border-rose-200 bg-rose-50 text-rose-700">
        Data unavailable
      </Badge>
    );
  }

  if (stock.dataState === "market_closed") {
    return (
      <Badge variant="outline" className="border-slate-200 bg-slate-50 text-slate-600">
        Market closed
      </Badge>
    );
  }

  return (
    <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
      Fresh · {stock.lastUpdated}
    </Badge>
  );
}

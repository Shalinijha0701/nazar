import { BarChart3, Target, Zap } from "lucide-react";

import type { Signal } from "@/lib/nazar/types";


function SignalIcon({ kind }: { kind: Signal["kind"] }) {
  if (kind === "personal_rule") return <Target />;
  if (kind === "sector_surprise") return <BarChart3 />;
  return <Zap />;
}

export function SignalBadge({ signal }: { signal: Signal }) {
  const tone = {
    violet: "border-violet-200 bg-violet-50 text-violet-800",
    blue: "border-sky-200 bg-sky-50 text-sky-800",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
  }[signal.tone];

  return (
    <div className={`flex items-start gap-3 rounded-xl border px-3.5 py-3 ${tone}`}>
      <span className="mt-0.5 [&_svg]:size-4">
        <SignalIcon kind={signal.kind} />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold leading-5">{signal.label}</p>
        <p className="mt-0.5 text-xs leading-5 opacity-75">{signal.detail}</p>
      </div>
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BellRing,
  ChevronDown,
  Database,
  Eye,
  Info,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  Target,
  Trash2,
} from "lucide-react";
import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
} from "recharts";
import { toast } from "sonner";

import { DataBadge } from "@/components/nazar/data-badge";
import { SignalBadge } from "@/components/nazar/signal-badge";
import { StockCard } from "@/components/nazar/stock-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Toaster } from "@/components/ui/sonner";
import { mapCatchupResponse } from "@/lib/nazar/catchup-mapper";
import { formatChange, formatPrice, projectStock } from "@/lib/nazar/signal-engine";
import { addableStocks } from "@/lib/nazar/stock-catalog";
import { nazarApi, useCatchup } from "@/lib/nazar/use-catchup";
import type { DisplayStock } from "@/lib/nazar/types";

export default function NazarDashboard() {
  const [requestedWatchlistId, setRequestedWatchlistId] = useState<string | null>(null);
  const { data: catchup, error: catchupError, loading, refresh } = useCatchup(requestedWatchlistId);
  const [replayPosition, setReplayPosition] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState("all");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [ruleStock, setRuleStock] = useState<DisplayStock | null>(null);
  const [ruleType, setRuleType] = useState("price_above");
  const [ruleValue, setRuleValue] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [noiseOpen, setNoiseOpen] = useState(false);

  const stocks = useMemo(
    () => catchup ? mapCatchupResponse(catchup) : [],
    [catchup],
  );
  const watchlistId = catchup?.watchlist_id ?? requestedWatchlistId ?? "primary";
  const maxReplayIndex = useMemo(
    () => Math.max(0, ...stocks.map((stock) => stock.series.length - 1)),
    [stocks],
  );

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setReplayPosition((current) => {
        const position = current ?? maxReplayIndex;
        if (position >= maxReplayIndex) {
          setPlaying(false);
          return position;
        }
        return position + 1;
      });
    }, 700);
    return () => window.clearInterval(timer);
  }, [maxReplayIndex, playing]);

  const replayIndex = replayPosition ?? maxReplayIndex;

  const projected = useMemo(
    () => stocks.map((stock) => projectStock(stock, replayIndex)),
    [stocks, replayIndex],
  );
  const selected = projected.find((stock) => stock.symbol === selectedSymbol) ?? null;

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return projected.filter((stock) => {
      const matchesQuery = !normalized || stock.symbol.toLowerCase().includes(normalized) || stock.company.toLowerCase().includes(normalized);
      const matchesTab = tab === "all" || stock.group === tab;
      return matchesQuery && matchesTab;
    });
  }, [projected, query, tab]);

  const groups = useMemo(() => ({
    attention: filtered.filter((stock) => stock.group === "attention"),
    normal: filtered.filter((stock) => stock.group === "normal"),
    unavailable: filtered.filter((stock) => stock.group === "unavailable"),
  }), [filtered]);

  const allCounts = useMemo(() => ({
    attention: projected.filter((stock) => stock.group === "attention").length,
    normal: projected.filter((stock) => stock.group === "normal").length,
    unavailable: projected.filter((stock) => stock.group === "unavailable").length,
  }), [projected]);

  const replayTime = stocks[0]?.times[Math.min(replayIndex, maxReplayIndex)] ?? "11:15";
  const surpriseSignal = selected?.visibleSignals.find(
    (signal) => signal.kind === "sector_surprise" && signal.percentile != null,
  );

  function resetReplay() {
    setPlaying(false);
    setReplayPosition(0);
    setReviewed(false);
    toast("Replay reset to your last review");
  }

  async function markReviewed() {
    if (!catchup) return;
    try {
      await nazarApi("/api/watchlists/me/acknowledge", {
        method: "POST",
        body: JSON.stringify({
          watchlist_id: watchlistId,
          evaluated_through: catchup.evaluated_through,
        }),
      });
      setPlaying(false);
      setReplayPosition(0);
      setReviewed(true);
      refresh();
      toast.success("Watchlist reviewed", {
        description: "The backend watermark moved after your acknowledgement.",
      });
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save review");
    }
  }

  async function addStock(symbol: string) {
    const candidate = addableStocks.find((item) => item.symbol === symbol);
    if (!candidate || stocks.some((stock) => stock.symbol === symbol)) return;
    try {
      let activeWatchlistId = catchup?.watchlist_id;
      if (!activeWatchlistId) {
        const created = await nazarApi<{ watchlist_id: string }>("/api/watchlists", {
          method: "POST",
          body: JSON.stringify({ name: "My watchlist" }),
        });
        const createdId = String(created.watchlist_id);
        activeWatchlistId = createdId;
        setRequestedWatchlistId(createdId);
      }
      if (!activeWatchlistId) throw new Error("Watchlist was not created");
      await nazarApi(`/api/watchlists/${activeWatchlistId}/items`, {
        method: "POST",
        body: JSON.stringify({
          symbol: candidate.symbol,
          company_name: candidate.company,
          sector_index: candidate.sectorIndex,
        }),
      });
      setAddOpen(false);
      refresh();
      toast.success(`${symbol} added`, { description: "Saved to your watchlist." });
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not add stock");
    }
  }

  async function saveRule() {
    if (!ruleStock || !ruleValue || Number.isNaN(Number(ruleValue))) {
      toast.error("Enter a valid threshold");
      return;
    }
    const value = Number(ruleValue);

    try {
      await nazarApi(`/api/watchlists/items/${ruleStock.itemId ?? ruleStock.symbol}/rules`, {
        method: "POST",
        body: JSON.stringify({ rule_type: ruleType, threshold: value }),
      });
      setRuleStock(null);
      setRuleValue("");
      refresh();
      toast.success("Rule saved", { description: "The backend recalculated this review interval." });
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save rule");
    }
  }

  async function removeStock(stock: DisplayStock) {
    if (!stock.itemId) return;
    try {
      await nazarApi(`/api/watchlists/items/${encodeURIComponent(stock.itemId)}`, {
        method: "DELETE",
      });
      setSelectedSymbol(null);
      refresh();
      toast.success(`${stock.symbol} removed`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove stock");
    }
  }

  const detailSeries = selected?.series.slice(0, replayIndex + 1).map((value, index) => ({
    time: selected.times[index],
    value,
  })) ?? [];

  return (
    <div className="min-h-screen bg-[#f4f6f8] text-slate-950">
      <Toaster position="top-right" richColors />

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[248px] flex-col border-r border-slate-200 bg-[#0b1020] text-white lg:flex">
        <div className="flex h-20 items-center gap-3 px-6">
          <div className="grid size-9 place-items-center rounded-xl bg-[#b8ff65] text-[#0b1020]"><Eye className="size-5" /></div>
          <div><p className="font-black tracking-tight">Nazar</p><p className="text-xs text-slate-400">Meaningful change</p></div>
        </div>
        <nav className="px-3">
          <button className="flex w-full items-center gap-3 rounded-xl bg-white/10 px-3 py-3 text-sm font-semibold"><Activity className="size-4 text-[#b8ff65]" /> Market catch-up</button>
          <button className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm text-slate-400 hover:bg-white/5 hover:text-white"><Target className="size-4" /> Personal rules</button>
          <button className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm text-slate-400 hover:bg-white/5 hover:text-white"><Database className="size-4" /> Data health</button>
        </nav>
        <div className="mt-7 px-6"><p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Your watchlist</p></div>
        <div className="mt-3 flex-1 overflow-y-auto px-3 pb-4">
          {projected.slice(0, 8).map((stock) => (
            <button key={stock.symbol} onClick={() => setSelectedSymbol(stock.symbol)} className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-slate-300 hover:bg-white/5">
              <span>{stock.symbol}</span>
              <span className={`size-1.5 rounded-full ${stock.group === "attention" ? "bg-[#b8ff65]" : stock.group === "unavailable" ? "bg-rose-400" : "bg-slate-600"}`} />
            </button>
          ))}
        </div>
        <div className="border-t border-white/10 p-4">
          <div className="rounded-xl bg-white/5 p-3"><p className="text-xs font-semibold">{catchup?.source === "groww" ? "Groww market feed" : "Recorded replay feed"}</p><p className="mt-1 text-xs leading-5 text-slate-400">Evidence is calculated by the API signal engine.</p></div>
        </div>
      </aside>

      <main className="lg:pl-[248px]">
        <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-[#f4f6f8]/90 backdrop-blur-xl">
          <div className="flex min-h-20 flex-wrap items-center justify-between gap-4 px-4 py-3 sm:px-7 lg:px-10">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-xl bg-[#0b1020] text-[#b8ff65] lg:hidden"><Eye className="size-5" /></div>
              <div>
                <h1 className="text-xl font-black tracking-[-0.03em]">Your market catch-up</h1>
                <p className="text-sm text-slate-500">Since your last review · {replayIndex * 15} trading minutes shown</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="hidden border-amber-200 bg-amber-50 text-amber-800 sm:inline-flex">{loading ? "Connecting" : catchupError ? "Backend unavailable" : catchup?.source === "replay" ? "Replay connected" : "Live connected"} · {replayTime} IST</Badge>
              <Button variant="outline" className="rounded-xl bg-white" onClick={() => setAddOpen(true)}><Plus /> Add stock</Button>
              <Button className="rounded-xl bg-[#0b1020] text-white hover:bg-[#1b2440]" onClick={markReviewed} disabled={reviewed || !catchup || loading}><ShieldCheck /> {reviewed ? "Reviewed" : "Mark reviewed"}</Button>
            </div>
          </div>
        </header>

        <div className="mx-auto max-w-[1460px] px-4 py-6 sm:px-7 lg:px-10 lg:py-8">
          {catchupError && <section className="mb-6 flex flex-col gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-900 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-bold">Market API is unavailable</p><p className="mt-1 text-sm text-rose-700">{catchupError}. Start the FastAPI service or check NEXT_PUBLIC_API_BASE.</p></div><Button variant="outline" className="border-rose-300 bg-white" onClick={refresh}>Retry</Button></section>}
          <section className="relative overflow-hidden rounded-3xl bg-[#111831] p-5 text-white shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:p-7">
            <div className="absolute -right-20 -top-24 size-72 rounded-full border border-[#b8ff65]/20" />
            <div className="absolute -right-8 -top-12 size-44 rounded-full border border-[#b8ff65]/30" />
            <div className="relative grid gap-6 xl:grid-cols-[1fr_420px] xl:items-end">
              <div>
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.17em] text-[#b8ff65]"><BellRing className="size-4" /> While you were away</div>
                <p className="mt-4 max-w-2xl text-2xl font-bold leading-tight tracking-[-0.03em] sm:text-3xl">
                  {allCounts.attention === 0 ? "Nothing needs your attention yet." : `${allCounts.attention} ${allCounts.attention === 1 ? "stock needs" : "stocks need"} attention—not because they moved, but because the move meant something.`}
                </p>
                <div className="mt-5 flex flex-wrap gap-2 text-sm">
                  <span className="rounded-full bg-[#b8ff65] px-3 py-1.5 font-bold text-[#0b1020]">{allCounts.attention} attention</span>
                  <span className="rounded-full bg-white/10 px-3 py-1.5 text-slate-200">{allCounts.normal} normal noise</span>
                  <span className="rounded-full bg-rose-400/15 px-3 py-1.5 text-rose-200">{allCounts.unavailable} unavailable</span>
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.07] p-4 backdrop-blur">
                <div className="flex items-center justify-between">
                  <div><p className="text-sm font-bold">Market interval replay</p><p className="text-xs text-slate-400">Drag through the interval</p></div>
                  <div className="flex gap-1">
                    <Button size="icon-sm" variant="ghost" className="text-white hover:bg-white/10 hover:text-white" onClick={resetReplay} aria-label="Reset replay"><RotateCcw /></Button>
                    <Button size="icon-sm" className="bg-[#b8ff65] text-[#0b1020] hover:bg-[#a8ef58]" onClick={() => setPlaying((value) => !value)} aria-label={playing ? "Pause replay" : "Play replay"}>{playing ? <Pause /> : <Play />}</Button>
                  </div>
                </div>
                <Slider className="mt-5" min={0} max={maxReplayIndex} step={1} value={[Math.min(replayIndex, maxReplayIndex)]} onValueChange={(value) => { setPlaying(false); setReplayPosition(value[0] ?? 0); }} />
                <div className="mt-3 flex items-center justify-between text-xs text-slate-400"><span>Last reviewed · 11:15</span><span className="font-bold text-white">{replayTime} IST</span></div>
              </div>
            </div>
          </section>

          <section className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="h-11 rounded-xl bg-white p-1 shadow-sm" variant="default">
                <TabsTrigger value="all" className="rounded-lg px-4">All</TabsTrigger>
                <TabsTrigger value="attention" className="rounded-lg px-4">Attention</TabsTrigger>
                <TabsTrigger value="normal" className="rounded-lg px-4">Normal</TabsTrigger>
                <TabsTrigger value="unavailable" className="rounded-lg px-4">Unavailable</TabsTrigger>
              </TabsList>
            </Tabs>
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search this watchlist" className="h-11 rounded-xl border-slate-200 bg-white pl-9" />
            </div>
          </section>

          {groups.attention.length > 0 && (
            <section className="mt-7">
              <div className="mb-4 flex items-end justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-violet-600">Needs attention</p><h2 className="mt-1 text-xl font-black tracking-tight">Signals with evidence</h2></div><p className="hidden text-sm text-slate-500 sm:block">No predictions. No combined score.</p></div>
              <div className="grid gap-4 xl:grid-cols-2">{groups.attention.map((stock) => <StockCard key={stock.symbol} stock={stock} onInspect={(item) => setSelectedSymbol(item.symbol)} onAddRule={setRuleStock} />)}</div>
            </section>
          )}

          {groups.normal.length > 0 && (
            <Collapsible open={noiseOpen} onOpenChange={setNoiseOpen} className="mt-8 rounded-2xl border border-slate-200 bg-white">
              <CollapsibleTrigger className="flex w-full items-center justify-between p-5 text-left">
                <div><p className="text-xs font-bold uppercase tracking-[0.16em] text-slate-400">Normal noise</p><p className="mt-1 font-bold">{groups.normal.length} stocks moved inside their expected range</p></div>
                <ChevronDown className={`size-5 text-slate-400 transition ${noiseOpen ? "rotate-180" : ""}`} />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="grid gap-4 border-t border-slate-100 p-4 xl:grid-cols-2">{groups.normal.map((stock) => <StockCard key={stock.symbol} stock={stock} onInspect={(item) => setSelectedSymbol(item.symbol)} onAddRule={setRuleStock} />)}</div>
              </CollapsibleContent>
            </Collapsible>
          )}

          {groups.unavailable.length > 0 && (
            <section className="mt-8">
              <div className="mb-4"><p className="text-xs font-bold uppercase tracking-[0.16em] text-rose-600">Data unavailable</p><h2 className="mt-1 text-xl font-black tracking-tight">Separated from live attention</h2></div>
              <div className="grid gap-4 xl:grid-cols-2">{groups.unavailable.map((stock) => <StockCard key={stock.symbol} stock={stock} onInspect={(item) => setSelectedSymbol(item.symbol)} onAddRule={setRuleStock} />)}</div>
            </section>
          )}

          {filtered.length === 0 && <div className="mt-10 rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center"><Search className="mx-auto size-6 text-slate-400" /><p className="mt-3 font-bold">No matching stocks</p><p className="mt-1 text-sm text-slate-500">Try a symbol or company name.</p></div>}
        </div>
      </main>

      <Sheet open={!!selected} onOpenChange={(open) => !open && setSelectedSymbol(null)}>
        <SheetContent className="w-full overflow-y-auto border-slate-200 bg-white sm:max-w-xl">
          {selected && (
            <>
              <SheetHeader className="border-b border-slate-100 p-6 pr-12">
                <div className="flex items-center gap-2"><Badge variant="outline">{selected.sectorIndex}</Badge><DataBadge stock={selected} /></div>
                <SheetTitle className="mt-3 text-2xl font-black tracking-tight">{selected.symbol} · {formatPrice(selected.currentPrice)}</SheetTitle>
                <SheetDescription>{selected.company} · {formatChange(selected.changePercent)} since your last review</SheetDescription>
              </SheetHeader>
              <div className="p-6">
                <div className="h-60 rounded-2xl bg-[#0f1730] p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={detailSeries} margin={{ top: 12, right: 8, left: 8, bottom: 0 }}>
                      <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: "#94a3b8", fontSize: 11 }} interval="preserveStartEnd" />
                      <ChartTooltip contentStyle={{ background: "#fff", border: 0, borderRadius: 12, color: "#0f172a" }} formatter={(value) => [formatPrice(Number(value)), "Price"]} />
                      <ReferenceLine y={selected.baseline} stroke="#64748b" strokeDasharray="4 4" />
                      <Line type="monotone" dataKey="value" stroke="#b8ff65" strokeWidth={3} dot={false} activeDot={{ r: 5, fill: "#b8ff65" }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-6 rounded-2xl border border-slate-200 p-4"><div className="flex items-center gap-2 text-sm font-bold"><Info className="size-4 text-violet-600" /> What happened</div><p className="mt-2 text-sm leading-6 text-slate-600">{selected.narrative}</p></div>
                <div className="mt-6"><h3 className="text-sm font-black uppercase tracking-[0.12em] text-slate-400">Evidence receipt</h3><div className="mt-3 grid gap-2">{selected.visibleSignals.length ? selected.visibleSignals.map((signal) => <SignalBadge key={signal.id} signal={signal} />) : <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">No signal crossed its visible threshold in this interval.</div>}</div></div>
                {surpriseSignal?.percentile != null && <div className="mt-6 rounded-2xl border border-slate-200 p-4"><div className="flex items-center justify-between text-sm"><span className="font-semibold">Historical surprise percentile</span><span className="font-black">{surpriseSignal.percentile.toFixed(1)}%</span></div><Progress value={surpriseSignal.percentile} className="mt-3 bg-slate-100 [&_[data-slot=progress-indicator]]:bg-violet-600" /><p className="mt-3 text-xs leading-5 text-slate-500">Compared with {surpriseSignal.observationCount ?? "available"} valid sector-relative observations for the selected trading-time horizon.</p></div>}
                {selected.itemId && <Button variant="outline" className="mt-6 w-full border-rose-200 text-rose-700 hover:bg-rose-50 hover:text-rose-800" onClick={() => removeStock(selected)}><Trash2 /> Remove from watchlist</Button>}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="rounded-2xl">
          <DialogHeader><DialogTitle>Add to watchlist</DialogTitle><DialogDescription>Tracking begins at the current review watermark.</DialogDescription></DialogHeader>
          <div className="grid gap-2">{addableStocks.map((item) => <button key={item.symbol} onClick={() => addStock(item.symbol)} disabled={stocks.some((stock) => stock.symbol === item.symbol)} className="flex items-center justify-between rounded-xl border border-slate-200 p-4 text-left hover:border-violet-300 hover:bg-violet-50 disabled:opacity-40"><div><p className="font-bold">{item.symbol}</p><p className="text-sm text-slate-500">{item.company}</p></div><span className="font-semibold">{formatPrice(item.price)}</span></button>)}</div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!ruleStock} onOpenChange={(open) => !open && setRuleStock(null)}>
        <DialogContent className="rounded-2xl">
          <DialogHeader><DialogTitle>Add a rule for {ruleStock?.symbol}</DialogTitle><DialogDescription>Rules remain separate from statistical surprise signals.</DialogDescription></DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-2"><Label>Rule type</Label><Select value={ruleType} onValueChange={setRuleType}><SelectTrigger className="w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="price_above">Price crosses above</SelectItem><SelectItem value="price_below">Price crosses below</SelectItem><SelectItem value="volume_pace">Volume pace exceeds</SelectItem></SelectContent></Select></div>
            <div className="grid gap-2"><Label htmlFor="rule-value">{ruleType === "volume_pace" ? "Multiple" : "Price threshold"}</Label><Input id="rule-value" inputMode="decimal" value={ruleValue} onChange={(event) => setRuleValue(event.target.value)} placeholder={ruleType === "volume_pace" ? "1.8" : "2800"} /></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setRuleStock(null)}>Cancel</Button><Button className="bg-[#0b1020]" onClick={saveRule}>Save rule</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

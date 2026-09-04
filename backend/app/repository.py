from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Protocol
from uuid import uuid4

from app.auth import supabase_client


@dataclass(frozen=True)
class WatchlistItemRecord:
    id: str
    symbol: str
    company_name: str
    sector_index: str


@dataclass(frozen=True)
class RuleRecord:
    id: str
    watchlist_item_id: str
    rule_type: str
    threshold: float
    armed: bool = True


@dataclass(frozen=True)
class PathEventRecord:
    symbol: str
    event_type: str
    occurred_at: datetime
    magnitude: float
    percentile: float
    evidence: dict[str, float | int | str | bool | None]


class WatchlistStore(Protocol):
    def get_or_create_watchlist(self, user_id: str, watchlist_id: str | None) -> str: ...
    def create_watchlist(self, user_id: str, name: str) -> str: ...
    def list_items(self, user_id: str, watchlist_id: str) -> list[WatchlistItemRecord]: ...
    def add_item(
        self,
        user_id: str,
        watchlist_id: str,
        symbol: str,
        company_name: str,
        sector_index: str,
    ) -> str: ...
    def remove_item(self, user_id: str, item_id: str) -> None: ...
    def list_rules(self, user_id: str, watchlist_id: str) -> list[RuleRecord]: ...
    def add_rule(
        self,
        user_id: str,
        watchlist_item_id: str,
        rule_type: str,
        threshold: float,
    ) -> str: ...
    def get_watermark(self, user_id: str, watchlist_id: str, default: datetime) -> datetime: ...
    def list_confirmed_path_events(
        self,
        user_id: str,
        watchlist_id: str,
        since: datetime,
    ) -> list[PathEventRecord]: ...
    def acknowledge(
        self,
        user_id: str,
        watchlist_id: str,
        evaluated_through: datetime,
    ) -> datetime: ...


DEFAULT_ITEMS = (
    ("RELIANCE", "Reliance Industries", "NIFTY50"),
    ("INFY", "Infosys", "NIFTY_IT"),
    ("HDFCBANK", "HDFC Bank", "NIFTY_BANK"),
    ("TCS", "Tata Consultancy Services", "NIFTY_IT"),
    ("MARUTI", "Maruti Suzuki", "NIFTY_AUTO"),
    ("SUNPHARMA", "Sun Pharmaceutical", "NIFTY_PHARMA"),
    ("ITC", "ITC", "NIFTY_FMCG"),
    ("TATAMOTORS", "Tata Motors", "NIFTY_AUTO"),
    ("IRCTC", "Indian Railway Catering & Tourism", "NIFTY500"),
    ("ZOMATO", "Eternal", "NIFTY_CONSUMER"),
)


class MemoryWatchlistRepository:
    def __init__(self) -> None:
        self._lock = Lock()
        self._watchlists: dict[tuple[str, str], str] = {}
        self._items: dict[str, list[WatchlistItemRecord]] = {}
        self._rules: dict[str, list[RuleRecord]] = {}
        self._watermarks: dict[tuple[str, str], datetime] = {}
        self._path_events = [
            PathEventRecord(
                symbol="IRCTC",
                event_type="peak_to_trough",
                occurred_at=datetime.fromisoformat("2026-09-04T06:45:00+00:00"),
                magnitude=0.031,
                percentile=96.4,
                evidence={"peak_price": 978.2, "confirmed_before_outage": True},
            )
        ]

    def get_or_create_watchlist(self, user_id: str, watchlist_id: str | None) -> str:
        candidate = watchlist_id or "primary"
        key = (user_id, candidate)
        with self._lock:
            if key not in self._watchlists:
                self._watchlists[key] = "My watchlist"
                self._items[candidate] = [
                    WatchlistItemRecord(
                        id=f"{candidate}:{symbol}",
                        symbol=symbol,
                        company_name=company,
                        sector_index=sector,
                    )
                    for symbol, company, sector in DEFAULT_ITEMS
                ]
                self._rules[candidate] = [
                    RuleRecord("rule-reliance", f"{candidate}:RELIANCE", "price_above", 2800.0),
                    RuleRecord("rule-hdfc", f"{candidate}:HDFCBANK", "volume_pace", 1.8),
                ]
        return candidate

    def create_watchlist(self, user_id: str, name: str) -> str:
        watchlist_id = str(uuid4())
        with self._lock:
            self._watchlists[(user_id, watchlist_id)] = name
            self._items[watchlist_id] = []
            self._rules[watchlist_id] = []
        return watchlist_id

    def list_items(self, user_id: str, watchlist_id: str) -> list[WatchlistItemRecord]:
        self._owned_watchlist(user_id, watchlist_id)
        return list(self._items.get(watchlist_id, []))

    def add_item(
        self,
        user_id: str,
        watchlist_id: str,
        symbol: str,
        company_name: str,
        sector_index: str,
    ) -> str:
        self._owned_watchlist(user_id, watchlist_id)
        normalized_symbol = symbol.strip().upper()
        with self._lock:
            existing = next(
                (item for item in self._items[watchlist_id] if item.symbol == normalized_symbol),
                None,
            )
            if existing:
                return existing.id
            item_id = f"{watchlist_id}:{normalized_symbol}"
            self._items[watchlist_id].append(
                WatchlistItemRecord(
                    id=item_id,
                    symbol=normalized_symbol,
                    company_name=company_name.strip(),
                    sector_index=sector_index.strip().upper().replace(" ", "_"),
                )
            )
        return item_id

    def remove_item(self, user_id: str, item_id: str) -> None:
        watchlist_id = self._owned_item(user_id, item_id)
        with self._lock:
            self._items[watchlist_id] = [item for item in self._items[watchlist_id] if item.id != item_id]
            self._rules[watchlist_id] = [
                rule for rule in self._rules[watchlist_id] if rule.watchlist_item_id != item_id
            ]

    def list_rules(self, user_id: str, watchlist_id: str) -> list[RuleRecord]:
        self._owned_watchlist(user_id, watchlist_id)
        return list(self._rules.get(watchlist_id, []))

    def add_rule(
        self,
        user_id: str,
        watchlist_item_id: str,
        rule_type: str,
        threshold: float,
    ) -> str:
        watchlist_id = self._owned_item(user_id, watchlist_item_id)
        rule_id = str(uuid4())
        with self._lock:
            self._rules[watchlist_id].append(
                RuleRecord(rule_id, watchlist_item_id, rule_type, threshold)
            )
        return rule_id

    def get_watermark(self, user_id: str, watchlist_id: str, default: datetime) -> datetime:
        self._owned_watchlist(user_id, watchlist_id)
        return self._watermarks.get((user_id, watchlist_id), default)

    def list_confirmed_path_events(
        self,
        user_id: str,
        watchlist_id: str,
        since: datetime,
    ) -> list[PathEventRecord]:
        symbols = {item.symbol for item in self.list_items(user_id, watchlist_id)}
        return [
            event
            for event in self._path_events
            if event.symbol in symbols and event.occurred_at > since
        ]

    def acknowledge(
        self,
        user_id: str,
        watchlist_id: str,
        evaluated_through: datetime,
    ) -> datetime:
        self._owned_watchlist(user_id, watchlist_id)
        key = (user_id, watchlist_id)
        with self._lock:
            current = self._watermarks.get(key)
            final = max(current, evaluated_through) if current else evaluated_through
            self._watermarks[key] = final
        return final

    def _owned_watchlist(self, user_id: str, watchlist_id: str) -> None:
        if (user_id, watchlist_id) not in self._watchlists:
            raise PermissionError("watchlist not found")

    def _owned_item(self, user_id: str, item_id: str) -> str:
        for watchlist_id, items in self._items.items():
            if any(item.id == item_id for item in items):
                self._owned_watchlist(user_id, watchlist_id)
                return watchlist_id
        raise PermissionError("watchlist item not found")


class SupabaseWatchlistRepository:
    def get_or_create_watchlist(self, user_id: str, watchlist_id: str | None) -> str:
        client = supabase_client()
        query = client.table("watchlists").select("id").eq("owner_id", user_id)
        if watchlist_id:
            query = query.eq("id", watchlist_id)
        result = query.order("created_at").limit(1).execute()
        if result.data:
            return str(result.data[0]["id"])
        if watchlist_id:
            raise PermissionError("watchlist not found")
        return self.create_watchlist(user_id, "My watchlist")

    def create_watchlist(self, user_id: str, name: str) -> str:
        result = (
            supabase_client()
            .table("watchlists")
            .insert({"owner_id": user_id, "name": name})
            .execute()
        )
        return str(result.data[0]["id"])

    def list_items(self, user_id: str, watchlist_id: str) -> list[WatchlistItemRecord]:
        self._owned_watchlist(user_id, watchlist_id)
        result = (
            supabase_client()
            .table("watchlist_items")
            .select("id,symbol,company_name,sector_index")
            .eq("watchlist_id", watchlist_id)
            .order("created_at")
            .execute()
        )
        return [WatchlistItemRecord(**row) for row in result.data]

    def add_item(
        self,
        user_id: str,
        watchlist_id: str,
        symbol: str,
        company_name: str,
        sector_index: str,
    ) -> str:
        self._owned_watchlist(user_id, watchlist_id)
        result = (
            supabase_client()
            .table("watchlist_items")
            .upsert(
                {
                    "watchlist_id": watchlist_id,
                    "symbol": symbol.strip().upper(),
                    "company_name": company_name.strip(),
                    "sector_index": sector_index.strip().upper().replace(" ", "_"),
                },
                on_conflict="watchlist_id,symbol",
            )
            .execute()
        )
        return str(result.data[0]["id"])

    def remove_item(self, user_id: str, item_id: str) -> None:
        self._owned_item(user_id, item_id)
        supabase_client().table("watchlist_items").delete().eq("id", item_id).execute()

    def list_rules(self, user_id: str, watchlist_id: str) -> list[RuleRecord]:
        self._owned_watchlist(user_id, watchlist_id)
        item_ids = [item.id for item in self.list_items(user_id, watchlist_id)]
        if not item_ids:
            return []
        result = (
            supabase_client()
            .table("personal_rules")
            .select("id,watchlist_item_id,rule_type,threshold,armed")
            .in_("watchlist_item_id", item_ids)
            .execute()
        )
        return [
            RuleRecord(
                id=str(row["id"]),
                watchlist_item_id=str(row["watchlist_item_id"]),
                rule_type=str(row["rule_type"]),
                threshold=float(row["threshold"]),
                armed=bool(row["armed"]),
            )
            for row in result.data
        ]

    def add_rule(
        self,
        user_id: str,
        watchlist_item_id: str,
        rule_type: str,
        threshold: float,
    ) -> str:
        self._owned_item(user_id, watchlist_item_id)
        result = (
            supabase_client()
            .table("personal_rules")
            .insert(
                {
                    "watchlist_item_id": watchlist_item_id,
                    "rule_type": rule_type,
                    "threshold": threshold,
                }
            )
            .execute()
        )
        return str(result.data[0]["id"])

    def get_watermark(self, user_id: str, watchlist_id: str, default: datetime) -> datetime:
        self._owned_watchlist(user_id, watchlist_id)
        result = (
            supabase_client()
            .table("review_watermarks")
            .select("reviewed_through")
            .eq("watchlist_id", watchlist_id)
            .maybe_single()
            .execute()
        )
        if not result.data:
            return default
        return datetime.fromisoformat(str(result.data["reviewed_through"]).replace("Z", "+00:00"))

    def list_confirmed_path_events(
        self,
        user_id: str,
        watchlist_id: str,
        since: datetime,
    ) -> list[PathEventRecord]:
        symbols = [item.symbol for item in self.list_items(user_id, watchlist_id)]
        if not symbols:
            return []
        result = (
            supabase_client()
            .table("path_events")
            .select("symbol,event_type,occurred_at,magnitude,percentile,evidence")
            .in_("symbol", symbols)
            .eq("confirmed_from_fresh_data", True)
            .gt("occurred_at", since.isoformat())
            .order("occurred_at")
            .execute()
        )
        return [
            PathEventRecord(
                symbol=str(row["symbol"]),
                event_type=str(row["event_type"]),
                occurred_at=datetime.fromisoformat(str(row["occurred_at"]).replace("Z", "+00:00")),
                magnitude=float(row["magnitude"]),
                percentile=float(row["percentile"]),
                evidence=dict(row.get("evidence") or {}),
            )
            for row in result.data
        ]

    def acknowledge(
        self,
        user_id: str,
        watchlist_id: str,
        evaluated_through: datetime,
    ) -> datetime:
        self._owned_watchlist(user_id, watchlist_id)
        result = supabase_client().rpc(
            "acknowledge_watchlist",
            {
                "target_watchlist_id": watchlist_id,
                "acknowledged_through": evaluated_through.isoformat(),
            },
        ).execute()
        return datetime.fromisoformat(str(result.data).replace("Z", "+00:00"))

    def _owned_watchlist(self, user_id: str, watchlist_id: str) -> None:
        result = (
            supabase_client()
            .table("watchlists")
            .select("id")
            .eq("id", watchlist_id)
            .eq("owner_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result.data:
            raise PermissionError("watchlist not found")

    def _owned_item(self, user_id: str, item_id: str) -> None:
        result = (
            supabase_client()
            .table("watchlist_items")
            .select("id,watchlists!inner(owner_id)")
            .eq("id", item_id)
            .eq("watchlists.owner_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result.data:
            raise PermissionError("watchlist item not found")

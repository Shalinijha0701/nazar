from datetime import datetime

from app.auth import supabase_client


class WatchlistRepository:
    """Persistence boundary for user-owned watchlist state."""

    def create_watchlist(self, user_id: str, name: str = "My watchlist") -> str:
        result = (
            supabase_client()
            .table("watchlists")
            .insert({"owner_id": user_id, "name": name})
            .execute()
        )
        return str(result.data[0]["id"])

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
            .insert({
                "watchlist_id": watchlist_id,
                "symbol": symbol,
                "company_name": company_name,
                "sector_index": sector_index,
            })
            .execute()
        )
        return str(result.data[0]["id"])

    def remove_item(self, user_id: str, item_id: str) -> None:
        self._owned_item(user_id, item_id)
        supabase_client().table("watchlist_items").delete().eq("id", item_id).execute()

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
            .insert({
                "watchlist_item_id": watchlist_item_id,
                "rule_type": rule_type,
                "threshold": threshold,
            })
            .execute()
        )
        return str(result.data[0]["id"])

    def get_watermark(
        self,
        user_id: str,
        watchlist_id: str,
        default: datetime,
    ) -> datetime:
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

    def _owned_watchlist(self, user_id: str, watchlist_id: str) -> None:
        owner = (
            supabase_client()
            .table("watchlists")
            .select("id")
            .eq("id", watchlist_id)
            .eq("owner_id", user_id)
            .maybe_single()
            .execute()
        )
        if not owner.data:
            raise PermissionError("watchlist not found")

    def _owned_item(self, user_id: str, item_id: str) -> None:
        item = (
            supabase_client()
            .table("watchlist_items")
            .select("id, watchlists!inner(owner_id)")
            .eq("id", item_id)
            .eq("watchlists.owner_id", user_id)
            .maybe_single()
            .execute()
        )
        if not item.data:
            raise PermissionError("watchlist item not found")

    def acknowledge(
        self,
        user_id: str,
        watchlist_id: str,
        evaluated_through: datetime,
    ) -> datetime:
        client = supabase_client()
        self._owned_watchlist(user_id, watchlist_id)

        result = client.rpc(
            "acknowledge_watchlist",
            {
                "target_watchlist_id": watchlist_id,
                "acknowledged_through": evaluated_through.isoformat(),
            },
        ).execute()
        return datetime.fromisoformat(str(result.data).replace("Z", "+00:00"))

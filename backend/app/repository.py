from datetime import datetime

from app.auth import supabase_client


class WatchlistRepository:
    """Persistence boundary for user-owned watchlist state."""

    def acknowledge(
        self,
        user_id: str,
        watchlist_id: str,
        evaluated_through: datetime,
    ) -> datetime:
        client = supabase_client()
        owner = (
            client.table("watchlists")
            .select("id")
            .eq("id", watchlist_id)
            .eq("owner_id", user_id)
            .maybe_single()
            .execute()
        )
        if not owner.data:
            raise PermissionError("watchlist not found")

        result = client.rpc(
            "acknowledge_watchlist",
            {
                "target_watchlist_id": watchlist_id,
                "acknowledged_through": evaluated_through.isoformat(),
            },
        ).execute()
        return datetime.fromisoformat(str(result.data).replace("Z", "+00:00"))

from datetime import UTC, datetime
from typing import Sequence

import httpx

from app.models import Candle


class GrowwProvider:
    """Small adapter around Groww market-data endpoints.

    Order endpoints are intentionally excluded: Nazar observes and explains;
    it never places trades.
    """

    def __init__(self, access_token: str, base_url: str = "https://api.groww.in/v1"):
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "X-API-VERSION": "1.0",
        }

    async def latest_prices(self, symbols: Sequence[str]) -> dict[str, float]:
        if not symbols:
            return {}
        params = {
            "segment": "CASH",
            "exchange_symbols": ",".join(f"NSE_{symbol}" for symbol in symbols),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self._base_url}/live-data/ltp",
                params=params,
                headers=self._headers,
            )
            response.raise_for_status()
            payload = response.json().get("payload", {})

        prices: dict[str, float] = {}
        for symbol in symbols:
            raw = payload.get(f"NSE_{symbol}")
            if raw is not None:
                prices[symbol] = float(raw)
        return prices

    async def candles(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
        interval: str = "1minute",
    ) -> dict[str, list[Candle]]:
        # Historical request shapes can change independently of the domain.
        # Keep that translation isolated here and normalize before returning.
        result: dict[str, list[Candle]] = {}
        async with httpx.AsyncClient(timeout=20) as client:
            for symbol in symbols:
                response = await client.get(
                    f"{self._base_url}/historical/candle/range",
                    params={
                        "exchange": "NSE",
                        "segment": "CASH",
                        "trading_symbol": symbol,
                        "start_time": start.isoformat(),
                        "end_time": end.isoformat(),
                        "interval_in_minutes": 1,
                    },
                    headers=self._headers,
                )
                response.raise_for_status()
                rows = response.json().get("payload", {}).get("candles", [])
                result[symbol] = [
                    Candle(
                        symbol=symbol,
                        interval_start=datetime.fromtimestamp(row[0] / 1000, tz=UTC),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=int(row[5]),
                    )
                    for row in rows
                ]
        return result

from datetime import timedelta
import unittest

from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import DEMO_END
from app.main import create_app, memory_repository


class CatchupApiTests(unittest.TestCase):
    def setUp(self) -> None:
        memory_repository.cache_clear()
        settings = Settings(
            market_provider="replay",
            persistence_backend="memory",
            auth_mode="demo",
            demo_token="test-token",
            allowed_origins="http://localhost:3000",
            _env_file=None,
        )
        self.client = TestClient(create_app(settings))
        self.headers = {"Authorization": "Bearer test-token"}

    def catchup(self):
        return self.client.get("/api/watchlists/me/catchup", headers=self.headers)

    def test_authentication_is_required(self) -> None:
        response = self.client.get("/api/watchlists/me/catchup")
        self.assertEqual(response.status_code, 401)

    def test_replay_response_is_computed_and_grouped(self) -> None:
        response = self.catchup()
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["source"], "replay")
        self.assertEqual(payload["trading_minutes"], 165)
        self.assertEqual(payload["horizon_minutes"], 240)
        self.assertEqual(payload["counts"], {
            "attention": 3,
            "normal": 5,
            "data_unavailable": 2,
        })

        signals = {
            card["symbol"]: {signal["kind"] for signal in card["signals"]}
            for card in payload["attention"]
        }
        self.assertEqual(signals["RELIANCE"], {"personal_rule", "sector_surprise"})
        self.assertEqual(signals["INFY"], {"path_event"})
        self.assertEqual(signals["HDFCBANK"], {"personal_rule"})
        irctc = next(card for card in payload["data_unavailable"] if card["symbol"] == "IRCTC")
        self.assertEqual({signal["kind"] for signal in irctc["signals"]}, {"path_event"})

    def test_acknowledgement_clears_completed_interval(self) -> None:
        initial = self.catchup().json()
        response = self.client.post(
            "/api/watchlists/me/acknowledge",
            headers=self.headers,
            json={
                "watchlist_id": initial["watchlist_id"],
                "evaluated_through": initial["evaluated_through"],
            },
        )
        self.assertEqual(response.status_code, 200)

        refreshed = self.catchup().json()
        self.assertEqual(refreshed["counts"]["attention"], 0)
        self.assertEqual(refreshed["trading_minutes"], 0)
        self.assertEqual(refreshed["coverage"], "insufficient_interval")

    def test_watermark_is_monotonic(self) -> None:
        initial = self.catchup().json()
        first = self.client.post(
            "/api/watchlists/me/acknowledge",
            headers=self.headers,
            json={"watchlist_id": initial["watchlist_id"], "evaluated_through": DEMO_END.isoformat()},
        )
        earlier = self.client.post(
            "/api/watchlists/me/acknowledge",
            headers=self.headers,
            json={
                "watchlist_id": initial["watchlist_id"],
                "evaluated_through": (DEMO_END - timedelta(hours=1)).isoformat(),
            },
        )
        self.assertEqual(earlier.json()["reviewed_through"], first.json()["reviewed_through"])

    def test_add_rule_and_remove_item_round_trip(self) -> None:
        payload = self.catchup().json()
        item = next(card for card in payload["normal"] if card["symbol"] == "TCS")

        rule = self.client.post(
            f"/api/watchlists/items/{item['item_id']}/rules",
            headers=self.headers,
            json={"rule_type": "price_above", "threshold": 4220},
        )
        self.assertEqual(rule.status_code, 200)
        updated = self.catchup().json()
        tcs = next(card for card in updated["attention"] if card["symbol"] == "TCS")
        self.assertIn("personal_rule", {signal["kind"] for signal in tcs["signals"]})

        removed = self.client.delete(
            f"/api/watchlists/items/{item['item_id']}",
            headers=self.headers,
        )
        self.assertEqual(removed.status_code, 200)
        symbols = {
            card["symbol"]
            for group in ("attention", "normal", "data_unavailable")
            for card in self.catchup().json()[group]
        }
        self.assertNotIn("TCS", symbols)

    def test_future_acknowledgement_is_rejected(self) -> None:
        response = self.client.post(
            "/api/watchlists/me/acknowledge",
            headers=self.headers,
            json={"watchlist_id": "primary", "evaluated_through": (DEMO_END + timedelta(minutes=1)).isoformat()},
        )
        self.assertEqual(response.status_code, 422)

    def test_naive_acknowledgement_is_rejected(self) -> None:
        response = self.client.post(
            "/api/watchlists/me/acknowledge",
            headers=self.headers,
            json={"watchlist_id": "primary", "evaluated_through": "2026-09-04T08:30:00"},
        )
        self.assertEqual(response.status_code, 422)


class ConfigurationTests(unittest.TestCase):
    def test_supabase_auth_and_persistence_move_together(self) -> None:
        settings = Settings(
            persistence_backend="supabase",
            auth_mode="demo",
            _env_file=None,
        )
        with self.assertRaisesRegex(RuntimeError, "enabled together"):
            create_app(settings)


if __name__ == "__main__":
    unittest.main()

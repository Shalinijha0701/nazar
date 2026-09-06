import unittest

from app.repository import MAX_WATCHLISTS_PER_USER, MemoryWatchlistRepository


class MemoryRepositoryIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = MemoryWatchlistRepository()

    def test_default_watchlists_are_isolated_per_user(self) -> None:
        self.repo.get_or_create_watchlist("user-a", None)
        self.repo.add_item("user-a", "primary", "WIPRO", "Wipro", "NIFTY_IT")

        self.repo.get_or_create_watchlist("user-b", None)

        a_symbols = {item.symbol for item in self.repo.list_items("user-a", "primary")}
        b_symbols = {item.symbol for item in self.repo.list_items("user-b", "primary")}
        self.assertIn("WIPRO", a_symbols)
        self.assertNotIn("WIPRO", b_symbols)

    def test_second_user_does_not_reset_first_users_items(self) -> None:
        self.repo.get_or_create_watchlist("user-a", None)
        first = self.repo.list_items("user-a", "primary")
        self.repo.remove_item("user-a", first[0].id)
        before = len(self.repo.list_items("user-a", "primary"))

        self.repo.get_or_create_watchlist("user-b", None)

        self.assertEqual(len(self.repo.list_items("user-a", "primary")), before)

    def test_remove_item_requires_ownership(self) -> None:
        self.repo.get_or_create_watchlist("user-a", None)
        item_id = self.repo.add_item("user-a", "primary", "WIPRO", "Wipro", "NIFTY_IT")
        self.repo.get_or_create_watchlist("user-b", None)

        with self.assertRaises(PermissionError):
            self.repo.remove_item("user-b", item_id)

    def test_add_rule_requires_ownership(self) -> None:
        self.repo.get_or_create_watchlist("user-a", None)
        item_id = self.repo.add_item("user-a", "primary", "WIPRO", "Wipro", "NIFTY_IT")
        self.repo.get_or_create_watchlist("user-b", None)

        with self.assertRaises(PermissionError):
            self.repo.add_rule("user-b", item_id, "price_above", 100.0)


class MemoryRepositoryLimitTests(unittest.TestCase):
    def test_watchlist_creation_is_capped_per_user(self) -> None:
        repo = MemoryWatchlistRepository()
        for index in range(MAX_WATCHLISTS_PER_USER):
            repo.create_watchlist("user-a", f"watchlist {index}")

        with self.assertRaises(ValueError):
            repo.create_watchlist("user-a", "one too many")

        # Other users are unaffected by another user's cap.
        repo.create_watchlist("user-b", "fresh start")


if __name__ == "__main__":
    unittest.main()

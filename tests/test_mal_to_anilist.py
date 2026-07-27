import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, mock_open, patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "mal_to_anilist.py"
TEST_CONFIG = {
    "mal_client_id": "mal-client",
    "anilist_client_id": "anilist-client",
    "anilist_client_secret": "anilist-secret",
    "mal_username": "tester",
    "sync_interval_days": 23,
}


def load_module():
    spec = importlib.util.spec_from_file_location("mal_to_anilist_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", mock_open(read_data=json.dumps(TEST_CONFIG))
    ):
        spec.loader.exec_module(module)
    return module


class UpdateMalEntryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.token = "mal-token"

    def test_maps_anime_status_progress_score_and_headers(self):
        response = Mock(status_code=200)
        with patch.object(self.module.requests, "put", return_value=response) as put:
            ok = self.module.update_mal_entry(123, "anime", "CURRENT", 7, 8.5, self.token)

        self.assertTrue(ok)
        put.assert_called_once()
        _, kwargs = put.call_args
        self.assertEqual(kwargs["data"]["status"], "watching")
        self.assertEqual(kwargs["data"]["num_watched_episodes"], 7)
        self.assertNotIn("num_chapters_read", kwargs["data"])
        self.assertEqual(kwargs["data"]["score"], 9)
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {self.token}")
        self.assertEqual(kwargs["headers"]["X-MAL-CLIENT-ID"], "mal-client")

    def test_maps_manga_status_and_progress_field(self):
        response = Mock(status_code=200)
        with patch.object(self.module.requests, "put", return_value=response) as put:
            ok = self.module.update_mal_entry(456, "manga", "PAUSED", 12, 6, self.token)

        self.assertTrue(ok)
        data = put.call_args.kwargs["data"]
        self.assertEqual(data["status"], "on_hold")
        self.assertEqual(data["num_chapters_read"], 12)
        self.assertNotIn("num_watched_episodes", data)

    def test_maps_repeating_anime_with_rewatching_flag(self):
        response = Mock(status_code=200)
        with patch.object(self.module.requests, "put", return_value=response) as put:
            ok = self.module.update_mal_entry(789, "anime", "REPEATING", 3, 10, self.token)

        self.assertTrue(ok)
        data = put.call_args.kwargs["data"]
        self.assertEqual(data["status"], "watching")
        self.assertEqual(data["is_rewatching"], "true")
        self.assertNotIn("is_rereading", data)

    def test_maps_repeating_manga_with_rereading_flag(self):
        response = Mock(status_code=200)
        with patch.object(self.module.requests, "put", return_value=response) as put:
            ok = self.module.update_mal_entry(789, "manga", "REPEATING", 3, 10, self.token)

        self.assertTrue(ok)
        data = put.call_args.kwargs["data"]
        self.assertEqual(data["status"], "reading")
        self.assertEqual(data["is_rereading"], "true")
        self.assertNotIn("is_rewatching", data)

    def test_unsupported_status_returns_false_without_request(self):
        with patch.object(self.module.requests, "put") as put, patch.object(self.module, "log"):
            ok = self.module.update_mal_entry(123, "anime", "UNKNOWN", 1, 1, self.token)

        self.assertFalse(ok)
        put.assert_not_called()

    def test_non_200_response_returns_false(self):
        response = Mock(status_code=400, text="bad request")
        with patch.object(self.module.requests, "put", return_value=response), patch.object(self.module, "log"):
            ok = self.module.update_mal_entry(123, "anime", "CURRENT", 1, 1, self.token)

        self.assertFalse(ok)

    def test_request_exception_returns_false(self):
        with patch.object(
            self.module.requests,
            "put",
            side_effect=self.module.requests.exceptions.RequestException("network down"),
        ), patch.object(self.module, "log"):
            ok = self.module.update_mal_entry(123, "anime", "CURRENT", 1, 1, self.token)

        self.assertFalse(ok)

    def test_mal_score_uses_half_up_rounding_and_clamps(self):
        self.assertEqual(self.module.mal_score(7.5), 8)
        self.assertEqual(self.module.mal_score(8.5), 9)
        self.assertEqual(self.module.mal_score(-1), 0)
        self.assertEqual(self.module.mal_score(11), 10)


class ReverseSyncFlowTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_anilist_ahead_updates_mal_counter(self):
        entries = [{
            "mal_id": 1,
            "title": "Ahead on AniList",
            "status": "watching",
            "score": 4,
            "progress": 2,
            "type": "anime",
        }]
        logs = []

        with patch.object(self.module, "already_ran_recently", return_value=False), \
             patch.object(self.module, "days_since_last_run", return_value=None), \
             patch.object(self.module, "get_mal_token", return_value="mal-token"), \
             patch.object(self.module, "get_anilist_token", return_value="al-token"), \
             patch.object(self.module, "fetch_mal_list", side_effect=[entries, []]), \
             patch.object(self.module, "get_anilist_entry", return_value=(101, "CURRENT", 5, 8)), \
             patch.object(self.module, "update_mal_entry", return_value=True) as update_mal, \
             patch.object(self.module, "update_anilist_entry") as update_anilist, \
             patch.object(self.module, "mark_ran_today"), \
             patch.object(self.module.time, "sleep"), \
             patch.object(self.module, "log", side_effect=logs.append):
            self.module.sync()

        update_mal.assert_called_once_with(1, "anime", "CURRENT", 5, 8, "mal-token")
        update_anilist.assert_not_called()
        self.assertTrue(any("MAL updated: 1" in message for message in logs))

    def test_failed_anilist_ahead_mal_update_counts_as_skipped(self):
        entries = [{
            "mal_id": 1,
            "title": "Ahead on AniList",
            "status": "watching",
            "score": 4,
            "progress": 2,
            "type": "anime",
        }]
        logs = []

        with patch.object(self.module, "already_ran_recently", return_value=False), \
             patch.object(self.module, "days_since_last_run", return_value=None), \
             patch.object(self.module, "get_mal_token", return_value="mal-token"), \
             patch.object(self.module, "get_anilist_token", return_value="al-token"), \
             patch.object(self.module, "fetch_mal_list", side_effect=[entries, []]), \
             patch.object(self.module, "get_anilist_entry", return_value=(101, "CURRENT", 5, 8)), \
             patch.object(self.module, "update_mal_entry", return_value=False), \
             patch.object(self.module, "mark_ran_today"), \
             patch.object(self.module.time, "sleep"), \
             patch.object(self.module, "log", side_effect=logs.append):
            self.module.sync()

        self.assertTrue(any("MAL updated: 0" in message and "Skipped: 1" in message for message in logs))


if __name__ == "__main__":
    unittest.main()

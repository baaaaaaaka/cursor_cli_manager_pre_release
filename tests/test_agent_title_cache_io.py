import json
import tempfile
import unittest
from pathlib import Path

from cursor_cli_manager.agent_title_cache import CHAT_TITLE_CACHE_FILENAME, load_chat_title_cache


class TestAgentTitleCacheIO(unittest.TestCase):
    def test_load_cache_missing_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            cache = load_chat_title_cache(config_dir)
            self.assertEqual(cache.workspaces, {})

    def test_load_cache_invalid_json_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            p = config_dir / CHAT_TITLE_CACHE_FILENAME
            p.write_text("{not json", encoding="utf-8")
            cache = load_chat_title_cache(config_dir)
            self.assertEqual(cache.workspaces, {})

    def test_load_cache_filters_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            p = config_dir / CHAT_TITLE_CACHE_FILENAME
            payload = {
                "version": 1,
                "workspaces": {
                    "ws": {
                        "chat_ok": {"title": "Hello", "updated_ms": 1},
                        "chat_bad_title": {"title": "   ", "updated_ms": 2},
                        "chat_bad_ms": {"title": "World", "updated_ms": "x"},
                        "chat_bad_entry": "nope",
                    }
                },
            }
            p.write_text(json.dumps(payload), encoding="utf-8")
            cache = load_chat_title_cache(config_dir)
            self.assertIn("ws", cache.workspaces)
            self.assertIn("chat_ok", cache.workspaces["ws"])
            self.assertIn("chat_bad_ms", cache.workspaces["ws"])
            self.assertNotIn("chat_bad_title", cache.workspaces["ws"])
            self.assertNotIn("chat_bad_entry", cache.workspaces["ws"])
            self.assertEqual(cache.workspaces["ws"]["chat_bad_ms"]["updated_ms"], 0)


if __name__ == "__main__":
    unittest.main()


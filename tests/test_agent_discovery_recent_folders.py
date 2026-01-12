import unittest
from pathlib import Path
from unittest.mock import patch

from cursor_cli_manager.agent_discovery import discover_recent_folders_from_cursor_gui
from cursor_cli_manager.paths import CursorUserDirs


class TestAgentDiscoveryRecentFolders(unittest.TestCase):
    def test_discover_recent_folders_parses_file_uris(self) -> None:
        user_dirs = CursorUserDirs(user_dir=Path("/tmp/cursor/User"))

        data = {
            "entries": [
                {"folderUri": "file:///home/user/repo"},
                {"folderUri": "file:///home/user/with%20space"},
                {"folderUri": "http://example.com/not-a-file"},
                {"folderUri": 123},
                "nope",
            ]
        }

        with patch("cursor_cli_manager.agent_discovery.read_json", return_value=data):
            out = discover_recent_folders_from_cursor_gui(user_dirs)

        self.assertEqual(out, [Path("/home/user/repo"), Path("/home/user/with space")])

    def test_discover_recent_folders_handles_unexpected_shapes(self) -> None:
        user_dirs = CursorUserDirs(user_dir=Path("/tmp/cursor/User"))
        with patch("cursor_cli_manager.agent_discovery.read_json", return_value=None):
            self.assertEqual(discover_recent_folders_from_cursor_gui(user_dirs), [])
        with patch("cursor_cli_manager.agent_discovery.read_json", return_value={"entries": "nope"}):
            self.assertEqual(discover_recent_folders_from_cursor_gui(user_dirs), [])


if __name__ == "__main__":
    unittest.main()


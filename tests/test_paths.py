import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cursor_cli_manager.paths import (
    ENV_CURSOR_USER_DATA_DIR,
    CursorUserDirs,
    _candidate_user_dirs_for_platform,
    first_existing,
    get_cursor_user_dirs,
)


class TestPaths(unittest.TestCase):
    def test_candidate_user_dirs_for_platform(self) -> None:
        with patch("pathlib.Path.home", return_value=Path("/home/test")):
            darwin = list(_candidate_user_dirs_for_platform("Darwin"))
            self.assertEqual(
                darwin,
                [Path("/home/test/Library/Application Support/Cursor/User")],
            )

            linux = list(_candidate_user_dirs_for_platform("Linux"))
            self.assertEqual(
                linux,
                [Path("/home/test/.config/Cursor/User"), Path("/home/test/.config/cursor/User")],
            )

            other = list(_candidate_user_dirs_for_platform("OtherOS"))
            self.assertEqual(other, [Path("/home/test/.config/Cursor/User")])

    def test_get_cursor_user_dirs_env_override(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {ENV_CURSOR_USER_DATA_DIR: td}):
                d = get_cursor_user_dirs()
                self.assertEqual(d.user_dir, Path(td))
                self.assertEqual(d.global_storage_dir, Path(td) / "globalStorage")
                self.assertEqual(d.global_state_vscdb, Path(td) / "globalStorage" / "state.vscdb")
                self.assertEqual(d.workspace_storage_dir, Path(td) / "workspaceStorage")

    def test_get_cursor_user_dirs_falls_back_to_first_candidate_when_missing(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch("platform.system", return_value="Linux"):
                with patch("pathlib.Path.home", return_value=Path("/home/test")):
                    # Pretend no candidate exists.
                    with patch("pathlib.Path.exists", return_value=False):
                        d = get_cursor_user_dirs()
                        self.assertEqual(d, CursorUserDirs(Path("/home/test/.config/Cursor/User")))

    def test_first_existing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            a = base / "a"
            b = base / "b"
            c = base / "c"
            b.write_text("x", encoding="utf-8")
            c.write_text("y", encoding="utf-8")
            self.assertEqual(first_existing([a, b, c]), b)
            self.assertEqual(first_existing([a]), None)


if __name__ == "__main__":
    unittest.main()


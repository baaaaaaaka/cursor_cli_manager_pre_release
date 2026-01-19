import unittest
from unittest import mock

import curses

from cursor_cli_manager.tui import (
    _decode_esc_sequence,
    _esc_sequence_complete,
    _input_timeout_ms,
    _is_xterm_like,
    _map_esc_sequence,
    _parse_csi_tilde_number,
    _should_quit,
    force_exit_alternate_screen,
)


class TestTuiInputHandling(unittest.TestCase):
    def test_should_quit_ignores_q_and_Q_in_search_mode(self) -> None:
        self.assertFalse(_should_quit(ch=ord("q"), input_mode="ws"))
        self.assertFalse(_should_quit(ch=ord("Q"), input_mode="chat"))

    def test_should_quit_allows_q_and_Q_when_not_searching(self) -> None:
        self.assertTrue(_should_quit(ch=ord("q"), input_mode=None))
        self.assertTrue(_should_quit(ch=ord("Q"), input_mode=None))

    def test_should_quit_allows_key_exit_when_available(self) -> None:
        key_exit = getattr(curses, "KEY_EXIT", None)
        if isinstance(key_exit, int):
            self.assertTrue(_should_quit(ch=key_exit, input_mode=None))
            self.assertFalse(_should_quit(ch=key_exit, input_mode="ws"))

    def test_input_timeout_ms_polls_when_bg_or_update_pending(self) -> None:
        self.assertEqual(_input_timeout_ms(bg_pending=False, update_checking=False, ui_pending=False), -1)
        self.assertEqual(_input_timeout_ms(bg_pending=True, update_checking=False, ui_pending=False), 80)
        self.assertEqual(_input_timeout_ms(bg_pending=False, update_checking=True, ui_pending=False), 80)
        self.assertEqual(_input_timeout_ms(bg_pending=False, update_checking=False, ui_pending=True), 80)

    def test_parse_csi_tilde_number(self) -> None:
        self.assertEqual(_parse_csi_tilde_number("[5~"), 5)
        self.assertEqual(_parse_csi_tilde_number("[6;2~"), 6)
        self.assertIsNone(_parse_csi_tilde_number("[A"))
        self.assertIsNone(_parse_csi_tilde_number("[~"))
        self.assertIsNone(_parse_csi_tilde_number("[;5~"))
        self.assertIsNone(_parse_csi_tilde_number("[x~"))

    def test_map_esc_sequence_page_keys(self) -> None:
        self.assertEqual(_map_esc_sequence("[5~"), curses.KEY_PPAGE)
        self.assertEqual(_map_esc_sequence("[6~"), curses.KEY_NPAGE)
        self.assertEqual(_map_esc_sequence("[5;2~"), curses.KEY_PPAGE)
        self.assertEqual(_map_esc_sequence("[6;2~"), curses.KEY_NPAGE)

    def test_map_esc_sequence_arrows(self) -> None:
        self.assertEqual(_map_esc_sequence("[A"), curses.KEY_UP)
        self.assertEqual(_map_esc_sequence("[B"), curses.KEY_DOWN)
        self.assertEqual(_map_esc_sequence("[C"), curses.KEY_RIGHT)
        self.assertEqual(_map_esc_sequence("[D"), curses.KEY_LEFT)
        self.assertEqual(_map_esc_sequence("OA"), curses.KEY_UP)
        self.assertEqual(_map_esc_sequence("OB"), curses.KEY_DOWN)
        self.assertEqual(_map_esc_sequence("OC"), curses.KEY_RIGHT)
        self.assertEqual(_map_esc_sequence("OD"), curses.KEY_LEFT)

    def test_map_esc_sequence_home_end(self) -> None:
        self.assertEqual(_map_esc_sequence("[H"), curses.KEY_HOME)
        self.assertEqual(_map_esc_sequence("[F"), curses.KEY_END)
        self.assertEqual(_map_esc_sequence("OH"), curses.KEY_HOME)
        self.assertEqual(_map_esc_sequence("OF"), curses.KEY_END)
        self.assertEqual(_map_esc_sequence("[1~"), curses.KEY_HOME)
        self.assertEqual(_map_esc_sequence("[4~"), curses.KEY_END)
        self.assertEqual(_map_esc_sequence("[7~"), curses.KEY_HOME)
        self.assertEqual(_map_esc_sequence("[8~"), curses.KEY_END)

    def test_map_esc_sequence_unknown_returns_none(self) -> None:
        self.assertIsNone(_map_esc_sequence("[9~"))
        self.assertIsNone(_map_esc_sequence("x"))

    def test_esc_sequence_complete(self) -> None:
        self.assertFalse(_esc_sequence_complete(""))
        self.assertFalse(_esc_sequence_complete("["))
        self.assertFalse(_esc_sequence_complete("[5"))
        self.assertTrue(_esc_sequence_complete("[5~"))
        self.assertTrue(_esc_sequence_complete("[6;2~"))
        self.assertFalse(_esc_sequence_complete("O"))
        self.assertTrue(_esc_sequence_complete("OA"))
        self.assertTrue(_esc_sequence_complete("[A"))
        self.assertFalse(_esc_sequence_complete("x"))

    def test_decode_esc_sequence_escape_only(self) -> None:
        class _FakeWin:
            def __init__(self, inputs):
                self.inputs = list(inputs)
                self.timeouts = []

            def timeout(self, ms):
                self.timeouts.append(ms)

            def getch(self):
                if self.inputs:
                    return self.inputs.pop(0)
                return -1

        win = _FakeWin([])
        with mock.patch.object(curses, "ungetch") as unget:
            key = _decode_esc_sequence(win, timeout_ms=5, restore_timeout_ms=0)
        self.assertEqual(key, 27)
        unget.assert_not_called()

    def test_decode_esc_sequence_known_sequence(self) -> None:
        class _FakeWin:
            def __init__(self, inputs):
                self.inputs = list(inputs)
                self.timeouts = []

            def timeout(self, ms):
                self.timeouts.append(ms)

            def getch(self):
                if self.inputs:
                    return self.inputs.pop(0)
                return -1

        win = _FakeWin([ord("["), ord("5"), ord("~")])
        with mock.patch.object(curses, "ungetch") as unget:
            key = _decode_esc_sequence(win, timeout_ms=5, restore_timeout_ms=0)
        self.assertEqual(key, curses.KEY_PPAGE)
        unget.assert_not_called()

    def test_decode_esc_sequence_unknown_ungets_bytes(self) -> None:
        class _FakeWin:
            def __init__(self, inputs):
                self.inputs = list(inputs)
                self.timeouts = []

            def timeout(self, ms):
                self.timeouts.append(ms)

            def getch(self):
                if self.inputs:
                    return self.inputs.pop(0)
                return -1

        win = _FakeWin([ord("x")])
        calls = []

        def _record(ch):
            calls.append(ch)

        with mock.patch.object(curses, "ungetch", side_effect=_record):
            key = _decode_esc_sequence(win, timeout_ms=5, restore_timeout_ms=0)
        self.assertEqual(key, 27)
        self.assertEqual(calls, [ord("x")])

    def test_decode_esc_sequence_incomplete_ungets_reverse(self) -> None:
        class _FakeWin:
            def __init__(self, inputs):
                self.inputs = list(inputs)
                self.timeouts = []

            def timeout(self, ms):
                self.timeouts.append(ms)

            def getch(self):
                if self.inputs:
                    return self.inputs.pop(0)
                return -1

        win = _FakeWin([ord("["), ord("5")])
        calls = []

        def _record(ch):
            calls.append(ch)

        with mock.patch.object(curses, "ungetch", side_effect=_record):
            key = _decode_esc_sequence(win, timeout_ms=5, restore_timeout_ms=0)
        self.assertEqual(key, 27)
        self.assertEqual(calls, [ord("5"), ord("[")])

    def test_is_xterm_like(self) -> None:
        self.assertTrue(_is_xterm_like("xterm-256color"))
        self.assertTrue(_is_xterm_like("screen"))
        self.assertTrue(_is_xterm_like("tmux-256color"))
        self.assertTrue(_is_xterm_like("wezterm"))
        self.assertFalse(_is_xterm_like("linux"))
        self.assertFalse(_is_xterm_like("vt100"))

    def test_force_exit_alternate_screen_prefers_rmcup(self) -> None:
        with mock.patch.object(curses, "tigetstr", return_value=b"RM"), mock.patch(
            "cursor_cli_manager.tui._write_stdout_bytes"
        ) as write, mock.patch("sys.stdout.isatty", return_value=True):
            force_exit_alternate_screen()
        write.assert_called_once_with(b"RM")

    def test_force_exit_alternate_screen_fallback(self) -> None:
        with mock.patch.object(curses, "tigetstr", return_value=None), mock.patch(
            "cursor_cli_manager.tui._write_stdout_bytes"
        ) as write, mock.patch.dict("os.environ", {"TERM": "xterm-256color"}), mock.patch(
            "sys.stdout.isatty", return_value=True
        ):
            force_exit_alternate_screen()
        write.assert_called_once_with(b"\x1b[?1049l")

    def test_force_exit_alternate_screen_no_tty(self) -> None:
        with mock.patch.object(curses, "tigetstr", return_value=b"RM"), mock.patch(
            "sys.stdout.isatty", return_value=False
        ), mock.patch("os.write") as os_write:
            force_exit_alternate_screen()
        os_write.assert_not_called()

    def test_force_exit_alternate_screen_no_fallback(self) -> None:
        with mock.patch.object(curses, "tigetstr", return_value=None), mock.patch(
            "cursor_cli_manager.tui._write_stdout_bytes"
        ) as write, mock.patch.dict("os.environ", {"TERM": "vt100"}), mock.patch(
            "sys.stdout.isatty", return_value=True
        ):
            force_exit_alternate_screen()
        write.assert_not_called()


if __name__ == "__main__":
    unittest.main()


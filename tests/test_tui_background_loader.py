import threading
import time
import unittest
from pathlib import Path
from typing import List, Optional, Tuple

from cursor_cli_manager.models import AgentChat, AgentWorkspace
from cursor_cli_manager.tui import _BackgroundLoader


class TestTuiBackgroundLoader(unittest.TestCase):
    def test_ensure_chats_is_non_blocking(self) -> None:
        ws = AgentWorkspace(cwd_hash="h", workspace_path=Path("/tmp/ws"), chats_root=Path("/tmp/chats/h"))
        evt = threading.Event()

        def load_chats(_ws: AgentWorkspace) -> List[AgentChat]:
            # Block until the test allows it to finish.
            evt.wait(timeout=2.0)
            return [
                AgentChat(
                    chat_id="c1",
                    name="Chat",
                    created_at_ms=None,
                    mode=None,
                    latest_root_blob_id=None,
                    store_db_path=Path("/tmp/store.db"),
                )
            ]

        def load_preview_snippet(_chat: AgentChat, _max_messages: int) -> Tuple[Optional[str], Optional[str]]:
            return None, None

        def load_preview_full(_chat: AgentChat) -> Tuple[Optional[str], Optional[str]]:
            return None, None

        bg = _BackgroundLoader(load_chats=load_chats, load_preview_snippet=load_preview_snippet, load_preview_full=load_preview_full)

        t0 = time.monotonic()
        bg.ensure_chats(ws)
        # Must return immediately (well under the event timeout).
        self.assertLess(time.monotonic() - t0, 0.2)

        # No result until we release the event.
        self.assertEqual(bg.drain(), [])
        evt.set()

        # Eventually we should see a chats_ok message.
        deadline = time.monotonic() + 2.0
        seen = False
        while time.monotonic() < deadline:
            for msg in bg.drain():
                if msg[0] == "chats_ok":
                    seen = True
                    break
            if seen:
                break
            time.sleep(0.01)
        self.assertTrue(seen)

    def test_ensure_preview_snippet_and_full_are_non_blocking_and_return_results(self) -> None:
        ws = AgentWorkspace(cwd_hash="h", workspace_path=Path("/tmp/ws"), chats_root=Path("/tmp/chats/h"))
        chat = AgentChat(
            chat_id="c1",
            name="Chat",
            created_at_ms=None,
            mode=None,
            latest_root_blob_id="root",
            store_db_path=Path("/tmp/store.db"),
        )

        evt_snip = threading.Event()
        evt_full = threading.Event()

        def load_chats(_ws: AgentWorkspace) -> List[AgentChat]:
            return [chat]

        def load_preview_snippet(_chat: AgentChat, max_messages: int) -> Tuple[Optional[str], Optional[str]]:
            assert max_messages == 12
            evt_snip.wait(timeout=2.0)
            return "history", "snippet"

        def load_preview_full(_chat: AgentChat) -> Tuple[Optional[str], Optional[str]]:
            evt_full.wait(timeout=2.0)
            return "history", "full"

        bg = _BackgroundLoader(load_chats=load_chats, load_preview_snippet=load_preview_snippet, load_preview_full=load_preview_full)

        t0 = time.monotonic()
        bg.ensure_preview_snippet(chat, max_messages=12)
        self.assertLess(time.monotonic() - t0, 0.2)

        t1 = time.monotonic()
        bg.ensure_preview_full(chat)
        self.assertLess(time.monotonic() - t1, 0.2)

        # Release snippet first, then full.
        self.assertEqual(bg.drain(), [])
        evt_snip.set()

        deadline = time.monotonic() + 2.0
        seen_snip = False
        while time.monotonic() < deadline:
            for msg in bg.drain():
                if msg[0] == "preview_snippet_ok":
                    _kind, chat_id, max_messages, role, text = msg
                    self.assertEqual(chat_id, "c1")
                    self.assertEqual(max_messages, 12)
                    self.assertEqual(role, "history")
                    self.assertEqual(text, "snippet")
                    seen_snip = True
                    break
            if seen_snip:
                break
            time.sleep(0.01)
        self.assertTrue(seen_snip)

        evt_full.set()
        deadline = time.monotonic() + 2.0
        seen_full = False
        while time.monotonic() < deadline:
            for msg in bg.drain():
                if msg[0] == "preview_full_ok":
                    _kind, chat_id, role, text = msg
                    self.assertEqual(chat_id, "c1")
                    self.assertEqual(role, "history")
                    self.assertEqual(text, "full")
                    seen_full = True
                    break
            if seen_full:
                break
            time.sleep(0.01)
        self.assertTrue(seen_full)


if __name__ == "__main__":
    unittest.main()


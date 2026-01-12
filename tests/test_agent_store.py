import binascii
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cursor_cli_manager.agent_store import (
    extract_initial_messages,
    extract_last_message_preview,
    extract_recent_messages,
    read_chat_meta,
    read_chat_meta_and_preview,
)


def _make_store_db(db_path: Path, *, meta_obj: dict, blob_id: str, blob_data: bytes) -> None:
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB);")
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);")

    meta_json = json.dumps(meta_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    meta_hex = binascii.hexlify(meta_json).decode("ascii")
    con.execute("INSERT INTO meta(key, value) VALUES(?, ?);", ("0", meta_hex))
    con.execute("INSERT INTO blobs(id, data) VALUES(?, ?);", (blob_id, blob_data))
    con.commit()
    con.close()


class TestAgentStore(unittest.TestCase):
    def test_read_meta_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "store.db"
            root = "rootblob"
            meta = {
                "agentId": "chat-1",
                "latestRootBlobId": root,
                "name": "My Chat",
                "mode": "default",
                "createdAt": 123,
            }
            msg = b'{"id":"1","role":"user","content":[{"type":"text","text":"hello"}]}'
            blob = b"\x00\x01" + msg + b"\x00"
            _make_store_db(db, meta_obj=meta, blob_id=root, blob_data=blob)

            m = read_chat_meta(db)
            assert m is not None
            self.assertEqual(m.agent_id, "chat-1")
            self.assertEqual(m.latest_root_blob_id, root)
            self.assertEqual(m.name, "My Chat")
            self.assertEqual(m.mode, "default")
            self.assertEqual(m.created_at_ms, 123)

            role, text = extract_last_message_preview(db, root)
            self.assertEqual(role, "user")
            self.assertEqual(text, "hello")

            meta2, role2, text2 = read_chat_meta_and_preview(db)
            assert meta2 is not None
            self.assertEqual(meta2.agent_id, "chat-1")
            self.assertEqual(role2, "user")
            self.assertEqual(text2, "hello")

    def test_preview_fallback_scans_other_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "store.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB);")
            con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);")

            # Root blob is binary/no-json (simulates latestRootBlobId pointing to a non-message root node).
            root = "rootblob"
            con.execute("INSERT INTO blobs(id, data) VALUES(?, ?);", (root, b"\x00\x01\x02\x03"))

            # Another blob contains the actual message JSON.
            msg_blob = "msgblob"
            msg = b'{"id":"1","role":"user","content":[{"type":"text","text":"hello"}]}'
            con.execute("INSERT INTO blobs(id, data) VALUES(?, ?);", (msg_blob, msg))

            meta = {"agentId": "chat-1", "latestRootBlobId": root, "name": "My Chat"}
            meta_json = json.dumps(meta, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            meta_hex = binascii.hexlify(meta_json).decode("ascii")
            con.execute("INSERT INTO meta(key, value) VALUES(?, ?);", ("0", meta_hex))
            con.commit()
            con.close()

            role, text = extract_last_message_preview(db, root)
            self.assertEqual(role, "user")
            self.assertEqual(text, "hello")

            msgs = extract_recent_messages(db, max_messages=5)
            self.assertEqual(msgs, [("user", "hello")])

            msgs_all = extract_recent_messages(db, max_messages=None, max_blobs=None)
            self.assertEqual(msgs_all, [("user", "hello")])

            msgs_init = extract_initial_messages(db, max_messages=5, max_blobs=None)
            self.assertEqual(msgs_init, [("user", "hello")])

    def test_extract_initial_vs_recent_message_order(self) -> None:
        """
        initial: from the start of the chat (chronological)
        recent: from the end of the chat (chronological, last N)
        """
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "store.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB);")
            con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);")
            con.execute("INSERT INTO meta(key, value) VALUES(?, ?);", ("0", ""))

            def _msg(i: int, role: str) -> bytes:
                txt = f"m{i}"
                return json.dumps(
                    {"id": str(i), "role": role, "content": [{"type": "text", "text": txt}]},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")

            # 6 messages across 3 blobs, in chronological insertion order.
            blob1 = b"\x00" + _msg(0, "user") + b"\x00" + _msg(1, "assistant") + b"\x00"
            blob2 = b"\x00" + _msg(2, "user") + b"\x00" + _msg(3, "assistant") + b"\x00"
            blob3 = b"\x00" + _msg(4, "user") + b"\x00" + _msg(5, "assistant") + b"\x00"
            con.execute("INSERT INTO blobs(id, data) VALUES(?, ?);", ("b1", blob1))
            con.execute("INSERT INTO blobs(id, data) VALUES(?, ?);", ("b2", blob2))
            con.execute("INSERT INTO blobs(id, data) VALUES(?, ?);", ("b3", blob3))
            con.commit()
            con.close()

            init3 = extract_initial_messages(db, max_messages=3, max_blobs=None)
            self.assertEqual(init3, [("user", "m0"), ("assistant", "m1"), ("user", "m2")])

            recent3 = extract_recent_messages(db, max_messages=3, max_blobs=None)
            self.assertEqual(recent3, [("assistant", "m3"), ("user", "m4"), ("assistant", "m5")])


if __name__ == "__main__":
    unittest.main()


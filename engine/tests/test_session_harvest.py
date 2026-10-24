"""wiki_session_harvest.py's Hermes reader against the ways Hermes stores one message more than once.

Run: python tests/test_session_harvest.py   (stdlib only; builds a throwaway state.db, never reads
the real Hermes home)

Why these cases: when Hermes compacts a conversation in place it keeps the old rows (archived, not
deleted) and inserts copies with the same timestamp, role and content. A long conversation that is
compacted several times is then stored two or three times over, which used to fill the harvest file
with repeats and force its assistant messages down to 300 characters. The owner's message can also
survive only in archived rows, because the visible copy is merged into the compaction summary that
the harvest drops; filtering on Hermes' visibility columns would lose it, so the reader must
de-duplicate instead of filter.
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import wiki_session_harvest as harvest  # noqa: E402

FULL_SCHEMA = (
    "CREATE TABLE sessions (id TEXT, title TEXT, parent_session_id TEXT, source TEXT);"
    "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,"
    " timestamp REAL, _compressed_summary INTEGER, display_kind TEXT, active INTEGER,"
    " compacted INTEGER);"
)
OLD_SCHEMA = (   # a Hermes version before compaction flags and display kinds existed
    "CREATE TABLE sessions (id TEXT, title TEXT, parent_session_id TEXT, source TEXT);"
    "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,"
    " timestamp REAL);"
)
SUMMARY = ("[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted ...\n\n"
           "--- END OF CONTEXT SUMMARY — respond to the message below, not the summary above ---\n\n")


class HermesReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def db(self, schema, rows):
        con = sqlite3.connect(self.home / "state.db")
        con.executescript(schema)
        con.execute("INSERT INTO sessions VALUES ('s1', 'Chat', NULL, 'desktop')")
        cols = [r[1] for r in con.execute("PRAGMA table_info(messages)")][1:]
        for row in rows:
            con.execute(f"INSERT INTO messages ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        row[:len(cols)])
        con.commit()
        con.close()

    def read(self):
        return [(t, role, text) for _, _, msgs in harvest.read_hermes(self.home, 0, 10_000)
                for t, role, text in msgs]

    def test_compaction_copies_are_read_once(self):
        # (session, role, content, timestamp, _compressed_summary, display_kind, active, compacted)
        self.db(FULL_SCHEMA, [
            ("s1", "user", "use sqlite", 100.0, 0, None, 0, 1),          # summarized original
            ("s1", "user", "use sqlite", 100.0, 0, None, 0, 0),          # carried-tail original
            ("s1", "user", "use sqlite", 100.0, 0, None, 1, 0),          # live copy
            ("s1", "assistant", "done: sqlite", 101.0, 0, None, 0, 1),
            ("s1", "assistant", "done: sqlite", 101.0, 0, None, 1, 0),
        ])
        self.assertEqual(self.read(), [(100.0, "user", "use sqlite"), (101.0, "assistant", "done: sqlite")])

    def test_owner_message_kept_when_only_archived_rows_hold_it(self):
        self.db(FULL_SCHEMA, [
            ("s1", "user", "keep the 2014 rules", 200.0, 0, None, 0, 0),
            ("s1", "user", "keep the 2014 rules", 200.0, 0, None, 0, 0),
            ("s1", "user", SUMMARY + "keep the 2014 rules", 200.0, 1, None, 0, 1),
        ])
        self.assertEqual(self.read(), [(200.0, "user", "keep the 2014 rules")])

    def test_same_words_at_different_times_are_two_messages(self):
        self.db(FULL_SCHEMA, [
            ("s1", "user", "start", 300.0, 0, None, 1, 0),
            ("s1", "user", "start", 400.0, 0, None, 1, 0),
        ])
        self.assertEqual([t for t, _, _ in self.read()], [300.0, 400.0])

    def test_old_schema_without_compaction_columns(self):
        self.db(OLD_SCHEMA, [
            ("s1", "user", "hello", 100.0),
            ("s1", "user", "hello", 100.0),
            ("s1", "assistant", "hi", 101.0),
        ])
        self.assertEqual(self.read(), [(100.0, "user", "hello"), (101.0, "assistant", "hi")])


class CodexReader(unittest.TestCase):
    """Codex stores older rollouts zstd-compressed; the reader once globbed *.jsonl only."""

    def test_compressed_and_plain_rollouts_are_both_read_once(self):
        try:
            from compression import zstd
        except ImportError:
            self.skipTest("zstd decoder needs Python 3.14+")
        import json
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "sessions" / "2026" / "09" / "01"
            day.mkdir(parents=True)

            def rollout(text, t):
                rows = ({"type": "session_meta", "payload": {"cwd": "C:/Dev/Game", "originator": "codex_cli_rs"}},
                        {"type": "response_item", "timestamp": t,
                         "payload": {"type": "message", "role": "user",
                                     "content": [{"type": "input_text", "text": text}]}})
                return "\n".join(json.dumps(r) for r in rows) + "\n"
            (day / "rollout-plain.jsonl").write_text(rollout("plain", "2026-09-01T10:00:00Z"), encoding="utf-8")
            (day / "rollout-old.jsonl.zst").write_bytes(zstd.compress(rollout("old", "2026-09-01T09:00:00Z").encode()))
            (day / "rollout-plain.jsonl.zst").write_bytes(zstd.compress(rollout("dup", "2026-09-01T10:00:00Z").encode()))
            got = {sid: [m[2] for m in msgs] for sid, _, msgs in harvest.read_codex(Path(tmp), 0, 4e9)}
        self.assertEqual(sorted(got), ["rollout-old", "rollout-plain"])
        self.assertEqual(got["rollout-old"], ["old"])

if __name__ == "__main__":
    unittest.main()

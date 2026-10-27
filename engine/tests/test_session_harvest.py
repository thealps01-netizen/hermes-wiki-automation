"""wiki_session_harvest.py's readers: the ways Hermes stores one message more than once, and unreadable histories.

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
import json
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


class ReaderFailures(unittest.TestCase):
    """A history that cannot be read raises instead of reading as empty, and nothing is silently clipped."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_malformed_claude_history_is_not_reported_as_an_empty_reader(self):
        claude = self.root / "claude"
        (claude / "project").mkdir(parents=True)
        (claude / "project/corrupt.jsonl").write_bytes(b"{broken historical message\n")
        with self.assertRaises(harvest.HarvestError):
            list(harvest.read_claude(claude, 0, float("inf")))

    def test_malformed_codex_history_is_not_reported_as_an_empty_reader(self):
        codex = self.root / "codex"
        (codex / "sessions").mkdir(parents=True)
        (codex / "sessions/corrupt.jsonl").write_bytes(b"{broken historical message\n")
        with self.assertRaises(harvest.HarvestError):
            list(harvest.read_codex(codex, 0, float("inf")))

    def test_antigravity_reader_preserves_utf8_and_refuses_decode_loss(self):
        root = self.root / "antigravity"
        log = root / "brain/utf8-fixture/.system_generated/logs/transcript_full.jsonl"
        log.parent.mkdir(parents=True)
        text = "Owner decision: caf\u00e9, \u0131, \u4e2d\u6587"
        valid = {"type": "USER_INPUT", "content": "<USER_REQUEST>" + text + "</USER_REQUEST>", "created_at": 100}
        log.write_bytes(json.dumps(valid, ensure_ascii=False).encode("utf-8") + b"\n")
        rows = list(harvest.read_antigravity(root, 0, 1000))
        self.assertEqual(rows[0][2], [(100.0, "user", text)])
        log.write_bytes(b'{"type":"USER_INPUT","content":"owner \xff bytes","created_at":100}\n')
        with self.assertRaises((UnicodeError, harvest.HarvestError)):
            list(harvest.read_antigravity(root, 0, 1000))
        log.write_bytes(json.dumps(valid).encode() + b'\n{"type":"USER_INPUT","content":"truncated owner decision\n')
        with self.assertRaises(harvest.HarvestError):
            list(harvest.read_antigravity(root, 0, 1000))

    def test_a_missing_folder_is_not_found_not_empty(self):
        for reader in (harvest.read_hermes, harvest.read_codex, harvest.read_claude, harvest.read_antigravity):
            with self.subTest(reader=reader.__name__), self.assertRaises(FileNotFoundError):
                list(reader(self.root / "absent", 0, 1000))

    def test_corrupt_old_cursors_are_not_a_first_run(self):
        path = self.root / "harvest-state.json"
        path.write_bytes(b"{broken")
        with self.assertRaises(harvest.HarvestError):
            harvest.load_state(path)
        self.assertEqual(path.read_bytes(), b"{broken")
        self.assertEqual(harvest.load_state(self.root / "absent.json"), {"cursors": {}})

    def test_user_text_is_not_silently_clipped(self):
        text = "u" * (harvest.USER_CLIP + 17)
        rendered, clip = harvest.render("Fixture", [(1, "user", text)], 10000)
        self.assertIn(text, "\n".join(rendered))


if __name__ == "__main__":
    unittest.main()

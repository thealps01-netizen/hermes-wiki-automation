import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import harvest_ledger as hl  # noqa: E402

ITEM = {'type': 'decision', 'claim': 'Raise the interval to 40.', 'quote': 'raise the interval to 40',
        'message_index': 3, 'later_use': 'Keep 40.', 'part': 1}


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'harvest-ledger.sqlite'
        self.clock = Clock()

    def tearDown(self):
        self.tmp.cleanup()

    def ledger(self):
        return hl.Ledger(self.path, clock=self.clock)

    def offer(self, ledger, through=50.0, digest='h1', after=None, cid='c1'):
        return ledger.offer('hermes', cid, after, through, [f'# part {digest}'], 'p1')


class NewConversations(Base):
    def test_a_new_conversation_becomes_one_pending_row_read_from_the_start(self):
        with self.ledger() as ledger:
            self.assertIsNone(ledger.tail_start('hermes', 'c1'))
            self.assertEqual(self.offer(ledger), 'queued')
            rows = ledger.rows()
        self.assertEqual([(r['status'], r['after'], r['through'], r['attempts']) for r in rows],
                         [('pending', None, 50.0, 0)])
        self.assertEqual((rows[0]['parts'], rows[0]['content_hash']), (['# part h1'], hl.content_hash(['# part h1'])))

    def test_a_claim_leases_the_row_and_counts_a_paid_attempt(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            row = ledger.claim('w1')
            self.assertEqual((row['status'], row['lease_worker'], row['attempts']), ('processing', 'w1', 1))
            self.assertIsNone(ledger.claim('w2'))

    def test_items_finish_the_row_as_done_and_move_the_tail(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            row = ledger.claim('w1')
            ledger.finish(row['id'], 'w1', [ITEM], ['one problem'], cost_usd=0.1, tokens_in=10, tokens_out=2)
            done = ledger.rows()[0]
            self.assertEqual(ledger.tail_start('hermes', 'c1'), 50.0)
        self.assertEqual((done['status'], done['items'], done['problems'], done['lease_worker']),
                         ('done', [ITEM], ['one problem'], None))
        self.assertEqual((done['cost_usd'], done['tokens_in'], done['tokens_out']), (0.1, 10, 2))

    def test_no_items_finish_the_row_as_empty(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            ledger.finish(ledger.claim('w1')['id'], 'w1', [], [])
            self.assertEqual(ledger.rows()[0]['status'], 'empty')
            self.assertEqual(ledger.tail_start('hermes', 'c1'), 50.0)


class GrowingConversations(Base):
    def finished(self, ledger):
        self.offer(ledger)
        ledger.finish(ledger.claim('w1')['id'], 'w1', [ITEM], [])

    def test_unchanged_content_after_done_queues_nothing(self):
        with self.ledger() as ledger:
            self.finished(ledger)
            self.assertEqual(self.offer(ledger, after=50.0, through=50.0), 'nothing_new')
            self.assertEqual(len(ledger.rows()), 1)

    def test_a_tail_after_done_becomes_a_new_row_for_the_tail_only(self):
        with self.ledger() as ledger:
            self.finished(ledger)
            self.assertEqual(self.offer(ledger, after=50.0, through=80.0, digest='h2'), 'queued')
            tail = ledger.rows()[1]
        self.assertEqual((tail['status'], tail['after'], tail['through'], tail['parts']),
                         ('pending', 50.0, 80.0, ['# part h2']))

    def test_a_tail_offered_from_the_wrong_start_is_refused(self):
        with self.ledger() as ledger:
            self.finished(ledger)
            with self.assertRaises(hl.LedgerError):
                self.offer(ledger, after=None, through=80.0, digest='h2')

    def test_growth_before_processing_updates_the_pending_row(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            self.assertEqual(self.offer(ledger, through=80.0, digest='h2'), 'updated')
            rows = ledger.rows()
        self.assertEqual([(r['through'], r['parts']) for r in rows], [(80.0, ['# part h2'])])

    def test_growth_while_processing_waits_for_the_running_row(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            ledger.claim('w1')
            self.assertEqual(self.offer(ledger, through=80.0, digest='h2'), 'busy')
            self.assertEqual(ledger.rows()[0]['through'], 50.0)


class Failures(Base):
    def test_a_retryable_failure_waits_until_its_retry_time(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            row = ledger.claim('w1')
            ledger.fail(row['id'], 'w1', 'rate limited', retry_at=1100.0, cost_usd=0.02)
            self.assertIsNone(ledger.claim('w1'))
            self.clock.now = 1100.0
            again = ledger.claim('w1')
        self.assertEqual((again['id'], again['attempts'], again['cost_usd'], again['last_error']),
                         (row['id'], 2, 0.02, 'rate limited'))

    def test_a_final_failure_is_an_error_that_blocks_the_conversation_until_retried(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            ledger.fail(ledger.claim('w1')['id'], 'w1', 'no JSON after repair')
            self.assertEqual(ledger.rows()[0]['status'], 'error')
            self.assertEqual(self.offer(ledger, through=80.0, digest='h2'), 'blocked')
            ledger.retry(ledger.rows()[0]['id'])
            self.assertEqual(ledger.rows()[0]['status'], 'pending')
            self.assertEqual(ledger.claim('w1')['attempts'], 1)

    def test_the_second_paid_attempt_is_the_last_even_when_retry_is_asked(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            ledger.fail(ledger.claim('w1')['id'], 'w1', 'overloaded', retry_at=1000.0)
            ledger.fail(ledger.claim('w1')['id'], 'w1', 'overloaded', retry_at=1000.0)
            row = ledger.rows()[0]
        self.assertEqual((row['status'], row['attempts'], row['last_error']), ('error', 2, 'overloaded'))

    def test_an_expired_lease_returns_the_row_then_errors_after_the_last_attempt(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            ledger.claim('w1')
            self.clock.now += hl.LEASE_SECONDS + 1
            second = ledger.claim('w2')
            self.assertEqual((second['lease_worker'], second['attempts']), ('w2', 2))
            self.clock.now += hl.LEASE_SECONDS + 1
            self.assertIsNone(ledger.claim('w3'))
            row = ledger.rows()[0]
        self.assertEqual(row['status'], 'error')
        self.assertIn('lease expired', row['last_error'])

    def test_only_the_lease_holder_may_finish_or_fail(self):
        with self.ledger() as ledger:
            self.offer(ledger)
            row = ledger.claim('w1')
            with self.assertRaises(hl.LedgerError):
                ledger.finish(row['id'], 'w2', [ITEM], [])
            with self.assertRaises(hl.LedgerError):
                ledger.fail(row['id'], 'w2', 'x')
            ledger.finish(row['id'], 'w1', [ITEM], [])
            with self.assertRaises(hl.LedgerError):
                ledger.finish(row['id'], 'w1', [ITEM], [])


class Store(Base):
    def test_finished_rows_wait_for_the_merger_once(self):
        with self.ledger() as ledger:
            self.offer(ledger, cid='a')
            self.offer(ledger, cid='b')
            self.offer(ledger, cid='c')
            ledger.finish(ledger.claim('w1')['id'], 'w1', [ITEM], [])
            ledger.finish(ledger.claim('w1')['id'], 'w1', [], [])
            waiting = ledger.unmerged()
            self.assertEqual([r['conversation'] for r in waiting], ['a', 'b'])
            ledger.mark_merged([r['id'] for r in waiting], 'night-1')
            self.assertEqual(ledger.unmerged(), [])
            self.assertEqual({r['merged'] for r in ledger.rows()}, {'night-1', None})
            with self.assertRaises(hl.LedgerError):
                ledger.mark_merged([ledger.rows()[2]['id']], 'night-1')

    def test_rows_survive_reopening(self):
        with self.ledger() as ledger:
            self.offer(ledger)
        with self.ledger() as ledger:
            self.assertEqual(len(ledger.rows()), 1)

    def test_summary_counts_rows_by_status_and_adds_cost(self):
        with self.ledger() as ledger:
            self.offer(ledger, cid='a')
            self.offer(ledger, cid='b')
            ledger.finish(ledger.claim('w1')['id'], 'w1', [ITEM], [], cost_usd=0.25)
            summary = ledger.summary()
        self.assertEqual(summary, {'counts': {'pending': 1, 'done': 1}, 'cost_usd': 0.25})

    def test_items_are_taken_one_by_one_and_a_row_is_merged_once_all_its_items_are(self):
        with self.ledger() as ledger:
            self.offer(ledger, cid='a')
            self.offer(ledger, cid='b')
            first = ledger.claim('w1')
            ledger.finish(first['id'], 'w1', [ITEM, dict(ITEM, claim='Second.')], [])
            second = ledger.claim('w1')
            ledger.finish(second['id'], 'w1', [ITEM], [])
            ledger.mark_items_merged([(first['id'], 0), (second['id'], 0)], 'night-1')
            self.assertEqual(ledger.merged_items(), {(first['id'], 0), (second['id'], 0)})
            self.assertEqual([r['conversation'] for r in ledger.unmerged()], ['a'])
            ledger.mark_items_merged([(first['id'], 1)], 'night-2')
            self.assertEqual(ledger.unmerged(), [])
            self.assertEqual([r['merged'] for r in ledger.rows()], ['night-2', 'night-1'])

    def test_an_item_cannot_be_taken_twice_or_from_an_unfinished_row(self):
        with self.ledger() as ledger:
            self.offer(ledger, cid='a')
            self.offer(ledger, cid='b')
            row = ledger.claim('w1')
            ledger.finish(row['id'], 'w1', [ITEM, ITEM], [])
            ledger.mark_items_merged([(row['id'], 0)], 'night-1')
            for pairs in ([(row['id'], 0)], [(row['id'], 2)], [(ledger.rows()[1]['id'], 0)]):
                with self.assertRaises(hl.LedgerError):
                    ledger.mark_items_merged(pairs, 'night-2')
            self.assertEqual(ledger.merged_items(), {(row['id'], 0)})

    def test_the_collector_mark_is_kept_between_runs(self):
        with self.ledger() as ledger:
            self.assertIsNone(ledger.get_meta('collected_until'))
            ledger.set_meta('collected_until', 123.5)
        with self.ledger() as ledger:
            self.assertEqual(ledger.get_meta('collected_until'), 123.5)

    def test_a_first_version_ledger_is_upgraded_in_place_and_keeps_its_rows(self):
        db = sqlite3.connect(self.path)
        db.execute('CREATE TABLE conversations (id INTEGER PRIMARY KEY, agent TEXT NOT NULL,'
                   ' conversation TEXT NOT NULL, after REAL, through REAL NOT NULL, content_hash TEXT NOT NULL,'
                   ' prompt_version TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,'
                   ' last_error TEXT, next_attempt_at REAL, lease_worker TEXT, lease_started REAL,'
                   ' tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,'
                   ' cost_usd REAL NOT NULL DEFAULT 0, parts TEXT NOT NULL, items TEXT, problems TEXT, merged TEXT,'
                   ' created REAL NOT NULL, updated REAL NOT NULL)')
        db.execute("INSERT INTO conversations (agent, conversation, through, content_hash, prompt_version, status,"
                   " parts, items, created, updated) VALUES ('hermes', 'a', 5, 'h', 'p', 'done', '[]', '[]', 1, 1)")
        db.execute('PRAGMA user_version=1')
        db.commit()
        db.close()
        with self.ledger() as ledger:
            self.assertEqual([r['conversation'] for r in ledger.rows()], ['a'])
            self.assertEqual(ledger.merged_items(), set())
        db = sqlite3.connect(self.path)
        self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], hl.SCHEMA_VERSION)
        db.close()

    def test_a_foreign_database_is_refused_and_left_untouched(self):
        db = sqlite3.connect(self.path)
        db.execute('CREATE TABLE other (x)')
        db.commit()
        db.close()
        before = self.path.read_bytes()
        with self.assertRaises(hl.LedgerError):
            with self.ledger():
                pass
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

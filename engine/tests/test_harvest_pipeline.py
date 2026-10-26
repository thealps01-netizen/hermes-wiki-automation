import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import harvest_ledger as hl  # noqa: E402
import harvest_pipeline as hp  # noqa: E402

ITEM = {'type': 'decision', 'claim': 'Raise the interval to 40.', 'quote': 'raise the interval to 40',
        'message_index': 1, 'later_use': 'Keep 40.', 'part': 1}
FIRST = [(100.0, 'user', 'why do so many skill suggestions arrive'),
         (110.0, 'assistant', 'Background review proposes skills after every reply.')]
LATER = (200.0, 'user', 'then raise the interval to 40')


def result(items=(), error=None, retryable=False, cost=0.05):
    return {'items': list(items), 'problems': [], 'error': error, 'retryable': retryable,
            'cost_usd': cost, 'tokens_in': 1000, 'tokens_out': 50}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = hl.Ledger(Path(self.tmp.name) / 'ledger.sqlite', clock=lambda: 1000.0).__enter__()

    def tearDown(self):
        self.ledger.__exit__()
        self.tmp.cleanup()

    def collect(self, *conversations):
        return hp.collect(self.ledger, conversations, max_chars=60000, prompt_version='p1')


class Collect(Base):
    def test_a_new_conversation_is_queued_as_rendered_parts(self):
        counts = self.collect(('hermes', 's1', 'Skill suggestions', FIRST))
        rows = self.ledger.rows()
        self.assertEqual(counts, {'queued': 1})
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['parts'][0].startswith('# Skill suggestions'))
        self.assertIn('Background review proposes skills', rows[0]['parts'][0])
        self.assertEqual((rows[0]['through'], rows[0]['prompt_version']), (110.0, 'p1'))

    def test_collecting_the_same_messages_again_queues_nothing(self):
        self.collect(('hermes', 's1', 'Skill suggestions', FIRST))
        counts = self.collect(('hermes', 's1', 'Skill suggestions', FIRST))
        self.assertEqual(counts, {'nothing_new': 1})
        self.assertEqual(len(self.ledger.rows()), 1)

    def test_after_a_finished_row_only_the_new_messages_are_queued(self):
        self.collect(('hermes', 's1', 'Skill suggestions', FIRST))
        row = self.ledger.claim('w')
        self.ledger.finish(row['id'], 'w', [ITEM], [])
        self.collect(('hermes', 's1', 'Skill suggestions', FIRST + [LATER]))
        tail = self.ledger.rows()[1]
        self.assertEqual((tail['after'], tail['through']), (110.0, 200.0))
        self.assertIn('raise the interval to 40', tail['parts'][0])
        self.assertNotIn('Background review', tail['parts'][0])

    def test_a_conversation_with_nothing_the_owner_or_assistant_said_is_not_queued(self):
        counts = self.collect(('hermes', 's2', 'Empty', [(100.0, 'assistant', '   ')]))
        self.assertEqual(counts, {'nothing_to_read': 1})
        self.assertEqual(self.ledger.rows(), [])


class Process(Base):
    def queue(self, *ids):
        for cid in ids:
            self.collect(('hermes', cid, cid, FIRST))

    def test_items_finish_the_row_with_its_cost_and_tokens(self):
        self.queue('a')
        report = hp.process(self.ledger, lambda parts: result([ITEM]), 'w')
        row = self.ledger.rows()[0]
        self.assertEqual((row['status'], row['items'], row['cost_usd'], row['tokens_in']), ('done', [ITEM], 0.05, 1000))
        self.assertEqual(report, {'done': 1, 'empty': 0, 'error': 0, 'waiting': 0, 'cost_usd': 0.05, 'stopped': None})

    def test_extractor_receives_the_stored_parts(self):
        self.queue('a')
        seen = []
        hp.process(self.ledger, lambda parts: seen.append(parts) or result(), 'w')
        self.assertEqual(seen, [self.ledger.rows()[0]['parts']])
        self.assertEqual(self.ledger.rows()[0]['status'], 'empty')

    def test_an_invalid_reply_marks_that_row_error_and_the_next_row_is_still_read(self):
        self.queue('a', 'b')
        answers = [result(error='part 1: no JSON'), result([ITEM])]
        report = hp.process(self.ledger, lambda parts: answers.pop(0), 'w')
        self.assertEqual([r['status'] for r in self.ledger.rows()], ['error', 'done'])
        self.assertEqual(self.ledger.rows()[0]['last_error'], 'part 1: no JSON')
        self.assertEqual((report['error'], report['done']), (1, 1))

    def test_a_failed_call_stops_the_night_and_leaves_the_row_waiting_for_a_retry(self):
        self.queue('a', 'b')
        calls = []
        report = hp.process(self.ledger, lambda parts: calls.append(1) or result(error='overloaded', retryable=True), 'w')
        rows = self.ledger.rows()
        self.assertEqual(len(calls), 1)
        self.assertEqual([(r['status'], r['attempts']) for r in rows], [('pending', 1), ('pending', 0)])
        self.assertEqual(rows[0]['next_attempt_at'], 1000.0 + hp.RETRY_AFTER_SECONDS)
        self.assertEqual((report['waiting'], report['stopped']), (1, 'call failed: overloaded'))

    def test_the_cost_cap_stops_before_the_next_paid_conversation(self):
        self.queue('a', 'b', 'c')
        report = hp.process(self.ledger, lambda parts: result([ITEM], cost=0.3), 'w', cap_usd=0.5)
        self.assertEqual([r['status'] for r in self.ledger.rows()], ['done', 'done', 'pending'])
        self.assertIn('cap', report['stopped'])
        self.assertAlmostEqual(report['cost_usd'], 0.6)


if __name__ == '__main__':
    unittest.main()

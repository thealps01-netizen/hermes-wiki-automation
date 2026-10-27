import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import harvest_ledger as hl  # noqa: E402
import harvest_merge as hm  # noqa: E402
import harvest_night as hn  # noqa: E402
from test_harvest_merge import DECISION, PAGE, RULES, TARGET, UPDATED, draft_reply  # noqa: E402

ROUTE = json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})
GOOD = draft_reply({'kind': 'update', 'summary': 's', 'why': 'w'}, UPDATED)


class Night(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.wiki, self.inbox, self.nights = root / 'wiki', root / 'inbox', root / 'nights'
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir(parents=True)
        (self.wiki / 'raw/sources' / TARGET).write_text(PAGE, encoding='utf-8', newline='\n')
        self.ledger = hl.Ledger(root / 'ledger.sqlite', clock=lambda: 1761436800.0).__enter__()
        self.settings = dict(hn.DEFAULTS)

    def tearDown(self):
        self.ledger.__exit__()
        self.tmp.cleanup()

    def queue(self, *cids):
        for cid in cids:
            self.ledger.offer('hermes', cid, None, 1761436800.0, [f'# Conversation {cid}\n\n### user · x\n\nhi\n'], 'p1')

    def night(self, extract, merge, night='n1', **kwargs):
        return hn.run_night(self.ledger, extract=extract, merge_caller=merge, wiki=self.wiki, inbox=self.inbox,
                            nights=self.nights, rules_text=RULES, night=night, today='2026-10-26',
                            settings=self.settings, **kwargs)

    @staticmethod
    def extracted(items, cost=0.1):
        return lambda parts: {'items': items, 'problems': [], 'error': None, 'cost_usd': cost,
                              'tokens_in': 1, 'tokens_out': 1}

    @staticmethod
    def merger(replies, cost=0.1):
        calls = []

        def call(prompt):
            calls.append(prompt)
            return replies[len(calls) - 1], {'cost_usd': cost}
        return call, calls

    def test_a_night_reads_merges_and_puts_the_draft_in_the_review_inbox(self):
        self.queue('a')
        merge, calls = self.merger([ROUTE, GOOD])
        report = self.night(self.extracted([DECISION]), merge)
        self.assertEqual(report['read']['done'], 1)
        self.assertEqual(len(report['merge']['candidates']), 1)
        self.assertTrue((self.inbox / 'n1/candidates/2026-10-14-skill-suggestions/candidate.json').is_file())
        self.assertTrue((self.nights / 'n1/report.json').is_file())
        self.assertFalse((self.inbox / 'n1/replies').exists())
        self.assertEqual(self.ledger.unmerged(), [])

    def test_reading_leaves_part_of_the_cap_for_merging(self):
        # cap 1.0: reading may spend 0.7, so the third 0.3 conversation waits; merging still runs.
        self.settings['cap_usd'] = 1.0
        self.queue('a', 'b', 'c')
        merge, calls = self.merger([ROUTE, GOOD])
        report = self.night(self.extracted([DECISION], cost=0.3), merge)
        self.assertEqual((report['read']['done'], [r['status'] for r in self.ledger.rows()][-1]), (2, 'pending'))
        self.assertIn('cap', report['stopped'])
        self.assertEqual(len(calls), 2)

    def test_reading_leaves_part_of_the_time_for_merging(self):
        self.settings['minutes'] = 10   # 600 s; reading may use 420 s: four 100 s reads end by 400 s
        self.queue('a', 'b', 'c', 'd', 'e')
        now = [0.0]

        def extract(parts):
            now[0] += 100
            return self.extracted([DECISION])(parts)
        merge, calls = self.merger([ROUTE, GOOD])
        report = self.night(extract, merge, clock=lambda: now[0])
        self.assertEqual(report['read']['done'], 4)
        self.assertEqual(len(calls), 2)

    def test_a_page_with_a_draft_waiting_in_review_is_not_drafted_again(self):
        waiting = self.inbox / 'older/candidates/2026-10-14-skill-suggestions'
        waiting.mkdir(parents=True)
        (waiting / 'candidate.json').write_text(json.dumps({'kind': 'update', 'target': TARGET}), encoding='utf-8')
        self.queue('a')
        merge, calls = self.merger([ROUTE])
        report = self.night(self.extracted([DECISION]), merge)
        self.assertEqual(report['merge']['waiting_on_review'], [{'target': TARGET, 'items': ['I1']}])
        self.assertEqual(len(calls), 1)
        self.assertFalse((self.inbox / 'n1').exists())
        self.assertEqual(len(self.ledger.unmerged()), 1)

    def test_an_approved_draft_no_longer_holds_its_page(self):
        approved = self.inbox / 'older/candidates/2026-10-14-skill-suggestions'
        approved.mkdir(parents=True)
        (approved / 'candidate.json').write_text(json.dumps({'kind': 'update', 'target': TARGET}), encoding='utf-8')
        (approved / 'applied.json').write_text('{}', encoding='utf-8')
        self.assertEqual(hn.busy_targets(self.inbox), set())

    def test_nothing_new_makes_no_merge_call_and_no_inbox_folder(self):
        report = self.night(self.extracted([]), lambda prompt: self.fail('no call expected'))
        self.assertIsNone(report['merge'])
        self.assertFalse(self.inbox.exists())

    def test_a_failed_reading_call_stops_the_night_before_merging(self):
        # 'a' is read, then the provider fails on 'b': merging 'a' now would only pay into the same outage.
        self.queue('a', 'b')
        replies = [self.extracted([DECISION])(None),
                   {'items': None, 'problems': [], 'error': 'overloaded', 'retryable': True,
                    'cost_usd': 0.0, 'tokens_in': 0, 'tokens_out': 0}]
        report = self.night(lambda parts: replies.pop(0), lambda prompt: self.fail('no merge after a failed call'))
        self.assertEqual(report['read']['done'], 1)
        self.assertIn('call failed', report['stopped'])


class Start(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = hl.Ledger(Path(self.tmp.name) / 'ledger.sqlite').__enter__()

    def tearDown(self):
        self.ledger.__exit__()
        self.tmp.cleanup()

    def test_the_first_run_starts_each_agent_where_the_packed_harvest_stopped_it(self):
        # An agent whose cursor never moved (codex: not installed) must not pull every other agent back.
        since = hn.since_for(self.ledger, hn.DEFAULTS, {'hermes': 500.0, 'codex': 300.0}, 10 * 86400, 2)
        self.assertEqual((since['hermes'], since['codex'], since['claude']), (500.0, 300.0, 8 * 86400))

    def test_a_configured_start_wins_over_the_packed_harvest_cursor(self):
        settings = dict(hn.DEFAULTS, start='1970-01-01T00:10:00+00:00')
        self.assertEqual(hn.since_for(self.ledger, settings, {'hermes': 500.0}, 10_000, 2)['hermes'], 600.0)

    def test_without_any_cursor_the_first_run_reads_the_last_days(self):
        self.assertEqual(hn.since_for(self.ledger, hn.DEFAULTS, {}, 10 * 86400, 2)['hermes'], 8 * 86400)

    def test_later_runs_continue_from_the_last_collection_with_an_overlap(self):
        self.ledger.set_meta('collected_until', 100_000.0)
        self.assertEqual(hn.since_for(self.ledger, hn.DEFAULTS, {'hermes': 5.0}, 200_000, 2)['codex'],
                         100_000.0 - hn.OVERLAP_SECONDS)


class Entry(unittest.TestCase):
    def test_arguments_are_refused_before_any_setting_is_read(self):
        # The real settings are never reached: if the argument check broke, loading them fails the test
        # instead of starting a real (paid) night.
        from unittest import mock
        with mock.patch('wikiconfig.load', side_effect=AssertionError('settings must not be read')):
            self.assertEqual(hn.main(['--now']), 1)
            self.assertEqual(hn.main(['--status', '--now']), 1)


class Record(unittest.TestCase):
    """The night's record (night.json) and the read-only status the panel's Harvest card shows."""

    def setUp(self):
        from unittest import mock
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.audit, self.home = root / 'audit', root / 'home'
        self.audit.mkdir()
        for folder in ('hermes', '.codex/sessions', '.claude/projects'):
            (self.home / folder).mkdir(parents=True)
        self.cfg = {'harvest': {'agents': {'antigravity': False}}}
        self.patches = [mock.patch('wikiconfig.audit_dir', return_value=self.audit),
                        mock.patch('wikiconfig.hermes_home', return_value=self.home / 'hermes'),
                        mock.patch('pathlib.Path.home', return_value=self.home),
                        mock.patch.dict('os.environ', {'CODEX_HOME': '', 'CLAUDE_CONFIG_DIR': ''})]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def files(self):
        return sorted(str(path.relative_to(self.audit)) for path in self.audit.rglob('*'))

    def test_status_before_any_night_reads_the_packed_harvest_cursors_and_writes_nothing(self):
        (self.audit / 'harvest-state.json').write_text(json.dumps({'cursors': {'hermes': 1000.0}}), encoding='utf-8')
        before = self.files()
        out = hn.status(self.cfg)
        self.assertEqual(self.files(), before, 'status created a file (the ledger or a night folder)')
        rows = {row['id']: row for row in out['agents']}
        self.assertEqual(rows['hermes']['cursor'], hn.stamp(1000.0))
        self.assertTrue(rows['codex']['cursor'].startswith('none (first run looks back'))
        self.assertEqual((rows['antigravity']['enabled'], rows['codex']['found']), (False, True))
        self.assertIsNone(out['last_night'])

    def test_status_after_a_night_shows_the_ledger_point_and_the_newest_record(self):
        with hl.Ledger(self.audit / 'harvest-ledger.sqlite') as ledger:
            ledger.set_meta('collected_until', 5000.0)
        (self.audit / 'harvest-state.json').write_text(json.dumps({'cursors': {'hermes': 1000.0}}), encoding='utf-8')
        nights = self.audit / 'harvest-nights'
        hn.write_record(nights, '20261026-213000-aaaaaaaaaaaa', {'ok': True, 'agents': {}}, 10.0, 20.0)
        hn.write_record(nights, '20261027-213000-bbbbbbbbbbbb',
                        {'ok': True, 'agents': {'codex': 'not found (sessions not found)'},
                         'read': {'cost_usd': 1.25}, 'merge': {'cost_usd': 2.5, 'candidates': []},
                         'stopped': 'time limit reached; the rest waits for the next night'}, 100.0, 2700.0)
        (nights / '20261028-213000-cccccccccccc').mkdir()
        before = self.files()
        out = hn.status(self.cfg)
        self.assertEqual(self.files(), before)
        rows = {row['id']: row for row in out['agents']}
        self.assertEqual({row['cursor'] for row in out['agents']}, {hn.stamp(5000.0)})
        self.assertFalse(rows['codex']['found'], 'a source last night could not find counts as not found')
        self.assertTrue(rows['claude']['found'])
        night = out['last_night']
        self.assertEqual(night['night'], '20261027-213000-bbbbbbbbbbbb', 'a folder without a record was taken')
        self.assertEqual((night['cost_usd'], night['started'], night['finished']), (3.75, hn.stamp(100.0), hn.stamp(2700.0)))

    def test_a_record_that_names_another_night_is_refused(self):
        nights = self.audit / 'harvest-nights'
        hn.write_record(nights, '20261027-213000-bbbbbbbbbbbb', {'ok': True}, 1.0, 2.0)
        record = nights / '20261027-213000-bbbbbbbbbbbb' / hn.RECORD
        record.write_text(json.dumps({'night': 'other'}), encoding='utf-8')
        with self.assertRaises(ValueError):
            hn.status(self.cfg)

    def night_main(self, run_night):
        from unittest import mock
        import harvest_extract as hx
        import harvest_pipeline as hp
        with mock.patch('wikiconfig.load', return_value=self.cfg), \
                mock.patch('wikiconfig.project_root', return_value=self.home / 'wiki'), \
                mock.patch('shutil.which', return_value='hermes'), \
                mock.patch.object(hx, 'hermes_caller', return_value=None), \
                mock.patch.object(hp, 'owner_rules', return_value=[]), \
                mock.patch.object(hp, 'found_conversations', return_value=iter([])), \
                mock.patch.object(hn, 'run_night', side_effect=run_night):
            code = hn.main([])
        records = sorted((self.audit / 'harvest-nights').glob(f'*/{hn.RECORD}'))
        self.assertEqual(len(records), 1)
        return code, json.loads(records[0].read_bytes())

    def test_a_finished_night_keeps_its_report_and_whole_cost(self):
        code, record = self.night_main(lambda *a, **k: {
            'read': {'cost_usd': 0.5}, 'merge': {'cost_usd': 1.0, 'candidates': [{}]}, 'stopped': None})
        self.assertEqual(code, 0)
        self.assertEqual((record['ok'], record['cost_usd']), (True, 1.5))
        self.assertEqual(record['night'], record['night'].strip())
        self.assertIn('ledger', record)

    def test_a_night_that_failed_after_it_started_still_leaves_its_record(self):
        def boom(*args, **kwargs):
            raise hm.MergeError('merge reply unreadable')
        code, record = self.night_main(boom)
        self.assertEqual(code, 1)
        self.assertEqual((record['ok'], record['error'], record['cost_usd']), (False, 'merge reply unreadable', 0.0))


if __name__ == '__main__':
    unittest.main()

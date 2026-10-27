"""A stale update draft is re-derived onto the page as it is now and reviewed again, using synthetic sources."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wiki_candidates as candidates
from test_draft_adapter import submit

TARGET = '2026-10-06-fixture.md'
LIVE = ('# Fixture\n\n## Scope\n\nPanels.\n\n## Decisions\n\n'
        '**1. One route per panel.**\n- Why: owner.\n- Evidence: kept-code.\n\n'
        '**2. The repository stays.**\n- Why: owner.\n- Evidence: none (owner-directed, 2026-10-01).\n\n'
        '## Changed decisions\n\n- "Two panels" -> one panel (decision 2).\n')
APPROVED = LIVE.replace('## Changed decisions', '**3. Metro layout.**\n- Why: owner.\n'
                        + ''.join(f'- Metro line {i}.\n' for i in range(30))
                        + '- Evidence: other-code.\n\n## Changed decisions')
STALE = LIVE.replace('**2. The repository stays.**', '**2. The repository was deleted on 2026-10-17.**')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RederiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.wiki, self.inbox = root / 'wiki', root / 'data/inbox'
        (self.wiki / '.llm-wiki').mkdir(parents=True)
        (self.wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
        (self.wiki / 'raw/sources').mkdir(parents=True)
        for value in ('kept-code', 'other-code'):
            (self.wiki / f'raw/evidence/{value}').mkdir(parents=True)
            (self.wiki / f'raw/evidence/{value}/manifest.json').write_text(
                json.dumps({'schema': 1, 'evidence_id': value, 'used_by': []}))
        self.target = self.wiki / 'raw/sources' / TARGET
        self.target.write_bytes(LIVE.encode())
        run = self.inbox / '20261022-012328-run'
        run.mkdir(parents=True)
        self.ref = submit(self.wiki, run, 'watchdog-repository-deleted', dict(
            kind='update', target=TARGET, summary='Repository deleted', why='Owner said so',
            evidence_ids=['kept-code'], base_sha256=sha(LIVE.encode())), STALE)
        self.original = self.inbox / '20261022-012328-run/candidates/watchdog-repository-deleted'

    def listed(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            candidates.cmd_list(self.inbox, True, wiki=self.wiki)
        return json.loads(out.getvalue())

    def approve_other_draft(self, text=APPROVED):
        self.target.write_bytes(text.encode())

    def test_an_update_draft_keeps_the_page_it_was_written_from(self):
        self.assertEqual((self.original / 'base.md').read_bytes(), LIVE.encode())

    def test_a_stale_update_is_rederived_onto_the_current_page(self):
        self.approve_other_draft()
        rows = self.listed()
        self.assertEqual([r.get('derived_from') for r in rows], [self.ref])
        derived = self.inbox / rows[0]['ref'].replace('/', '/candidates/')
        meta = json.loads((derived / 'candidate.json').read_bytes())
        self.assertEqual(meta['base_sha256'], sha(APPROVED.encode()))
        self.assertEqual(meta['derived_from']['ref'], self.ref)
        self.assertEqual(meta['derived_from']['base_sha256'], sha(LIVE.encode()))
        self.assertEqual(meta['evidence_ids'], ['kept-code', 'other-code'])
        text = (derived / 'source.md').read_text(encoding='utf-8')
        self.assertIn('Metro line 29.', text)
        self.assertIn('was deleted on 2026-10-17', text)
        self.assertNotIn('The repository stays.', text)
        self.assertEqual((derived / 'base.md').read_bytes(), APPROVED.encode())
        candidates.review_snapshot(self.wiki, self.inbox, rows[0]['ref'])
        self.assertIsNone(candidates.approval_preflight(self.wiki, self.inbox, rows[0]['ref']))

    def test_the_stale_original_still_cannot_be_approved(self):
        self.approve_other_draft()
        self.listed()
        with self.assertRaisesRegex(candidates.Refused, 'stale'):
            candidates.review_snapshot(self.wiki, self.inbox, self.ref)

    def test_rederivation_is_idempotent(self):
        self.approve_other_draft()
        first, second = self.listed(), self.listed()
        self.assertEqual(first, second)
        self.assertEqual(len(list((self.original.parent).iterdir())), 2)

    def test_a_conflict_is_shown_on_the_original_and_nothing_is_derived(self):
        self.approve_other_draft(LIVE.replace('**2. The repository stays.**', '**2. The repository is archived.**'))
        rows = self.listed()
        self.assertEqual([r['ref'] for r in rows], [self.ref])
        self.assertIn('both', rows[0]['stale'])
        self.assertEqual(len(rows[0]['conflicts']), 1)
        self.assertEqual(len(list(self.original.parent.iterdir())), 1)

    def test_without_the_page_it_was_written_from_the_draft_stays_refused_with_a_reason(self):
        (self.original / 'base.md').unlink()
        self.approve_other_draft()
        rows = self.listed()
        self.assertEqual([r['ref'] for r in rows], [self.ref])
        self.assertIn('not kept', rows[0]['stale'])

    def test_the_page_it_was_written_from_is_recovered_from_an_applied_operation(self):
        (self.original / 'base.md').unlink()
        operation = self.inbox.parent / 'operations' / ('a' * 64)
        operation.mkdir(parents=True)
        (operation / 'base.md').write_bytes(LIVE.encode())
        self.approve_other_draft()
        self.assertEqual([r.get('derived_from') for r in self.listed()], [self.ref])

    def test_a_rejected_rederivation_does_not_bring_the_original_back(self):
        self.approve_other_draft()
        derived = self.inbox / self.listed()[0]['ref'].replace('/', '/candidates/')
        rejected = self.inbox / 'rejected' / f'20261022-012328-run-{derived.name}'
        rejected.parent.mkdir(parents=True)
        shutil.move(str(derived), str(rejected))
        self.assertEqual(self.listed(), [])

    def test_a_second_change_rederives_from_the_original_draft(self):
        self.approve_other_draft()
        first = self.listed()[0]['ref']
        self.approve_other_draft(APPROVED.replace('Panels.\n', 'Panels and the metro map.\n'))
        rows = self.listed()
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0]['ref'], first)
        self.assertEqual(rows[0]['derived_from'], self.ref)
        text = (self.inbox / rows[0]['ref'].replace('/', '/candidates/') / 'source.md').read_text(encoding='utf-8')
        self.assertIn('Panels and the metro map.', text)
        self.assertIn('was deleted on 2026-10-17', text)

    def test_the_derived_draft_applies_only_with_its_own_owner_approval(self):
        from candidate_apply import ApplyRefused, apply_candidate
        from owner_decisions import OwnerDecisions
        from workflow_store import WorkflowStore
        data = self.inbox.parent

        def approve(ref):
            snapshot = candidates.review_snapshot(self.wiki, self.inbox, ref)
            with OwnerDecisions(data, initialize=True) as authority:
                request = authority.prepare(snapshot, 'fixture-owner')
                return snapshot, authority.confirm(request['request_id'], snapshot, 'fixture-owner')

        old_snapshot, old_approval = approve(self.ref)
        self.approve_other_draft()
        derived = self.listed()[0]['ref']
        with WorkflowStore(data / 'workflow.sqlite') as store:
            for ref in (self.ref, derived):
                with self.subTest(old_approval_for=ref), self.assertRaises((ApplyRefused, candidates.Refused)):
                    apply_candidate(self.wiki, self.inbox, ref, old_snapshot, old_approval, store)
            self.assertEqual(self.target.read_bytes(), APPROVED.encode())
            snapshot, approval = approve(derived)
            self.assertEqual(apply_candidate(self.wiki, self.inbox, derived, snapshot, approval, store)['state'], 'applied')
        merged = (self.inbox / derived.replace('/', '/candidates/') / 'source.md').read_bytes()
        self.assertEqual(self.target.read_bytes(), merged)
        self.assertEqual(self.listed(), [])

    def test_listing_without_a_wiki_changes_nothing(self):
        self.approve_other_draft()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            candidates.cmd_list(self.inbox, True)
        self.assertEqual([r['ref'] for r in json.loads(out.getvalue())], [self.ref])
        self.assertEqual(len(list(self.original.parent.iterdir())), 1)


if __name__ == '__main__':
    unittest.main()

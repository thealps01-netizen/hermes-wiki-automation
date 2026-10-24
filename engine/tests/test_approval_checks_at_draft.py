"""An approval refusal is known before approval: at submission (the harvest fixes it) and in the review."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_evidence_requests as base

RELEASED = ('# Fixture\n\n## Decisions\n\n**1. The panel has a settings page. Released as 4.4.0.**\n'
            '- Why: owner.\n- Evidence: none (owner-directed, 2026-10-20).\n')
WITHOUT_NUMBER = RELEASED.replace(' Released as 4.4.0.', '')
BARE_FINDING = WITHOUT_NUMBER + '\n## Findings\n\n**F1. Tool renders 8 angles.**\n- Evidence: none (method).\n'


class ApprovalChecksAtDraftAndReview(unittest.TestCase):
    tearDown = base.EvidenceRequestTests.tearDown
    files = base.EvidenceRequestTests.files
    approve_dry = base.EvidenceRequestTests.approve_dry

    def setUp(self):
        base.EvidenceRequestTests.setUp(self)
        self.plain = dict(kind='new', target='2026-10-20-fixture.md', summary='Fixture', why='Owner choice',
                          evidence_ids=[])

    def show(self, ref):
        import wiki_candidates
        with contextlib.redirect_stdout(io.StringIO()) as out:
            wiki_candidates.cmd_show(self.wiki, self.inbox, ref, True)
        return json.loads(out.getvalue())

    def test_a_draft_approval_would_refuse_is_refused_at_submission_and_names_the_decision(self):
        import draft_adapter
        before = self.files()
        for text, rule, named in ((RELEASED, 'pinned version', 'Released as 4.4.0'),
                                  (BARE_FINDING, 'no retained evidence', 'Tool renders 8 angles')):
            with self.subTest(rule=rule):
                with self.assertRaisesRegex(draft_adapter.DraftRefused, rule) as caught:
                    self.adapter.submit('fixture', self.plain, text)
                self.assertIn('fix it and submit again', str(caught.exception))
                self.assertIn(named, str(caught.exception))
        self.assertEqual(self.files(), before)

    def test_the_same_decision_without_the_release_number_is_drafted_and_approvable(self):
        ref = self.adapter.submit('fixture', self.plain, WITHOUT_NUMBER)
        shown = self.show(ref)
        self.assertIsNone(shown['approval_refusal'])
        self.assertEqual(self.approve_dry()[0], 0)

    def test_a_stored_draft_that_approval_refuses_shows_the_reason_in_the_review(self):
        folder = self.run / 'candidates/fixture'
        folder.mkdir(parents=True)
        (folder / 'candidate.json').write_text(json.dumps(self.plain))
        (folder / 'source.md').write_text(RELEASED, encoding='utf-8', newline='\n')
        before = self.files()
        shown = self.show('fixture-run/fixture')
        self.assertIn('pinned version', shown['approval_refusal'])
        self.assertIn('The panel has a settings page. Released as 4.4.0.', shown['approval_refusal'])
        self.assertEqual(self.files(), before)

    def test_a_pending_request_is_the_reason_shown_until_it_is_fetched(self):
        ref = self.adapter.submit('fixture', self.metadata, self.source_with_request())
        self.assertIn('not fetched yet', self.show(ref)['approval_refusal'])

    def source_with_request(self):
        return base.SOURCE


if __name__ == '__main__':
    unittest.main()

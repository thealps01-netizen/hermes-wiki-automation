"""Evidence requests: the harvest names a public copy, only the owner's fetch downloads it."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SHA = 'd923a5eb487a17c0a68801bba9ef0f56c81040a8'
CODE = b'def plan():\n    # Pinned/manual/drift/pip are never auto-applied\n    return []\n'
REQUEST = {'id': 'fixture-pin-code', 'supports': 'Pinned plugins take no automatic update.',
           'github': [f'owner/repo@{SHA}:cli/cadence.py'],
           'passages': ['Pinned/manual/drift/pip are never auto-applied']}
SOURCE = ('# Fixture\n\n## Decisions\n\n**1. Fixture.**\nWhy: owner.\nEvidence: none (owner-directed, 2026-10-20).\n\n'
          '## Findings\n\n**F1. Pinned plugins take no automatic update (repo d923a5e).**\n'
          '- Evidence: fixture-pin-code\n\n## Evidence\n\n| id | source | pinned at | backs |\n|---|---|---|---|\n'
          '| fixture-pin-code | owner/repo cli/cadence.py | d923a5e | F1 |\n')


class EvidenceRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        root = Path(self.temp.name)
        self.wiki, self.inbox = root / 'wiki', root / 'data/inbox'
        (self.wiki / '.llm-wiki').mkdir(parents=True)
        (self.wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir(parents=True)
        self.run = self.inbox / 'fixture-run'
        self.run.mkdir(parents=True)
        self.metadata = dict(kind='new', target='2026-10-20-fixture.md', summary='Fixture', why='Owner choice',
                             evidence_ids=['fixture-pin-code'], evidence_requests=[REQUEST])

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, name, metadata, source):
        from test_draft_adapter import submit
        return submit(self.wiki, self.run, name, metadata, source)

    def files(self):
        root = Path(self.temp.name)
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def network(self, code=CODE):
        import evidence_capture
        calls = []
        def raw(repo, path, ref):
            calls.append((repo, path, ref))
            return code
        return calls, contextlib.ExitStack(), [
            mock.patch.object(evidence_capture, 'resolve_sha', lambda repo, ref: SHA),
            mock.patch.object(evidence_capture, 'gh_raw', raw),
            mock.patch.object(evidence_capture, 'repo_license', lambda repo, sha: ('MIT', b'MIT licence\n')),
            mock.patch.object(evidence_capture, 'http_get', mock.Mock(side_effect=AssertionError('no web fetch'))),
        ]

    def fetch(self, digest, code=CODE):
        import evidence_requests
        calls, stack, patches = self.network(code)
        with stack:
            for item in patches:
                stack.enter_context(item)
            return calls, evidence_requests.fetch(self.wiki, self.inbox, 'fixture-run/fixture', digest)

    def approve_dry(self):
        import wiki_candidates
        with contextlib.redirect_stdout(io.StringIO()) as out:
            return wiki_candidates.cmd_approve(self.wiki, self.inbox, 'fixture-run/fixture', True), out.getvalue()

    def test_a_finding_with_a_request_is_drafted_and_waits_for_the_owner_fetch(self):
        import wiki_candidates
        ref = self.submit('fixture', self.metadata, SOURCE)
        stored = json.loads((self.run / 'candidates/fixture/candidate.json').read_bytes())
        self.assertEqual(stored['evidence_requests'], [REQUEST])
        snapshot = wiki_candidates.review_snapshot(self.wiki, self.inbox, ref)
        self.assertEqual(snapshot['pending_evidence'], ['fixture-pin-code'])
        self.assertFalse((self.run / 'candidates/fixture/evidence').exists(), 'drafting fetched something')
        with self.assertRaisesRegex(wiki_candidates.Refused, 'not fetched yet.*fixture-pin-code'):
            self.approve_dry()

    def test_the_owner_fetch_stores_the_verified_copy_and_approval_then_passes(self):
        import wiki_candidates
        ref = self.submit('fixture', self.metadata, SOURCE)
        before = wiki_candidates.review_snapshot(self.wiki, self.inbox, ref)
        calls, result = self.fetch(before['review_digest'])
        self.assertTrue(result['ok'], result)
        self.assertEqual(calls, [('owner/repo', 'cli/cadence.py', SHA)])
        folder = self.run / 'candidates/fixture/evidence/fixture-pin-code'
        manifest = json.loads((folder / 'manifest.json').read_bytes())
        self.assertEqual((manifest['evidence_id'], manifest['commit'], manifest['used_by']),
                         ('fixture-pin-code', SHA, ['2026-10-20-fixture.md']))
        self.assertEqual((folder / f'files/{SHA[:8]}/cli/cadence.py').read_bytes(), CODE)
        self.assertEqual(manifest['files'][f'files/{SHA[:8]}/cli/cadence.py']['sha256'], hashlib.sha256(CODE).hexdigest())
        after = wiki_candidates.review_snapshot(self.wiki, self.inbox, ref)
        self.assertEqual(after['pending_evidence'], [])
        self.assertNotEqual(after['review_digest'], before['review_digest'], 'the fetched copy must be reviewed again')
        self.assertEqual(self.approve_dry()[0], 0)
        self.assertFalse((self.wiki / 'raw/evidence/fixture-pin-code').exists(), 'fetching wrote into the wiki')
        calls, again = self.fetch(after['review_digest'])
        self.assertEqual((calls, again['results'][0]['status']), ([], 'already-fetched'))

    def test_a_passage_missing_from_the_downloaded_file_writes_nothing(self):
        import wiki_candidates
        ref = self.submit('fixture', self.metadata, SOURCE)
        digest = wiki_candidates.review_snapshot(self.wiki, self.inbox, ref)['review_digest']
        before = self.files()
        _, result = self.fetch(digest, code=b'def plan():\n    return ["everything"]\n')
        self.assertFalse(result['ok'])
        self.assertIn('passage not found', result['results'][0]['error'])
        self.assertEqual(result['pending'], ['fixture-pin-code'])
        self.assertEqual(self.files(), before)

    def test_an_id_that_entered_the_wiki_after_drafting_is_not_fetched_over(self):
        import wiki_candidates
        ref = self.submit('fixture', self.metadata, SOURCE)
        digest = wiki_candidates.review_snapshot(self.wiki, self.inbox, ref)['review_digest']
        (self.wiki / 'raw/evidence/fixture-pin-code').mkdir()
        with self.assertRaisesRegex(wiki_candidates.Refused, 'already exists'):
            self.fetch(digest)
        self.assertFalse((self.run / 'candidates/fixture/evidence').exists())

    def test_a_fetch_needs_the_digest_of_the_displayed_review(self):
        import wiki_candidates
        self.submit('fixture', self.metadata, SOURCE)
        for digest in ('0' * 64, 'not-a-digest', None):
            with self.subTest(digest=digest):
                calls, stack, patches = self.network()
                with stack, self.assertRaises(wiki_candidates.Refused):
                    for item in patches:
                        stack.enter_context(item)
                    import evidence_requests
                    evidence_requests.fetch(self.wiki, self.inbox, 'fixture-run/fixture', digest)
                self.assertEqual(calls, [])

    def test_unsafe_or_malformed_requests_are_refused_without_draft_writes(self):
        import draft_adapter
        (self.wiki / 'raw/evidence/taken-code').mkdir()
        (self.wiki / 'raw/evidence/taken-code/manifest.json').write_text('{"schema":1,"evidence_id":"taken-code"}')
        def changed(**fields):
            return [{**REQUEST, **fields}]
        cases = {
            'id not in evidence_ids': (dict(evidence_ids=[]), SOURCE.replace('fixture-pin-code', 'none (owner-directed)')),
            'existing id': (dict(evidence_ids=['taken-code'], evidence_requests=changed(id='taken-code')),
                            SOURCE.replace('fixture-pin-code', 'taken-code')),
            'local file': (dict(evidence_requests=[{**{k: v for k, v in REQUEST.items() if k != 'github'}, 'file': 'C:/secret.txt'}]), SOURCE),
            'github and url': (dict(evidence_requests=changed(url='https://example.org/page')), SOURCE),
            'plain http': (dict(evidence_requests=[{**{k: v for k, v in REQUEST.items() if k != 'github'}, 'url': 'http://example.org/'}]), SOURCE),
            'ip address': (dict(evidence_requests=[{**{k: v for k, v in REQUEST.items() if k != 'github'}, 'url': 'https://127.0.0.1/x'}]), SOURCE),
            'private host': (dict(evidence_requests=[{**{k: v for k, v in REQUEST.items() if k != 'github'}, 'url': 'https://localhost/x'}]), SOURCE),
            'credentials': (dict(evidence_requests=[{**{k: v for k, v in REQUEST.items() if k != 'github'}, 'url': 'https://user:pw@example.org/x'}]), SOURCE),
            'two repositories': (dict(evidence_requests=changed(github=REQUEST['github'] + [f'other/repo@{SHA}:a.py'])), SOURCE),
            'traversal': (dict(evidence_requests=changed(github=[f'owner/repo@{SHA}:../secret'])), SOURCE),
            'short passage': (dict(evidence_requests=changed(passages=['short'])), SOURCE),
            'no passage': (dict(evidence_requests=changed(passages=[])), SOURCE),
            'extra field': (dict(evidence_requests=changed(note='x')), SOURCE),
            'a date as id': (dict(evidence_ids=['2026-10-06'], evidence_requests=changed(id='2026-10-06')),
                             SOURCE.replace('fixture-pin-code', '2026-10-06')),
            'unrequested new id': (dict(evidence_ids=['fixture-pin-code', 'other-code']),
                                   SOURCE + 'Evidence: other-code\n'),
        }
        before = self.files()
        for label, (fields, source) in cases.items():
            with self.subTest(label):
                with self.assertRaises(draft_adapter.DraftRefused):
                    self.submit('fixture', {**self.metadata, **fields}, source)
        self.assertEqual(self.files(), before)
        self.assertFalse((self.run / 'candidates').exists())

    def test_a_new_evidence_id_cannot_be_a_bare_date(self):
        import evidence_requests
        with self.assertRaises(evidence_requests.RequestRefused):
            evidence_requests.requests_of({'evidence_ids': ['2026-10-06'],
                                           'evidence_requests': [{**REQUEST, 'id': '2026-10-06'}]})
        self.assertEqual(evidence_requests.requests_of({'evidence_ids': ['run-2026-10-06'],
                                                        'evidence_requests': [{**REQUEST, 'id': 'run-2026-10-06'}]})[0]['id'],
                         'run-2026-10-06')

    def test_a_retirement_cannot_request_evidence(self):
        import draft_adapter
        target = self.wiki / 'raw/sources/2026-10-20-fixture.md'
        target.write_text(SOURCE.replace('fixture-pin-code', 'none (owner-directed)'), encoding='utf-8', newline='\n')
        base = hashlib.sha256(target.read_bytes()).hexdigest()
        with self.assertRaisesRegex(draft_adapter.DraftRefused, 'retirement'):
            self.submit('fixture', {**self.metadata, 'kind': 'retire', 'base_sha256': base}, None)


if __name__ == '__main__':
    unittest.main()

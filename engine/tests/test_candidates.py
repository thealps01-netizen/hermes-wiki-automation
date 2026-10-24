"""Candidate authorization and exact-byte review checks, using synthetic sources."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wiki_candidates as candidates


class CandidatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.wiki, self.inbox = root / 'wiki', root / 'data' / 'inbox'
        (self.wiki / '.llm-wiki').mkdir(parents=True)
        (self.wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}', encoding='utf-8')
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir(parents=True)
        self.c = self.inbox / 'run/candidates/draft'
        self.c.mkdir(parents=True)
        self.metadata = dict(kind='new', target='2026-10-06-fixture.md', summary='Fixture', why='Test', evidence_ids=[])
        self.save_metadata()
        (self.c / 'source.md').write_bytes(b'# Fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: none (method).\n')

    def save_metadata(self):
        (self.c / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')

    def test_unconfirmed_cli_cannot_apply(self):
        before = {str(p): p.read_bytes() for p in self.wiki.rglob('*') if p.is_file()}
        with self.assertRaises(candidates.Refused):
            candidates.cmd_approve(self.wiki, self.inbox, 'run/draft', False)
        after = {str(p): p.read_bytes() for p in self.wiki.rglob('*') if p.is_file()}
        self.assertEqual(after, before)
        self.assertFalse((self.c / 'applied.json').exists())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(candidates.cmd_approve(self.wiki, self.inbox, 'run/draft', True), 0)
        self.assertFalse((self.c / 'applied.json').exists())

    def test_review_digest_binds_every_reviewed_input(self):
        snapshot = candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')
        for path, content in [
            (self.c / 'source.md', b'changed draft'),
            (self.c / 'candidate.json', json.dumps({**self.metadata, 'summary': 'changed'}).encode()),
            (self.wiki / '.llm-wiki/project.json', b'{"id":"other"}'),
        ]:
            original = path.read_bytes()
            path.write_bytes(content)
            with self.subTest(path=path.name):
                self.assertNotEqual(candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')['review_digest'], snapshot['review_digest'])
            path.write_bytes(original)
        self.assertEqual(candidates.review_snapshot(self.wiki, self.inbox, 'run/draft'), snapshot)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            candidates.cmd_show(self.wiki, self.inbox, 'run/draft', True)
        shown = json.loads(output.getvalue())
        self.assertEqual(shown['review_digest'], snapshot['review_digest'])
        self.assertEqual(shown['source_text'].encode(), (self.c / 'source.md').read_bytes())

    def test_ref_path_escape_refused(self):
        for ref in ('../draft', '/run/draft', 'run/../draft', 'run\\draft', 'RUN/draft'):
            with self.subTest(ref=ref), self.assertRaises(candidates.Refused):
                candidates.load_candidate(self.inbox, ref)
        (self.c / 'candidate.json').unlink()
        outside = Path(self.temp.name) / 'outside.json'
        outside.write_text(json.dumps(self.metadata), encoding='utf-8')
        try:
            (self.c / 'candidate.json').symlink_to(outside)
        except OSError:
            os.link(outside, self.c / 'candidate.json')
        with self.assertRaises(candidates.Refused):
            candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')

    def test_update_and_retire_require_base_hash(self):
        target = self.wiki / 'raw/sources' / self.metadata['target']
        target.write_bytes((self.c / 'source.md').read_bytes())
        for kind in ('update', 'retire'):
            for invalid in (None, 'bad', 'g' * 64, 'a' * 64):
                self.metadata.update(kind=kind, base_sha256=invalid)
                self.save_metadata()
                with self.subTest(kind=kind, base=invalid), self.assertRaises(candidates.Refused):
                    candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')
        self.metadata.update(kind='update', base_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        self.save_metadata()
        self.assertEqual(candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')['expected_base'], self.metadata['base_sha256'])

    def test_review_binds_stored_and_candidate_evidence(self):
        evidence = self.c / 'evidence/fixture-code'
        evidence.mkdir(parents=True)
        (evidence / 'manifest.json').write_bytes(b'{"schema":1,"evidence_id":"fixture-code"}')
        (evidence / 'payload.txt').write_bytes(b'first payload')
        (self.c / 'source.md').write_bytes(b'# Fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: fixture-code.\n')
        self.metadata['evidence_ids'] = ['fixture-code']
        self.save_metadata()
        before = candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')['review_digest']
        (evidence / 'payload.txt').write_bytes(b'second payload')
        after = candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')['review_digest']
        self.assertNotEqual(before, after)
        stored = self.wiki / 'raw/evidence/fixture-code'
        stored.mkdir()
        (stored / 'manifest.json').write_bytes(b'{"schema":1,"evidence_id":"fixture-code","used_by":[]}')
        stored_before = candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')['review_digest']
        (stored / 'manifest.json').write_bytes(b'{"schema":1,"evidence_id":"fixture-code","used_by":["changed"]}')
        self.assertNotEqual(stored_before, candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')['review_digest'])
        self.metadata['evidence_ids'] = ['../outside']
        self.save_metadata()
        with self.assertRaises(candidates.Refused):
            candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')

    def test_dry_run_no_journal_or_file_writes(self):
        root = Path(self.temp.name)
        before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()):
            candidates.cmd_show(self.wiki, self.inbox, 'run/draft', True)
            candidates.cmd_approve(self.wiki, self.inbox, 'run/draft', True)
        after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_caller_claims_and_transport_correlation_are_not_authority(self):
        snapshot = candidates.review_snapshot(self.wiki, self.inbox, 'run/draft')
        before = {str(p): p.read_bytes() for p in self.wiki.rglob('*') if p.is_file()}
        for approval in ({'confirm': True, 'actor': 'owner'},
                         {'choice': 'once', 'request_id': 'claimed', 'request_digest': snapshot['review_digest']}):
            with self.subTest(approval=approval), self.assertRaises(candidates.Refused):
                candidates.cmd_approve(self.wiki, self.inbox, 'run/draft', False,
                                       snapshot['review_digest'], approval)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.wiki.rglob('*') if p.is_file()})
        self.assertFalse((self.c / 'applied.json').exists())

    def test_show_refuses_mixed_revision_from_concurrent_writer(self):
        original_sha = candidates.sha
        changed = [False]
        def replace_after_hash(path):
            value = original_sha(path)
            if Path(path) == self.c / 'source.md' and not changed[0]:
                changed[0] = True
                Path(path).write_bytes(b'# Changed while review was assembled\n')
            return value
        with patch.object(candidates, 'sha', replace_after_hash), contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(candidates.Refused):
                candidates.cmd_show(self.wiki, self.inbox, 'run/draft', True)
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()

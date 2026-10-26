"""Draft submissions are data, immutable in the inbox, and never live writes."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class DraftTests(unittest.TestCase):
    def test_unsupported_retained_citations_are_refused_without_draft_writes(self):
        import draft_adapter
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            wiki, inbox = root / 'wiki', root / 'data/inbox'
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
            (wiki / 'raw/sources').mkdir(parents=True)
            evidence = wiki / 'raw/evidence/fixture-code'
            evidence.mkdir(parents=True)
            (evidence / 'manifest.json').write_text('{"schema":1,"evidence_id":"fixture-code","used_by":[]}')
            run = inbox / 'fixture-run'
            run.mkdir(parents=True)
            (run / 'run.json').write_text(json.dumps({'execution_id': 'execution', 'job_id': 'job', 'project_id': 'fixture'}))
            adapter = draft_adapter.DraftAdapter(wiki, inbox, 'fixture-run', 'execution', 'job')
            metadata = dict(kind='new', target='2026-10-06-fixture.md', summary='Fixture', why='Owner choice', evidence_ids=[])
            source = '# Fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: fixture-code\n'
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for ids in ([], ['fixture-code']):
                with self.subTest(evidence_ids=ids):
                    with self.assertRaisesRegex(draft_adapter.DraftRefused, 'citations.*adapter'):
                        adapter.submit('fixture', {**metadata, 'evidence_ids': ids}, source)
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertFalse((run / 'candidates').exists())

    def retained_fixture(self, root):
        import draft_adapter
        wiki, inbox = root / 'wiki', root / 'data/inbox'
        (wiki / '.llm-wiki').mkdir(parents=True)
        (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
        (wiki / 'raw/sources').mkdir(parents=True)
        for value in ('kept-code', 'other-code'):
            (wiki / f'raw/evidence/{value}').mkdir(parents=True)
            (wiki / f'raw/evidence/{value}/manifest.json').write_text(json.dumps({'schema': 1, 'evidence_id': value, 'used_by': []}))
        live = '# Fixture\n\n## Decisions\n\n**1. Fixture.**\nWhy: owner.\nEvidence: kept-code\n'
        (wiki / 'raw/sources/2026-10-06-fixture.md').write_text(live, encoding='utf-8', newline='\n')
        run = inbox / 'fixture-run'
        run.mkdir(parents=True)
        (run / 'run.json').write_text(json.dumps({'execution_id': 'execution', 'job_id': 'job', 'project_id': 'fixture'}))
        adapter = draft_adapter.DraftAdapter(wiki, inbox, 'fixture-run', 'execution', 'job')
        base = hashlib.sha256((wiki / 'raw/sources/2026-10-06-fixture.md').read_bytes()).hexdigest()
        metadata = dict(kind='update', target='2026-10-06-fixture.md', summary='Fixture', why='Owner choice',
                        evidence_ids=['kept-code'], base_sha256=base)
        source = live + '\n**2. Second.**\nWhy: owner.\nEvidence: none (owner-directed, 2026-10-12).\n'
        return wiki, inbox, run, adapter, metadata, source

    def test_an_update_may_keep_evidence_its_current_target_already_cites(self):
        import wiki_candidates
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            wiki, inbox, run, adapter, metadata, source = self.retained_fixture(Path(temp))
            ref = adapter.submit('fixture', metadata, source)
            self.assertEqual(ref, 'fixture-run/fixture')
            snapshot = wiki_candidates.review_snapshot(wiki, inbox, ref)
            self.assertRegex(snapshot['review_digest'], '^[0-9a-f]{64}$')

    def test_only_retained_evidence_of_the_exact_current_target_is_accepted(self):
        import draft_adapter
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            wiki, inbox, run, adapter, metadata, source = self.retained_fixture(root)
            refusals = {
                'new evidence': ({**metadata, 'evidence_ids': ['kept-code', 'other-code']},
                                 source + 'Evidence: other-code\n'),
                'new source': ({**metadata, 'kind': 'new', 'target': '2026-10-07-fixture.md'}, source),
                'stale base': ({**metadata, 'base_sha256': '0' * 64}, source),
                'metadata without citation': (metadata, source.replace('Evidence: kept-code', 'Evidence: none (owner-directed)')),
                'citation without metadata': ({**metadata, 'evidence_ids': []}, source),
            }
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for label, (meta, text) in refusals.items():
                with self.subTest(label), self.assertRaises(draft_adapter.DraftRefused):
                    adapter.submit('fixture', meta, text)
            (wiki / 'raw/evidence/kept-code/manifest.json').unlink()
            with self.subTest('unbound retained evidence'), self.assertRaises(draft_adapter.DraftRefused):
                adapter.submit('fixture', metadata, source)
            before.pop('wiki/raw/evidence/kept-code/manifest.json')
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertFalse((run / 'candidates').exists())

    def test_the_same_checks_and_storage_work_without_a_bound_run(self):
        import draft_adapter
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            wiki, inbox, run, adapter, metadata, source = self.retained_fixture(root)
            candidates = root / 'shadow/candidates'
            for label, (meta, text) in {
                    'stale base': ({**metadata, 'base_sha256': '0' * 64}, source),
                    'no decisions section': (metadata, source.replace('## Decisions', '## Notes')),
            }.items():
                with self.subTest(label), self.assertRaises(draft_adapter.DraftRefused):
                    draft_adapter.check_draft(wiki, candidates, meta, text)
            base = draft_adapter.check_draft(wiki, candidates, metadata, source)
            self.assertEqual(base, (wiki / 'raw/sources/2026-10-06-fixture.md').read_bytes())
            draft_adapter.store_draft(candidates / 'fixture', metadata, source, base)
            self.assertEqual((candidates / 'fixture/base.md').read_bytes(), base)
            self.assertEqual((candidates / 'fixture/source.md').read_text(encoding='utf-8'), source)
            draft_adapter.store_draft(candidates / 'fixture', metadata, source, base)
            with self.assertRaises(draft_adapter.DraftRefused):
                draft_adapter.store_draft(candidates / 'fixture', metadata, source + 'changed\n', base)

    def test_read_and_submit_are_confined_to_bound_run(self):
        import draft_adapter
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            root = Path(temp)
            wiki, inbox = root / 'wiki', root / 'data/inbox'
            (wiki / '.llm-wiki').mkdir(parents=True)
            (wiki / '.llm-wiki/project.json').write_text('{"id":"fixture"}')
            (wiki / 'raw/sources').mkdir(parents=True)
            (wiki / 'raw/evidence').mkdir(parents=True)
            run = inbox / 'fixture-run'
            (run / 'conversations').mkdir(parents=True)
            (run / 'run.json').write_text(json.dumps({'execution_id': 'execution', 'job_id': 'job', 'project_id': 'fixture'}))
            (run / 'conversations/session.md').write_text('Owner chose the fixture.\n')
            adapter = draft_adapter.DraftAdapter(wiki, inbox, 'fixture-run', 'execution', 'job')
            read = adapter.read('conversations/session.md', 0, 5)
            self.assertEqual(read['text'], 'Owner')
            self.assertTrue(read['truncated'])
            self.assertEqual(read['next_offset'], 5)
            for denied in ('../secrets', 'candidate.json', '../../wiki/raw/sources/test.md', 'run.json/../../../secret'):
                with self.subTest(path=denied), self.assertRaises(draft_adapter.DraftRefused):
                    adapter.read(denied)
            before = {str(p): p.read_bytes() for p in wiki.rglob('*') if p.is_file()}
            metadata = dict(kind='new', target='2026-10-06-fixture.md', summary='Fixture', why='Owner choice', evidence_ids=[])
            source = '# Fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: none (owner-directed).\n'
            ref = adapter.submit('fixture', metadata, source)
            self.assertEqual(ref, 'fixture-run/fixture')
            self.assertEqual(adapter.submit('fixture', metadata, source), ref)
            with self.assertRaises(draft_adapter.DraftRefused):
                adapter.submit('fixture', metadata, source + '\nChanged after review')
            after = {str(p): p.read_bytes() for p in wiki.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            self.assertFalse((run / 'candidates/fixture/applied.json').exists())
            with self.assertRaises(draft_adapter.DraftRefused):
                draft_adapter.DraftAdapter(wiki, inbox, 'fixture-run', 'different-execution', 'job')


if __name__ == '__main__':
    unittest.main()

"""Citation identity policy uses real disposable reviews and protected publication."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evidence_store
from wiki_candidates import Refused, cmd_approve, review_snapshot


class EvidenceIdentifierPolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.wiki, self.data = self.root / 'wiki', self.root / 'data'
        self.inbox = self.data / 'inbox'
        self.candidate = self.inbox / 'run/candidates/draft'
        self.candidate.mkdir(parents=True)
        (self.wiki / '.llm-wiki').mkdir(parents=True)
        (self.wiki / '.llm-wiki/project.json').write_bytes(b'{"id":"identifier-policy-fixture"}')
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir()
        self.target = self.wiki / 'raw/sources/2026-10-08-identifier-policy.md'
        self.metadata = {'kind': 'new', 'target': self.target.name, 'summary': 'Citation fixture',
                         'why': 'Test identifier policy', 'evidence_ids': []}

    def write_candidate(self, text, ids):
        self.source = text.encode('utf-8')
        self.metadata['evidence_ids'] = ids
        (self.candidate / 'candidate.json').write_text(json.dumps(self.metadata), encoding='utf-8')
        (self.candidate / 'source.md').write_bytes(self.source)

    def source_table(self, rows):
        return ('# Citation fixture\n\n## Decisions\n\n**1. Fixture.**\nEvidence: none (method).\n'
                '\n## Evidence\n\n| ID | Support |\n| --- | --- |\n'
                + ''.join(f'| `{value}` | Fixture |\n' for value in rows))

    def retained(self, evidence_id):
        folder = self.wiki / 'raw/evidence' / evidence_id
        folder.mkdir()
        payload = b'Exact retained evidence'
        (folder / 'payload.txt').write_bytes(payload)
        manifest = {'schema': 1, 'evidence_id': evidence_id, 'used_by': [],
                    'files': {'payload.txt': {'sha256': evidence_store.sha256(payload)}}}
        (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_no_evidence_prefix_does_not_hide_later_identifiers_in_a_clause(self):
        from wiki_candidates import validate_source_citations
        for value in ('none (method); none-code, none-tools', 'none. none-code + none-tools',
                      'none-code (none-tools)', 'none-code and none-tools',
                      'none-code\n  none-tools'):
            with self.subTest(value=value):
                text = f'Evidence: {value}\n'
                self.assertEqual(evidence_store._evidence_texts(text), ([value], []))
                validate_source_citations(text, ['none-code', 'none-tools'])
                with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
                    validate_source_citations(text, [])

    def test_separate_parenthesized_clause_is_not_a_whole_placeholder(self):
        from wiki_candidates import validate_source_citations
        value = 'none (method) + (none-code)'
        self.assertEqual(evidence_store._evidence_texts(f'Evidence: {value}\n'), ([value], []))
        validate_source_citations(f'Evidence: {value}\n', ['none-code'])

    def test_placeholder_annotation_words_are_not_citations(self):
        # Real harvest drafts: the annotation of a complete `none (...)` clause explains why there
        # is no retained evidence. Dates and hyphenated words inside it are not evidence ids, also
        # when the annotation wraps onto a continuation line or shares the field with real ids.
        from wiki_candidates import validate_source_citations
        cases = (
            ('none (measurement: `docs/parity.md` at `f2bd9c9`, 2026-10-10, 239 items: 187 done, 52\n'
             '  open).', []),
            ('none (measurement: seeded-defect and malicious-skill comparison in network-less Docker\n'
             '  containers, 2026-10-08); real-code;\n  other-code.', ['real-code', 'other-code']),
            ('real-code; none (measurement:\n  `context-loader` reproduction, 2026-10-08).', ['real-code']),
            ('none (owner-directed, see (nested-note), 2026-10-10) + (none-code).', ['none-code']),
        )
        for value, ids in cases:
            with self.subTest(value=value):
                text = f'Evidence: {value}\n'
                validate_source_citations(text, ids)
                with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
                    validate_source_citations(text, ids + ['extra-code'])

    def test_a_date_is_never_an_evidence_id(self):
        # Real wiki pages: a date after an id or between clauses explains the evidence; no evidence id is a
        # bare date (a new id that is one is refused at request time), so it cannot hide a citation.
        from wiki_candidates import validate_source_citations
        cases = (
            ('wiki-embedding-benchmark-2026-10-06 (own measurement report, 2026-10-06).', ['wiki-embedding-benchmark-2026-10-06']),
            ('none (owner-directed, 2026-10-25); 2026-09-16 trial: none (observation).', []),
            ('real-code, run 2026-10-08 and 2026-10-09', ['real-code']),
        )
        for value, ids in cases:
            with self.subTest(value=value):
                text = f'Evidence: {value}\n'
                validate_source_citations(text, ids)
                with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
                    validate_source_citations(text, ids + ['2026-10-06'])

    def test_multiline_placeholder_is_a_complete_placeholder(self):
        value = 'none (measurement: oracle tests, 2026-10-10,\n  three characters).'
        self.assertTrue(evidence_store._no_evidence(value))
        pinned = f'## Decisions\n\n**1. Tool v1.2.3.**\nEvidence: {value}\n'
        self.assertEqual(evidence_store.version_claims_without_evidence(pinned, ''),
                         ['**1. Tool v1.2.3.**'])

    def test_unbalanced_placeholder_annotation_still_fails_closed(self):
        from wiki_candidates import validate_source_citations
        for value in ('none (seeded-defect', 'none seeded-defect)', 'none (a) seeded-defect)'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
                    validate_source_citations(f'Evidence: {value}\n', [])

    def test_pinned_no_evidence_field_cannot_be_hidden_by_later_prose(self):
        for trailing in ('- Rejected: Unretained alternatives.', 'Owner note: Not measured.'):
            with self.subTest(trailing=trailing):
                text = ('# Fixture\n\n## Decisions\n\n**1. Tool v1.2.3 is reliable.**\n'
                        '- Why: Assumed behaviour.\nEvidence: none (method).\n' + trailing + '\n')
                self.write_candidate(text, [])
                before = self.files()
                self.assertEqual(evidence_store.version_claims_without_evidence(text, ''),
                                 ['**1. Tool v1.2.3 is reliable.**'])
                snapshot = review_snapshot(self.wiki, self.inbox, 'run/draft')
                self.assertEqual(snapshot['evidence'], [])
                with self.assertRaisesRegex(Refused, 'pinned version'):
                    cmd_approve(self.wiki, self.inbox, 'run/draft', True)
                self.assertEqual(self.files(), before)
                from candidate_apply import apply_candidate
                from workflow_store import WorkflowStore
                signed, approval = self.authorize()
                with WorkflowStore(self.data / 'workflow.sqlite') as store:
                    with self.assertRaisesRegex(Refused, 'pinned version'):
                        apply_candidate(self.wiki, self.inbox, 'run/draft', signed, approval, store)
                    self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)
                self.assertFalse(self.target.exists())
                self.assertFalse((self.candidate / 'applied.json').exists())

    def test_pinned_decision_with_none_prefixed_evidence_is_not_unbacked(self):
        text = '# Fixture\n\n## Decisions\n\n**1. Tool v1.2.3.**\nEvidence: none-code.\n'
        self.assertEqual(evidence_store.version_claims_without_evidence(text, ''), [])

    def test_none_prefixed_table_requires_explicit_owner_metadata_before_review(self):
        self.retained('none-code')
        self.write_candidate(self.source_table(['none-code']), [])
        before = self.files()
        with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
            review_snapshot(self.wiki, self.inbox, 'run/draft')
        with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
            cmd_approve(self.wiki, self.inbox, 'run/draft', True)
        self.assertEqual(self.files(), before)
        self.assertFalse((self.data / 'owner-decisions.sqlite').exists())
        self.assertFalse((self.data / 'workflow.sqlite').exists())
        self.assertFalse(self.target.exists())

    def test_exact_placeholders_remain_empty_in_line_and_table_reviews(self):
        placeholders = ('none', 'none.', 'NONE', 'none(method)', 'none (method).',
                        'none (owner-directed method)', 'none (owner-directed, 2026-10-08)',
                        'none (measurement: command(nested(x)), 2026-10-08).', '-', '–', '—')
        for value in placeholders:
            with self.subTest(value=value):
                self.assertTrue(evidence_store._no_evidence(value))
                text = self.source_table([value]).replace('none (method).', value, 1)
                self.write_candidate(text, [])
                before = self.files()
                snapshot = review_snapshot(self.wiki, self.inbox, 'run/draft')
                self.assertEqual(snapshot['evidence'], [])
                self.assertEqual(snapshot['stored_evidence'], [])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cmd_approve(self.wiki, self.inbox, 'run/draft', True), 0)
                self.assertEqual(self.files(), before)
                pinned = f'## Decisions\n\n**1. Tool v1.2.3.**\nEvidence: {value}\n'
                self.assertEqual(evidence_store.version_claims_without_evidence(pinned, ''),
                                 ['**1. Tool v1.2.3.**'])

    def test_prefixes_and_incomplete_annotations_are_not_placeholders(self):
        for value in ('none-code', 'none-tools', 'nonetheless-code', 'none-code-v1',
                      'none of these: none-code', 'none (method); none-code',
                      'none (method) + (none-code)', 'none (method', 'none method)',
                      'none ((method)', 'none (method))'):
            with self.subTest(value=value):
                self.assertFalse(evidence_store._no_evidence(value))

    def test_invalid_table_grammar_does_not_disappear_as_a_none_prefix(self):
        for value in ('none_code', 'none.code', 'none-CODE', 'none-code, none-tools', '../none-code'):
            with self.subTest(value=value):
                self.write_candidate(self.source_table([value]), [])
                before = self.files()
                with self.assertRaisesRegex(Refused, 'Invalid source citations'):
                    review_snapshot(self.wiki, self.inbox, 'run/draft')
                with self.assertRaisesRegex(Refused, 'Invalid source citations'):
                    cmd_approve(self.wiki, self.inbox, 'run/draft', True)
                self.assertEqual(self.files(), before)

    def test_multiple_table_identifiers_require_exact_declared_set(self):
        self.retained('none-code')
        self.retained('none-tools')
        for ids in ([], ['none-code'], ['none-tools'], ['other-code'],
                    ['none-code', 'none-tools', 'unused-code'], ['none-code', 'none-code'], None):
            with self.subTest(ids=ids):
                self.write_candidate(self.source_table(['none-code', 'none-tools']), ids)
                before = self.files()
                with self.assertRaises(Refused):
                    review_snapshot(self.wiki, self.inbox, 'run/draft')
                with self.assertRaises(Refused):
                    cmd_approve(self.wiki, self.inbox, 'run/draft', True)
                self.assertEqual(self.files(), before)

    def test_none_prefixed_citation_requires_matching_schema_one_manifest(self):
        self.write_candidate(self.source_table(['none-code']), ['none-code'])
        with self.assertRaisesRegex(Refused, 'evidence.*manifest'):
            review_snapshot(self.wiki, self.inbox, 'run/draft')
        self.retained('none-code')
        manifest = self.wiki / 'raw/evidence/none-code/manifest.json'
        initial = json.loads(manifest.read_bytes())
        for changes in ({'schema': 0}, {'evidence_id': 'other-code'}):
            with self.subTest(changes=changes):
                manifest.write_text(json.dumps({**initial, **changes}), encoding='utf-8')
                before = self.files()
                with self.assertRaisesRegex(Refused, 'evidence.*manifest'):
                    review_snapshot(self.wiki, self.inbox, 'run/draft')
                with self.assertRaisesRegex(Refused, 'evidence.*manifest'):
                    cmd_approve(self.wiki, self.inbox, 'run/draft', True)
                self.assertEqual(self.files(), before)

    def authorize(self):
        from owner_decisions import OwnerDecisions
        snapshot = review_snapshot(self.wiki, self.inbox, 'run/draft')
        with OwnerDecisions(self.data, initialize=True) as authority:
            request = authority.prepare(snapshot, 'fixture-owner')
            approval = authority.confirm(request['request_id'], snapshot, 'fixture-owner')
        return snapshot, approval

    def test_matched_identifiers_bind_publish_and_attribute_end_to_end(self):
        import shutil
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        completed = 0
        for kind in ('new', 'update'):
            for origin in ('stored_evidence', 'evidence'):
                for style in ('table-single', 'table-multiple', 'line-multiple'):
                    with self.subTest(kind=kind, origin=origin, style=style):
                        fixture = EvidenceIdentifierPolicyTests()
                        fixture.setUp()
                        try:
                            ids = ['none-code'] if style == 'table-single' else ['none-code', 'none-tools', 'fixture-code']
                            for value in ids:
                                fixture.retained(value)
                                if origin == 'evidence':
                                    destination = fixture.candidate / 'evidence' / value
                                    destination.parent.mkdir(exist_ok=True)
                                    shutil.move(fixture.wiki / 'raw/evidence' / value, destination)
                            text = fixture.source_table(ids)
                            if style == 'line-multiple':
                                text = ('# Citation fixture\n\n## Decisions\n\n**1. Tool v1.2.3.**\n'
                                        'Evidence: none-code (none-tools) + fixture-code.\n')
                            fixture.metadata['kind'] = kind
                            if kind == 'update':
                                original = b'# Previously reviewed source\n'
                                fixture.target.write_bytes(original)
                                fixture.metadata['base_sha256'] = evidence_store.sha256(original)
                            fixture.write_candidate(text, ids)
                            # Only the fixture owner corrects metadata; the parser never expands it.
                            before = fixture.files()
                            snapshot = review_snapshot(fixture.wiki, fixture.inbox, 'run/draft')
                            expected_paths = {f'{value}/{name}' for value in ids
                                              for name in ('manifest.json', 'payload.txt')}
                            self.assertEqual({entry['path'] for entry in snapshot[origin]}, expected_paths)
                            self.assertEqual(snapshot['evidence' if origin == 'stored_evidence' else 'stored_evidence'], [])
                            for entry in snapshot[origin]:
                                root = fixture.wiki / 'raw/evidence' if origin == 'stored_evidence' else fixture.candidate / 'evidence'
                                self.assertEqual(entry['sha256'], evidence_store.sha256((root / entry['path']).read_bytes()))
                            with contextlib.redirect_stdout(io.StringIO()):
                                self.assertEqual(cmd_approve(fixture.wiki, fixture.inbox, 'run/draft', True), 0)
                            self.assertEqual(fixture.files(), before)
                            signed_snapshot, approval = fixture.authorize()
                            self.assertEqual(signed_snapshot, snapshot)
                            with WorkflowStore(fixture.data / 'workflow.sqlite') as store:
                                result = apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', snapshot, approval, store)
                                self.assertEqual(result['state'], 'applied')
                                self.assertEqual(store.get_operation(result['operation_id'])['snapshot'], snapshot)
                                repeated = apply_candidate(fixture.wiki, fixture.inbox, 'run/draft', snapshot, approval, store)
                                self.assertFalse(repeated['later_drift'])
                                self.assertEqual(repeated['operation_id'], result['operation_id'])
                                self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 1)
                            self.assertEqual(fixture.target.read_bytes(), fixture.source)
                            self.assertTrue((fixture.candidate / 'applied.json').is_file())
                            for value in ids:
                                folder = fixture.wiki / 'raw/evidence' / value
                                self.assertEqual(json.loads((folder / 'manifest.json').read_bytes())['used_by'], [fixture.target.name])
                                self.assertEqual((folder / 'payload.txt').read_bytes(), b'Exact retained evidence')
                            cites, missing = evidence_store.citations(fixture.wiki / 'raw/sources', set(ids))
                            self.assertEqual(cites, {value: {fixture.target.name} for value in ids})
                            self.assertEqual(missing, [])
                            completed += 1
                        finally:
                            fixture.doCleanups()
        self.assertEqual(completed, 12)
        print(f'NONE_IDENTIFIER_PUBLICATION completed={completed} expected=12')

    def test_owner_metadata_change_after_review_refuses_actual_publication(self):
        from candidate_apply import apply_candidate
        from workflow_store import WorkflowStore
        self.retained('none-code')
        text = self.source_table(['none-code'])
        self.write_candidate(text, ['none-code'])
        snapshot, approval = self.authorize()
        self.write_candidate(text, [])
        canonical_before = {p.relative_to(self.wiki).as_posix(): p.read_bytes()
                            for p in self.wiki.rglob('*') if p.is_file()}
        with WorkflowStore(self.data / 'workflow.sqlite') as store:
            with self.assertRaisesRegex(Refused, 'citations.*evidence_ids'):
                apply_candidate(self.wiki, self.inbox, 'run/draft', snapshot, approval, store)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM operations').fetchone()[0], 0)
        self.assertEqual(canonical_before, {p.relative_to(self.wiki).as_posix(): p.read_bytes()
                                          for p in self.wiki.rglob('*') if p.is_file()})
        self.assertFalse(self.target.exists())
        self.assertFalse((self.candidate / 'applied.json').exists())
        self.assertEqual(json.loads((self.candidate / 'candidate.json').read_bytes())['evidence_ids'], [])


class FindingsEvidence(unittest.TestCase):
    """Sources may carry '## Findings'; a finding is a bare factual claim, so it needs evidence."""

    SRC = ("# T\n\n## Decisions\n\n**1. Use X.**\n- Why: y.\n- Evidence: none (method).\n\n"
           "## Findings\n\n{body}\n## Open\n")

    def test_finding_without_evidence_is_refused(self):
        text = self.SRC.format(body="**F1. Tool renders 8 angles.**\n- Evidence: none.\n")
        self.assertEqual(evidence_store.findings_without_evidence(text, ""), ["**F1. Tool renders 8 angles.**"])

    def test_finding_with_retained_copy_or_own_measurement_passes(self):
        for ev in ("tool-readme-9aa2593f.", "none (measurement: bench.py at 04d8b67, 2026-10-16)."):
            with self.subTest(ev=ev):
                text = self.SRC.format(body=f"**F1. Tool renders 8 angles.**\n- Evidence: {ev}\n")
                self.assertEqual(evidence_store.findings_without_evidence(text, ""), [])

    def test_unchanged_finding_is_not_rejudged(self):
        text = self.SRC.format(body="**F1. Old claim.**\n- Evidence: none.\n")
        self.assertEqual(evidence_store.findings_without_evidence(text, text), [])

    def test_pinned_version_in_a_finding_needs_a_pinned_copy(self):
        text = self.SRC.format(body="**F1. Tool v1.2.3 drops frames.**\n- Evidence: none (measurement: run, 2026-10-16).\n")
        self.assertEqual(evidence_store.version_claims_without_evidence(text, ""), ["**F1. Tool v1.2.3 drops frames.**"])

    def test_source_without_findings_is_unaffected(self):
        text = "# T\n\n## Decisions\n\n**1. Use X.**\n- Evidence: none (method).\n"
        self.assertEqual(evidence_store.findings_without_evidence(text, ""), [])

if __name__ == '__main__':
    unittest.main()

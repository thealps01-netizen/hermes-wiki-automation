import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import harvest_ledger as hl  # noqa: E402
import harvest_merge as hm  # noqa: E402

PAGE = """# Skill suggestions

## Scope

How Hermes proposes skills after a reply, and how the owner keeps the volume down.

## Decisions

**1. Keep the approval gate on.**
Why: the owner reviews every skill. Rejected: auto-install.
Evidence: none (owner-directed, 2026-10-14).

**2. Background review stays enabled.**
Why: it finds real skills. Rejected: turning it off.
Evidence: none (owner-directed, 2026-10-14).

## Open

- Whether 40 is the right interval.

## Evidence

| id | what |
|----|------|
| none | owner-directed |
"""
TARGET = '2026-10-14-skill-suggestions.md'
RULES = (Path(__file__).resolve().parents[1] / 'harvest_prompt.md').read_text(encoding='utf-8')
DECISION = {'type': 'decision', 'claim': 'The owner raised the skill nudge interval to 40.',
            'quote': 'then raise the interval to 40', 'message_index': 3, 'later_use': 'Keep 40.', 'part': 1}
PROCESS = {'type': 'process', 'claim': 'Show a before/after sample before changing UI code.',
           'quote': 'show me before and after first', 'message_index': 5, 'later_use': 'Ask first.', 'part': 1}
UPDATED = PAGE.replace('## Open', '**3. Raise the nudge interval to 40.**\nWhy: fewer suggestions. Rejected: 10.\n'
                       'Evidence: none (owner-directed, 2026-10-26).\n\n## Open')


def draft_reply(metadata, source=None):
    text = '=== METADATA ===\n' + json.dumps(metadata) + '\n'
    if source is not None:
        text += '=== SOURCE ===\n' + source + '=== END ===\n'
    return text


class Wiki(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.wiki = self.root / 'wiki'
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir(parents=True)
        (self.wiki / 'raw/sources' / TARGET).write_text(PAGE, encoding='utf-8', newline='\n')
        self.base_sha = hashlib.sha256((self.wiki / 'raw/sources' / TARGET).read_bytes()).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()


class Index(Wiki):
    def test_the_routing_index_lists_file_title_and_scope_only(self):
        index = hm.routing_index(self.wiki)
        self.assertIn(TARGET, index)
        self.assertIn('Skill suggestions', index)
        self.assertIn('How Hermes proposes skills', index)
        self.assertNotIn('Keep the approval gate on', index)

    def test_house_rules_are_cut_from_the_drafting_prompt(self):
        rules = hm.house_rules(RULES)
        for heading in ('## What counts', '## Decide the kind for each decision', '## Evidence'):
            self.assertIn(heading, rules)
        self.assertIn('## Decisions` (numbered bold decisions', rules)
        self.assertNotIn('## Finish', rules)
        with self.assertRaises(hm.MergeError):
            hm.house_rules('# nothing\n')


class Routes(Wiki):
    def test_each_item_gets_an_existing_target_a_new_dated_name_or_a_drop_reason(self):
        items = {'I1': DECISION, 'I2': DECISION, 'I3': DECISION}
        reply = json.dumps({'routes': [{'item': 'I1', 'target': TARGET}, {'item': 'I2', 'new': 'voice-assistant'},
                                       {'item': 'I3', 'drop': 'already a rule in AGENTS.md'}]})
        routes, dropped, problems = hm.parse_routes(reply, items, self.wiki, '2026-10-26')
        self.assertEqual(routes, {TARGET: ['I1'], '2026-10-26-voice-assistant.md': ['I2']})
        self.assertEqual(dropped, {'I3': 'already a rule in AGENTS.md'})
        self.assertEqual(problems, [])

    def test_unknown_targets_bad_names_and_missing_items_are_problems_not_routes(self):
        items = {'I1': DECISION, 'I2': DECISION, 'I3': DECISION}
        reply = json.dumps({'routes': [{'item': 'I1', 'target': '2026-01-01-made-up.md'},
                                       {'item': 'I2', 'new': 'Bad Name!'}]})
        routes, dropped, problems = hm.parse_routes(reply, items, self.wiki, '2026-10-26')
        self.assertEqual(routes, {})
        self.assertEqual(len(problems), 3)
        self.assertTrue(any('I3' in p for p in problems))


class Draft(Wiki):
    def test_a_reply_is_split_into_metadata_and_source(self):
        metadata, source = hm.parse_draft(draft_reply({'kind': 'update', 'summary': 's', 'why': 'w',
                                                       'evidence_ids': []}, UPDATED))
        self.assertEqual((metadata['kind'], source), ('update', UPDATED))

    def test_the_draft_prompt_states_the_metadata_limits_and_that_code_fills_evidence_ids(self):
        prompt = hm.draft_prompt(TARGET, PAGE, {'I1': dict(DECISION, label='a', date='2026-10-26')}, 'rules', '2026-10-26')
        self.assertIn('at most 2000 characters', prompt)
        self.assertIn('evidence_ids is filled in by code', prompt)

    def test_no_change_needs_no_source(self):
        metadata, source = hm.parse_draft(draft_reply({'kind': 'none', 'why': 'already decision 2'}))
        self.assertEqual((metadata['kind'], source), ('none', None))

    def test_a_reply_without_markers_is_an_error(self):
        with self.assertRaises(hm.MergeError):
            hm.parse_draft('Here is the updated page: # Skill suggestions')

    def test_lost_decisions_headings_and_evidence_rows_are_named(self):
        dropped = UPDATED.replace('**2. Background review stays enabled.**\nWhy: it finds real skills. Rejected: '
                                  'turning it off.\nEvidence: none (owner-directed, 2026-10-14).\n\n', '')
        dropped = dropped.replace('## Open\n\n- Whether 40 is the right interval.\n\n', '')
        dropped = dropped.replace('| none | owner-directed |\n', '')
        lost = hm.lost_units(PAGE, dropped)
        self.assertTrue(any('decision 2' in x for x in lost))
        self.assertTrue(any('## Open' in x for x in lost))
        self.assertTrue(any('| none | owner-directed |' in x for x in lost))

    def test_an_evidence_row_updated_under_its_own_id_is_not_a_loss(self):
        changed = UPDATED.replace('| none | owner-directed |', '| none | owner-directed; also decision 3 |')
        self.assertEqual(hm.lost_units(PAGE, changed), [])

    def test_decisions_numbered_before_the_bold_are_also_counted(self):
        page = PAGE.replace('**1. Keep', '1. **Keep').replace('**2. Background', '2. **Background')
        self.assertEqual(hm.lost_units(page, page.replace('2. **Background', 'Background')), ['decision 2'])

    def test_a_removed_changed_decision_bullet_is_a_loss_but_a_reworded_one_is_not(self):
        page = PAGE.replace('## Open', '## Changed decisions\n\n- "Interval 10" → interval 20 (2026-10-01), because\n'
                            '  ten was too frequent.\n\n## Open')
        reworded = page.replace('because\n  ten was too frequent.', 'because ten was too often.')
        self.assertEqual(hm.lost_units(page, reworded), [])
        lost = hm.lost_units(page, page.replace('- "Interval 10" → interval 20 (2026-10-01), because\n  ten was too frequent.\n', ''))
        self.assertTrue(any('Interval 10' in x for x in lost))

    def test_a_removed_open_item_is_a_warning_not_a_refusal(self):
        resolved = UPDATED.replace('- Whether 40 is the right interval.\n', '- None.\n')
        self.assertEqual(hm.lost_units(PAGE, resolved), [])
        self.assertEqual(hm.removed_open(PAGE, resolved), ['Whether 40 is the right interval.'])
        self.assertEqual(hm.removed_open(PAGE, UPDATED.replace('right interval', 'right interval for him')), [])

    def test_an_open_item_is_compared_with_its_continuation_lines(self):
        page = PAGE.replace('- Whether 40 is the right interval.', '- Check the nudge\n  interval after a week.\n'
                            '- Check the nudge\n  wording with the owner before release.')
        draft = page.replace('- Check the nudge\n  wording with the owner before release.', '')
        self.assertEqual(hm.removed_open(page, draft), ['Check the nudge wording with the owner before release.'])

    def test_the_draft_prompt_names_the_decision_format(self):
        prompt = hm.draft_prompt(TARGET, PAGE, {'I1': dict(DECISION, label='a', date='2026-10-26')}, 'rules', '2026-10-26')
        self.assertIn('**1. Title.**', prompt)

    def test_a_decision_changed_in_place_is_not_a_loss(self):
        changed = UPDATED.replace('**2. Background review stays enabled.**', '**2. Background review is off.**')
        self.assertEqual(hm.lost_units(PAGE, changed), [])

    def test_requested_passages_must_be_copied_from_the_item_quotes(self):
        good = {'evidence_requests': [{'id': 'x', 'supports': 's', 'url': 'https://e.com', 'passages': ['raise the interval']}]}
        bad = {'evidence_requests': [{'id': 'x', 'supports': 's', 'url': 'https://e.com', 'passages': ['set it to 100']}]}
        self.assertEqual(hm.unquoted_passages(good, [DECISION]), [])
        self.assertEqual(hm.unquoted_passages(bad, [DECISION]), ['set it to 100'])


class Night(Wiki):
    def setUp(self):
        super().setUp()
        self.ledger = hl.Ledger(self.root / 'ledger.sqlite', clock=lambda: 1761436800.0).__enter__()
        self.out = self.root / 'shadow' / 'night-1'

    def tearDown(self):
        self.ledger.__exit__()
        super().tearDown()

    def finished(self, cid, items):
        self.ledger.offer('hermes', cid, None, 1761436800.0, [f'# Conversation {cid}\n\n### user · x\n\nhi\n'], 'p1')
        row = self.ledger.claim('w')
        self.ledger.finish(row['id'], 'w', items, [])

    def caller(self, answers):
        prompts = []

        def call(prompt):
            prompts.append(prompt)
            kind = 'route' if hm.ROUTE_MARK in prompt else 'draft'
            return answers[kind].pop(0), {'session_id': f's{len(prompts)}', 'cost_usd': 0.01,
                                          'usage': {'input_tokens': 10, 'output_tokens': 1, 'cache_write_tokens': 5}}
        return call, prompts

    def run_night(self, call):
        return hm.merge_night(self.ledger, self.wiki, self.out, call, RULES, 'night-1', '2026-10-26')

    def test_a_night_routes_drafts_checks_and_stores_one_candidate_per_page(self):
        self.finished('a', [DECISION, PROCESS])
        call, prompts = self.caller({
            'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
            'draft': [draft_reply({'kind': 'update', 'summary': 'Adds the interval decision', 'why': 'conversation a',
                                   'evidence_ids': []}, UPDATED)]})
        report = self.run_night(call)
        folder = self.out / 'candidates' / '2026-10-14-skill-suggestions'
        metadata = json.loads((folder / 'candidate.json').read_text(encoding='utf-8'))
        self.assertEqual((metadata['kind'], metadata['target'], metadata['base_sha256']), ('update', TARGET, self.base_sha))
        self.assertEqual((folder / 'source.md').read_text(encoding='utf-8'), UPDATED)
        self.assertEqual((folder / 'base.md').read_text(encoding='utf-8'), PAGE)
        self.assertEqual(report['candidates'], [{'target': TARGET, 'kind': 'update', 'items': ['I1'], 'removed_open': []}])
        self.assertEqual(report['skill_candidates'], [PROCESS['claim']])
        self.assertNotIn('show me before and after', prompts[0])
        self.assertIn(PAGE, prompts[1])
        self.assertEqual(json.loads((self.out / 'report.json').read_text(encoding='utf-8'))['candidates'],
                         report['candidates'])
        self.assertEqual(self.ledger.unmerged(), [])
        self.assertEqual((report['tokens_in'], report['tokens_out']), (30, 2))
        self.assertEqual((self.wiki / 'raw/sources' / TARGET).read_text(encoding='utf-8'), PAGE)

    def test_an_open_item_the_update_removes_is_listed_next_to_the_candidate(self):
        self.finished('a', [DECISION])
        resolved = UPDATED.replace('- Whether 40 is the right interval.\n', '- None.\n')
        call, _ = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                               'draft': [draft_reply({'kind': 'update', 'summary': 's', 'why': 'w'}, resolved)]})
        report = self.run_night(call)
        self.assertEqual(report['candidates'][0]['removed_open'], ['Whether 40 is the right interval.'])

    def test_a_refused_draft_gets_one_repair_call_with_the_reason(self):
        self.finished('a', [DECISION])
        lossy = UPDATED.replace('## Open\n\n- Whether 40 is the right interval.\n\n', '')
        call, prompts = self.caller({
            'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
            'draft': [draft_reply({'kind': 'update', 'summary': 's', 'why': 'w', 'evidence_ids': []}, lossy),
                      draft_reply({'kind': 'update', 'summary': 's', 'why': 'w', 'evidence_ids': []}, UPDATED)]})
        report = self.run_night(call)
        self.assertIn('## Open', prompts[2])
        self.assertEqual(len(report['candidates']), 1)
        self.assertEqual(report['refused'], [])

    def test_prose_words_read_as_evidence_ids_are_named_so_the_repair_can_rephrase_them(self):
        prose = PAGE.replace('Evidence: none (owner-directed, 2026-10-14).\n\n**2.',
                             'Evidence: none (owner-directed, 2026-10-14); the head-to-head is a measurement.\n\n**2.')
        (self.wiki / 'raw/sources' / TARGET).write_text(prose, encoding='utf-8', newline='\n')
        self.finished('a', [DECISION])
        kept = UPDATED.replace('Evidence: none (owner-directed, 2026-10-14).\n\n**2.',
                               'Evidence: none (owner-directed, 2026-10-14); the head-to-head is a measurement.\n\n**2.')
        call, prompts = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                                     'draft': [draft_reply({'kind': 'update', 'summary': 's', 'why': 'w'}, kept),
                                               draft_reply({'kind': 'update', 'summary': 's', 'why': 'w'}, UPDATED)]})
        report = self.run_night(call)
        self.assertIn('head-to-head', prompts[2])
        self.assertIn('none (...)', prompts[2])
        self.assertEqual(len(report['candidates']), 1)

    def test_a_draft_still_refused_after_the_repair_is_reported_and_not_stored(self):
        self.finished('a', [DECISION])
        no_decisions = UPDATED.replace('## Decisions', '## Notes')
        bad = draft_reply({'kind': 'update', 'summary': 's', 'why': 'w', 'evidence_ids': []}, no_decisions)
        call, prompts = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                                     'draft': [bad, bad]})
        report = self.run_night(call)
        self.assertEqual(report['candidates'], [])
        self.assertEqual(report['refused'][0]['target'], TARGET)
        self.assertFalse((self.out / 'candidates').exists() and any((self.out / 'candidates').iterdir()))

    def test_a_too_long_why_is_refused_with_its_length_so_the_repair_can_fix_it(self):
        self.finished('a', [DECISION])
        long_why = draft_reply({'kind': 'update', 'summary': 's', 'why': 'w' * 2500, 'evidence_ids': []}, UPDATED)
        good = draft_reply({'kind': 'update', 'summary': 's', 'why': 'w', 'evidence_ids': []}, UPDATED)
        call, prompts = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                                     'draft': [long_why, good]})
        report = self.run_night(call)
        self.assertIn('why is 2500 characters; at most 2000', prompts[2])
        self.assertEqual(len(report['candidates']), 1)

    def test_evidence_ids_come_from_the_draft_citations_not_from_the_model(self):
        self.finished('a', [DECISION])
        call, _ = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                               'draft': [draft_reply({'kind': 'update', 'summary': 's', 'why': 'w',
                                                      'evidence_ids': ['made-up-id']}, UPDATED)]})
        report = self.run_night(call)
        folder = self.out / 'candidates' / '2026-10-14-skill-suggestions'
        self.assertEqual(json.loads((folder / 'candidate.json').read_text(encoding='utf-8'))['evidence_ids'], [])
        self.assertEqual(report['refused'], [])

    def test_every_reply_is_kept_and_pages_not_reached_are_reported(self):
        self.finished('a', [DECISION, dict(DECISION, claim='Second subject.')])
        bad = draft_reply({'kind': 'update', 'summary': 's', 'why': 'w', 'evidence_ids': []},
                          UPDATED.replace('## Decisions', '## Notes'))
        route = json.dumps({'routes': [{'item': 'I1', 'target': TARGET}, {'item': 'I2', 'new': 'second-subject'}]})
        call, prompts = self.caller({'route': [route], 'draft': [bad, bad]})
        report = hm.merge_night(self.ledger, self.wiki, self.out, call, RULES, 'night-1', '2026-10-26', cap_usd=0.03)
        replies = sorted(p.name for p in (self.out / 'replies').iterdir())
        self.assertEqual(replies, ['2026-10-14-skill-suggestions.1.txt', '2026-10-14-skill-suggestions.2.txt',
                                   'route.1.txt'])
        self.assertEqual((self.out / 'replies' / 'route.1.txt').read_text(encoding='utf-8'), route)
        self.assertEqual(report['not_drafted'], [{'target': '2026-10-26-second-subject.md', 'items': ['I2']}])

    def test_a_page_that_already_holds_the_items_gets_no_candidate(self):
        self.finished('a', [DECISION])
        call, _ = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                               'draft': [draft_reply({'kind': 'none', 'why': 'already in the Open list'})]})
        report = self.run_night(call)
        self.assertEqual(report['candidates'], [])
        self.assertEqual(report['unchanged'], [{'target': TARGET, 'why': 'already in the Open list'}])

    def test_the_cost_cap_stops_before_the_next_call_and_keeps_the_rows(self):
        self.finished('a', [DECISION])
        call, prompts = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                                     'draft': []})
        report = hm.merge_night(self.ledger, self.wiki, self.out, call, RULES, 'night-1', '2026-10-26', cap_usd=0.01)
        self.assertEqual(len(prompts), 1)
        self.assertIn('cap', report['stopped'])
        self.assertEqual(len(self.ledger.unmerged()), 1)

    def test_the_cost_cap_stops_when_the_next_call_could_pass_it(self):
        # Each call costs 0.01: route and draft spend 0.02, and a third call could pass 0.025.
        self.finished('a', [DECISION])
        bad = draft_reply({'kind': 'update', 'summary': 's', 'why': 'w'}, UPDATED.replace('## Decisions', '## Notes'))
        call, prompts = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                                     'draft': [bad, bad]})
        report = hm.merge_night(self.ledger, self.wiki, self.out, call, RULES, 'night-1', '2026-10-26', cap_usd=0.025)
        self.assertEqual(len(prompts), 2)
        self.assertIn('cap', report['stopped'])
        self.assertLessEqual(report['cost_usd'], 0.025)

    def test_a_failed_call_leaves_the_rows_for_the_next_night(self):
        self.finished('a', [DECISION])

        def call(prompt):
            import harvest_extract
            raise harvest_extract.CallError('overloaded')

        report = self.run_night(call)
        self.assertIn('overloaded', report['stopped'])
        self.assertEqual(len(self.ledger.unmerged()), 1)

    def test_after_a_stopped_night_only_the_items_not_reached_are_offered_again(self):
        self.finished('a', [DECISION, dict(DECISION, claim='Second subject.')])
        route = json.dumps({'routes': [{'item': 'I1', 'target': TARGET}, {'item': 'I2', 'new': 'second-subject'}]})
        good = draft_reply({'kind': 'update', 'summary': 's', 'why': 'w'}, UPDATED)
        call, prompts = self.caller({'route': [route], 'draft': [good]})
        report = hm.merge_night(self.ledger, self.wiki, self.out, call, RULES, 'night-1', '2026-10-26', cap_usd=0.025)
        self.assertIn('cap', report['stopped'])
        self.assertEqual(len(report['candidates']), 1)
        self.assertEqual(len(self.ledger.unmerged()), 1)
        call, prompts = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'new': 'second-subject'}]})],
                                     'draft': ['=== METADATA ===\n{"kind": "none", "why": "nothing new"}\n']})
        report = hm.merge_night(self.ledger, self.wiki, self.root / 'night-2', call, RULES, 'night-2', '2026-10-27')
        self.assertIn('Second subject.', prompts[0])
        self.assertNotIn('raised the skill nudge interval', prompts[0])
        self.assertEqual(self.ledger.unmerged(), [])

    def test_candidates_can_be_stored_apart_from_the_replies_and_report(self):
        self.finished('a', [DECISION])
        call, _ = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})],
                               'draft': [draft_reply({'kind': 'update', 'summary': 's', 'why': 'w'}, UPDATED)]})
        inbox = self.root / 'inbox' / 'night-1' / 'candidates'
        hm.merge_night(self.ledger, self.wiki, self.out, call, RULES, 'night-1', '2026-10-26', candidates_dir=inbox)
        self.assertTrue((inbox / '2026-10-14-skill-suggestions' / 'candidate.json').is_file())
        self.assertFalse((self.out / 'candidates').exists())
        self.assertTrue((self.out / 'report.json').is_file())

    def test_an_item_dropped_with_a_reason_is_taken(self):
        self.finished('a', [DECISION])
        call, _ = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'drop': 'chatter'}]})], 'draft': []})
        report = self.run_night(call)
        self.assertEqual(report['dropped'], {'I1': 'chatter'})
        self.assertEqual(self.ledger.unmerged(), [])

    def test_a_page_waiting_in_review_is_not_drafted_and_keeps_its_items(self):
        self.finished('a', [DECISION])
        call, prompts = self.caller({'route': [json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]})], 'draft': []})
        report = hm.merge_night(self.ledger, self.wiki, self.out, call, RULES, 'night-1', '2026-10-26', busy={TARGET})
        self.assertEqual(len(prompts), 1)
        self.assertEqual(report['waiting_on_review'], [{'target': TARGET, 'items': ['I1']}])
        self.assertEqual(report['not_drafted'], [])
        self.assertEqual(len(self.ledger.unmerged()), 1)

    def test_the_clock_stops_the_night_before_a_call_that_could_run_past_the_deadline(self):
        # Each call takes 100 s on this clock; after the route call at t=100 a draft call would end at 200.
        self.finished('a', [DECISION])
        now = [0.0]
        calls = []

        def call(prompt):
            now[0] += 100
            calls.append(prompt)
            return json.dumps({'routes': [{'item': 'I1', 'target': TARGET}]}), {'cost_usd': 0.01}
        report = hm.merge_night(self.ledger, self.wiki, self.out, call, RULES, 'night-1', '2026-10-26',
                                deadline=150.0, clock=lambda: now[0])
        self.assertEqual(len(calls), 1)
        self.assertIn('time', report['stopped'])
        self.assertEqual(len(self.ledger.unmerged()), 1)

    def test_a_night_with_nothing_to_draft_makes_no_call_and_marks_the_rows(self):
        self.finished('a', [])
        report = self.run_night(lambda prompt: self.fail('no call expected'))
        self.assertEqual((report['candidates'], report['cost_usd']), ([], 0.0))
        self.assertEqual(self.ledger.unmerged(), [])


if __name__ == '__main__':
    unittest.main()

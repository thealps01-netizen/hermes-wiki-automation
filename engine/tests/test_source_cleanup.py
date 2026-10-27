"""One-off cleanup of existing wiki sources: drafts that only remove, never rewrite.

Why: sources written before the personal-customisation and state-of-work rules (harvest_prompt.md,
What counts) still carry which theme or skin the owner uses, the looks rejected on the way and where a
piece of work stood. The cleanup reads every source once and proposes, through Review, an update that
drops what does not count, a retirement when nothing durable is left, or nothing.

Removal is by number: the model is shown the source with every line and sentence numbered and names
the numbers to remove; the code builds the draft, so no kept word can be reworded. The first real run
(2026-10-27, Phosphor) lost a lesson and an open question because each shared one entry with a skin
name or a state note and the model could only keep or drop whole entries.

These tests use a fake model; no paid call is made.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import source_cleanup as sc

RULES = (Path(__file__).resolve().parents[1] / 'harvest_prompt.md').read_text(encoding='utf-8')
AGENTS = '# Wiki\n\n## What may become a source\n\n- Knowledge that survives without the session.\n'
TARGET = '2026-10-17-skin-decisions.md'
PAGE = """# Skin: the owner's black desktop skin

## Scope

The black skin search and the skin that came out of it.

## Decisions

**1. The main app uses the built-in mono skin.**
- Why: the owner chose it.
- Evidence: none (owner-directed, 2026-10-26).

**2. A skin does not force headings to capitals.** It was renamed Noir on 2026-10-26.
- Why: forced capitals turn the Turkish "i" into "I". When a skin is renamed, every profile that names it is changed in the same step.
- Evidence: none (owner-directed, 2026-10-17).

## Changed decisions

- "noir is the active skin" (2026-10-17) -> mono (2026-10-26).

## Open

- Glass makes any skin slightly see-through; the assistant offered a fix and did not apply it. The owner can turn Glass off in Settings.

## Evidence

| Evidence id | What it holds |
|---|---|
| none | All decisions are owner-directed. |
"""
CLEANED = """# Skin lessons: building a desktop skin

## Scope

What building a desktop skin showed. Which skin the owner uses is not recorded here.

## Decisions

**2. A skin does not force headings to capitals.**
- Why: forced capitals turn the Turkish "i" into "I". When a skin is renamed, every profile that names it is changed in the same step.
- Evidence: none (owner-directed, 2026-10-17).

## Open

- Glass makes any skin slightly see-through. The owner can turn Glass off in Settings.

## Evidence

| Evidence id | What it holds |
|---|---|
| none | All decisions are owner-directed. |
"""
TITLE = 'Skin lessons: building a desktop skin'
SCOPE = 'What building a desktop skin showed. Which skin the owner uses is not recorded here.'
REMOVE = [{'id': 'decision 1', 'reason': 'which skin is in use is not wiki knowledge'},
          {'id': '13.2', 'reason': 'a skin rename is a personal customisation'},
          {'id': '17', 'reason': 'its section is left empty'},
          {'id': '19', 'reason': 'history of which skin was active'},
          {'id': '23.2', 'reason': 'where a piece of work stood'}]


def reply(metadata):
    return '=== METADATA ===\n' + json.dumps(metadata) + '\n=== END ===\n'


def update(remove=REMOVE):
    return reply({'kind': 'update', 'summary': 'Drops which skin is in use.', 'title': TITLE, 'scope': SCOPE,
                  'remove': remove})


GOOD = update()


class Cleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.wiki, self.inbox, self.runs = root / 'wiki', root / 'inbox', root / 'runs'
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir(parents=True)
        (self.wiki / 'AGENTS.md').write_text(AGENTS, encoding='utf-8')
        self.write(PAGE)
        self.state = root / 'state.json'

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text, name=TARGET, encoding='utf-8', newline='\n'):
        (self.wiki / 'raw/sources' / name).write_text(text, encoding=encoding, newline=newline)

    @staticmethod
    def model(replies, cost=0.2):
        calls = []

        def call(prompt):
            calls.append(prompt)
            return replies[len(calls) - 1], {'cost_usd': cost}
        return call, calls

    def run_cleanup(self, call, run='cleanup-1', **kwargs):
        options = dict(cap_usd=8.0, deadline=None, only=None, again=False)
        options.update(kwargs)
        return sc.run(wiki=self.wiki, inbox=self.inbox, runs=self.runs, state_path=self.state, caller=call,
                      rules_text=RULES, owner_rules=AGENTS, run_id=run, **options)

    def candidate(self, run='cleanup-1'):
        folder = self.inbox / run / 'candidates' / Path(TARGET).stem
        return json.loads((folder / 'candidate.json').read_text(encoding='utf-8')), folder

    def refused_after_repair(self, bad, words):
        call, calls = self.model([bad, bad])
        report = self.run_cleanup(call)
        self.assertEqual(len(calls), 2)
        self.assertIn('YOUR PREVIOUS REPLY WAS REFUSED', calls[1])
        self.assertEqual(report['candidates'], [])
        self.assertIn(words, ' '.join(report['refused'][0]['problems']))

    # The prompt

    def test_prompt_carries_the_rules_and_the_source_with_its_numbers(self):
        call, calls = self.model([GOOD])
        self.run_cleanup(call)
        prompt = calls[0]
        self.assertIn('Nor does a personal customisation', prompt)
        self.assertIn('Nor does the state of work', prompt)
        self.assertIn('## What may become a source', prompt)
        self.assertIn('[9] **1. The main app uses the built-in mono skin.**', prompt)
        self.assertIn('[23] - {1} Glass makes any skin slightly see-through; {2} the assistant offered a fix and did '
                      'not apply it. {3} The owner', prompt)

    def test_prompt_tells_the_model_to_keep_what_it_is_unsure_of(self):
        call, calls = self.model([GOOD])
        self.run_cleanup(call)
        self.assertIn('When you are unsure whether something counts, keep it', calls[0])

    # Building the draft by number

    def test_removals_by_number_build_the_draft_and_name_each_reason(self):
        call, _ = self.model([GOOD])
        report = self.run_cleanup(call)
        self.assertEqual([c['target'] for c in report['candidates']], [TARGET])
        meta, folder = self.candidate()
        self.assertEqual(meta['kind'], 'update')
        self.assertEqual((folder / 'source.md').read_text(encoding='utf-8'), CLEANED)
        self.assertEqual((folder / 'base.md').read_text(encoding='utf-8'), PAGE)
        self.assertIn('decision 1: which skin is in use is not wiki knowledge', meta['why'])
        self.assertIn('23.2: where a piece of work stood (removed: "the assistant offered a fix', meta['why'])

    def test_a_sentence_removed_from_a_reason_keeps_the_lesson_beside_it(self):
        text, problems = sc.apply_removals(PAGE, [{'id': '14.1', 'reason': 'test'}])
        self.assertEqual(problems, [])
        self.assertIn('\n- Why: When a skin is renamed, every profile that names it is changed in the same step.\n',
                      text)

    def test_a_clause_after_a_semicolon_goes_and_the_sentence_keeps_its_end(self):
        line = '- A is so. B holds; c was offered and not applied. D can be done.'
        self.assertEqual(sc.without_parts(line, {3}), ('- A is so. B holds. D can be done.', None))
        self.assertEqual(sc.without_parts(line, {2, 3}), ('- A is so. D can be done.', None))
        self.assertEqual(sc.without_parts(line, {1, 2, 3, 4}), (None, None))

    def test_the_first_clause_of_a_sentence_goes_only_with_its_later_clauses(self):
        call, _ = self.model([update(REMOVE[:-1] + [{'id': '23.1', 'reason': 'x'}])] * 2)
        report = self.run_cleanup(call)
        self.assertIn('opens a sentence', ' '.join(report['refused'][0]['problems']))

    def test_a_hard_wrapped_entry_is_one_numbered_line_and_keeps_its_label(self):
        # Many sources wrap at about 100 characters; a sentence that ran over two numbers lost its
        # "- Why: " label when its first line was removed (shadow run 2026-10-27).
        page = ('# T\n\n## Scope\n\nS.\n\n## Decisions\n\n**1. Text is larger, as\nthe owner asked.**\n'
                '- Why: the owner asked for larger text step by step (80 % scale, then 11 px,\n'
                '  then back). Text Size scales chat text only, so the panel follows the\n'
                '  app font.\n- Evidence: none.\n')
        self.assertIn('[10] - Why: {1} the owner asked for larger text step by step (80 % scale, then 11 px, '
                      'then back). {2} Text Size scales chat text only, so the panel follows the app font.',
                      sc.numbered(sc.unwrap(page)))
        self.assertIn('[9] **1. Text is larger, as the owner asked.**\n', sc.numbered(sc.unwrap(page)))
        draft, _, problems = sc.build_draft(page, {'remove': [{'id': '10.1', 'reason': 'x'}]})
        self.assertEqual(problems, [])
        self.assertIn('\n- Why: Text Size scales chat text only, so the panel follows the app font.\n', draft)

    def test_a_long_removal_before_a_kept_decision_is_a_deletion(self):
        # A Radagon shadow run was refused as "text that is not in the source: 2" after decision 1
        # went: the character diff paired the kept "**2." with the removed one.
        page = ('# T\n\n## Scope\n\nS.\n\n## Decisions\n\n**1. A halo and a glow on the\nbackground.**\n'
                '- Why: the owner wanted \"wow\"; the flat\n  background had no centre.\n- Evidence: none.\n\n'
                '**2. Crimson is accent only (bar, bubble edge, tab\nunderline). No reading text is crimson.**\n'
                '- Why: text colour must stay readable.\n- Evidence: none.\n')
        draft, _, problems = sc.build_draft(page, {'remove': [{'id': 'decision 1', 'reason': 'x'}]})
        self.assertEqual(problems, [])
        self.assertIn('## Decisions\n\n**2. Crimson is accent only (bar, bubble edge, tab underline). No reading '
                      'text is crimson.**\n- Why: text colour must stay readable.', draft)

    def test_a_reply_with_its_own_source_text_is_not_used(self):
        own = GOOD.replace('=== END ===', '=== SOURCE ===\n# Something else entirely\n=== END ===')
        call, _ = self.model([own])
        self.run_cleanup(call)
        _, folder = self.candidate()
        self.assertEqual((folder / 'source.md').read_text(encoding='utf-8'), CLEANED)

    def test_only_deletions_refuses_a_draft_with_a_word_that_is_not_in_the_source(self):
        reworded = CLEANED.replace('does not force headings', 'never forces headings')
        self.assertTrue(sc.only_deletions(PAGE, reworded))
        self.assertEqual(sc.only_deletions(PAGE, CLEANED), [])

    # Refusals

    def test_an_unknown_number_is_refused_after_one_repair(self):
        self.refused_after_repair(update(REMOVE + [{'id': '99', 'reason': 'x'}]), '99')

    def test_a_sentence_number_past_the_line_is_refused(self):
        self.refused_after_repair(update(REMOVE + [{'id': '23.9', 'reason': 'x'}]), '23.9')

    def test_a_removal_without_a_reason_is_refused(self):
        self.refused_after_repair(update(REMOVE[:-1] + [{'id': '23.2', 'reason': ''}]), 'reason')

    def test_a_decision_heading_is_removed_only_with_its_whole_decision(self):
        self.refused_after_repair(update(REMOVE + [{'id': '13.1', 'reason': 'x'}]), 'decision 2')

    def test_the_decisions_heading_cannot_be_removed(self):
        self.refused_after_repair(update(REMOVE + [{'id': '7', 'reason': 'x'}]), '## Decisions')

    def test_the_title_line_is_changed_only_through_the_title_field(self):
        self.refused_after_repair(update(REMOVE + [{'id': '1', 'reason': 'x'}]), 'title')

    def test_a_heading_whose_section_keeps_entries_cannot_be_removed(self):
        self.refused_after_repair(update(REMOVE + [{'id': '21', 'reason': 'x'}]), 'still has entries')

    def test_a_removal_citing_the_owner_rule_must_quote_it(self):
        cites = [{'id': 'decision 1', 'reason': 'this belongs in AGENTS.md'}] + REMOVE[1:]
        self.refused_after_repair(update(cites), 'quote')

    def test_a_quote_that_is_not_in_the_owner_rule_is_refused(self):
        cites = [{'id': 'decision 1', 'reason': 'already a rule in AGENTS.md',
                  'quote': 'Rename every reference in the same step.'}] + REMOVE[1:]
        self.refused_after_repair(update(cites), 'not in the owner')

    def test_a_quote_found_in_the_owner_rule_is_accepted(self):
        cites = [{'id': 'decision 1', 'reason': 'already a rule in AGENTS.md',
                  'quote': 'Knowledge that survives without the session.'}] + REMOVE[1:]
        call, _ = self.model([update(cites)])
        report = self.run_cleanup(call)
        self.assertEqual(len(report['candidates']), 1)

    # Warnings

    def test_a_draft_that_removes_more_than_half_of_the_text_says_so(self):
        many = REMOVE + [{'id': '14.1', 'reason': 'x'}, {'id': '21', 'reason': 'x'}, {'id': '23', 'reason': 'x'}]
        call, _ = self.model([update(many)])
        self.run_cleanup(call)
        meta, folder = self.candidate()
        share = sc.removed_share(PAGE, (folder / 'source.md').read_text(encoding='utf-8'))
        self.assertGreater(share, sc.LARGE_SHARE)
        self.assertTrue(meta['why'].startswith('Large removal:'), meta['why'])

    def test_a_small_removal_carries_no_warning(self):
        call, _ = self.model([update(REMOVE[-1:])])
        self.run_cleanup(call)
        meta, _ = self.candidate()
        self.assertFalse(meta['why'].startswith('Large removal:'), meta['why'])

    # Files written on Windows

    def test_a_source_with_a_byte_order_mark_keeps_its_title_line(self):
        self.write(PAGE, encoding='utf-8-sig')
        call, _ = self.model([GOOD])
        self.run_cleanup(call)
        _, folder = self.candidate()
        self.assertEqual((folder / 'source.md').read_text(encoding='utf-8'), CLEANED)

    def test_a_source_with_windows_line_endings_is_read_the_same(self):
        self.write(PAGE, newline='\r\n')
        call, _ = self.model([GOOD])
        self.run_cleanup(call)
        _, folder = self.candidate()
        self.assertEqual((folder / 'source.md').read_text(encoding='utf-8'), CLEANED)

    # Splitting into sentences

    def test_sentences_split_after_a_bold_heading_but_not_inside_it_or_after_an_abbreviation(self):
        prefix, parts = sc.pieces('**5. A is renamed B. The profile uses it.** It was tried. Then e.g. This.')
        self.assertEqual(prefix, '')
        self.assertEqual(parts, ['**5. A is renamed B. The profile uses it.** ', 'It was tried. ',
                                 'Then e.g. This.'])

    def test_a_bullet_label_stays_with_the_line_and_code_is_never_split(self):
        prefix, parts = sc.pieces('- Why: one thing. Another `a. B` thing.')
        self.assertEqual(prefix, '- Why: ')
        self.assertEqual(parts, ['one thing. ', 'Another `a. B` thing.'])

    def test_headings_and_table_rows_are_one_piece(self):
        self.assertEqual(sc.pieces('| a. B | c. D |'), ('', ['| a. B | c. D |']))
        self.assertEqual(sc.pieces('## Open. Now'), ('', ['## Open. Now']))

    # Outcomes and limits (unchanged behaviour)

    def test_nothing_to_remove_is_recorded_as_unchanged(self):
        call, _ = self.model([reply({'kind': 'none', 'why': 'every entry is durable'})])
        report = self.run_cleanup(call)
        self.assertEqual(report['unchanged'][0]['target'], TARGET)
        self.assertFalse(self.inbox.exists() and any(self.inbox.rglob('candidate.json')))

    def test_an_update_that_names_nothing_to_remove_is_refused(self):
        self.refused_after_repair(update([]), 'kind "none"')

    def test_a_source_with_nothing_durable_is_proposed_for_retirement(self):
        call, _ = self.model([reply({'kind': 'retire', 'summary': 'Only skin history.',
                                     'why': 'every decision records which skin is in use'})])
        report = self.run_cleanup(call)
        meta, _ = self.candidate()
        self.assertEqual(meta['kind'], 'retire')
        self.assertEqual(report['candidates'][0]['kind'], 'retire')

    def test_a_source_with_a_draft_waiting_in_review_is_skipped(self):
        waiting = self.inbox / 'night-1' / 'candidates' / 'x'
        waiting.mkdir(parents=True)
        (waiting / 'candidate.json').write_text(json.dumps({'target': TARGET}), encoding='utf-8')
        call, calls = self.model([])
        report = self.run_cleanup(call)
        self.assertEqual(calls, [])
        self.assertEqual(report['waiting_on_review'], [TARGET])

    def test_a_second_run_does_not_pay_for_a_source_already_read(self):
        call, _ = self.model([reply({'kind': 'none', 'why': 'durable'})])
        self.run_cleanup(call)
        again, calls = self.model([])
        report = self.run_cleanup(again, run='cleanup-2')
        self.assertEqual(calls, [])
        self.assertEqual(report['already_read'], [TARGET])

    def test_a_changed_source_is_read_again(self):
        call, _ = self.model([reply({'kind': 'none', 'why': 'durable'})])
        self.run_cleanup(call)
        self.write(PAGE.replace('slightly', 'a little'))
        again, calls = self.model([reply({'kind': 'none', 'why': 'durable'})])
        self.run_cleanup(again, run='cleanup-2')
        self.assertEqual(len(calls), 1)

    def test_the_cap_stops_before_the_next_call_and_the_rest_waits(self):
        second = '2026-10-18-other-decisions.md'
        self.write(PAGE, name=second)
        call, calls = self.model([reply({'kind': 'none', 'why': 'durable'})] * 2, cost=5.0)
        report = self.run_cleanup(call)
        self.assertEqual(len(calls), 1)
        self.assertIn('cap', report['stopped'])
        self.assertEqual(report['not_reached'], [second])

    def test_shadow_writes_only_into_its_own_folder_and_keeps_no_state(self):
        shadow = Path(self.tmp.name) / 'shadow'
        call, _ = self.model([GOOD])
        report = sc.run(wiki=self.wiki, inbox=shadow / 'inbox', runs=shadow, state_path=None, caller=call,
                        rules_text=RULES, owner_rules=AGENTS, run_id='cleanup-1', cap_usd=8.0, deadline=None,
                        only=[TARGET], again=False)
        self.assertEqual(len(report['candidates']), 1)
        self.assertFalse(self.inbox.exists())
        self.assertFalse(self.state.exists())
        self.assertTrue((shadow / 'cleanup-1' / 'report.json').is_file())


if __name__ == '__main__':
    unittest.main()

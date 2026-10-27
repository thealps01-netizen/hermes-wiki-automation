"""One-off cleanup of existing wiki sources: drafts that only remove, never rewrite.

Why: sources written before the personal-customisation rule (harvest_prompt.md, What counts) still
carry which theme or skin the owner uses and the looks rejected on the way. The cleanup reads every
source once and proposes, through Review, an update that drops what does not count, a retirement when
nothing durable is left, or nothing. These tests use a fake model; no paid call is made.
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

**2. A skin does not force headings to capitals.**
- Why: forced capitals turn the Turkish "i" into "I".
- Evidence: none (owner-directed, 2026-10-17).

## Changed decisions

- "noir is the active skin" (2026-10-17) -> mono (2026-10-26).

## Open

- Glass makes any skin slightly see-through.

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
- Why: forced capitals turn the Turkish "i" into "I".
- Evidence: none (owner-directed, 2026-10-17).

## Open

- Glass makes any skin slightly see-through.

## Evidence

| Evidence id | What it holds |
|---|---|
| none | All decisions are owner-directed. |
"""


def reply(metadata, source=None):
    text = '=== METADATA ===\n' + json.dumps(metadata) + '\n'
    if source is not None:
        text += '=== SOURCE ===\n' + source + '=== END ===\n'
    return text


REMOVED = [{'unit': 'decision 1', 'reason': 'which skin is in use is not wiki knowledge'},
           {'unit': 'changed decision 1', 'reason': 'history of which skin was active'}]
GOOD = reply({'kind': 'update', 'summary': 'Drops which skin is in use.', 'removed': REMOVED}, CLEANED)


class Cleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.wiki, self.inbox, self.runs = root / 'wiki', root / 'inbox', root / 'runs'
        (self.wiki / 'raw/sources').mkdir(parents=True)
        (self.wiki / 'raw/evidence').mkdir(parents=True)
        (self.wiki / 'AGENTS.md').write_text(AGENTS, encoding='utf-8')
        (self.wiki / 'raw/sources' / TARGET).write_text(PAGE, encoding='utf-8', newline='\n')
        self.state = root / 'state.json'

    def tearDown(self):
        self.tmp.cleanup()

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

    def test_prompt_carries_the_rule_the_page_and_the_removal_only_contract(self):
        call, calls = self.model([GOOD])
        self.run_cleanup(call)
        prompt = calls[0]
        self.assertIn('Nor does a personal customisation', prompt)
        self.assertIn('## What may become a source', prompt)
        self.assertIn(PAGE, prompt)
        self.assertIn('word for word', prompt)

    def test_a_removal_becomes_an_update_draft_in_review_with_its_reasons(self):
        call, _ = self.model([GOOD])
        report = self.run_cleanup(call)
        self.assertEqual([c['target'] for c in report['candidates']], [TARGET])
        meta, folder = self.candidate()
        self.assertEqual(meta['kind'], 'update')
        self.assertIn('decision 1: which skin is in use is not wiki knowledge', meta['why'])
        self.assertNotIn('removed', meta)
        self.assertEqual((folder / 'source.md').read_text(encoding='utf-8'), CLEANED)
        self.assertEqual((folder / 'base.md').read_text(encoding='utf-8'), PAGE)

    def test_a_reworded_entry_is_refused_after_one_repair(self):
        sneaky = CLEANED.replace('does not force headings to capitals', 'never uses capitals')
        bad = reply({'kind': 'update', 'summary': 's', 'removed': REMOVED}, sneaky)
        call, calls = self.model([bad, bad])
        report = self.run_cleanup(call)
        self.assertEqual(len(calls), 2)
        self.assertIn('YOUR PREVIOUS REPLY WAS REFUSED', calls[1])
        self.assertEqual(report['candidates'], [])
        self.assertTrue(any('not in the current page' in p for p in report['refused'][0]['problems']))

    def test_an_added_entry_is_refused(self):
        added = CLEANED.replace('## Open\n\n', '## Open\n\n- A brand new open question.\n')
        bad = reply({'kind': 'update', 'summary': 's', 'removed': REMOVED}, added)
        call, _ = self.model([bad, bad])
        report = self.run_cleanup(call)
        self.assertEqual(report['candidates'], [])

    def test_a_decision_dropped_without_a_reason_is_refused(self):
        bad = reply({'kind': 'update', 'summary': 's', 'removed': REMOVED[1:]}, CLEANED)
        call, calls = self.model([bad, GOOD])
        report = self.run_cleanup(call)
        self.assertIn('decision 1', calls[1])
        self.assertEqual(len(report['candidates']), 1)

    def test_a_removal_citing_the_owner_rule_must_quote_it(self):
        cites = [{'unit': 'decision 1', 'reason': 'this belongs in AGENTS.md'}] + REMOVED[1:]
        bad = reply({'kind': 'update', 'summary': 's', 'removed': cites}, CLEANED)
        call, calls = self.model([bad, bad])
        report = self.run_cleanup(call)
        self.assertEqual(report['candidates'], [])
        self.assertIn('quote', calls[1])

    def test_a_quote_that_is_not_in_the_owner_rule_is_refused(self):
        cites = [{'unit': 'decision 1', 'reason': 'already a rule in AGENTS.md',
                  'quote': 'Rename every reference in the same step.'}] + REMOVED[1:]
        bad = reply({'kind': 'update', 'summary': 's', 'removed': cites}, CLEANED)
        call, _ = self.model([bad, bad])
        report = self.run_cleanup(call)
        self.assertEqual(report['candidates'], [])
        self.assertTrue(any('not in the owner' in p for p in report['refused'][0]['problems']))

    def test_a_quote_found_in_the_owner_rule_is_accepted(self):
        cites = [{'unit': 'decision 1', 'reason': 'already a rule in AGENTS.md',
                  'quote': 'Knowledge that survives without the session.'}] + REMOVED[1:]
        good = reply({'kind': 'update', 'summary': 's', 'removed': cites}, CLEANED)
        call, _ = self.model([good])
        report = self.run_cleanup(call)
        self.assertEqual(len(report['candidates']), 1)

    def test_nothing_to_remove_is_recorded_as_unchanged(self):
        call, _ = self.model([reply({'kind': 'none', 'why': 'every entry is durable'})])
        report = self.run_cleanup(call)
        self.assertEqual(report['unchanged'][0]['target'], TARGET)
        self.assertFalse(self.inbox.exists() and any(self.inbox.rglob('candidate.json')))

    def test_a_source_with_nothing_durable_is_proposed_for_retirement(self):
        call, _ = self.model([reply({'kind': 'retire', 'summary': 'Only skin history.',
                                     'why': 'every decision records which skin is in use'})])
        report = self.run_cleanup(call)
        meta, folder = self.candidate()
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
        path = self.wiki / 'raw/sources' / TARGET
        path.write_text(PAGE.replace('slightly', 'a little'), encoding='utf-8', newline='\n')
        again, calls = self.model([reply({'kind': 'none', 'why': 'durable'})])
        self.run_cleanup(again, run='cleanup-2')
        self.assertEqual(len(calls), 1)

    def test_the_cap_stops_before_the_next_call_and_the_rest_waits(self):
        second = '2026-10-18-other-decisions.md'
        (self.wiki / 'raw/sources' / second).write_text(PAGE, encoding='utf-8', newline='\n')
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

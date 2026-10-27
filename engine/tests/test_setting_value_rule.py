"""The current value of a setting is one rule for every harvest stage and the cleanup.

Why: on 2026-10-27 a cleanup trial kept "the main app uses the built-in mono skin" because the reader
said a changed setting is a decision ("write the chosen value") and the cleanup could drop a Changed
decisions entry only with its decision. The owner ruled that a value he can change himself in the app's
settings is not wiki knowledge: the setting is where the value lives, and a copy in the wiki goes stale
without notice. Why a setting must have a certain value (a cause, a constraint) still counts. The
reader (harvest_extract.INSTRUCTIONS), the drafter (harvest_prompt.md, What counts) and the cleanup
(source_cleanup.cleanup_prompt) must carry it, or one stage lets back in what another drops.
"""
from pathlib import Path
import sys
import unittest

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
import harvest_extract as hx
import source_cleanup

CORE = ('the current value of a setting the owner can change himself: which skin, theme, model, provider or '
        'option is on right now (e.g. "the main app uses the dark skin", "the default model is the larger one"), '
        'and a changed decision that only records such a value; the setting itself is where the value lives, and '
        'a copy here drifts without notice; keep why a setting must have a certain value (a cause, a constraint)')


def flat(text):
    return ' '.join(text.split())


class SettingValueRuleTests(unittest.TestCase):
    def test_reader_lists_the_rule_under_do_not_list(self):
        rules = flat(hx.INSTRUCTIONS)
        self.assertIn("- a setting's current value: " + CORE, rules)
        self.assertLess(rules.index('Do not list:'), rules.index(CORE))

    def test_reader_no_longer_asks_for_the_chosen_value_of_a_setting(self):
        rules = flat(hx.INSTRUCTIONS)
        self.assertNotIn('Changing a setting', rules)
        self.assertIn('A changed setting counts only for the reason later work needs', rules)

    def test_drafter_carries_the_same_words(self):
        prompt = flat((ENGINE / 'harvest_prompt.md').read_text(encoding='utf-8'))
        counts = prompt[prompt.index('## What counts'):prompt.index('## Decide the kind')]
        self.assertIn('Nor does the current value of a setting: ' + CORE, counts)

    def test_cleanup_removes_it_and_its_changed_decision_entry(self):
        prompt = flat(source_cleanup.cleanup_prompt('x.md', '# x\n', '## What counts\n\nrules\n', ''))
        self.assertIn('the current value of a setting the owner can change himself', prompt)
        self.assertIn('only records which value a setting or customisation has now', prompt)


if __name__ == '__main__':
    unittest.main()

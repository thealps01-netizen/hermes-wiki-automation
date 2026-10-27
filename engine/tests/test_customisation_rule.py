"""The personal-customisation rule is one rule for both harvest stages.

Why: on 2026-10-26 the nightly harvest drafted "the main app keeps the built-in mono skin" and the
deletion of the owner's other skins into a wiki source. The reader treated "choosing a design direction"
as a decision, so which look the owner uses entered the wiki. The owner ruled that which theme, skin or
font is in use, and the looks rejected on the way, is not wiki knowledge; the lesson learned while
building one is. The reader (harvest_extract.INSTRUCTIONS) and the drafter (harvest_prompt.md, What
counts) must carry the same words, or one stage lets back in what the other drops.
"""
from pathlib import Path
import sys
import unittest

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
import harvest_extract as hx

CORE = ("which theme, skin, font, colour scheme, wallpaper or layout the owner uses, installed, renamed or "
        "deleted, and the looks rejected while searching for one; keep the lesson learned while building one "
        "(a cause, a constraint, a rule for next time)")


def flat(text):
    return ' '.join(text.split())


class CustomisationRuleTests(unittest.TestCase):
    def test_reader_lists_the_rule_under_do_not_list(self):
        rules = flat(hx.INSTRUCTIONS)
        self.assertIn('- a personal customisation: ' + CORE, rules)
        self.assertLess(rules.index('Do not list:'), rules.index(CORE))

    def test_reader_names_the_exception_beside_design_decisions(self):
        self.assertIn('a personal customisation is the exception listed below', flat(hx.INSTRUCTIONS))

    def test_drafter_carries_the_same_words(self):
        prompt = flat((ENGINE / 'harvest_prompt.md').read_text(encoding='utf-8'))
        counts = prompt[prompt.index('## What counts'):prompt.index('## Decide the kind')]
        self.assertIn('Nor does a personal customisation: ' + CORE, counts)


if __name__ == '__main__':
    unittest.main()

"""One numbered decision holds one choice and its reason.

Why: the source cleanup removes by number (source_cleanup.py), and on 2026-10-27 the drafter had put a
rule learned while renaming a skin inside a decision whose heading named the skin in use, so the lesson
could only be kept together with the customisation or dropped with it. The drafter (harvest_prompt.md)
therefore writes a second choice or a lesson as its own decision and one question per Open bullet.
"""
from pathlib import Path
import unittest

ENGINE = Path(__file__).resolve().parents[1]
RULE = ('One numbered decision holds one choice and its reason. A second choice, or a lesson learned on the way '
        '(a cause, a constraint, a rule for next time), is its own decision, and an `## Open` bullet holds one '
        'question, so each can later be kept, changed or dropped alone.')


class EntrySizeRuleTests(unittest.TestCase):
    def test_drafter_writes_one_choice_per_decision(self):
        prompt = ' '.join((ENGINE / 'harvest_prompt.md').read_text(encoding='utf-8').split())
        start = prompt.index('## Submit each candidate')
        submit = prompt[start:prompt.index('## Evidence Preserve', start)]
        self.assertIn(RULE, submit)


if __name__ == '__main__':
    unittest.main()

"""The state-of-work rule is one rule for both harvest stages.

Why: on 2026-10-27 the drafts waiting in Review held open items such as "whether pending-approvals #17
and #18 are merged and then installed" and "the first monthly semantic lint has not been run yet". The
conversation ended before the work did; the owner approved or installed it outside the chat, so the wiki
kept a stale "open" item. The owner ruled that where a piece of work stood is not wiki knowledge, while a
check nobody has made that later work depends on still is. The reader (harvest_extract.INSTRUCTIONS) and
the drafter (harvest_prompt.md, What counts) must carry the same words.
"""
from pathlib import Path
import sys
import unittest

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
import harvest_extract as hx

CORE = ('where a piece of work stood when the conversation ended: waiting for the owner\'s approval, not yet merged, installed, pushed, released or run (e.g. "the pull request is not merged yet", "the skill waits for approval", "the first monthly check has not run yet"); keep a check nobody has made that later work depends on (e.g. "the package was never tried on a machine without its build tools")')


def flat(text):
    return ' '.join(text.split())


class WorkStatusRuleTests(unittest.TestCase):
    def test_reader_lists_the_rule_under_do_not_list(self):
        rules = flat(hx.INSTRUCTIONS)
        self.assertIn('- the state of work: ' + CORE, rules)
        self.assertLess(rules.index('Do not list:'), rules.index(CORE))

    def test_drafter_carries_the_same_words(self):
        prompt = flat((ENGINE / 'harvest_prompt.md').read_text(encoding='utf-8'))
        counts = prompt[prompt.index('## What counts'):prompt.index('## Decide the kind')]
        self.assertIn('Nor does the state of work: ' + CORE, counts)

    def test_cleanup_names_it_among_what_it_removes(self):
        import source_cleanup
        prompt = flat(source_cleanup.cleanup_prompt('x.md', '# x\n', '## What counts\n\nrules\n', ''))
        self.assertIn('where a piece of work stood (waiting for approval', prompt)


if __name__ == '__main__':
    unittest.main()

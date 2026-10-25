"""Re-deriving a stale update draft against the page as it is now, using synthetic sources."""
import random
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import source_merge


def decision(n, title, why='Why: fixture.', evidence='Evidence: none (fixture).'):
    return f'**{n}. {title}**\n- {why}\n- {evidence}\n\n'


BASE = ('# Panels\n\n## Scope\n\nThis source covers the panels.\n\n## Decisions\n\n'
        + decision(1, 'One route per panel.') + decision(2, 'English copy only.')
        + decision(3, 'The watchdog repository stays.', evidence='Evidence: none (owner).')
        + '## Changed decisions\n\n- "Two panels" -> one panel (decision 3).\n\n'
        + '## Open\n\n- Is the light theme checked?\n\n'
        + '## Evidence\n\n| id | source |\n|---|---|\n| panels-notes | notes |\n')

METRO = ''.join(f'- Metro detail line {i}.\n' for i in range(30))
# The approved draft: a new decision with thirty lines, a new changed-decision bullet.
CURRENT = BASE.replace('## Changed decisions\n\n',
                       decision(4, 'Metro layout.', why='Why: the owner chose it.\n' + METRO.rstrip('\n'))
                       + '## Changed decisions\n\n- "Tiles" -> metro (decision 4).\n')
# The stale draft, written against BASE: decision 3 changes, one changed-decision bullet added.
DRAFT = BASE.replace('**3. The watchdog repository stays.**', '**3. The watchdog repository was deleted on 2026-10-17.**') \
            .replace('- "Two panels" -> one panel (decision 3).\n',
                     '- "Two panels" -> one panel (decision 3).\n- "Repository stays" -> deleted (decision 3).\n')


class SplitTests(unittest.TestCase):
    def test_units_join_back_to_the_exact_text(self):
        for text in (BASE, CURRENT, DRAFT, BASE.replace('\n', '\r\n'), '', 'no newline at end', '\n\n# H\n'):
            self.assertEqual(''.join(source_merge.split_units(text)), text)

    def test_a_numbered_decision_is_one_unit(self):
        units = source_merge.split_units(BASE)
        self.assertIn(decision(2, 'English copy only.'), units)
        self.assertIn('| panels-notes | notes |\n', units)
        self.assertIn('- Is the light theme checked?\n', units)
        self.assertIn('\n', units)


class MergeTests(unittest.TestCase):
    def test_incident_keeps_the_approved_lines_and_applies_the_draft(self):
        result = source_merge.merge(BASE, CURRENT, DRAFT)
        self.assertEqual(result.conflicts, [])
        self.assertIn('was deleted on 2026-10-17', result.text)
        self.assertIn('Metro detail line 29.', result.text)
        self.assertIn('- "Tiles" -> metro (decision 4).\n', result.text)
        self.assertIn('- "Repository stays" -> deleted (decision 3).\n', result.text)
        self.assertNotIn('The watchdog repository stays.', result.text)
        self.assertEqual(source_merge.preservation_problems(BASE, CURRENT, DRAFT, result.text), [])
        self.assertFalse(result.already_applied)

    def test_applying_the_stale_draft_as_is_fails_the_preservation_check(self):
        problems = source_merge.preservation_problems(BASE, CURRENT, DRAFT, DRAFT)
        self.assertTrue(problems)
        self.assertIn('Metro layout.', ' '.join(problems))

    def test_both_sides_changing_one_decision_differently_is_a_conflict(self):
        current = BASE.replace('**3. The watchdog repository stays.**', '**3. The watchdog repository is archived.**')
        result = source_merge.merge(BASE, current, DRAFT)
        self.assertIsNone(result.text)
        self.assertEqual(len(result.conflicts), 1)
        conflict = result.conflicts[0]
        self.assertIn('stays', conflict['base'])
        self.assertIn('archived', conflict['current'])
        self.assertIn('deleted', conflict['draft'])

    def test_lines_added_to_one_paragraph_by_both_sides_are_both_kept(self):
        current = BASE.replace('This source covers the panels.\n', 'This source covers the panels.\nMetro since 10-14.\n')
        draft = DRAFT.replace('This source covers the panels.\n', 'This source covers the panels.\nRepository deleted 10-17.\n')
        result = source_merge.merge(BASE, current, draft)
        self.assertEqual(result.conflicts, [])
        self.assertIn('This source covers the panels.\nMetro since 10-14.\nRepository deleted 10-17.\n', result.text)
        self.assertIn('was deleted on 2026-10-17', result.text)
        self.assertEqual(source_merge.preservation_problems(BASE, current, draft, result.text), [])

    def test_identical_changes_count_once(self):
        result = source_merge.merge(BASE, DRAFT, DRAFT)
        self.assertEqual(result.text, DRAFT)
        self.assertTrue(result.already_applied)

    def test_two_new_decisions_with_one_number_are_renumbered(self):
        current = BASE.replace('## Changed decisions', decision(4, 'Metro layout.') + '## Changed decisions')
        draft = BASE.replace('## Changed decisions', decision(4, 'Repository deleted.') + '## Changed decisions')
        result = source_merge.merge(BASE, current, draft)
        self.assertEqual(result.conflicts, [])
        self.assertIn('**4. Metro layout.**', result.text)
        self.assertIn('**5. Repository deleted.**', result.text)
        self.assertLess(result.text.index('**4. Metro'), result.text.index('**5. Repository'))
        self.assertEqual(result.renumbered, [(4, 5)])
        self.assertEqual(source_merge.preservation_problems(BASE, current, draft, result.text), [])

    def test_a_rewritten_untouched_unit_fails_the_preservation_check(self):
        result = source_merge.merge(BASE, CURRENT, DRAFT)
        bad = result.text.replace('**1. One route per panel.**', '**1. Two routes per panel.**')
        self.assertTrue(source_merge.preservation_problems(BASE, CURRENT, DRAFT, bad))

    def test_line_endings_of_the_current_page_are_kept(self):
        crlf = lambda s: s.replace('\n', '\r\n')
        result = source_merge.merge(crlf(BASE), crlf(CURRENT), crlf(DRAFT))
        self.assertEqual(result.conflicts, [])
        self.assertNotIn('\n', result.text.replace('\r\n', ''))

    def test_disjoint_random_edits_merge_like_applying_both(self):
        rng = random.Random(20261025)
        for _ in range(200):
            base = [f'- item {i}.\n' for i in range(12)]
            positions = rng.sample(range(12), 6)
            mine, theirs = set(positions[:3]), set(positions[3:])
            current = [f'- item {i} current.\n' if i in mine else u for i, u in enumerate(base)]
            draft = [f'- item {i} draft.\n' if i in theirs else u for i, u in enumerate(base)]
            both = [f'- item {i} current.\n' if i in mine else f'- item {i} draft.\n' if i in theirs else u
                    for i, u in enumerate(base)]
            head = '## Open\n\n'
            result = source_merge.merge(head + ''.join(base), head + ''.join(current), head + ''.join(draft))
            self.assertEqual(result.text, head + ''.join(both))


if __name__ == '__main__':
    unittest.main()

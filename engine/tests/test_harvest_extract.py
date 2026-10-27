import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import harvest_extract as hx  # noqa: E402

PART = """# Skill suggestions

### user · 2026-10-14T09:30:42+03:00

why do so many skill suggestions arrive

### assistant · 2026-10-14T09:31:25+03:00

Background review runs after every reply and proposes skills.

### user · 2026-10-14T09:35:00+03:00

then raise the interval to 40, keep the approval gate on
"""


def reply(*items, extra=''):
    return json.dumps({'items': list(items)}, ensure_ascii=False) + extra


GOOD = {'type': 'decision', 'claim': 'Raise the nudge interval to 40.', 'quote': 'raise the interval to 40',
        'message_index': 3, 'later_use': 'A later session keeps the interval at 40 instead of resetting it.'}

AGENTS = """# Wiki rules

## What may become a source

- Knowledge that survives without the session: verified findings, decisions with rationale.
- Not narration of attempts.

## Evidence copies

Unrelated text.
"""


class Turns(unittest.TestCase):
    def test_turns_split_at_message_headings_and_keep_the_title_out(self):
        title, turns = hx.turns(PART)
        self.assertEqual(title.strip(), '# Skill suggestions')
        self.assertEqual(len(turns), 3)
        self.assertTrue(turns[2].startswith('### user · 2026-10-14T09:35:00'))

    def test_context_tail_is_the_last_turns_of_the_previous_part(self):
        tail = hx.context_tail(PART, 2)
        self.assertNotIn('why do so many', tail)
        self.assertIn('Background review runs', tail)
        self.assertIn('raise the interval to 40', tail)


class Prompt(unittest.TestCase):
    def test_the_model_is_told_first_that_it_reads_a_record_and_is_not_a_participant(self):
        prompt = hx.build_prompt(PART)
        self.assertTrue(prompt.startswith(hx.FRAME))
        self.assertIn('not a participant', hx.FRAME)

    def test_conversation_comes_first_and_instructions_last(self):
        prompt = hx.build_prompt(PART)
        self.assertLess(prompt.index('raise the interval to 40'), prompt.index('"items"'))
        self.assertTrue(prompt.rstrip().endswith(hx.SCHEMA.strip()))

    def test_context_only_turns_are_marked_and_placed_before_the_part(self):
        prompt = hx.build_prompt(PART, context='### user · x\n\nearlier words\n')
        self.assertLess(prompt.index('CONTEXT ONLY'), prompt.index('earlier words'))
        self.assertLess(prompt.index('earlier words'), prompt.index('# Skill suggestions'))


class Parse(unittest.TestCase):
    def test_valid_items_are_returned(self):
        items, problems = hx.parse_reply(reply(GOOD))
        self.assertEqual(items, [GOOD])
        self.assertEqual(problems, [])

    def test_the_last_complete_object_wins_when_the_model_corrects_itself(self):
        first = dict(GOOD, claim='first try')
        items, _ = hx.parse_reply(reply(first) + '\n\nCorrected:\n' + reply(GOOD))
        self.assertEqual(items, [GOOD])

    def test_items_outside_the_schema_are_reported_not_kept(self):
        bad_type = dict(GOOD, type='opinion')
        no_index = {k: v for k, v in GOOD.items() if k != 'message_index'}
        items, problems = hx.parse_reply(reply(GOOD, bad_type, no_index))
        self.assertEqual(items, [GOOD])
        self.assertEqual(len(problems), 2)

    def test_a_reply_without_an_items_object_is_an_error(self):
        with self.assertRaises(hx.ExtractError):
            hx.parse_reply('I could not find anything.')


class Quotes(unittest.TestCase):
    def test_quote_must_occur_in_the_part_with_whitespace_collapsed(self):
        spaced = dict(GOOD, quote='raise  the\ninterval to 40')
        invented = dict(GOOD, quote='set the interval to 100 now')
        ok, bad = hx.check_quotes([spaced, invented], PART)
        self.assertEqual(ok, [spaced])
        self.assertEqual(bad, [invented])

    def test_markdown_emphasis_and_code_marks_are_ignored_on_both_sides(self):
        part = PART + '\n### assistant · x\n\nBoth are written in **Python + PyQt6** with `uv` setup.\n'
        ok, bad = hx.check_quotes([dict(GOOD, quote='Both are written in Python + PyQt6 with uv setup')], part)
        self.assertEqual(len(ok), 1)
        self.assertEqual(bad, [])

    def test_the_prompt_asks_for_the_approved_proposal_not_a_one_word_reply(self):
        self.assertIn('quote the proposal it approves', hx.INSTRUCTIONS)

    def test_a_quote_from_the_context_only_turns_does_not_count(self):
        ok, bad = hx.check_quotes([dict(GOOD, quote='earlier words of the previous part')], PART)
        self.assertEqual(ok, [])
        self.assertEqual(len(bad), 1)


class Durable(unittest.TestCase):
    def test_the_owner_rule_section_is_cut_from_agents_md_up_to_the_next_heading(self):
        rules = hx.source_rules(AGENTS)
        self.assertIn('Knowledge that survives without the session', rules)
        self.assertIn('Not narration of attempts', rules)
        self.assertNotIn('Unrelated text', rules)

    def test_a_missing_rule_section_stops_the_run(self):
        with self.assertRaises(hx.ExtractError):
            hx.source_rules('# Wiki rules\n\nnothing here\n')

    def test_the_owner_rule_is_in_the_prompt_verbatim_before_the_instructions(self):
        rules = hx.source_rules(AGENTS)
        prompt = hx.build_prompt(PART, rules=rules)
        self.assertIn(rules, prompt)
        self.assertLess(prompt.index(rules), prompt.index(hx.INSTRUCTIONS))

    def test_an_item_without_a_later_use_is_dropped(self):
        no_use = dict(GOOD, later_use='  ')
        items, problems = hx.parse_reply(reply(GOOD, no_use))
        self.assertEqual(items, [GOOD])
        self.assertIn('later_use', problems[0])

    def test_instructions_name_progress_notes_and_closing_decisions(self):
        text = hx.INSTRUCTIONS
        for phrase in ('progress', 'not adopted', 'without its content', 'chosen value'):
            self.assertIn(phrase, text)

    def test_examples_include_an_empty_answer_and_sit_after_the_conversation_before_the_schema(self):
        prompt = hx.build_prompt(PART)
        self.assertIn('{"items": []}', hx.EXAMPLES)
        self.assertLess(prompt.index('=== END CONVERSATION PART ==='), prompt.index(hx.EXAMPLES))
        self.assertLess(prompt.index(hx.EXAMPLES), prompt.rindex(hx.SCHEMA))


class Extract(unittest.TestCase):
    def test_one_repair_call_fixes_bad_quotes_then_stops(self):
        invented = dict(GOOD, quote='set the interval to 100 now')
        calls = []

        def caller(prompt):
            calls.append(prompt)
            if len(calls) == 1:
                return reply(GOOD, invented), {'session_id': 's1', 'cost_usd': 0.01}
            return reply(dict(invented, quote='keep the approval gate on')), {'session_id': 's2', 'cost_usd': 0.002}

        result = hx.extract([PART], caller)
        self.assertEqual(len(calls), 2)
        self.assertIn('set the interval to 100 now', calls[1])
        self.assertEqual([i['quote'] for i in result['items']], ['raise the interval to 40', 'keep the approval gate on'])
        self.assertEqual(result['problems'], [])
        self.assertAlmostEqual(result['cost_usd'], 0.012)
        self.assertEqual(result['sessions'], ['s1', 's2'])

    def test_quotes_still_bad_after_the_repair_are_problems_not_items(self):
        invented = dict(GOOD, quote='set the interval to 100 now')

        def caller(prompt):
            return reply(invented), {'session_id': 's', 'cost_usd': 0.0}

        result = hx.extract([PART], caller)
        self.assertEqual(result['items'], [])
        self.assertEqual(len(result['problems']), 1)
        self.assertIn('quote', result['problems'][0])

    def test_every_part_is_read_and_later_parts_get_the_previous_tail_as_context(self):
        second = PART.replace('# Skill suggestions', '# Skill suggestions (part 2 of 2)')
        prompts = []

        def caller(prompt):
            prompts.append(prompt)
            return reply(), {'session_id': f's{len(prompts)}', 'cost_usd': 0.0}

        result = hx.extract([PART, second], caller)
        self.assertEqual(len(prompts), 2)
        self.assertNotIn('CONTEXT ONLY', prompts[0])
        self.assertIn('CONTEXT ONLY', prompts[1])
        self.assertEqual(result['parts_read'], 2)

    def test_a_reply_without_json_gets_one_format_repair_call(self):
        answers = ['I am waiting for your next task.', reply(GOOD)]
        prompts = []

        def caller(prompt):
            prompts.append(prompt)
            return answers[len(prompts) - 1], {'session_id': f's{len(prompts)}', 'cost_usd': 0.0}

        result = hx.extract([PART], caller)
        self.assertEqual(len(prompts), 2)
        self.assertIn('did not contain', prompts[1])
        self.assertIn('raise the interval to 40', prompts[1])
        self.assertEqual(len(result['items']), 1)
        self.assertIsNone(result['error'])

    def test_a_second_reply_without_json_is_an_error_that_keeps_the_reply(self):
        def caller(prompt):
            return 'Understood. Waiting.', {'session_id': 's', 'cost_usd': 0.0}

        result = hx.extract([PART], caller)
        self.assertEqual(result['parts_read'], 0)
        self.assertIn('no complete', result['error'])
        self.assertEqual(result['reply_tail'], 'Understood. Waiting.')
        self.assertFalse(result['retryable'])

    def test_a_failed_call_is_reported_and_the_conversation_is_not_done(self):
        def caller(prompt):
            raise hx.CallError('provider overloaded')

        result = hx.extract([PART], caller)
        self.assertEqual(result['parts_read'], 0)
        self.assertIn('provider overloaded', result['error'])
        self.assertTrue(result['retryable'])

    def test_tokens_of_every_call_are_added_up(self):
        def caller(prompt):
            return reply(GOOD), {'session_id': 's', 'cost_usd': 0.01,
                                 'usage': {'input_tokens': 100, 'output_tokens': 7, 'cache_read_tokens': 30,
                                           'cache_write_tokens': None}}

        result = hx.extract([PART, PART], caller)
        self.assertEqual((result['tokens_in'], result['tokens_out']), (260, 14))


class Version(unittest.TestCase):
    def test_the_prompt_version_is_stable_and_follows_the_owner_rule(self):
        rules = hx.source_rules(AGENTS)
        self.assertEqual(hx.prompt_version(rules), hx.prompt_version(rules))
        self.assertNotEqual(hx.prompt_version(rules), hx.prompt_version(rules + '- one more rule\n'))
        self.assertRegex(hx.prompt_version(rules), r'^[0-9a-f]{12}$')


class Transport(unittest.TestCase):
    def test_command_uses_safe_mode_so_no_plugin_mcp_or_owner_rules_reach_the_model(self):
        command = hx.chat_command('hermes', Path('p.md'), 'claude-haiku-4-5', 'anthropic')
        self.assertEqual(command[:2], ['hermes', 'chat'])
        for flag in ('--query-file', '-Q', '--safe-mode', '-t', '-m', '--provider'):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index('-t') + 1], hx.NO_FILE_TOOLSET)

    def test_session_id_is_read_from_the_quiet_footer(self):
        self.assertEqual(hx.session_id_from('noise\nsession_id: 20261025_204538_03cce1\n'), '20261025_204538_03cce1')
        self.assertIsNone(hx.session_id_from('nothing here'))


class CostCap(unittest.TestCase):
    def test_the_next_call_is_judged_by_the_dearest_call_so_far(self):
        self.assertFalse(hx.over_cap(0.0, 0.0, 1.0))      # nothing spent yet: the first call is allowed
        self.assertFalse(hx.over_cap(0.4, 0.3, 1.0))
        self.assertTrue(hx.over_cap(0.8, 0.3, 1.0))
        self.assertFalse(hx.over_cap(5.0, 1.0, None))     # no cap
        self.assertTrue(hx.over_cap(1.0, 0.0, 1.0))       # spent reaches the cap
        self.assertFalse(hx.over_cap(0.7, 0.3, 1.0))      # a call that would land exactly on the cap fits
        self.assertTrue(hx.over_cap(0.0, 0.0, 0.0))       # a zero cap allows nothing

    def test_the_next_call_must_end_before_the_deadline_judged_by_the_slowest_call(self):
        self.assertFalse(hx.out_of_time(100.0, 40.0, None))
        self.assertFalse(hx.out_of_time(100.0, 40.0, 140.0))
        self.assertTrue(hx.out_of_time(100.0, 41.0, 140.0))
        self.assertTrue(hx.out_of_time(140.0, 0.0, 140.0))



class SessionCost(unittest.TestCase):
    """A chat call's cost comes from Hermes' own session store; a missing figure is named, never guessed."""

    COLUMNS = ('id TEXT, model TEXT, started_at REAL, ended_at REAL, end_reason TEXT, input_tokens INTEGER, '
               'output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER, '
               'estimated_cost_usd REAL, actual_cost_usd REAL, cost_status TEXT')

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def sessions(self, *rows):
        import sqlite3
        db = sqlite3.connect(self.home / 'state.db')
        db.execute(f'CREATE TABLE IF NOT EXISTS sessions ({self.COLUMNS})')
        db.executemany('INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        db.commit()
        db.close()

    def test_usage_and_cost_come_from_the_session_store(self):
        self.sessions(('session-one', 'fixture-model', 1.0, 2.0, 'cli_close', 30, 35011, 1309893, 0, 0.9451643, None,
                       'estimated'),
                      ('session-two', 'fixture-model', 1.0, 2.0, 'cli_close', 1, 1, 0, 0, 0.5, 0.25, 'actual'))
        self.assertEqual(hx.usage(self.home, 'session-one'), {
            'model': 'fixture-model', 'ended': True, 'end_reason': 'cli_close', 'input_tokens': 30,
            'output_tokens': 35011, 'cache_read_tokens': 1309893, 'cache_write_tokens': 0,
            'cost_usd': 0.9451643, 'cost_status': 'estimated'})
        self.assertEqual((hx.usage(self.home, 'session-two')['cost_usd'],
                          hx.usage(self.home, 'session-two')['cost_status']), (0.25, 'actual'))

    def test_a_missing_figure_is_reported_not_guessed(self):
        self.assertIsNone(hx.usage(self.home, None))
        self.assertIn('error', hx.usage(None, 'session-one'))
        self.assertIn('error', hx.usage(self.home, 'session-one'))
        self.sessions(('other', 'fixture-model', 1.0, 2.0, 'cli_close', 1, 1, 0, 0, 0.01, None, 'estimated'))
        self.assertIn('not in the profile session store', hx.usage(self.home, 'session-one')['error'])


if __name__ == '__main__':
    unittest.main()

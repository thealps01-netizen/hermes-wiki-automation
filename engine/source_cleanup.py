"""One-off cleanup of existing wiki sources: drafts that only remove, never rewrite.

WHY: sources written before the personal-customisation rule (harvest_prompt.md, "What counts") still
carry knowledge that does not count, such as which theme or skin the owner uses and the looks rejected
on the way. New conversations are filtered by that rule; old sources are not. This job reads every
source once and proposes, through Review, one of:
- update: the same source with the entries that do not count removed (each removed decision or
  finding named with its reason in the candidate's `why`);
- retire: the whole source, when nothing durable is left;
- nothing, when every entry counts.
Nothing reaches the wiki without the owner's approval (`wiki_candidates.py approve`).

REMOVAL ONLY: code refuses a draft that rewords or adds anything. Every entry of the draft (a decision
or finding block, a bullet, a table row, a heading) must be an entry of the current source, word for
word; only the title line and the Scope paragraph may be rewritten to describe what remains. A removed
decision or finding without a reason is refused. A refused draft gets one repair call, then it is
reported as refused. The drafting checks every other draft passes (`draft_adapter.check_draft`) run too.

LIMITS (settings.json "source_cleanup", defaults below): a cost cap and a time limit per run, judged
before each call by the dearest and slowest call so far. A source with a draft waiting in Review is
skipped. A source already read at the same content (state.json) is not read again, so a second run
never pays twice; `--again` reads it anyway.

USAGE (run from the installed engine release; prints one JSON line):
    python source_cleanup.py                       # every source, drafts go to Review
    python source_cleanup.py --only <file.md> ...  # these sources only
    python source_cleanup.py --shadow <folder>     # drafts and report into <folder> only; Review,
                                                   # the wiki and state.json are untouched
EXIT: 0 = the run finished or stopped at a limit (the report says which); 1 = it could not run.
OUTPUT: candidates in <audit>/inbox/<run>/candidates/; report.json and every model reply in
<audit>/source-cleanup/<run>/; what was read in <audit>/source-cleanup/state.json.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import secrets
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import draft_adapter
import evidence_store
import harvest_extract as hx
import harvest_merge as hm
from harvest_night import busy_targets

DEFAULTS = {'model': 'claude-opus-5-5', 'provider': 'anthropic', 'cap_usd': 8.0, 'minutes': 45,
            'call_timeout_seconds': 600}
CLEANUP_MARK = '=== CLEAN ONE SOURCE ==='
ENTRY_START = re.compile(r'^(?:- |#|\||\*\*|\d+\.\s)')
REASONED = ('decision ', 'finding F')
WHY_LIMIT = 2000


class CleanupError(Exception):
    pass


def entries(text):
    """The source's entries, whitespace-normalised: a heading, a bullet with its indented lines, a
    table row, or a paragraph (a decision or finding block runs until its next bullet or blank line)."""
    out = []
    current = None
    for line in text.splitlines():
        if not line.strip():
            current = None
            continue
        if current is None or ENTRY_START.match(line):
            out.append(line.strip())
            current = len(out) - 1
        else:
            out[current] += ' ' + line.strip()
    return [hx.norm(entry) for entry in out]


def body_entries(text):
    """Entries outside the two places a cleanup may rewrite: the title line and the Scope paragraph."""
    out, in_scope = [], False
    for entry in entries(text):
        if entry.startswith('# '):
            continue
        if entry.startswith('## '):
            in_scope = entry == '## Scope'
            out.append(entry)
            continue
        if not in_scope:
            out.append(entry)
    return out


def foreign_entries(base, draft):
    """Draft entries that are not entries of the current page (reworded or added)."""
    available = collections.Counter(body_entries(base))
    foreign = []
    for entry in body_entries(draft):
        if available[entry]:
            available[entry] -= 1
        else:
            foreign.append(entry)
    return foreign


def cleanup_prompt(target, page, rules_text, owner_rules):
    return (f'{CLEANUP_MARK}\nYou clean one existing source of the owner\'s wiki. It was written before the rules '
            'below were sharpened, so it may hold entries that do not count. You only remove; you never reword, '
            'merge, renumber or add.\n\n'
            f'=== WHAT COUNTS (the drafting job\'s rule) ===\n{hm.section(rules_text, "## What counts")}'
            f'=== END ===\n\n=== THE OWNER\'S RULE ===\n{owner_rules}=== END ===\n\n'
            f'The current source {target}, in full:\n=== CURRENT SOURCE ===\n{page}=== END CURRENT SOURCE ===\n\n'
            'Contract:\n'
            '- Keep every remaining entry word for word: a decision or finding with its Why:, Rejected: and '
            'Evidence: lines, each bullet, each table row, each heading. You may delete whole entries only: a '
            'whole decision or finding, or single bullet lines.\n'
            '- You may rewrite the title line and the Scope paragraph so they describe what remains; nothing '
            'else.\n'
            '- Keep the numbers of kept decisions and findings; gaps in the numbering are fine.\n'
            '- Remove an entry only when it does not count under the rules above: which personal customisation '
            'is in use and the looks rejected on the way, facts about one day or one machine\'s state, how work '
            'was done, attempts that were reverted. Do not remove a decision because it is old, small or '
            'owner-directed.\n'
            '- Remove a Changed decisions entry only when it is about a removed decision. Remove an Evidence row '
            'only when no kept entry cites it. Remove a section heading only when its section is left empty; '
            '## Decisions always stays.\n'
            '- When no decision or finding is left, the whole source is retired.\n\n'
            'Reply in exactly this format, nothing before or after:\n'
            '=== METADATA ===\n{"kind": "update|retire|none", "summary": "...", "why": "...", '
            '"removed": [{"unit": "decision 3", "reason": "..."}]}\n'
            '=== SOURCE ===\n<the complete cleaned source>\n=== END ===\n'
            'kind "update": the SOURCE block is the cleaned source; "removed" names every removed decision as '
            '"decision N" and every removed finding as "finding FN", each with a one-sentence reason, and may name '
            'other removed entries too. kind "retire": no SOURCE block; summary and why say why nothing durable '
            'is left. kind "none": only "why", no SOURCE block, when every entry counts.\n'
            'summary and why are plain text of one to three sentences, at most 2000 characters.\n')


def parse_reply(reply):
    text = reply or ''
    head = text.find('=== METADATA ===')
    if head < 0:
        raise CleanupError('The reply has no === METADATA === block')
    try:
        metadata = json.JSONDecoder().raw_decode(text, text.index('{', head))[0]
    except ValueError as exc:
        raise CleanupError('The METADATA block is not one JSON object') from exc
    if not isinstance(metadata, dict) or metadata.get('kind') not in ('update', 'retire', 'none'):
        raise CleanupError('METADATA kind must be update, retire or none')
    if metadata['kind'] != 'update':
        return metadata, None
    start, end = text.find('=== SOURCE ===\n'), text.rfind('=== END ===')
    if start < 0 or end < start:
        raise CleanupError('The reply has no complete === SOURCE === ... === END === block')
    return metadata, text[start + len('=== SOURCE ===\n'):end]


def removal_reasons(metadata):
    out = {}
    for entry in metadata.get('removed') or []:
        if isinstance(entry, dict) and isinstance(entry.get('unit'), str) and isinstance(entry.get('reason'), str):
            out[hx.norm(entry['unit'])] = hx.norm(entry['reason'])
    return out


def why_text(reasons, lost):
    """The candidate's `why`: every removed unit with its reason, then the other dropped units."""
    named = [f'{unit}: {reason}' for unit, reason in reasons.items()]
    other = [unit for unit in lost if unit not in reasons]
    text = 'Removed (does not count): ' + '; '.join(named) if named else 'Removed entries that do not count.'
    if other:
        text += ' Also dropped: ' + '; '.join(other)
    return text if len(text) <= WHY_LIMIT else text[:WHY_LIMIT - 3] + '...'


def proposal(wiki, candidates, target, page, metadata, source):
    """(candidate metadata, problems) for one parsed reply."""
    path = Path(wiki) / 'raw' / 'sources' / target
    base_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = metadata.get('summary')
    if not (isinstance(summary, str) and 1 <= len(summary) <= WHY_LIMIT):
        return None, ['summary must be plain text of 1 to 2000 characters']
    if metadata['kind'] == 'retire':
        why = metadata.get('why')
        if not (isinstance(why, str) and 1 <= len(why) <= WHY_LIMIT):
            return None, ['why must be plain text of 1 to 2000 characters']
        candidate = {'kind': 'retire', 'target': target, 'summary': summary, 'why': why, 'evidence_ids': [],
                     'base_sha256': base_sha}
        return candidate, []
    problems = [f'this entry is not in the current page word for word (reworded or added): {entry[:200]}'
                for entry in foreign_entries(page, source)]
    lost = hm.lost_units(page, source) + [f'open item "{item[:120]}"' for item in hm.removed_open(page, source)]
    reasons = removal_reasons(metadata)
    unreasoned = [unit for unit in lost if unit.startswith(REASONED) and unit not in reasons]
    if unreasoned:
        problems.append('these were removed without a reason in "removed": ' + ', '.join(unreasoned))
    if not lost:
        problems.append('nothing was removed; reply with kind "none" instead')
    if problems:
        return None, problems
    lines, table = evidence_store._evidence_texts(source)
    candidate = {'kind': 'update', 'target': target, 'summary': summary, 'why': why_text(reasons, lost),
                 'evidence_ids': sorted(evidence_store.cited_ids(lines + table)), 'base_sha256': base_sha}
    return candidate, []


def clean_one(target, wiki, candidates, rules_text, owner_rules, ask, report):
    path = Path(wiki) / 'raw' / 'sources' / target
    page = path.read_text(encoding='utf-8')
    prompt = cleanup_prompt(target, page, rules_text, owner_rules)
    problems = []
    for attempt in (1, 2):
        reply = ask(prompt, f'{Path(target).stem}.{attempt}')
        try:
            metadata, source = parse_reply(reply)
        except CleanupError as exc:
            problems = [str(exc)]
        else:
            if metadata['kind'] == 'none':
                report['unchanged'].append({'target': target, 'why': str(metadata.get('why', ''))[:500]})
                return 'unchanged'
            candidate, problems = proposal(wiki, candidates, target, page, metadata, source)
            if not problems:
                try:
                    base = draft_adapter.check_draft(wiki, candidates, candidate, source)
                except draft_adapter.DraftRefused as exc:
                    problems = [str(exc)]
            if not problems:
                draft_adapter.store_draft(candidates / Path(target).stem, candidate, source, base)
                report['candidates'].append({'target': target, 'kind': candidate['kind'],
                                             'summary': candidate['summary']})
                return candidate['kind']
        if attempt == 1:
            prompt = hm.repair_prompt(prompt, reply, problems)
    report['refused'].append({'target': target, 'problems': problems})
    return 'refused'


def load_state(path):
    if path is None or not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_state(path, state):
    if path is None:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(path).with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding='utf-8')
    temporary.replace(path)


def run(*, wiki, inbox, runs, state_path, caller, rules_text, owner_rules, run_id, cap_usd, deadline, only,
        again, clock=time.time):
    """Clean the sources (all, or `only`); returns the run's report (also written to report.json).
    `state_path` None is a shadow run: no state is read or written."""
    wiki, inbox, out_dir = Path(wiki), Path(inbox), Path(runs) / run_id
    candidates = inbox / run_id / 'candidates'
    sources = sorted(p.name for p in (wiki / 'raw' / 'sources').glob('*.md'))
    if only:
        unknown = sorted(set(only) - set(sources))
        if unknown:
            raise CleanupError('no such source: ' + ', '.join(unknown))
        sources = [name for name in sources if name in set(only)]
    state = load_state(state_path)
    busy = busy_targets(inbox)
    report = {'run': run_id, 'candidates': [], 'refused': [], 'unchanged': [], 'waiting_on_review': [],
              'already_read': [], 'not_reached': [], 'cost_usd': 0.0, 'tokens_in': 0, 'tokens_out': 0,
              'sessions': [], 'stopped': None}
    dearest, slowest = [0.0], [0.0]

    def ask(prompt, name):
        if hx.over_cap(report['cost_usd'], dearest[0], cap_usd):
            raise hm.CapReached(f'cost cap ${cap_usd:.2f} reached; the rest waits for the next run')
        if hx.out_of_time(clock(), slowest[0], deadline):
            raise hm.CapReached('time limit reached; the rest waits for the next run')
        started = clock()
        reply, usage = caller(prompt)
        slowest[0] = max(slowest[0], clock() - started)
        (out_dir / 'replies').mkdir(parents=True, exist_ok=True)
        (out_dir / 'replies' / f'{name}.txt').write_text(reply or '', encoding='utf-8')
        cost = usage.get('cost_usd') or 0.0
        report['cost_usd'] += cost
        dearest[0] = max(dearest[0], cost)
        report['tokens_in'] += hx.tokens_in(usage)
        report['tokens_out'] += (usage.get('usage') or {}).get('output_tokens') or 0
        report['sessions'].append(usage.get('session_id'))
        return reply or ''

    pending = []
    for name in sources:
        sha = hashlib.sha256((wiki / 'raw' / 'sources' / name).read_bytes()).hexdigest()
        if name in busy:
            report['waiting_on_review'].append(name)
        elif not again and state.get(name, {}).get('base_sha256') == sha:
            report['already_read'].append(name)
        else:
            pending.append((name, sha))
    done = 0
    try:
        for name, sha in pending:
            outcome = clean_one(name, wiki, candidates, rules_text, owner_rules, ask, report)
            done += 1
            if state_path is not None:
                state[name] = {'base_sha256': sha, 'outcome': outcome, 'run': run_id}
                save_state(state_path, state)
    except hx.CallError as exc:
        report['stopped'] = f'call failed: {exc}'
    except hm.CapReached as exc:
        report['stopped'] = str(exc)
    report['not_reached'] = [name for name, _ in pending[done:]]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return report


def main(argv):
    import wikiconfig
    from harvest_pipeline import owner_rules
    from workflow_paths import PathRefused, checked_path
    parser = argparse.ArgumentParser(description='Propose removal-only cleanups of existing wiki sources.')
    parser.add_argument('--only', nargs='+', metavar='SOURCE')
    parser.add_argument('--again', action='store_true')
    parser.add_argument('--shadow', metavar='FOLDER')
    args = parser.parse_args(argv)
    out = {'ok': True}
    try:
        cfg = wikiconfig.load()
        settings = {**DEFAULTS, **(cfg.get('source_cleanup') or {})}
        audit, wiki = wikiconfig.audit_dir(cfg), wikiconfig.project_root(cfg)
        hermes = shutil.which('hermes')
        if not hermes:
            raise ValueError('hermes is not on PATH')
        caller = hx.hermes_caller(hermes, settings['model'], settings['provider'], wikiconfig.hermes_home(cfg),
                                  timeout=int(settings['call_timeout_seconds']))
        now = time.time()
        run_id = 'cleanup-' + datetime.fromtimestamp(now).strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(4)
        if args.shadow:
            shadow = Path(args.shadow).resolve()
            inbox, runs, state_path = shadow / 'inbox', shadow, None
        else:
            inbox = checked_path(audit, 'inbox')
            runs = checked_path(audit, 'source-cleanup')
            state_path = checked_path(audit, 'source-cleanup/state.json')
        rules_text = (Path(__file__).resolve().parent / 'harvest_prompt.md').read_text(encoding='utf-8')
        out['report'] = run(wiki=wiki, inbox=inbox, runs=runs, state_path=state_path, caller=caller,
                            rules_text=rules_text, owner_rules=owner_rules(cfg), run_id=run_id,
                            cap_usd=float(settings['cap_usd']), deadline=now + 60 * float(settings['minutes']),
                            only=args.only, again=args.again)
        if (out['report']['stopped'] or '').startswith('call failed'):
            out['ok'] = False
    except (CleanupError, hx.ExtractError, hm.MergeError, PathRefused, wikiconfig.ConfigError, OSError,
            ValueError) as exc:
        out = {'ok': False, 'error': str(exc)}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

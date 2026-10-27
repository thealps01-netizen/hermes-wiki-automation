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

REMOVAL BY NUMBER: the model is shown the source with every line numbered and every sentence of a
line numbered within it ([23] - {1} ... {2} ...). It names what to remove ("23" a line, "23.2" one
sentence, "decision 3" / "finding F2" a whole block), each with a reason; the code builds the draft, so
no kept word can be reworded or added. Only the title line ("title") and the Scope paragraph ("scope")
may be rewritten to describe what remains. Why by sentence: the first real run (2026-10-27, Phosphor)
could only keep or drop whole entries and lost a lesson and an open question that each shared one
entry with a skin name or a note on where the work stood. The title line, "## Decisions", a decision's
or finding's bold heading (only with its whole block) and a heading whose section still has entries
cannot be removed by number. A reason that cites the owner's rule (AGENTS.md) must quote it, and the
quote must be in the rule the model was shown: the same run dropped a lesson as "belongs in AGENTS.md"
although AGENTS.md has no such rule. A draft that removes more than half of the source's text says so
at the start of its `why`. A refused reply gets one repair call, then it is reported as refused. The
drafting checks every other draft passes (`draft_adapter.check_draft`) run too. Sources are read as
UTF-8 with or without a byte order mark and with either line ending.

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
import difflib
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
WHY_LIMIT = 2000
LARGE_SHARE = 0.5   # chosen, not measured: a draft removing more of the text than this says so first
CITES_RULE = re.compile(r"AGENTS\.md|owner'?s rule|already a rule", re.I)


class CleanupError(Exception):
    pass


BLOCK = re.compile(r'^(decision|finding) (F?\d+)$', re.I)
LINE_ID = re.compile(r'^(\d+)(?:\.(\d+))?$')
PREFIX = re.compile(r'^\s*[-*+]\s+(?:(?:\*\*)?[A-Z][\w-]*(?: [\w-]+){0,2}:(?:\*\*)?\s+)?')
SPAN = re.compile(r'`[^`]*`|\*\*.+?\*\*')
SENTENCE_END = re.compile(r'[.!?](?:\*\*|["\')\]”’])*\s+(?=[A-Z0-9"“\'*`\[(])')
ABBREVIATIONS = {'e.g', 'i.e', 'etc', 'vs', 'cf', 'approx', 'no', 'mr', 'ms', 'dr'}


def pieces(line):
    """(prefix, sentences) of one line. The prefix (a bullet with its label such as "- Why: ") stays
    with the line; headings and table rows are one piece; a bold span or code span is never split."""
    if not line.strip() or line.lstrip().startswith(('#', '|')):
        return '', [line]
    match = PREFIX.match(line)
    prefix = match.group(0) if match else ''
    rest = line[len(prefix):]
    masked = list(rest)
    for span in SPAN.finditer(rest):
        keep_last = span.group(0).startswith('**')
        for i in range(span.start() + 2 if keep_last else span.start() + 1,
                       span.end() - (3 if keep_last else 1)):
            masked[i] = ' ' if rest[i].isspace() else 'x'
    masked = ''.join(masked)
    parts, start = [], 0
    for end in SENTENCE_END.finditer(masked):
        word = masked[:end.start()].rsplit(None, 1)[-1] if masked[:end.start()].strip() else ''
        word = rest[end.start() - len(word):end.start()]
        if '.' in word or word.lower() in ABBREVIATIONS or word.isdigit() or re.fullmatch(r'[A-Za-z]', word):
            continue
        parts.append(rest[start:end.end()])
        start = end.end()
    parts.append(rest[start:])
    return prefix, [part for part in parts if part]


CONTINUES = re.compile(r'^\s*(?:[-*+]\s|\d+[.)]\s|#|\||\*\*(?:\d+|F\d+)\.|```|~~~)')


def unwrap(page):
    """The page with every hard-wrapped paragraph, bullet or bold heading on one line, so a numbered
    line is a whole entry and a sentence never spans two numbers. Tables, headings, list markers and
    fenced code keep their own lines."""
    out, fence = [], False
    for line in page.split('\n'):
        if line.lstrip().startswith(('```', '~~~')):
            fence = not fence
            out.append(line)
            continue
        joins = (not fence and line.strip() and out and out[-1].strip() and not CONTINUES.match(line)
                 and not out[-1].lstrip().startswith(('#', '|', '```', '~~~')))
        if joins:
            out[-1] = out[-1].rstrip() + ' ' + line.strip()
        else:
            out.append(line)
    return '\n'.join(out)


def layout(page):
    """Line indexes of the title, the Scope paragraph and every decision or finding block."""
    lines = page.split('\n')
    title = 0 if lines and lines[0].startswith('# ') else None
    scope, blocks, in_scope = [], {}, False
    for i, line in enumerate(lines):
        if line.startswith('#'):
            in_scope = line.strip() == '## Scope'
            continue
        if in_scope and line.strip():
            scope.append(i)
    for pattern, kind in ((hm.DECISION_NUMBER, 'decision'), (hm.FINDING, 'finding')):
        for i, line in enumerate(lines):
            match = pattern.match(line)
            if not match:
                continue
            unit = f'{kind} ' + ('F' if kind == 'finding' else '') + (match.group(1) or match.group(2))
            end = i + 1
            while (end < len(lines) and lines[end].strip() and not lines[end].startswith('#')
                   and not hm.DECISION_NUMBER.match(lines[end]) and not hm.FINDING.match(lines[end])):
                end += 1
            blocks[unit.lower()] = (unit, list(range(i, end)))
    return lines, title, scope, blocks


TAIL = re.compile(r'[.!?:](?:\*\*|["\')\]”’])*\s*$|\s+$')


def mask(text):
    """The text with the inside of code spans and bold spans hidden (a bold span keeps its last
    character, so a bold heading that ends a sentence still ends it)."""
    masked = list(text)
    for span in SPAN.finditer(text):
        bold = span.group(0).startswith('**')
        for i in range(span.start() + (2 if bold else 1), span.end() - (3 if bold else 1)):
            masked[i] = ' ' if text[i].isspace() else 'x'
    return ''.join(masked)


def clauses(line):
    """(prefix, sentences): each sentence is (clauses, tail). A clause after the first starts with its
    "; ", and the tail is the sentence's end mark, so removing a later clause leaves "X. " and removing
    every clause of a sentence removes the whole sentence; both are pure deletions."""
    prefix, parts = pieces(line)
    out = []
    for sentence in parts:
        tail = TAIL.search(sentence) if not sentence.lstrip().startswith(('#', '|')) else None
        body, end = (sentence[:tail.start()], sentence[tail.start():]) if tail else (sentence, '')
        cuts = [m.start() for m in re.finditer(r';\s', mask(body))]
        bounds = [0] + cuts + [len(body)]
        out.append(([body[a:b] for a, b in zip(bounds, bounds[1:]) if body[a:b]], end))
    return prefix, out


def units(line):
    """The removable parts of a line in reading order: (sentence index, clause index, text)."""
    _, sentences = clauses(line)
    return [(s, c, text) for s, (parts, _) in enumerate(sentences) for c, text in enumerate(parts)]


def numbered(page):
    """The source as the model sees it: [line] and, for a line of several parts, {part}."""
    out = []
    for n, line in enumerate(page.split('\n'), 1):
        if not line.strip():
            out.append('')
            continue
        prefix, sentences = clauses(line)
        if len(units(line)) == 1:
            out.append(f'[{n}] {line}')
            continue
        text, k = f'[{n}] {prefix}', 0
        for parts, tail in sentences:
            for part in parts:
                k += 1
                if part.startswith(';'):
                    gap = part[:len(part) - len(part[1:].lstrip()) ]
                    text += f'{gap}{{{k}}} {part[len(gap):]}'
                else:
                    text += f'{{{k}}} {part}'
            text += tail
        out.append(text.rstrip())
    return '\n'.join(out).rstrip('\n') + '\n'


def heading_unit(blocks, index):
    return next((unit for unit, rows in blocks.values() if rows[0] == index), None)


def without_parts(line, numbers):
    """(the line without the numbered parts or None when nothing is left, problem). The first clause of
    a sentence goes only with the whole sentence, so a kept clause never starts with "; "."""
    prefix, sentences = clauses(line)
    text, k, problem = '', 0, None
    for parts, tail in sentences:
        kept = []
        for c, part in enumerate(parts):
            k += 1
            if k not in numbers:
                kept.append(part)
            elif c == 0 and any(k + j + 1 not in numbers for j in range(len(parts) - 1)):
                problem = f'part {k} opens a sentence whose later part is kept; remove the later part or all of it'
                kept.append(part)
        if kept:
            text += ''.join(kept) + tail
    if not text.strip():
        return None, problem
    return (prefix + text).rstrip(), problem


def apply_removals(page, remove, log=None):
    """(text, problems): the page without the named lines, sentences and blocks. `log` collects
    (id, reason, removed text) for the candidate's `why`."""
    lines, title, scope, blocks = layout(page)
    drop, drop_pieces, headings, problems = set(), collections.defaultdict(set), [], []
    if not isinstance(remove, list):
        return page, ['"remove" must be a list']
    for item in remove:
        if not isinstance(item, dict):
            problems.append('every "remove" entry is an object with "id" and "reason"')
            continue
        name = str(item.get('id', '')).strip()
        reason = item.get('reason')
        if not (isinstance(reason, str) and reason.strip()):
            problems.append(f'{name or "?"}: every removal needs a reason')
            continue
        block = BLOCK.match(name)
        line_id = LINE_ID.match(name)
        if block:
            found = blocks.get(name.lower())
            if not found:
                problems.append(f'{name} does not exist in the source')
                continue
            drop.update(found[1])
            removed = lines[found[1][0]].strip()
        elif line_id:
            index, piece = int(line_id.group(1)) - 1, line_id.group(2)
            if not (0 <= index < len(lines)) or not lines[index].strip():
                problems.append(f'{name} is not a numbered line of the source')
                continue
            if index == title:
                problems.append(f'{name} is the title line; change it through "title"')
                continue
            if lines[index].strip() == '## Decisions':
                problems.append(f'{name} is the ## Decisions heading, which always stays')
                continue
            if index in scope:
                problems.append(f'{name} is in the Scope paragraph; rewrite it through "scope"')
                continue
            unit = heading_unit(blocks, index)
            parts = units(lines[index])
            if unit and (piece is None or int(piece) == 1):
                problems.append(f'{name} is the heading of {unit}; remove the whole {unit} or keep it')
                continue
            if piece is None:
                drop.add(index)
                removed = lines[index].strip()
                if lines[index].startswith('## '):
                    headings.append((name, index))
            elif not 1 <= int(piece) <= len(parts):
                problems.append(f'{name} does not exist in the source (line {index + 1} has {len(parts)} '
                                'part(s))')
                continue
            else:
                drop_pieces[index].add(int(piece))
                removed = parts[int(piece) - 1][2].lstrip('; ').strip()
        else:
            problems.append(f'{name or "?"} is not a line ("23"), a sentence ("23.2"), "decision N" or "finding FN"')
            continue
        if log is not None:
            log.append((name, hx.norm(reason), removed, item.get('quote')))
    for name, index in headings:
        end = next((i for i in range(index + 1, len(lines)) if lines[i].startswith('#')), len(lines))
        if any(lines[i].strip() and i not in drop for i in range(index + 1, end)):
            problems.append(f'{name} is a section heading whose section still has entries')
    kept = []
    for i, line in enumerate(lines):
        if i in drop:
            continue
        if i in drop_pieces:
            line, problem = without_parts(line, drop_pieces[i])
            if problem:
                problems.append(f'line {i + 1}: {problem}')
            if line is None:
                continue
        kept.append(line)
    return tidy(kept), problems


def tidy(lines):
    """Drop a ## section left empty (never ## Decisions) and repeated blank lines."""
    out = []
    for i, line in enumerate(lines):
        if line.startswith('## ') and line.strip() != '## Decisions':
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith('#')), len(lines))
            if not any(lines[j].strip() for j in range(i + 1, end)):
                continue
        if not line.strip() and (not out or not out[-1].strip()):
            continue
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return '\n'.join(out) + '\n'


def body_text(text):
    """The text outside the two places a cleanup may rewrite: the title line and the Scope paragraph."""
    lines, title, scope, _ = layout(text)
    return '\n'.join(line for i, line in enumerate(lines) if i != title and i not in scope)


WORD = re.compile(r'\w+|[^\w\s]')


def only_deletions(base, draft):
    """Problems when the draft's body is not the base's body with parts deleted: every word of the
    draft and every punctuation mark, in order, must be one of the base's (line wraps and spacing are
    not text, and a removed clause may leave the sentence's own end mark after an earlier word)."""
    words = iter(WORD.findall(body_text(unwrap(base))))
    for word in WORD.findall(body_text(draft)):
        if not any(word == other for other in words):
            return [f'the draft has text that is not in the current source, from: {word[:80]}']
    return []


def removed_share(base, draft):
    before, after = len(' '.join(body_text(unwrap(base)).split())), len(' '.join(body_text(draft).split()))
    return 1 - after / before if before else 0.0


def build_draft(page, metadata):
    """(draft, log, problems) for an update reply."""
    log = []
    remove = metadata.get('remove')
    if not remove:
        return None, log, ['nothing was removed; reply with kind "none" instead']
    page = unwrap(page)
    draft, problems = apply_removals(page, remove, log)
    lines, title, scope, _ = layout(draft)
    new_title, new_scope = metadata.get('title'), metadata.get('scope')
    if new_title is not None:
        if not (isinstance(new_title, str) and 1 <= len(new_title.strip()) <= 200 and '\n' not in new_title):
            problems.append('"title" must be one line of 1 to 200 characters')
        elif title is not None:
            lines[title] = '# ' + new_title.strip()
    if new_scope is not None:
        if not (isinstance(new_scope, str) and 1 <= len(new_scope.strip()) <= 1000 and '\n' not in new_scope.strip()):
            problems.append('"scope" must be one paragraph of 1 to 1000 characters')
        elif scope:
            lines[scope[0]:scope[-1] + 1] = [new_scope.strip()]
    draft = '\n'.join(lines)
    problems += only_deletions(page, draft)
    return draft, log, problems


def cleanup_prompt(target, page, rules_text, owner_rules):
    return (f'{CLEANUP_MARK}\nYou clean one existing source of the owner\'s wiki. It was written before the rules '
            'below were sharpened, so it may hold text that does not count. You only name what to remove; the '
            'code removes it, so you never reword, merge, renumber or add.\n\n'
            f'=== WHAT COUNTS (the drafting job\'s rule) ===\n{hm.section(rules_text, "## What counts")}'
            f'=== END ===\n\n=== THE OWNER\'S RULE ===\n{owner_rules}=== END ===\n\n'
            f'The current source {target}, every line numbered as [N] and, where a line has several sentences, '
            'every sentence numbered as {k}:\n'
            f'=== CURRENT SOURCE ===\n{numbered(unwrap(page))}=== END CURRENT SOURCE ===\n\n'
            'Contract:\n'
            '- Name each removal by number: "N" removes line N, "N.k" removes sentence k of line N, '
            '"decision N" or "finding FN" removes that whole block. Remove the smallest part that does not '
            'count: when one sentence of a line does not count and the rest does, remove that sentence only.\n'
            '- Remove text only when it does not count under the rules above: which personal customisation is in '
            'use and the looks rejected on the way, where a piece of work stood (waiting for approval, not yet '
            'merged, installed or run), the current value of a setting the owner can change himself (which skin, '
            'theme, model or option is on), facts about one day or one machine\'s state, how work was done, attempts '
            'that were reverted. Do not remove a decision because it is old, small or owner-directed. A lesson '
            'learned while building something (a cause, a constraint, a rule for next time) counts even when '
            'the sentence beside it does not.\n'
            '- When you are unsure whether something counts, keep it.\n'
            '- Remove text as already a rule only when THE OWNER\'S RULE above already says it, and copy that '
            'sentence into "quote". Something that ought to become a rule is not removed for that reason.\n'
            '- A decision\'s or finding\'s bold heading goes only with its whole block. Remove a Changed decisions '
            'entry when it is about a removed decision or only records which value a setting or customisation has '
            'now, an Evidence row only when no kept text cites it, and '
            'a section heading only when its whole section goes; ## Decisions always stays.\n'
            '- You may give a new "title" and "scope" (one paragraph) so they describe what remains; leave them '
            'out to keep the current ones.\n'
            '- When no decision or finding is left, the whole source is retired.\n\n'
            'Reply in exactly this format, nothing before or after:\n'
            '=== METADATA ===\n{"kind": "update|retire|none", "summary": "...", "why": "...", "title": "...", '
            '"scope": "...", "remove": [{"id": "23.2", "reason": "...", "quote": "..."}]}\n=== END ===\n'
            'kind "update": "remove" names every removal, each with a one-sentence reason; "quote" only when the '
            'reason is the owner\'s rule; "why" is not needed. kind "retire": summary and why say why nothing '
            'durable is left. kind "none": only "why", when everything counts.\n'
            'summary and why are plain text of one to three sentences, at most 2000 characters.\n')


def parse_reply(reply):
    """The METADATA object. A source text in the reply is ignored: the code builds the draft."""
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
    return metadata


def unquoted_rules(log, owner_rules):
    """Removals whose reason cites the owner's rule without a quote found in that rule."""
    rules = hx.norm(owner_rules)
    problems = []
    for name, reason, _, quote in log:
        if not CITES_RULE.search(reason):
            continue
        if not (isinstance(quote, str) and hx.norm(quote)):
            problems.append(f'{name} is removed as the owner\'s rule but has no "quote" from that rule')
        elif hx.norm(quote) not in rules:
            problems.append(f'{name}: the quote is not in the owner\'s rule shown above, so the text is not '
                            'already a rule; keep it or give a reason the rules above support')
    return problems


def why_text(log, share):
    """The candidate's `why`: a warning for a large removal, then every removal with its reason and text."""
    named = [f'{name}: {reason} (removed: "{text[:160]}")' for name, reason, text, _ in log]
    text = 'Removed (does not count): ' + '; '.join(named)
    if share > LARGE_SHARE:
        text = (f'Large removal: about {round(share * 100)}% of the source text goes; check that nothing '
                'durable goes with it. ' + text)
    return text if len(text) <= WHY_LIMIT else text[:WHY_LIMIT - 3] + '...'


def proposal(wiki, candidates, target, page, metadata, owner_rules=''):
    """(candidate metadata, draft, problems) for one parsed reply."""
    path = Path(wiki) / 'raw' / 'sources' / target
    base_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    summary = metadata.get('summary')
    if not (isinstance(summary, str) and 1 <= len(summary) <= WHY_LIMIT):
        return None, None, ['summary must be plain text of 1 to 2000 characters']
    if metadata['kind'] == 'retire':
        why = metadata.get('why')
        if not (isinstance(why, str) and 1 <= len(why) <= WHY_LIMIT):
            return None, None, ['why must be plain text of 1 to 2000 characters']
        candidate = {'kind': 'retire', 'target': target, 'summary': summary, 'why': why, 'evidence_ids': [],
                     'base_sha256': base_sha}
        return candidate, None, []
    draft, log, problems = build_draft(page, metadata)
    problems += unquoted_rules(log, owner_rules)
    if problems:
        return None, None, problems
    lines, table = evidence_store._evidence_texts(draft)
    candidate = {'kind': 'update', 'target': target, 'summary': summary,
                 'why': why_text(log, removed_share(page, draft)),
                 'evidence_ids': sorted(evidence_store.cited_ids(lines + table)), 'base_sha256': base_sha}
    return candidate, draft, []


def clean_one(target, wiki, candidates, rules_text, owner_rules, ask, report):
    path = Path(wiki) / 'raw' / 'sources' / target
    page = path.read_text(encoding='utf-8-sig')   # newline=None also reads CRLF as LF
    prompt = cleanup_prompt(target, page, rules_text, owner_rules)
    problems = []
    for attempt in (1, 2):
        reply = ask(prompt, f'{Path(target).stem}.{attempt}')
        try:
            metadata = parse_reply(reply)
        except CleanupError as exc:
            problems = [str(exc)]
        else:
            if metadata['kind'] == 'none':
                report['unchanged'].append({'target': target, 'why': str(metadata.get('why', ''))[:500]})
                return 'unchanged'
            candidate, source, problems = proposal(wiki, candidates, target, page, metadata, owner_rules)
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

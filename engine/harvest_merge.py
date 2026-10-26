"""Merger: turn the extracted items of finished ledger rows into one source draft per wiki page.

WHY: the extractor reads one conversation at a time and never sees the wiki, so several
conversations can add to the same subject. Once per night the merger
1. routes every decision/finding item to the source it belongs to, from a small index of source
   file names, titles and scope lines (never the whole 80 KB decision index);
2. drafts each target with one model call that reads that target's current page in full;
3. checks the draft with the same code the drafting job's submissions pass (`draft_adapter.check_draft`)
   plus two merger checks: nothing of the page may be lost (a heading, a numbered decision or finding,
   an evidence row) and requested evidence passages must be copied from the items' verbatim quotes;
4. gives a refused draft one repair call with the reasons, then stores it or reports it as refused.

The drafting rules are not copied here: the sections "What counts", "Decide the kind", "Submit each
candidate" and "Evidence" are cut from `harvest_prompt.md`, the drafting job's own prompt, at run time.
Process items become skill candidates in the report and article signals are reported; neither is
routed to a page (design section 4.3 and 4.5). Retirement is never drafted here.

The merger writes only into `out_dir` (candidates in the inbox layout, plus report.json). Where
`out_dir` is the shadow folder, the owner's Review list is untouched.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import draft_adapter
import evidence_store
import harvest_extract as hx
from wiki_candidates import NAME_RE

ROUTE_MARK = '=== ROUTE ITEMS ==='
DRAFT_MARK = '=== DRAFT ONE SOURCE ==='
RULE_SECTIONS = ('## What counts', '## Decide the kind for each decision', '## Submit each candidate', '## Evidence')
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
# Both numbering styles occur in the wiki: "**1. Title.**" (most pages) and "1. **Title.**".
DECISION_NUMBER = re.compile(r'^(?:\*\*(\d+)\.|(\d+)\.\s+\*\*)', re.M)
FINDING = re.compile(r'^(?:\*\*F(\d+)\.|F(\d+)\.\s+\*\*)', re.M)
SIMILAR = 0.6   # a bullet at least this similar to one in the draft was reworded, not removed


class MergeError(Exception):
    pass


def section(text, heading):
    match = re.search(rf'^{re.escape(heading)}\s*$', text, re.M)
    if not match:
        raise MergeError(f'The drafting prompt has no "{heading}" section')
    rest = text[match.start():]
    following = re.search(r'^## ', rest[3:], re.M)
    return rest[:following.start() + 3 if following else len(rest)].strip() + '\n'


def house_rules(prompt_text):
    """The drafting job's own rules for what counts, the kind, the source format and evidence."""
    return '\n'.join(section(prompt_text, heading) for heading in RULE_SECTIONS)


def routing_index(wiki):
    """One line per current source: file name, title and the first scope paragraph (300 characters)."""
    lines = []
    for path in sorted((Path(wiki) / 'raw' / 'sources').glob('*.md')):
        text = path.read_text(encoding='utf-8', errors='replace')
        title = next((line[2:].strip() for line in text.splitlines() if line.startswith('# ')), path.stem)
        scope = re.search(r'^## Scope\s*\n+(.+?)(?:\n\s*\n|\n## |\Z)', text, re.M | re.S)
        lines.append(f'- {path.name}: {title}' + (f' | {hx.norm(scope.group(1))[:300]}' if scope else ''))
    return '\n'.join(lines) + '\n'


def item_line(item_id, item, with_quote=False):
    line = f"{item_id} [{item['type']}] {hx.norm(item['claim'])} (from: {item['label']}, {item['date']})"
    if with_quote:
        line += f"\n   quote: \"{hx.norm(item['quote'])}\"\n   later use: {hx.norm(item.get('later_use', ''))}"
    return line


def route_prompt(items, index, rules):
    listing = '\n'.join(item_line(item_id, item) for item_id, item in items.items())
    return (f'{ROUTE_MARK}\nYou assign knowledge items, extracted from the owner\'s conversations, to the wiki source '
            'each belongs to. You do not write pages. Match by subject using these rules:\n\n'
            f'{section(rules, "## Decide the kind for each decision")}\n'
            f'=== CURRENT SOURCES (file: title | scope) ===\n{index}=== END SOURCES ===\n\n'
            f'=== ITEMS ===\n{listing}\n=== END ITEMS ===\n\n'
            'Route every item exactly once. Use an existing file name from the list when the subject matches; '
            'otherwise propose a new subject as a short lowercase slug (words joined by hyphens); several items of '
            'one new subject share one slug. Drop an item only when it does not count under the rules (say why).\n'
            'Return JSON only, no prose and no code fence:\n'
            '{"routes": [{"item": "I1", "target": "<existing file name>"}, {"item": "I2", "new": "<slug>"}, '
            '{"item": "I3", "drop": "<reason>"}]}\n')


def json_object(reply, key):
    decoder, found = json.JSONDecoder(), None
    for match in re.finditer(r'\{\s*"' + re.escape(key) + '"', reply or ''):
        try:
            value = decoder.raw_decode(reply, match.start())[0]
        except ValueError:
            continue
        if isinstance(value, dict):
            found = value
    if found is None:
        raise MergeError(f'The reply holds no complete {{"{key}": ...}} object')
    return found


def parse_routes(reply, items, wiki, today):
    """(routes {target: [item ids]}, dropped {item: reason}, problems). Bad routes are problems, never routes."""
    routes, dropped, problems, seen = {}, {}, [], set()
    existing = {path.name for path in (Path(wiki) / 'raw' / 'sources').glob('*.md')}
    entries = json_object(reply, 'routes').get('routes')
    for entry in entries if isinstance(entries, list) else []:
        item = entry.get('item') if isinstance(entry, dict) else None
        if item not in items or item in seen:
            problems.append(f'route for an unknown or repeated item: {entry!r}'[:300])
            continue
        seen.add(item)
        if isinstance(entry.get('drop'), str) and entry['drop'].strip():
            dropped[item] = entry['drop'].strip()
        elif isinstance(entry.get('target'), str) and entry['target'] in existing:
            routes.setdefault(entry['target'], []).append(item)
        elif isinstance(entry.get('new'), str) and SLUG.fullmatch(entry['new']) and len(entry['new']) <= 60:
            name = f"{today}-{entry['new']}.md"
            if NAME_RE.fullmatch(name) and name not in existing:
                routes.setdefault(name, []).append(item)
            else:
                problems.append(f'{item}: new source name {name} is invalid or taken')
        else:
            problems.append(f'{item}: no valid target, new slug or drop reason: {entry!r}'[:300])
    problems += [f'{item}: not routed' for item in items if item not in seen]
    order = list(items)
    return {target: sorted(ids, key=order.index) for target, ids in routes.items()}, dropped, problems


def draft_prompt(target, page, items, rules, today):
    if page is None:
        where = f'There is no page yet. Write the new source {target}.\n'
    else:
        where = (f'The current page {target}, in full:\n=== CURRENT PAGE ===\n{page}=== END CURRENT PAGE ===\n'
                 'Write the complete updated page.\n')
    listing = '\n'.join(item_line(item_id, item, with_quote=True) for item_id, item in items.items())
    return (f'{DRAFT_MARK}\nYou write one wiki source draft for the owner\'s review from knowledge items that were '
            'extracted from his conversations. The rules below come from the nightly drafting job. Tool names in them '
            '(wiki_draft_read, wiki_draft_submit) do not apply to you: you reply with text and code checks and stores '
            'it. You may only draft `new` or `update`; never retire.\n\n'
            f'=== RULES ===\n{rules}=== END RULES ===\n\n{where}\n'
            f'=== ITEMS FOR THIS PAGE ===\n{listing}\n=== END ITEMS ===\n\n'
            f'Today is {today}. Use each item\'s own date in an owner-directed evidence label. An evidence request '
            'passage must be copied from an item quote above, character for character.\n'
            'Reply in exactly this format, nothing before or after:\n'
            '=== METADATA ===\n{"kind": "new|update|none", "summary": "...", "why": "...", "evidence_requests": []}\n'
            '=== SOURCE ===\n<the complete source>\n=== END ===\n'
            'Write each decision as a bold numbered line, **1. Title.**, then Why:, Rejected: and Evidence: lines, '
            'and each finding as **F1.** followed by its text; an update keeps the numbering style the page uses. '
            'Never drop an entry under Changed decisions. An Open item you remove because it is resolved must be '
            'named in why.\n'
            'summary and why are plain text of one to three sentences each, at most 2000 characters. '
            'evidence_ids is filled in by code from the citations in your source; do not write it.\n'
            'Use kind "none" with only "why", and no SOURCE block, when the page already holds every item.\n')


def parse_draft(reply):
    """(metadata, source); source is None for kind "none"."""
    text = reply or ''
    head = text.find('=== METADATA ===')
    if head < 0:
        raise MergeError('The reply has no === METADATA === block')
    try:
        metadata = json.JSONDecoder().raw_decode(text, text.index('{', head))[0]
    except ValueError as exc:
        raise MergeError('The METADATA block is not one JSON object') from exc
    if not isinstance(metadata, dict) or metadata.get('kind') not in ('new', 'update', 'none'):
        raise MergeError('METADATA kind must be new, update or none')
    if metadata['kind'] == 'none':
        return metadata, None
    start, end = text.find('=== SOURCE ===\n'), text.rfind('=== END ===')
    if start < 0 or end < start:
        raise MergeError('The reply has no complete === SOURCE === ... === END === block')
    return metadata, text[start + len('=== SOURCE ===\n'):end]


def evidence_rows(text):
    try:
        body = section(text, '## Evidence')
    except MergeError:
        return []
    rows = [line.strip() for line in body.splitlines() if line.strip().startswith('|')]
    return [row for row in rows[2:] if not re.fullmatch(r'\|[\s:|-]*', row)]


def row_id(row):
    """The first cell of an Evidence table row, the row's identity; its other cells may be updated."""
    return row.split('|')[1].strip().strip('`')


def numbers(pattern, text):
    return {next(group for group in match if group) for match in pattern.findall(text)}


def bullets(text, heading):
    """The `- ` entries of one section, each joined with its indented continuation lines."""
    try:
        body = section(text, heading)
    except MergeError:
        return []
    entries = []
    for line in body.splitlines()[1:]:
        if line.startswith('- '):
            entries.append(line[2:].strip())
        elif entries and line.startswith(' ') and line.strip():
            entries[-1] += ' ' + line.strip()
    return [hx.norm(entry) for entry in entries if hx.norm(entry).lower() not in ('none', 'none.')]


def removed_bullets(base, draft, heading):
    kept = bullets(draft, heading)
    return [entry for entry in bullets(base, heading)
            if not any(difflib.SequenceMatcher(None, entry, other).ratio() >= SIMILAR for other in kept)]


def removed_open(base, draft):
    """Open items the draft no longer lists. Resolving an item is allowed, so this is shown to the
    reviewer next to the candidate rather than refused."""
    return removed_bullets(base, draft, '## Open')


def lost_units(base, draft):
    """What of the current page the draft drops: a heading, a numbered decision or finding, an evidence row.
    A decision or finding rewritten under its own number is a change, not a loss."""
    lost, lines = [], {line.strip() for line in draft.splitlines()}
    lost += [f'heading {line.strip()}' for line in base.splitlines() if line.startswith('#') and line.strip() not in lines]
    for pattern, name in ((DECISION_NUMBER, 'decision '), (FINDING, 'finding F')):
        missing = sorted(numbers(pattern, base) - numbers(pattern, draft), key=int)
        lost += [f'{name}{number}' for number in missing]
    lost += [f'changed-decision entry "{entry[:120]}"' for entry in removed_bullets(base, draft, '## Changed decisions')]
    kept = {row_id(row) for row in evidence_rows(draft)}
    lost += [f'evidence row {row}' for row in evidence_rows(base) if row_id(row) not in kept]
    return lost


def unquoted_passages(metadata, items):
    quotes = [hx.quote_norm(item['quote']) for item in items]
    passages = [p for request in metadata.get('evidence_requests') or [] if isinstance(request, dict)
                for p in request.get('passages') or []]
    return [p for p in passages if not any(hx.quote_norm(p) in quote for quote in quotes)]


def unknown_ids(wiki, metadata, source):
    """A reason naming the words of Evidence: lines that are read as evidence ids but are neither retained
    evidence nor requested. Pages often explain evidence in prose ("the head-to-head is a measurement");
    every hyphenated word there counts as a citation, so the model must move the prose, not keep it."""
    if not isinstance(source, str):
        return []
    lines, table = evidence_store._evidence_texts(source)
    requested = {r.get('id') for r in metadata.get('evidence_requests') or [] if isinstance(r, dict)}
    unknown = sorted(i for i in evidence_store.cited_ids(lines + table)
                     if i not in requested and not (Path(wiki) / 'raw' / 'evidence' / i).is_dir())
    if not unknown:
        return []
    return [f'these words in Evidence lines are read as evidence ids, but no such evidence exists: {", ".join(unknown)}. '
            'An Evidence: line holds only evidence ids and none (...) placeholders: move the explanation inside '
            'the none (...) parentheses or into Why:, keeping the real evidence ids as they are']


def check(wiki, candidates, metadata, source, page, items):
    """(base bytes, refusal reasons): the drafting job's own checks, then the merger's."""
    try:
        base = draft_adapter.check_draft(wiki, candidates, metadata, source)
    except draft_adapter.DraftRefused as exc:
        return None, [str(exc)] + unknown_ids(wiki, metadata, source)
    problems = []
    if page is not None:
        problems += [f'the draft drops {unit} of the current page; keep it word for word or change it in place'
                     for unit in lost_units(page, source)]
    problems += [f'evidence passage is not copied from an item quote: {p[:200]}' for p in unquoted_passages(metadata, items)]
    return base, problems


def repair_prompt(prompt, reply, problems):
    reasons = '\n'.join(f'- {p}' for p in problems)
    return (f'{prompt}\n=== YOUR PREVIOUS REPLY WAS REFUSED ===\n{reasons}\n\n=== YOUR PREVIOUS REPLY ===\n{reply}\n'
            '=== END PREVIOUS REPLY ===\nFix exactly these problems and reply again in the same format.\n')


def label_of(row):
    first = (row['parts'] or [''])[0].splitlines()[0] if row['parts'] else ''
    return re.sub(r' \(part \d+ of \d+\)$', '', first.lstrip('# ').strip()) or row['conversation']


class CapReached(Exception):
    pass


def merge_night(ledger, wiki, out_dir, caller, rules_text, night, today, cap_usd=None):
    """Merge every finished, unmerged ledger row; returns the night's report (also written to report.json).
    A failed model call, or a next call that could pass `cap_usd` (judged by the dearest call so far),
    stops the night and leaves the rows for the next one."""
    wiki, out_dir = Path(wiki), Path(out_dir)
    rows = ledger.unmerged()
    report = {'night': night, 'rows': [r['id'] for r in rows], 'candidates': [], 'refused': [], 'unchanged': [],
              'dropped': {}, 'problems': [], 'skill_candidates': [], 'article_signals': [], 'cost_usd': 0.0,
              'tokens_in': 0, 'tokens_out': 0, 'sessions': [], 'not_drafted': [], 'stopped': None}
    routes = {}
    items = {}
    for row in rows:
        date = datetime.fromtimestamp(row['through']).strftime('%Y-%m-%d')
        for item in row['items'] or []:
            entry = dict(item, conversation=row['conversation'], agent=row['agent'], label=label_of(row), date=date)
            if item['type'] == 'process':
                report['skill_candidates'].append(item['claim'])
            elif item['type'] == 'article_signal':
                report['article_signals'].append(item['claim'])
            else:
                items[f'I{len(items) + 1}'] = entry

    dearest = [0.0]

    def ask(prompt, name):
        if hx.over_cap(report['cost_usd'], dearest[0], cap_usd):
            raise CapReached(f'cost cap ${cap_usd:.2f} reached')
        reply, usage = caller(prompt)
        (out_dir / 'replies').mkdir(parents=True, exist_ok=True)
        (out_dir / 'replies' / f'{name}.txt').write_text(reply or '', encoding='utf-8')
        report['cost_usd'] += usage.get('cost_usd') or 0.0
        dearest[0] = max(dearest[0], usage.get('cost_usd') or 0.0)
        report['tokens_in'] += hx.tokens_in(usage)
        report['tokens_out'] += (usage.get('usage') or {}).get('output_tokens') or 0
        report['sessions'].append(usage.get('session_id'))
        return reply or ''

    rules = house_rules(rules_text)
    try:
        if items:
            prompt = route_prompt(items, routing_index(wiki), rules)
            reply = ask(prompt, 'route.1')
            try:
                routes, report['dropped'], report['problems'] = parse_routes(reply, items, wiki, today)
            except MergeError:
                reply = ask(hx.format_repair_prompt(prompt), 'route.2')
                routes, report['dropped'], report['problems'] = parse_routes(reply, items, wiki, today)
            for target, ids in routes.items():
                draft_one(target, {i: items[i] for i in ids}, wiki, out_dir, rules, today, ask, report)
    except hx.CallError as exc:
        report['stopped'] = f'call failed: {exc}'
    except CapReached as exc:
        report['stopped'] = str(exc)
    except MergeError as exc:
        report['stopped'] = f'routing reply unusable: {exc}'
    reached = {entry['target'] for key in ('candidates', 'refused', 'unchanged') for entry in report[key]}
    report['not_drafted'] = [{'target': target, 'items': ids} for target, ids in routes.items() if target not in reached]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    if report['stopped'] is None:
        ledger.mark_merged(report['rows'], night)
    return report


def draft_one(target, items, wiki, out_dir, rules, today, ask, report):
    path = wiki / 'raw' / 'sources' / target
    page = path.read_text(encoding='utf-8') if path.is_file() else None
    prompt = draft_prompt(target, page, items, rules, today)
    problems = []
    for attempt in (1, 2):
        reply = ask(prompt, f'{Path(target).stem}.{attempt}')
        try:
            answer, source = parse_draft(reply)
        except MergeError as exc:
            problems = [str(exc)]
        else:
            if answer['kind'] == 'none':
                report['unchanged'].append({'target': target, 'why': str(answer.get('why', ''))[:500]})
                return
            metadata = {key: answer[key] for key in ('summary', 'why', 'evidence_requests') if key in answer}
            lines, table = evidence_store._evidence_texts(source)
            metadata.update(kind='update' if page is not None else 'new', target=target,
                            evidence_ids=sorted(evidence_store.cited_ids(lines + table)))
            if page is not None:
                metadata['base_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            problems = [f'{field} is {len(value)} characters; at most 2000' if isinstance(value, str)
                        else f'{field} must be plain text' for field in ('summary', 'why')
                        for value in [metadata.get(field)] if not (isinstance(value, str) and 1 <= len(value) <= 2000)]
            if not problems:
                base, problems = check(wiki, out_dir / 'candidates', metadata, source, page, list(items.values()))
            if not problems:
                draft_adapter.store_draft(out_dir / 'candidates' / Path(target).stem, metadata, source, base)
                report['candidates'].append({'target': target, 'kind': metadata['kind'], 'items': list(items),
                                             'removed_open': removed_open(page, source) if page else []})
                return
        if attempt == 1:
            prompt = repair_prompt(prompt, reply, problems)
    report['refused'].append({'target': target, 'items': list(items), 'problems': problems})

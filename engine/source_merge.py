"""Three-way merge of a source page by unit, for re-deriving a stale update draft.

A unit is a heading line, a numbered decision block (from its `**N.` line up to the next decision or
heading), a top-level list item with its continuation lines, a table row, a paragraph, or a run of
blank lines. The draft's changes against the page it was written from are replayed onto the page as
it is now. Where both sides changed the same units, the same merge runs again on those units' lines;
only lines both sides changed differently are a conflict, and then nothing is merged.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
import difflib
import re

DECISION = re.compile(r'\*\*(\d+)\.')
_ITEM = re.compile(r'(?:[-*+] |\d+[.)] )')
_ORDER = {'current': 0, 'merged': 1, 'draft': 2}


@dataclass
class MergeResult:
    text: str | None
    conflicts: list = field(default_factory=list)
    renumbered: list = field(default_factory=list)
    already_applied: bool = False


def split_units(text: str) -> list[str]:
    units: list[str] = []
    kind = None
    for line in text.splitlines(keepends=True):
        bare = line.rstrip('\r\n')
        if not bare.strip():
            if kind in ('decision', 'blank'):
                units[-1] += line
            else:
                units.append(line)
                kind = 'blank'
            continue
        if bare.startswith('#'):
            units.append(line)
            kind = 'heading'
        elif DECISION.match(bare):
            units.append(line)
            kind = 'decision'
        elif kind == 'decision':
            units[-1] += line
        elif bare.startswith('|'):
            units.append(line)
            kind = 'row'
        elif _ITEM.match(bare):
            units.append(line)
            kind = 'item'
        elif kind == 'paragraph' or (kind == 'item' and line[:1] in ' \t'):
            units[-1] += line
        else:
            units.append(line)
            kind = 'paragraph'
    return units


def _newline(text: str) -> str | None:
    crlf = text.count('\r\n')
    lf = text.count('\n') - crlf
    if crlf and lf:
        return None
    return '\r\n' if crlf else '\n'


def _edits(base: list[str], side: list[str], name: str) -> list[tuple]:
    matcher = difflib.SequenceMatcher(None, base, side, autojunk=False)
    return [(i1, i2, tuple(side[j1:j2]), name) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != 'equal']


def _clash(a: tuple, b: tuple) -> bool:
    if a[:3] == b[:3] or (a[0] == a[1] and b[0] == b[1]):
        return False
    if a[0] == a[1]:
        return b[0] < a[0] < b[1]
    if b[0] == b[1]:
        return a[0] < b[0] < a[1]
    return max(a[0], b[0]) < min(a[1], b[1])


def _touches(edit: tuple, start: int, end: int) -> bool:
    if edit[0] == edit[1]:
        return start < edit[0] < end
    return max(edit[0], start) < min(edit[1], end)


def _view(base: list[str], start: int, end: int, edits: list[tuple]) -> list[str]:
    out, pos = [], start
    for i1, i2, repl, _ in sorted(edits, key=lambda e: (e[0], e[0] != e[1])):
        out += base[pos:i1] + list(repl)
        pos = max(pos, i2)
    return out + base[pos:end]


def _replay(base: list[str], edits: list[tuple]) -> list[tuple[str, str]]:
    out, pos = [], 0
    for i1, i2, repl, side in sorted(edits, key=lambda e: (e[0], e[0] != e[1], _ORDER[e[3]])):
        out += [(u, 'base') for u in base[pos:i1]]
        out += [(u, side) for u in repl]
        pos = max(pos, i2)
    return out + [(u, 'base') for u in base[pos:]]


def _regions(edits: list[tuple], pairs: list[tuple]) -> list[tuple[int, int]]:
    regions = []
    for a, b in pairs:
        start, end = min(a[0], b[0]), max(a[1], b[1])
        while True:
            members = [e for e in edits if _touches(e, start, end)]
            grown = (min([start] + [e[0] for e in members]), max([end] + [e[1] for e in members]))
            if grown == (start, end):
                break
            start, end = grown
        regions.append((start, end))
    joined = []
    for start, end in sorted(regions):
        if joined and start < joined[-1][1]:
            joined[-1] = (joined[-1][0], max(end, joined[-1][1]))
        else:
            joined.append((start, end))
    return joined


def _merge_tokens(base: list[str], current: list[str], draft: list[str], *, nested: bool):
    ours, theirs = _edits(base, current, 'current'), _edits(base, draft, 'draft')
    theirs = [e for e in theirs if e[:3] not in {o[:3] for o in ours}]
    edits = ours + theirs
    pairs = [(o, t) for o in ours for t in theirs if _clash(o, t)]
    conflicts = []
    for start, end in _regions(edits, pairs):
        inside = [e for e in edits if _touches(e, start, end)]
        cur_view = _view(base, start, end, [e for e in inside if e[3] == 'current'])
        draft_view = _view(base, start, end, [e for e in inside if e[3] == 'draft'])
        merged = None
        if not nested:
            lines = lambda units: ''.join(units).splitlines(keepends=True)
            merged, _ = _merge_tokens(lines(base[start:end]), lines(cur_view), lines(draft_view), nested=True)
        if merged is None:
            conflicts.append({'base': ''.join(base[start:end]), 'current': ''.join(cur_view),
                              'draft': ''.join(draft_view)})
            continue
        replacement = tuple(split_units(''.join(u for u, _ in merged)))
        edits = [e for e in edits if e not in inside] + [(start, end, replacement, 'merged')]
    if conflicts:
        return None, conflicts
    return _replay(base, edits), []


def _number(unit: str) -> int | None:
    found = DECISION.match(unit)
    return int(found.group(1)) if found else None


def merge(base: str, current: str, draft: str) -> MergeResult:
    newline = _newline(current)
    if newline is None:
        return MergeResult(None, [{'reason': 'The current page mixes line endings; it cannot be merged by unit.'}])
    b, c, d = (split_units(t.replace('\r\n', '\n')) for t in (base, current, draft))
    units, conflicts = _merge_tokens(b, c, d, nested=False)
    if units is None:
        return MergeResult(None, conflicts)
    taken = {_number(u) for u, side in units if side != 'draft'} - {None}
    highest = max([n for n in (_number(u) for u, _ in units) if n is not None] or [0])
    renumbered, final = [], []
    for unit, side in units:
        n = _number(unit)
        if side == 'draft' and n is not None and n in taken and unit not in c:
            highest += 1
            renumbered.append((n, highest))
            unit = DECISION.sub(f'**{highest}.', unit, count=1)
        if n is not None:
            taken.add(_number(unit))
        final.append(unit)
    text = ''.join(final)
    if newline == '\r\n':
        text = text.replace('\n', '\r\n')
    return MergeResult(text, [], renumbered, text == current)


def preservation_problems(base: str, current: str, draft: str, result: str) -> list[str]:
    """Every line of the current page the draft did not change must survive, and every added line must
    be one the draft added (decision numbers aside)."""
    def lines(text):
        return Counter(line for line in text.replace('\r\n', '\n').split('\n') if line.strip())
    b, c, d, r = lines(base), lines(current), lines(draft), lines(result)
    problems = []
    allowed_removed = b - d
    for line, count in (c - r).items():
        if allowed_removed[line] < count:
            problems.append(f'removes or changes text the draft did not touch: {line.strip()[:120]}')
    numberless = lambda counter: Counter({DECISION.sub('**#.', k, count=1): n for k, n in counter.items()})
    allowed_added = numberless(d - b)
    for line, count in numberless(r - c).items():
        if allowed_added[line] < count:
            problems.append(f'adds text the draft does not contain: {line.strip()[:120]}')
    return problems

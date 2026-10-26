"""Per-conversation harvest pipeline: collect conversations into the ledger, then read them one by one.

WHY: the nightly harvest today packs many conversations into one drafting run; a long night stops
half way and the whole run is collected again. Here every conversation (or the new tail of one) is
its own ledger row (`harvest_ledger.py`) and is read by the extractor (`harvest_extract.py`) on
its own, so one failure stays one row and the cost of each conversation is recorded.

This module writes only the ledger and, with --merge, the shadow folder. It never touches
harvest-state.json, the inbox, the wiki or the current harvest, so it can run in shadow next to
the current harvest (design section 5, step 2). Drafting is `harvest_merge.py`'s job.

USAGE
  python harvest_pipeline.py --collect --since ISO              queue what is new (no model call)
  python harvest_pipeline.py --process --model M --provider P --cap USD
                                                                read due rows; stops at the cap,
                                                                before the next paid conversation
  python harvest_pipeline.py --merge --model M --provider P --cap USD   draft one candidate per page from the
                                                                finished rows into the shadow folder
                                                                <audit>/harvest-shadow/<night>/ (never the inbox)
  python harvest_pipeline.py --status                           ledger counts and cost
  --ledger PATH   use another ledger file (tests and dry runs); default <audit>/harvest-ledger.sqlite
Prints one JSON line.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harvest_extract as hx  # noqa: E402
import harvest_ledger as hl  # noqa: E402
import harvest_merge as hm  # noqa: E402
from workflow_paths import PathRefused  # noqa: E402

RETRY_AFTER_SECONDS = 6 * 3600   # a failed call is tried again on a later run, never in a tight loop


def collect(ledger, conversations, max_chars, prompt_version):
    """Offer each conversation's unread messages to the ledger. `conversations` yields
    (agent, id, label, messages[(time, role, text)]). Returns how many rows got each ledger answer."""
    from wiki_session_harvest import render
    counts = Counter()
    for agent, cid, label, messages in conversations:
        start = ledger.tail_start(agent, cid)
        tail = sorted((m for m in messages if start is None or m[0] > start), key=lambda m: m[0])
        parts = render(label, tail, max_chars)[0] if tail else []
        if not parts:
            counts['nothing_to_read' if tail or start is None else 'nothing_new'] += 1
            continue
        counts[ledger.offer(agent, cid, start, tail[-1][0], parts, prompt_version)] += 1
    return dict(counts)


def process(ledger, extract, worker, cap_usd=None):
    """Read due rows one at a time with `extract(parts) -> result` (harvest_extract.extract's shape).
    An invalid reply ends that row as `error` and the next row is read; a failed model call leaves the
    row waiting for a later run and stops this one, so a provider outage is not paid for row by row."""
    report = {'done': 0, 'empty': 0, 'error': 0, 'waiting': 0, 'cost_usd': 0.0, 'stopped': None}
    while True:
        if cap_usd is not None and report['cost_usd'] >= cap_usd:
            report['stopped'] = f'cost cap ${cap_usd:.2f} reached'
            return report
        row = ledger.claim(worker)
        if row is None:
            return report
        result = extract(row['parts'])
        spent = dict(cost_usd=result['cost_usd'], tokens_in=result['tokens_in'], tokens_out=result['tokens_out'])
        report['cost_usd'] += result['cost_usd'] or 0.0
        if not result['error']:
            ledger.finish(row['id'], worker, result['items'], result['problems'], **spent)
            report['done' if result['items'] else 'empty'] += 1
        elif result.get('retryable'):
            ledger.fail(row['id'], worker, result['error'], retry_at=ledger.clock() + RETRY_AFTER_SECONDS, **spent)
            report['waiting'] += 1
            report['stopped'] = f"call failed: {result['error']}"
            return report
        else:
            ledger.fail(row['id'], worker, result['error'], **spent)
            report['error'] += 1


def owner_rules(cfg):
    import wikiconfig
    return hx.source_rules((wikiconfig.project_root(cfg) / 'AGENTS.md').read_text(encoding='utf-8'))


def found_conversations(cfg, since, until, report):
    """Every enabled agent's conversations in (since, until]; an agent that cannot be read is reported."""
    import wiki_session_harvest as wsh
    agents = {**wsh.DEFAULTS['agents'], **((cfg.get('harvest') or {}).get('agents') or {})}
    roots = wsh.agent_roots(cfg)
    for agent, on in agents.items():
        if not on:
            report[agent] = 'off'
            continue
        try:
            found = list(wsh.READERS[agent](roots[agent], since, until))
        except FileNotFoundError as exc:
            report[agent] = f'not found ({exc})'
            continue
        except Exception as exc:  # a format change must be loud, never a silent skip
            report[agent] = f'UNREADABLE ({exc.__class__.__name__}: {exc})'
            continue
        report[agent] = f'{len(found)} conversation(s)'
        for cid, label, messages in found:
            yield agent, cid, label, messages


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--collect', action='store_true')
    ap.add_argument('--process', action='store_true')
    ap.add_argument('--merge', action='store_true')
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--since', help='ISO time; required with --collect')
    ap.add_argument('--model')
    ap.add_argument('--provider')
    ap.add_argument('--cap', type=float, help='USD; required with --process')
    ap.add_argument('--ledger', help='Ledger file (default <audit>/harvest-ledger.sqlite)')
    args = ap.parse_args(argv)
    import wikiconfig
    import wiki_session_harvest as wsh
    out = {'ok': True}
    try:
        cfg = wikiconfig.load()
        if args.ledger:
            path = Path(args.ledger)
        else:
            from workflow_paths import checked_path
            path = checked_path(wikiconfig.audit_dir(cfg), 'harvest-ledger.sqlite')
        if args.collect and not args.since:
            raise ValueError('--collect needs --since')
        if args.process and (not args.model or not args.provider or args.cap is None):
            raise ValueError('--process needs --model, --provider and --cap')
        if args.merge and (not args.model or not args.provider or args.cap is None):
            raise ValueError('--merge needs --model, --provider and --cap')
        with hl.Ledger(path) as ledger:
            if args.collect or args.process:
                rules = owner_rules(cfg)
                version = hx.prompt_version(rules)
            if args.collect:
                hcfg = {**wsh.DEFAULTS, **(cfg.get('harvest') or {})}
                until = datetime.now().timestamp() - 60 * int(hcfg['settle_minutes'])
                agents = {}
                found = found_conversations(cfg, wsh.ts(args.since), until, agents)
                out['collected'] = collect(ledger, found, int(hcfg['max_chars']), version)
                out['agents'] = agents
            if args.process or args.merge:
                hermes = shutil.which('hermes')
                if not hermes:
                    raise ValueError('hermes is not on PATH')
                caller = hx.hermes_caller(hermes, args.model, args.provider, wikiconfig.hermes_home(cfg))
            if args.process:
                worker = f'{socket.gethostname()}-{os.getpid()}'
                out['processed'] = process(ledger, lambda parts: hx.extract(parts, caller, rules), worker, args.cap)
            if args.merge:
                from workflow_paths import checked_path
                night = datetime.now().strftime('%Y%m%d-%H%M%S')
                shadow = checked_path(wikiconfig.audit_dir(cfg), f'harvest-shadow/{night}')
                prompt_text = (Path(__file__).resolve().parent / 'harvest_prompt.md').read_text(encoding='utf-8')
                report = hm.merge_night(ledger, wikiconfig.project_root(cfg), shadow, caller, prompt_text, night,
                                        datetime.now().strftime('%Y-%m-%d'), cap_usd=args.cap)
                out['merged'] = {key: report[key] for key in ('night', 'candidates', 'refused', 'unchanged',
                                                              'cost_usd', 'stopped')}
                out['merged']['folder'] = str(shadow)
            out['ledger'] = ledger.summary()
    except (hl.LedgerError, hx.ExtractError, hm.MergeError, PathRefused, wikiconfig.ConfigError, OSError, ValueError) as exc:
        out = {'ok': False, 'error': str(exc)}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

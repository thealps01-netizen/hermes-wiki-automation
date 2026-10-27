"""Nightly run of the per-conversation harvest: the script-only cron job "Wiki Harvest".

WHAT IT DOES, in order: collects the conversations that changed since the last run into the ledger
(code only), reads each one with the reading model, then merges the new items into at most one draft
per wiki page with the merging model. Drafts go to <audit>/inbox/<night>/candidates/, where the
Review list shows them; nothing reaches the wiki without the owner's approval. The night's report
(cost, why it stopped, pages not reached, pages waiting for a review, skill candidates, article
signals) and every model reply are kept in <audit>/harvest-nights/<night>/.

LIMITS (settings.json "harvest_pipeline", defaults below): a cost cap and a time limit per night.
Reading may use 70% of both, so merging always has room; what a night does not reach waits in the
ledger for the next night. The time limit stays below Hermes' own script limit (one hour by default),
and a single model call times out after `call_timeout_seconds`, so the job is never killed half way.

WHERE IT STARTS: the ledger remembers the last collection. On the very first run it starts where the
current packed harvest stopped (its oldest cursor in harvest-state.json, read only), or `start` when
set, or `first_run_days` ago.

EXIT: 0 = the night ran (also when it stopped at a limit; the report says why); 1 = it could not run
(settings, ledger or a model call failed), with the reason on the last line. Prints one JSON line.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import harvest_extract as hx  # noqa: E402
import harvest_ledger as hl  # noqa: E402
import harvest_merge as hm  # noqa: E402
import harvest_pipeline as hp  # noqa: E402
from workflow_paths import PathRefused, checked_path  # noqa: E402

DEFAULTS = {'read_model': 'claude-sonnet-5-5', 'merge_model': 'claude-opus-5-5', 'provider': 'anthropic',
            'cap_usd': 10.0, 'minutes': 45, 'call_timeout_seconds': 600, 'start': None}
READ_SHARE = 0.7          # reading may use this share of the cap and of the time
OVERLAP_SECONDS = 6 * 3600   # re-scan this much before the last collection; the ledger skips what it has


def settings_of(cfg):
    return {**DEFAULTS, **(cfg.get('harvest_pipeline') or {})}


def since_for(ledger, settings, old_cursors, now, first_run_days):
    """{agent: epoch seconds to collect from} (see WHERE IT STARTS). Each agent starts from its own
    packed-harvest cursor: one agent whose cursor never moved must not pull the others back."""
    import wiki_session_harvest as wsh
    last = ledger.get_meta('collected_until')
    if last is not None:
        start = {}
        fallback = last - OVERLAP_SECONDS
    elif settings.get('start'):
        start, fallback = {}, wsh.ts(settings['start'])
    else:
        start, fallback = dict(old_cursors), now - first_run_days * 86400
    return {agent: start.get(agent, fallback) for agent in wsh.DEFAULTS['agents']}


def busy_targets(inbox):
    """Pages that already have a draft waiting in Review."""
    from wiki_candidates import pending
    busy = set()
    for folder in pending(inbox):
        try:
            busy.add(json.loads((folder / 'candidate.json').read_bytes())['target'])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return busy


def run_night(ledger, *, extract, merge_caller, wiki, inbox, nights, rules_text, night, today, settings,
              clock=time.time):
    """Read and merge one night (the ledger is already collected). Returns the report."""
    started = clock()
    deadline = started + 60 * float(settings['minutes'])
    cap = float(settings['cap_usd'])
    worker = f'{socket.gethostname()}-{os.getpid()}'
    read = hp.process(ledger, extract, worker, cap_usd=cap * READ_SHARE,
                      deadline=started + (deadline - started) * READ_SHARE, clock=clock)
    report = {'night': night, 'read': read, 'merge': None}
    if read['stopped'] and read['stopped'].startswith('call failed'):
        report['stopped'] = read['stopped']
        return report
    if not ledger.unmerged():
        report['stopped'] = read['stopped']
        return report
    candidates = checked_path(inbox, f'{night}/candidates')
    merged = hm.merge_night(ledger, wiki, checked_path(nights, night), merge_caller, rules_text, night, today,
                            cap_usd=max(cap - read['cost_usd'], 0.0), busy=busy_targets(inbox),
                            deadline=deadline, clock=clock, candidates_dir=candidates)
    report['merge'] = {key: merged[key] for key in ('candidates', 'refused', 'unchanged', 'not_drafted',
                                                    'waiting_on_review', 'cost_usd', 'stopped')}
    report['stopped'] = read['stopped'] or merged['stopped']
    return report


def main(argv):
    import wikiconfig
    import wiki_session_harvest as wsh
    out = {'ok': True}
    try:
        if argv:
            raise ValueError(f'harvest_night.py takes no arguments (got {argv[0]!r})')
        cfg = wikiconfig.load()
        settings = settings_of(cfg)
        audit, wiki = wikiconfig.audit_dir(cfg), wikiconfig.project_root(cfg)
        hcfg = {**wsh.DEFAULTS, **(cfg.get('harvest') or {})}
        hermes = shutil.which('hermes')
        if not hermes:
            raise ValueError('hermes is not on PATH')
        home = wikiconfig.hermes_home(cfg)
        timeout = int(settings['call_timeout_seconds'])
        read_call = hx.hermes_caller(hermes, settings['read_model'], settings['provider'], home, timeout=timeout)
        merge_call = hx.hermes_caller(hermes, settings['merge_model'], settings['provider'], home, timeout=timeout)
        rules = hp.owner_rules(cfg)
        rules_text = (Path(__file__).resolve().parent / 'harvest_prompt.md').read_text(encoding='utf-8')
        now = time.time()
        night = datetime.fromtimestamp(now).strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(6)
        with hl.Ledger(checked_path(audit, 'harvest-ledger.sqlite')) as ledger:
            old = wsh.load_state(checked_path(audit, 'harvest-state.json'))['cursors']
            since = since_for(ledger, settings, old, now, int(hcfg['first_run_days']))
            until = now - 60 * int(hcfg['settle_minutes'])
            agents = {}
            found = hp.found_conversations(cfg, since, until, agents)
            out['collected'] = hp.collect(ledger, found, int(hcfg['max_chars']), hx.prompt_version(rules))
            out['agents'] = agents
            ledger.set_meta('collected_until', until)
            out.update(run_night(ledger, extract=lambda parts: hx.extract(parts, read_call, rules),
                                 merge_caller=merge_call, wiki=wiki, inbox=checked_path(audit, 'inbox'),
                                 nights=checked_path(audit, 'harvest-nights'), rules_text=rules_text, night=night,
                                 today=datetime.fromtimestamp(now).strftime('%Y-%m-%d'), settings=settings))
            out['ledger'] = ledger.summary()
        if out['stopped'] and out['stopped'].startswith('call failed'):
            out['ok'] = False
    except (hl.LedgerError, hx.ExtractError, hm.MergeError, PathRefused, wikiconfig.ConfigError, OSError,
            ValueError) as exc:
        out = {'ok': False, 'error': str(exc)}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

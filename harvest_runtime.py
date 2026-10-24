from functools import partial
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def current(ctx):
    execution = ctx.current_cron_execution()
    if (ctx.get_config('harvest_workflow_enabled', None) is not True or execution is None
            or execution.job_id != ctx.get_config('draft_job_id', None)
            or execution.source not in ('builtin', 'direct')):
        return None
    from .draft_security import approval_runtime_ready
    if not approval_runtime_ready():
        return None
    return execution


def run(paths, args, body=None):
    reply = subprocess.run([sys.executable, '-B', str(paths.engine_dir / 'wiki_session_harvest.py'), *args],
        input=json.dumps(body) if body is not None else None, capture_output=True, text=True,
        encoding='utf-8', timeout=60, env=paths.environment())
    if reply.returncode:
        raise RuntimeError('Native harvest refused or failed; captured inputs and cursors were preserved')
    return json.loads(reply.stdout.splitlines()[-1])


def start(ctx, *, session_id, **kwargs):
    execution = current(ctx)
    if execution is None:
        return
    from .engine_paths import resolve_engine_paths
    paths = resolve_engine_paths()
    engine = paths.engine_dir
    settings = json.loads(paths.settings_path.read_bytes())
    if settings.get('harvest_workflow_enabled') is not True:
        raise RuntimeError('Selected engine has not explicitly activated native harvest')
    if not settings.get('hermes_home') or Path(settings['hermes_home']).resolve() != paths.home:
        raise RuntimeError('Collector settings are not owned by the current native profile')
    data = Path(settings['audit_dir'])
    if not data.is_dir():
        raise RuntimeError('Configured harvest data root is absent; no fallback collection is allowed')
    previous = getattr(ctx, '_wiki_harvest_states', {}).get(execution.execution_id)
    if previous is not None:
        if previous['session'] != session_id or previous['paths'] != paths:
            raise RuntimeError('An existing native execution cannot be rebound to another session or engine')
        return
    reply = run(paths, ['--execution-id', execution.execution_id, '--job-id', execution.job_id])
    if not reply.get('run_id'):
        return
    manifest = json.loads((data / 'inbox' / reply['run_id'] / 'run.json').read_bytes())
    if manifest.get('execution_id') != execution.execution_id or manifest.get('job_id') != execution.job_id:
        raise RuntimeError('Collector returned a foreign execution')
    states = getattr(ctx, '_wiki_harvest_states', {})
    states[execution.execution_id] = {'session': session_id, 'engine': engine, 'paths': paths, 'manifest': manifest,
        'run': reply['run_id'], 'reads': {}, 'totals': {}, 'submitted': set(), 'response': None}
    ctx._wiki_harvest_states = states


def state(ctx, session_id=None):
    execution = current(ctx)
    if execution is None:
        return None
    row = getattr(ctx, '_wiki_harvest_states', {}).get(execution.execution_id)
    if row is None or (session_id is not None and row['session'] != session_id):
        return None
    return row


def inject(ctx, *, session_id, **kwargs):
    row = state(ctx, session_id)
    if row is None:
        return
    return {'context': 'Native bound harvest run: ' + row['run']
        + '. Use only wiki_draft_read and wiki_draft_submit. Read run.json and every sources-index/conversation part completely. '
        + 'Never run a command, approve, apply or advance cursors. Final response must be one JSON object with '
        + 'owner_report (the human morning report) and missing_evidence. The candidates are the ones wiki_draft_submit accepted; a listed candidate is not read. A scheduler success or SILENT does not finish domain processing.'}


def observe(ctx, operation, args, output):
    row = state(ctx)
    if row is None or args.get('run_id') != row['run']:
        return
    if operation == 'submit':
        if isinstance(output.get('ref'), str):
            row['submitted'].add(output['ref'])
        return
    if operation != 'read':
        return
    path = args.get('path')
    if path not in row['manifest']['input_hashes']:
        return
    if not isinstance(output.get('text'), str) or output.get('sha256') != row['manifest']['input_hashes'][path]:
        row['reads'].pop(path, None)
        row['totals'].pop(path, None)
        return False
    start = args.get('offset', 0)
    end = start + len(output['text'])
    row['reads'].setdefault(path, []).append((start, end))
    if output.get('truncated') is False:
        row['totals'][path] = end


def final(parsed):
    if not isinstance(parsed, dict):
        return None
    items = parsed.get('missing_evidence')
    return {'missing_evidence': [item for item in items if isinstance(item, str)] if isinstance(items, list) else []}


def render_report(ctx, *, session_id, response_text, **kwargs):
    row = state(ctx, session_id)
    if row is None:
        return
    try:
        parsed = json.loads(response_text)
        if final(parsed) is None or not isinstance(parsed.get('owner_report'), str) or not parsed['owner_report'].strip():
            return
        row['response'] = final(parsed)
        row['rendered_hash'] = hashlib.sha256(parsed['owner_report'].encode('utf-8')).hexdigest()
        return parsed['owner_report']
    except (ValueError, TypeError):
        return


def response(ctx, *, session_id, assistant_response, **kwargs):
    row = state(ctx, session_id)
    if row is None:
        return
    if isinstance(assistant_response, str) and row.get('rendered_hash') == hashlib.sha256(assistant_response.encode('utf-8')).hexdigest():
        return
    row['response'] = None
    row.pop('rendered_hash', None)
    try:
        row['response'] = final(json.loads(assistant_response))
    except (TypeError, ValueError):
        pass


def finish(ctx, *, session_id, completed=False, failed=True, interrupted=True, **kwargs):
    row = state(ctx, session_id)
    if row is None or completed is not True or failed is not False or interrupted is not False or row['response'] is None:
        return
    for path in row['manifest']['input_hashes']:
        end = 0
        for begin, stop in sorted(row['reads'].get(path, [])):
            if begin > end:
                return
            end = max(end, stop)
        if path not in row['totals'] or end != row['totals'][path]:
            return
    execution = ctx.current_cron_execution()
    refs = sorted(row['submitted'])
    outcome = {'status': 'drafted' if refs else 'no_candidates', 'candidate_refs': refs,
        'missing_evidence': row['response']['missing_evidence'], 'execution_id': execution.execution_id, 'job_id': execution.job_id,
        'reviewed_inputs': row['manifest']['input_hashes']}
    run(row['paths'], ['--host-outcome', '--home', str(row['paths'].home),
        '--execution-id', execution.execution_id, '--job-id', execution.job_id],
        {'run_id': row['run'], 'outcome': outcome})


def register(ctx):
    for name, handler in (('on_session_start', start), ('pre_llm_call', inject),
            ('transform_llm_output', render_report), ('post_llm_call', response), ('on_session_end', finish)):
        ctx.register_hook(name, partial(handler, ctx))

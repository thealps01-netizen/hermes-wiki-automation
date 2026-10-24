from functools import partial
import json
import subprocess
import sys

DRAFT_TOOLS = frozenset({'wiki_draft_read', 'wiki_draft_submit'})


def draft_guard(ctx, *, tool_name, args=None, **kwargs):
    execution = ctx.current_cron_execution()
    if execution is None:
        return None
    job_id = ctx.get_config('draft_job_id', None)
    if job_id and execution.job_id == job_id and tool_name not in DRAFT_TOOLS:
        return {'action': 'block', 'message': 'Wiki drafting can only read bounded inputs and submit candidates; execution, approval and live writes are forbidden.'}
    return None


def draft_call(ctx, operation, args, **kwargs):
    execution = ctx.current_cron_execution()
    if execution is None or execution.job_id != ctx.get_config('draft_job_id', None):
        return json.dumps({'error': 'Only the configured, host-bound drafting job may call this tool'})
    try:
        from .engine_paths import resolve_engine_paths
        from .harvest_runtime import state
        captured = state(ctx)
        paths = captured['paths'] if captured is not None else resolve_engine_paths()
        engine = paths.engine_dir
        encoded = json.dumps(args, ensure_ascii=False)
        if len(encoded.encode('utf-8')) > 300000:
            raise ValueError('Draft request is oversized')
        proc = subprocess.run([sys.executable, '-B', str(engine / 'draft_adapter.py'), operation,
                               '--execution-id', execution.execution_id, '--job-id', execution.job_id,
                               '--home', str(paths.home), '--settings', str(paths.settings_path)],
                              input=encoded, capture_output=True, text=True, encoding='utf-8',
                              timeout=30, env=paths.environment())
        if proc.returncode:
            return json.dumps({'error': (proc.stdout or proc.stderr or 'Draft adapter failed')[:2000]})
        output = json.loads(proc.stdout)
        from .harvest_runtime import observe
        if observe(ctx, operation, args, output) is False:
            return json.dumps({'error': 'Captured input changed; out-of-snapshot content was not returned'})
        return json.dumps(output, ensure_ascii=False)
    except (OSError, ValueError, subprocess.SubprocessError, ImportError) as exc:
        return json.dumps({'error': str(exc)[:2000]})


def approval_runtime_ready():
    from hermes_cli.plugins import iter_hook_callbacks
    from cron.jobs import get_job
    from cron.execution_identity import enter_cron_execution, exit_cron_execution
    try:
        guards = [callback for callback in iter_hook_callbacks('pre_tool_call')
                  if isinstance(callback, partial) and callback.func is draft_guard and callback.args]
        if len(guards) != 1:
            return False
        ctx = guards[0].args[0]
        from tools.registry import registry
        for name, operation in (('wiki_draft_read', 'read'), ('wiki_draft_submit', 'submit')):
            entry = registry.get_entry(name)
            handler = entry.handler if entry is not None else None
            if entry is None or entry.toolset != 'wiki_draft' or not isinstance(handler, partial):
                return False
            if handler.func is not draft_call or handler.args != (ctx, operation) or handler.keywords:
                return False
        job_id = ctx.get_config('draft_job_id', None)
        job = get_job(job_id) if job_id else None
        if not job or job.get('no_agent') or set(job.get('enabled_toolsets') or []) != {'wiki_draft', 'no_mcp'}:
            return False
        token = enter_cron_execution(job, 'owner-readiness-probe', {})
        try:
            for name in ('terminal', 'execute_code', 'write_file', 'browser_exec', 'computer_use', 'delegate_task', 'tool_call'):
                directive = draft_guard(ctx, tool_name=name, args={})
                if not directive or directive.get('action') != 'block':
                    return False
        finally:
            exit_cron_execution(token)
        return True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def register(ctx):
    ctx.register_hook('pre_tool_call', partial(draft_guard, ctx))
    common = {'run_id': {'type': 'string'}}
    for name, operation, fields, required in [
        ('wiki_draft_read', 'read', {'path': {'type': 'string'}, 'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}}, ['run_id', 'path']),
        ('wiki_draft_submit', 'submit', {'name': {'type': 'string'}, 'metadata': {'type': 'object'}, 'source': {'type': ['string', 'null']}}, ['run_id', 'name', 'metadata', 'source']),
    ]:
        ctx.register_tool(name=name, toolset='wiki_draft',
                          schema={'name': name, 'description': 'Bounded wiki draft input read' if operation == 'read' else 'Submit an immutable candidate, never apply it',
                                  'parameters': {'type': 'object', 'properties': {**common, **fields}, 'required': required, 'additionalProperties': False}},
                          handler=partial(draft_call, ctx, operation))


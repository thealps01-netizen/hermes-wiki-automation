"""Process-local evidence, not an all-process or human-gesture attestation.

The deliberately inert canary is outside the drafting toolset. If the veto is absent, its own
handler returns an error without doing anything. No terminal, file, browser or model is invoked.
"""
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import uuid

_INCARNATION = uuid.uuid4().hex
_LOADED_CODE_HASH = hashlib.sha256(b''.join((Path(__file__).parent / name).read_bytes()
    for name in ('__init__.py', 'draft_security.py', 'runtime_probe.py', 'runtime_channel.py', 'harvest_runtime.py', 'engine_paths.py'))).hexdigest()
_REACHED = ContextVar('wiki_security_probe_reached', default=None)


def canary(args, **kwargs):
    reached = _REACHED.get()
    if reached is not None:
        reached['handler_reached'] = True
    return json.dumps({'error': 'Inert runtime canary reached its handler; drafting veto is not verified'})


def register(ctx):
    ctx.register_tool(name='wiki_security_canary', toolset='wiki_security_internal',
        schema={'name': 'wiki_security_canary', 'description': 'Inert native-dispatch canary, not a drafting or approval capability',
                'parameters': {'type': 'object', 'properties': {'challenge': {'type': 'string'}},
                               'required': ['challenge'], 'additionalProperties': False}}, handler=canary)


def probe(ctx, challenge, *, paths=None):
    from cron.execution_identity import enter_cron_execution, exit_cron_execution
    from model_tools import handle_function_call
    from .engine_paths import resolve_engine_paths
    if not isinstance(challenge, str) or len(challenge) != 64 or any(ch not in '0123456789abcdef' for ch in challenge):
        raise ValueError('Runtime challenge must be an exact SHA-256-sized nonce')
    job_id = ctx.get_config('draft_job_id', None)
    paths = resolve_engine_paths() if paths is None else paths
    result = {'schema_version': 1, 'challenge': challenge, 'pid': os.getpid(),
              'incarnation': _INCARNATION, 'loaded_code_hash': _LOADED_CODE_HASH,
              'home': str(paths.home), 'job_id': job_id, 'engine_identity': paths.code_identity(),
              'scope': 'process-local synthetic cron-context canary',
              'handler_reached': False, 'veto_exercised': False}
    if not job_id:
        return result
    reached = {'handler_reached': False}
    reach_token = _REACHED.set(reached)
    token = enter_cron_execution({'id': job_id}, f'verification-{challenge}', {'source': 'native-verification'})
    try:
        verdict = json.loads(handle_function_call('wiki_security_canary', {'challenge': challenge},
            tool_call_id=challenge, enabled_toolsets=['wiki_draft', 'no_mcp']))
        error = verdict.get('error', '')
        result['handler_reached'] = reached['handler_reached']
        result['veto_exercised'] = (not reached['handler_reached'] and isinstance(error, str)
                                   and error.startswith('Wiki drafting can only read bounded inputs and submit candidates;'))
        return result
    finally:
        exit_cron_execution(token)
        _REACHED.reset(reach_token)

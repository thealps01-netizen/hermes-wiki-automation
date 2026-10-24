from __future__ import annotations
import hashlib
import json
from fastapi import APIRouter, Request, HTTPException


def _host_owner_session(request: Request):
    """Shared caller checks: a token-verified interactive host session, never cron or a service."""
    from hermes_cli.web_server import _require_token
    from hermes_constants import get_hermes_home
    from cron.execution_identity import current_cron_execution
    if current_cron_execution() is not None or getattr(request.state, 'token_authenticated', False):
        raise HTTPException(status_code=403, detail='Automated/service callers cannot issue owner decisions')
    _require_token(request)
    from hermes_cli.config import load_config_readonly
    if (load_config_readonly().get('plugins') or {}).get('isolation') == 'host':
        raise HTTPException(status_code=403, detail='Owner session bridge is unsupported in host plugin isolation')
    return get_hermes_home().resolve()


def host_binding(request: Request) -> dict:
    """The owner binding this host session would hold, derived only from host-verified state."""
    home = _host_owner_session(request)
    if getattr(request.app.state, 'auth_required', False):
        session = request.state.session
        return {'mode': 'interactive_owner', 'home': str(home), 'provider': session.provider,
                'user_id': session.user_id, 'org_id': session.org_id}
    return {'mode': 'local_owner', 'home': str(home)}


def owner_principal(request: Request, binding=None) -> str:
    from pathlib import Path
    from hermes_cli.web_server import _SESSION_TOKEN
    home = _host_owner_session(request)
    if not isinstance(binding, dict) or not binding.get('home') or Path(binding['home']).resolve() != home:
        raise HTTPException(status_code=403, detail='No explicit owner binding exists for this profile')
    if getattr(request.app.state, 'auth_required', False):
        session = request.state.session
        if binding.get('mode') != 'interactive_owner' or any(getattr(session, field, None) != binding.get(field) for field in ('provider', 'user_id', 'org_id')):
            raise HTTPException(status_code=403, detail='Authenticated caller is not the configured owner')
        identity = ['interactive_owner', session.provider, session.user_id, session.org_id,
                    hashlib.sha256(session.access_token.encode()).hexdigest()]
    else:
        if binding.get('mode') != 'local_owner':
            raise HTTPException(status_code=403, detail='Local owner trust is not explicitly configured')
        identity = ['local_owner', _SESSION_TOKEN]
    value = json.dumps([str(home), identity], ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(value).hexdigest()


def binding_key(binding):
    from pathlib import Path
    identity = [str(Path(binding['home']).resolve()), binding['mode']]
    if binding['mode'] == 'interactive_owner':
        identity.extend(binding[field] for field in ('provider', 'user_id', 'org_id'))
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def checked_result(result, operation=None):
    schemas = {
        'activate': {'ok', 'reason', 'activated'},
        'prepare': {'ok', 'reason', 'retryable', 'needs_confirm', 'request_id', 'review_digest', 'expires_at', 'output'},
        'confirm': {'ok', 'reason', 'retryable', 'authorized', 'request_id', 'operation_id', 'state', 'later_drift'},
        'recover': {'ok', 'reason', 'retryable', 'authorized', 'request_id', 'operation_id', 'state', 'later_drift'},
        'recoverable': {'ok', 'reason', 'retryable', 'operations'},
    }
    allowed = set().union(*schemas.values()) if operation is None else schemas[operation]
    if not isinstance(result, dict) or set(result) - allowed or type(result.get('ok')) is not bool:
        raise ValueError('Owner engine returned an unsupported response schema')
    for key, value in result.items():
        if key in {'ok', 'retryable', 'authorized', 'needs_confirm', 'later_drift', 'activated'}:
            valid = type(value) is bool
        elif key == 'expires_at':
            import math
            valid = type(value) in (int, float) and math.isfinite(value)
        elif key == 'operations':
            fields = {'request_id', 'ref', 'kind', 'target', 'review_digest', 'state'}
            valid = isinstance(value, list) and all(isinstance(row, dict) and set(row) == fields
                and all(isinstance(item, str) for item in row.values()) for row in value)
        else:
            valid = isinstance(value, str)
        if not valid:
            raise ValueError('Owner engine returned an unsupported response value')
    return result


def make_router(run, ready, owner_binding=None, activation=None):
    router = APIRouter()

    @router.get('/activation')
    def activation_status(request: Request):
        binding = host_binding(request)
        if activation is None:
            return {'ok': False, 'reason': 'Owner setup is unavailable in this build.'}
        try:
            return activation.plan(binding)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {'ok': False, 'reason': f'Owner setup unavailable: {exc}'}

    @router.post('/activation')
    def activate(payload: dict, request: Request):
        binding = host_binding(request)
        digest = payload.get('plan_digest')
        if set(payload) != {'confirm', 'plan_digest'} or payload.get('confirm') is not True or not isinstance(digest, str) \
                or len(digest) != 64 or any(ch not in '0123456789abcdef' for ch in digest):
            raise HTTPException(status_code=400, detail='Owner setup needs the reviewed plan and an explicit confirmation')
        if activation is None:
            return {'ok': False, 'reason': 'Owner setup is unavailable in this build.'}
        try:
            plan = activation.plan(binding)
            if plan.get('ok') is not True or plan.get('plan_digest') != digest:
                return {'ok': False, 'reason': plan.get('reason') or 'The setup changed after it was shown; review it again.'}
            result = checked_result(run('activate', {'binding': binding, 'loaded_code_hash': plan['loaded_code_hash']}),
                                    'activate')
            if result.get('ok') is not True:
                return result
            activation.apply(plan)
            return {'ok': True, 'restart_required': True}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {'ok': False, 'reason': f'Owner setup failed: {exc}'}

    @router.post('/decision')
    def decide(payload: dict, request: Request):
        binding = owner_binding() if owner_binding else None
        principal = owner_principal(request, binding)
        if not ready():
            return {'ok': False, 'reason': 'Constrained drafting runtime is not verified; owner authority is unavailable.'}
        if set(payload) - {'ref', 'review_digest', 'confirm', 'request_id'} or type(payload.get('confirm')) is not bool:
            raise HTTPException(status_code=400, detail='Unsupported owner decision fields')
        if not isinstance(payload.get('review_digest'), str) or len(payload['review_digest']) != 64:
            return {'ok': False, 'reason': 'Exact displayed review digest is required; review again.'}
        operation = 'confirm' if payload['confirm'] else 'prepare'
        body = {'ref': payload.get('ref'), 'review_digest': payload['review_digest'], 'principal': principal,
                'owner_key': binding_key(binding)}
        if operation == 'confirm':
            if not isinstance(payload.get('request_id'), str):
                return {'ok': False, 'reason': 'Pending owner request is required; review again.'}
            body['request_id'] = payload['request_id']
        try:
            return checked_result(run(operation, body), operation)
        except (OSError, ValueError) as exc:
            return {'ok': False, 'reason': f'Owner decision unavailable: {exc}'}

    @router.post('/recover')
    def recover(payload: dict, request: Request):
        binding = owner_binding() if owner_binding else None
        principal = owner_principal(request, binding)
        request_id = payload.get('request_id')
        if set(payload) != {'request_id'} or not isinstance(request_id, str) or len(request_id) != 64 or any(ch not in '0123456789abcdef' for ch in request_id):
            raise HTTPException(status_code=400, detail='Recovery accepts only an approved request identity')
        if not ready():
            return {'ok': False, 'reason': 'Constrained drafting runtime is not verified; recovery is unavailable.'}
        try:
            return checked_result(run('recover', {'principal': principal, 'owner_key': binding_key(binding), 'request_id': request_id}), 'recover')
        except (OSError, ValueError) as exc:
            return {'ok': False, 'reason': f'Owner recovery unavailable: {exc}'}

    @router.get('/recoverable')
    def recoverable(request: Request):
        binding = owner_binding() if owner_binding else None
        principal = owner_principal(request, binding)
        if not ready():
            return {'ok': False, 'reason': 'Constrained drafting runtime is not verified; recovery is unavailable.'}
        try:
            return checked_result(run('recoverable', {'principal': principal, 'owner_key': binding_key(binding)}), 'recoverable')
        except (OSError, ValueError) as exc:
            return {'ok': False, 'reason': f'Owner recovery unavailable: {exc}'}

    return router

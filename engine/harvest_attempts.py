"""Per-run record of why a harvest run stopped and what its drafting session cost.

The native plugin reports two events for each bound run: `start` (which drafting session
owns the run) and `end` (how the turn ended and, when the run could not be finished, why).
They are stored beside the run as `attempt.json`; the captured inputs and `run.json` are never
touched. Usage and cost are read, read-only, from the owning profile's session store, so the
figures are the ones Hermes itself recorded, not an estimate made here.

Reported stop reasons (`code`):
  not_recorded    the run predates this record
  no_end_event    the drafting session ended without reporting back (end reason named)
  turn_failed     the drafting turn failed or was interrupted
  no_final_report the final answer was not the required JSON report
  unread_input    a captured input was not read completely
  outcome_refused the engine refused the completion (its reason is kept)
  not_finished    the turn ended cleanly but the run was not finished
"""
import json
import os
from pathlib import Path
import sqlite3
import tempfile

ATTEMPT = 'attempt.json'
START_FIELDS = {'stage', 'session_id'}
END_FIELDS = {'stage', 'session_id', 'completed', 'failed', 'interrupted', 'turn_exit_reason', 'model', 'stop'}
STOP_CODES = {'turn_failed', 'no_final_report', 'unread_input', 'outcome_refused'}
USAGE_COLUMNS = ('model', 'ended_at', 'end_reason', 'input_tokens', 'output_tokens', 'cache_read_tokens',
                 'cache_write_tokens', 'estimated_cost_usd', 'actual_cost_usd', 'cost_status')


class AttemptError(Exception):
    pass


def _run_dir(audit: Path, run_id: str) -> Path:
    from workflow_paths import checked_path, identifier, PathRefused
    try:
        return checked_path(audit, f'inbox/{identifier(run_id)}')
    except (PathRefused, ValueError) as exc:
        raise AttemptError('Run name is not a plain run identifier') from exc


def _text(value, limit=400):
    return isinstance(value, str) and 0 < len(value) <= limit


def _check(event: dict) -> None:
    if not isinstance(event, dict) or event.get('stage') not in ('start', 'end'):
        raise AttemptError('Unsupported attempt event')
    if set(event) != (START_FIELDS if event['stage'] == 'start' else END_FIELDS):
        raise AttemptError('Unsupported attempt event fields')
    if not _text(event['session_id'], 200):
        raise AttemptError('Attempt event lacks its session')
    if event['stage'] == 'end':
        if any(not isinstance(event[name], bool) for name in ('completed', 'failed', 'interrupted')):
            raise AttemptError('Turn end flags must be true or false')
        if any(event[name] is not None and not _text(event[name], 200) for name in ('turn_exit_reason', 'model')):
            raise AttemptError('Turn end labels are malformed')
        stop = event['stop']
        if stop is not None and (not isinstance(stop, dict) or set(stop) != {'code', 'detail'}
                                 or stop['code'] not in STOP_CODES or not _text(stop['detail'], 2000)):
            raise AttemptError('Stop reason is malformed')


def _read(folder: Path) -> dict:
    path = folder / ATTEMPT
    if not path.is_file():
        return {}
    data = json.loads(path.read_bytes())
    if not isinstance(data, dict):
        raise AttemptError(f'{path.name} is not an object')
    return data


def record(audit: Path, run_id: str, execution_id: str, job_id: str, event: dict) -> None:
    """Store one event for a run collected by this exact native execution."""
    _check(event)
    folder = _run_dir(audit, run_id)
    manifest = json.loads((folder / 'run.json').read_bytes())
    if not execution_id or manifest.get('execution_id') != execution_id or manifest.get('job_id') != job_id:
        raise AttemptError('Attempt is not bound to the collected execution')
    data = _read(folder)
    bound = (data.get('start') or {}).get('session_id')
    if bound and bound != event['session_id']:
        raise AttemptError('A run cannot be rebound to another drafting session')
    data[event['stage']] = event
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    handle, temporary = tempfile.mkstemp(dir=folder, prefix='.attempt-', suffix='.tmp')
    try:
        with os.fdopen(handle, 'wb') as stream:
            stream.write(payload)
        os.replace(temporary, folder / ATTEMPT)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def usage(home, session_id):
    """Hermes' own token and cost figures for the drafting session; an error is reported, not guessed."""
    if not session_id:
        return None
    if not home:
        return {'error': 'The owning profile is not configured, so cost cannot be read'}
    database = Path(home) / 'state.db'
    if not database.is_file():
        return {'error': 'The profile session store is missing, so cost cannot be read'}
    try:
        connection = sqlite3.connect(f'{database.resolve().as_uri()}?mode=ro', uri=True, timeout=5)
        try:
            present = {row[1] for row in connection.execute('PRAGMA table_info(sessions)')}
            columns = [name for name in USAGE_COLUMNS if name in present]
            row = connection.execute(f'SELECT {", ".join(columns)} FROM sessions WHERE id = ?', (session_id,)).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return {'error': f'The profile session store could not be read: {exc}'}
    if row is None:
        return {'error': 'The drafting session is not in the profile session store'}
    found = dict(zip(columns, row))
    actual = found.get('actual_cost_usd')
    return {'model': found.get('model'), 'ended': found.get('ended_at') is not None, 'end_reason': found.get('end_reason'),
            'input_tokens': found.get('input_tokens'), 'output_tokens': found.get('output_tokens'),
            'cache_read_tokens': found.get('cache_read_tokens'), 'cache_write_tokens': found.get('cache_write_tokens'),
            'cost_usd': actual if actual is not None else found.get('estimated_cost_usd'),
            'cost_status': 'actual' if actual is not None else found.get('cost_status')}


def describe(audit: Path, run_id: str, manifest: dict, home=None) -> dict:
    """The run's drafting session, why it stopped (None while running or once finished) and its usage."""
    data = _read(_run_dir(audit, run_id))
    session_id = (data.get('start') or data.get('end') or {}).get('session_id')
    spent = usage(home, session_id)
    end = data.get('end')
    if manifest.get('committed') is True:
        stop = None
    elif not data:
        stop = {'code': 'not_recorded', 'detail': 'This run predates the stop-reason record.'}
    elif end and end.get('stop'):
        stop = end['stop']
    elif end:
        stop = {'code': 'not_finished', 'detail': 'The drafting turn ended cleanly, but the run was not finished.'}
    elif spent and spent.get('ended'):
        stop = {'code': 'no_end_event', 'detail': 'The drafting session ended without reporting back '
                f"(session end reason: {spent.get('end_reason') or 'none recorded'})."}
    else:
        stop = None
    return {'session_id': session_id, 'stop_reason': stop, 'usage': spent}

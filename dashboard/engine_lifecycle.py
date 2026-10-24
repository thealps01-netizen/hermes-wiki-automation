"""Transport and verified staging only; engine setup remains engine-owned."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import os
import stat
import uuid
import secrets
import time
from fastapi import Request
from contextlib import contextmanager
from functools import wraps


@contextmanager
def installation_lock(home):
    target = confined(Path(home), 'state/wiki-automation/lifecycle.lock')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a+b') as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LifecycleRefused('Another installation is in progress; retry the same plan later') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def serialized(function):
    @wraps(function)
    def run(home, *args, **kwargs):
        with installation_lock(home):
            return function(home, *args, **kwargs)
    return run

MAX_EXPANDED = 32 * 1024 * 1024
MAX_ENTRIES = 512


def _reject_links(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise LifecycleRefused('Release path metadata is unreadable') from exc
    if (stat.S_ISLNK(metadata.st_mode)
            or getattr(metadata, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
        raise LifecycleRefused('Linked release path refused')
    if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink > 1:
        raise LifecycleRefused('Hard-linked release path refused')


def relative_parts(relative: str) -> list:
    if not isinstance(relative, str) or not relative or any(ch in relative for ch in ('\\', ':', '\0')):
        raise LifecycleRefused('Invalid relative artifact path')
    parts = relative.split('/')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *('COM' + str(i) for i in range(1, 10)), *('LPT' + str(i) for i in range(1, 10))}
    if any(part in ('', '.', '..') or part.endswith(('.', ' ')) or part.split('.')[0].upper() in reserved for part in parts):
        raise LifecycleRefused('Archive traversal or ambiguous spelling')
    return parts


def confined(root: Path, relative: str) -> Path:
    parts = relative_parts(relative)
    root = Path(root)
    current = root
    absolute = root.absolute()
    for ancestor in [*reversed(absolute.parents), absolute]:
        _reject_links(ancestor)
    for part in parts:
        if current.is_dir():
            matching = [entry.name for entry in current.iterdir() if entry.name.casefold() == part.casefold()]
            if matching and matching != [part]:
                raise LifecycleRefused('Release path case collision')
        current = current / part
        _reject_links(current)
    return current


class LifecycleRefused(RuntimeError):
    pass


def release_digest(files: dict) -> str:
    return hashlib.sha256(_canonical(sorted([name, hashlib.sha256(data).hexdigest()]
        for name, data in files.items()))).hexdigest()


def read_release_tree(package: Path, manifest: dict) -> dict:
    root = confined(package, manifest['artifact'])
    if not root.is_dir():
        raise LifecycleRefused('Bundled engine folder is missing')
    files, folded, expanded = {}, set(), 0
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if '__pycache__' in relative.split('/'):
            continue
        safe = confined(root, relative)
        if safe.is_dir():
            continue
        if not safe.is_file():
            raise LifecycleRefused('Linked, special or unreadable engine file')
        if relative.casefold() in folded:
            raise LifecycleRefused('Duplicate or case-colliding engine file')
        folded.add(relative.casefold())
        if len(folded) > MAX_ENTRIES:
            raise LifecycleRefused('Bundled engine has too many files')
        data = safe.read_bytes()
        expanded += len(data)
        if expanded > MAX_EXPANDED:
            raise LifecycleRefused('Bundled engine exceeds the size limit')
        files[relative] = data
    return files


def stage_release(home: Path, package: Path, manifest: dict) -> Path:
    if (manifest.get('schema') != 2 or not isinstance(manifest.get('artifact'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', manifest.get('sha256', ''))
            or manifest.get('revision') != manifest['sha256'][:40]):
        raise LifecycleRefused('Unsupported or incomplete pinned release manifest')
    python_min, schema = manifest.get('python_min'), manifest.get('workflow_schema')
    if (not isinstance(python_min, list) or len(python_min) != 2
            or any(type(part) is not int or part < 0 for part in python_min)
            or sys.version_info[:2] < tuple(python_min)
            or not isinstance(schema, dict) or type(schema.get('min')) is not int
            or type(schema.get('max')) is not int or not 1 <= schema['min'] <= 1 <= schema['max']):
        raise LifecycleRefused('Release Python or workflow-schema requirements are incompatible')
    files = read_release_tree(package, manifest)
    if release_digest(files) != manifest['sha256']:
        raise LifecycleRefused('Bundled engine digest disagrees with the selected release')
    release = confined(home, 'state/wiki-automation/releases/' + manifest['revision'])
    if release.exists():
        observed = set()
        for target in release.rglob('*'):
            name = target.relative_to(release).as_posix()
            confined(release, name)
            if target.is_file():
                observed.add(name)
                if name not in files or target.read_bytes() != files[name]:
                    raise LifecycleRefused('Existing code release is dirty; it was preserved')
        if observed != set(files):
            raise LifecycleRefused('Existing release is incomplete; it was preserved')
        return release
    staging = confined(home, 'state/wiki-automation/staging/' + uuid.uuid4().hex)
    staging.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = confined(staging, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    release.parent.mkdir(parents=True, exist_ok=True)
    os.rename(staging, release)
    return release


def _checkpoint(phase):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex)
    with temporary.open('xb') as output:
        output.write(_canonical(value) + b'\n')
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _run(code, home, data, arguments):
    env = {**os.environ, 'HERMES_HOME': str(home), 'LLMWIKI_SETTINGS': str(data / 'settings.json')}
    env.pop('LLMWIKI_AUDIT_DIR', None)
    reply = subprocess.run([sys.executable, '-B', str(code / 'install.py'), *arguments],
        env=env, cwd=home, capture_output=True, text=True, encoding='utf-8', timeout=90)
    try:
        payload = json.loads(reply.stdout)
    except ValueError as exc:
        raise LifecycleRefused('Engine installer returned an unsupported response') from exc
    if reply.returncode != 0 or not isinstance(payload, dict):
        reason = 'Engine installer refused the selected plan: ' + str(payload.get('reason', 'unavailable'))
        raise (LifecyclePlanStale if payload.get('state') == 'stale' else LifecycleRefused)(reason)
    return payload


class LifecyclePlanStale(LifecycleRefused):
    """The engine refused before journaling anything: the preview is stale, not half-applied."""


def _preview(record):
    plan = record['plan']
    adopted = plan.get('legacy_adoptions') or {}
    refresh = plan.get('job_refresh') or {}
    existing = {job['id'] for job in plan.get('existing_jobs') or []}
    mapped = plan['settings'].get('jobs') or {}

    def disposition(role):
        if role in adopted:
            return 'adopt_paused' if plan['job_definitions'][role]['kind'] == 'agent' else 'adopt_existing'
        if role in refresh:
            return 'refresh_' + refresh[role]['field']
        return 'keep_existing' if mapped.get(role) in existing else 'create_paused'
    return {'ok': True, 'state': record['state'], 'install_id': record['install_id'],
        'plan_digest': plan['digest'], 'revision': record['manifest']['revision'],
        'project_root': plan['settings']['project_root'], 'project_id': plan['project_id'],
        'requested_project_root': record['requested_project_root'],
        'engine_dir': plan['engine_dir'], 'audit_dir': plan['audit_dir'],
        'jobs': [{'role': role, 'name': job['name'],
            'schedule': (plan['settings'].get('schedule') or {}).get(role) or job['default_schedule'],
            'disposition': disposition(role)}
            for role, job in sorted(plan['job_definitions'].items())],
        'activation': ('Adopted script jobs keep their schedule and on/off state and run the new engine code '
            'from their next scheduled run. An adopted drafting job is paused until you turn it on. ' if adopted else '')
            + 'New jobs remain paused. Content-owner authority is not configured by installation.'}


def _release_hashes(code):
    files = {}
    for path in Path(code).rglob('*'):
        relative = path.relative_to(code).as_posix()
        safe = confined(code, relative)
        if safe.is_file():
            files[relative] = hashlib.sha256(safe.read_bytes()).hexdigest()
    return files


def _readback(record):
    plan = record['plan']
    home, code, data = map(Path, (plan['hermes_home'], plan['engine_dir'], plan['audit_dir']))
    if json.loads(confined(home, 'state/wiki-automation/location.json').read_bytes()) != plan['location']:
        raise LifecycleRefused('Active location differs from its verified installation plan')
    if _release_hashes(code) != record.get('release_hashes'):
        raise LifecycleRefused('Installed code release is dirty or lacks verified file identity')
    settings = confined(data, 'settings.json')
    for name, content in plan['launcher_payloads'].items():
        if confined(home, 'scripts/' + name).read_bytes() != bytes.fromhex(content):
            raise LifecycleRefused('Installed launcher changed; existing bytes were preserved')
    env = {**os.environ, 'HERMES_HOME': str(home), 'LLMWIKI_SETTINGS': str(settings)}
    env.pop('LLMWIKI_AUDIT_DIR', None)
    checked = subprocess.run([sys.executable, '-B', str(confined(home, 'scripts/palantir_wiki_watchdog.py')), '--launcher-check'],
        capture_output=True, text=True, encoding='utf-8', timeout=30, cwd=home, env=env)
    selected = json.loads(checked.stdout)
    if (checked.returncode or Path(selected['audit_dir']).resolve() != data.resolve()
            or selected['project_id'] != plan['project_id']
            or Path(selected['project_root']).resolve() != Path(plan['settings']['project_root']).resolve()):
        raise LifecycleRefused('Installed launcher did not select the approved data and project')
    inspect = (
        'import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
        'import install; p=json.loads(sys.stdin.read()); home=Path(p["hermes_home"]); '
        'cfg=json.loads(Path(sys.argv[2]).read_bytes()); '
        'rows=install.existing_job_snapshot(home)["jobs"]; '
        'jobs=[next((job for job in rows if job["id"]==(cfg.get("jobs") or {}).get(role)),None) '
        'for role in p["job_definitions"]];\n'
        'for role,job in zip(p["job_definitions"],jobs): install.verify_job_role(job,role,p);\n'
        'print(json.dumps({"state":"installed_with_existing_jobs" if any(job.get("enabled",True) for job in jobs) else "installed_paused"}));\n')
    verified = subprocess.run([sys.executable, '-B', '-c', inspect, str(code), str(settings)],
        input=json.dumps(plan), capture_output=True, text=True, encoding='utf-8', timeout=30, cwd=home, env=env)
    if verified.returncode:
        raise LifecycleRefused('Owned native jobs did not pass engine readback; no repair was attempted')
    return json.loads(verified.stdout)['state']


@serialized
def prepare_install(home, package, manifest, project_root, *, principal, administrator=None):
    home = Path(home).resolve()
    if not home.is_dir() or not isinstance(principal, str) or not principal:
        raise LifecycleRefused('Captured application session and existing profile home are required')
    code = stage_release(home, package, manifest)
    location = confined(home, 'state/wiki-automation/location.json')
    data = confined(home, 'state/wiki-automation/data')
    if location.exists():
        previous = json.loads(location.read_bytes())
        if not isinstance(previous, dict) or type(previous.get('schema', 1)) is not int or previous.get('schema', 1) not in (1, 2):
            raise LifecycleRefused('Existing engine location is unsupported; it was preserved')
        selected = previous.get('audit_dir')
        if not isinstance(selected, str) or not Path(selected).is_absolute() or not Path(selected).is_dir():
            raise LifecycleRefused('Retained mutable data root is invalid or missing')
        data = Path(selected)
    plan = _run(code, home, data, ['--plan-json', '--data-root', str(data),
        '--hermes-home', str(home), '--project-root', str(project_root), '--no-plugin'])
    record = {'schema': 1, 'home': str(home), 'principal': principal, 'original_administrator': administrator, 'manifest': manifest, 'plan': plan,
        'requested_project_root': str(project_root), 'release_hashes': _release_hashes(code)}
    install_id = hashlib.sha256(_canonical(record)).hexdigest()
    record.update(install_id=install_id, state='prepared')
    target = confined(home, 'state/wiki-automation/installations/' + install_id + '.json')
    if target.exists():
        saved = json.loads(target.read_bytes())
        if any(saved.get(key) != record[key] for key in ('home', 'principal', 'original_administrator', 'manifest', 'plan', 'install_id', 'requested_project_root', 'release_hashes')):
            raise LifecycleRefused('Saved installation identity disagreed')
        record = saved
    else:
        _save(target.with_suffix('.plan.json'), plan)
        _save(target, record)
    return _preview(record)


@serialized
def apply_install(home, package, manifest, install_id, plan_digest, *, principal):
    home = Path(home).resolve()
    if not isinstance(install_id, str) or not re.fullmatch('[0-9a-f]{64}', install_id):
        raise LifecycleRefused('Exact prepared installation identity is required')
    target = confined(home, 'state/wiki-automation/installations/' + install_id + '.json')
    record = json.loads(target.read_bytes())
    if (record.get('home') != str(home) or record.get('principal') != principal
            or record.get('manifest') != manifest or record['plan']['digest'] != plan_digest):
        raise LifecycleRefused('Installation session, profile, release or exact plan changed')
    code = stage_release(home, package, manifest)
    data = Path(record['plan']['audit_dir'])
    plan_file = target.with_suffix('.plan.json')
    if json.loads(plan_file.read_bytes()) != record['plan']:
        raise LifecycleRefused('Stored engine plan changed')
    return _execute_install(target, record, code, home, data, plan_file, plan_digest)


def _execute_install(target, record, code, home, data, plan_file, plan_digest, *, recovery_state=None):
    install_id, manifest = record['install_id'], record['manifest']
    record['approved'] = True
    record['state'] = 'applying'
    _save(target, record)
    _checkpoint('applying_recorded')
    try:
        arguments = ['--apply-plan', str(plan_file), '--expected-digest', plan_digest]
        if recovery_state is not None:
            arguments.extend(['--expected-recovery-state', recovery_state])
        result = _run(code, home, data, arguments)
        _checkpoint('engine_applied')
        if result.get('ok') is not True or result.get('state') != 'location_recorded':
            raise LifecycleRefused('Engine installation projections are not verified')
        if recovery_state is not None and _recovery_facts(record, code, plan_file)['state'] != 'applied':
            raise LifecycleRefused('Native recovery readback did not verify the original applied operation')
        state = _readback(record)
        _checkpoint('launcher_verified')
        record['state'] = state
        record['result'] = {'ok': True, 'state': record['state'], 'install_id': install_id,
            'revision': manifest['revision'], 'activation_required': True}
        _save(target, record)
        _checkpoint('installed_recorded')
        return record['result']
    except (OSError, ValueError, LifecycleRefused, subprocess.SubprocessError) as exc:
        # A stale preview was refused before the engine journaled anything: nothing to recover.
        stale = isinstance(exc, LifecyclePlanStale) and recovery_state is None
        record['state'] = 'stale' if stale else 'recovery_required'
        _save(target, record)
        raise


def _recovery_original(home, package, manifest, install_id, administrator):
    if not isinstance(install_id, str) or not re.fullmatch('[0-9a-f]{64}', install_id):
        raise LifecycleRefused('Exact original installation identity is required')
    target = confined(home, 'state/wiki-automation/installations/' + install_id + '.json')
    record = json.loads(target.read_bytes())
    if (record.get('approved') is not True or record.get('state') not in ('applying', 'recovery_required')
            or not isinstance(administrator, str) or not re.fullmatch('[0-9a-f]{64}', administrator)
            or record.get('original_administrator') != administrator
            or record.get('home') != str(home) or record.get('install_id') != install_id
            or record.get('manifest') != manifest or record['plan']['hermes_home'] != str(home)):
        raise LifecycleRefused('Recovery requires original approval, same verified administrator, profile and release')
    identity = {key: record[key] for key in ('schema', 'home', 'principal', 'original_administrator',
        'manifest', 'plan', 'requested_project_root', 'release_hashes')}
    if hashlib.sha256(_canonical(identity)).hexdigest() != install_id:
        raise LifecycleRefused('Original immutable installation identity changed; adoption refused')
    plan_file = confined(target.parent, install_id + '.plan.json')
    if json.loads(plan_file.read_bytes()) != record['plan']:
        raise LifecycleRefused('Original immutable installation plan changed')
    code = confined(home, 'state/wiki-automation/releases/' + manifest['revision'])
    if (str(code) != record['plan']['engine_dir'] or not code.is_dir()
            or _release_hashes(code) != record.get('release_hashes')
            or release_digest(read_release_tree(package, manifest)) != manifest['sha256']):
        raise LifecycleRefused('Original pinned installation release changed or is unavailable')
    return target, record, code, plan_file


def _recovery_facts(record, code, plan_file):
    facts = _run(code, Path(record['home']), Path(record['plan']['audit_dir']),
        ['--validate-recovery-plan', str(plan_file), '--expected-digest', record['plan']['digest']])
    if (facts.get('ok') is not True or not isinstance(facts.get('current_state_digest'), str)
            or not re.fullmatch('[0-9a-f]{64}', facts['current_state_digest'])
            or facts.get('state') not in ('unstarted', 'collected', 'prepared', 'applying', 'recovery_required', 'applied')):
        raise LifecycleRefused('Pinned engine lacks supported read-only recovery validation')
    return facts


@serialized
def prepare_recovery(home, package, manifest, install_id, *, principal, administrator):
    confined(home, 'state/wiki-automation')
    home = Path(home).resolve()
    target, record, code, plan_file = _recovery_original(home, package, manifest, install_id, administrator)
    facts = _recovery_facts(record, code, plan_file)
    review_id = secrets.token_hex(32)
    review = {'schema': 1, 'state': 'prepared', 'home': str(home), 'install_id': install_id,
        'principal': principal, 'administrator': administrator, 'plan_digest': record['plan']['digest'],
        'original_record_digest': hashlib.sha256(_canonical(record)).hexdigest(),
        'current_state_digest': facts['current_state_digest'], 'review_expires_at': time.time() + 300,
        'recovery_review_id': review_id}
    review_digest = hashlib.sha256(_canonical(review)).hexdigest()
    review['recovery_review_digest'] = review_digest
    _save(confined(home, 'state/wiki-automation/recovery-reviews/' + review_id + '.json'), review)
    return {**_preview(record), 'state': 'recovery_prepared', 'recovery_review_id': review_id,
        'recovery_review_digest': review_digest, 'review_expires_at': review['review_expires_at'],
        'operation_state': record['state'], 'native_operation_state': facts['state']}


@serialized
def apply_recovery(home, package, manifest, install_id, plan_digest, review_id, review_digest, *, principal, administrator):
    confined(home, 'state/wiki-automation')
    home = Path(home).resolve()
    if any(not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value)
            for value in (install_id, plan_digest, review_id, review_digest)):
        raise LifecycleRefused('Exact original plan and fresh recovery review are required')
    review_path = confined(home, 'state/wiki-automation/recovery-reviews/' + review_id + '.json')
    review = json.loads(review_path.read_bytes())
    unsigned = {key: value for key, value in review.items() if key != 'recovery_review_digest'}
    if (review.get('state') != 'prepared' or review.get('home') != str(home)
            or review.get('install_id') != install_id or review.get('plan_digest') != plan_digest
            or review.get('recovery_review_id') != review_id or review.get('recovery_review_digest') != review_digest
            or hashlib.sha256(_canonical(unsigned)).hexdigest() != review_digest
            or review.get('principal') != principal or review.get('administrator') != administrator
            or type(review.get('review_expires_at')) not in (int, float) or time.time() >= review['review_expires_at']):
        raise LifecycleRefused('Recovery review expired, was consumed, or its application session changed')
    target, record, code, plan_file = _recovery_original(home, package, manifest, install_id, administrator)
    if (record['plan']['digest'] != plan_digest
            or hashlib.sha256(_canonical(record)).hexdigest() != review.get('original_record_digest')
            or _recovery_facts(record, code, plan_file)['current_state_digest'] != review.get('current_state_digest')):
        raise LifecycleRefused('Original installation or current native state changed after recovery review')
    review['state'] = 'confirmed'
    _save(review_path, review)
    return _execute_install(target, record, code, home, Path(record['plan']['audit_dir']), plan_file,
        plan_digest, recovery_state=review['current_state_digest'])


def lifecycle_status(home, manifest):
    home = Path(home)
    root = confined(home, 'state/wiki-automation/installations')
    home = home.resolve()
    paths = [path for path in root.glob('*.json')
        if not path.name.endswith('.plan.json')] if root.exists() else []
    paths.sort(key=lambda path: path.lstat().st_mtime_ns, reverse=True)
    records, unreadable = [], False
    for path in paths:
        try:
            path = confined(root, path.name)
            record = json.loads(path.read_bytes())
            if (not isinstance(record, dict) or record.get('install_id') != path.stem
                    or not re.fullmatch('[0-9a-f]{64}', record['install_id'])
                    or not re.fullmatch('[0-9a-f]{64}', record['plan']['digest'])
                    or not isinstance(record.get('state'), str)):
                raise ValueError('Unsupported installation record')
            records.append(record)
        except (OSError, ValueError, KeyError, TypeError, LifecycleRefused):
            unreadable = True
    latest = next((record for record in records if record['state'] in ('applying', 'recovery_required')),
        records[0] if records else None)
    unfinished = latest and latest['state'] in ('applying', 'recovery_required')
    if unreadable and not unfinished:
        raise LifecycleRefused('Installation records are unreadable; existing data was preserved')
    if unfinished:
        # Discover the original operation independently of active projections.
        result = {'ok': True, 'state': latest['state'], 'selected_revision': manifest['revision'],
            'current_revision': None, 'active_state': None, 'active_verification': 'unverified',
            'operation_state': latest['state'], 'install_id': latest['install_id'],
            'plan_digest': latest['plan']['digest']}
        try:
            location = confined(home, 'state/wiki-automation/location.json')
            if location.exists() and json.loads(location.read_bytes()) == latest['plan']['location']:
                result['current_revision'] = latest['manifest']['revision']
            code = Path(latest['plan']['engine_dir'])
            plan_file = confined(root, latest['install_id'] + '.plan.json')
            if (_release_hashes(code) != latest.get('release_hashes')
                    or json.loads(plan_file.read_bytes()) != latest['plan']):
                raise LifecycleRefused('Original installation code or plan changed; no readback code was executed')
            facts = _recovery_facts(latest, code, plan_file)
            result['read_only_diagnostic'] = {'ok': True, 'state': facts['state'],
                'reason': 'Native original operation inspected; active installation health remains unverified'}
        except (OSError, ValueError, KeyError, TypeError, LifecycleRefused, subprocess.SubprocessError) as exc:
            reason = str(exc)[:240] if isinstance(exc, LifecycleRefused) else 'Installation projections are unreadable; existing data was preserved'
            result['read_only_diagnostic'] = {'ok': False, 'state': 'refused', 'reason': reason}
        return result
    location = confined(home, 'state/wiki-automation/location.json')
    active, active_state = None, None
    if location.exists():
        selected = json.loads(location.read_bytes())
        if not isinstance(selected, dict):
            raise LifecycleRefused('Selected location is unsupported; existing data was preserved')
        active = next((record for record in records if record['plan']['location'] == selected), None)
        if active is None:
            # A pre-panel or unrecorded engine: report it honestly; only an exact approved plan adopts it,
            # and the engine refuses at preview when it cannot.
            result = {'ok': True, 'state': 'existing_unverified', 'selected_revision': manifest['revision'],
                'current_revision': None, 'active_state': None, 'active_verification': 'unverified',
                'operation_state': latest['state'] if latest else None}
            if latest:
                result.update(install_id=latest['install_id'], plan_digest=latest['plan']['digest'])
            return result
        if not unfinished:
            active_state = _readback(active)
    state = active_state or (latest['state'] if latest and latest['state'] != 'stale' else 'missing')
    if latest and latest['state'] in ('applying', 'recovery_required'):
        state = latest['state']
    result = {'ok': True, 'state': state, 'selected_revision': manifest['revision'],
        'current_revision': active['manifest']['revision'] if active else None,
        'active_state': active_state, 'operation_state': latest['state'] if latest else None}
    if latest:
        result.update(install_id=latest['install_id'], plan_digest=latest['plan']['digest'])
    return result


def installation_principal(request):
    from fastapi import HTTPException
    from hermes_cli.web_server import _require_token, _SESSION_TOKEN
    from hermes_cli.config import load_config_readonly
    from hermes_constants import get_hermes_home
    from cron.execution_identity import current_cron_execution
    if current_cron_execution() is not None or getattr(request.state, 'token_authenticated', False):
        raise HTTPException(status_code=403, detail='Service and cron callers cannot confirm installation')
    try:
        confined(get_hermes_home(), 'state/wiki-automation')
    except LifecycleRefused as exc:
        raise HTTPException(status_code=409, detail='Selected raw profile path is linked or unsupported; no state was inspected') from exc
    _require_token(request)
    if (load_config_readonly().get('plugins') or {}).get('isolation') == 'host':
        raise HTTPException(status_code=403, detail='Installation session bridge is unsupported in host isolation')
    if getattr(request.app.state, 'auth_required', False):
        session = request.state.session
        identity = ['interactive_installation', _SESSION_TOKEN, session.provider, session.user_id, session.org_id,
            hashlib.sha256(session.access_token.encode()).hexdigest()]
    else:
        identity = ['local_application_installation', _SESSION_TOKEN]
    return hashlib.sha256(_canonical([str(get_hermes_home().resolve()), identity])).hexdigest()


def installation_administrator(request):
    from hermes_constants import get_hermes_home
    installation_principal(request)
    home = get_hermes_home()
    confined(home, 'state/wiki-automation')
    if getattr(request.app.state, 'auth_required', False):
        session = request.state.session
        if not all(isinstance(value, str) and value for value in (session.provider, session.user_id)):
            raise LifecycleRefused('Verified stable interactive administrator is required')
        identity = ['verified_administrator', session.provider, session.user_id, session.org_id]
    else:
        identity = ['local_application_administrator']
    return hashlib.sha256(_canonical([str(home.resolve()), identity])).hexdigest()


def make_router(package_loader, manifest_loader):
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import JSONResponse
    from hermes_constants import get_hermes_home
    router = APIRouter()

    def body(value, fields):
        if not isinstance(value, dict) or set(value) != fields:
            raise HTTPException(status_code=400, detail='Unexpected or missing installation fields')
        return value

    def refused(exc):
        reason = str(exc) if isinstance(exc, LifecycleRefused) else 'Installation state is unreadable; existing data was preserved'
        return JSONResponse(status_code=409, content={'ok': False, 'state': 'refused', 'reason': reason})

    @router.get('/status')
    def status(request: Request):
        installation_principal(request)
        home = get_hermes_home().resolve()
        try:
            return lifecycle_status(home, manifest_loader())
        except (OSError, ValueError, LifecycleRefused) as exc:
            return refused(exc)

    @router.post('/prepare')
    def prepare(request: Request, payload: dict):
        principal = installation_principal(request)
        home = get_hermes_home().resolve()
        payload = body(payload, {'project_root'})
        root = payload['project_root']
        if not isinstance(root, str) or not root or len(root) > 4096 or not Path(root).is_absolute():
            raise HTTPException(status_code=400, detail='Select an absolute existing project root')
        try:
            return prepare_install(home, package_loader(), manifest_loader(), root, principal=principal,
                administrator=installation_administrator(request))
        except (OSError, ValueError, LifecycleRefused, subprocess.SubprocessError) as exc:
            return refused(exc)

    @router.post('/apply')
    def apply(request: Request, payload: dict):
        principal = installation_principal(request)
        home = get_hermes_home().resolve()
        payload = body(payload, {'install_id', 'plan_digest', 'confirm'})
        if payload['confirm'] is not True or any(not isinstance(payload[key], str) or not re.fullmatch('[0-9a-f]{64}', payload[key]) for key in ('install_id', 'plan_digest')):
            raise HTTPException(status_code=400, detail='Exact prepared plan and explicit confirmation are required')
        try:
            return apply_install(home, package_loader(), manifest_loader(), payload['install_id'], payload['plan_digest'], principal=principal)
        except (OSError, ValueError, LifecycleRefused, subprocess.SubprocessError) as exc:
            return refused(exc)

    @router.post('/recovery/prepare')
    def recovery_prepare(request: Request, payload: dict):
        principal = installation_principal(request)
        payload = body(payload, {'install_id'})
        if not isinstance(payload['install_id'], str) or not re.fullmatch('[0-9a-f]{64}', payload['install_id']):
            raise HTTPException(status_code=400, detail='Exact original installation identity is required')
        try:
            return prepare_recovery(get_hermes_home(), package_loader(), manifest_loader(), payload['install_id'],
                principal=principal, administrator=installation_administrator(request))
        except (OSError, ValueError, KeyError, TypeError, LifecycleRefused, subprocess.SubprocessError) as exc:
            return refused(exc)

    @router.post('/recovery/apply')
    def recovery_apply(request: Request, payload: dict):
        principal = installation_principal(request)
        fields = {'install_id', 'plan_digest', 'recovery_review_id', 'recovery_review_digest', 'confirm'}
        payload = body(payload, fields)
        if payload['confirm'] is not True or any(not isinstance(payload[key], str) or not re.fullmatch('[0-9a-f]{64}', payload[key]) for key in fields - {'confirm'}):
            raise HTTPException(status_code=400, detail='Exact recovery review and explicit confirmation are required')
        try:
            return apply_recovery(get_hermes_home(), package_loader(), manifest_loader(), payload['install_id'],
                payload['plan_digest'], payload['recovery_review_id'], payload['recovery_review_digest'],
                principal=principal, administrator=installation_administrator(request))
        except (OSError, ValueError, KeyError, TypeError, LifecycleRefused, subprocess.SubprocessError) as exc:
            return refused(exc)

    return router

"""Authenticated, probe-only loopback channel owned by a loaded plugin instance.

This is not a standalone daemon, approval transport, or a same-OS-user sandbox. The descriptor
contains an IPC secret and must never enter draft inputs, UI responses, or model context.
"""
import contextvars
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import stat
import struct
import tempfile
import threading
import time


class ProbeRefused(RuntimeError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _safe(home, path):
    home, path = Path(home), Path(path)
    path.relative_to(home)
    for item in (path, *path.parents):
        reparse = False
        try:
            reparse = bool(getattr(item.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))
        except FileNotFoundError:
            pass
        if reparse or item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise ProbeRefused('Linked runtime descriptor path')
        if item.is_file() and item.stat().st_nlink != 1:
            raise ProbeRefused('Linked runtime descriptor file')
        if item == home:
            break
    return path


def _path(home, pid):
    if type(pid) is not int or pid <= 0:
        raise ProbeRefused('Exact peer PID is required')
    return _safe(home, Path(home) / 'cache/wiki-automation/runtime' / f'{pid}.json')


def _sign(body, key):
    return {'body': body, 'signature': hmac.new(key, _canonical(body), hashlib.sha256).hexdigest()}


def _verify(envelope, key):
    if not isinstance(envelope, dict) or set(envelope) != {'body', 'signature'} or not isinstance(envelope['body'], dict):
        raise ProbeRefused('Invalid probe frame')
    signature = envelope['signature']
    if not isinstance(signature, str) or len(signature) != 64 or not all(ch in '0123456789abcdef' for ch in signature):
        raise ProbeRefused('Invalid probe signature')
    expected = _sign(envelope['body'], key)['signature']
    if not hmac.compare_digest(signature, expected):
        raise ProbeRefused('Unauthenticated probe frame')
    return envelope['body']


def _receive(connection):
    def exact(size):
        data = bytearray()
        while len(data) < size:
            part = connection.recv(size - len(data))
            if not part:
                raise ProbeRefused('Incomplete probe frame')
            data.extend(part)
        return bytes(data)
    size = struct.unpack('!I', exact(4))[0]
    if not 0 < size <= 8192:
        raise ProbeRefused('Probe frame is oversized')
    return json.loads(exact(size))


def _send(connection, envelope):
    data = _canonical(envelope)
    if len(data) > 8192:
        raise ProbeRefused('Probe frame is oversized')
    connection.sendall(struct.pack('!I', len(data)) + data)


class ProbeChannel:
    def __init__(self, home, ctx, prove, ready):
        self.home, self.ctx, self.prove, self.ready = Path(home).resolve(), ctx, prove, ready
        self.path = _path(self.home, os.getpid())
        self.key = secrets.token_bytes(32)
        self.channel_id = secrets.token_hex(32)
        self.stop = threading.Event()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(4)
        self.listener.settimeout(0.1)
        descriptor = {'schema_version': 1, 'pid': os.getpid(), 'home': str(self.home),
                      'port': self.listener.getsockname()[1], 'channel_id': self.channel_id,
                      'key': self.key.hex()}
        self.saved = _canonical(descriptor)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            _safe(self.home, self.path)
            fd, temporary = tempfile.mkstemp(prefix='.descriptor-', dir=self.path.parent)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(self.saved)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            copied = contextvars.copy_context()
            self.thread = threading.Thread(target=lambda: copied.run(self._serve), name='wiki-runtime-probe', daemon=True)
            self.thread.start()
        except BaseException:
            self.listener.close()
            raise

    def _serve(self):
        used = {}
        while not self.stop.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(0.5)
                try:
                    request = _verify(_receive(connection), self.key)
                    if set(request) != {'operation', 'challenge', 'expires_at'} or request['operation'] != 'probe':
                        raise ProbeRefused('The runtime channel accepts only a guard probe')
                    challenge, expires = request['challenge'], request['expires_at']
                    if not isinstance(challenge, str) or len(challenge) != 64 or not all(ch in '0123456789abcdef' for ch in challenge):
                        raise ProbeRefused('Exact probe nonce is required')
                    if type(expires) not in (int, float) or not time.time() < expires <= time.time() + 5:
                        raise ProbeRefused('Probe request expired or invalid')
                    used = {nonce: deadline for nonce, deadline in used.items() if deadline > time.time()}
                    if challenge in used or len(used) >= 128:
                        raise ProbeRefused('Probe nonce reused or channel capacity exceeded')
                    used[challenge] = expires + 2
                    try:
                        if not self.ready():
                            raise ProbeRefused('Loaded peer guard or configured agent job is not ready')
                        proof = self.prove(self.ctx, challenge)
                    except ProbeRefused:
                        raise
                    except Exception as exc:
                        logging.getLogger(__name__).warning('Native runtime probe callback failed (%s); readiness denied', type(exc).__name__)
                        continue
                    _send(connection, _sign({'proof': proof, 'channel_id': self.channel_id, 'challenge': challenge}, self.key))
                except (OSError, ValueError, TypeError, KeyError, ProbeRefused):
                    continue

    def close(self):
        self.stop.set()
        self.listener.close()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise ProbeRefused('Runtime probe listener did not stop')
        try:
            _safe(self.home, self.path)
            if self.path.read_bytes() == self.saved:
                self.path.unlink()
        except FileNotFoundError:
            pass


def register(ctx):
    if ctx.get_config('runtime_probe_enabled', False) is not True:
        return None
    from hermes_constants import get_hermes_home
    from .runtime_probe import probe
    from .draft_security import approval_runtime_ready
    if approval_runtime_ready():
        # Initialize the actual dispatcher before exposing the listener; do not cache this proof.
        proof = probe(ctx, secrets.token_hex(32))
        if proof.get('veto_exercised') is not True or proof.get('handler_reached') is not False:
            raise ProbeRefused('Native dispatcher initialization did not exercise the veto')
    channel = ProbeChannel(get_hermes_home(), ctx, probe, approval_runtime_ready)
    try:
        cleanup = ctx.on_unload(channel.close)
        if cleanup is None:
            raise ProbeRefused('Host did not accept ownership of the runtime listener')
    except BaseException:
        channel.close()
        raise
    return channel


def query_peer(home, pid, expected_hash, job_id, *, timeout=1, challenge=None, expected_engine=None):
    home = Path(home).resolve()
    try:
        descriptor = json.loads(_path(home, pid).read_bytes())
        if descriptor.get('schema_version') != 1 or descriptor.get('pid') != pid or descriptor.get('home') != str(home):
            raise ProbeRefused('Runtime descriptor belongs to another process or profile')
        port = descriptor['port']
        if type(port) is not int or not 0 < port < 65536:
            raise ProbeRefused('Invalid local runtime port')
        key = bytes.fromhex(descriptor['key'])
        if len(key) != 32:
            raise ProbeRefused('Invalid runtime authentication material')
        challenge = challenge or secrets.token_hex(32)
        request = {'operation': 'probe', 'challenge': challenge, 'expires_at': time.time() + 3}
        with socket.create_connection(('127.0.0.1', port), timeout=timeout) as connection:
            _send(connection, _sign(request, key))
            response = _verify(_receive(connection), key)
        if time.time() >= request['expires_at']:
            raise ProbeRefused('Runtime proof arrived after the challenge deadline')
        if response.get('challenge') != challenge or response.get('channel_id') != descriptor['channel_id']:
            raise ProbeRefused('Runtime proof is stale or belongs to another channel')
        proof = response['proof']
        if not isinstance(proof, dict) or type(proof.get('schema_version')) is not int or proof['schema_version'] != 1 or type(proof.get('pid')) is not int:
            raise ProbeRefused('Unsupported runtime proof schema or process identity')
        if proof.get('pid') != pid or proof.get('home') != str(home) or proof.get('job_id') != job_id:
            raise ProbeRefused('Runtime proof belongs to another process, profile or job')
        if proof.get('challenge') != challenge or proof.get('loaded_code_hash') != expected_hash or not proof.get('incarnation'):
            raise ProbeRefused('Runtime proof has a different nonce or loaded release')
        if expected_engine is not None and proof.get('engine_identity') != expected_engine:
            raise ProbeRefused('Runtime peer selected different engine code or settings')
        if proof.get('veto_exercised') is not True or proof.get('handler_reached') is not False:
            raise ProbeRefused('Native peer veto was not exercised')
        return proof
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise ProbeRefused('Peer runtime is unavailable or unauthenticated') from exc

"""Independent process used for lock and abrupt-interruption tests."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candidate_apply
from candidate_apply import operation_lock, ApplyRefused
from workflow_store import WorkflowStore

try:
    if sys.argv[1] in ('owner-held-write', 'owner-held-partial'):
        target = Path(sys.argv[2])
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            create = kernel.CreateFileW
            create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                               wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
            create.restype = wintypes.HANDLE
            handle = create(str(target), 0x40000000, 7, None, 3, 0, None)
            if handle == wintypes.HANDLE(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
        else:
            fd = os.open(target, os.O_WRONLY)
        with os.fdopen(fd, 'wb') as output:
            print('OWNER_OPEN', flush=True)
            sys.stdin.readline()
            content = bytes.fromhex(sys.argv[3])
            if sys.argv[1] == 'owner-held-partial':
                output.write(content[:len(content) // 2])
                output.truncate()
                output.flush()
                os.fsync(output.fileno())
                print('OWNER_PARTIAL', flush=True)
                sys.stdin.readline()
                output.seek(0)
            output.write(content)
            output.truncate()
            output.flush()
            os.fsync(output.fileno())
        print('OWNER_WROTE', flush=True)
    elif sys.argv[1] in ('owner-write', 'owner-replace'):
        target = Path(sys.argv[2])
        content = bytes.fromhex(sys.argv[3])
        if sys.argv[1] == 'owner-write':
            target.write_bytes(content)
        else:
            import tempfile
            fd, temporary = tempfile.mkstemp(dir=target.parent)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(content)
            os.replace(temporary, target)
        print('OWNER_WROTE', flush=True)
    elif sys.argv[1] in ('apply', 'attribution-death'):
        if sys.argv[1] == 'attribution-death':
            phase = sys.argv[3] if len(sys.argv) == 4 else 'before-publish'
            real_rename = candidate_apply._rename_no_replace
            real_atomic = candidate_apply._atomic
            real_fsync = os.fsync
            active = [None]
            def atomic(path, data, **kwargs):
                previous = active[0]
                if path.name == 'publication.bin' and 'evidence-attribution' in path.parts:
                    active[0] = path
                try:
                    return real_atomic(path, data, **kwargs)
                finally:
                    active[0] = previous
            def fsync(fd):
                if active[0] is not None and phase == 'before-fsync':
                    print(str(next(active[0].parent.glob('.publication.bin.*'))), flush=True)
                    os._exit(91)
                result = real_fsync(fd)
                if active[0] is not None and phase == 'after-fsync':
                    print(str(next(active[0].parent.glob('.publication.bin.*'))), flush=True)
                    os._exit(91)
                return result
            def rename(source, destination):
                source, destination = Path(source), Path(destination)
                manifest = source.name == 'manifest.json' or destination.name == 'manifest.json'
                if manifest and source.name == 'publication.bin' and phase == 'before-publish':
                    print(str(source), flush=True)
                    os._exit(91)
                if manifest and source.name == 'restoration.bin' and phase == 'before-restore':
                    print(str(source), flush=True)
                    os._exit(91)
                result = real_rename(source, destination)
                if manifest and ((source.name == 'restoration.bin' and phase == 'after-restore')
                                 or (destination.name == 'captured.bin' and phase == 'after-capture')
                                 or (source.name == 'publication.bin' and phase == 'after-publish')):
                    print(str(destination), flush=True)
                    os._exit(91)
                return result
            candidate_apply._atomic = atomic
            candidate_apply._rename_no_replace = rename
            os.fsync = fsync
        request = json.loads(Path(sys.argv[2]).read_bytes())
        count = [0]
        if len(sys.argv) == 4 and sys.argv[1] == 'apply':
            def interrupt(point):
                if count[0] == int(sys.argv[3]):
                    os._exit(91)
                count[0] += 1
            candidate_apply._checkpoint = interrupt
        with WorkflowStore(Path(request['inbox']).parent / 'workflow.sqlite') as store:
            prepared = store.db.execute("SELECT id FROM operations WHERE json_extract(identity, '$.type')='candidate'").fetchall()
            if len(sys.argv) == 3 and prepared:
                result = candidate_apply.reconcile_operation(Path(request['wiki']), Path(request['inbox']), prepared[0][0], store)
            else:
                result = candidate_apply.apply_candidate(Path(request['wiki']), Path(request['inbox']),
                    'run/draft', request['snapshot'], request['approval'], store)
        print(json.dumps(result))
    else:
        with operation_lock(Path(sys.argv[2]), timeout=0):
            if sys.argv[1] == 'hold-lock':
                print('LOCKED', flush=True)
                time.sleep(60)
except ApplyRefused as exc:
    print(exc)
    raise SystemExit(2)

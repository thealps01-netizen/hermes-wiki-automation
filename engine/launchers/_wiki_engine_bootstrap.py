"""Shared profile-scoped entry point; generated wrappers contain no engine business logic."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


def unlinked_path(value):
    """Check the original spelling, including ancestors, before any resolution or I/O."""
    path = Path(value).absolute()
    for component in [*reversed(path.parents), path]:
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(metadata.st_mode)
                or getattr(metadata, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
            raise ValueError('Linked path refused: ' + str(component))
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink > 1:
            raise ValueError('Hard-linked path refused: ' + str(component))
    return path


def cron_exit(code, alert):
    if code is None or code == 0 or (alert and code == 1):
        return 0
    return code if isinstance(code, int) else 2


def launch(implementation, args=None):
    args = list(sys.argv[1:] if args is None else args)
    alert = implementation in ('wiki_autocommit.py', 'wiki_ingest_watch.py')
    if '--launcher-selftest' in args:
        assert cron_exit(0, True) == 0 and cron_exit(1, True) == 0
        assert cron_exit(1, False) == 1 and cron_exit(2, True) == 2
        print('[launcher selftest] alert and real-failure exit contracts hold')
        return 0
    try:
        # Keep the raw profile identity: resolving scripts first can adopt an outside home.
        home = unlinked_path(__file__).parent.parent
        unlinked_path(sys.argv[0])
        executable = unlinked_path(sys.executable)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.py', implementation):
            raise ValueError('Invalid engine implementation name')
        location = unlinked_path(home / 'state/wiki-automation/location.json')
        record = json.loads(location.read_bytes())
        if not isinstance(record, dict):
            raise ValueError('Engine location must be an object')
        schema = record.get('schema', 1)
        if type(schema) is not int or schema not in (1, 2):
            raise ValueError('Unsupported engine location schema')
        roots = (record['engine_dir'] if schema == 2 else record['audit_dir'], record['audit_dir'])
        if any(not isinstance(root, str) or not Path(root).is_absolute() for root in roots):
            raise ValueError('Selected code and data roots must be absolute')
        code, data = map(unlinked_path, roots)
        if not code.is_dir() or not data.is_dir():
            raise ValueError('Selected code or data root is missing')
        settings = unlinked_path(data / 'settings.json')
        if '--launcher-check' in args:
            target, args = unlinked_path(code / 'wikiconfig.py'), ['show']
            alert = False
        else:
            target = unlinked_path(code / implementation)
        if not target.is_file():
            raise ValueError('Selected engine implementation is missing')
        env = {**os.environ, 'HERMES_HOME': str(home), 'LLMWIKI_SETTINGS': str(settings),
               'LLMWIKI_AUDIT_DIR': str(code)}
        result = subprocess.run([str(executable), '-B', str(target), *args], cwd=str(home), env=env)
        return cron_exit(result.returncode, alert)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'!! Engine launcher refused: {exc}')
        return 2

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat


class EnginePathError(ValueError):
    pass


def _checked_path(path):
    path = Path(path)
    absolute = path.absolute()
    for component in [*reversed(absolute.parents), absolute]:
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise EnginePathError('Engine path metadata is unreadable') from exc
        if (stat.S_ISLNK(metadata.st_mode)
                or getattr(metadata, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)):
            raise EnginePathError('Linked engine path refused')
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink > 1:
            raise EnginePathError('Hard-linked engine path refused')
    return path


@dataclass(frozen=True)
class EnginePaths:
    home: Path
    engine_dir: Path
    audit_dir: Path
    settings_path: Path

    def environment(self):
        return {**os.environ, 'HERMES_HOME': str(self.home),
                'LLMWIKI_SETTINGS': str(self.settings_path)}

    def code_identity(self):
        files = sorted(_checked_path(self.engine_dir).glob('*.py'), key=lambda path: path.name)
        if not files:
            return None
        hashes = {path.name: hashlib.sha256(_checked_path(path).read_bytes()).hexdigest() for path in files}
        digest = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return {'engine_dir': str(self.engine_dir), 'audit_dir': str(self.audit_dir),
                'settings_path': str(self.settings_path), 'code_hash': digest}


def resolve_engine_paths(home=None, *, default=None):
    if home is None:
        from hermes_constants import get_hermes_home
        home = get_hermes_home()
    home = _checked_path(home).resolve()
    selected = False
    override = os.environ.get('LLMWIKI_AUDIT_DIR')
    if override:
        code = data = _checked_path(override)
        if not code.is_dir():
            raise EnginePathError('Explicit engine code override is missing; no fallback is allowed')
    else:
        location = _checked_path(home / 'state/wiki-automation/location.json')
        try:
            record = json.loads(location.read_bytes())
        except FileNotFoundError:
            code = data = _checked_path(Path(default) if default is not None else Path.home() / '.llmwiki-audit')
        except (OSError, ValueError) as exc:
            raise EnginePathError('Selected engine location is unreadable; no fallback is allowed') from exc
        else:
            selected = True
            if not isinstance(record, dict):
                raise EnginePathError('Selected engine location must be an object')
            schema = record.get('schema', 1)
            if type(schema) is not int or schema not in (1, 2):
                raise EnginePathError('Unsupported engine location schema; no fallback is allowed')
            values = (record.get('engine_dir') if schema == 2 else record.get('audit_dir'), record.get('audit_dir'))
            if any(not isinstance(value, str) or not value or not Path(value).is_absolute() for value in values):
                raise EnginePathError('Selected engine location requires absolute code and data roots')
            code, data = map(_checked_path, values)
            if not code.is_dir() or not data.is_dir():
                raise EnginePathError('Selected engine code or data root is missing; no fallback is allowed')
    settings = os.environ.get('LLMWIKI_SETTINGS')
    settings_path = _checked_path(Path(settings) if settings else data / 'settings.json').resolve()
    if selected or settings or settings_path.exists():
        try:
            value = json.loads(settings_path.read_bytes())
        except (OSError, ValueError) as exc:
            raise EnginePathError('Selected engine settings are missing or unreadable; no fallback is allowed') from exc
        if not isinstance(value, dict):
            raise EnginePathError('Selected engine settings must be an object')
    return EnginePaths(home, code.resolve(), data.resolve(), settings_path)

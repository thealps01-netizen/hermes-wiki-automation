"""Write or check `engine-release.json` from the bundled `engine/` folder.

The manifest is generated, never hand-edited: run `python tools/engine_release.py` after any change under
`engine/`, and `python tools/engine_release.py --check` (CI and the unit suite do) to prove the committed
manifest names exactly the engine that ships. The digest comes from the panel's own installer code
(`dashboard/engine_lifecycle.py`), so the check and the install can never disagree on what "the engine" is.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
MANIFEST = PACKAGE / 'engine-release.json'
FIXED = {'schema': 2, 'artifact': 'engine', 'workflow_schema': {'min': 1, 'max': 1}, 'python_min': [3, 11]}


def _lifecycle():
    try:
        import fastapi  # noqa: F401  (the installer imports it; the digest code itself never uses it)
    except ImportError:  # CI's gate runner has no web stack: the routes are not exercised here
        sys.modules['fastapi'] = types.SimpleNamespace(Request=object)
    spec = importlib.util.spec_from_file_location('wa_engine_lifecycle', PACKAGE / 'dashboard/engine_lifecycle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected(package: Path = PACKAGE) -> dict:
    lifecycle = _lifecycle()
    digest = lifecycle.release_digest(lifecycle.read_release_tree(package, FIXED))
    return {**FIXED, 'revision': digest[:40], 'sha256': digest}


def render(manifest: dict) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode()


def main(argv: list) -> int:
    want = render(expected())
    if '--check' in argv:
        have = MANIFEST.read_bytes() if MANIFEST.exists() else b''
        if have.replace(b'\r\n', b'\n') != want:
            print('engine-release.json does not match engine/: run python tools/engine_release.py', file=sys.stderr)
            return 1
        print('engine-release.json matches engine/')
        return 0
    MANIFEST.write_bytes(want)
    print('wrote engine-release.json', json.loads(want)['revision'])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

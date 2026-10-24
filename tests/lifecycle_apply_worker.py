"""Kill the actual lifecycle process at a durable installation handoff."""
import importlib.util
import json
import os
from pathlib import Path
import sys

home, package = map(Path, sys.argv[1:3])
spec = importlib.util.spec_from_file_location('lifecycle_crash_worker', package / 'dashboard/engine_lifecycle.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def checkpoint(phase):
    if phase == sys.argv[5]:
        os._exit(91)

module._checkpoint = checkpoint
manifest = json.loads((package / 'engine-release.json').read_bytes())
module.apply_install(home, package, manifest, sys.argv[3], sys.argv[4], principal='owner-session')

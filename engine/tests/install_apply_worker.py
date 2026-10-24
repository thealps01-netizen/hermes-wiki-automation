"""Real abrupt-death fixture for engine-owned installation projection replay."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candidate_apply
import install

plan = json.loads(Path(sys.argv[1]).read_bytes())
point = sys.argv[2]
def stop(actual):
    if actual == point:
        os._exit(91)
candidate_apply._checkpoint = stop
install.apply_plan(plan, plan['digest'])
raise SystemExit('Requested installation checkpoint was not reached')

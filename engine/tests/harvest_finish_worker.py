"""Abrupt-process-death fixture for private native harvest completion."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candidate_apply
import wiki_session_harvest
from workflow_store import WorkflowStore

root = Path(sys.argv[1])
point = sys.argv[2]
def stop(actual):
    if actual == point:
        os._exit(91)
candidate_apply._checkpoint = stop
outcome = json.loads((root / 'outcome.json').read_bytes())
with WorkflowStore(root / 'workflow.sqlite') as store:
    wiki_session_harvest.finish_run(root, 'run-one', outcome, store)
raise SystemExit('Requested checkpoint was not reached')

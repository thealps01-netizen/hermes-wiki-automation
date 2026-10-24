"""Abruptly stop the disposable broker process at an application boundary."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candidate_apply
import owner_decisions

home = Path(sys.argv[1])
point = sys.argv[2] if len(sys.argv) > 2 else None
if point == 'after-confirm':
    original = owner_decisions.OwnerDecisions.confirm
    def interrupted_confirm(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(91)
    owner_decisions.OwnerDecisions.confirm = interrupted_confirm
elif point:
    def interrupt(name):
        if name == point:
            os._exit(91)
    candidate_apply._checkpoint = interrupt
raise SystemExit(owner_decisions.main(['confirm', '--home', str(home), '--settings', str(home / 'settings.json')]))

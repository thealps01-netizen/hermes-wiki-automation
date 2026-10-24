"""Subprocess fixture consumer; it is not an installed runtime command."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from owner_decisions import OwnerDecisions, DecisionRefused

if __name__ == '__main__':
    data, fixture, operation = sys.argv[1:]
    body = json.loads(Path(fixture).read_bytes())
    try:
        with OwnerDecisions(Path(data)) as store:
            result = store.consume(body['receipt'], body['snapshot'], operation)
        print(json.dumps(result))
    except DecisionRefused as exc:
        print(str(exc))
        raise SystemExit(2)

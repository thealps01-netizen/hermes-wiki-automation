"""Review and apply wiki source candidates prepared by the nightly session harvest.

WHY: the harvest drafts candidates; only the owner decides what enters the wiki, because a wrong
claim in raw/sources/ spreads into shared pages and an ingest costs model usage. This script is the
single writer from the inbox into the wiki. A panel, a chat agent or a terminal all call it, so the
rules below hold whatever surface the owner uses.

A CANDIDATE is a folder <audit>/inbox/<run>/candidates/<name>/ holding:
  candidate.json   {"kind": "new" | "update" | "retire", "target": "<raw/sources file name>",
                    "summary": "...", "why": "...", "evidence_ids": [...]}
  source.md        the full proposed source (new / update); absent for retire
  evidence/<id>/   evidence folders made with evidence_capture.py (optional)

  new     -> writes raw/sources/<target>; when that file exists, only a correction is possible: the file
             is the unchanged one an earlier approved draft wrote, and this draft was submitted after
             it (a corrected resubmission); it then replaces the file as an update would
  update  -> replaces raw/sources/<target> in place (same name, so the app treats it as an edit);
             refuses if the target is missing or the current file changed since the harvest ran
  retire  -> deletes raw/sources/<target>; the app then deletes the pages owned only by it

USAGE
  python wiki_candidates.py list [--json]              pending candidates, oldest run first
  python wiki_candidates.py show <run>/<name>          summary + diff against the current source
  python wiki_candidates.py approve <run>/<name> [--dry-run]
  python wiki_candidates.py reject <run>/<name> --reason "<why>"
  python wiki_candidates.py fetch-evidence <run>/<name> --expected-review-digest <digest>
                                                       download the public copies the candidate's
                                                       evidence_requests name (evidence_requests.py)

Approve copies evidence folders that are missing into raw/evidence/, refuses when a candidate brings
a DIFFERENT copy under an id that already exists (the old decision would silently keep the old copy),
refuses new or changed decisions that name a pinned version but have "Evidence: none" (nothing could
re-check them after an upgrade), checks the source against the house format (decision records, no
front matter, no [[wikilinks]]), then writes and re-derives every evidence folder's used_by from the
sources. It does not commit: the daily auto-commit does, once the app has finished ingesting.
Rejected candidates move to <audit>/inbox/rejected/ with the reason, so the harvest's hit rate can
be measured later.
"""
from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import io
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_store  # noqa: E402
import wikiconfig  # noqa: E402
from workflow_paths import PathRefused, checked_path, identifier

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")
KINDS = ("new", "update", "retire")


class Refused(Exception):
    pass


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def paths():
    cfg = wikiconfig.load()
    wiki = wikiconfig.project_root(cfg)
    audit = wikiconfig.audit_dir(cfg)
    return wiki, audit / "inbox"


def submitted(c: Path) -> tuple:
    """Submission order: the run folder name starts with the harvest's start time, and a candidate
    folder is written once when the drafting agent submits it."""
    return (c.parent.parent.name, (c / 'candidate.json').stat().st_mtime_ns, c.name)


def ref_of(c: Path) -> str:
    return f"{c.parent.parent.name}/{c.name}"


def correction_of(wiki: Path, inbox: Path, c: Path, meta: dict) -> str:
    """For a 'new' candidate whose target already exists: the ref of the earlier approved candidate
    whose file it corrects. Refused when it cannot be a correction, saying what to do instead."""
    target = wiki / 'raw' / 'sources' / meta['target']
    current = sha(target)
    writer = None
    for marker in sorted(inbox.glob('*/candidates/*/applied.json')):
        other = marker.parent
        if other == c or other.parent.parent.name == 'rejected':
            continue
        try:
            checked_path(inbox, marker.relative_to(inbox).as_posix())
            data = json.loads(marker.read_bytes())
        except (PathRefused, OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get('target') == meta['target'] and data.get('source_hash') == current:
            writer = other
    if writer is None:
        raise Refused(f"raw/sources/{meta['target']} already exists and is not the unchanged file an earlier "
                      "approved draft wrote, so this draft cannot be added; reject it, and the next harvest "
                      "proposes an update instead")
    if submitted(c) < submitted(writer):
        raise Refused(f"A newer draft of this source ({ref_of(writer)}) is already approved; this one is older, "
                      "reject it")
    source = c / 'source.md'
    if source.is_file() and sha(source) == current:
        raise Refused(f"This draft is identical to the source already approved from {ref_of(writer)}; "
                      "reject it as a duplicate")
    return ref_of(writer)


def pending(inbox: Path) -> list[Path]:
    out = []
    for run in sorted(p for p in inbox.iterdir() if p.is_dir() and p.name != "rejected") if inbox.exists() else []:
        for c in sorted((run / "candidates").glob("*")) if (run / "candidates").is_dir() else []:
            if (c / "candidate.json").exists() and not (c / "applied.json").exists():
                out.append(c)
    return out


def load_candidate(inbox: Path, ref: str) -> tuple[Path, dict]:
    parts = ref.split('/')
    try:
        if len(parts) != 2:
            raise PathRefused('Candidate reference requires run/name')
        c = checked_path(inbox, f'{identifier(parts[0])}/candidates/{identifier(parts[1])}')
        checked_path(inbox, f'{parts[0]}/candidates/{parts[1]}/candidate.json')
        for p in c.rglob('*'):
            checked_path(inbox, p.relative_to(inbox).as_posix())
    except (PathRefused, OSError) as exc:
        raise Refused(str(exc)) from exc
    if not (c / 'candidate.json').exists():
        raise Refused(f"candidate not found: {ref} (use <run>/<name> from `list`)")
    meta = json.loads((c / "candidate.json").read_text(encoding="utf-8"))
    if meta.get("kind") not in KINDS:
        raise Refused(f"unknown kind {meta.get('kind')!r}")
    if not NAME_RE.match(meta.get("target") or ""):
        raise Refused(f"target must be a raw/sources file name: {meta.get('target')!r}")
    return c, meta


def same_evidence(a: Path, b: Path) -> bool:
    """True when two evidence folders hold the same stored files (manifest aside): re-approving a
    candidate whose folder is already in the wiki is fine; a different copy under an old id is not."""
    def files(d: Path) -> dict[str, str]:
        return {p.relative_to(d).as_posix(): sha(p) for p in d.rglob("*")
                if p.is_file() and p.name != "manifest.json"}
    return files(a) == files(b)


def check_format(text: str) -> list[str]:
    problems = []
    if text.lstrip().startswith("---"):
        problems.append("has YAML front matter")
    if re.search(r"\[\[[^\]]+\]\]", re.sub(r"```.*?```|`[^`\n]*`", "", text, flags=re.S)):
        problems.append("contains [[wikilinks]]")
    if not re.search(r"^## Decisions", text, re.M):
        problems.append("no '## Decisions' section")
    if re.search(r"(?i)C:[/\\]+Users[/\\]|/c/Users/", text):
        problems.append("contains a machine-specific path")
    return problems


def cmd_list(inbox: Path, as_json: bool) -> int:
    rows = []
    waiting = pending(inbox)
    wiki = None
    for c in waiting:
        m = json.loads((c / "candidate.json").read_text(encoding="utf-8"))
        row = {"ref": ref_of(c), "kind": m.get("kind"), "target": m.get("target"), "summary": m.get("summary", "")}
        newer = [o for o in waiting if o != c and submitted(o) > submitted(c)
                 and json.loads((o / "candidate.json").read_text(encoding="utf-8")).get("target") == m.get("target")]
        if newer:
            row["superseded_by"] = ref_of(max(newer, key=submitted))
        if m.get("kind") == "new" and NAME_RE.match(m.get("target") or ""):
            wiki = wiki or wikiconfig.project_root(wikiconfig.load())
            if (wiki / "raw" / "sources" / m["target"]).is_file():
                try:
                    row["corrects"] = correction_of(wiki, inbox, c, m)
                except Refused as exc:
                    row["blocked"] = str(exc)
        rows.append(row)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print(f"{len(rows)} pending candidate(s)")
        for r in rows:
            print(f"- {r['ref']}  [{r['kind']}] {r['target']}\n    {r['summary']}")
    return 0


def validate_source_citations(text: str, ids) -> None:
    """Refuse unreviewed citation identities; never expand metadata authorization."""
    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
        raise Refused('Invalid evidence identifiers')
    try:
        declared = {identifier(value) for value in ids}
    except PathRefused as exc:
        raise Refused(str(exc)) from exc
    if len(declared) != len(ids):
        raise Refused('Invalid evidence identifiers')
    lines, table = evidence_store._evidence_texts(text)
    actual = evidence_store.cited_ids(lines + table)
    if any(not evidence_store.ID_TOKEN.fullmatch(value) for value in table):
        raise Refused('Invalid source citations in Evidence table')
    if actual != declared:
        raise Refused('Actual source citations must match evidence_ids exactly; review corrected metadata')


def validate_evidence_bindings(wiki: Path, candidate: Path, ids: list[str]) -> None:
    for value in ids:
        present = [folder for folder in (
            checked_path(candidate, f'evidence/{identifier(value)}'),
            checked_path(wiki, f'raw/evidence/{identifier(value)}')) if folder.exists()]
        if not present:
            raise Refused(f'Cited evidence {value} requires a bound manifest.json')
        for folder in present:
            try:
                manifest = json.loads(checked_path(folder, 'manifest.json').read_bytes())
            except (OSError, ValueError) as exc:
                raise Refused(f'Cited evidence {value} requires a readable bound manifest.json') from exc
            if not isinstance(manifest, dict) or manifest.get('schema') != evidence_store.SCHEMA or manifest.get('evidence_id') != value:
                raise Refused(f'Cited evidence {value} requires a schema-1 identity-matching manifest')


def _pending_requests(c: Path, metadata: dict) -> list[str]:
    import evidence_requests
    try:
        if metadata['kind'] == 'retire' and metadata.get('evidence_requests') is not None:
            raise evidence_requests.RequestRefused('A retirement cannot request evidence')
        return evidence_requests.pending_ids(c, metadata)
    except (evidence_requests.RequestRefused, PathRefused) as exc:
        raise Refused(str(exc)) from exc


def content_refusals(new_text: str, old_text: str) -> list[str]:
    """The evidence rules a source's own text must pass before approval. The draft adapter applies
    the same list when a draft is submitted, so a draft that approval would refuse is never stored."""
    out = []
    unbacked = evidence_store.version_claims_without_evidence(new_text, old_text)
    if unbacked:
        out.append("new or changed decisions name a pinned version but have 'Evidence: none'. A version "
                   "number or commit in a decision's text makes the claim depend on that release, so it "
                   "needs a retained copy (an evidence request) that a later upgrade can be re-checked "
                   "against; when the number is only release history, leave it out of the decision's "
                   "text: " + "; ".join(unbacked))
    bare = evidence_store.findings_without_evidence(new_text, old_text)
    if bare:
        out.append("new or changed findings have no retained evidence (request a copy, or move the "
                   "finding under '## Open'): " + "; ".join(bare))
    return out


def approval_preflight(wiki: Path, inbox: Path, ref: str) -> str | None:
    """Why approval would be refused now, or None. Runs the approval's own read-only checks."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_approve(wiki, inbox, ref, True)
    except Refused as exc:
        return str(exc)
    return None


def review_snapshot(wiki: Path, inbox: Path, ref: str) -> dict:
    c, metadata = load_candidate(inbox, ref)
    target = wiki / 'raw' / 'sources' / metadata['target']
    identity = wiki / '.llm-wiki' / 'project.json'
    try:
        checked_path(wiki, f"raw/sources/{metadata['target']}")
        checked_path(wiki, '.llm-wiki/project.json')
    except PathRefused as exc:
        raise Refused(str(exc)) from exc
    actual_base = sha(target) if target.is_file() else None
    if metadata['kind'] in ('update', 'retire'):
        base = metadata.get('base_sha256')
        if not isinstance(base, str) or not re.fullmatch('[0-9a-f]{64}', base) or base != actual_base:
            raise Refused('Required target base hash is missing, malformed or stale')
    corrects = correction_of(wiki, inbox, c, metadata) if metadata['kind'] == 'new' and target.exists() else None
    project = json.loads(identity.read_text(encoding='utf-8'))
    if not project.get('id'):
        raise Refused('Project identity missing')
    source = c / 'source.md'
    if metadata['kind'] in ('new', 'update'):
        if not source.is_file():
            raise Refused('source.md missing')
        validate_source_citations(source.read_text(encoding='utf-8'), metadata.get('evidence_ids', []))
    pending = _pending_requests(c, metadata)
    if metadata['kind'] in ('new', 'update'):
        validate_evidence_bindings(wiki, c, [v for v in metadata.get('evidence_ids', []) if v not in pending])
    evidence = [{'path': p.relative_to(c / 'evidence').as_posix(), 'sha256': sha(p)}
                for p in sorted((c / 'evidence').rglob('*')) if p.is_file()]
    stored_evidence = []
    try:
        ids = metadata.get('evidence_ids', [])
        if not isinstance(ids, list) or len(ids) != len(set(ids)):
            raise PathRefused('Invalid evidence identifiers')
        for value in sorted(ids):
            ev = checked_path(wiki, f'raw/evidence/{identifier(value)}')
            for p in sorted(ev.rglob('*')):
                checked_path(wiki, p.relative_to(wiki).as_posix())
                if p.is_file():
                    stored_evidence.append({'path': p.relative_to(wiki / 'raw/evidence').as_posix(), 'sha256': sha(p)})
    except (PathRefused, TypeError) as exc:
        raise Refused(str(exc)) from exc
    snapshot = {
        'project_root': str(wiki.resolve()), 'project_id': project['id'],
        'project_hash': sha(identity), 'ref': ref, 'kind': metadata['kind'],
        'target': metadata['target'], 'metadata_hash': sha(c / 'candidate.json'),
        'source_hash': sha(source) if source.is_file() else None,
        'evidence': evidence, 'stored_evidence': stored_evidence, 'pending_evidence': pending,
        'expected_base': sha(target) if target.is_file() else None,
    }
    if corrects:
        snapshot['corrects'] = corrects
    encoded = json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return {**snapshot, 'review_digest': hashlib.sha256(encoded).hexdigest()}


def cmd_show(wiki: Path, inbox: Path, ref: str, as_json: bool = False) -> int:
    c, m = load_candidate(inbox, ref)
    metadata_bytes = (c / 'candidate.json').read_bytes()
    if json.loads(metadata_bytes) != m:
        raise Refused('Candidate changed while review was assembled; review again')
    snapshot = review_snapshot(wiki, inbox, ref)
    cur = wiki / "raw" / "sources" / m["target"]
    new = c / "source.md"
    old_bytes = cur.read_bytes() if cur.exists() else None
    new_bytes = new.read_bytes() if new.exists() else None
    old_full = old_bytes.decode('utf-8') if old_bytes is not None else None
    new_full = new_bytes.decode('utf-8') if new_bytes is not None else None
    old_text = old_full.splitlines() if old_full is not None else []
    new_text = new_full.splitlines() if new_full is not None else []
    diff = list(difflib.unified_diff(old_text, new_text, f"current/{m['target']}",
                                     f"candidate/{m['target']}", lineterm=""))
    probs = check_format(new_full) if new_full is not None else []
    observed = {
        'metadata_hash': hashlib.sha256(metadata_bytes).hexdigest(),
        'source_hash': hashlib.sha256(new_bytes).hexdigest() if new_bytes is not None else None,
        'expected_base': hashlib.sha256(old_bytes).hexdigest() if old_bytes is not None else None,
    }
    if any(snapshot[k] != value for k, value in observed.items()) or review_snapshot(wiki, inbox, ref) != snapshot:
        raise Refused('Candidate, evidence, project or target changed while review was assembled; review again')
    if as_json:
        ev = sorted(p.name for p in (c / "evidence").glob("*")) if (c / "evidence").is_dir() else []
        print(json.dumps({"ref": ref, "candidate": m, "diff": diff, "format_problems": probs,
                          "target_exists": old_bytes is not None, "evidence_folders": ev,
                          "corrects": snapshot.get('corrects'),
                          "evidence_requests": __import__('evidence_requests').describe(c, m),
                          "pending_evidence": snapshot['pending_evidence'],
                          "approval_refusal": approval_preflight(wiki, inbox, ref),
                          "review_digest": snapshot['review_digest'],
                          "source_text": new_full,
                          "current_text": old_full}, ensure_ascii=False))
        return 0
    print(json.dumps(m, ensure_ascii=False, indent=1))
    for line in diff:
        print(line)
    if new.exists():
        print("format: ok" if not probs else "format problems: " + "; ".join(probs))
    return 0


def cmd_approve(wiki: Path, inbox: Path, ref: str, dry: bool,
                review_digest: str | None = None, approval: dict | None = None) -> int:
    if not dry:
        raise Refused('Live application is disabled until the owner-approval transport and recoverable application are verified; confirm flags and actor labels are not authorization')
    c, m = load_candidate(inbox, ref)
    target = wiki / "raw" / "sources" / m["target"]
    src = c / "source.md"
    kind = m["kind"]
    if kind in ("new", "update"):
        if not src.exists():
            raise Refused("source.md missing")
        validate_source_citations(src.read_text(encoding='utf-8'), m.get('evidence_ids', []))
        waiting = _pending_requests(c, m)
        if waiting:
            raise Refused("requested evidence is not fetched yet (use Fetch evidence first): " + ", ".join(waiting))
        validate_evidence_bindings(wiki, c, m.get('evidence_ids', []))
        probs = check_format(src.read_text(encoding="utf-8"))
        if probs:
            raise Refused("format: " + "; ".join(probs))
    if kind == "new" and target.exists():
        correction_of(wiki, inbox, c, m)
    if kind in ("update", "retire"):
        if not target.exists():
            raise Refused(f"{m['target']} does not exist")
        base = m.get("base_sha256")
        if base and sha(target) != base:
            raise Refused(f"{m['target']} changed since the harvest; regenerate the candidate")
    ev_new = []
    for ev in sorted((c / "evidence").glob("*")) if (c / "evidence").is_dir() else []:
        dest = wiki / "raw" / "evidence" / ev.name
        if not dest.exists():
            ev_new.append((ev, dest))
        elif not same_evidence(ev, dest):
            raise Refused(f"evidence id {ev.name} already exists in raw/evidence with different "
                          f"content; capture the new copy under a new id (e.g. with the date or "
                          f"commit) so the old decision keeps its own evidence")
    missing = [e for e in m.get("evidence_ids", [])
               if not (wiki / "raw" / "evidence" / e).exists() and not (c / "evidence" / e).exists()]
    if missing:
        raise Refused("evidence ids with no folder: " + ", ".join(missing))
    if kind in ("new", "update"):
        refusals = content_refusals(src.read_text(encoding="utf-8"),
                                    target.read_text(encoding="utf-8") if target.exists() else "")
        if refusals:
            raise Refused(refusals[0])
    if dry:
        print(f"[dry-run] would {kind} {m['target']}; new evidence folders: {[d.name for _, d in ev_new]}")
        return 0
    for ev, dest in ev_new:
        shutil.copytree(ev, dest)
    if kind == "retire":
        target.unlink()
    else:
        shutil.copy2(src, target)
    synced = evidence_store.sync_used_by(wiki / "raw" / "evidence", wiki / "raw" / "sources")
    (c / "applied.json").write_text(json.dumps({
        "at": datetime.now().astimezone().isoformat(timespec="seconds"), "kind": kind,
        "target": m["target"], "evidence_added": [d.name for _, d in ev_new],
        "used_by_synced": synced}, indent=1) + "\n",
        encoding="utf-8")
    print(f"OK {kind} {m['target']} applied; evidence added: {len(ev_new)}. The app ingests it "
          f"(model cost); the daily auto-commit backs it up.")
    return 0


def cmd_reject(inbox: Path, ref: str, reason: str, *, wiki: Path | None = None,
               expected_review_digest: str | None = None) -> int:
    from candidate_apply import reject_candidate, ApplyRefused
    from workflow_store import WorkflowError
    try:
        reject_candidate(inbox, ref, reason, wiki=wiki, expected_review_digest=expected_review_digest)
    except (ApplyRefused, PathRefused, WorkflowError) as exc:
        raise Refused(str(exc)) from exc
    print(f"OK rejected {ref}: {reason}")
    return 0


def cmd_recover(wiki: Path, inbox: Path, operation_id: str, dry: bool) -> int:
    from workflow_store import WorkflowStore, WorkflowError
    if not dry:
        raise Refused('Live recovery remains disabled until runtime activation and release verification pass')
    identifier(operation_id)
    try:
        with WorkflowStore(checked_path(inbox.parent, 'workflow.sqlite'), read_only=True) as store:
            operation = store.get_operation(operation_id)
            if not operation or operation.get('type') != 'candidate':
                raise Refused('No prepared candidate operation has this identity')
            snapshot = operation['snapshot']
            if snapshot['project_root'] != str(wiki.resolve()) or sha(checked_path(wiki, '.llm-wiki/project.json')) != snapshot['project_hash']:
                raise Refused('Recovery belongs to another project or changed project identity')
            target = checked_path(wiki, f"raw/sources/{snapshot['target']}")
            actual = sha(target) if target.is_file() else None
            desired = None if snapshot['kind'] == 'retire' else snapshot['source_hash']
            print(json.dumps({'operation_id': operation_id, 'state': operation['state'], 'actual_source_hash': actual,
                              'prepared_source_hash': desired, 'source_matches_prepared': actual == desired,
                              'publication_enabled': False, 'dry_run': True}))
    except (WorkflowError, PathRefused) as exc:
        raise Refused(str(exc)) from exc
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("show"); p.add_argument("ref"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("approve"); p.add_argument("ref"); p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("reject"); p.add_argument("ref"); p.add_argument("--reason", required=True)
    p.add_argument("--expected-review-digest")
    p = sub.add_parser("fetch-evidence"); p.add_argument("ref"); p.add_argument("--expected-review-digest", required=True)
    p = sub.add_parser("recover"); p.add_argument("operation_id"); p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("reconcile"); p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        wiki, inbox = paths()
        if args.cmd == "list":
            return cmd_list(inbox, args.json)
        if args.cmd == "show":
            return cmd_show(wiki, inbox, args.ref, args.json)
        if args.cmd == "approve":
            return cmd_approve(wiki, inbox, args.ref, args.dry_run)
        if args.cmd == "fetch-evidence":
            import evidence_requests
            result = evidence_requests.fetch(wiki, inbox, args.ref, args.expected_review_digest)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["ok"] else 1
        if args.cmd == "recover":
            return cmd_recover(wiki, inbox, args.operation_id, args.dry_run)
        if args.cmd == "reconcile":
            if not args.dry_run:
                raise Refused("Legacy import remains disabled until release verification passes; use a read-only preview")
            from candidate_apply import reconcile_legacy
            print(json.dumps(reconcile_legacy(wiki, inbox, None), ensure_ascii=False))
            return 0
        return cmd_reject(inbox, args.ref, args.reason, wiki=wiki, expected_review_digest=args.expected_review_digest)
    except (Refused, PathRefused, wikiconfig.ConfigError, OSError, ValueError) as exc:
        print(f"!! refused: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

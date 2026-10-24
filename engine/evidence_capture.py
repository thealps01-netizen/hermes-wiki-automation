"""Capture offline evidence for a wiki source: download, pin, hash, and verify passages.

WHY: a link in a source dies eventually, and then the decision it supports can no longer be
checked. A source's decisions therefore rely on downloaded copies kept in
`<wiki root>/raw/evidence/<evidence-id>/`. That folder is never ingested: the app only watches
raw/sources/. This script is the single way those copies are made, so every agent (Hermes,
Codex, Claude Code, a cron job) produces the same folder shape.

WHAT IT WRITES in raw/evidence/<id>/:
  files/<commit8>/<path>   for a GitHub file pinned to a commit (the full file, byte-exact)
  <name>                   for a web page (HTML or text as served) or a local file
  LICENSE.upstream         the repository licence, when one exists (GitHub only)
  manifest.json            source_url, commit/revision, captured_at, license, files (bytes and
                           sha256 each), passages (verbatim, with the file they were found in),
                           supports, used_by

A PASSAGE MUST BE FOUND in the stored file, or the capture fails and nothing is written. This
keeps an error page, a login wall or a 200 OK interstitial from ever becoming "evidence".
If a web URL fails, the Wayback Machine copy is tried. If that fails too, a manifest with
"status": "lost" is written only when --allow-lost is given; otherwise the script exits 1.

USAGE
  python evidence_capture.py --id <evidence-id> --used-by <source.md> --supports "<claim>"
         (--github <owner>/<repo>@<ref>:<path> [--github ...] | --url <url> | --file <path>)
         --passage "<verbatim text>" [--passage ...] [--allow-lost] [--dry-run]

  --github takes a branch, tag or sha as <ref>; it is resolved to the full commit sha.
  --file is for local material (a checkout, a config); it is copied as-is.
  Re-running with an existing id adds used_by entries; it never overwrites stored files.

EXIT CODES: 0 captured (or already present); 1 failed (nothing written unless --allow-lost);
2 bad arguments.

MAINTENANCE MODES (no capture; all read-only unless stated)
  python evidence_capture.py --verify     check every folder against its manifest and against
                                          the sources that cite it; exit 1 on any problem
  python evidence_capture.py --recheck    re-read the pinned upstream files of watched products at
                                          the INSTALLED version and report passages that no longer
                                          occur there (the decision they back needs a new look)
  python evidence_capture.py --normalise [--dry-run]
                                          rewrite every manifest into schema 1 and set used_by from
                                          the sources (WRITES manifests; nothing else is touched)

MANIFEST SCHEMA 1 (what --normalise produces and --verify expects):
  schema 1, evidence_id, status (captured | archived-copy | lost | not-stored), source_url,
  repository (<owner>/<repo> or null), commit (full sha, or null), license, captured_at,
  capture_tool, supports, used_by (list of raw/sources file names, derived from the sources),
  files {<stored relative path>: {bytes, sha256, stored?, upstream_path?, ...}},
  passages [{file, text, ...}], http {status, content_type} (web captures), extra {every other
  field an older manifest carried, kept verbatim}.
used_by is DERIVED, never hand-kept: the source files' "Evidence:" lines and "## Evidence" table are
the record of which source relies on which folder, so a folder is never taken for unused while a
source still cites it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_store  # noqa: E402
import wikiconfig  # noqa: E402
from evidence_store import SCHEMA  # noqa: E402

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_BYTES = 50 * 1024 * 1024          # larger files: manifest only (see --file / --url)
UA = "Mozilla/5.0 (evidence-capture; +personal knowledge base archive)"
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING", "LICENSE-MIT",
                 "LICENSE-APACHE")


class CaptureError(Exception):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def gh_raw(repo: str, path: str, ref: str) -> bytes:
    """A file's exact bytes at <ref> via the GitHub API (authenticated gh when available)."""
    gh = shutil.which("gh")
    if gh:
        p = subprocess.run([gh, "api", f"repos/{repo}/contents/{urllib.parse.quote(path)}?ref={ref}",
                            "-H", "Accept: application/vnd.github.raw"], capture_output=True)
        if p.returncode == 0 and p.stdout:
            return p.stdout
        raise CaptureError(f"gh api {repo}:{path}@{ref} failed: {p.stderr.decode('utf-8', 'replace')[:200]}")
    return http_get(f"https://raw.githubusercontent.com/{repo}/{ref}/{path}")[0]


def gh_json(endpoint: str) -> dict | list | None:
    gh = shutil.which("gh")
    if gh:
        p = subprocess.run([gh, "api", endpoint], capture_output=True)
        if p.returncode != 0:
            return None
        return json.loads(p.stdout.decode("utf-8"))
    try:
        return json.loads(http_get(f"https://api.github.com/{endpoint}")[0].decode("utf-8"))
    except CaptureError:
        return None


def resolve_sha(repo: str, ref: str) -> str:
    data = gh_json(f"repos/{repo}/commits/{ref}")
    if not isinstance(data, dict) or not data.get("sha"):
        raise CaptureError(f"cannot resolve {repo}@{ref} to a commit")
    return data["sha"]


def repo_license(repo: str, sha: str) -> tuple[str, bytes | None]:
    """(spdx or note, licence file bytes or None). Looks at the tree, not only the API field."""
    info = gh_json(f"repos/{repo}/license")
    spdx = (info or {}).get("license", {}).get("spdx_id") if isinstance(info, dict) else None
    tree = gh_json(f"repos/{repo}/git/trees/{sha}")
    names = [e.get("path") for e in (tree or {}).get("tree", [])] if isinstance(tree, dict) else []
    for n in LICENSE_NAMES:
        if n in names:
            try:
                return (spdx or n), gh_raw(repo, n, sha)
            except CaptureError:
                break
    return (spdx or "none found"), None


LAST_HTTP: dict = {}


def http_get(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise CaptureError(f"{url}: larger than {MAX_BYTES} bytes")
            LAST_HTTP.clear()
            LAST_HTTP.update({"status": getattr(r, "status", None),
                              "content_type": r.headers.get("Content-Type")})
            return data, r.geturl()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CaptureError(f"{url}: {exc}") from exc


def wayback(url: str) -> tuple[bytes, str]:
    data, final = http_get(f"https://web.archive.org/web/2026id_/{url}")
    return data, final


def wayback_save(url: str) -> dict:
    """Ask the Wayback Machine to archive <url> now, so a public second copy exists. Best effort:
    the result is recorded, a failure never fails the capture (the local copy is the evidence)."""
    try:
        _, final = http_get(f"https://web.archive.org/save/{url}")
        return {"requested_at": now_iso(), "snapshot": final}
    except CaptureError as exc:
        return {"requested_at": now_iso(), "error": str(exc)[:200]}


def check_passages(files: dict[str, bytes], passages: list[str]) -> list[dict]:
    """Every passage must occur verbatim (line endings normalised) in one stored text file."""
    texts = {name: norm(data.decode("utf-8", "replace")) for name, data in files.items()}
    out = []
    for p in passages:
        hit = next((name for name, t in texts.items() if norm(p) in t), None)
        if hit is None:
            raise CaptureError(f"passage not found in any stored file: {p[:80]!r}")
        out.append({"file": hit, "text": p})
    return out


def safe_name(url: str) -> str:
    u = urllib.parse.urlparse(url)
    base = (u.netloc + u.path).strip("/").replace("/", "_") or "page"
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base)[:120]
    known = (".html", ".htm", ".md", ".txt", ".pdf", ".json", ".xml", ".csv")
    return base if base.lower().endswith(known) else base + ".html"


def capture(args) -> dict:
    files: dict[str, bytes] = {}
    manifest: dict = {"schema": SCHEMA, "evidence_id": args.id, "status": "captured",
                      "repository": None, "commit": None, "captured_at": now_iso(),
                      "supports": args.supports, "used_by": [args.used_by],
                      "capture_tool": "evidence_capture.py"}
    if args.github:
        specs = []
        for g in args.github:
            m = re.match(r"^([\w.-]+/[\w.-]+)@([^:]+):(.+)$", g)
            if not m:
                raise CaptureError(f"--github must be <owner>/<repo>@<ref>:<path>, got {g!r}")
            specs.append(m.groups())
        repos = {s[0] for s in specs}
        if len(repos) != 1:
            raise CaptureError("one evidence item holds one repository; use several ids")
        repo = repos.pop()
        sha = resolve_sha(repo, specs[0][1])
        for _, ref, path in specs:
            if resolve_sha(repo, ref) != sha:
                raise CaptureError("all --github files of one item must resolve to the same commit")
            files[f"files/{sha[:8]}/{path}"] = gh_raw(repo, path, sha)
        lic, lic_bytes = repo_license(repo, sha)
        if lic_bytes:
            files["LICENSE.upstream"] = lic_bytes
        manifest.update({"source_url": f"https://github.com/{repo}/tree/{sha}", "repository": repo,
                         "commit": sha,
                         "license": lic if lic_bytes else f"{lic}: private archive copy for "
                                                         f"personal verification only; do not republish"})
    elif args.url:
        try:
            data, final = http_get(args.url)
            manifest.update({"source_url": args.url, "fetched_url": final, "accessed": now_iso(),
                             "http": dict(LAST_HTTP)})
        except CaptureError as live_err:
            try:
                data, final = wayback(args.url)
                manifest.update({"source_url": args.url, "fetched_url": final, "accessed": now_iso(),
                                 "status": "archived-copy", "live_error": str(live_err),
                                 "http": dict(LAST_HTTP)})
            except CaptureError as wb_err:
                if not args.allow_lost:
                    raise CaptureError(f"live: {live_err} | wayback: {wb_err}")
                manifest.update({"source_url": args.url, "status": "lost",
                                 "live_error": str(live_err), "wayback_error": str(wb_err),
                                 "passages": [{"file": None, "text": p, "unverified": True}
                                              for p in args.passage]})
                return {"manifest": manifest, "files": {}}
        files[safe_name(args.url)] = data
        manifest["license"] = args.license or ("not stated: private archive copy for personal "
                                               "verification only; do not republish")
        if args.wayback_save and manifest.get("status") != "archived-copy":
            manifest["wayback_save"] = wayback_save(args.url)
    elif args.file:
        src = Path(args.file)
        if not src.is_file():
            raise CaptureError(f"--file not found: {src}")
        if src.stat().st_size > MAX_BYTES:
            raise CaptureError(f"--file larger than {MAX_BYTES} bytes; record it by hash only")
        files[src.name] = src.read_bytes()
        manifest.update({"source_url": args.origin or f"local file {src.name}", "accessed": now_iso(),
                         "license": args.license or "local material: private, do not republish"})
    manifest["passages"] = check_passages(
        {k: v for k, v in files.items() if k != "LICENSE.upstream"}, args.passage)
    manifest["files"] = {k: {"bytes": len(v), "sha256": sha256(v)} for k, v in files.items()}
    return {"manifest": manifest, "files": files}


def write(root: Path, result: dict, dry: bool) -> Path:
    folder = root / result["manifest"]["evidence_id"]
    if dry:
        return folder
    tmp = folder.with_name(folder.name + ".partial")
    if tmp.exists():
        shutil.rmtree(tmp)
    for rel, data in result["files"].items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "manifest.json").write_text(json.dumps(result["manifest"], indent=1, ensure_ascii=False)
                                       + "\n", encoding="utf-8")
    tmp.rename(folder)
    return folder


def add_user(folder: Path, used_by: str, dry: bool) -> bool:
    mf = folder / "manifest.json"
    m = json.loads(mf.read_text(encoding="utf-8"))
    users = m.get("used_by") or []
    users = [users] if isinstance(users, str) else list(users)
    if used_by in users:
        return False
    if not dry:
        m["used_by"] = users + [used_by]
        mf.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def maintenance(args) -> int:
    cfg = wikiconfig.load()
    wiki = wikiconfig.project_root(cfg)
    root = Path(args.evidence_root) if args.evidence_root else wiki / "raw" / "evidence"
    sources = wiki / "raw" / "sources"
    if args.normalise:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bdir = None if args.dry_run else evidence_store.backup_dir(wikiconfig.audit_dir(cfg), stamp)
        changed, problems = evidence_store.normalise(root, sources, args.dry_run, bdir)
        for p in problems:
            print(f"!! {p}")
        print(f"{'[dry-run] would rewrite' if args.dry_run else 'OK rewrote'} {changed} manifest(s)"
              f"{'' if args.dry_run or not changed else f'; previous manifests in {bdir}'}")
        return 1 if problems else 0
    if args.recheck:
        state = wikiconfig.audit_dir(cfg) / "evidence-recheck-cache.json"
        cache = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
        inst = evidence_store.installed_commits(cfg, wikiconfig.hermes_home(cfg))
        found = evidence_store.recheck(root, inst, wikiconfig.hermes_home(cfg), cache)
        state.write_text(json.dumps(cache, indent=1) + "\n", encoding="utf-8")
        print(f"installed: {', '.join(f'{r}@{s[:10]}' for r, s in inst.items()) or 'none readable'}")
        for f in found:
            print(f"!! {f}")
        print(f"{'OK' if not found else '!!'} {len(found)} evidence folder(s) whose pinned passages "
              f"changed in the installed version")
        return 1 if found else 0
    found = evidence_store.verify(root, sources)
    for f in found:
        print(f"!! {f}")
    print(f"{'OK' if not found else '!!'} evidence store: {len(evidence_store.folders(root))} folder(s), "
          f"{len(found)} problem(s)")
    return 1 if found else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--verify", action="store_true", help="check the whole store (read-only)")
    mode.add_argument("--recheck", action="store_true",
                      help="re-read pinned passages at the installed LLM Wiki / Hermes version")
    mode.add_argument("--normalise", action="store_true",
                      help="rewrite every manifest into schema 1 (use --dry-run first)")
    ap.add_argument("--id")
    ap.add_argument("--used-by", help="the raw/sources file name that relies on it")
    ap.add_argument("--supports", help="the decision or claim this evidence backs")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--github", action="append", help="<owner>/<repo>@<ref>:<path> (repeatable)")
    src.add_argument("--url")
    src.add_argument("--file")
    ap.add_argument("--origin", help="where a --file came from (repo@sha:path, tool, config)")
    ap.add_argument("--license", help="licence note for --url/--file material")
    ap.add_argument("--passage", action="append",
                    help="verbatim text that supports the decision (repeatable)")
    ap.add_argument("--allow-lost", action="store_true",
                    help="write a 'lost' manifest when neither the live URL nor Wayback answers")
    ap.add_argument("--wayback-save", action="store_true",
                    help="also ask the Wayback Machine to archive a --url now (public second copy)")
    ap.add_argument("--evidence-root", help="override <wiki root>/raw/evidence (tests, staging)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.verify or args.recheck or args.normalise:
        try:
            return maintenance(args)
        except wikiconfig.ConfigError as exc:
            print(f"!! {exc}")
            return 1
    need = [n for n, v in (("--id", args.id), ("--used-by", args.used_by), ("--supports", args.supports),
                           ("--passage", args.passage),
                           ("--github/--url/--file", args.github or args.url or args.file)) if not v]
    if need:
        print(f"!! a capture needs {', '.join(need)} (or use --verify / --recheck / --normalise)")
        return 2
    if not ID_RE.match(args.id):
        print(f"!! evidence id must be lowercase words joined by hyphens: {args.id!r}")
        return 2
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md", args.used_by):
        print(f"!! --used-by must be a raw/sources file name (<YYYY-MM-DD>-<topic>.md): {args.used_by!r}")
        return 2
    try:
        root = Path(args.evidence_root) if args.evidence_root else \
            wikiconfig.project_root(wikiconfig.load()) / "raw" / "evidence"
    except wikiconfig.ConfigError as exc:
        print(f"!! {exc}")
        return 1

    folder = root / args.id
    if folder.exists():
        added = add_user(folder, args.used_by, args.dry_run)
        print(f"OK evidence {args.id} already present{' - used_by updated' if added else ''}: {folder}")
        return 0
    try:
        result = capture(args)
    except CaptureError as exc:
        print(f"!! capture failed, nothing written: {exc}")
        return 1
    out = write(root, result, args.dry_run)
    m = result["manifest"]
    status = m.get("status", "captured")
    size = sum(f["bytes"] for f in m.get("files", {}).values())
    if status == "lost":
        print(f"!! evidence {args.id} LOST{' (dry-run)' if args.dry_run else ''}: neither the live URL "
              f"nor the Wayback Machine answered; manifest written, passages NOT verified -> {out}")
        return 0
    print(f"OK evidence {args.id} {status}{' (dry-run)' if args.dry_run else ''}: {len(m.get('files', {}))} "
          f"file(s), {size} bytes, {len(m.get('passages', []))} passage(s) verified -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

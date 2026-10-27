"""Evidence store maintenance: one manifest shape, used_by derived from the sources, daily checks.

WHY: raw/evidence/<id>/ holds the downloaded copies that the wiki's decisions rely on. Before
evidence_capture.py existed, early folders were written by hand in many manifest shapes, and
used_by lists were kept by hand and drifted from the sources that actually cite a folder. Nothing
re-checked the store, so a broken copy, a missing folder or a decision whose upstream code had
changed since it was pinned would go unnoticed. This module is the single implementation of:

  normalise(root)   rewrite every manifest into schema 1 (evidence_capture.py docstring) without
                    dropping a field: fields schema 1 does not name move under "extra" verbatim.
                    A file whose recorded sha256 differs from the disk is NOT rewritten (reported).
  sync_used_by()    used_by := the raw/sources files that cite the folder.
  verify(root)      read-only fixity + consistency check, one problem string per finding.
  recheck(root)     for evidence pinned in a WATCHED product (LLM Wiki, Hermes), re-read each
                    stored file at the INSTALLED version and report passages that no longer occur:
                    the decision they back may be stale. Cached per installed commit.

Who cites what is read from the sources, never from the manifests: a decision's "Evidence:" line
and the "## Evidence" table (first column = id). Called by evidence_capture.py (--verify,
--normalise, --recheck), watchdog.py (daily) and wiki_candidates.py (approve).
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA = 1
TOP_KEYS = ("schema", "evidence_id", "status", "source_url", "repository", "commit", "license",
            "captured_at", "capture_tool", "supports", "used_by", "files", "passages")
KEEP_TOP = ("fetched_url", "accessed", "http", "live_error", "wayback_error", "wayback_save")
STATUSES = ("captured", "archived-copy", "lost", "not-stored")
ID_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")
# A bare date (2026-10-06) matches ID_TOKEN but is never an evidence id: pages write dates next to ids
# and between clauses. evidence_requests refuses a new id that is one, so skipping dates hides nothing.
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
# Products whose installed version this machine can tell; evidence pinned there is re-checked.
WATCHED = {"nashsu/llm_wiki": "llm-wiki", "NousResearch/hermes-agent": "hermes"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\r\n", "\n")).strip()


def folders(root: Path) -> dict[str, Path]:
    return {d.name: d for d in sorted(root.iterdir()) if d.is_dir() and not d.name.endswith(".partial")} \
        if root.is_dir() else {}


# ---------------------------------------------------------------- who cites what (from sources)

def _no_evidence(value: str) -> bool:
    """Only a complete placeholder is absent evidence, never an identifier prefix."""
    # The annotation may wrap onto the field's indented continuation lines.
    match = re.fullmatch(r"none(?:\s*\((.*)\))?\.?|[-–—]", value.strip(), re.I | re.S)
    if match is None:
        return False
    # An annotation may nest parentheses, but may not end before another clause.
    depth = 0
    for char in match.group(1) or "":
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _evidence_values(text: str) -> list[str]:
    """Read only Evidence field values, including their indented continuations."""
    return [m.group(1) for m in re.finditer(r"Evidence:\s*(.+(?:\n {2,}\S.*)*)", text)]


_PLACEHOLDER_HEAD = re.compile(r"(?<![A-Za-z0-9-])none\s*\(", re.I)


def _without_placeholders(chunk: str) -> str:
    """Drop every complete `none (...)` clause, whose annotation explains missing evidence and
    may hold dates or hyphenated words. An unbalanced annotation is kept, so its words still
    count as citations and the review fails closed instead of hiding an identifier."""
    out, pos = [], 0
    for match in _PLACEHOLDER_HEAD.finditer(chunk):
        if match.start() < pos:
            continue
        depth, end = 0, None
        for index in range(match.end() - 1, len(chunk)):
            if chunk[index] == "(":
                depth += 1
            elif chunk[index] == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is not None:
            out.append(chunk[pos:match.start()])
            pos = end
    return "".join(out) + chunk[pos:]


def cited_ids(chunks: list[str]) -> set[str]:
    """Evidence ids named by Evidence values or table cells (see _evidence_texts)."""
    return {token for chunk in chunks
            for token in ID_TOKEN.findall(_without_placeholders(chunk).replace("`", " "))
            if not DATE.fullmatch(token)}


def _evidence_texts(text: str) -> tuple[list[str], list[str]]:
    """(free-text Evidence: values, first-column ids of the ## Evidence table)."""
    lines = [value for value in _evidence_values(text) if not _no_evidence(value)]
    table = []
    if "## Evidence" in text:
        sec = text.split("## Evidence", 1)[1].split("\n## ", 1)[0]
        for row in sec.splitlines():
            cells = [c.strip().strip("`") for c in row.split("|")]
            if row.lstrip().startswith("|") and len(cells) > 2 and cells[1] and \
                    not set(cells[1]) <= set("-: ") and cells[1].lower() not in ("id", "evidence id") \
                    and not _no_evidence(cells[1]):
                table.append(cells[1])
    return lines, table


def citations(sources: Path, known: set[str]) -> tuple[dict[str, set[str]], list[tuple[str, str]]]:
    """({evidence id: {source file names}}, [(source, table id with no folder)])."""
    cites: dict[str, set[str]] = {}
    missing: list[tuple[str, str]] = []
    for p in sorted(sources.glob("*.md")):
        lines, table = _evidence_texts(p.read_text(encoding="utf-8"))
        for tok in cited_ids(lines + table):
            if tok in known:
                cites.setdefault(tok, set()).add(p.name)
        for tid in table:
            if tid not in known:
                missing.append((p.name, tid))
    return cites, missing


# ---------------------------------------------------------------- version claims without evidence

# A pinned version of a product: v1.2.3 / 1.2.3 (three parts, not an IP address) or a 10-40 hex
# commit id.
PIN_RE = re.compile(r"(?<![\d.])v?\d+\.\d+\.\d+(?!\.\d)|\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{10,40}\b")


def decision_blocks(text: str) -> list[str]:
    sec = text.split("## Decisions", 1)[1].split("\n## ", 1)[0] if "## Decisions" in text else ""
    return [b for b in re.split(r"\n(?=\*\*\d+\.)", sec) if b.lstrip().startswith("**")]


def finding_blocks(text: str) -> list[str]:
    """`**F<n>. ...**` blocks of the optional `## Findings` section: verified facts about outside
    tools, techniques or our own measurements that no decision depends on yet."""
    sec = text.split("## Findings", 1)[1].split("\n## ", 1)[0] if "## Findings" in text else ""
    return [b for b in re.split(r"\n(?=\*\*F\d+\.)", sec) if b.lstrip().startswith("**F")]


def _changed(blocks: list[str], old_blocks: list[str]) -> list[str]:
    old = {re.sub(r"\s+", " ", b).strip() for b in old_blocks}
    return [b for b in blocks if re.sub(r"\s+", " ", b).strip() not in old]


def findings_without_evidence(new_text: str, old_text: str) -> list[str]:
    """New or changed findings with no retained copy. A finding is a factual claim with no decision
    to justify it, so 'Evidence: none' is accepted only for our own measurement
    (`none (measurement: <command or commit, date>)`); anything else belongs under `## Open`.
    Unchanged findings are not re-judged."""
    out = []
    for b in _changed(finding_blocks(new_text), finding_blocks(old_text)):
        values = _evidence_values(b)
        if not values or any(_no_evidence(v) and not re.match(r"none\s*\(\s*measurement:", v.strip(), re.I)
                             for v in values):
            out.append(b.split("\n", 1)[0][:90])
    return out


def version_claims_without_evidence(new_text: str, old_text: str) -> list[str]:
    """Decisions and findings that are new or changed in this candidate, name a pinned version or
    commit in their own claim, and still say 'Evidence: none'. Such a claim can go stale on the
    next upgrade and nothing could re-check it, because no pinned copy exists. Unchanged blocks are
    not re-judged, so an update never fails on text the owner already approved."""
    old = {re.sub(r"\s+", " ", b).strip() for b in decision_blocks(old_text) + finding_blocks(old_text)}
    out = []
    for b in decision_blocks(new_text) + finding_blocks(new_text):
        if re.sub(r"\s+", " ", b).strip() in old:
            continue
        claim = b.partition("Evidence:")[0]
        if any(_no_evidence(value) for value in _evidence_values(b)) and PIN_RE.search(claim.split("- Why:")[0]):
            out.append(b.split("\n", 1)[0][:90])
    return out


# ---------------------------------------------------------------- normalise

def _repo_of(m: dict) -> str | None:
    for v in (m.get("repository"), m.get("source_url"), m.get("repo_path")):
        if not isinstance(v, str):
            continue
        v = v.strip()
        if re.fullmatch(r"[\w.-]+/[\w.-]+", v):
            return v
        g = re.search(r"https://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?(?=[/)\s,]|$)", v)
        if g:
            return g.group(1)
    return None


def _old_file_entries(m: dict) -> list[dict]:
    out = []
    f = m.get("files")
    if isinstance(f, dict):
        out += [dict(v or {}, path=k) for k, v in f.items()]
    elif isinstance(f, list):
        out += [dict(x, path=x.get("path") or x.get("name")) for x in f if isinstance(x, dict)]
    for x in m.get("stored_files") or []:
        if isinstance(x, dict):
            out.append(dict(x, path=x.get("path") or x.get("name")))
    return out


def _old_passages(m: dict) -> list[dict]:
    p = m.get("passages")
    out: list[dict] = []
    if isinstance(p, dict):
        for f, texts in p.items():
            for t in texts if isinstance(texts, list) else [texts]:
                out.append({"file": f, "text": t})
    elif isinstance(p, list):
        out += [dict(x) if isinstance(x, dict) else {"file": None, "text": x} for x in p]
    for it in m.get("items") or []:
        if isinstance(it, dict) and it.get("excerpt"):
            x = {k: v for k, v in it.items() if k != "excerpt"}
            x["text"] = it["excerpt"]
            out.append(x)
    return out


def normalise_one(folder: Path, cited_by: set[str]) -> tuple[dict | None, list[str]]:
    """(schema-1 manifest, problems). None when the folder cannot be normalised safely."""
    old = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    disk = {p.relative_to(folder).as_posix(): p for p in sorted(folder.rglob("*"))
            if p.is_file() and p.name != "manifest.json"}
    disk_sha = {k: sha256(p.read_bytes()) for k, p in disk.items()}
    files: dict[str, dict] = {}
    for e in _old_file_entries(old):
        rel = e.pop("path", None)
        if not rel:
            continue
        hit = rel if rel in disk else next(
            (k for k in disk if (Path(k).name == Path(rel).name and e.get("sha256") in (None, disk_sha[k]))
             or k.endswith("/" + rel)), None)
        if e.get("stored") is False and hit is None:
            files[rel] = e
            continue
        if hit is None:
            problems.append(f"listed file {rel} is not on disk")
            continue
        if e.get("sha256") and e["sha256"] != disk_sha[hit]:
            problems.append(f"sha256 of {hit} differs from the manifest (disk changed?)")
            return None, problems
        if hit != rel:
            e.setdefault("recorded_path", rel)
        e.update({"bytes": disk[hit].stat().st_size, "sha256": disk_sha[hit]})
        files[hit] = {**files.get(hit, {}), **e}
    for k in disk:
        if k not in files:  # stored but never hashed (e.g. licence files): baseline starts now
            files[k] = {"bytes": disk[k].stat().st_size, "sha256": disk_sha[k], "hashed_at_normalise": True}

    texts = {k: collapse(disk[k].read_bytes().decode("utf-8", "replace")) for k in disk}

    def locate(t: str, ps: dict) -> str | None:
        hits = [k for k, v in texts.items() if collapse(t) in v]
        if not hits:
            return None
        rec, com = str(ps.get("file") or ""), str(ps.get("commit") or "")[:8]
        for pref in (lambda k: k == rec,
                     lambda k: com and f"/{com}/" in f"/{k}" and rec and k.endswith(rec),
                     lambda k: rec and k.endswith("/" + rec),
                     lambda k: rec and Path(k).name == Path(rec).name):
            best = [k for k in hits if pref(k)]
            if best:
                return best[0]
        return hits[0]

    passages = []
    for ps in _old_passages(old):
        t = ps.get("text") or ""
        if not ps.get("unverified") and texts:
            found = locate(t, ps)
            if found is None and "``" in t:
                alt = t.replace("``", "`")
                found = locate(alt, ps)
                if found:
                    ps["text_as_recorded"], ps["text"] = t, alt
            if found and ps.get("file") != found:
                if ps.get("file"):
                    ps.setdefault("recorded_file", ps["file"])
                ps["file"] = found
        passages.append({"file": ps.pop("file", None), "text": ps.pop("text", ""), **ps})

    status = old.get("status") if old.get("status") in STATUSES else "captured"
    extra = {}
    if isinstance(old.get("status"), str) and old["status"] not in STATUSES:
        extra["status_note"] = old["status"]
        if any(v.get("stored") is False for v in files.values()) and not disk:
            status = "not-stored"
    commit = old.get("commit")
    if not (isinstance(commit, str) and SHA40.match(commit)):
        if commit is not None:
            extra["commit_recorded"] = commit
        commit = None
    src = old.get("source_url")
    if isinstance(src, list):
        extra["source_urls"] = src
        src = src[0] if src else None
    used = old.get("used_by")
    used = {used} if isinstance(used, str) else set(used or [])
    new = {"schema": SCHEMA, "evidence_id": folder.name, "status": status, "source_url": src,
           "repository": _repo_of(old), "commit": commit,
           "license": old.get("license") or old.get("licence"),
           "captured_at": old.get("captured_at") or old.get("created") or old.get("accessed"),
           "capture_tool": old.get("capture_tool") or "manual (before evidence_capture.py)",
           "supports": old.get("supports"), "used_by": sorted(cited_by or used),
           "files": files, "passages": passages}
    for k in KEEP_TOP:
        if k in old:
            new[k] = old[k]
    skip = set(TOP_KEYS) | set(KEEP_TOP) | {"stored_files", "items", "licence", "created", "extra"}
    extra.update({k: v for k, v in old.items() if k not in skip})
    extra.update(old.get("extra") or {})
    if old.get("evidence_id") not in (None, folder.name):
        extra["evidence_id_recorded"] = old["evidence_id"]
    if isinstance(old.get("repository"), str) and old["repository"] != new["repository"]:
        extra.setdefault("repository_recorded", old["repository"])
    if extra:
        new["extra"] = extra
    return new, problems


def write_manifest(folder: Path, m: dict, *, staging_folder: Path | None = None,
                   checkpoint=None, expected_base: str) -> None:
    """Publish losslessly; retained before-images stay outside canonical evidence."""
    import tempfile
    from candidate_apply import publish_file
    from workflow_paths import checked_path
    stage = staging_folder if staging_folder is not None else Path(
        tempfile.mkdtemp(prefix='.evidence-attribution-', dir=folder.parent.parent))
    target = checked_path(folder, 'manifest.json')
    check = checkpoint if checkpoint is not None else lambda point: None
    name = f'attribution-manifest-{folder.name}'

    def manifest_check(point):
        phase, _, item = point.partition(':')
        if item == 'publication.bin' and phase in ('before-temp', 'after-temp', 'before-fsync', 'after-fsync'):
            check(f'{phase}:{name}')
        elif item == 'manifest.json':
            check(f'{phase}:{name}')
        else:
            check(point)

    publish_file(target, (json.dumps(m, indent=1, ensure_ascii=False) + '\n').encode('utf-8'),
                 expected_base, checked_path(stage, 'captured.bin'), checkpoint=manifest_check,
                 boundary=name)


def normalise(root: Path, sources: Path, dry: bool, backup: Path | None) -> tuple[int, list[str]]:
    fs = folders(root)
    cites, _ = citations(sources, set(fs))
    changed, problems = 0, []
    if backup and not dry:
        backup.mkdir(parents=True, exist_ok=False)
    for name, d in fs.items():
        before_bytes = (d / "manifest.json").read_bytes()
        before = before_bytes.decode('utf-8')
        new, probs = normalise_one(d, cites.get(name, set()))
        problems += [f"{name}: {p}" for p in probs]
        if new is None:
            continue
        if json.loads(before) != new:
            changed += 1
            if not dry:
                if backup:
                    (backup / name).mkdir()
                    (backup / name / "manifest.json").write_text(before, encoding="utf-8")
                write_manifest(d, new, expected_base=sha256(before_bytes))
    return changed, problems


def sync_used_by(root: Path, sources: Path, only: set[str] | None = None, *,
                 staging_root: Path | None = None, checkpoint=None, bind_base=None) -> list[str]:
    """Set used_by from the sources on schema-1 manifests; returns the folders changed."""
    fs = folders(root)
    cites, _ = citations(sources, set(fs))
    out = []
    for name, d in fs.items():
        if only is not None and name not in only:
            continue
        before = (d / "manifest.json").read_bytes()
        m = json.loads(before)
        want = sorted(cites.get(name, set()))
        if m.get("schema") == SCHEMA and m.get("used_by") != want:
            m["used_by"] = want
            if staging_root is not None:
                from workflow_paths import checked_path, identifier
                stage = checked_path(staging_root, identifier(name))
            else:
                stage = None
            if bind_base is not None:
                bind_base(name, sha256(before))
            write_manifest(d, m, staging_folder=stage, checkpoint=checkpoint, expected_base=sha256(before))
            out.append(name)
    return out


# ---------------------------------------------------------------- verify

def verify(root: Path, sources: Path) -> list[str]:
    fs = folders(root)
    cites, missing = citations(sources, set(fs))
    out = [f"{s} cites evidence id {i!r} in its Evidence table, but raw/evidence/{i}/ does not exist"
           for s, i in missing]
    out += [f"{p.name}: leftover partial capture folder (delete it and re-run the capture)"
            for p in sorted(root.glob("*.partial"))] if root.is_dir() else []
    for name, d in fs.items():
        mf = d / "manifest.json"
        if not mf.exists():
            out.append(f"{name}: manifest.json missing")
            continue
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except ValueError as exc:
            out.append(f"{name}: manifest.json unreadable ({exc})")
            continue
        if m.get("schema") != SCHEMA:
            out.append(f"{name}: manifest is not schema {SCHEMA} (run evidence_capture.py --normalise)")
            continue
        if m.get("evidence_id") != name:
            out.append(f"{name}: evidence_id {m.get('evidence_id')!r} differs from the folder name")
        files = m.get("files") or {}
        disk = {p.relative_to(d).as_posix(): p for p in d.rglob("*")
                if p.is_file() and p.name != "manifest.json"}
        for rel, e in files.items():
            if e.get("stored") is False:
                continue
            if rel not in disk:
                out.append(f"{name}: {rel} listed but missing on disk")
            elif sha256(disk[rel].read_bytes()) != e.get("sha256"):
                out.append(f"{name}: {rel} changed on disk (sha256 no longer matches)")
        for rel in disk:
            if rel not in files:
                out.append(f"{name}: {rel} on disk but not in the manifest")
        if m.get("status") in ("captured", "archived-copy") and disk:
            blob = "\n".join(collapse(p.read_bytes().decode("utf-8", "replace")) for p in disk.values())
            for ps in m.get("passages") or []:
                if not ps.get("unverified") and collapse(ps.get("text", "")) not in blob:
                    out.append(f"{name}: passage no longer found in the stored files: "
                               f"{ps.get('text', '')[:60]!r}")
        want = sorted(cites.get(name, set()))
        if not want:
            out.append(f"{name}: no source cites this folder (retire it with its source, or cite it)")
        elif m.get("used_by") != want:
            out.append(f"{name}: used_by {m.get('used_by')} differs from the citing sources {want} "
                       f"(run evidence_capture.py --normalise)")
    return out


# ---------------------------------------------------------------- recheck against installed versions

def installed_commits(cfg: dict, hermes_home: Path) -> dict[str, str]:
    """{repo: installed full commit} for the watched products this machine can read."""
    out = {}
    hermes = hermes_home / "hermes-agent"
    p = subprocess.run(["git", "-C", str(hermes), "rev-parse", "HEAD"], capture_output=True, text=True)
    if p.returncode == 0 and SHA40.match(p.stdout.strip()):
        out["NousResearch/hermes-agent"] = p.stdout.strip()
    try:
        with urllib.request.urlopen(f"{cfg.get('api_base', 'http://127.0.0.1:19828')}/api/v1/health",
                                    timeout=5) as r:
            ver = json.loads(r.read().decode("utf-8")).get("version")
        if ver:
            g = subprocess.run(["gh", "api", f"repos/nashsu/llm_wiki/commits/v{ver}", "-q", ".sha"],
                               capture_output=True, text=True)
            if g.returncode == 0 and SHA40.match(g.stdout.strip()):
                out["nashsu/llm_wiki"] = g.stdout.strip()
    except (OSError, ValueError):
        pass  # app not running: LLM Wiki is simply not re-checked this run
    return out


def _upstream_text(repo: str, sha: str, path: str, hermes_home: Path) -> str | None:
    if repo == "NousResearch/hermes-agent":
        p = subprocess.run(["git", "-C", str(hermes_home / "hermes-agent"), "show", f"{sha}:{path}"],
                           capture_output=True)
    else:
        p = subprocess.run(["gh", "api", f"repos/{repo}/contents/{urllib.parse.quote(path)}?ref={sha}",
                            "-H", "Accept: application/vnd.github.raw"], capture_output=True)
    return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else None


def recheck(root: Path, installed: dict[str, str], hermes_home: Path, cache: dict) -> list[str]:
    """Findings for passages that no longer occur at the installed commit. `cache` is updated
    in place: {"<folder>@<installed sha>": [findings]} so an unchanged pair is never re-fetched."""
    out = []
    texts: dict[tuple[str, str, str], str | None] = {}
    for name, d in folders(root).items():
        try:
            m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        except ValueError:
            continue
        repo, pinned = m.get("repository"), m.get("commit")
        now = installed.get(repo or "")
        if not now or not pinned or now == pinned:
            continue
        key = f"{name}@{now}"
        if key not in cache:
            found = []
            for ps in m.get("passages") or []:
                rel = ps.get("file") or ""
                up = (m.get("files", {}).get(rel) or {}).get("upstream_path")
                if not up and rel.startswith("files/"):
                    up = re.sub(r"^files/[0-9a-f]{8}/", "", rel)
                if not up:
                    continue
                if (repo, now, up) not in texts:
                    raw = _upstream_text(repo, now, up, hermes_home)
                    texts[(repo, now, up)] = None if raw is None else collapse(raw)
                text = texts[(repo, now, up)]
                if text is None:
                    found.append(f"{up} no longer exists at {now[:10]}")
                elif collapse(ps.get("text", "")) not in text:
                    found.append(f"{up}: {ps.get('text', '')[:60]!r} changed at {now[:10]}")
            cache[key] = sorted(set(found))
        if cache[key]:
            out.append(f"{name} (pinned {pinned[:10]}, installed {now[:10]}; used by "
                       f"{', '.join(m.get('used_by') or [])}): " + "; ".join(cache[key][:3])
                       + (f" (+{len(cache[key]) - 3} more)" if len(cache[key]) > 3 else ""))
    return out


def backup_dir(audit: Path, stamp: str) -> Path:
    return audit / "backups" / f"evidence-manifests-{stamp}"

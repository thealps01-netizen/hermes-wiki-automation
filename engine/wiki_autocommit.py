"""LLM Wiki - automatic commit of app-generated changes.

WHY THIS EXISTS
  The LLM Wiki desktop app (nashsu/llm_wiki) generates wiki pages, index.md and log.md but never
  commits anything, and the off-machine mirrors (the wiki's git remotes) are refreshed by
  the repository's post-commit hook only. So the backup is exactly as fresh as the last manual
  commit. Measured on 2026-09-17: last commit 40 hours old, 192 changed paths, mirrors 0 commits
  behind HEAD only because HEAD itself was old. This script closes that gap deterministically.

WHAT ONE RUN DOES (in this order)

  1. Nothing to commit -> silent, exit 0. Only the staged paths below count as changes: an
     untracked folder elsewhere in the repository is not a reason to commit.
  2. SAFETY ALERTS (no commit, exit 1 so the run is visibly red):
       - page count fell by DROP_ALERT or more against the watchdog baseline (state.json "pages")
       - purpose.md / schema.md match the app's blank-template sizes (Create Project clobber)
       - .llm-wiki/project.json id is not CANONICAL_ID (project re-initialised)
  3. GATES (silent exit 0 - the app may still be writing, this is normal, not a finding):
       - any app queue non-empty (ingest-queue / file-change-queue / dedup-queue)
       - a .llm-wiki/*.tmp residue exists (unfinished write)
       - the newest mtime under wiki/ or raw/ is younger than QUIET_MIN minutes
  4. COMMIT - stages only wiki/, raw/sources/, raw/evidence/ and .llm-wiki/project.json. Never `git add -A` at the
     repository root, so nothing unexpected is swept into history. The message carries the ingested
     source names and the integrity numbers, so a reader who never saw this session can tell what
     was committed and whether the wiki got worse.
  5. PUSH CHECK - the post-commit hook pushes both mirrors; this script does not trust that. It
     re-reads `git rev-list --count <remote>/main..HEAD` and reports a mirror that is still ahead
     (exit 1), because a stale mirror is the failure this whole script exists to prevent.

OUTPUT CONTRACT (Hermes cron runs this with no_agent: stdout is delivered verbatim)
  nothing to commit  -> no output, exit 0
  committed          -> 1-3 lines, exit 0
  alert / push failed-> "!!" lines, exit 1 (alert path; the job shows red until it clears)

Run
  python wiki_autocommit.py              # normal (cron) run
  python wiki_autocommit.py --dry-run    # gates + report only, writes nothing to git
  python wiki_autocommit.py --force      # ignore the quiet-period gate (manual use)

stdout is pinned to UTF-8: a Windows console codepage (cp1254 here) raises UnicodeEncodeError on a
symbol like the alert marker, killing the run at the exact moment the alert was needed.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Script klasörü sys.path'e ÖNCE eklenir: cron giriş noktası bu dosyayı `runpy.run_path` ile koşar
# ve o yolda script'in kendi klasörü path'e girmez (`python script.py` ile girer). Sıra önemli —
# import satırı bunun ALTINDA olmalı, yoksa cron koşusunda ModuleNotFoundError alınır (yaşandı).
sys.path.insert(0, str(Path(__file__).resolve().parent))

import wikiconfig  # tek ayar kaynağı (settings.json) — makineye özel yol KODDA YOK

try:
    CFG = wikiconfig.load()
    WIKI = wikiconfig.project_root(CFG)          # seçili proje kökü; ayarsızsa ALARM
except wikiconfig.ConfigError as exc:
    print(f"!! ayar sorunu: {exc}")
    print(f"   düzeltme: {wikiconfig.settings_path()} içindeki 'project_root' alanını doldur")
    raise SystemExit(1)

AUDIT_DIR = wikiconfig.audit_dir(CFG)
_GATES = CFG.get("gates") or {}
STATE = AUDIT_DIR / "state.json"
LOCK = AUDIT_DIR / "auto-commit.lock"

# Kimlik beklentisi AYARDAN gelir (başka PC'de proje kimliği farklıdır): tanımlı değilse o kontrol
# atlanır, yanlış alarm üretilmez.
CANONICAL_ID = CFG.get("project_id")
TEMPLATE_SIZES = {324, 2078}  # the app's blank purpose.md / schema.md
DROP_ALERT = int(_GATES.get("page_drop", 3))
QUIET_MIN = int(_GATES.get("quiet_minutes", 5))
TMP_MAX_MIN = int(_GATES.get("tmp_max_minutes", 15))
LOCK_MAX_MIN = int(_GATES.get("lock_max_minutes", 30))
# The mirrors come from the settings (default: every remote of the wiki repo); no name is built in.
REMOTES = tuple(wikiconfig.mirror_remotes(CFG, WIKI))
# raw/evidence holds offline copies of what a source's decisions rely on (never ingested: the app
# only watches raw/sources). It is staged so the copies reach the same off-machine mirrors.
STAGE_PATHS = ("wiki", "raw/sources", "raw/evidence", ".llm-wiki/project.json")

CODE_SPAN = re.compile(r"```.*?```|`[^`\n]*`", re.S)

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


ENGINE_HOOK = Path(__file__).resolve().parent / 'wiki-hooks' / 'pre-commit'


def own_hook(path: Path) -> bool:
    """The hook this engine release installs (install.py copies wiki-hooks/ into <wiki>/.githooks/)."""
    try:
        return path.read_bytes().replace(b'\r\n', b'\n') == ENGINE_HOOK.read_bytes().replace(b'\r\n', b'\n')
    except OSError:
        return False


def git(*args: str, index_file: Path | None = None, extra_env: dict | None = None):
    env = os.environ.copy()
    if index_file is not None:
        env['GIT_INDEX_FILE'] = str(index_file)
    env.update(extra_env or {})
    return subprocess.run(
        ["git", "-C", str(WIKI), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env,
    )


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def queues_busy() -> str | None:
    """Return a reason string when the app still has queued work, else None."""
    checks = (("ingest-queue.json", None), ("file-change-queue.json", "tasks"), ("dedup-queue.json", None))
    for name, key in checks:
        p = WIKI / ".llm-wiki" / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            return f"{name} unreadable ({exc.__class__.__name__})"
        if key:
            n = len(data.get(key, [])) if isinstance(data, dict) else 0
        else:
            n = len(data) if isinstance(data, (list, dict)) else 0
        if n:
            return f"{name}: {n} pending"
    return None


def tmp_residue() -> list[str]:
    """Fresh *.tmp files only: the app writes its state atomically through temp files, so a RECENT
    one means a write is in flight. Older ones are crash residue (the app leaves them behind -
    measured 16-18 h old here) and gating on those would make this check a permanent no-op."""
    now = time.time()
    return sorted(
        p.name for p in (WIKI / ".llm-wiki").glob("*.tmp")
        if (now - p.stat().st_mtime) / 60.0 < TMP_MAX_MIN
    )


def quiet_minutes() -> float:
    newest = 0.0
    for base in (WIKI / "wiki", WIKI / "raw"):
        for p in base.rglob("*"):
            if p.is_file():
                try:
                    newest = max(newest, p.stat().st_mtime)
                except OSError:
                    pass
    return (time.time() - newest) / 60.0 if newest else 1e9


def page_files() -> list[Path]:
    return sorted((WIKI / "wiki").rglob("*.md"))


def safety_alerts(pages: int) -> list[str]:
    alerts: list[str] = []
    proj = read_json(WIKI / ".llm-wiki" / "project.json", {})
    pid = proj.get("id") if isinstance(proj, dict) else None
    if CANONICAL_ID and pid != CANONICAL_ID:
        alerts.append(f".llm-wiki/project.json id={pid} != canonical {CANONICAL_ID} (project re-initialised)")
    for name in ("purpose.md", "schema.md"):
        p = WIKI / name
        if p.exists() and p.stat().st_size in TEMPLATE_SIZES:
            alerts.append(f"{name} is the app's blank template ({p.stat().st_size} B) - Create Project over the folder?")
    baseline = read_json(STATE, {}).get("pages", 0)
    if baseline and pages <= baseline - DROP_ALERT:
        alerts.append(f"page count {pages} vs baseline {baseline} ({pages - baseline}) - data-loss signal")
    return alerts


def integrity():
    """(unique stems, duplicate-stem map, dangling-link map) computed from the files on disk."""
    stems: dict[str, list[str]] = {}
    for p in page_files():
        stems.setdefault(p.stem, []).append(str(p.relative_to(WIKI)))
    dups = {k: v for k, v in stems.items() if len(v) > 1}
    known = set(stems)
    dangling: dict[str, int] = {}
    for p in page_files():
        body = CODE_SPAN.sub(" ", p.read_text(encoding="utf-8", errors="ignore"))
        for m in re.findall(r"\[\[([^\]]+)\]\]", body):
            t = m.split("|")[0].split("#")[0].strip()
            if t.endswith(".md"):
                t = t[:-3]
            t = t.rsplit("/", 1)[-1]
            if t and t not in known:
                dangling[t] = dangling.get(t, 0) + 1
    return len(stems), dups, dangling


def mirror_state() -> dict:
    out = {}
    head = git('rev-parse', 'HEAD')
    for remote in REMOTES:
        actual = git('ls-remote', '--exit-code', remote, 'refs/heads/main')
        if head.returncode or actual.returncode:
            out[remote] = {'state': 'unknown', 'error': actual.stderr.strip() or 'Remote or HEAD unavailable'}
            continue
        rows = actual.stdout.splitlines()
        if len(rows) != 1 or len(rows[0].split()) != 2:
            out[remote] = {'state': 'unknown', 'error': 'Remote returned an unsupported reference'}
            continue
        revision, ref = rows[0].split()
        if ref != 'refs/heads/main' or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', revision):
            out[remote] = {'state': 'unknown', 'error': 'Invalid remote revision'}
        elif revision == head.stdout.strip():
            out[remote] = {'state': 'fresh', 'revision': revision}
        elif git('merge-base', '--is-ancestor', revision, 'HEAD').returncode == 0:
            out[remote] = {'state': 'behind', 'revision': revision}
        else:
            out[remote] = {'state': 'unknown', 'revision': revision, 'error': 'Remote diverged or ancestry is unavailable'}
    return out


def retry_mirrors() -> dict:
    states = mirror_state()
    for remote, status in states.items():
        if status['state'] == 'behind':
            pushed = git('push', remote, 'HEAD:refs/heads/main')
            if pushed.returncode:
                status['error'] = pushed.stderr.strip() or 'Push failed'
    refreshed = mirror_state()
    for remote, status in states.items():
        if status.get('error') and refreshed[remote]['state'] != 'fresh':
            refreshed[remote]['error'] = status['error']
    return refreshed


def app_commit(pages: list[Path]) -> tuple[str, str]:
    """Commit the app's changes under STAGE_PATHS. Returns (short sha, "OK ..." line) or ("", "!! ...")."""
    from workflow_store import WorkflowStore, WorkflowError
    from workflow_paths import checked_path
    try:
        journal = checked_path(AUDIT_DIR, 'workflow.sqlite')
        if journal.exists():
            with WorkflowStore(journal, read_only=True) as store:
                if store.db.execute("SELECT 1 FROM operations WHERE state IN ('applying','recovery_required') LIMIT 1").fetchone():
                    return '', '!! auto-commit blocked: source application or recovery is unfinished'
    except (RuntimeError, OSError, ValueError) as exc:
        return '', f'!! auto-commit blocked: workflow unavailable ({type(exc).__name__})'
    run_own_hook = False
    for hook in ('pre-commit', 'prepare-commit-msg', 'commit-msg'):
        resolved = git('rev-parse', '--git-path', f'hooks/{hook}')
        if resolved.returncode:
            return '', '!! auto-commit blocked: Git hook location cannot be verified'
        path = Path(resolved.stdout.strip())
        if not path.is_absolute():
            path = WIKI / path
        if hook == 'pre-commit' and path.exists() and own_hook(path):
            run_own_hook = True
        elif path.exists():
            return '', f'!! auto-commit blocked: {hook} is not the engine\'s own hook and may change the index; hook and user work preserved; commit manually'
    resolved = git('rev-parse', '--path-format=absolute', '--git-path', 'index')
    if resolved.returncode:
        return '', '!! auto-commit blocked: index location cannot be verified'
    shared_index = Path(resolved.stdout.strip())
    index_lock = shared_index.with_name(shared_index.name + '.lock')
    try:
        lock = index_lock.open('xb')
    except FileExistsError:
        return '', '!! auto-commit blocked: native index.lock exists; lock and user staging preserved'
    except OSError as exc:
        return '', f'!! auto-commit blocked: native index lock unavailable ({type(exc).__name__})'
    # Native Git writers cannot accept staging while this lock is held. Never
    # stage/reset the shared index: every Git mutation uses a private snapshot.
    publish_started = False
    published = False
    tmp = None
    try:
        tmp = Path(tempfile.mkdtemp(prefix='wiki-commit-', dir=shared_index.parent))
        index_file = tmp / 'index'
        if shared_index.exists():
            shutil.copyfile(shared_index, index_file)
        baseline_head = git('rev-parse', 'HEAD')
        if baseline_head.returncode:
            return '', '!! auto-commit blocked: unreadable HEAD'
        staged = git('diff', '--cached', '--quiet', index_file=index_file)
        if staged.returncode != 0:
            return '', '!! auto-commit blocked: pre-existing staged work or unreadable index; staging preserved'
        st = git('add', '-A', '--', *STAGE_PATHS, index_file=index_file)
        if st.returncode:
            return '', f'!! auto-commit: git add failed: {st.stderr.strip()}'
        if run_own_hook:
            # The engine's hook normalizes link form in staged pages and re-stages only those, into
            # this private index. It runs before the tree is captured; the commit then skips hooks.
            ran = git('hook', 'run', 'pre-commit', index_file=index_file, extra_env={
                'LLMWIKI_AUDIT_DIR': str(ENGINE_HOOK.parent.parent), 'PYTHONDONTWRITEBYTECODE': '1',
                'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')})
            if ran.returncode:
                return '', f'!! auto-commit blocked: the engine\'s pre-commit hook failed (exit {ran.returncode}); nothing committed'
        sha, message, publish_started = _commit_index(pages, baseline_head, index_file, skip_hooks=run_own_hook)
        if not sha:
            if publish_started:
                message += f'; native lock and private snapshot retained at {tmp}'
            return sha, message
        # Only a successful private commit is installed, under the same native
        # lock. No checkout/worktree refresh, comparison/reset or advisory lock.
        publish_started = True
        lock.write(index_file.read_bytes())
        lock.flush()
        os.fsync(lock.fileno())
        lock.close()
        os.replace(index_lock, shared_index)
        published = True
        return sha, message
    except OSError as exc:
        retained = f'; native lock and private snapshot retained at {tmp}' if publish_started else ''
        return '', f'!! auto-commit recovery required: native index operation unavailable ({type(exc).__name__}); shared index preserved{retained}'
    finally:
        lock.close()
        if not publish_started:
            index_lock.unlink()
        if tmp is not None and (not publish_started or published):
            shutil.rmtree(tmp)


def _commit_index(pages: list[Path], baseline_head, index_file: Path, skip_hooks: bool = False) -> tuple[str, str, bool]:
    """Commit captured index bytes, never refresh them from the worktree."""
    tree = git('write-tree', index_file=index_file)
    if tree.returncode:
        return '', '!! auto-commit blocked: private index tree cannot be captured', False
    ns = git("diff", "--cached", "--name-only", "--diff-filter=A", "--", "raw/sources", index_file=index_file)
    new_sources = [l.strip() for l in ns.stdout.splitlines() if l.strip()]
    numstat = git("diff", "--cached", "--numstat", "--", *STAGE_PATHS, index_file=index_file)
    files = [l for l in numstat.stdout.splitlines() if l.strip()]
    added = sum(int(r.split("\t")[0]) for r in files if r.split("\t")[0].isdigit())
    removed = sum(int(r.split("\t")[1]) for r in files if r.split("\t")[1].isdigit())
    n_stems, dups, dangling = integrity()

    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    msg = [
        f"Wiki auto-commit {stamp}",
        "",
        f"Sources ingested: {len(new_sources)}",
        *[f"- {s}" for s in new_sources[:10]],
        *([f"- ... and {len(new_sources) - 10} more"] if len(new_sources) > 10 else []),
        "",
        f"Changes: {len(files)} files, +{added}/-{removed} lines.",
        f"Pages on disk: {len(pages)} ({n_stems} unique stems, {len(dups)} duplicate stem(s), "
        f"{len(dangling)} unresolved link target(s)).",
        "",
        "Committed by ~/.llmwiki-audit/wiki_autocommit.py (the desktop app generates pages but never commits).",
    ]
    cm = git("commit", *(["--no-verify"] if skip_hooks else []), "-m", "\n".join(msg), index_file=index_file)
    if cm.returncode != 0:
        current = git('rev-parse', 'HEAD')
        uncertain = current.returncode != 0 or current.stdout != baseline_head.stdout
        return '', f'!! auto-commit recovery required: commit failed; shared staging preserved: {cm.stderr.strip()}', uncertain
    revision = git('rev-parse', 'HEAD')
    if revision.returncode:
        return '', '!! auto-commit recovery required: committed HEAD cannot be verified', True
    identity = git('show', '-s', '--format=%T%n%P', revision.stdout.strip())
    if identity.returncode or identity.stdout.splitlines() != [tree.stdout.strip(), baseline_head.stdout.strip()]:
        return '', '!! auto-commit recovery required: HEAD no longer matches the captured tree and parent; shared staging preserved', True
    shortened = git('rev-parse', '--short', revision.stdout.strip())
    if shortened.returncode:
        return '', '!! auto-commit recovery required: committed revision cannot be inspected', True
    sha = shortened.stdout.strip()
    head = new_sources[0] if len(new_sources) == 1 else f"{len(new_sources)} sources"
    return sha, f"OK wiki commit {sha}: {len(files)} files (+{added}/-{removed}), {head}", True


def main() -> int:
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    force = "--force" in argv

    # Only the paths this script stages count. Checked over the whole repository, an untracked
    # folder elsewhere (a tool's .serena/ config dir) made every run attempt an empty commit, which
    # git refused - delivered as "commit failed" on 2026-09-25 and 2026-09-26.
    dirty = git("status", "--porcelain", "--", *STAGE_PATHS).stdout.strip()

    pages = page_files()
    alerts = safety_alerts(len(pages))
    if alerts:
        print(f"!! wiki auto-commit: {len(alerts)} safety alert(s) - nothing committed")
        for a in alerts:
            print(f"   - {a}")
        print(f"   inspect: python {AUDIT_DIR}/wiki_audit.py  |  git -C {WIKI} status --short")
        return 1

    blocked = None
    quiet = quiet_minutes()
    busy = queues_busy()
    if busy:
        blocked = f"app queue not empty ({busy})"
    else:
        residue = tmp_residue()
        if residue:
            blocked = f"fresh .tmp write in flight ({residue[0]})"
    if blocked is None and quiet < QUIET_MIN and not force:
        blocked = f"quiet period {quiet:.1f} min < {QUIET_MIN} min (the app may still be writing)"
    if blocked:
        if dry:
            print(f"[dry-run] blocked: {blocked}")
        return 0

    if dry:
        if dirty:
            n_stems, dups, dangling = integrity()
            print(f"[dry-run] would commit {len(dirty.splitlines())} changed path(s); "
                  f"{len(pages)} pages, {n_stems} unique stems, {len(dups)} duplicate stem(s), "
                  f"{len(dangling)} unresolved link target(s); quiet {quiet:.1f} min")
        return 0

    from candidate_apply import operation_lock, ApplyRefused
    lock = operation_lock(AUDIT_DIR, timeout=0.2)
    try:
        lock.__enter__()
    except (ApplyRefused, OSError) as exc:
        print(f'!! auto-commit blocked: {exc}')
        return 1
    try:
        lines: list[str] = []
        if dirty:
            sha, line = app_commit(pages)
            if not sha:
                print(line)
                return 1
            lines.append(line)
        mirrors = retry_mirrors()
        stale = {remote: status for remote, status in mirrors.items() if status['state'] != 'fresh'}
        summary = 'mirrors: ' + (' '.join(f"{remote}={status['state']}" for remote, status in mirrors.items()) or 'none')
        if lines:
            lines[-1] += ' | ' + summary
            print('\n'.join(lines))
        elif stale:
            print('!! ' + summary)
        if stale:
            print(f'!! mirror not refreshed: {stale}; existing commit preserved; retry will not create a duplicate commit')
            return 1
        return 0
    finally:
        lock.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())

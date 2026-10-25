"""Collect finished agent conversations since the last harvest, for wiki source candidates.

WHY: decisions made in a session reach the wiki only if someone writes them into a source. People
forget, and work happens in several agents. This script is the deterministic half of the nightly
"Wiki Session Harvest" job: it gathers what was said since the last successful harvest, from every
enabled agent (Hermes, Codex, Claude Code, Antigravity), into one inbox run folder. An agent that
is not installed on this PC is reported as "not found" and skipped; the others still run. An agent
whose history exists but cannot be read is reported as "UNREADABLE" and the run is "partial": that
agent's cursor stays where it was, so its conversations wait for a later run, while the others are
collected and can be completed. Neither case stops the other agents. The job's
agent step then reads that folder and drafts candidate sources (decision records plus evidence).
Nothing here writes to the wiki; candidates reach raw/sources/ only through
`wiki_candidates.py approve`, which the owner triggers.

HOW IT AVOIDS REPEATS: one cursor per agent (a timestamp) in <audit>/harvest-state.json. A run
collects messages newer than the cursor and older than the settle window, so a conversation still
in progress is taken next time. The cursor moves only when the run is committed
(`--commit <run-id>`, the agent step's last action). A failed or interrupted run leaves the cursor
where it was, so the next run collects the same messages again. A PC that was off for days is
covered by one run: the window is "since the cursor", not "today".

RUN BUDGET: everything the agent step must read in one run (sources index plus conversation
files) stays within max_run_chars, so a backlog never outgrows the drafting model's working
context. Pending conversations are taken oldest first and whole; one that no longer fits waits,
with every later one, for the next run. A single conversation larger than the budget is taken in
time order up to the budget and continued next run. Conversations taken while others wait are
recorded in harvest-state.json `done` (conversation -> time read through), so the next run skips
exactly what was read and nothing is dropped.

WHAT IS SKIPPED: subagent/worker conversations (their result reaches the parent conversation),
scheduled-job and one-shot runs, headless `codex exec` runs, and tool output. Only what the user
and the assistant said is kept. Codex conversations the owner archived (moved to
`archived_sessions/`) are read like live ones. Hermes stores a message again each time it compacts
a conversation in place; those copies are read once.
Messages the agent app writes into the user's turn are dropped too, because they are not the
owner speaking and can fill a long conversation many times over: context-compaction summaries,
subagent and background-job reports, hook feedback, goal check-ins, loaded skill text, and
embedded images. A skill or slash-command call keeps only the instruction the owner typed.

LONG CONVERSATIONS: every owner message is kept. If a conversation is still over max_chars,
assistant messages are shortened step by step; if that is not enough, the conversation is split
into ordered parts (`...-part2.md`). Nothing is dropped silently: run.json records each
conversation's `assistant_clip` and `parts`, and the agent step reports them.

OUTPUT (prints one JSON line last, for the Hermes cron pre-run gate):
  {"wakeAgent": false}                       nothing new -> the job costs nothing
  {"wakeAgent": true, "context": {...}}      run folder, session count, per-agent status
  "status": "partial" marks a run in which an enabled agent's history could not be read

USAGE
  python wiki_session_harvest.py                 collect into a new inbox run (pre-run script)
  python wiki_session_harvest.py --status        cursors and per-agent availability, no writes
  python wiki_session_harvest.py --last-run      the newest host-bound run and its outcome (JSON), no writes
  python wiki_session_harvest.py --commit <run>  advance the cursors recorded by that run
  python wiki_session_harvest.py --since <ISO>   collect from a given time (test / backfill);
                                                 does not change any cursor on its own

SETTINGS (settings.json, key "harvest"; all optional):
  agents          {"hermes": true, "codex": true, "claude": true, "antigravity": true}
  settle_minutes  30     messages younger than this wait for the next run
  max_chars       60000  size of one conversation file; longer ones are shortened, then split
  max_run_chars   250000 everything one run asks the agent step to read; the rest waits
  first_run_days  2      look-back when an agent has no cursor yet
"""
from __future__ import annotations

import argparse
import hashlib
import math
import uuid
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wikiconfig  # noqa: E402

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULTS = {"agents": {"hermes": True, "codex": True, "claude": True, "antigravity": True},
            "settle_minutes": 30, "max_chars": 60000, "max_run_chars": 250000, "first_run_days": 2}
ASSISTANT_CLIP = 2500           # one assistant message; decisions are stated, not dumped
CLIP_STEPS = (2500, 1200, 600, 300)   # tried in order until a conversation fits max_chars
USER_CLIP = 8000                # a pasted document is not a decision; its first part is enough
INJECTED = re.compile(r"^\s*(# AGENTS\.md instructions|<environment_context>|<user_instructions>|"
                      r"<system-reminder>|<command-name>|<local-command|Caveat:)", re.I)
# Text an agent app writes into the user's turn (not the owner speaking). Matched at the start.
APP_NOTE = re.compile(r"^\s*(\[CONTEXT COMPACTION|\[IMPORTANT: Background process|\[ASYNC DELEGATION|"
                      r"\[Request interrupted|Another Claude session sent a message|Stop hook feedback|"
                      r"A session-scoped Stop hook|Goal check-in:|<task-notification|"
                      r"<artifact-content-authored-by-others|This session is being continued from a previous|"
                      r"Base directory for this skill:|Skill /\S+ was loaded)")
DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]{200,}")
SKILL_CALL = re.compile(r"^\[IMPORTANT: The user has invoked the \"([^\"]+)\" skill.*?"
                        r"(?:The user has provided the following instruction alongside the skill "
                        r"invocation: (.*))?$", re.S)
COMMAND_CALL = re.compile(r"^\s*<command-message>.*?<command-name>([^<]*)</command-name>"
                          r"(?:\s*<command-args>(.*?)</command-args>)?", re.S)
STEER = re.compile(r"^\[OUT-OF-BAND USER MESSAGE[^\n]*\n(.*?)\n\[/OUT-OF-BAND USER MESSAGE\]\s*$", re.S)


def ts(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).astimezone().isoformat(timespec="seconds")


def text_of(content) -> str:
    """Plain text from a message content that may be a string or a list of typed parts."""
    if isinstance(content, str) and content.startswith("\x00json:"):   # Hermes multimodal row
        try:
            content = json.loads(content[len("\x00json:"):])
        except ValueError:
            return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") in ("text", "input_text", "output_text"):
                parts.append(p.get("text") or "")
        return "\n".join(x for x in parts if x)
    return ""


def owner_text(text: str) -> str:
    """What the owner actually said in a user turn; "" when the turn is an app-written note."""
    text = DATA_URI.sub("[image omitted]", text or "").strip()
    if APP_NOTE.match(text):
        return ""
    m = SKILL_CALL.match(text)
    if m:
        return f"/{m.group(1)} {(m.group(2) or '').strip()}".strip()
    m = COMMAND_CALL.match(text)
    if m:
        return f"{m.group(1).strip()} {(m.group(2) or '').strip()}".strip()
    m = STEER.match(text)
    if m:
        return m.group(1).strip()
    return text


# ---- per-agent readers: each yields (conversation id, label, [(t, role, text)]) ----------------

def read_hermes(home: Path, since: float, until: float):
    db = home / "state.db"
    if not db.exists():
        raise FileNotFoundError(f"{db} not found")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    cols = {r[1] for r in con.execute("PRAGMA table_info(messages)")}
    app_rows = ""                                  # older Hermes versions lack these columns
    if "_compressed_summary" in cols:
        app_rows += " AND COALESCE(m._compressed_summary, 0) = 0"
    if "display_kind" in cols:
        app_rows += (" AND COALESCE(m.display_kind, '') NOT IN ('async_delegation_complete', "
                     "'process_complete', 'model_switch', 'auto_continue')")
    rows = con.execute(
        f"""SELECT s.id, COALESCE(s.title, ''), m.timestamp, m.role, m.content
           FROM messages m JOIN sessions s ON s.id = m.session_id
           WHERE m.timestamp > ? AND m.timestamp <= ? AND m.role IN ('user', 'assistant')
             AND s.parent_session_id IS NULL
             AND COALESCE(s.source, '') NOT IN ('cron', 'oneshot')
             AND COALESCE(s.title, '') NOT LIKE 'Subagent%'{app_rows}
           ORDER BY s.id, m.timestamp""", (since, until)).fetchall()
    con.close()
    # In-place compaction keeps the archived originals beside their re-inserted copies, all with the
    # same timestamp, role and content, so one message can be stored two or three times. Read each
    # once. Do not filter on Hermes' active/compacted flags instead: when compaction lands inside a
    # turn, the owner's message survives only in archived rows (its visible copy is merged into the
    # compaction summary, dropped above), and a visibility filter would lose it.
    convs: dict[str, tuple[str, list]] = {}
    seen: set[tuple] = set()
    for sid, title, t, role, content in rows:
        if (sid, t, role, content) in seen:
            continue
        seen.add((sid, t, role, content))
        convs.setdefault(sid, (title, []))[1].append((float(t), role, text_of(content or "")))
    for sid, (title, msgs) in convs.items():
        yield sid, title or sid, msgs


def codex_session_files(root: Path) -> list[Path]:
    """Every Codex session file under `sessions/` and `archived_sessions/`, plain or compressed.

    Codex keeps a rollout as `*.jsonl` and later stores older ones zstd-compressed as `*.jsonl.zst`.
    A `*.jsonl`-only glob skipped every compressed session without a trace; the watchdog compares
    this list against the folder, so a new file form shows up as an alert instead of a silent gap."""
    files: list[Path] = []
    for sub in ("sessions", "archived_sessions"):
        folder = root / sub
        if folder.is_dir():
            files += [*folder.rglob("*.jsonl"), *folder.rglob("*.jsonl.zst")]
    return sorted(files)


def codex_session_id(f: Path) -> str:
    """One id for a rollout whether it is stored plain or compressed."""
    return f.name.removesuffix(".zst").removesuffix(".jsonl")


def codex_lines(f: Path):
    """Lines of one Codex rollout; a compressed rollout needs the zstd decoder of Python 3.14+."""
    if f.name.endswith(".zst"):
        try:
            from compression import zstd
        except ImportError as exc:
            raise HarvestError('A Codex session is zstd-compressed and this Python has no zstd decoder '
                               '(Python 3.14+ is needed); the reader cannot be marked complete') from exc
        with zstd.open(f, "rt", encoding="utf-8", errors="replace") as fh:
            yield from fh
    else:
        with f.open(encoding="utf-8", errors="replace") as fh:
            yield from fh


def read_codex(root: Path, since: float, until: float):
    """Codex home: live `sessions/` plus `archived_sessions/` (archiving moves the file there)."""
    if not (root / "sessions").is_dir():
        raise FileNotFoundError(f"{root / 'sessions'} not found")
    seen: set[str] = set()
    for f in codex_session_files(root):
        sid = codex_session_id(f)
        if sid in seen:
            continue
        seen.add(sid)
        if f.stat().st_mtime <= since:
            continue
        msgs, meta = [], {}
        for line in codex_lines(f):
            try:
                d = json.loads(line)
            except ValueError as exc:
                raise HarvestError('Codex session JSON is unreadable; the reader cannot be marked complete') from exc
            p = d.get("payload") or {}
            if d.get("type") == "session_meta":
                meta = p
                continue
            if p.get("type") != "message" or p.get("role") not in ("user", "assistant"):
                continue
            t = ts(d.get("timestamp"))
            if t is None or not (since < t <= until):
                continue
            msgs.append((t, p["role"], text_of(p.get("content"))))
        if meta.get("originator") == "codex_exec" or not msgs:
            continue
        yield sid, f"codex {Path(meta.get('cwd') or '').name or sid}", msgs


def read_claude(root: Path, since: float, until: float):
    if not root.is_dir():
        raise FileNotFoundError(f"{root} not found")
    for f in sorted(root.glob("*/*.jsonl")):          # top level only: subagents/ are workers
        if f.stat().st_mtime <= since:
            continue
        msgs, title = [], ""
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError as exc:
                    raise HarvestError('Claude session JSON is unreadable; the reader cannot be marked complete') from exc
                if d.get("type") == "custom-title":
                    title = d.get("customTitle") or title
                if d.get("type") not in ("user", "assistant") or d.get("isSidechain"):
                    continue
                if d.get("type") == "user" and (
                        d.get("isMeta") or d.get("isCompactSummary")
                        or (d.get("origin") or {}).get("kind") in ("task-notification", "peer")):
                    continue                           # written by Claude Code, not the owner
                t = ts(d.get("timestamp"))
                if t is None or not (since < t <= until):
                    continue
                m = d.get("message") or {}
                msgs.append((t, m.get("role") or d["type"], text_of(m.get("content"))))
        if msgs:
            yield f.stem, f"claude {title or f.parent.name}", msgs


USER_REQUEST = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.S)


def read_antigravity(root: Path, since: float, until: float):
    """Antigravity: brain/<id>/.system_generated/logs/transcript_full.jsonl, one step per line.

    Kept: USER_INPUT steps (only the text inside <USER_REQUEST>, not the injected metadata) and
    PLANNER_RESPONSE steps that carry text. Tool calls, tool results (GENERIC) and thinking are
    dropped. Subagent conversations (nesting_depth > 0 in conversation_summaries.db) are skipped.
    """
    brain = root / "brain"
    if not brain.is_dir():
        raise FileNotFoundError(f"{brain} not found")
    titles, nested = {}, set()
    db = root / "conversation_summaries.db"
    if db.exists():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for cid, title, depth, parent in con.execute(
                "SELECT conversation_id, COALESCE(title, ''), COALESCE(nesting_depth, 0), "
                "COALESCE(parent_conversation_id, '') FROM conversation_summaries"):
            titles[cid] = title
            if depth or parent:
                nested.add(cid)
        con.close()
    for f in sorted(brain.glob("*/.system_generated/logs/transcript_full.jsonl")):
        cid = f.parents[2].name
        if cid in nested or f.stat().st_mtime <= since:
            continue
        msgs = []
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError as exc:
                    raise HarvestError('Unreadable Antigravity history record') from exc
                kind, text = d.get("type"), d.get("content")
                if kind == "USER_INPUT" and isinstance(text, str):
                    m = USER_REQUEST.search(text)
                    role, text = "user", (m.group(1) if m else text)
                elif kind == "PLANNER_RESPONSE" and isinstance(text, str) and text.strip():
                    role = "assistant"
                else:
                    continue
                t = ts(d.get("created_at"))
                if t is None or not (since < t <= until):
                    continue
                msgs.append((t, role, text))
        if msgs:
            yield cid, f"antigravity {titles.get(cid) or cid}", msgs


def agent_roots(cfg: dict) -> dict[str, Path]:
    home = Path.home()
    return {
        "hermes": wikiconfig.hermes_home(cfg),
        "codex": Path(os.environ.get("CODEX_HOME") or home / ".codex"),
        "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude") / "projects",
        "antigravity": home / ".gemini" / "antigravity",
    }


READERS = {"hermes": read_hermes, "codex": read_codex, "claude": read_claude,
           "antigravity": read_antigravity}


def blocks(msgs: list, clip: int) -> list[str]:
    out = []
    for t, role, text in msgs:
        text = owner_text(text) if role == "user" else DATA_URI.sub("[image omitted]", text or "").strip()
        if not text or (role == "user" and INJECTED.match(text)):
            continue
        limit = len(text) if role == "user" else clip
        if len(text) > limit:
            text = text[:limit] + " […]"
        out.append(f"### {role} · {iso(t)}\n\n{text}\n")
    return out


def render(label: str, msgs: list, max_chars: int) -> tuple[list[str], int]:
    """(files, assistant clip used). Owner messages are never dropped: assistant messages are
    shortened first, then the conversation is split into ordered parts of at most max_chars."""
    for clip in CLIP_STEPS:
        out = blocks(msgs, clip)
        if sum(len(b) + 1 for b in out) <= max_chars:
            break
    if not out:
        return [], clip
    parts, cur = [], []
    for b in out:
        if cur and sum(len(x) + 1 for x in cur) + len(b) > max_chars:
            parts.append(cur)
            cur = []
        cur.append(b)
    parts.append(cur)
    n = len(parts)
    files = [f"# {label}" + (f" (part {i} of {n})" if n > 1 else "") + "\n\n" + "\n".join(p)
             for i, p in enumerate(parts, 1)]
    return files, clip


def pack(pending: list, max_chars: int, budget: int, until: float) -> tuple[list, list, dict]:
    """Choose what one run reads: whole conversations, oldest first, within `budget` characters.
    Returns (conversations, waiting [(agent, id)], done {agent:id: time read through}).
    The first conversation is always taken; if it alone exceeds the budget, only its oldest
    messages that fit are taken (at least one), ending between two distinct timestamps."""
    taken, waiting, done, room = [], [], {}, budget
    for agent, cid, label, msgs in sorted(pending, key=lambda row: (row[3][0][0], row[0], str(row[1]))):
        if waiting:
            waiting.append((agent, cid))
            continue
        files, clip = render(label, msgs, max_chars)
        size = sum(len(text) for text in files)
        through = until
        if size > room:
            if taken:
                waiting.append((agent, cid))
                continue
            keep = fitting_prefix(label, msgs, max_chars, room)
            if keep < len(msgs):
                msgs, through = msgs[:keep], msgs[keep - 1][0]
                files, clip = render(label, msgs, max_chars)
                waiting.append((agent, cid))
        room -= size
        if files:
            taken.append((agent, cid, label, files, len(msgs), clip))
            done[f"{agent}:{cid}"] = through
    return taken, waiting, done


def fitting_prefix(label: str, msgs: list, max_chars: int, room: int) -> int:
    """Largest count of oldest messages whose files fit `room`, never splitting equal timestamps
    and never zero, so an oversized conversation still advances by at least one message."""
    def fits(count):
        return sum(len(text) for text in render(label, msgs[:count], max_chars)[0]) <= room
    low, high = 0, len(msgs)
    while low < high:
        middle = (low + high + 1) // 2
        if fits(middle):
            low = middle
        else:
            high = middle - 1
    boundary = lambda count: count == len(msgs) or msgs[count - 1][0] < msgs[count][0]
    keep = low
    while keep > 0 and not boundary(keep):
        keep -= 1
    if keep == 0:
        keep = 1
        while not boundary(keep):
            keep += 1
    return keep


def source_index(wiki: Path) -> str:
    """Title, scope line and decision headings of every current source: what candidates match."""
    lines = ["# Current wiki sources (decision headings)", ""]
    for f in sorted((wiki / "raw" / "sources").glob("*.md")):
        t = f.read_text(encoding="utf-8", errors="replace")
        title = next((l[2:].strip() for l in t.splitlines() if l.startswith("# ")), f.stem)
        decisions = [re.sub(r"\s+", " ", d) for d in
                     re.findall(r"^\*\*(\d+\.\s[\s\S]+?)\*\*", t, re.M)]
        lines.append(f"## {f.name}\n{title}")
        lines += [f"- {d}" for d in decisions]
        lines.append("")
    return "\n".join(lines)


class HarvestError(RuntimeError):
    pass


def load_state(path: Path) -> dict:
    if not path.exists():
        return {'cursors': {}}
    try:
        state = json.loads(path.read_bytes())
        if not isinstance(state, dict) or not isinstance(state.get('cursors'), dict):
            raise ValueError('Invalid cursor state')
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0
               for value in state['cursors'].values()):
            raise ValueError('Invalid cursor timestamp')
        done = state.get('done', {})
        if not isinstance(done, dict) or any(
                not isinstance(key, str) or ':' not in key or type(value) not in (int, float)
                or not math.isfinite(value) or value < 0 for key, value in done.items()):
            raise ValueError('Invalid conversation progress')
        return state
    except (OSError, ValueError) as exc:
        raise HarvestError('Existing harvest state is unreadable; preserve it and inspect before retry') from exc


READ_STATUS = re.compile(r"\d+ conversation\(s\)")


def bound_runs(audit: Path, home=None):
    """Host-bound runs, newest first, each with why it stopped and what its drafting session cost."""
    from workflow_paths import checked_path, identifier, PathRefused
    import harvest_attempts
    inbox = audit / "inbox"
    names = sorted((entry.name for entry in inbox.iterdir() if entry.is_dir()), reverse=True) if inbox.is_dir() else []
    for name in names:
        try:
            path = checked_path(audit, f"inbox/{identifier(name)}/run.json")
        except PathRefused:
            continue
        if not path.is_file():
            continue
        try:
            manifest = json.loads(path.read_bytes())
            if not isinstance(manifest, dict) or not manifest.get("execution_id"):
                continue
            attempt = harvest_attempts.describe(audit, name, manifest, home)
        except (ValueError, harvest_attempts.AttemptError) as exc:
            raise HarvestError(f"Run {name} has an unreadable run.json or attempt.json") from exc
        outcome = manifest.get("outcome") if isinstance(manifest.get("outcome"), dict) else {}
        yield {"run": name, "execution_id": manifest["execution_id"], "job_id": manifest.get("job_id"),
               "created": manifest.get("created"), "committed": manifest.get("committed") is True,
               "status": outcome.get("status"), "agents": manifest.get("agents") or {},
               "conversations": len(manifest.get("conversations") or []), **attempt}


def last_run(audit: Path, home=None) -> dict:
    for row in bound_runs(audit, home):
        return {"ok": True, **row}
    return {"ok": True, "run": None}


def finish_run(audit: Path, run_id: str, outcome: dict, store) -> dict:
    from candidate_apply import operation_lock, _atomic
    from workflow_paths import checked_path, identifier, PathRefused
    from owner_decisions import canonical
    try:
        identifier(run_id)
        if store.path.resolve() != checked_path(audit, 'workflow.sqlite').resolve():
            raise HarvestError('Harvest journal belongs to a different data root')
        with operation_lock(audit):
            run_path = checked_path(audit, f'inbox/{run_id}/run.json')
            manifest = json.loads(run_path.read_bytes())
            hashes = manifest.get('input_hashes')
            if not isinstance(hashes, dict) or not hashes:
                raise HarvestError('Run lacks captured input hashes')
            if not isinstance(outcome, dict) or set(outcome) != {
                    'execution_id', 'job_id', 'status', 'reviewed_inputs', 'candidate_refs', 'missing_evidence'}:
                raise HarvestError('Explicit host-validated drafting outcome is required')
            if outcome['status'] not in ('drafted', 'no_candidates') or not isinstance(outcome['missing_evidence'], list):
                raise HarvestError('Drafting was not completed')
            if any(not manifest.get(field) or outcome[field] != manifest[field] for field in ('execution_id', 'job_id')):
                raise HarvestError('Outcome is not bound to the collected execution')
            if outcome['reviewed_inputs'] != hashes:
                raise HarvestError('Not every captured input was reviewed')
            read = {agent for agent, status in manifest['agents'].items() if READ_STATUS.fullmatch(str(status))}
            if any(agent not in read for agent in manifest['cursors_to_commit']) or any(
                    str(key).split(':', 1)[0] not in read for key in manifest.get('done_to_commit') or {}):
                raise HarvestError('A source that was not read cannot advance its cursor')
            required = {name for row in manifest['conversations'] for name in row['files']}
            if not required.issubset(hashes):
                raise HarvestError('Manifest omits conversation parts')
            for name, digest in hashes.items():
                if name != 'sources-index.md' and not name.startswith('conversations/'):
                    raise HarvestError('Unexpected collection artifact')
                path = checked_path(audit, f'inbox/{run_id}/{name}')
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise HarvestError('Collected input changed or disappeared')
            refs = outcome['candidate_refs']
            if not isinstance(refs, list) or len(set(refs)) != len(refs) or any(
                    not isinstance(ref, str) or not ref.startswith(run_id + '/') for ref in refs):
                raise HarvestError('Invalid completion candidates')
            actual = {f'{run_id}/{folder.name}' for folder in checked_path(audit, f'inbox/{run_id}/candidates').iterdir()}
            if set(refs) != actual or bool(refs) != (outcome['status'] == 'drafted'):
                raise HarvestError('Candidate completion does not match captured artifacts')
            candidate_hashes = {}
            for ref in refs:
                from wiki_candidates import load_candidate, check_format
                folder, metadata = load_candidate(audit / 'inbox', ref)
                candidate_hashes[ref] = hashlib.sha256((folder / 'candidate.json').read_bytes()).hexdigest()
                if metadata['kind'] != 'retire':
                    source = (folder / 'source.md').read_bytes()
                    if check_format(source.decode('utf-8')):
                        raise HarvestError('Incomplete or invalid drafted candidate')
                    candidate_hashes[ref + ':source'] = hashlib.sha256(source).hexdigest()
            stable = {key: value for key, value in manifest.items() if key not in ('committed', 'outcome')}
            operation_id = hashlib.sha256(canonical({'harvest': run_id, 'data_root': str(audit.resolve())})).hexdigest()
            identity = {'operation_id': operation_id, 'domain': 'harvest', 'run_id': run_id,
                        'manifest_sha256': hashlib.sha256(canonical(stable)).hexdigest()}
            store.record_operation(identity)
            result = {**outcome, 'candidate_hashes': candidate_hashes}
            store.record_step(operation_id, 'draft-completion', result)
            state_path = checked_path(audit, 'harvest-state.json')
            state = load_state(state_path)
            cursors = dict(state['cursors'])
            for agent, cursor in manifest['cursors_to_commit'].items():
                if type(cursor) not in (int, float) or not math.isfinite(cursor) or cursor < 0:
                    raise HarvestError('Invalid captured cursor')
                cursors[agent] = max(cursors.get(agent, 0), cursor)
            done = dict(state.get('done', {}))
            for key, through in (manifest.get('done_to_commit') or {}).items():
                if not isinstance(key, str) or ':' not in key or type(through) not in (int, float) \
                        or not math.isfinite(through) or through < 0:
                    raise HarvestError('Invalid captured conversation progress')
                done[key] = max(done.get(key, 0), through)
            done = {key: through for key, through in done.items()
                    if through > cursors.get(key.split(':', 1)[0], 0)}
            state.update(cursors=cursors, last_commit={'run': run_id, 'status': result['status']})
            if done:
                state['done'] = done
            else:
                state.pop('done', None)
            encoded = canonical(state) + b'\n'
            if not state_path.exists() or state_path.read_bytes() != encoded:
                _atomic(state_path, encoded)
            manifest.update(committed=True, outcome=result)
            encoded = canonical(manifest) + b'\n'
            if run_path.read_bytes() != encoded:
                _atomic(run_path, encoded)
            if store.get_operation(operation_id)['state'] == 'collected':
                store.transition(operation_id, 'collected', 'drafted', result)
            return result
    except (OSError, ValueError, KeyError, TypeError, PathRefused) as exc:
        raise HarvestError('Run is incomplete or unsafe; cursors retained') from exc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--last-run", action="store_true")
    ap.add_argument("--commit", metavar="RUN_ID")
    ap.add_argument("--execution-id", help="Native plugin supplied occurrence, not model authority")
    ap.add_argument("--job-id", help="Native plugin supplied configured job")
    ap.add_argument("--host-outcome", action="store_true")
    ap.add_argument("--record-attempt", action="store_true",
                    help="Native plugin: store a run's start/end event (stdin: {run_id, event})")
    ap.add_argument("--runs", action="store_true", help="Every host-bound run with its stop reason and cost")
    ap.add_argument("--json", action="store_true", help="With --runs: print JSON")
    ap.add_argument("--home", help="Owning native profile")
    ap.add_argument("--since", help="ISO time; test or backfill, cursors are not read")
    args = ap.parse_args(argv)

    try:
        cfg = wikiconfig.load()
        wiki = wikiconfig.project_root(cfg)
    except wikiconfig.ConfigError as exc:
        print(f"!! {exc}")
        print(json.dumps({"wakeAgent": False}))
        return 1
    audit = wikiconfig.audit_dir(cfg)
    if args.host_outcome:
        from workflow_store import WorkflowStore, WorkflowError
        from workflow_paths import checked_path
        try:
            if cfg.get('harvest_workflow_enabled') is not True:
                raise HarvestError('Native harvest completion is not explicitly activated')
            if not args.home or not cfg.get('hermes_home') or Path(args.home).resolve() != Path(cfg['hermes_home']).resolve():
                raise HarvestError('Native outcome is not owned by the selected profile')
            request = json.loads(sys.stdin.buffer.read(300001))
            if not isinstance(request, dict) or set(request) != {'run_id', 'outcome'}:
                raise HarvestError('Unsupported native outcome fields')
            outcome = request['outcome']
            if outcome.get('execution_id') != args.execution_id or outcome.get('job_id') != args.job_id:
                raise HarvestError('Native occurrence binding changed')
            with WorkflowStore(checked_path(audit, 'workflow.sqlite')) as store:
                result = finish_run(audit, request['run_id'], outcome, store)
            print(json.dumps({'ok': True, 'status': result['status']}))
            return 0
        except (HarvestError, WorkflowError, OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({'ok': False, 'status': 'failed', 'reason': str(exc)}))
            return 1
    if args.record_attempt:
        import harvest_attempts
        try:
            if cfg.get('harvest_workflow_enabled') is not True:
                raise HarvestError('Native harvest is not explicitly activated')
            if not args.home or not cfg.get('hermes_home') or Path(args.home).resolve() != Path(cfg['hermes_home']).resolve():
                raise HarvestError('Attempt is not owned by the selected profile')
            request = json.loads(sys.stdin.buffer.read(20001))
            if not isinstance(request, dict) or set(request) != {'run_id', 'event'}:
                raise HarvestError('Unsupported attempt fields')
            harvest_attempts.record(audit, request['run_id'], args.execution_id, args.job_id, request['event'])
            print(json.dumps({'ok': True}))
            return 0
        except (HarvestError, harvest_attempts.AttemptError, OSError, ValueError, KeyError, TypeError) as exc:
            print(json.dumps({'ok': False, 'reason': str(exc)}))
            return 1
    if args.runs:
        try:
            rows = list(bound_runs(audit, cfg.get('hermes_home')))
        except (HarvestError, OSError, ValueError) as exc:
            print(json.dumps({'ok': False, 'error': str(exc)}))
            return 1
        if args.json:
            print(json.dumps({'ok': True, 'runs': rows}, ensure_ascii=False))
        else:
            for row in rows:
                spent = row['usage'] or {}
                cost = f"${spent['cost_usd']:.2f}" if isinstance(spent.get('cost_usd'), (int, float)) else '-'
                why = 'finished' if row['committed'] else (row['stop_reason'] or {}).get('detail', 'running')
                print(f"{row['run']}  {row['conversations']:>3} conv  {cost:>7}  {why}")
        return 0
    hcfg = {**DEFAULTS, **(cfg.get("harvest") or {})}
    hcfg["agents"] = {**DEFAULTS["agents"], **((cfg.get("harvest") or {}).get("agents") or {})}
    state_path = audit / "harvest-state.json"
    inbox = audit / "inbox"
    state = load_state(state_path)
    roots = agent_roots(cfg)

    if args.commit:
        print('!! Agent-side commit is disabled; only a verified native host outcome may finish processing')
        print(json.dumps({'wakeAgent': False, 'status': 'refused'}))
        return 1

    now = datetime.now().timestamp()
    until = now - 60 * int(hcfg["settle_minutes"])
    first = now - 86400 * int(hcfg["first_run_days"])

    if args.last_run:
        try:
            print(json.dumps(last_run(audit, cfg.get('hermes_home')), ensure_ascii=False))
            return 0
        except (HarvestError, OSError, ValueError) as exc:
            print(json.dumps({'ok': False, 'error': str(exc)}))
            return 1

    if args.status:
        for agent, on in hcfg["agents"].items():
            root = roots.get(agent)
            cur = state.get("cursors", {}).get(agent)
            print(f"{agent:11} {'on ' if on else 'off'} {'found' if root and root.exists() else 'NOT FOUND'} "
                  f"cursor={iso(cur) if cur else 'none (first run looks back ' + str(hcfg['first_run_days']) + ' days)'}")
        return 0

    if bool(args.execution_id) != bool(args.job_id):
        print(json.dumps({"wakeAgent": False, "status": "failed", "reason": "Both native binding fields are required"}))
        return 1
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:12]
    run_dir = inbox / run_id
    conversations, agents_report, cursors = [], {}, {}
    pending, starts = [], {}
    for agent, on in hcfg["agents"].items():
        if not on:
            agents_report[agent] = "off"
            continue
        since = ts(args.since) if args.since else float(state.get("cursors", {}).get(agent) or first)
        try:
            found = list(READERS[agent](roots[agent], since, until))
        except FileNotFoundError as exc:
            agents_report[agent] = f"not found ({exc})"
            continue
        except Exception as exc:  # a format change must be loud, never a silent skip
            agents_report[agent] = f"UNREADABLE ({exc.__class__.__name__}: {exc})"
            continue
        n = 0
        progress = {} if args.since else state.get("done", {})
        for cid, label, msgs in found:
            through = progress.get(f"{agent}:{cid}")
            msgs = sorted((m for m in msgs if through is None or m[0] > through), key=lambda m: m[0])
            if msgs and blocks(msgs, CLIP_STEPS[-1]):
                pending.append((agent, cid, label, msgs))
                n += 1
        agents_report[agent] = f"{n} conversation(s)"
        cursors[agent] = until
        starts[agent] = since

    index = source_index(wiki)
    conversations, waiting, done_next = pack(pending, int(hcfg["max_chars"]),
                                             int(hcfg["max_run_chars"]) - len(index), until)
    for agent in {agent for agent, _ in waiting}:
        cursors[agent] = starts[agent]
    done_next = {key: through for key, through in done_next.items()
                 if cursors[key.split(":", 1)[0]] < through}

    unread = any(str(value).startswith("UNREADABLE") for value in agents_report.values())
    if not conversations and not args.execution_id:
        print("harvest: nothing new since the last run | " + " | ".join(f"{a}: {r}" for a, r in agents_report.items()))
        if unread:
            print("!! an agent's history could not be read; its format may have changed")
        print(json.dumps({"wakeAgent": False, "status": "partial" if unread else "no_new_inputs"}))
        return 0

    (run_dir / "conversations").mkdir(parents=True, exist_ok=False)
    (run_dir / "candidates").mkdir(exist_ok=True)
    listing = []
    for agent, cid, label, files, count, clip in conversations:
        stem = f"{agent}-{re.sub(r'[^A-Za-z0-9_-]+', '-', cid)[:60]}"
        names = [f"{stem}.md" if len(files) == 1 else f"{stem}-part{i}.md" for i in range(1, len(files) + 1)]
        for name, md in zip(names, files):
            (run_dir / "conversations" / name).write_text(md, encoding="utf-8")
        listing.append({"agent": agent, "id": cid, "label": label, "file": f"conversations/{names[0]}",
                        "files": [f"conversations/{n}" for n in names], "parts": len(names),
                        "assistant_clip": clip, "messages": count})
    (run_dir / "sources-index.md").write_text(index, encoding="utf-8")
    rec = {"run": run_id, "created": iso(now), "window_until": iso(until),
           "since": {a: iso(ts(args.since) if args.since else float(state.get("cursors", {}).get(a) or first))
                     for a in cursors},
           "agents": agents_report, "conversations": listing,
           "execution_id": args.execution_id, "job_id": args.job_id, "project_id": cfg.get("project_id"),
           "input_hashes": {name: hashlib.sha256((run_dir / name).read_bytes()).hexdigest()
                            for name in ["sources-index.md", *[part for row in listing for part in row["files"]]]},
           "cursors_to_commit": {} if args.since else cursors,
           "done_to_commit": {} if args.since else done_next,
           "waiting": [{"agent": agent, "id": cid} for agent, cid in waiting], "committed": False}
    (run_dir / "run.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"harvest: run {run_id}: {len(listing)} conversation(s) | "
          + " | ".join(f"{a}: {r}" for a, r in agents_report.items()))
    if unread:
        print("!! an agent's history could not be read; its format may have changed. Its cursor stays, "
              "the other agents are collected")
    if waiting:
        print(f"   waiting: {len(waiting)} conversation(s) exceed this run's budget of "
              f"{hcfg['max_run_chars']} chars and are taken by the next run")
    for c in listing:
        if c["parts"] > 1 or c["assistant_clip"] < ASSISTANT_CLIP:
            print(f"   long: {c['label'][:60]}: {c['parts']} part(s), assistant messages cut at "
                  f"{c['assistant_clip']} chars")
    print(json.dumps({"wakeAgent": bool(conversations), "run_id": run_id,
                      "status": "partial" if unread else "collected" if conversations else "collected_empty", "context": {"run": run_id, "run_dir": str(run_dir),
                                                     "conversations": len(listing),
                                                     "agents": agents_report}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

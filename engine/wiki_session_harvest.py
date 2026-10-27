"""Conversation readers for Wiki Harvest: each enabled agent's stored history as conversations.

WHY: decisions made in a session reach the wiki only if someone writes them into a source, and
work happens in several agents. The readers here turn the history of every enabled agent (Hermes,
Codex, Claude Code, Antigravity) into conversations of (time, role, text) messages;
`harvest_pipeline.py` collects them into the harvest ledger and `harvest_night.py` reads and merges
them into drafts. Nothing here writes anywhere.

THE NAME: the file is named after the retired Wiki Session Harvest agent job (removed in 2.13.3),
whose collector and completion steps it held; the watchdog's Codex coverage finding names it too.

WHEN A READER FAILS: an agent that is not installed on this PC raises FileNotFoundError and is
reported as "not found"; a history that exists but cannot be read raises (HarvestError or the
parser's own error) and is reported as "UNREADABLE", never as an empty reader. Either way the
other agents are still read.

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
`render` shortens assistant messages step by step; if that is not enough, it splits the
conversation into ordered parts.

THE OLD CURSORS: `harvest-state.json` holds the retired job's per-agent cursors. `load_state` only
reads them: Wiki Harvest's first night starts each agent there, and its status shows them until a
night has run.

SETTINGS (settings.json, key "harvest"; all optional):
  agents          {"hermes": true, "codex": true, "claude": true, "antigravity": true}
  settle_minutes  30     messages younger than this wait for the next night
  max_chars       60000  size of one conversation part; longer ones are shortened, then split
  first_run_days  2      look-back when nothing was collected yet
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wikiconfig  # noqa: E402

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULTS = {"agents": {"hermes": True, "codex": True, "claude": True, "antigravity": True},
            "settle_minutes": 30, "max_chars": 60000, "first_run_days": 2}
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

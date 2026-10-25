from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sqlite3
import logging
import subprocess
import sys
from collections import deque
from pathlib import Path
from contextvars import ContextVar
from functools import wraps

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from ..engine_paths import resolve_engine_paths, EnginePathError
except ImportError:
    import importlib.util
    _paths_spec = importlib.util.spec_from_file_location(__name__ + "._engine_paths", Path(__file__).resolve().parents[1] / "engine_paths.py")
    _paths_module = sys.modules.get(_paths_spec.name)
    if _paths_module is None:
        _paths_module = importlib.util.module_from_spec(_paths_spec)
        sys.modules[_paths_spec.name] = _paths_module
        _paths_spec.loader.exec_module(_paths_module)
    resolve_engine_paths = _paths_module.resolve_engine_paths
    EnginePathError = _paths_module.EnginePathError

_log = logging.getLogger("hermes.plugins.wiki-automation")

router = APIRouter()
_SELECTED_PATHS = ContextVar("wiki_panel_selected_paths", default=None)

AUDIT_DIR = Path.home() / ".llmwiki-audit"
CHECKER_SOURCE = "checker"
_JOB_COLS = ("id, job_id, status, delivery_outcome, claimed_at, started_at, finished_at, "
             "scheduled_instant, error")
_ERROR_PREVIEW = 240

_EXPLAIN_TEXT = {
    'harvest_missing': 'Harvest engine is not installed.',
    'harvest_call_failed': 'Harvest status could not be read: {error}',
    'harvest_failed': 'Harvest status failed (exit {code}): {error}',
    'harvest_unsupported': 'Harvest status format is unsupported. Update the panel and engine.',
    'harvest_empty': 'Harvest status returned no adapters.',
    'harvest_last_failed': 'The last harvest run could not be read (exit {code}): {error}',
    'harvest_last_unsupported': 'The last harvest run format is unsupported. Update the panel and engine.',
    'auto_title': 'Wiki Automation',
    'auto_sub': 'watched project root and install status',
    'auto_missing': 'automation folder not found (~/.llmwiki-audit) — the package is not installed here',
    'auto_unreadable': 'automation settings unreadable',
    'auto_no_path': 'no path given',
    'auto_invalid': 'the folder is not a verified wiki root',
    'auto_write_failed': 'the settings file could not be written',
    'auto_call_failed': 'the automation checker failed: {error}',
    'auto_root_ok': 'verified',
    'auto_scan_root_bad': 'folder not found',
    'auto_not_folder': 'the scan root must be an absolute path to an existing folder',
    'auto_same_id': 'this folder carries the SAME project id but a different path (possibly a '
                    'copy/mirror) — making it the root degrades the backup check. Confirm to save.',
    'auto_root_bad': 'not verified',
    'auto_loud': 'with no root set the scripts do NOT stay silent — they alert',
    'jobs_file_unreadable': 'the scheduled jobs (cron/jobs.json) could not be read: {error}',
    'job_management_unavailable': 'This Hermes version does not offer the cron store lock, so job changes stay off.',
    'job_unknown_role': 'this job is not part of the engine',
    'job_unknown_action': 'unknown job action',
    'job_agent_fixed': 'the drafting job is created and removed only by the engine installer',
    'job_create_install': 'a missing job is created by the reviewed engine installation',
    'job_confirm': 'deleting a job needs confirmation',
    'job_changed': 'the job changed since this page read it - refresh and try again',
    'job_not_recorded': 'this job has no recorded ID',
    'job_paused_reason': 'Paused from the Wiki Automation panel.',
    'job_readback': 'the {action} was written but the store does not show it - refresh and check the job',
    'job_no_config': 'the automation folder could not be read - it carries the job definitions and the wiki root',
    'job_no_cron': 'the app cron store is not reachable from this process',
    'job_act_failed': 'the action failed: {error}',
    'job_read_failed': 'the scheduled jobs could not be read: {error}',
    'job_no_expr': 'no schedule was given',
    'job_bad_expr': 'the store refused that schedule: {error}',
    'job_no_catalogue': 'the engine job definition could not be read ({path})',
    'cand_missing': 'the engine has no candidate script (wiki_candidates.py) in the automation folder',
    'cand_read_failed': 'the candidates could not be read: {error}',
    'cand_bad_ref': 'a candidate is named <run>/<name>, with letters, digits, - and _ only',
    'cand_bad_action': 'unknown candidate action',
    'cand_confirm': "approving writes this source into the wiki's raw/sources folder, and the LLM Wiki "
                    'app will then ingest it, which costs model usage',
    'cand_no_reason': 'rejecting a candidate needs a reason',
    'cand_refused': 'the engine refused to {action} this candidate',
    'cand_fetch_partial': 'Some requested evidence could not be fetched; nothing was stored for it. The reason is shown under each request.',
    'owner_failed': 'Owner decision failed: {error}',
    'owner_timeout': 'Owner operation timed out; retry the same confirmation to inspect or finish that operation.',
    'owner_legacy_block': 'Legacy confirmation flags cannot authorize publication; use the protected owner review.',
    'cand_call_failed': 'the candidate script could not run: {error}',
    'run_none': 'no run recorded for this job',
    'run_live_false': 'this job is no longer defined',
    'wd_what_not_indexed': '{n} page(s) were reported outside index.md by a check the engine no longer runs: '
                           'LLM Wiki v0.6.12 keeps index.md as a bounded Recently Updated list of 200 entries.',
    'wd_not_indexed_title': 'Page outside the index (retired check)',
    'wd_not_indexed_action': 'Nothing to do: this line is history from before the check was retired.',
    'wd_what_wikilink': '{n} link(s) are written as paths ([[a/b]]); the app graph cannot see them as edges.',
    'wd_wikilink_title': 'Path-form link',
    'wd_wikilink_action': 'Rewrite them as [[page-name]].',
    'wd_what_dup': 'Two pages share the same name; [[link]] targets become ambiguous and the app graph cannot draw an edge.',
    'wd_dup_title': 'Two pages with one name',
    'wd_dup_action': 'Merge one into the other; keep a single page.',
    'wd_what_drift': 'The Hermes, Codex and Claude setups differ (skill content or plugin version).',
    'wd_drift_title': 'Agent setup drift',
    'wd_drift_action': 'Sync the difference or note that it is intentional.',
    'wd_what_mirror': "The local repo is {n} commit(s) ahead of the '{remote}' mirror; the backup is stale.",
    'wd_mirror_title': 'Backup mirror behind',
    'wd_mirror_action': 'Run the backup (git command below).',
    'wd_what_identity': "The app's active project id differs from the canonical id; per-project settings are read from the active one.",
    'wd_identity_title': 'Project id mismatch',
    'wd_identity_action': "Open the project from the app's own list; clean the stale id.",
    'wd_what_unresolvable': 'A body link points at a target that does not exist in the files.',
    'wd_unresolvable_title': 'Unresolvable link',
    'wd_unresolvable_action': 'Create the target page or fix the link.',
    'wd_what_isolated': '{n} page(s) have no links at all (graph degree 0); they sit alone in the app graph.',
    'wd_isolated_title': 'Page alone in the graph',
    'wd_isolated_action': 'Link those pages, or archive them if unneeded.',
    'wd_what_pages_down': 'Page count dropped {before} → {after}; a page may have been deleted.',
    'wd_pages_down_title': 'Page count dropped',
    'wd_pages_down_action': 'Check the deleted pages (baseline: state.json).',
    'wd_what_crash': 'The {fn} checker errored: {detail}',
    'wd_crash_title': 'Checker crashed',
    'wd_crash_action': 'A checker bug — it does not mean the wiki is broken; fix the code.',
    'wd_what_evidence_store': '{n} problem(s) in the evidence store: a stored file no longer matches its '
                              'sha256, a passage is gone, a manifest or used_by list is off, or a source '
                              'names a pinned version with no evidence.',
    'wd_evidence_store_title': 'Evidence store problem',
    'wd_evidence_store_action': 'Run evidence_capture.py --verify in the engine folder for the detail and the fix.',
    'wd_what_evidence_stale': '{n} evidence passage(s) no longer occur in the installed LLM Wiki or Hermes '
                              'version; the decisions pinned to them may be stale after an upgrade.',
    'wd_evidence_stale_title': 'Evidence out of date',
    'wd_evidence_stale_action': 'Run evidence_capture.py --recheck in the engine folder, review those decisions '
                                'and recapture the evidence at the new commit.',
    'wd_what_control_missing': '{name} is missing from the wiki folder; the file was deleted.',
    'wd_control_missing_title': 'Control file missing',
    'wd_control_missing_action': 'Restore the file from git (the command is in the line as written).',
    'wd_what_control_changed': '{name} differs from its version in git; the app may have rewritten it.',
    'wd_control_changed_title': 'Control file changed',
    'wd_control_changed_action': 'Compare it with git diff in the wiki folder and keep the right version.',
    'wd_what_control_template': "{name} has the size of the app's blank template; the Create Project flow may "
                                'have written over the project.',
    'wd_control_template_title': 'Control file reset to a template',
    'wd_control_template_action': 'Check .llm-wiki/project.json and the git history; restore the file from git '
                                  'if needed.',
    'wd_what_project_file_missing': '.llm-wiki/project.json is missing; the app will make a new project id and '
                                    'the project starts over.',
    'wd_project_file_missing_title': 'Project file missing',
    'wd_project_file_missing_action': 'Restore .llm-wiki/project.json from git.',
    'wd_what_project_file_unreadable': '.llm-wiki/project.json cannot be read; the file is damaged.',
    'wd_project_file_unreadable_title': 'Project file unreadable',
    'wd_project_file_unreadable_action': 'Restore .llm-wiki/project.json from git.',
    'wd_what_project_reregistered': 'The app registered this folder again under a new project id and shows that '
                                    'id as the active project.',
    'wd_project_reregistered_title': 'Folder registered again',
    'wd_project_reregistered_action': 'Check the content with git diff --stat, then restore .llm-wiki/project.json '
                                      'from git.',
    'wd_what_index_stale': '{n} page(s) are listed in index.md but have no file; a page may have been renamed.',
    'wd_index_stale_title': 'Index lists a missing page',
    'wd_index_stale_action': 'Check whether those pages were renamed; the app builds index.md from file names.',
    'wd_what_unsplit_ingest': '{n} page(s) hold an unsplit ingest output: the pages in their ---FILE: blocks '
                              'were never written.',
    'wd_unsplit_ingest_title': 'Unsplit ingest output',
    'wd_unsplit_ingest_action': 'Ingest that source again; do not point the broken links at other pages.',
    'wd_what_mcp_off': '"Enable MCP access" is off in the app; MCP tools answer "MCP access is disabled" although '
                       'clients show Connected.',
    'wd_mcp_off_title': 'MCP access is off',
    'wd_mcp_off_action': 'Turn it on: Settings → API + MCP → Enable MCP access → Save.',
    'wd_what_commit_backlog': '{n} wiki change(s) have not been committed for {hours} hours; the automatic commit '
                              'is not saving them.',
    'wd_commit_backlog_title': 'Changes not committed',
    'wd_commit_backlog_action': 'Check the Saving job (wiki auto-commit) and its last output.',
    'wd_what_drift_crash': 'drift_check crashed; it says nothing about the agent setups.',
    'wd_drift_crash_title': 'Setup check crashed',
    'wd_drift_crash_action': 'A checker bug, not a setup difference; run drift_check.py for the detail.',
    'wd_what_harvest_unread': 'The harvest does not read {n} Codex session(s) of a file type it does not list.',
    'wd_harvest_unread_title': 'Codex sessions not read',
    'wd_harvest_unread_action': 'Add that file type to wiki_session_harvest.codex_session_files.',
    'wd_what_harvest_zstd': '{n} compressed Codex session(s) exist, but this Python has no zstd decoder '
                            '(3.14 or later is needed).',
    'wd_harvest_zstd_title': 'Compressed sessions unreadable',
    'wd_harvest_zstd_action': 'Run the harvest on Python 3.14 or later; until then it stops on these sessions.',
    'wd_what_engine_copies': '{n} engine script(s) in the data folder differ from the installed version; an old '
                             'copy can bypass the approval gates.',
    'wd_engine_copies_title': 'Old engine copies',
    'wd_engine_copies_action': 'Run the scripts from the installed engine folder, not from the data folder.',
    'wd_what_other': 'A watchdog finding that matches no known pattern; the detail is below.',
    'wd_other_title': 'Other finding',
    'wd_other_action': 'Act on the message in the detail line.',
    'wd_detail_short': 'detail line',
    'wd_cleared': '{n} run(s) deleted',
    'jb_run_missing': 'run not found (not in executions.db)',
    'wd_clear_refused': 'refused: send {"confirm": true} to archive and empty alerts.log',
    'wd_backups_unusable': 'the backups folder {path} cannot be used, so nothing was changed: {error}',
    'jb_keys_too_many': 'at most {cap} records can be archived and cleared at once, {n} were sent',
    'jb_active_kept': '{n} running or starting run(s) were kept; the scheduler still owns them',
}
_JB_TEXT = {
    "status": {"completed": "completed", "failed": "failed", "claimed": "starting",
               "running": "running", "unknown": "unknown"},
    "delivery": {"delivered": "delivered", "suppressed": "silent (no output)",
                 "queued": "queued", "failed": "delivery failed", "none": "no delivery record"},
    "body": {"output": "run output", "error": "recorded error",
             "none": "no body record (the output file was never written or has been removed)"},
}
_STATUS_TEXT = {"completed": "Completed", "failed": "Failed", "running": "Running", "unknown": "Unknown"}
_DELIVERY_TEXT = {"delivered": "Delivered", "suppressed": "Silent", "queued": "Queued",
                  "failed": "Delivery failed", "none": "No record"}


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except ImportError:
        pass
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local and (Path(local) / "hermes").is_dir():
        return Path(local) / "hermes"
    return Path.home() / ".hermes"


def _state_path() -> Path:
    selected = _SELECTED_PATHS.get()
    return (selected.home if selected is not None else _hermes_home()) / "state" / "wiki-automation"


def _engine_paths():
    paths = _SELECTED_PATHS.get()
    return paths if paths is not None else resolve_engine_paths(_hermes_home(), default=AUDIT_DIR)


def _selected_operation(handler):
    @wraps(handler)
    def selected(*args, **kwargs):
        token = None
        try:
            if _SELECTED_PATHS.get() is None:
                token = _SELECTED_PATHS.set(_engine_paths())
            return handler(*args, **kwargs)
        except EnginePathError as exc:
            return {"ok": False, "available": False, "error": str(exc), "reason": str(exc)}
        finally:
            if token is not None:
                _SELECTED_PATHS.reset(token)
    return selected


def _audit_dir() -> Path:
    return _engine_paths().audit_dir


def _tx(key: str, **kw) -> str:
    text = _EXPLAIN_TEXT.get(key) or key
    if not kw:
        return text
    try:
        return text.format(**kw)
    except (KeyError, IndexError, ValueError) as exc:
        _log.warning("wiki-automation: _tx(%r) could not be formatted: %s", key, exc)
        return text


def _jb_label(group: str, value: str) -> str:
    return ((_JB_TEXT.get(group) or {}).get(value)) or str(value)


def _label(kind: str, value: str) -> str:
    table = _STATUS_TEXT if kind == "status" else _DELIVERY_TEXT
    return table.get(value) or value


def _reason_fields(payload: dict | None) -> dict:
    reason = str((payload or {}).get("reason") or "").strip()
    if not reason:
        return {}
    return {"reason": reason, "reason_source": CHECKER_SOURCE}


def _run_json_ex(cmd: list, timeout: int = 60, paths=None):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout,
                              env=paths.environment() if paths is not None else None)
    except (OSError, subprocess.SubprocessError) as exc:
        _log.warning("wiki-automation: %s could not run: %s", cmd[1:3], exc)
        return None, str(exc)
    text = (proc.stdout or "").strip()
    start = text.find("{")
    found = None
    if start >= 0:
        try:
            found = json.loads(text[start:])
        except ValueError:
            found = None
    if isinstance(found, dict):
        return found, ""
    detail = f"exit {proc.returncode}: " + ((proc.stderr or "").strip() or text or "no output")
    _log.warning("wiki-automation: %s failed: %s", cmd[1:3], detail)
    return None, detail[:_ERROR_PREVIEW * 4]


def _run_json(cmd: list, default=None, timeout: int = 60):
    found, _detail = _run_json_ex(cmd, timeout=timeout)
    return default if found is None else found


def _config_run(args):
    paths = _engine_paths()
    return _run_json_ex([sys.executable, "-B", str(paths.engine_dir / "wikiconfig.py"), *args], paths=paths)


def _unreadable(detail: str) -> str:
    return _tx("auto_call_failed", error=detail) if detail else _tx("auto_unreadable")


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value, datetime.timezone.utc).isoformat()
    return str(value)


def _aware(value) -> datetime.datetime | None:
    text = _iso(value).strip()
    if not text:
        return None
    try:
        dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def _ms(start, end) -> int | None:
    a, b = _aware(start), _aware(end)
    if a is None or b is None:
        return None
    return max(0, int((b - a).total_seconds() * 1000))


def _live_jobs_ex() -> tuple:
    path = _hermes_home() / "cron" / "jobs.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else (raw.get("jobs") or [])
        out = {}
        for item in items:
            jid = str(item.get("id") or "").strip()
            if jid:
                out[jid] = str(item.get("name") or jid)
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        _log.warning("wiki-automation: cron/jobs.json is unreadable (%s): %s", path, exc)
        return None, _tx("jobs_file_unreadable", error=str(exc))
    return out, None


def _live_jobs() -> dict:
    return _live_jobs_ex()[0] or {}


def _jobs_from_settings(settings: dict) -> dict:
    return {str(k): str(v) for k, v in ((settings or {}).get("jobs") or {}).items() if v}


def _role_map() -> dict:
    mapped = {}
    for path in (_engine_paths().settings_path, _state_path() / "settings.json"):
        try:
            settings = json.loads(path.read_bytes())
        except FileNotFoundError:
            settings = {}
        except (OSError, ValueError) as exc:
            raise EnginePathError("Job mapping is unreadable; owner IDs were preserved") from exc
        if not isinstance(settings, dict):
            raise EnginePathError("Job mapping must be an object; owner IDs were preserved")
        for key in ("jobs", "primary_job_ids"):
            values = settings.get(key)
            if values is None:
                values = {}
            if not isinstance(values, dict):
                raise EnginePathError("Job mapping is unreadable; owner IDs were preserved")
            for role, jid in values.items():
                if not isinstance(role, str) or not isinstance(jid, str) or not jid:
                    raise EnginePathError("Job mapping is invalid; owner IDs were preserved")
                if role in mapped and mapped[role] != jid:
                    raise EnginePathError("Conflicting job mappings; owner IDs were preserved")
                if any(other != role and saved == jid for other, saved in mapped.items()):
                    raise EnginePathError("Conflicting native role IDs; owner IDs were preserved")
                mapped[role] = jid
    return mapped


ENGINE_JOBS = "jobs.json"
ENGINE_SETTINGS = "settings.json"
CANDIDATES_SCRIPT = "wiki_candidates.py"
_CANDIDATE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_-]*")
_CANDIDATE_ACTIONS = ("approve", "reject", "fetch_evidence")
_REJECT_REASON_MAX = 500


def _engine_file(name: str) -> dict:
    paths = _engine_paths()
    path = paths.settings_path if name == ENGINE_SETTINGS else paths.engine_dir / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log.warning("wiki-automation: the engine file %s is unreadable: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _job_catalogue() -> dict:
    jobs = _engine_file(ENGINE_JOBS).get("jobs")
    deliver = str(_engine_file(ENGINE_SETTINGS).get("deliver") or "ntfy")
    out = {}
    for role, meta in (jobs.items() if isinstance(jobs, dict) else ()):
        if not isinstance(meta, dict):
            continue
        kind = str(meta.get("kind") or "script")
        out[str(role)] = {
            "name": str(meta.get("name") or role), "kind": kind,
            "launcher": str(meta.get("launcher") or ""), "impl": str(meta.get("impl") or ""),
            "deliver": deliver, "prompt": str(meta.get("description") or "") if kind == "script" else "",
            "schedule_key": str(meta.get("schedule_key") or role),
            "default_schedule": str(meta.get("default_schedule") or ""),
        }
    return out


def _planned_schedule(meta: dict, cfg) -> str:
    schedule = (cfg or {}).get("schedule") or {}
    return str(schedule.get(meta.get("schedule_key")) or meta.get("default_schedule") or "")


def _cron_jobs():
    try:
        from cron import jobs
        return jobs
    except Exception as exc:
        _log.warning("wiki-automation: the cron store could not be imported: %s", exc)
        return None


def _state_settings() -> dict:
    try:
        data = json.loads((_state_path() / "settings.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        _log.warning("wiki-automation: the panel settings are unreadable: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


_DISPATCH_FLAGS = {"late": "late", "catch_up": "missed"}
_PREVIEW_RUNS = 3


def _dispatch_flag(rec: dict | None) -> dict | None:
    stamp = (rec or {}).get("last_dispatch")
    if not isinstance(stamp, dict):
        return None
    flag = _DISPATCH_FLAGS.get(str(stamp.get("kind") or ""))
    if not flag:
        return None
    try:
        lateness = float(stamp.get("lateness_seconds") or 0)
    except (TypeError, ValueError):
        lateness = 0.0
    return {"flag": flag, "scheduled_at": _iso(stamp.get("scheduled_at")),
            "dispatched_at": _iso(stamp.get("dispatched_at")), "lateness_seconds": lateness}


def _run_state(rec: dict | None) -> dict:
    rec = rec or {}
    return {"next_run_at": _iso(rec.get("next_run_at")) or None,
            "last_run_at": _iso(rec.get("last_run_at")) or None,
            "last_status": str(rec.get("last_status") or "") or None,
            "dispatch": _dispatch_flag(rec)}


def _store_zone() -> dict:
    try:
        from hermes_time import get_timezone_name, now as hermes_now
        name, current = str(get_timezone_name() or ""), hermes_now()
    except Exception as exc:
        _log.warning("wiki-automation: the store time zone could not be read, using local time: %s", exc)
        name, current = "", datetime.datetime.now().astimezone()
    offset = current.strftime("%z")
    return {"name": name, "offset": f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset}


def _jobs_preview(expr: str) -> dict:
    expr = str(expr or "").strip()
    if not expr:
        return {"ok": False, "reason": _tx("job_no_expr")}
    cron = _cron_jobs()
    if cron is None:
        return {"ok": False, "reason": _tx("job_no_cron")}
    try:
        parsed = cron.parse_schedule(expr)
    except Exception as exc:
        return {"ok": False, "reason": _tx("job_bad_expr", error=str(exc))}
    runs, anchor = [], None
    for _ in range(_PREVIEW_RUNS):
        try:
            nxt = cron.compute_next_run(parsed, anchor)
        except Exception as exc:
            _log.warning("wiki-automation: the next run of %r could not be computed: %s", expr, exc)
            nxt = None
        if not nxt or nxt in runs:
            break
        runs.append(str(nxt))
        anchor = str(nxt)
    return {"ok": True, "schedule": expr, "kind": str(parsed.get("kind") or ""), "next_runs": runs,
            "timezone": _store_zone()}


def _native_job_operation(handler):
    @wraps(handler)
    @_selected_operation
    def selected(*args, **kwargs):
        cron = _cron_jobs()
        if cron is None:
            return {"ok": False, "reason": _tx("job_no_cron")}
        with cron.use_cron_store(_engine_paths().home):
            return handler(*args, **kwargs)
    return selected


def _verified_job_policy_source(paths):
    lifecycle = sys.modules[__name__ + "._engine_lifecycle"]
    root = lifecycle.confined(paths.home, "state/wiki-automation/installations")
    location = json.loads(lifecycle.confined(paths.home, "state/wiki-automation/location.json").read_bytes())
    hashes = lifecycle._release_hashes(paths.engine_dir)
    for path in sorted(root.glob("*.json")):
        if path.name.endswith(".plan.json"):
            continue
        record = json.loads(lifecycle.confined(root, path.name).read_bytes())
        plan = record.get("plan") or {}
        if (record.get("home") == str(paths.home) and plan.get("location") == location
                and plan.get("engine_dir") == str(paths.engine_dir)
                and plan.get("audit_dir") == str(paths.audit_dir)
                and plan.get("settings_path") == str(paths.settings_path)
                and record.get("release_hashes") == hashes):
            return
    raise EnginePathError("Selected native job policy source has no verified installation identity")


def _verified_native_jobs(mapped):
    paths = _engine_paths()
    try:
        _verified_job_policy_source(paths)
    except (OSError, ValueError, sys.modules[__name__ + "._engine_lifecycle"].LifecycleRefused) as exc:
        raise EnginePathError("Selected native job policy source is unavailable or unverified") from exc
    paths.code_identity()
    inspect = (
        'import sys,json,importlib.util; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
        'spec=importlib.util.spec_from_file_location("selected_install",Path(sys.argv[1])/"install.py"); '
        'install=importlib.util.module_from_spec(spec); spec.loader.exec_module(install); '
        'from cron.jobs import get_job,use_cron_store; '
        'from workflow_store import WorkflowStore; from workflow_paths import checked_path; '
        'p=json.loads(sys.stdin.read()); home=Path(sys.argv[3]); '
        'cfg=json.loads(Path(sys.argv[2]).read_bytes()); '
        'plan=install.build_plan(cfg,home,Path(sys.argv[1]),Path(sys.argv[2]).parent); '
        'out={};\n'
        'with WorkflowStore(checked_path(home,"state/wiki-automation/installation.sqlite"),read_only=True) as journal, use_cron_store(home):\n'
        ' operations=[journal.get_operation(row[0]) for row in journal.db.execute("SELECT id FROM operations")];\n'
        ' for role,jid in p.items():\n'
        '  job=get_job(jid);\n'
        '  if job is None: raise ValueError("Mapped native job is missing; owner IDs were preserved");\n'
        '  install.verify_job_role(job,role,plan);\n'
        '  if job.get("workdir")!=plan["settings"]["project_root"]: raise ValueError("Native job belongs to another project");\n'
        '  proofs=[op for op in operations if op.get("type")=="installation" and op.get("state")=="applied" and any(step["step"]=="job-"+role and step["result"]=={"job_id":jid,"origin":job.get("origin")} for step in journal.steps(op["operation_id"]))];\n'
        '  proofs=[op for op in proofs if all(op["plan"][key]==plan[key] for key in ("hermes_home","engine_dir","audit_dir","project_id")) and op["plan"]["settings"]["project_root"]==cfg["project_root"] and op["plan"]["code_hashes"]==plan["code_hashes"]];\n'
        '  if not proofs: raise ValueError("Native job has no selected installation provenance");\n'
        '  approved=proofs[-1]["plan"];\n'
        '  if json.loads(checked_path(home,"state/wiki-automation/location.json").read_bytes())!=approved["location"]: raise ValueError("Selected location differs from engine installation provenance");\n'
        '  names=["_wiki_engine_bootstrap.py",plan["job_definitions"][role]["launcher"]];\n'
        '  if any(checked_path(home,"scripts/"+name).read_bytes()!=bytes.fromhex(approved["launcher_payloads"][name]) for name in names): raise ValueError("Selected launcher differs from engine installation provenance");\n'
        '  out[role]=job;\n'
        'print(json.dumps({"jobs":out}));\n')
    result = subprocess.run([sys.executable, "-B", "-c", inspect, str(paths.engine_dir),
        str(paths.settings_path), str(paths.home)], input=json.dumps(mapped),
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        cwd=paths.home, env=paths.environment())
    if result.returncode:
        raise EnginePathError("Native job ownership could not be verified; owner jobs and IDs were preserved: "
                              + (result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "engine refused"))
    return json.loads(result.stdout)["jobs"]


@_native_job_operation
def _jobs_view(cfg=None, state=None) -> dict:
    mapped = _role_map()
    binding = _job_bindings()
    verified = _verified_native_jobs(mapped) if mapped else {}
    if _role_map() != mapped or _job_bindings() != binding:
        raise EnginePathError("Captured job ownership changed during role inspection")
    cfg = _config_run(["show"])[0] if cfg is None else cfg
    if _role_map() != mapped or _job_bindings() != binding:
        raise EnginePathError("Captured job ownership changed before role labels were assigned")
    state = _state_settings() if state is None else state
    catalogue = _job_catalogue()
    audit = _audit_dir()
    if not catalogue:
        return {"ok": False, "reason": _tx("job_no_catalogue", path=str(_engine_paths().engine_dir / ENGINE_JOBS)),
                "roles": [], "orphans": [], "mutation_available": False}
    cron = _cron_jobs()
    project = (cfg or {}).get("project") or {}
    rows = []
    for role, meta in catalogue.items():
        jid = mapped.get(role)
        rec = verified.get(role)
        if rec is not None and cron.get_job(jid) != rec:
            raise EnginePathError("Native job changed after role inspection; no role label was assigned")
        impl = str(meta.get("impl") or "")
        impl_ok = bool(impl) and (_engine_paths().engine_dir / impl).is_file()
        root_ok = bool(project.get("ok"))
        if rec is None:
            job_state = "absent"
        else:
            try:
                job_state = str(cron.effective_job_state(rec))
            except Exception:
                job_state = "enabled" if rec.get("enabled") else "paused"
        stored_sched = ""
        if rec is not None:
            got = rec.get("schedule")
            if isinstance(got, dict):
                got = got.get("expr") or rec.get("schedule_display") or ""
            stored_sched = str(got or "")
        planned = _planned_schedule(meta, cfg)
        rows.append({
            "role": role, "name": meta.get("name") or role, "kind": meta.get("kind") or "script",
            "id": jid if rec is not None else None,
            "mapped_id": jid or None,
            "live": rec is not None, "state": job_state,
            "schedule": stored_sched or planned,
            "planned_schedule": planned,
            "schedule_source": "store" if stored_sched else ("config" if planned else ""),
            **_run_state(rec),
            "deliver": (rec or {}).get("deliver") or meta.get("deliver") or "local",
            "target": {"ok": root_ok and impl_ok, "root_ok": root_ok, "impl_ok": impl_ok,
                       "root": str(project.get("path") or ""), "impl": impl,
                       **_reason_fields(project)},
        })
    return {"ok": True, "available": bool(cfg), "cron": cron is not None,
            "mutation_available": hasattr(cron, "_jobs_lock"),
            "management_reason": None if hasattr(cron, "_jobs_lock") else _tx("job_management_unavailable"),
            "error": None if cfg else _tx("job_no_config"), "audit_dir": str(audit),
            "timezone": _store_zone(), "roles": rows,
            "orphans": [r["role"] for r in rows
                        if r["live"] and r["state"] != "paused" and not r["target"]["ok"]]}


def _job_bindings():
    paths = _engine_paths()
    files = (paths.settings_path, paths.home / "state/wiki-automation/settings.json",
             paths.home / "state/wiki-automation/location.json",
             paths.home / "state/wiki-automation/installation.sqlite")
    lifecycle = sys.modules[__name__ + "._engine_lifecycle"]
    return {"code": paths.code_identity(),
            "launchers": lifecycle._release_hashes(paths.home / "scripts"),
            "installations": lifecycle._release_hashes(paths.home / "state/wiki-automation/installations"),
            "files": [lifecycle.confined(path.parent, path.name).read_bytes() if path.exists() else None
                      for path in files]}


_JOB_ACTIONS = ("pause", "resume", "schedule", "remove", "create")
_JOB_FACTS = ("id", "state", "schedule")


def _job_facts(rec: dict, cron) -> dict:
    try:
        state = str(cron.effective_job_state(rec))
    except Exception:
        state = "enabled" if rec.get("enabled") else "paused"
    got = rec.get("schedule")
    if isinstance(got, dict):
        got = got.get("expr") or rec.get("schedule_display") or ""
    return {"id": str(rec.get("id") or ""), "state": state, "schedule": str(got or "")}


def _forget_role(role: str, jid: str) -> None:
    for path in (_engine_paths().settings_path, _state_path() / "settings.json"):
        if not path.exists():
            continue
        data = json.loads(path.read_bytes())
        changed = False
        for key in ("jobs", "primary_job_ids"):
            values = data.get(key)
            if isinstance(values, dict) and values.get(role) == jid:
                del values[role]
                changed = True
        if changed:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(path)


def _notify_scheduler() -> None:
    try:
        from cron.scheduler import _notify_provider_jobs_changed
        _notify_provider_jobs_changed()
    except Exception as exc:
        _log.warning("wiki-automation: the scheduler was not notified of the job change: %s", exc)


@_native_job_operation
def _jobs_act(role: str, action: str, confirm: bool, cfg=None, schedule: str = "", expected=None) -> dict:
    meta = _job_catalogue().get(role)
    if not meta:
        return {"ok": False, "reason": _tx("job_unknown_role")}
    if action not in _JOB_ACTIONS:
        return {"ok": False, "reason": _tx("job_unknown_action")}
    agent = meta.get("kind") != "script"
    if action in ("create", "remove") and agent:
        return {"ok": False, "reason": _tx("job_agent_fixed")}
    if action == "create":
        return {"ok": False, "install": True, "reason": _tx("job_create_install")}
    if action == "remove" and not confirm:
        return {"ok": False, "reason": _tx("job_confirm")}
    cron = _cron_jobs()
    if not hasattr(cron, "_jobs_lock"):
        return {"ok": False, "reason": _tx("job_management_unavailable")}
    expr = str(schedule or "").strip()
    if action == "schedule":
        if not expr:
            return {"ok": False, "reason": _tx("job_no_expr")}
        try:
            cron.parse_schedule(expr)
        except Exception as exc:
            return {"ok": False, "reason": _tx("job_bad_expr", error=str(exc))}
    if not isinstance(expected, dict) or any(not isinstance(expected.get(k), str) for k in _JOB_FACTS):
        return {"ok": False, "reason": _tx("job_changed")}
    mapped = _role_map()
    binding = _job_bindings()
    jid = mapped.get(role)
    if not jid:
        return {"ok": False, "reason": _tx("job_not_recorded")}
    rec = _verified_native_jobs({role: jid})[role]
    with cron._jobs_lock():
        if _role_map() != mapped or _job_bindings() != binding or cron.get_job(jid) != rec:
            return {"ok": False, "reason": _tx("job_changed")}
        if _job_facts(rec, cron) != {k: expected[k] for k in _JOB_FACTS}:
            return {"ok": False, "reason": _tx("job_changed")}
        if action == "pause":
            cron.pause_job(jid, reason=_tx("job_paused_reason"))
        elif action == "resume":
            cron.resume_job(jid)
        elif action == "schedule":
            cron.update_job(jid, {"schedule": expr})
        else:
            cron.remove_job(jid)
        after = cron.get_job(jid)
    _notify_scheduler()
    if action == "remove":
        if after is not None:
            return {"ok": False, "reason": _tx("job_readback", action=action)}
        _forget_role(role, jid)
        return {"ok": True, "action": action, "role": role}
    facts = _job_facts(after or {}, cron)
    want = {"pause": facts["state"] == "paused", "resume": facts["state"] not in ("paused", "absent"),
            "schedule": facts["schedule"] == expr}[action]
    if after is None or not want:
        return {"ok": False, "reason": _tx("job_readback", action=action)}
    return {"ok": True, "action": action, "role": role, "schedule": facts["schedule"],
            "state": facts["state"], "next_run_at": _iso(after.get("next_run_at")) or None}


def _recent_runs(job_ids: list, limit: int) -> dict:
    db = _hermes_home() / "cron" / "executions.db"
    out = {jid: [] for jid in job_ids}
    if not db.exists():
        return out
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=3.0)
    except sqlite3.Error as exc:
        _log.warning("wiki-automation: executions.db could not be opened: %s", exc)
        return out
    try:
        con.row_factory = sqlite3.Row
        for jid in job_ids:
            rows = con.execute(
                f"select {_JOB_COLS} from executions where job_id = ?"
                " order by claimed_at desc limit ?", (jid, limit)).fetchall()
            for row in rows:
                rec = dict(row)
                status = str(rec.get("status") or "unknown").lower()
                delivery = str(rec.get("delivery_outcome") or "none").lower()
                out[jid].append({
                    "at": _iso(rec.get("claimed_at")),
                    "status": status, "status_label": _label("status", status),
                    "delivery": delivery, "delivery_label": _label("delivery", delivery),
                    "ms": _ms(rec.get("claimed_at"), rec.get("finished_at")),
                    "error_preview": (str(rec.get("error") or "").strip()[:_ERROR_PREVIEW] or None),
                })
    except sqlite3.Error as exc:
        _log.warning("wiki-automation: reading executions.db failed: %s", exc)
        return out
    finally:
        con.close()
    return out


@router.get("/automation")
@_selected_operation
def automation():
    paths = _engine_paths()
    audit = paths.audit_dir
    info = {"audit_dir": str(audit), "available": False, "settings": None, "scripts": {}, "error": None}
    cfg_py = paths.engine_dir / "wikiconfig.py"
    if not cfg_py.exists():
        info["error"] = _tx("auto_missing")
        return info
    info["available"] = True
    payload, detail = _run_json_ex([sys.executable, "-B", str(cfg_py), "show"], paths=paths)
    if payload is None:
        info["error"] = _unreadable(detail)
    else:
        project = payload.get("project")
        info["settings"] = {**payload, "project": ({**project, **_reason_fields(project)}
                                                   if project else project)}
    for name in ("wiki_autocommit.py", "wiki_ingest_watch.py", "watchdog.py", "wiki_audit.py",
                 "install.py", "portability_check.py"):
        info["scripts"][name] = (paths.engine_dir / name).exists()
    return info


@router.post("/automation/validate")
@_selected_operation
def automation_validate(payload: dict):
    path = str((payload or {}).get("path") or "").strip()
    if not path:
        return {"ok": False, "reason": _tx("auto_no_path")}
    found, detail = _config_run(["validate", path])
    if found is None:
        return {"ok": False, "reason": _unreadable(detail)}
    return {**found, **_reason_fields(found)}


@router.post("/automation/derive")
@_selected_operation
def automation_derive(payload: dict):
    picked = str((payload or {}).get("picked") or "").strip()
    if not picked:
        return {"ok": False, "reason": _tx("auto_no_path")}
    found, detail = _config_run(["derive", picked])
    if found is None:
        return {"ok": False, "reason": _unreadable(detail)}
    return {**found, **_reason_fields(found)}


@router.get("/automation/candidates")
@_selected_operation
def automation_candidates(root: str = ""):
    args = ["candidates"]
    if root and not (Path(root).is_absolute() and Path(root).is_dir()):
        return {"ok": False, "found": [], "scanned": 0, "skipped": 0, "truncated": False,
                "reason": _tx("auto_not_folder")}
    if root:
        args.append(root)
    found, detail = _config_run(args)
    if found is None:
        return {"ok": False, "found": [], "scanned": 0, "skipped": 0, "truncated": False,
                "reason": _unreadable(detail)}
    return {**found, **_reason_fields(found)}


@router.post("/automation/scan_root")
@_selected_operation
def automation_scan_root(payload: dict):
    path = str((payload or {}).get("path") or "").strip()
    if not path:
        return {"ok": False, "reason": _tx("auto_no_path")}
    target = Path(path)
    if not target.is_absolute():
        return {"ok": False, "reason": _tx("auto_not_folder")}
    if not target.is_dir():
        return {"ok": False, "reason": _tx("auto_scan_root_bad")}
    written, detail = _config_run(["set", f"scan_root={target}"])
    if not written or not written.get("ok"):
        return {"ok": False, "reason": _tx("auto_write_failed") + (f" ({detail})" if detail else ""),
                **_reason_fields(written)}
    return {"ok": True, "scan_root": str(target)}


@router.post("/automation/settings")
@_selected_operation
def automation_settings(payload: dict):
    root = str((payload or {}).get("project_root") or "").strip()
    if not root:
        return {"ok": False, "reason": _tx("auto_no_path")}
    checked, detail = _config_run(["validate", root])
    if checked is None:
        return {"ok": False, "reason": _unreadable(detail)}
    if not checked.get("ok"):
        return {"ok": False, "reason": _tx("auto_invalid"), **_reason_fields(checked)}
    force = bool((payload or {}).get("force"))
    current = _config_run(["show"])[0] or {}
    cur_id = (current.get("project") or {}).get("id")
    cur_root = str(current.get("project_root") or "")
    pid = checked.get("id")
    if (not force and pid and cur_id and pid == cur_id and cur_root
            and os.path.normcase(os.path.abspath(root)) != os.path.normcase(os.path.abspath(cur_root))):
        return {"ok": False, "needs_force": True, "reason": _tx("auto_same_id")}
    pairs = [f"project_root={root}"] + ([f"project_id={pid}"] if pid else [])
    written, detail = _config_run(["set", *pairs])
    if not written or not written.get("ok"):
        return {"ok": False, "reason": _tx("auto_write_failed") + (f" ({detail})" if detail else "")}
    return {"ok": True, "project_root": written.get("project_root"), "project": checked,
            "settings": _config_run(["show"])[0]}


@router.get("/jobs")
def jobs_view_route():
    try:
        view = _jobs_view()
    except Exception as exc:
        _log.warning("wiki-automation: reading the scheduled jobs failed: %s", exc)
        view = {"ok": False, "reason": _tx("job_read_failed", error=str(exc))}
    return {"roles": [], "orphans": [], "mutation_available": False, **view}


@router.post("/jobs/preview")
def jobs_preview_route(payload: dict):
    try:
        return _jobs_preview(str((payload or {}).get("schedule") or ""))
    except Exception as exc:
        return {"ok": False, "reason": _tx("job_act_failed", error=str(exc))}


@router.post("/jobs/act")
def jobs_act_route(payload: dict):
    body = payload or {}
    try:
        return _jobs_act(str(body.get("role") or ""), str(body.get("action") or ""),
                         bool(body.get("confirm")), schedule=str(body.get("schedule") or ""),
                         expected=body.get("expected"))
    except Exception as exc:
        return {"ok": False, "reason": _tx("job_act_failed", error=str(exc))}


def _candidates_run(args: list, timeout: int = 120):
    paths = _engine_paths()
    script = paths.engine_dir / CANDIDATES_SCRIPT
    if not script.is_file():
        return None, _tx("cand_missing")
    try:
        proc = subprocess.run([sys.executable, "-B", str(script), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout,
                              env=paths.environment())
    except (OSError, subprocess.SubprocessError) as exc:
        _log.warning("wiki-automation: %s %s could not run: %s", CANDIDATES_SCRIPT, args[:1], exc)
        return None, _tx("cand_call_failed", error=str(exc))
    return proc, ""


def _script_text(proc) -> str:
    text = "\n".join(part.strip() for part in (proc.stdout or "", proc.stderr or "") if part.strip())
    return text[:_ERROR_PREVIEW * 8]


def _script_json(proc):
    try:
        return json.loads(proc.stdout or "")
    except ValueError:
        return None


def _script_failed(proc) -> str:
    detail = f"exit {proc.returncode}: " + (_script_text(proc) or "no output")
    _log.warning("wiki-automation: %s failed: %s", CANDIDATES_SCRIPT, detail)
    return _tx("cand_read_failed", error=detail)


def _body_text(body: dict, key: str) -> str:
    return str((body or {}).get(key) or "").strip()


@router.get("/harvest/status")
@_selected_operation
def harvest_status():
    paths = _engine_paths()
    script = paths.engine_dir / "wiki_session_harvest.py"
    failed = {"ok": False, "agents": []}
    if not script.is_file():
        return {**failed, "error": _tx("harvest_missing")}
    try:
        proc = subprocess.run([sys.executable, "-B", str(script), "--status"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=15, env=paths.environment())
    except (OSError, subprocess.SubprocessError) as exc:
        return {**failed, "error": _tx("harvest_call_failed", error=str(exc))}
    if proc.returncode != 0:
        return {**failed, "error": _tx("harvest_failed", code=proc.returncode, error=_script_text(proc))}
    agents = []
    seen = set()
    for line in (proc.stdout or "").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"(\S+)\s+(on|off)\s+(found|NOT FOUND)\s+cursor=(.+)", line.strip())
        if not match or match[1] in seen:
            return {**failed, "error": _tx("harvest_unsupported")}
        seen.add(match[1])
        agents.append({"id": match[1], "enabled": match[2] == "on", "found": match[3] == "found",
                       "cursor": match[4]})
    if not agents:
        return {**failed, "error": _tx("harvest_empty")}
    try:
        last = subprocess.run([sys.executable, "-B", str(script), "--last-run"], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=15, env=paths.environment())
    except (OSError, subprocess.SubprocessError) as exc:
        return {**failed, "error": _tx("harvest_call_failed", error=str(exc))}
    if last.returncode == 2 and "unrecognized arguments: --last-run" in (last.stderr or ""):
        return {"ok": True, "agents": agents, "last_run_supported": False, "last_run": None}
    row = _script_json(last)
    if last.returncode != 0:
        return {**failed, "error": _tx("harvest_last_failed", code=last.returncode,
                                       error=(row or {}).get("error") if isinstance(row, dict) and row.get("error")
                                       else _script_text(last))}
    if not isinstance(row, dict) or row.get("ok") is not True or "run" not in row:
        return {**failed, "error": _tx("harvest_last_unsupported")}
    if row["run"] is None:
        return {"ok": True, "agents": agents, "last_run_supported": True, "last_run": None}
    agent_states = row.get("agents")
    if not isinstance(row.get("execution_id"), str) or not isinstance(row.get("committed"), bool) \
            or not isinstance(agent_states, dict) or not all(isinstance(value, str) for value in agent_states.values()):
        return {**failed, "error": _tx("harvest_last_unsupported")}
    stop, spent = row.get("stop_reason"), row.get("usage")
    return {"ok": True, "agents": agents, "last_run_supported": True,
            "last_run": {**{key: row.get(key) for key in ("run", "execution_id", "created", "committed", "status", "agents")},
                         "stop_reason": stop if isinstance(stop, dict) and isinstance(stop.get("detail"), str) else None,
                         "cost_usd": spent.get("cost_usd") if isinstance(spent, dict)
                         and isinstance(spent.get("cost_usd"), (int, float)) else None}}


@router.get("/candidates")
@_selected_operation
def candidates_list():
    audit = str(_audit_dir())
    proc, detail = _candidates_run(["list", "--json"])
    if proc is None:
        return {"ok": False, "candidates": [], "audit_dir": audit, "error": detail}
    rows = _script_json(proc)
    if proc.returncode != 0 or not isinstance(rows, list):
        return {"ok": False, "candidates": [], "audit_dir": audit, "error": _script_failed(proc)}
    return {"ok": True, "candidates": [row for row in rows if isinstance(row, dict)], "audit_dir": audit}


@router.get("/candidates/show")
@_selected_operation
def candidates_show(ref: str = ""):
    ref = str(ref or "")
    if not _CANDIDATE_REF.fullmatch(ref):
        return {"ok": False, "ref": ref, "error": _tx("cand_bad_ref")}
    proc, detail = _candidates_run(["show", ref, "--json"])
    if proc is None:
        return {"ok": False, "ref": ref, "error": detail}
    found = _script_json(proc)
    if proc.returncode != 0 or not isinstance(found, dict):
        return {"ok": False, "ref": ref, "error": _script_failed(proc)}
    return {**found, "ok": True, "ref": ref}


def _owner_run(operation, payload):
    try:
        paths = _engine_paths()
        engine = paths.engine_dir
        proc = subprocess.run([sys.executable, '-B', str(engine / 'owner_decisions.py'), operation,
                               '--home', str(paths.home), '--settings', str(paths.settings_path)],
                              input=json.dumps(payload), capture_output=True, text=True, encoding='utf-8',
                              timeout=30, env=paths.environment())
        result = json.loads(proc.stdout)
        if not isinstance(result, dict) or proc.returncode not in (0, 1):
            raise ValueError('Unsupported owner-authority response')
        return result
    except subprocess.TimeoutExpired:
        return {'ok': False, 'retryable': True,
                'reason': _tx('owner_timeout')}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'ok': False, 'reason': _tx('owner_failed', error=str(exc))}


def _owner_binding():
    return _engine_file(ENGINE_SETTINGS).get('owner_approval_owner')


def _draft_guard():
    from functools import partial
    from hermes_cli.plugins import iter_hook_callbacks
    guard_file = Path(__file__).resolve().parents[1] / 'draft_security.py'
    guards = [cb for cb in iter_hook_callbacks('pre_tool_call') if isinstance(cb, partial) and cb.args
              and getattr(cb.func, '__name__', '') == 'draft_guard'
              and Path(cb.func.__code__.co_filename).resolve() == guard_file]
    return guards[0] if len(guards) == 1 else None


class _OwnerSetup:
    HOST_SETTINGS = ('draft_job_id', 'harvest_workflow_enabled', 'runtime_probe_enabled')

    def _loaded(self):
        guard = _draft_guard()
        probe = sys.modules.get(guard.func.__globals__['__package__'] + '.runtime_probe') if guard else None
        if guard is None or probe is None:
            raise ValueError('the Wiki Automation guard is not loaded in this Hermes process; restart the background service from Review')
        return guard.args[0], probe._LOADED_CODE_HASH

    def plan(self, binding):
        from cron.jobs import get_job
        ctx, code_hash = self._loaded()
        paths = _engine_paths()
        settings = json.loads(paths.settings_path.read_bytes())
        job_id = (settings.get('jobs') or {}).get('session_harvest')
        job = get_job(job_id) if isinstance(job_id, str) and job_id else None
        if not job or job.get('no_agent') or set(job.get('enabled_toolsets') or []) != {'wiki_draft', 'no_mcp'}:
            return {'ok': False, 'reason': 'The Session Harvest job is missing or not limited to the wiki drafting '
                    'tools; repair the engine installation in Nexus first.'}
        host = {key: ctx.get_config(key, None) for key in self.HOST_SETTINGS}
        pinned = (settings.get('owner_approval_runtime') or {}).get('loaded_code_hash')
        bound = settings.get('owner_approval_owner') == binding
        active = (bound and pinned == code_hash and host == {'draft_job_id': job_id, 'harvest_workflow_enabled': True,
                  'runtime_probe_enabled': True} and all(settings.get(key) is True for key in
                  ('owner_approval_enabled', 'owner_publication_enabled', 'harvest_workflow_enabled')))
        schedule = job.get('schedule') or {}
        identity = {'binding': binding, 'loaded_code_hash': code_hash, 'job_id': job_id,
                    'engine': str(paths.engine_dir), 'settings': str(paths.settings_path)}
        return {'ok': True, 'active': active, 'ready': bool(active and _owner_ready()),
                'code_changed': bool(bound and pinned and pinned != code_hash),
                'owner': binding['mode'] if binding['mode'] == 'local_owner'
                    else f"{binding['provider']}:{binding['user_id']}",
                'job': {'id': job_id, 'name': str(job.get('name') or ''),
                        'schedule': str(schedule.get('display') or schedule.get('expr') or '')},
                'loaded_code_hash': code_hash,
                'plan_digest': hashlib.sha256(json.dumps(identity, sort_keys=True).encode('utf-8')).hexdigest()}

    def apply(self, plan):
        ctx, code_hash = self._loaded()
        if code_hash != plan['loaded_code_hash']:
            raise ValueError('the loaded Wiki Automation code changed during setup; review it again')
        for key, value in zip(self.HOST_SETTINGS, (plan['job']['id'], True, True)):
            ctx.set_config(key, value)


def _owner_ready():
    import secrets
    from gateway.control_socket import identify_gateway
    from tools.process_registry import restart_safe_gateway_child_argv
    from hermes_cli.config import load_config_readonly
    try:
        paths = _engine_paths()
        identity = paths.code_identity()
        if identity is None:
            return False
        cfg = load_config_readonly()
        if (cfg.get('cron') or {}).get('provider') not in (None, '', 'builtin', 'in-process', 'inprocess'):
            return False
        dispatch = restart_safe_gateway_child_argv([sys.executable, '-c', 'pass'],
            unit_suffix='wiki-security-verification', require_restart_safe_scope=True)
        if dispatch.mode != 'in_process':
            return False
        expected = (json.loads(paths.settings_path.read_bytes()).get('owner_approval_runtime') or {}).get('loaded_code_hash')
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            return False
        peer = identify_gateway(paths.home, timeout=1)
        if not peer or type(peer.get('pid')) is not int or peer['pid'] <= 0 or not isinstance(peer.get('hermes_home'), str):
            return False
        if not peer['hermes_home'] or Path(peer['hermes_home']).resolve() != paths.home:
            return False
        guard = _draft_guard()
        if guard is None:
            return False
        if not guard.func.__globals__['approval_runtime_ready']():
            return False
        loaded = sys.modules.get(guard.func.__globals__['__package__'] + '.runtime_probe')
        if loaded is None:
            return False
        proof = loaded.probe(guard.args[0], secrets.token_hex(32), paths=paths)
        if proof['loaded_code_hash'] != expected or proof['veto_exercised'] is not True or proof['handler_reached'] is not False:
            return False
        if proof.get('engine_identity') != identity:
            return False
        if peer['pid'] != os.getpid():
            package = guard.func.__globals__['__package__']
            channel = sys.modules.get(package + '.runtime_channel')
            if channel is None or guard.args[0].get_config('runtime_probe_enabled', False) is not True:
                return False
            channel.query_peer(paths.home, peer['pid'], expected, guard.args[0].get_config('draft_job_id', None), expected_engine=identity)
        return True
    except (OSError, RuntimeError, ValueError, KeyError, AttributeError, TypeError, ImportError):
        return False


@router.post("/candidates/act")
def candidates_act(payload: dict):
    body = payload or {}
    ref = str(body.get("ref") or "")
    action = _body_text(body, "action")
    head = {"ok": False, "ref": ref, "action": action}
    if not _CANDIDATE_REF.fullmatch(ref):
        return {**head, "reason": _tx("cand_bad_ref")}
    if action not in _CANDIDATE_ACTIONS:
        return {**head, "reason": _tx("cand_bad_action")}
    if action == "reject":
        why = _body_text(body, "reason")[:_REJECT_REASON_MAX]
        if not why:
            return {**head, "reason": _tx("cand_no_reason")}
        digest = body.get("review_digest")
        if digest is None and body.get("unreviewable") is True:
            proc, detail = _candidates_run(["show", ref, "--json"])
            if proc is None:
                return {**head, "reason": detail}
            if proc.returncode == 0:
                return {**head, "reason": "This candidate can be reviewed now; review it and reject the displayed content."}
            args = ["reject", ref, f"--reason={why}"]
        elif not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            return {**head, "reason": "Exact displayed review digest is required; review again."}
        else:
            args = ["reject", ref, f"--reason={why}", f"--expected-review-digest={digest}"]
    elif action == "fetch_evidence":
        digest = body.get("review_digest")
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            return {**head, "reason": "Exact displayed review digest is required; review again."}
        proc, detail = _candidates_run(["fetch-evidence", ref, f"--expected-review-digest={digest}"], timeout=600)
        if proc is None:
            return {**head, "reason": detail}
        found = _script_json(proc)
        if not isinstance(found, dict) or not isinstance(found.get("results"), list):
            return {**head, "reason": _tx("cand_refused", action="fetch evidence for"), "output": _script_text(proc)}
        return {**head, "ok": found.get("ok") is True, "results": [r for r in found["results"] if isinstance(r, dict)],
                "pending": [str(v) for v in found.get("pending") or []],
                "reason": None if found.get("ok") is True else _tx("cand_fetch_partial")}
    elif not body.get("confirm"):
        proc, detail = _candidates_run(["approve", ref, "--dry-run"])
        if proc is None:
            return {**head, "reason": detail}
        if proc.returncode != 0:
            return {**head, "reason": _tx("cand_refused", action=action), "output": _script_text(proc)}
        return {**head, "needs_confirm": True, "reason": _tx("cand_confirm"), "output": _script_text(proc)}
    else:
        return {**head, "reason": _tx("owner_legacy_block")}
    proc, detail = _candidates_run(args)
    if proc is None:
        return {**head, "reason": detail}
    if proc.returncode != 0:
        return {**head, "reason": _tx("cand_refused", action=action), "output": _script_text(proc)}
    return {**head, "ok": True, "output": _script_text(proc)}


@router.get("/runs")
@_native_job_operation
def runs(limit: int = 8):
    limit = max(1, min(int(limit or 8), 50))
    jobs = _role_map()
    _verified_native_jobs(jobs) if jobs else None
    live, error = _live_jobs_ex()
    ids = [jid for jid in jobs.values()]
    by_id = _recent_runs(ids, limit)
    out = []
    for role, jid in jobs.items():
        out.append({"role": role, "job_id": jid, "name": (live or {}).get(jid) or jid,
                    "live": None if live is None else jid in live, "runs": by_id.get(jid, [])})
    return {"ok": True, "limit": limit, "jobs": out, "error": error}


_WD_RULES = (
    ("not_indexed", re.compile(r"index'te hiç görünmeyen sayfa \((\d+)\)", re.S)),
    ("wikilink", re.compile(r"path-form wikilinks \((\d+)", re.S)),
    ("dup", re.compile(r"(AYNI İSİMLİ İKİ SAYFA|duplicate page stems)", re.S)),
    ("drift", re.compile(r"(ajan kurulumları farklı|agent-setup drift|Ajan kurulumu sapması)", re.S)),
    ("mirror", re.compile(r"(?:(?P<tr_n>\d+) commit '(?P<tr_remote>[^']+)' mirror'una gitmemiş"
                          r"|(?P<en_n>\d+) commit\(s\) ahead of '(?P<en_remote>[^']+)')", re.S)),
    ("identity", re.compile(r"(app'in AKTİF proje kimliği|PROJE KİMLİĞİ DEĞİŞMİŞ|app's ACTIVE project id)", re.S)),
    ("unresolvable", re.compile(r"(var olmayan sayfalara giden linkler|unresolvable body links)", re.S)),
    ("isolated", re.compile(r"(?:(\d+) sayfa app-graph'ta izole|(\d+) app-graph isolated page\(s\))", re.S)),
    ("pages_down", re.compile(r"sayfa sayısı düştü: (\d+) → (\d+)", re.S)),
    ("drift_crash", re.compile(r"drift_check ÇÖKTÜ \(çıkış", re.S)),
    ("crash", re.compile(r"ÇÖKTÜ:", re.S)),
    ("evidence_store", re.compile(r"kanıt deposu \((\d+) sorun\)", re.S)),
    ("evidence_stale", re.compile(r"sürüm değişti, (\d+) kanıt artık kurulu sürümle uyuşmuyor", re.S)),
    ("control_missing", re.compile(r"(purpose\.md|schema\.md) YOK", re.S)),
    ("control_changed", re.compile(r"(purpose\.md|schema\.md) git'teki sürümden farklı", re.S)),
    ("control_template", re.compile(r"(purpose\.md|schema\.md) BOŞ ŞABLON boyutunda", re.S)),
    ("project_file_missing", re.compile(r"\.llm-wiki/project\.json YOK", re.S)),
    ("project_file_unreadable", re.compile(r"\.llm-wiki/project\.json okunamıyor", re.S)),
    ("project_reregistered", re.compile(r"APP BU KLASÖRÜ YENİDEN KAYDETTİ", re.S)),
    ("index_stale", re.compile(r"index'te kayıtlı ama dosyası yok \((\d+)\)", re.S)),
    ("unsplit_ingest", re.compile(r"bölünmemiş ingest çıktısı \((\d+) sayfa\)", re.S)),
    ("mcp_off", re.compile(r"\"Enable MCP access\" KAPALI", re.S)),
    ("commit_backlog", re.compile(r"(\d+) wiki değişikliği (\d+) saattir commit edilmedi", re.S)),
    ("harvest_unread", re.compile(r"harvest (\d+) Codex oturumunu okumuyor", re.S)),
    ("harvest_zstd", re.compile(r"(\d+) sıkıştırılmış Codex oturumu var ama bu Python'da zstd çözücü yok", re.S)),
    ("engine_copies", re.compile(r"veri klasöründe kurulu sürümden farklı (\d+) motor betiği", re.S)),
)

_WD_IDS = re.compile(r"(\S+)\s*\(beklenen\s+([^)]+)\)", re.S)

_TR_UPPER = str.maketrans("iıçğöşü", "İIÇĞÖŞÜ")
_SENTENCE_END = (".", "!", "?", "…", ":")
_CMD_HINT = re.compile(r"(^|\s)(git|npm|pnpm|python|pip|uv|curl|cp|mv|rm|cd|bash|sh)\s|--|/")


def _tr_upper_first(ch: str) -> str:
    return ch.translate(_TR_UPPER).upper()


def _sentence(text: object) -> str:
    t = " ".join(str(text or "").split())
    t = re.sub(r"^[—–\-•●\s]+", "", t)
    t = re.sub(r"[\s;:,]+$", "", t)
    if not t:
        return ""
    t = _tr_upper_first(t[0]) + t[1:]
    if t.endswith(_SENTENCE_END) or _CMD_HINT.search(t) or " " not in t:
        return t
    return t + "."


_WD_KINDS = {
    "not_indexed": ("wd_not_indexed_title", "wd_not_indexed_action", "neutral", False),
    "wikilink": ("wd_wikilink_title", "wd_wikilink_action", "warn", False),
    "dup": ("wd_dup_title", "wd_dup_action", "bad", False),
    "drift": ("wd_drift_title", "wd_drift_action", "warn", False),
    "mirror": ("wd_mirror_title", "wd_mirror_action", "warn", True),
    "identity": ("wd_identity_title", "wd_identity_action", "bad", True),
    "unresolvable": ("wd_unresolvable_title", "wd_unresolvable_action", "bad", False),
    "isolated": ("wd_isolated_title", "wd_isolated_action", "warn", False),
    "pages_down": ("wd_pages_down_title", "wd_pages_down_action", "bad", False),
    "crash": ("wd_crash_title", "wd_crash_action", "bad", False),
    "evidence_store": ("wd_evidence_store_title", "wd_evidence_store_action", "bad", False),
    "evidence_stale": ("wd_evidence_stale_title", "wd_evidence_stale_action", "warn", False),
    "control_missing": ("wd_control_missing_title", "wd_control_missing_action", "bad", False),
    "control_changed": ("wd_control_changed_title", "wd_control_changed_action", "warn", False),
    "control_template": ("wd_control_template_title", "wd_control_template_action", "bad", False),
    "project_file_missing": ("wd_project_file_missing_title", "wd_project_file_missing_action", "bad", False),
    "project_file_unreadable": ("wd_project_file_unreadable_title", "wd_project_file_unreadable_action", "bad",
                                False),
    "project_reregistered": ("wd_project_reregistered_title", "wd_project_reregistered_action", "bad", False),
    "index_stale": ("wd_index_stale_title", "wd_index_stale_action", "warn", False),
    "unsplit_ingest": ("wd_unsplit_ingest_title", "wd_unsplit_ingest_action", "bad", False),
    "mcp_off": ("wd_mcp_off_title", "wd_mcp_off_action", "warn", False),
    "commit_backlog": ("wd_commit_backlog_title", "wd_commit_backlog_action", "warn", False),
    "drift_crash": ("wd_drift_crash_title", "wd_drift_crash_action", "bad", False),
    "harvest_unread": ("wd_harvest_unread_title", "wd_harvest_unread_action", "warn", False),
    "harvest_zstd": ("wd_harvest_zstd_title", "wd_harvest_zstd_action", "warn", False),
    "engine_copies": ("wd_engine_copies_title", "wd_engine_copies_action", "warn", False),
    "other": ("wd_other_title", "wd_other_action", "warn", True),
}

_WD_RETIRED = frozenset({"not_indexed"})


def _watchdog_finding(text: str) -> dict:
    raw = (text or "").strip()
    body, action = (raw.rsplit(" — ", 1) if " — " in raw else (raw, ""))
    kind = "other"
    for name, pattern in _WD_RULES:
        if pattern.search(body):
            kind = name
            break
    title_key, action_key, tone, tail_is_action = _WD_KINDS[kind]
    match = next((p.search(body) for n, p in _WD_RULES if n == kind), None)
    groups = [g for g in (match.groups() if match else ()) if g]
    what_key = "wd_what_" + kind
    data: dict[str, str] = {}
    if kind in ("not_indexed", "isolated", "wikilink", "evidence_store", "evidence_stale", "index_stale",
                "unsplit_ingest", "harvest_unread", "harvest_zstd", "engine_copies") and groups:
        data["n"] = groups[0]
    elif kind == "commit_backlog" and len(groups) >= 2:
        data["n"], data["hours"] = groups[0], groups[1]
    elif kind in ("control_missing", "control_changed", "control_template") and groups:
        data["name"] = groups[0]
    elif kind == "project_reregistered":
        ids = _WD_IDS.search(body)
        if ids:
            data["id"], data["expected"] = ids.group(1), ids.group(2)
    elif kind == "mirror" and len(groups) >= 2:
        data["n"], data["remote"] = groups[0], groups[1]
    elif kind == "pages_down" and len(groups) >= 2:
        data["before"], data["after"] = groups[0], groups[1]
    elif kind == "identity":
        ids = _WD_IDS.search(body)
        if ids:
            data["id"], data["expected"] = ids.group(1), ids.group(2)
    elif kind == "crash":
        head, _sep, tail = body.partition("ÇÖKTÜ:")
        data["fn"] = head.strip() or "?"
        data["error"] = tail.strip()
    kwargs = ({"fn": data["fn"], "detail": _tx("wd_detail_short")} if kind == "crash" else dict(data))
    weight = int(groups[0]) if groups and groups[0].isdigit() else None
    return {
        "kind": kind,
        "n": weight,
        "title": _tx(title_key),
        "tone": tone,
        "what": _tx(what_key, **kwargs),
        "action": (_sentence(action) if tail_is_action and action.strip() else _tx(action_key)),
        "by_watchdog": bool(tail_is_action and action.strip()),
        "retired": kind in _WD_RETIRED,
        "detail": body.strip(),
        "raw": raw,
        "data": data,
    }


@router.post("/health/watchdog/clear")
def health_watchdog_clear(body: dict):
    log = _audit_dir() / "alerts.log"
    if (body or {}).get("confirm") is not True:
        return {"ok": False, "removed": 0, "archive": None, "error": _tx("wd_clear_refused")}
    if not log.exists():
        return {"ok": True, "removed": 0, "archive": None, "message": _tx("wd_cleared", n=0)}
    original = log.read_bytes()
    runs = 0
    for raw in original.decode("utf-8", errors="replace").splitlines():
        if raw.startswith("[") and raw.rstrip().endswith("]"):
            runs += 1
    if not original.strip():
        return {"ok": True, "removed": 0, "archive": None, "message": _tx("wd_cleared", n=0)}
    try:
        path = _fresh_path("alerts", ".log")
    except OSError as exc:
        _log.warning("wiki-automation: backups folder unusable: %s", exc)
        return {"ok": False, "removed": 0, "archive": None,
                "error": _tx("wd_backups_unusable", path=_backups_path(), error=exc)}
    try:
        path.write_bytes(original)
        copied = path.read_bytes()
    except OSError as exc:
        _log.warning("wiki-automation: alerts.log archive %s could not be written: %s", path, exc)
        return {"ok": False, "removed": 0, "archive": None,
                "error": f"the archive could not be written, alerts.log is untouched: {exc}"}
    if copied != original:
        return {"ok": False, "removed": 0, "archive": str(path),
                "error": "the archive does not match alerts.log, so alerts.log is untouched"}
    try:
        current = log.read_bytes()
        if not current.startswith(copied):
            return {"ok": False, "removed": 0, "archive": str(path),
                    "error": "alerts.log changed after it was archived, so it is untouched"}
        rest = current[len(copied):]
        tmp = log.with_name(f".{log.name}.{os.getpid()}.tmp")
        try:
            tmp.write_bytes(rest)
            os.replace(tmp, log)
        finally:
            if tmp.exists():
                tmp.unlink()
    except OSError as exc:
        _log.warning("wiki-automation: alerts.log could not be emptied: %s", exc)
        return {"ok": False, "removed": 0, "archive": str(path),
                "error": f"alerts.log could not be emptied: {exc}"}
    return {"ok": True, "removed": runs, "archive": str(path),
            "archive_sha256": hashlib.sha256(copied).hexdigest(),
            "message": _tx("wd_cleared", n=runs)}


@router.get("/health/watchdog")
@_selected_operation
def health_watchdog(limit: int = 1000):
    run_limit = max(1, min(int(limit), 1000))
    log = _audit_dir() / "alerts.log"
    state_path = _audit_dir() / "state.json"
    kept: deque[dict] = deque(maxlen=run_limit)
    total = 0
    if log.exists():
        current: dict | None = None
        with log.open(encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.rstrip()
                if line.startswith("[") and line.endswith("]"):
                    if current is not None and current["findings"]:
                        total += 1
                        kept.append(current)
                    current = {"at": line[1:-1].strip(), "findings": []}
                elif line.startswith("- ") and current is not None:
                    current["findings"].append(line[2:].strip())
        if current is not None and current["findings"]:
            total += 1
            kept.append(current)
    runs = list(kept)
    for run in runs:
        run["ts"], run["date"] = _watchdog_time(run["at"])
        run["items"] = [{**_watchdog_finding(f), "ts": run["ts"], "date": run["date"], "at": run["at"]}
                        for f in run["findings"]]
    state: dict = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _log.warning("wiki-automation: state.json unreadable (%s), read as empty: %s", state_path, exc)
            state = {}
    if state.get("checked"):
        state["checked_ts"] = _watchdog_time(str(state["checked"]))[0]
    return {
        "runs": runs[::-1],
        "total": total,
        "state": state,
        "log": str(log),
    }


_WD_TIME_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\D+(\d{1,2}):(\d{2}):(\d{2})")


def _watchdog_time(at: str) -> tuple[float | None, str | None]:
    match = _WD_TIME_RE.search(at or "")
    if not match:
        return None, None
    day, month, year, hour, minute, second = (int(g) for g in match.groups())
    try:
        when = datetime.datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None, None
    return when.timestamp(), when.strftime("%Y-%m-%d")


CRON_DIR: Path | None = None
MAX_RUNS = 3000
TREND_BUCKETS = 24
BODY_PREVIEW = 400
BODY_FULL_MAX = 200_000
WINDOW_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30, "all": None}
_WD_JOB_COLS = ("id, job_id, status, delivery_outcome, error, claimed_at, started_at, finished_at,"
             " scheduled_instant, pid, source")
_OUT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})\.md$")


def _cron_dir() -> Path:
    return CRON_DIR if CRON_DIR is not None else _hermes_home() / "cron"



def _backups_path() -> Path:
    return _hermes_home() / "backups" / "wiki-watchdog"


def _backups_dir() -> Path:
    out = _backups_path()
    out.mkdir(parents=True, exist_ok=True)
    return out


def _fresh_path(prefix: str, suffix: str) -> Path:
    folder = _backups_dir()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = folder / f"{prefix}-{stamp}{suffix}"
    serial = 1
    while path.exists():
        path = folder / f"{prefix}-{stamp}-{serial}{suffix}"
        serial += 1
    return path


ACTIVE_STATUSES = ("running", "claimed")



class _StoreError(Exception):
    pass


def _chunks(items: list[str], size: int = 400) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _archive_and_clear(keys: list[str]) -> dict:
    ids = sorted({str(k).strip() for k in keys if str(k).strip()})
    requested = len(ids)
    if not ids:
        return {"ok": False, "error": "no keys were given", "cleared": 0, "missing": 0}
    db = _cron_dir() / "executions.db"
    if not db.exists():
        return {"ok": False, "error": "there is no run store to clear", "cleared": 0, "missing": 0}
    rows: list[dict] = []
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5.0)
        con.row_factory = sqlite3.Row
        for chunk in _chunks(ids):
            marks = ",".join("?" for _ in chunk)
            rows.extend(dict(r) for r in
                        con.execute(f"select * from executions where id in ({marks})", chunk))
        con.close()
    except sqlite3.Error as exc:
        return {"ok": False, "error": f"the run store could not be read: {exc}", "cleared": 0,
                "missing": 0}
    found = len(rows)
    active = sum(1 for r in rows if str(r.get("status")) in ACTIVE_STATUSES)
    rows = [r for r in rows if str(r.get("status")) not in ACTIVE_STATUSES]
    ids = [str(r.get("id")) for r in rows]
    note = _tx("jb_active_kept", n=active) if active else None
    if not rows:
        return {"ok": True, "cleared": 0, "missing": requested - found, "active": active,
                "archive": None,
                "note": note or "none of those records is in the store any more"}
    archive = {"archived_at": datetime.datetime.now().isoformat(timespec="seconds"),
               "requested": requested, "found": len(rows), "rows": rows}
    try:
        path = _fresh_path("runs", ".json")
        path.write_text(json.dumps(archive, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    except OSError as exc:
        _log.warning("wiki-automation: run archive could not be written: %s", exc)
        return {"ok": False, "error": f"the archive could not be written: {exc}", "cleared": 0,
                "missing": 0, "active": active}
    try:
        back = json.loads(path.read_text(encoding="utf-8"))
        archived_ids = [str(r.get("id")) for r in back["rows"]]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": f"the archive could not be read back: {exc}", "cleared": 0,
                "missing": 0, "archive": str(path)}
    if archived_ids != [str(r.get("id")) for r in rows]:
        return {"ok": False, "error": "the archive does not match the records", "cleared": 0,
                "missing": 0, "archive": str(path)}
    removed = 0
    try:
        w = sqlite3.connect(str(db), timeout=10.0)
        try:
            w.execute("begin immediate")
            for chunk in _chunks(ids):
                marks = ",".join("?" for _ in chunk)
                removed += w.execute(f"delete from executions where id in ({marks})"
                                     " and status not in ('running', 'claimed')", chunk).rowcount
            if removed != len(rows):
                w.rollback()
                return {"ok": False, "cleared": 0, "missing": 0, "archive": str(path),
                        "error": f"the store removed {removed} of {len(rows)} records, so nothing"
                                 " was removed"}
            w.commit()
        finally:
            w.close()
    except sqlite3.Error as exc:
        return {"ok": False, "error": f"the store refused the removal: {exc}", "cleared": 0,
                "missing": 0, "archive": str(path)}
    return {"ok": True, "cleared": removed, "missing": requested - found, "active": active,
            "note": note, "archive": str(path),
            "archive_bytes": path.stat().st_size,
            "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _wd_iso(ts: object) -> datetime.datetime | None:
    try:
        when = datetime.datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo is not None else when.astimezone()


def _job_registry() -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        data = json.loads((_cron_dir() / "jobs.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return out
    except (OSError, ValueError) as exc:
        _log.warning("wiki-automation: jobs.json unreadable, the job list is empty: %s", exc)
        return out
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    for job in (jobs if isinstance(jobs, list) else []):
        job = job or {}
        jid = str(job.get("id") or "")
        if not jid:
            continue
        sched = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
        out[jid] = {
            "id": jid,
            "name": job.get("name"),
            "live": True,
            "schedule": job.get("schedule_display") or sched.get("display"),
            "script": job.get("script"),
            "mode": "script" if job.get("no_agent") else "agent",
            "deliver": job.get("deliver"),
            "state": job.get("state"),
            "enabled": bool(job.get("enabled")),
            "last_status": job.get("last_status"),
            "last_error": job.get("last_error"),
            "last_run_at": job.get("last_run_at"),
            "next_run_at": job.get("next_run_at"),
        }
    return out


_AT_UTC = "coalesce(julianday(claimed_at), 0)"


def _utc_floor(since: datetime.datetime) -> str:
    return since.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _executions(limit: int, since: datetime.datetime | None = None) -> tuple[list[dict], bool]:
    db = _cron_dir() / "executions.db"
    if not db.exists():
        return [], False
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=3.0)
    except sqlite3.Error as exc:
        _log.warning("wiki-automation: %s could not be opened: %s", db, exc)
        raise _StoreError(f"the run store could not be opened: {exc}") from exc
    try:
        con.row_factory = sqlite3.Row
        if since is None:
            rows = con.execute(f"select {_WD_JOB_COLS} from executions"
                               f" order by {_AT_UTC} desc limit ?", (limit + 1,)).fetchall()
        else:
            rows = con.execute(f"select {_WD_JOB_COLS} from executions"
                               " where julianday(claimed_at) >= julianday(?)"
                               f" order by {_AT_UTC} desc limit ?",
                               (_utc_floor(since), limit + 1)).fetchall()
    except sqlite3.Error as exc:
        _log.warning("wiki-automation: %s could not be read: %s", db, exc)
        raise _StoreError(f"the run store could not be read: {exc}") from exc
    finally:
        con.close()
    return [dict(r) for r in rows[:limit]], len(rows) > limit


def _trend_rows(since: datetime.datetime | None) -> tuple[list[dict], bool]:
    db = _cron_dir() / "executions.db"
    if not db.exists():
        return [], False
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=3.0)
    except sqlite3.Error as exc:
        _log.warning("wiki-automation: %s could not be opened for the trend: %s", db, exc)
        raise _StoreError(f"the run store could not be opened: {exc}") from exc
    try:
        con.row_factory = sqlite3.Row
        if since is None:
            rows = con.execute(f"select {_WD_JOB_COLS} from executions"
                               f" order by {_AT_UTC} desc limit ?", (MAX_RUNS + 1,)).fetchall()
        else:
            rows = con.execute(f"select {_WD_JOB_COLS} from executions"
                               " where julianday(claimed_at) >= julianday(?)"
                               f" order by {_AT_UTC} desc limit ?",
                               (_utc_floor(since), MAX_RUNS + 1)).fetchall()
    except sqlite3.Error as exc:
        _log.warning("wiki-automation: %s could not be read for the trend: %s", db, exc)
        raise _StoreError(f"the run store could not be read: {exc}") from exc
    finally:
        con.close()
    return [dict(r) for r in rows[:MAX_RUNS]], len(rows) > MAX_RUNS


def _trend(span_hours: int | None, now: datetime.datetime) -> dict:
    empty = {"bucket_hours": 0, "buckets": [], "prev": None, "prev_basis": None, "per_job": {},
             "trend_truncated": False}
    whole = span_hours is None
    if whole:
        rows, truncated = _trend_rows(None)
        stamps = [when for when in (_wd_iso(r.get("claimed_at")) for r in rows) if when is not None]
        if not stamps:
            return empty
        span_hours = max(24, int((now - min(stamps)).total_seconds() // 3600) + 1)
    elif not span_hours:
        return empty
    else:
        rows, truncated = _trend_rows(now - datetime.timedelta(hours=2 * span_hours))
    bucket_h = max(1, -(-span_hours // TREND_BUCKETS))
    count = -(-span_hours // bucket_h)
    edges = [now - datetime.timedelta(hours=(count - index) * bucket_h) for index in range(count)]

    def blank() -> list[dict]:
        return [{"iso": edge.isoformat(timespec="seconds"), "runs": 0, "failed": 0, "silent": 0,
                 "delivered": 0} for edge in edges]

    buckets = blank()
    prev = {"runs": 0, "failed": 0, "silent": 0, "delivered": 0}
    per_job: dict[str, list[dict]] = {}
    floor = now - datetime.timedelta(hours=span_hours)
    for row in rows:
        when = _wd_iso(row.get("claimed_at"))
        if when is None:
            continue
        failed = 1 if str(row.get("status")) == "failed" else 0
        delivery = str(row.get("delivery_outcome"))
        silent = 1 if delivery == "suppressed" else 0
        delivered = 1 if delivery == "delivered" else 0
        if when < floor:
            prev["runs"] += 1
            prev["failed"] += failed
            prev["silent"] += silent
            prev["delivered"] += delivered
            continue
        age = (now - when).total_seconds() / 3600
        index = min(count - 1, max(0, count - 1 - int(age // bucket_h)))
        for slots in (buckets, per_job.setdefault(str(row.get("job_id") or ""), blank())):
            slot = slots[index]
            slot["runs"] += 1
            slot["failed"] += failed
            slot["silent"] += silent
            slot["delivered"] += delivered
    return {"bucket_hours": bucket_h, "buckets": buckets, "prev": None if whole else prev,
            "prev_basis": None if whole else f"{span_hours}h", "per_job": per_job,
            "trend_truncated": truncated}


def _output_index(job_id: str) -> list[tuple[float, Path]]:
    items: list[tuple[float, Path]] = []
    try:
        for p in (_cron_dir() / "output" / job_id).glob("*.md"):
            m = _OUT_RE.match(p.name)
            if not m:
                continue
            try:
                when = datetime.datetime(*(int(g) for g in m.groups()))
            except ValueError:
                continue
            items.append((when.timestamp(), p))
    except OSError as exc:
        _log.warning("wiki-automation: output folder of job %s unreadable: %s", job_id, exc)
    return sorted(items, reverse=True)


_HEADER_FIELD = re.compile(r"\*\*[^*\n]+:\*\*( |$)")


_PROMPT_FRAMED = re.compile(r"(?m)^\*\*Prompt Characters:\*\* (\d+)\n## Prompt\n\n")
_RESPONSE_FRAMED = re.compile(r"\*\*Response Characters:\*\* (\d+)\n## Response\n\n")


def _strip_header(raw: str) -> str:
    text = raw.replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines[0].startswith("# Cron Job:"):
        marker = "\n---\n"
        return text.split(marker, 1)[1].strip() if marker in text else text.strip()
    framed = _PROMPT_FRAMED.search(text)
    if framed:
        after = framed.end() + int(framed.group(1))
        reply = _RESPONSE_FRAMED.match(text, after + 2) or _RESPONSE_FRAMED.search(text, after)
        if reply:
            return text[reply.end():reply.end() + int(reply.group(1))].strip()
    index = 1
    while index < len(lines):
        line = lines[index]
        if line == "---" or line.startswith("**Status:**"):
            return "\n".join(lines[index + 1:]).strip()
        if line == "## Prompt":
            rest = "\n".join(lines[index:])
            cut, heading = max((rest.rfind(h), h) for h in ("\n## Response\n", "\n## Error\n"))
            return rest[cut + len(heading):].strip() if cut >= 0 else rest.strip()
        if line.strip() and not _HEADER_FIELD.match(line):
            break
        index += 1
    return "\n".join(lines[index:]).strip()


def _body_for(job_id: str, claimed: datetime.datetime | None, finished: datetime.datetime | None,
              error: object, cache: dict[str, list[tuple[float, Path]]]) -> tuple[str, str]:
    if job_id not in cache:
        cache[job_id] = _output_index(job_id)
    if claimed is not None and finished is not None:
        floor, ceiling = claimed.timestamp() - 1, finished.timestamp() + 1
        hit = max((it for it in cache[job_id] if floor <= it[0] <= ceiling), key=lambda it: it[0], default=None)
        if hit is not None:
            try:
                return _strip_header(hit[1].read_text(encoding="utf-8", errors="replace")), "output"
            except OSError as exc:
                _log.warning("wiki-automation: run output %s unreadable: %s", hit[1], exc)
    if error:
        return str(error), "error"
    return "", "none"


def _body_findings(body: str) -> list[dict]:
    return [_watchdog_finding(line.strip()[2:])
            for line in (body or "").splitlines() if line.strip().startswith("- ")]


def _by_runs(entry: tuple) -> int:
    return int((entry[1] or {}).get("runs") or 0)


def _run_record(row: dict, registry: dict[str, dict],
                cache: dict[str, list[tuple[float, Path]]]) -> dict:
    jid = str(row.get("job_id") or "")
    meta = registry.get(jid) or {}
    claimed = _wd_iso(row.get("claimed_at"))
    started = _wd_iso(row.get("started_at"))
    finished = _wd_iso(row.get("finished_at"))
    sched = _wd_iso(row.get("scheduled_instant"))
    body, source = _body_for(jid, claimed, finished, row.get("error"), cache)
    status = str(row.get("status") or "unknown")
    delivery = str(row.get("delivery_outcome") or "none")
    findings = [] if meta.get("mode") == "agent" else _body_findings(body)
    return {
        "id": row.get("id"),
        "job_id": jid,
        "job_name": meta.get("name"),
        "job_live": bool(meta.get("live")),
        "at": row.get("claimed_at"),
        "at_ts": claimed.timestamp() if claimed else None,
        "date": claimed.strftime("%Y-%m-%d") if claimed else None,
        "scheduled_at": row.get("scheduled_instant"),
        "finished_at": row.get("finished_at"),
        "status": status,
        "status_label": _jb_label("status", status),
        "delivery": delivery,
        "delivery_label": _jb_label("delivery", delivery),
        "duration_ms": (int((finished - started).total_seconds() * 1000)
                        if (finished and started) else None),
        "lateness_s": round((claimed - sched).total_seconds(), 1) if (claimed and sched) else None,
        "silent": bool(delivery == "suppressed" and not (body or "").strip()),
        "body": (body or "")[:BODY_PREVIEW],
        "body_len": len(body or ""),
        "body_source": source,
        "body_label": _jb_label("body", source),
        "findings": findings,
        "findings_count": len(findings),
    }


@router.get("/health/jobs")
def health_jobs(window: str = "24h", limit: int = MAX_RUNS):
    win = window if window in WINDOW_HOURS else "24h"
    hours = WINDOW_HOURS[win]
    cap = max(1, min(int(limit), MAX_RUNS))
    now = datetime.datetime.now().astimezone()
    since = now - datetime.timedelta(hours=hours) if hours else None

    registry = _job_registry()
    try:
        rows, truncated = _executions(cap, since)
        trend = _trend(hours, now)
    except _StoreError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "cron_dir": str(_cron_dir())},
                            status_code=503)
    cache: dict[str, list[tuple[float, Path]]] = {}
    runs: list[dict] = []
    for row in rows:
        when = _wd_iso(row.get("claimed_at"))
        if since is not None and when is not None and when < since:
            continue
        runs.append(_run_record(row, registry, cache))

    per_job: dict[str, dict] = {}
    for r in runs:
        agg = per_job.setdefault(r["job_id"], {"runs": 0, "failed": 0, "silent": 0,
                                               "delivered": 0, "findings": 0, "last_at": None})
        agg["runs"] += 1
        agg["failed"] += 1 if r["status"] == "failed" else 0
        agg["silent"] += 1 if r["silent"] else 0
        agg["delivered"] += 1 if r["delivery"] == "delivered" else 0
        agg["findings"] += r["findings_count"]
        if agg["last_at"] is None:
            agg["last_at"] = r["at"]

    empty = {"runs": 0, "failed": 0, "silent": 0, "delivered": 0, "findings": 0, "last_at": None}
    registry_out: list[dict] = []
    for jid, meta in registry.items():
        registry_out.append({**meta, **per_job.pop(jid, dict(empty))})
    for jid, agg in sorted(per_job.items(), key=_by_runs, reverse=True):
        registry_out.append({"id": jid, "name": None, "live": False, "schedule": None,
                             "script": None, "mode": None, "deliver": None, "state": None,
                             "enabled": False, "last_status": None, "last_error": None,
                             "last_run_at": None, "next_run_at": None, **agg})
    registry_out.sort(key=lambda e: (not e["live"], -(e.get("runs") or 0)))

    return {
        "trend": trend,
        "generatedAt": now.isoformat(timespec="seconds"),
        "window": win,
        "since": since.isoformat(timespec="seconds") if since else None,
        "truncated": truncated,
        "cap": cap,
        "cron_dir": str(_cron_dir()),
        "registry": registry_out,
        "runs": runs,
        "totals": {
            "runs": len(runs),
            "failed": sum(1 for r in runs if r["status"] == "failed"),
            "silent": sum(1 for r in runs if r["silent"]),
            "delivered": sum(1 for r in runs if r["delivery"] == "delivered"),
            "findings": sum(1 for r in runs if r["findings_count"]),
            "jobs": len(registry_out),
            "deleted_jobs": sum(1 for e in registry_out if not e["live"]),
        },
    }


@router.post("/health/runs/archive-clear")
def health_runs_archive_clear(body: dict):
    keys = (body or {}).get("keys")
    if not isinstance(keys, list):
        return {"ok": False, "error": "keys must be a list of record ids", "cleared": 0, "missing": 0}
    if len(keys) > MAX_RUNS:
        return {"ok": False, "error": _tx("jb_keys_too_many", cap=MAX_RUNS, n=len(keys)),
                "cleared": 0, "missing": 0}
    return _archive_and_clear(keys)


@router.get("/health/jobs/run")
def health_job_run(id: str = "", job_id: str = "", at: str = ""):
    db = _cron_dir() / "executions.db"
    row: dict | None = None
    if db.exists():
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=3.0)
        except sqlite3.Error as exc:
            _log.warning("wiki-automation: %s could not be opened for a run: %s", db, exc)
            return JSONResponse({"ok": False, "error": f"the run store could not be opened: {exc}"},
                                status_code=503)
        if con is not None:
            try:
                con.row_factory = sqlite3.Row
                if id:
                    found = con.execute(f"select {_WD_JOB_COLS} from executions where id = ?",
                                        (id,)).fetchone()
                elif job_id and at:
                    found = con.execute(f"select {_WD_JOB_COLS} from executions"
                                        " where job_id = ? and claimed_at = ?",
                                        (job_id, at)).fetchone()
                else:
                    found = None
                row = dict(found) if found else None
            except sqlite3.Error as exc:
                _log.warning("wiki-automation: %s could not be read for a run: %s", db, exc)
                return JSONResponse({"ok": False,
                                     "error": f"the run store could not be read: {exc}"},
                                    status_code=503)
            finally:
                con.close()
    if row is None:
        return JSONResponse({"ok": False, "error": _tx("jb_run_missing")}, status_code=404)
    registry = _job_registry()
    rec = _run_record(row, registry, {})
    claimed = _wd_iso(row.get("claimed_at"))
    body, source = _body_for(str(row.get("job_id") or ""), claimed, _wd_iso(row.get("finished_at")),
                             row.get("error"), {})
    return {
        "ok": True,
        "id": rec["id"], "job_id": rec["job_id"], "job_name": rec["job_name"],
        "job_live": rec["job_live"], "at": rec["at"], "status": rec["status"],
        "status_label": rec["status_label"], "delivery": rec["delivery"],
        "delivery_label": rec["delivery_label"],
        "body": body[:BODY_FULL_MAX], "body_len": len(body),
        "body_source": source, "body_label": _jb_label("body", source),
        "truncated": len(body) > BODY_FULL_MAX,
    }


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class _captured:
    def __enter__(self) -> list[str]:
        self.handler = _Capture()
        _log.addHandler(self.handler)
        return self.handler.messages

    def __exit__(self, *exc: object) -> None:
        _log.removeHandler(self.handler)


def _health_selftest_body() -> int:
    import tempfile

    global AUDIT_DIR, CRON_DIR, MAX_RUNS, _backups_dir
    keep = AUDIT_DIR
    with tempfile.TemporaryDirectory(prefix="wiki-automation-health-") as tmp:
        try:
            AUDIT_DIR = Path(tmp) / "audit"
            AUDIT_DIR.mkdir(parents=True)
            (AUDIT_DIR / "alerts.log").write_text(
                "[bilinmeyen damga]\n- damgasız bulgu\n\n"
                "[Pzt 14.09.2026  7:02:58,57]\n- eski bulgu\n\n"
                "[Sal 15.09.2026 10:22:56,44]\n- yeni bulgu A\n- yeni bulgu B\n", encoding="utf-8")
            (AUDIT_DIR / "state.json").write_text(
                '{"pages": 204, "checked": "Sal 15.09.2026 10:22:56,03"}', encoding="utf-8")
            wd = health_watchdog(limit=10)
            assert wd["total"] == 3 and len(wd["runs"]) == 3, wd
            assert wd["runs"][0]["at"].startswith("Sal 15.09"), wd["runs"][0]["at"]
            assert wd["runs"][0]["date"] == "2026-09-15", wd["runs"][0]
            assert wd["runs"][1]["date"] == "2026-09-14", wd["runs"][1]
            assert wd["runs"][2]["date"] is None, wd["runs"][2]
            assert wd["runs"][0]["ts"] > wd["runs"][1]["ts"] > 0, "epoch order is wrong"
            assert all(it["date"] == "2026-09-15" for it in wd["runs"][0]["items"]), wd["runs"][0]["items"]
            assert len(health_watchdog(limit=1)["runs"]) == 1, "limit was not applied"
            assert wd["state"]["pages"] == 204, wd["state"]
            assert wd["state"]["checked_ts"] > 0, wd["state"]
            assert _watchdog_time("Sal 15.09.2026  7:04:31,84")[1] == "2026-09-15"
            assert _watchdog_time("tamamen bozuk damga") == (None, None)
            assert _watchdog_time("Sal 31.02.2026 10:00:00,00") == (None, None), "impossible day"
            before = (AUDIT_DIR / "alerts.log").read_bytes()
            refused = health_watchdog_clear({})
            assert refused["ok"] is False and refused["removed"] == 0, refused
            assert (AUDIT_DIR / "alerts.log").read_bytes() == before, "an unconfirmed clear touched the log"
            keep_home = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = str(Path(tmp) / "home")
            try:
                assert _backups_dir() == Path(tmp) / "home" / "backups" / "wiki-watchdog", _backups_dir()
                assert Path(__file__).resolve().parent.parent not in _backups_dir().parents, \
                    "backups must live outside the plugin folder"
                cleared = health_watchdog_clear({"confirm": True})
                assert cleared["ok"] and cleared["removed"] == 3, cleared
                saved = Path(cleared["archive"])
                assert saved.parent == _backups_dir() and saved.read_bytes() == before, cleared
                assert (AUDIT_DIR / "alerts.log").read_text(encoding="utf-8") == "", "log was not emptied"
                assert (AUDIT_DIR / "state.json").exists(), "state.json must survive"
                again = health_watchdog_clear({"confirm": True})
                assert again["ok"] and again["removed"] == 0 and again["archive"] is None, again
                log = AUDIT_DIR / "alerts.log"
                first_run = "[Sal 15.09.2026 10:22:56,44]\n- ilk bulgu\n".encode("utf-8")
                late_run = "[Sal 15.09.2026 10:30:00,00]\n- geç bulgu\n".encode("utf-8")
                log.write_bytes(first_run)
                real_fresh = _fresh_path

                def racing_fresh(prefix: str, suffix: str) -> Path:
                    with log.open("ab") as fh:
                        fh.write(late_run)
                    return real_fresh(prefix, suffix)

                globals()["_fresh_path"] = racing_fresh
                try:
                    raced = health_watchdog_clear({"confirm": True})
                finally:
                    globals()["_fresh_path"] = real_fresh
                assert raced["ok"] and raced["removed"] == 1, raced
                assert Path(raced["archive"]).read_bytes() == first_run, "the archive lost the original lines"
                assert log.read_bytes() == late_run, \
                    f"a line appended between the read and the clear was lost: {log.read_bytes()!r}"
                assert not [p for p in AUDIT_DIR.iterdir() if p.name not in ("alerts.log", "state.json")], \
                    f"the atomic rewrite left a temp file behind: {sorted(p.name for p in AUDIT_DIR.iterdir())}"
                log.write_bytes(first_run)
                rewritten = "[Çar 16.09.2026 09:00:00,00]\n- başka dosya\n".encode("utf-8")

                def replacing_fresh(prefix: str, suffix: str) -> Path:
                    log.write_bytes(rewritten)
                    return real_fresh(prefix, suffix)

                globals()["_fresh_path"] = replacing_fresh
                try:
                    swapped = health_watchdog_clear({"confirm": True})
                finally:
                    globals()["_fresh_path"] = real_fresh
                assert swapped["ok"] is False and swapped["removed"] == 0, swapped
                assert Path(swapped["archive"]).read_bytes() == first_run, swapped
                assert log.read_bytes() == rewritten, "a log that no longer starts with the archive was touched"
            finally:
                if keep_home is None:
                    os.environ.pop("HERMES_HOME", None)
                else:
                    os.environ["HERMES_HOME"] = keep_home
            (AUDIT_DIR / "alerts.log").write_text("[Sal 15.09.2026 10:22:56,44]\n- yeni bulgu\n", encoding="utf-8")
            (AUDIT_DIR / "state.json").write_text("{bozuk", encoding="utf-8")
            with _captured() as seen:
                assert health_watchdog()["state"] == {}, "a broken state file must read as empty"
            assert any("state.json" in m for m in seen), f"a broken state.json was swallowed silently: {seen}"
            (AUDIT_DIR / "alerts.log").write_text(
                "".join(f"[Sal 15.09.2026 10:{i:02d}:00,00]\n- bulgu {i}\n" for i in range(25)),
                encoding="utf-8")
            assert len(health_watchdog()["runs"]) == 25, "the default limit must read the whole history"
            assert len(health_watchdog(limit=2)["runs"]) == 2, "an explicit limit must apply"
            import tracemalloc
            with (AUDIT_DIR / "alerts.log").open("w", encoding="utf-8") as fh:
                for i in range(60000):
                    fh.write(f"[Sal 15.09.2026 10:{i % 60:02d}:00,00]\n- bulgu {i} {'x' * 60}\n\n")
            tracemalloc.start()
            try:
                big = health_watchdog()
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            assert big["total"] == 60000 and len(big["runs"]) == 1000, (big["total"], len(big["runs"]))
            assert big["runs"][0]["findings"][0].startswith("bulgu 59999 "), big["runs"][0]["findings"]
            assert peak < 16 * 1024 * 1024, f"alerts.log is read whole, peak {peak} bytes"
        finally:
            AUDIT_DIR = keep

    for kind, (title_key, action_key, _tone, _tail) in _WD_KINDS.items():
        assert title_key in _EXPLAIN_TEXT, title_key
        assert action_key in _EXPLAIN_TEXT, action_key
        assert f"wd_what_{kind}" in _EXPLAIN_TEXT, kind
    assert _tx("wd_other_title") == "Other finding", _tx("wd_other_title")
    assert _tx("wd_what_isolated", n=3) == "3 page(s) have no links at all (graph degree 0); " \
        "they sit alone in the app graph.", _tx("wd_what_isolated", n=3)
    unknown_key = "yok_böyle_anahtar"
    missing_args = "wd_what_isolated"
    assert _tx(missing_args) == _EXPLAIN_TEXT[missing_args], "a missing argument must not raise"
    with _captured() as seen:
        assert _tx(missing_args, **{"wrong": 1}) == _EXPLAIN_TEXT[missing_args]
    assert any(missing_args in m for m in seen), f"_tx did not log through the logger: {seen}"
    assert _tx(unknown_key) == unknown_key, "an unknown key must come back as itself"

    global CRON_DIR
    keep_cron = CRON_DIR
    with tempfile.TemporaryDirectory(prefix="wiki-jobs-") as jobstmp:
        keep_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(Path(jobstmp) / "moved-home")
        try:
            assert _cron_dir() == Path(jobstmp) / "moved-home" / "cron", \
                f"the run store stayed on the home seen at import: {_cron_dir()}"
            moved = health_jobs(window="24h")
            assert moved["cron_dir"] == str(Path(jobstmp) / "moved-home" / "cron"), moved["cron_dir"]
        finally:
            if keep_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = keep_home
        try:
            cron = Path(jobstmp) / "cron"
            (cron / "output" / "live1").mkdir(parents=True)
            (cron / "jobs.json").write_text(json.dumps({"jobs": [
                {"id": "live1", "name": "Live One", "no_agent": True, "script": "a.py",
                 "deliver": "ntfy", "enabled": True, "state": "scheduled",
                 "schedule_display": "every 10m", "last_status": "ok"},
            ]}), encoding="utf-8")
            con = sqlite3.connect(cron / "executions.db")
            con.execute(
                "create table executions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL,"
                " source TEXT NOT NULL, process_id TEXT NOT NULL, pid INTEGER NOT NULL,"
                " process_started_at INTEGER, status TEXT NOT NULL,"
                " handoff_pending INTEGER NOT NULL DEFAULT 0, handoff_started_at REAL,"
                " claimed_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, error TEXT,"
                " delivery_outcome TEXT, scheduled_instant TEXT)")
            now = datetime.datetime.now().astimezone()

            def inst(hours_ago: float, late_s: int = 0) -> tuple[str, str, str, str, str]:
                when = (now - datetime.timedelta(hours=hours_ago)).replace(microsecond=0)
                started = when + datetime.timedelta(milliseconds=200)
                finished = when + datetime.timedelta(seconds=1)
                planned = when - datetime.timedelta(seconds=late_s)
                return (when.isoformat(timespec="seconds"),
                        started.isoformat(timespec="milliseconds"),
                        finished.isoformat(timespec="seconds"),
                        planned.astimezone(datetime.timezone.utc).isoformat(timespec="seconds"),
                        when.strftime("%Y-%m-%d_%H-%M-%S"))

            e1, e2, e3 = inst(2), inst(2.2, late_s=60), inst(3)
            e4, e5, e6 = inst(4), inst(5), inst(8 * 24)
            con.executemany(
                "insert into executions (id, job_id, status, delivery_outcome, error, claimed_at,"
                " started_at, finished_at, scheduled_instant, source, process_id, pid)"
                " values (?,?,?,?,?,?,?,?,?,'builtin','p',1)", [
                    ("e1", "live1", "completed", "delivered", None,
                     e1[0], e1[1], e1[2], e1[3]),
                    ("e2", "live1", "completed", "suppressed", None,
                     e2[0], e2[1], e2[2], e2[3]),
                    ("e3", "gone1", "completed", "suppressed", None,
                     e3[0], None, None, e3[3]),
                    ("e4", "live1", "failed", "delivered",
                     "Script exited with code 1\nstdout:\n⚠ denetim",
                     e4[0], e4[1], e4[2], e4[3]),
                    ("e5", "live1", "running", None, None,
                     e5[0], None, None, e5[3]),
                    ("e6", "live1", "completed", "delivered", None,
                     e6[0], e6[1], e6[2], e6[3]),
                ])
            con.commit()
            con.close()
            (cron / "output" / "live1" / f"{e1[4]}.md").write_text(
                "# Cron Job: Live One\r\n\r\n**Job ID:** live1\r\n"
                f"**Run Time:** {e1[0][:10]} {e1[0][11:19]}\r\n"
                "**Mode:** no_agent (script)\r\n\r\n---\r\n\r\n⚠ 1 bulgu\r\n"
                "- 3 commit 'onedrive' mirror'una gitmemiş — yedeği çalıştır\r\n", encoding="utf-8")
            CRON_DIR = cron
            data = health_jobs(window="24h")
            assert {e["id"] for e in data["registry"]} == {"live1", "gone1"}, data["registry"]
            gone = next(e for e in data["registry"] if e["id"] == "gone1")
            assert gone["live"] is False and gone["name"] is None and gone["runs"] == 1, gone
            live = next(e for e in data["registry"] if e["id"] == "live1")
            assert live["live"] is True and live["name"] == "Live One", live
            assert live["script"] == "a.py" and live["mode"] == "script", live
            assert data["registry"][0]["live"] is True, "live jobs must come first"
            assert data["totals"]["deleted_jobs"] == 1, data["totals"]
            assert data["totals"]["runs"] == 5, data["totals"]
            by = {r["id"]: r for r in data["runs"]}
            assert by["e1"]["body_source"] == "output", by["e1"]
            assert by["e1"]["findings_count"] == 1, by["e1"]["findings"]
            assert by["e1"]["findings"][0]["kind"] == "mirror", by["e1"]["findings"][0]
            assert by["e1"]["findings"][0]["title"] == "Backup mirror behind", by["e1"]["findings"][0]
            assert by["e1"]["lateness_s"] == 0.0, by["e1"]["lateness_s"]
            assert by["e1"]["duration_ms"] == 800, by["e1"]["duration_ms"]
            assert by["e2"]["lateness_s"] == 60.0, by["e2"]["lateness_s"]
            assert by["e2"]["body_source"] == "none" and by["e2"]["silent"] is True, by["e2"]
            assert by["e3"]["silent"] is True and by["e3"]["body_source"] == "none", by["e3"]
            assert by["e4"]["status"] == "failed" and by["e4"]["delivery"] == "delivered", by["e4"]
            assert by["e4"]["status_label"] == "failed", by["e4"]
            assert by["e4"]["body_source"] == "error" and by["e4"]["findings"] == [], by["e4"]
            assert by["e4"]["silent"] is False, "a failed + delivered run is not silent"
            assert by["e5"]["status"] == "running" and by["e5"]["delivery"] == "none", by["e5"]
            assert by["e5"]["status_label"] == "running", by["e5"]
            assert all(r["id"] != "e6" for r in data["runs"]), "a run outside the window must not be listed"
            assert health_jobs(window="all")["totals"]["runs"] == 6, "`all` must read the whole history"
            full = health_job_run(id="e1")
            assert full["ok"] and "bulgu" in full["body"] and "**Job ID:**" not in full["body"], full
            trend = data["trend"]
            assert trend["bucket_hours"] >= 1 and len(trend["buckets"]) <= 24, trend
            assert sum(b["runs"] for b in trend["buckets"]) == 5, trend["buckets"]
            assert trend["prev"] == {"runs": 0, "failed": 0, "silent": 0, "delivered": 0}, trend["prev"]
            assert trend["prev_basis"] == "24h", trend["prev_basis"]
            per_job_runs = sum(b["runs"] for cells in trend["per_job"].values() for b in cells)
            assert per_job_runs == sum(b["runs"] for b in trend["buckets"]), trend["per_job"]
            assert set(trend["per_job"]) <= {"live1", "gone1"}, sorted(trend["per_job"])
            assert health_jobs(window="all")["trend"]["prev"] is None, "`all` has no previous window"
            assert health_job_run(id="yok-böyle-kayıt").status_code == 404
            assert health_jobs(window="24h", limit=5)["truncated"] is False, \
                "every in-window run is listed, yet older rows past the cap mark the window as capped"
            capped = health_jobs(window="24h", limit=4)
            assert capped["truncated"] is True and len(capped["runs"]) == 4, \
                "an in-window run past the cap was dropped without the capped notice"
            far = datetime.timezone(datetime.timedelta(hours=-12))
            con = sqlite3.connect(cron / "executions.db")
            con.executemany(
                "insert into executions (id, job_id, status, delivery_outcome, claimed_at, source,"
                " process_id, pid) values (?,'live1','completed','delivered',?,'builtin','p',1)", [
                    ("e7", (now - datetime.timedelta(hours=40)).astimezone(far).isoformat(timespec="seconds")),
                    ("e8", (now - datetime.timedelta(hours=23)).astimezone(far).isoformat(timespec="seconds")),
                    ("e9", (datetime.datetime.now() - datetime.timedelta(hours=3)).replace(
                        microsecond=0).isoformat()),
                ])
            con.commit()
            con.close()
            mixed = health_jobs(window="24h")
            mixed_ids = {r["id"] for r in mixed["runs"]}
            assert {"e8", "e9"} <= mixed_ids and "e7" not in mixed_ids, sorted(mixed_ids)
            assert mixed["trend"]["prev"]["runs"] == 1, \
                f"a run stored with another UTC offset fell out of the previous window: {mixed['trend']['prev']}"
            assert sum(b["runs"] for b in mixed["trend"]["buckets"]) == 7, mixed["trend"]["buckets"]
            assert mixed["trend"].get("trend_truncated") is False, mixed["trend"]
            keep_max = MAX_RUNS
            MAX_RUNS = 3
            try:
                small = _trend(24, datetime.datetime.now().astimezone())
            finally:
                MAX_RUNS = keep_max
            assert small.get("trend_truncated") is True, \
                f"a trend read cut at the cap was reported as complete: prev {small['prev']}"
            assert health_jobs(window="all")["trend"].get("trend_truncated") is False
            whole = health_jobs(window="all")
            assert whole["trend"]["bucket_hours"] >= 1 and whole["trend"]["buckets"], \
                f"`all` drew no activity although runs exist: {whole['trend']}"
            assert sum(b["runs"] for b in whole["trend"]["buckets"]) == whole["totals"]["runs"], \
                (sum(b["runs"] for b in whole["trend"]["buckets"]), whole["totals"]["runs"])
            assert whole["trend"]["prev"] is None, "`all` still has no previous window"
            con = sqlite3.connect(cron / "executions.db")
            base = datetime.datetime.now().astimezone().replace(microsecond=0)

            def finished_run(rid, minutes_ago, seconds, status, delivery, error, body):
                claimed = base - datetime.timedelta(minutes=minutes_ago)
                finished = claimed + datetime.timedelta(seconds=seconds)
                con.execute(
                    "insert into executions (id, job_id, status, delivery_outcome, error, claimed_at,"
                    " started_at, finished_at, source, process_id, pid)"
                    " values (?,'live1',?,?,?,?,?,?,'builtin','p',1)",
                    (rid, status, delivery, error, claimed.isoformat(timespec="seconds"),
                     claimed.isoformat(timespec="seconds"), finished.isoformat(timespec="seconds")))
                if body is not None:
                    (cron / "output" / "live1" / f"{finished.strftime('%Y-%m-%d_%H-%M-%S')}.md").write_text(
                        "# Cron Job: Live One\r\n\r\n**Job ID:** live1\r\n"
                        f"**Run Time:** {finished.strftime('%Y-%m-%d %H:%M:%S')}\r\n"
                        "**Mode:** no_agent (script)\r\n" + body, encoding="utf-8")

            finished_run("f1", 30, 13, "completed", "delivered", None,
                         "\r\n---\r\n\r\n⚠ 1 bulgu\r\n- 3 commit 'onedrive' mirror'una gitmemiş — yedeği çalıştır\r\n")
            finished_run("f2", 50, 2, "completed", "suppressed", None, "**Status:** silent (empty output)\n")
            finished_run("f3", 70, 4, "failed", "delivered", "Script exited with code 2",
                         "**Status:** script failed\n\nboom output\n")
            finished_run("f6", 100 + 40 / 60, 10, "completed", "delivered", None,
                         "\r\n---\r\n\r\nneighbour output\r\n")
            finished_run("f5", 100, 1, "completed", "suppressed", None, None)
            con.commit()
            con.close()
            named = {r["id"]: r for r in health_jobs(window="24h")["runs"]}
            assert named["f1"]["body_source"] == "output" and named["f1"]["findings_count"] == 1, \
                f"an output file named at the finish time was not matched to its run: {named['f1']}"
            assert named["f2"]["silent"] is True and named["f2"]["body"] == "", \
                f"an empty-output file without a separator read its header as the body: {named['f2']}"
            assert named["f3"]["body"] == "boom output" and named["f3"]["body_source"] == "output", named["f3"]
            assert named["f5"]["body_source"] == "none" and "neighbour" not in named["f5"]["body"], \
                f"a run without its own output borrowed the previous run's file: {named['f5']}"
            assert named["f6"]["body"] == "neighbour output", named["f6"]
            single = health_job_run(id="f1")
            assert single["ok"] and "bulgu" in single["body"] and "**Job ID:**" not in single["body"], single
            jobs_doc = json.loads((cron / "jobs.json").read_text(encoding="utf-8"))
            jobs_doc["jobs"].append({"id": "agent1", "name": "Agent One", "enabled": True, "state": "scheduled",
                                     "schedule_display": "30 21 * * *", "last_status": "ok"})
            (cron / "jobs.json").write_text(json.dumps(jobs_doc), encoding="utf-8")
            (cron / "output" / "agent1").mkdir()
            agent_claimed = base - datetime.timedelta(minutes=20)
            agent_finished = agent_claimed + datetime.timedelta(seconds=90)
            con = sqlite3.connect(cron / "executions.db")
            con.execute(
                "insert into executions (id, job_id, status, delivery_outcome, claimed_at, started_at,"
                " finished_at, source, process_id, pid) values ('a1','agent1','completed','delivered',?,?,?,"
                "'builtin','p',1)", (agent_claimed.isoformat(timespec="seconds"),
                                     agent_claimed.isoformat(timespec="seconds"),
                                     agent_finished.isoformat(timespec="seconds")))
            con.commit()
            con.close()
            (cron / "output" / "agent1" / f"{agent_finished.strftime('%Y-%m-%d_%H-%M-%S')}.md").write_text(
                "# Cron Job: Agent One\n\n**Job ID:** agent1\n\n## Prompt\n\n- read `run.json` first\n"
                "- write each candidate\n\n## Response\n\n- **update** · a page\n", encoding="utf-8")
            agent_run = {r["id"]: r for r in health_jobs(window="24h")["runs"]}["a1"]
            assert agent_run["body_source"] == "output" and agent_run["findings_count"] == 0, \
                f"an agent job's prompt and reply bullets were counted as watchdog findings: {agent_run['findings']}"
            assert {r["id"]: r for r in health_jobs(window="24h")["runs"]}["f1"]["findings_count"] == 1
            (cron / "output" / "live2").mkdir()
            jobs_doc["jobs"].append({"id": "live2", "name": "Live Two", "no_agent": True, "script": "b.py",
                                     "enabled": True, "state": "scheduled", "schedule_display": "every 1m"})
            (cron / "jobs.json").write_text(json.dumps(jobs_doc), encoding="utf-8")
            con = sqlite3.connect(cron / "executions.db")
            mark = base - datetime.timedelta(minutes=10)

            def live2_run(rid, start_s, end_s, status, body):
                claimed = mark + datetime.timedelta(seconds=start_s)
                finished = None if end_s is None else mark + datetime.timedelta(seconds=end_s)
                con.execute(
                    "insert into executions (id, job_id, status, delivery_outcome, claimed_at, started_at,"
                    " finished_at, source, process_id, pid) values (?,'live2',?,'delivered',?,?,?,"
                    "'builtin','p',1)", (rid, status, claimed.isoformat(timespec="seconds"),
                                         claimed.isoformat(timespec="seconds"),
                                         finished.isoformat(timespec="seconds") if finished else None))
                if body is not None:
                    saved = mark + datetime.timedelta(seconds=end_s - 2 if end_s - start_s > 2 else end_s)
                    (cron / "output" / "live2" / f"{saved.strftime('%Y-%m-%d_%H-%M-%S')}.md").write_text(
                        "# Cron Job: Live Two\n\n**Job ID:** live2\n**Mode:** no_agent (script)\n" + body,
                        encoding="utf-8")

            live2_run("g1", 0, 60, "completed", "\n---\n\nA output\n")
            live2_run("g2", 62, 63, "completed", "\n---\n\nB output\n")
            live2_run("g3", 120, 125, "failed", "**Status:** script failed\n\n**Error:** disk full\nmore\n")
            live2_run("g4", 200, 206, "completed", "\n---\n\nD output (previous run)\n")
            live2_run("g5", 206, None, "running", None)
            con.commit()
            con.close()
            two = {r["id"]: r for r in health_jobs(window="24h")["runs"]}
            assert two["g1"]["body"] == "A output" and two["g2"]["body"] == "B output", \
                f"back-to-back runs swapped their output: {two['g1']['body']!r} / {two['g2']['body']!r}"
            assert two["g3"]["body"] == "**Error:** disk full\nmore", \
                f"real output that starts with a bold field was eaten as header: {two['g3']['body']!r}"
            assert two["g5"]["body_source"] == "none" and two["g5"]["body"] == "", \
                f"a running run borrowed the previous run's output: {two['g5']['body']!r}"
            assert {r["id"]: r for r in health_jobs(window="24h")["runs"]}["a1"]["body"] == "- **update** · a page", \
                "an agent job's body is its reply, not the prompt"
            (cron / "output" / "live3").mkdir()
            (cron / "output" / "agent3").mkdir()
            jobs_doc["jobs"].append({"id": "live3", "name": "Live Three", "no_agent": True, "script": "c.py",
                                     "enabled": True, "state": "scheduled", "schedule_display": "every 1m"})
            jobs_doc["jobs"].append({"id": "agent3", "name": "Agent Three", "enabled": True, "state": "scheduled",
                                     "schedule_display": "every 1h"})
            (cron / "jobs.json").write_text(json.dumps(jobs_doc), encoding="utf-8")
            con = sqlite3.connect(cron / "executions.db")
            mark3 = base - datetime.timedelta(minutes=8)

            def run3(job, rid, start_s, end_s, status, save_s, body):
                claimed = mark3 + datetime.timedelta(seconds=start_s)
                finished = mark3 + datetime.timedelta(seconds=end_s)
                con.execute(
                    "insert into executions (id, job_id, status, delivery_outcome, claimed_at, started_at,"
                    " finished_at, source, process_id, pid) values (?,?,?,'delivered',?,?,?,'builtin','p',1)",
                    (rid, job, status, claimed.isoformat(timespec="seconds"),
                     claimed.isoformat(timespec="seconds"), finished.isoformat(timespec="seconds")))
                saved = mark3 + datetime.timedelta(seconds=save_s)
                (cron / "output" / job / f"{saved.strftime('%Y-%m-%d_%H-%M-%S')}.md").write_text(
                    f"# Cron Job: {job}\n\n**Job ID:** {job}\n**Run Time:** x\n**Schedule:** y\n\n" + body,
                    encoding="utf-8")

            run3("live3", "h1", 0, 54, "completed", 50, "---\n\nA delivered late\n")
            run3("live3", "h2", 55, 57, "completed", 56, "---\n\nB output\n")
            run3("live3", "h3", 100, 102, "failed", 101, "**Status:** script failed\n\nfirst part\n---\nsecond part\n")
            framed_prompt = "do the work\n## Response\n\nnot the reply"
            framed_reply = "REAL REPLY\n---\nmore"
            run3("agent3", "h4", 200, 260, "completed", 258,
                 f"**Prompt Characters:** {len(framed_prompt)}\n## Prompt\n\n{framed_prompt}\n\n"
                 f"**Response Characters:** {len(framed_reply)}\n## Response\n\n{framed_reply}\n")
            run3("agent3", "h5", 300, 330, "failed", 329,
                 "## Prompt\n\nthe long prompt\n\n## Error\n\n```\nTraceback: boom\n```\n")
            con.commit()
            con.close()
            three = {r["id"]: r for r in health_jobs(window="24h")["runs"]}
            assert three["h1"]["body"] == "A delivered late" and three["h2"]["body"] == "B output", \
                f"a run whose delivery outlasted the gap took the next run's output: {three['h1']['body']!r}"
            assert three["h3"]["body"] == "first part\n---\nsecond part", \
                f"a failed script's output was cut at its own separator line: {three['h3']['body']!r}"
            assert three["h4"]["body"] == framed_reply, \
                f"the reply was not read through Hermes' character frame: {three['h4']['body']!r}"
            assert "Traceback: boom" in three["h5"]["body"] and "long prompt" not in three["h5"]["body"], \
                f"a failed agent run shows its prompt instead of its error: {three['h5']['body']!r}"
            (cron / "jobs.json").write_text("{bozuk", encoding="utf-8")
            with _captured() as seen:
                assert _job_registry() == {}, "a broken jobs.json must read as an empty registry"
            assert any("jobs.json" in m for m in seen), f"a broken jobs.json was swallowed silently: {seen}"
            (cron / "executions.db").write_bytes(b"this is not a sqlite database" * 64)
            with _captured() as seen:
                broken = health_jobs(window="24h")
            assert getattr(broken, "status_code", 200) == 503, "a corrupt run store must not read as empty"
            payload = json.loads(broken.body)
            assert payload["ok"] is False and "run store" in payload["error"], payload
            assert any("executions.db" in m for m in seen), f"the store error was not logged: {seen}"
            with _captured() as seen:
                broken_run = health_job_run(id="e1")
            assert getattr(broken_run, "status_code", 200) == 503, "a corrupt run store read as 'run not found'"
            assert "run store" in json.loads(broken_run.body)["error"], broken_run.body
            assert seen, "the run lookup error was not logged"
            with _captured() as seen:
                try:
                    _trend_rows(None)
                    raise AssertionError("_trend_rows returned rows from a corrupt store")
                except _StoreError:
                    pass
            assert seen, "the trend read error was not logged"
            keep_cron, keep_backups = CRON_DIR, _backups_dir
            store_home = tempfile.TemporaryDirectory(prefix="wiki-automation-health-store-")
            store = Path(store_home.name) / "executions.db"
            con = sqlite3.connect(str(store))
            con.execute("create table executions (id text primary key, job_id text, status text,"
                        " delivery_outcome text, error text, claimed_at text, started_at text,"
                        " finished_at text, scheduled_instant text, pid integer, source text)")
            for rid in ("keep-1", "gone-1", "gone-2"):
                con.execute("insert into executions (id, job_id, status) values (?,?,?)",
                            (rid, "23b87c7253d4", "completed"))
            con.commit()
            con.close()
            try:
                CRON_DIR = Path(store_home.name)
                _backups_dir = lambda: Path(store_home.name) / "backups"
                (Path(store_home.name) / "backups").mkdir(exist_ok=True)
                out_md = Path(store_home.name) / "output" / "23b87c7253d4" / "2026-09-15_10-22-56.md"
                out_md.parent.mkdir(parents=True)
                out_md.write_text("---\n- bulgu\n", encoding="utf-8")
                cleared = _archive_and_clear(["gone-1", "gone-2", "never-1"])
                assert cleared["ok"], cleared
                assert cleared["cleared"] == 2 and cleared["missing"] == 1, cleared
                assert out_md.read_text(encoding="utf-8") == "---\n- bulgu\n", \
                    "archive-clear touched a run output file, which the archive does not hold"
                archived = json.loads(Path(cleared["archive"]).read_text(encoding="utf-8"))
                assert [r["id"] for r in archived["rows"]] == ["gone-1", "gone-2"], archived["rows"]
                assert archived["found"] == 2 and archived["requested"] == 3, archived
                con = sqlite3.connect(str(store))
                left = [r[0] for r in con.execute("select id from executions order by id")]
                con.close()
                assert left == ["keep-1"], f"a record that was not selected was removed: {left}"
                empty = _archive_and_clear([])
                assert not empty["ok"] and empty["cleared"] == 0, empty
                again = _archive_and_clear(["gone-1"])
                assert again["ok"] and again["cleared"] == 0 and again["missing"] == 1, again
                con = sqlite3.connect(str(store))
                con.executemany("insert into executions (id, job_id, status) values (?,?,?)", [
                    ("same-1", "j", "completed"), ("same-2", "j", "completed"),
                    ("busy-1", "j", "running"), ("busy-2", "j", "claimed")])
                con.commit()
                con.close()
                real_dt = datetime.datetime

                class _Frozen(real_dt):
                    @classmethod
                    def now(cls, tz=None):
                        return real_dt(2026, 9, 18, 20, 32, 7, 123456, tzinfo=tz)

                datetime.datetime = _Frozen
                try:
                    first = _archive_and_clear(["same-1"])
                    second = _archive_and_clear(["same-2"])
                finally:
                    datetime.datetime = real_dt
                assert first["ok"] and second["ok"], (first, second)
                assert first["archive"] != second["archive"], "two clears in one instant share one archive"
                kept = json.loads(Path(first["archive"]).read_text(encoding="utf-8"))
                assert [r["id"] for r in kept["rows"]] == ["same-1"], \
                    f"the second clear overwrote the first archive: {kept['rows']}"
                busy = _archive_and_clear(["busy-1", "busy-2", "keep-1"])
                assert busy["ok"] and busy["cleared"] == 1 and busy["active"] == 2, busy
                con = sqlite3.connect(str(store))
                left = sorted(r[0] for r in con.execute("select id from executions"))
                con.close()
                assert left == ["busy-1", "busy-2"], f"a running or claimed run was removed: {left}"
                flood = health_runs_archive_clear({"keys": [f"k{i}" for i in range(MAX_RUNS + 1)]})
                assert not flood["ok"] and "at most" in flood["error"], flood
                _backups_dir = keep_backups
                bad_home = Path(store_home.name) / "badhome"
                bad_home.mkdir()
                (bad_home / "backups").write_text("not a folder", encoding="utf-8")
                keep_home = os.environ.get("HERMES_HOME")
                os.environ["HERMES_HOME"] = str(bad_home)
                try:
                    con = sqlite3.connect(str(store))
                    con.execute("insert into executions (id, job_id, status) values ('done-3','j','completed')")
                    con.commit()
                    con.close()
                    blocked = _archive_and_clear(["done-3"])
                    (AUDIT_DIR_BAD := Path(store_home.name) / "audit").mkdir()
                    (AUDIT_DIR_BAD / "alerts.log").write_text("[x]\n- y\n", encoding="utf-8")
                    os.environ["LLMWIKI_AUDIT_DIR"] = str(AUDIT_DIR_BAD)
                    blocked_log = health_watchdog_clear({"confirm": True})
                finally:
                    os.environ.pop("LLMWIKI_AUDIT_DIR", None)
                    if keep_home is None:
                        os.environ.pop("HERMES_HOME", None)
                    else:
                        os.environ["HERMES_HOME"] = keep_home
                assert blocked["ok"] is False and "archive" in blocked["error"], blocked
                assert blocked_log["ok"] is False and blocked_log["removed"] == 0, blocked_log
                assert (AUDIT_DIR_BAD / "alerts.log").read_text(encoding="utf-8") == "[x]\n- y\n", \
                    "alerts.log was touched though its archive folder could not be made"
                con = sqlite3.connect(str(store))
                assert con.execute("select count(*) from executions where id='done-3'").fetchone()[0] == 1, \
                    "a record was removed though its archive could not be written"
                con.close()
            finally:
                CRON_DIR, _backups_dir = keep_cron, keep_backups
                store_home.cleanup()
        finally:
            CRON_DIR = keep_cron

    kinds = [
        ("11 sayfa app-graph'ta izole (derece ≤1): a (deg 1) — bu sayfalara link ekle", "isolated"),
        ("11 app-graph isolated page(s) — add a link", "isolated"),
        ("var olmayan sayfalara giden linkler: {'abap_dev': 1} — hedef sayfayı oluştur", "unresolvable"),
        ("3 commit 'onedrive' mirror'una gitmemiş — yedek eksik", "mirror"),
        ("2 commit(s) ahead of 'onedrive'", "mirror"),
        ("app'in AKTİF proje kimliği abc (beklenen def) — App'te projeyi aç", "identity"),
        ("PROJE KİMLİĞİ DEĞİŞMİŞ: abc (beklenen def)", "identity"),
        ("ajan kurulumları farklı: a; b — kopyaları hizala", "drift"),
        ("index'te hiç görünmeyen sayfa (2): [a, b] — App'te yeniden tarat", "not_indexed"),
        ("sayfa sayısı düştü: 204 → 200 (baseline: state.json)", "pages_down"),
        ("check_links ÇÖKTÜ: KeyError — bu denetleyicinin hatası", "crash"),
        ("kanıt deposu (2 sorun): ['a.md: x'] — ayrıntı ve düzeltme: python e/evidence_capture.py --verify",
         "evidence_store"),
        ("sürüm değişti, 3 kanıt artık kurulu sürümle uyuşmuyor: ['a', 'b'] — liste: python e --recheck",
         "evidence_stale"),
        ("purpose.md YOK — dosya silinmiş. Geri al: git -C w checkout -- purpose.md", "control_missing"),
        ("schema.md git'teki sürümden farklı (disk 2410B / commit 2078B) — app yeniden yazmış olabilir. "
         "Farkı gör: git -C w diff -- schema.md", "control_changed"),
        ('purpose.md BOŞ ŞABLON boyutunda (324B) — "Create Project" akışı projenin üzerine yazmış olabilir; '
         "kimliği (.llm-wiki/project.json) ve git geçmişini kontrol et", "control_template"),
        (".llm-wiki/project.json YOK — app yeni bir proje kimliği üretecek (proje yeniden başlar). Geri al: "
         "git -C w checkout -- .llm-wiki/project.json", "project_file_missing"),
        (".llm-wiki/project.json okunamıyor (Expecting value: line 1 column 1 (char 0)) — dosya bozuk; git'ten "
         "geri al", "project_file_unreadable"),
        ("APP BU KLASÖRÜ YENİDEN KAYDETTİ: kimlik 7f0a (beklenen 9c1b) ve app bu kimliği aktif proje olarak "
         "gösteriyor — Create Project akışı çalışmış olabilir", "project_reregistered"),
        ("index'te kayıtlı ama dosyası yok (2): ['concepts/x'] — app index'i dosya adından üretir; sayfa adı "
         "değişmiş olabilir", "index_stale"),
        ("bölünmemiş ingest çıktısı (4 sayfa): ['sources/a.md'] — gövdedeki '---FILE:' bloklarının sayfaları "
         "hiç yazılmadı", "unsplit_ingest"),
        ('Uygulamada "Enable MCP access" KAPALI — MCP araçları "MCP access is disabled" döndürür', "mcp_off"),
        ("12 wiki değişikliği 30 saattir commit edilmedi — otomatik commit kaydetmiyor. Son otomatik commit "
         "çıktısı: nothing to commit", "commit_backlog"),
        ("drift_check ÇÖKTÜ (çıkış 1): ModuleNotFoundError: tomllib — denetleyicinin hatası; ajan kurulumları "
         "hakkında bilgi vermez", "drift_crash"),
        ("harvest 3 Codex oturumunu okumuyor (dosya türü: .jsonl.zst) — wiki_session_harvest.codex_session_files "
         "bu türü de listelemeli", "harvest_unread"),
        ("5 sıkıştırılmış Codex oturumu var ama bu Python'da zstd çözücü yok (3.11.9; 3.14+ gerekir) — harvest "
         "bu oturumlarda durur", "harvest_zstd"),
        ("veri klasöründe kurulu sürümden farklı 2 motor betiği: ['watchdog.py'] — eski kopya onay kapılarını "
         "atlayabilir", "engine_copies"),
        ("Bilinmeyen bir bulgu satırı", "other"),
    ]
    for raw, want in kinds:
        got = _watchdog_finding(raw)
        assert got["kind"] == want, (raw, got["kind"], want)
        assert got["retired"] is (want == "not_indexed"), (raw, got["retired"])
    old_line = _watchdog_finding("index'te hiç görünmeyen sayfa (2): [a, b] — App'te yeniden tarat")
    assert old_line["title"].endswith("(retired check)") and old_line["tone"] == "neutral", old_line
    assert old_line["by_watchdog"] is False and "no longer runs" in old_line["what"], old_line
    assert _watchdog_finding("11 sayfa app-graph'ta izole (derece ≤1): x")["n"] == 11
    assert _watchdog_finding("var olmayan sayfalara giden linkler: {'a': 1}")["n"] is None
    assert _watchdog_finding("Bilinmeyen bulgu")["n"] is None

    data_cases = [
        ("3 commit 'onedrive' mirror'una gitmemiş — yedeği çalıştır", {"n": "3", "remote": "onedrive"}),
        ("2 commit(s) ahead of 'onedrive'", {"n": "2", "remote": "onedrive"}),
        ("sayfa sayısı düştü: 204 → 200 (baseline: state.json)", {"before": "204", "after": "200"}),
        ("app'in AKTİF proje kimliği abc123 (beklenen def456) — App'te projeyi aç",
         {"id": "abc123", "expected": "def456"}),
        ("PROJE KİMLİĞİ DEĞİŞMİŞ: 7f0a (beklenen 9c1b)", {"id": "7f0a", "expected": "9c1b"}),
        ("11 sayfa app-graph'ta izole (derece ≤1): a (deg 1)", {"n": "11"}),
        ("index'te hiç görünmeyen sayfa (2): ['a', 'b']", {"n": "2"}),
        ("path-form wikilinks (3): {'a/b': 1}", {"n": "3"}),
        ("kanıt deposu (2 sorun): ['a.md: x'] — ayrıntı ve düzeltme: python e --verify", {"n": "2"}),
        ("sürüm değişti, 3 kanıt artık kurulu sürümle uyuşmuyor: ['a'] — liste: python e --recheck", {"n": "3"}),
        ("check_links ÇÖKTÜ: KeyError('/wiki/x') — bu denetleyicinin hatası",
         {"fn": "check_links", "error": "KeyError('/wiki/x')"}),
        ("purpose.md YOK — dosya silinmiş", {"name": "purpose.md"}),
        ("APP BU KLASÖRÜ YENİDEN KAYDETTİ: kimlik 7f0a (beklenen 9c1b) ve app bu kimliği aktif proje olarak "
         "gösteriyor — doğrula", {"id": "7f0a", "expected": "9c1b"}),
        ("index'te kayıtlı ama dosyası yok (2): ['a'] — sayfa adı değişmiş olabilir", {"n": "2"}),
        ("bölünmemiş ingest çıktısı (4 sayfa): ['a'] — yeniden ingest et", {"n": "4"}),
        ("12 wiki değişikliği 30 saattir commit edilmedi — kaydetmiyor", {"n": "12", "hours": "30"}),
        ("drift_check ÇÖKTÜ (çıkış 1): err — denetleyicinin hatası", {}),
        ("harvest 3 Codex oturumunu okumuyor (dosya türü: .zst) — listelemeli", {"n": "3"}),
        ("5 sıkıştırılmış Codex oturumu var ama bu Python'da zstd çözücü yok (3.11) — durur", {"n": "5"}),
        ("veri klasöründe kurulu sürümden farklı 2 motor betiği: ['a'] — çalıştır", {"n": "2"}),
    ]
    for line, want in data_cases:
        got = _watchdog_finding(line)
        assert got["raw"] == line, (line, got["raw"])
        assert got["data"] == want, (line, got["data"])
    unmapped = _watchdog_finding("bilinmeyen bir denetim satırı (2): ['a']")
    assert unmapped["kind"] == "other" and unmapped["data"] == {}, unmapped
    assert unmapped["raw"] == unmapped["detail"] == "bilinmeyen bir denetim satırı (2): ['a']", unmapped
    assert _watchdog_finding("  3 commit 'x' mirror'una gitmemiş  ")["raw"] == "3 commit 'x' mirror'una gitmemiş"
    assert _watchdog_finding("sayfa sayısı düştü: 204 → 200")["what"] == \
        "Page count dropped 204 → 200; a page may have been deleted."

    assert _sentence("app'te projeyi açıp yeniden tarat") == "App'te projeyi açıp yeniden tarat.", _sentence("app'te x")
    assert _sentence("içerik güncellenmedi") == "İçerik güncellenmedi.", _sentence("içerik güncellenmedi")
    assert _sentence("— .llm-wiki/project.json'ı kontrol et") == ".llm-wiki/project.json'ı kontrol et", _sentence("yol")
    assert _sentence("Çalıştır: git -C /w push mirror") == "Çalıştır: git -C /w push mirror", _sentence("komut")
    assert _sentence("  zaten   noktalı.  ") == "Zaten noktalı.", _sentence("nokta")
    assert _jb_label("status", "failed") == "failed", _jb_label("status", "failed")
    assert _jb_label("delivery", "suppressed") == "silent (no output)", _jb_label("delivery", "suppressed")
    assert _jb_label("status", "yok") == "yok", "an unknown label must come back as itself"
    print("health selftest OK: parsing (dates/limit/broken state) + classification (TR+EN "
          "patterns, weight) + the raw checker line kept verbatim beside its extracted data for "
          "every kind (the English mapping lives in the panel) + ONE English message table behind _tx "
          "(no language parameter) + "
          "sentence normaliser + clear + job runs (union registry, deleted job, timezone "
          "normalisation, two axes, missing body, window)")
    return 0

def _health_selftest() -> int:
    import tempfile

    keep_home = os.environ.get("HERMES_HOME")
    keep_audit = os.environ.pop("LLMWIKI_AUDIT_DIR", None)
    with tempfile.TemporaryDirectory(prefix="wiki-automation-health-home-") as home:
        os.environ["HERMES_HOME"] = home
        try:
            return _health_selftest_body()
        finally:
            if keep_home is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = keep_home
            if keep_audit is not None:
                os.environ["LLMWIKI_AUDIT_DIR"] = keep_audit



def _selftest_validate_blocked() -> dict:
    path = str(_audit_dir() / "wikiconfig.py")
    if Path(path).exists():
        return {"ok": False, "reason": "selftest: unexpected file"}
    return _run_json([sys.executable, path, "validate", "__missing__"],
                     default={"ok": False, "reason": _tx("auto_unreadable")})


def _selftest() -> int:
    import tempfile

    global AUDIT_DIR
    problems = []
    tmp = Path(tempfile.mkdtemp(prefix="wiki-auto-selftest-"))
    try:
        fake_audit = tmp / "audit"
        fake_audit.mkdir()
        keep, AUDIT_DIR = AUDIT_DIR, fake_audit
        os.environ["LLMWIKI_AUDIT_DIR"] = str(fake_audit)
        try:
            if harvest_status().get("ok") is not False:
                problems.append("harvest status accepted a missing engine")
            harvest_script = fake_audit / "wiki_session_harvest.py"
            status_output = ("hermes      on  found cursor=2026-10-05T21:00:00+03:00\n"
                             "codex       off NOT FOUND cursor=none (first run looks back 3 days)\n")
            def status_engine(last_run):
                return ("import sys\nassert sys.dont_write_bytecode is True\n"
                        f"if sys.argv[1:] == ['--last-run']:\n{last_run}\n"
                        "else:\n    assert sys.argv[1:] == ['--status']\n"
                        f"    print({status_output!r}, end='')\n")
            old_engine = ("    sys.stderr.write('usage: wiki_session_harvest.py\\nerror: unrecognized arguments: "
                          "--last-run\\n')\n    sys.exit(2)")
            status_script = status_engine(old_engine)
            harvest_script.write_text(status_script, encoding="utf-8")
            status = harvest_status()
            if status.get("last_run_supported") is not False or status.get("last_run") is not None:
                problems.append(f"harvest status did not report an engine without --last-run: {status}")
            if status.get("ok") is not True or status.get("agents") != [
                {"id": "hermes", "enabled": True, "found": True,
                 "cursor": "2026-10-05T21:00:00+03:00"},
                {"id": "codex", "enabled": False, "found": False,
                 "cursor": "none (first run looks back 3 days)"}
            ]:
                problems.append(f"harvest status did not preserve engine adapter state: {status}")
            if harvest_script.read_text(encoding="utf-8") != status_script \
                    or set(fake_audit.iterdir()) != {harvest_script}:
                problems.append("harvest status wrote files")
            row = {"ok": True, "run": "20261018-200224-bf54f97515cf", "execution_id": "e1", "job_id": "j1",
                   "created": "2026-10-18T20:02:24+03:00", "committed": False, "status": None,
                   "agents": {"hermes": "114 conversation(s)", "codex": "not found (fixture)"}}
            cases = [("    print('{\"ok\": true, \"run\": null}')", True, None),
                     (f"    print({json.dumps(row)!r})", True, {**{key: row[key] for key in (
                         "run", "execution_id", "created", "committed", "status", "agents")},
                         "stop_reason": None, "cost_usd": None}),
                     (f"    print({json.dumps({**row, 'stop_reason': {'code': 'unread_input', 'detail': 'one input'}, 'usage': {'cost_usd': 0.5}})!r})",
                      True, {**{key: row[key] for key in ("run", "execution_id", "created", "committed", "status", "agents")},
                             "stop_reason": {"code": "unread_input", "detail": "one input"}, "cost_usd": 0.5}),
                     ("    print('{\"ok\": false, \"error\": \"Run r2 has an unreadable run.json\"}')\n    sys.exit(1)",
                      False, "Run r2 has an unreadable run.json"),
                     ("    print('{\"ok\": true}')", False, "unsupported"),
                     (f"    print({json.dumps({**row, 'committed': 'no'})!r})", False, "unsupported"),
                     (f"    print({json.dumps({**row, 'agents': {'hermes': 3}})!r})", False, "unsupported")]
            for body, ok, expected in cases:
                harvest_script.write_text(status_engine(body), encoding="utf-8")
                seen = harvest_status()
                if ok and (seen.get("ok") is not True or seen.get("last_run_supported") is not True
                           or seen.get("last_run") != expected or len(seen.get("agents") or []) != 2):
                    problems.append(f"harvest status lost the last run {body!r}: {seen}")
                if not ok and (seen.get("ok") is not False or expected not in str(seen.get("error"))):
                    problems.append(f"harvest status accepted a broken last run {body!r}: {seen}")
            harvest_script.write_text(status_script, encoding="utf-8")
            for malformed in ("", "engine changed its protocol", status_output + "unexpected\n",
                              status_output + status_output):
                harvest_script.write_text(f"print({malformed!r})\n", encoding="utf-8")
                if harvest_status().get("ok") is not False:
                    problems.append(f"harvest status accepted malformed output: {malformed!r}")
            harvest_script.write_text("import sys\nsys.stderr.write('status exploded')\nsys.exit(3)\n",
                                      encoding="utf-8")
            failure = harvest_status()
            if failure.get("ok") is not False or "status exploded" not in str(failure) \
                    or "3" not in str(failure):
                problems.append(f"harvest status lost its process failure: {failure}")
            from unittest.mock import patch as mock_patch
            with mock_patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("status", 15)):
                if harvest_status().get("ok") is not False:
                    problems.append("harvest status accepted a timed-out engine")
        finally:
            os.environ.pop("LLMWIKI_AUDIT_DIR", None)
        probe = _run_json([sys.executable, "-c", "print('{}')"], default={"x": 1})
        if probe != {}:
            problems.append("_run_json did not fall back to the default on broken output")
        res = json.loads(json.dumps(_selftest_validate_blocked()))
        if res.get("ok") is not False:
            problems.append("validation answered ok without a resolver (silent wrong answer)")
        os.environ["LLMWIKI_AUDIT_DIR"] = str(fake_audit)
        if _audit_dir() != fake_audit:
            problems.append("LLMWIKI_AUDIT_DIR was ignored")
        del os.environ["LLMWIKI_AUDIT_DIR"]
        AUDIT_DIR = keep

        import inspect
        for route in router.routes:
            if inspect.iscoroutinefunction(getattr(route, "endpoint", None)):
                problems.append(f"the route {route.path} is async: its subprocess blocks the server")
        failed = _run_json_ex([sys.executable, "-c",
                               "import sys; sys.stderr.write('checker exploded'); sys.exit(3)"])
        if failed[0] is not None or "checker exploded" not in failed[1] or "3" not in failed[1]:
            problems.append(f"a failed call lost its stderr or exit code: {failed}")
        broken = tmp / "broken"
        broken.mkdir()
        (broken / "wikiconfig.py").write_text(
            "import sys\nsys.stderr.write('checker exploded')\nsys.exit(3)\n", encoding="utf-8")
        os.environ["LLMWIKI_AUDIT_DIR"] = str(broken)
        seen = automation_validate({"path": str(tmp)})
        if "checker exploded" not in str(seen):
            problems.append(f"a failed validate reads as merely unreadable: {seen}")
        if "checker exploded" not in str(automation().get("error")):
            problems.append("a failed /automation read dropped the checker's stderr")
        retired = automation()
        if "run_watchdog.cmd" in retired.get("scripts", {}) or "scheduler_registered" in retired \
                or "scheduler_task" in retired:
            problems.append(f"the retired Task Scheduler task is still reported: {sorted(retired)}")
        if "checker exploded" not in str(automation_scan_root({"path": str(tmp)})):
            problems.append("a failed scan-root write dropped the checker's stderr")
        if "checker exploded" not in str(automation_settings({"project_root": str(tmp)})):
            problems.append("a failed pre-save validation dropped the checker's stderr")
        for bad_root in ("relative/dir", str(broken / "wikiconfig.py")):
            refused = automation_candidates(root=bad_root)
            if refused.get("ok") is not False or "checker exploded" in str(refused):
                problems.append(f"a candidate scan accepted a root that is not a folder: {bad_root}")
        if automation_scan_root({"path": "relative/dir"}).get("ok") is not False:
            problems.append("a relative scan root was accepted")
        try:
            import hermes_constants
        except ImportError:
            hermes_constants = None
        if hermes_constants is not None:
            token = hermes_constants.set_hermes_home_override(tmp / "profile-x")
            try:
                if _hermes_home() != tmp / "profile-x":
                    problems.append(f"the backend ignores the active profile's home: {_hermes_home()}")
            finally:
                hermes_constants.reset_hermes_home_override(token)
        keep_view = globals()["_jobs_view"]

        def _exploding_view(*_args, **_kwargs):
            raise RuntimeError("store exploded")

        globals()["_jobs_view"] = _exploding_view
        try:
            broken_view = jobs_view_route()
        finally:
            globals()["_jobs_view"] = keep_view
        if broken_view.get("ok") is not False or broken_view.get("roles") != [] \
                or "store exploded" not in str(broken_view) \
                or "could not be read" not in str(broken_view):
            problems.append(f"a failed /jobs read does not say it could not read the jobs: {broken_view}")
        spy = tmp / "spy"
        spy.mkdir()
        (spy / "wikiconfig.py").write_text(
            "import json, sys\n"
            "if sys.argv[1] == 'set':\n"
            "    open(sys.argv[0] + '.log', 'a', encoding='utf-8').write(' '.join(sys.argv[2:]) + '\\n')\n"
            "    print(json.dumps({'ok': True, 'project_root': sys.argv[2]}))\n"
            "elif sys.argv[1] == 'validate':\n"
            "    print(json.dumps({'ok': True, 'id': 'pid-1'}))\n"
            "else:\n"
            "    print('{}')\n", encoding="utf-8")
        os.environ["LLMWIKI_AUDIT_DIR"] = str(spy)
        automation_settings({"project_root": str(tmp)})
        log_file = spy / "wikiconfig.py.log"
        writes = log_file.read_text(encoding="utf-8").splitlines() if log_file.exists() else []
        if len(writes) != 1 or "project_id=pid-1" not in writes[0] or "project_root=" not in writes[0]:
            problems.append(f"saving a root is not one write carrying the root and its id: {writes}")
        del os.environ["LLMWIKI_AUDIT_DIR"]

        class _Kept(logging.Handler):
            def __init__(self):
                super().__init__()
                self.lines = []

            def emit(self, record):
                self.lines.append(record.getMessage())
        kept = _Kept()
        _log.addHandler(kept)

        ms = _ms("2026-09-17T16:00:27+03:00", "2026-09-17T13:00:28+00:00")
        if ms != 1000:
            problems.append(f"timezone normalization broken: {ms} (expected 1000)")
        if _label("status", "completed") == _label("delivery", "suppressed"):
            problems.append("status and delivery labels collapsed into one axis")
        if _label("delivery", "unknown-value") != "unknown-value":
            problems.append("an unknown delivery value was invented instead of passed through")

        marked = _reason_fields({"ok": False, "reason": "klasör yok"})
        if marked != {"reason": "klasör yok", "reason_source": "checker"}:
            problems.append(f"a checker reason lost its raw text or its provenance: {marked}")
        if _reason_fields({"ok": True}) != {}:
            problems.append("a payload without a reason was given a provenance")

        jobs = _jobs_from_settings({"jobs": {"autocommit": "aaa", "ingest_watch": "bbb"}})
        if jobs != {"autocommit": "aaa", "ingest_watch": "bbb"}:
            problems.append(f"job ids were not read from the settings: {jobs}")
        if _jobs_from_settings({"jobs": None}) != {}:
            problems.append("missing job ids did not yield an empty mapping")

        home = tmp / "hermes"
        (home / "cron").mkdir(parents=True)
        (home / "cron" / "jobs.json").write_text(json.dumps(
            [{"id": "aaa", "name": "Wiki Auto-Commit"}]), encoding="utf-8")
        con = sqlite3.connect(str(home / "cron" / "executions.db"))
        con.execute("create table executions (id text, job_id text, status text, "
                    "delivery_outcome text, claimed_at text, started_at text, finished_at text, "
                    "scheduled_instant text, error text)")
        con.execute("insert into executions values ('e1','aaa','failed','delivered',"
                    "'2026-09-17T17:00:27+03:00','2026-09-17T17:00:27+03:00',"
                    "'2026-09-17T17:00:28+03:00','2026-09-17T14:00:00+00:00','boom')")
        con.execute("insert into executions values ('e2','bbb','completed','suppressed',"
                    "'2026-09-17T16:30:26+03:00',null,'2026-09-17T16:30:27+03:00',null,null)")
        con.commit()
        con.close()
        keep_home = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = str(home)
        live = _live_jobs()
        if live.get("aaa") != "Wiki Auto-Commit":
            problems.append("the live job definition could not be read")
        got = _recent_runs(["aaa", "bbb"], 5)
        os.environ["LLMWIKI_AUDIT_DIR"] = str(spy)
        credited = [j.get("job_id") for j in runs(8).get("jobs", [])]
        del os.environ["LLMWIKI_AUDIT_DIR"]
        if "aaa" in credited:
            problems.append("/runs credited a job the panel did not create, by its name")
        cfg_only = tmp / "cfg-only"
        cfg_only.mkdir()
        (cfg_only / "wikiconfig.py").write_text(
            "import json\nprint(json.dumps({'jobs': {'autocommit': 'aaa'}}))\n", encoding="utf-8")
        os.environ["LLMWIKI_AUDIT_DIR"] = str(cfg_only)
        credited = [j.get("job_id") for j in runs(8).get("jobs", [])]
        del os.environ["LLMWIKI_AUDIT_DIR"]
        if "aaa" in credited:
            problems.append("/runs credited a job id only the wiki config maps, not one the panel recorded")
        keep_cols = globals()["_JOB_COLS"]
        globals()["_JOB_COLS"] = "no_such_column"
        kept.lines.clear()
        _recent_runs(["aaa"], 5)
        globals()["_JOB_COLS"] = keep_cols
        if not any("executions" in line for line in kept.lines):
            problems.append("a failed run-history read left no warning")
        first = (got.get("aaa") or [{}])[0]
        if first.get("status_label") != "Failed":
            problems.append(f"status label did not arrive: {first.get('status_label')}")
        if first.get("ms") != 1000:
            problems.append(f"run duration wrong: {first.get('ms')}")
        engine = tmp / "engine"
        engine.mkdir()
        engine_jobs = {"jobs": {
            role: {"name": name, "kind": "script", "launcher": f"launch_{role}.py", "impl": f"{role}.py",
                   "schedule_key": role, "default_schedule": "0 9 * * *", "description": f"{name} prompt"}
            for role, name in (("autocommit", "Wiki Auto-Commit"), ("ingest_watch", "Wiki Ingest Watch"),
                               ("watchdog", "Watch Dog"))}}
        engine_jobs["jobs"]["session_harvest"] = {
            "name": "Wiki Session Harvest", "kind": "agent", "launcher": "launch_harvest.py",
            "impl": "session_harvest.py", "prompt_file": "harvest_prompt.md", "schedule_key": "session_harvest",
            "default_schedule": "30 21 * * *", "description": "agent job"}
        (engine / "jobs.json").write_text(json.dumps(engine_jobs), encoding="utf-8")
        (engine / "settings.json").write_text(json.dumps({"deliver": "ntfy"}), encoding="utf-8")
        os.environ["LLMWIKI_AUDIT_DIR"] = str(engine)
        cat = _job_catalogue()
        if set(cat) != {"autocommit", "ingest_watch", "watchdog", "session_harvest"}:
            problems.append(f"the engine job definition is not the four roles: {sorted(cat)}")
        for role, meta in cat.items():
            for field in ("name", "launcher", "impl", "deliver", "kind"):
                if not meta.get(field):
                    problems.append(f"engine role {role!r} has no {field}")
            if meta.get("kind") == "script" and meta.get("prompt") != f"{meta.get('name')} prompt":
                problems.append(f"a script job's prompt is not the engine description: {role}")
        if cat.get("session_harvest", {}).get("kind") != "agent" or cat["session_harvest"].get("prompt"):
            problems.append("the agent job is not read as an agent job")
        if cat.get("autocommit", {}).get("deliver") != "ntfy":
            problems.append("deliver does not come from the engine settings")
        native = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s",
            str(Path(__file__).resolve().parents[1] / "tests"), "-p", "test_job_ownership.py", "-v"],
            capture_output=True, text=True, encoding="utf-8", timeout=180)
        if native.returncode:
            problems.append("Real disposable native ownership checks failed: " + native.stdout + native.stderr)
        else:
            print(native.stderr.strip())
        with _cron_jobs().use_cron_store(tmp / "preview-store"):
            before_preview = list((tmp / "preview-store").rglob("*"))
            daily = jobs_preview_route({"schedule": "30 21 * * *"})
            local = [datetime.datetime.fromisoformat(value) for value in daily.get("next_runs", [])]
            if not daily.get("ok") or len(local) != 3 or any((value.hour, value.minute) != (21, 30) for value in local):
                problems.append(f"A daily preview did not return three local 21:30 runs: {daily}")
            every = jobs_preview_route({"schedule": "*/15 * * * *"})
            gaps = [(_aware(b) - _aware(a)).total_seconds() for a, b in zip(
                every.get("next_runs", []), every.get("next_runs", [])[1:])]
            if not every.get("ok") or gaps != [900.0, 900.0]:
                problems.append(f"A 15-minute preview did not return 15-minute gaps: {every}")
            for invalid in ({"schedule": "not a cron expression"}, {"schedule": "  "}, {}):
                if jobs_preview_route(invalid).get("ok"):
                    problems.append("Invalid schedule preview was accepted")
            if list((tmp / "preview-store").rglob("*")) != before_preview:
                problems.append("A schedule preview wrote to the native store")
        _state_path().mkdir(parents=True, exist_ok=True)
        (_state_path() / "settings.json").write_text(json.dumps({"probe_setting": "kept"}), encoding="utf-8")
        panel_settings = _state_path() / "settings.json"
        before_refusal = panel_settings.read_bytes(), panel_settings.stat().st_mtime_ns
        for action in ("create", "remove", "pause", "resume", "schedule"):
            refused = jobs_act_route({"role": "autocommit", "action": action,
                                      "confirm": True, "schedule": "*/7 * * * *"})
            if refused.get("ok") is not False:
                problems.append(f"A job action without the page's reviewed record was not refused: {refused}")
        if (panel_settings.read_bytes(), panel_settings.stat().st_mtime_ns) != before_refusal:
            problems.append("Management refusal changed owner panel settings")
        if panel_settings.with_name("settings.json.tmp").exists():
            problems.append("Management refusal left a temporary settings file")
        del os.environ["LLMWIKI_AUDIT_DIR"]
        if (Path(__file__).resolve().parent / "job_catalogue.json").exists():
            problems.append("the plugin keeps its own job catalogue beside the engine definition")
        real_jobs = Path.home() / ".llmwiki-audit" / "jobs.json"
        if real_jobs.exists():
            os.environ["LLMWIKI_AUDIT_DIR"] = str(real_jobs.parent)
            live_cat = _job_catalogue()
            del os.environ["LLMWIKI_AUDIT_DIR"]
            if not {"autocommit", "ingest_watch", "watchdog", "session_harvest"} <= set(live_cat):
                problems.append(f"the engine's own jobs.json does not give the four roles: {sorted(live_cat)}")
        if not (first.get("error_preview") or "").startswith("boom"):
            problems.append("error preview did not arrive")
        if (got.get("bbb") or [{}])[0].get("delivery_label") != "Silent":
            problems.append("delivery label did not arrive")
        jobs_home = tmp / "jobs-home"
        (tmp / "no-engine").mkdir(exist_ok=True)
        (jobs_home / "cron").mkdir(parents=True)
        (jobs_home / "state" / "wiki-automation").mkdir(parents=True)
        (jobs_home / "state" / "wiki-automation" / "settings.json").write_text(
            json.dumps({"jobs": {"autocommit": "aaa"}}), encoding="utf-8")
        os.environ["HERMES_HOME"] = str(jobs_home)
        os.environ["LLMWIKI_AUDIT_DIR"] = str(tmp / "no-engine")
        if _live_jobs() != {}:
            problems.append("a missing jobs.json did not read as no jobs")
        missing_view = runs(8)
        if missing_view.get("ok") is not False or missing_view.get("jobs"):
            problems.append(f"Unverified recorded ID was assigned a run-history role: {missing_view}")
        (jobs_home / "cron" / "jobs.json").write_text("{not json", encoding="utf-8")
        kept.lines.clear()
        corrupt_live, corrupt_error = _live_jobs_ex()
        if corrupt_live is not None or "jobs.json" not in str(corrupt_error):
            problems.append(f"An unreadable native job store lost its read error: {corrupt_error}")
        if not any("jobs.json" in line for line in kept.lines):
            problems.append("an unreadable jobs.json left no warning")
        del os.environ["LLMWIKI_AUDIT_DIR"]
        if keep_home is None:
            del os.environ["HERMES_HOME"]
        else:
            os.environ["HERMES_HOME"] = keep_home

        cand_dir = tmp / "cand"
        cand_dir.mkdir()
        (cand_dir / CANDIDATES_SCRIPT).write_text(
            "import json, sys\n"
            "open(sys.argv[0] + '.log', 'a', encoding='utf-8').write(json.dumps(sys.argv[1:]) + '\\n')\n"
            "cmd = sys.argv[1]\n"
            "if cmd == 'list':\n"
            "    print(json.dumps([{'ref': 'r1/a-b', 'kind': 'new', 'target': 't.md', 'summary': 's'}]))\n"
            "elif cmd == 'show':\n"
            "    print(json.dumps({'ref': sys.argv[2], 'candidate': {'kind': 'new'}, 'diff': ['+x'],\n"
            "                      'format_problems': [], 'target_exists': False, 'evidence_folders': []}))\n"
            "elif cmd == 'fetch-evidence' and 'refuse' not in sys.argv[2]:\n"
            "    print(json.dumps({'ref': sys.argv[2], 'ok': False, 'pending': ['b-code'], 'results': [\n"
            "        {'id': 'a-code', 'ok': True, 'status': 'captured'},\n"
            "        {'id': 'b-code', 'ok': False, 'error': 'passage not found in any stored file'}]}))\n"
            "    sys.exit(1)\n"
            "elif 'refuse' in sys.argv[2]:\n"
            "    print('!! refused: format: no decisions')\n"
            "    sys.exit(1)\n"
            "else:\n"
            "    print('OK ' + ' '.join(sys.argv[1:]))\n", encoding="utf-8")
        cand_log = cand_dir / (CANDIDATES_SCRIPT + ".log")
        os.environ["LLMWIKI_AUDIT_DIR"] = str(cand_dir)
        listed = candidates_list()
        if not listed.get("ok") or [c.get("ref") for c in listed.get("candidates", [])] != ["r1/a-b"]:
            problems.append(f"the candidate list does not come from the engine script: {listed}")
        shown = candidates_show("r1/a-b")
        if not shown.get("ok") or shown.get("diff") != ["+x"]:
            problems.append(f"a candidate detail does not come from the engine script: {shown}")
        for bad in ("../x", "r1/a/b", "r1", "r1/a b", "-r/--help", "r1/a;b", ""):
            if candidates_show(bad).get("ok") or candidates_act({"ref": bad, "action": "reject",
                                                                  "reason": "x"}).get("ok"):
                problems.append(f"a malformed candidate ref reached the script: {bad!r}")
        cand_log.unlink(missing_ok=True)
        armed = candidates_act({"ref": "r1/a-b", "action": "approve"})
        calls = [json.loads(line) for line in cand_log.read_text(encoding="utf-8").splitlines()] \
            if cand_log.exists() else []
        if armed.get("ok") or not armed.get("needs_confirm") or "model usage" not in str(armed):
            problems.append(f"an approve without confirm was not held for confirmation: {armed}")
        if calls != [["approve", "r1/a-b", "--dry-run"]]:
            problems.append(f"an unconfirmed approve reached the engine as a real write: {calls}")
        cand_log.unlink(missing_ok=True)
        done = candidates_act({"ref": "r1/a-b", "action": "approve", "confirm": True})
        calls = [json.loads(line) for line in cand_log.read_text(encoding="utf-8").splitlines()] \
            if cand_log.exists() else []
        if done.get("ok") or calls or "Legacy confirmation" not in str(done):
            problems.append(f"legacy confirm flags reached an unbound engine publication: {done} {calls}")
        cand_log.unlink(missing_ok=True)
        if candidates_act({"ref": "r1/a-b", "action": "reject", "reason": "  "}).get("ok") or cand_log.exists():
            problems.append("a reject without a reason reached the engine")
        if candidates_act({"ref": "r1/a-b", "action": "reject", "reason": "No displayed review"}).get("ok") or cand_log.exists():
            problems.append("a rejection without its exact displayed digest reached the engine")
        gone = candidates_act({"ref": "r1/a-b", "action": "reject", "reason": "--dry-run duplicate", "review_digest": "a" * 64})
        calls = [json.loads(line) for line in cand_log.read_text(encoding="utf-8").splitlines()] \
            if cand_log.exists() else []
        if not gone.get("ok") or calls != [["reject", "r1/a-b", "--reason=--dry-run duplicate", "--expected-review-digest=" + "a" * 64]]:
            problems.append(f"a reject did not pass its reason as one argument: {gone} {calls}")
        refused = candidates_act({"ref": "r1/refuse", "action": "approve", "confirm": False})
        if refused.get("ok") or "no decisions" not in str(refused.get("output")):
            problems.append(f"an engine refusal lost the script's own text: {refused}")
        cand_log.unlink(missing_ok=True)
        if candidates_act({"ref": "r1/a-b", "action": "fetch_evidence"}).get("ok") or cand_log.exists():
            problems.append("an evidence fetch without the displayed review digest reached the engine")
        fetched = candidates_act({"ref": "r1/a-b", "action": "fetch_evidence", "review_digest": "b" * 64})
        calls = [json.loads(line) for line in cand_log.read_text(encoding="utf-8").splitlines()] \
            if cand_log.exists() else []
        if (calls != [["fetch-evidence", "r1/a-b", "--expected-review-digest=" + "b" * 64]] or fetched.get("ok") is not False
                or fetched.get("pending") != ["b-code"] or [x.get("ok") for x in fetched.get("results", [])] != [True, False]):
            problems.append(f"an evidence fetch did not report each request as the engine did: {fetched} {calls}")
        fetch_refused = candidates_act({"ref": "r1/refuse", "action": "fetch_evidence", "review_digest": "b" * 64})
        if fetch_refused.get("ok") or "no decisions" not in str(fetch_refused.get("output")):
            problems.append(f"an evidence fetch refusal lost the script's own text: {fetch_refused}")
        if candidates_act({"ref": "r1/a-b", "action": "delete"}).get("ok"):
            problems.append("an unknown candidate action was accepted")
        os.environ["LLMWIKI_AUDIT_DIR"] = str(tmp / "no-engine")
        missing_cand = candidates_list()
        if missing_cand.get("ok") is not False or "wiki_candidates.py" not in str(missing_cand.get("error")):
            problems.append(f"a missing candidate script reads as no candidates: {missing_cand}")
        (cand_dir / CANDIDATES_SCRIPT).write_text("import sys\nsys.stderr.write('harvest exploded')\n"
                                                  "sys.exit(2)\n", encoding="utf-8")
        os.environ["LLMWIKI_AUDIT_DIR"] = str(cand_dir)
        broken_cand = candidates_list()
        if broken_cand.get("ok") is not False or "harvest exploded" not in str(broken_cand.get("error")):
            problems.append(f"a failed candidate read dropped the script's stderr: {broken_cand}")
        del os.environ["LLMWIKI_AUDIT_DIR"]

        real_cfg = Path.home() / ".llmwiki-audit" / "wikiconfig.py"
        if real_cfg.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("wc_for_selftest", real_cfg)
            wc = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(wc)
            tree = tmp / "scan"
            for rel, ident in (("p1", "id-p1"), ("x/p2", "id-p2"), ("x/y/p3", "id-p3")):
                (tree / rel / ".llm-wiki").mkdir(parents=True)
                (tree / rel / "wiki").mkdir()
                (tree / rel / ".llm-wiki" / "project.json").write_text('{"id": "%s"}' % ident,
                                                                      encoding="utf-8")
                (tree / rel / "wiki" / "a.md").write_text("# s", encoding="utf-8")
            (tree / "mirror" / ".llm-wiki").mkdir(parents=True)
            (tree / "mirror" / "wiki").mkdir()
            (tree / "mirror" / ".llm-wiki" / "project.json").write_text('{"id": "id-p1"}',
                                                                        encoding="utf-8")
            (tree / "mirror" / "wiki" / "a.md").write_text("# s", encoding="utf-8")
            scan = wc.candidates(tree)
            by_name = {Path(item["root"]).name: item for item in scan["found"]}
            if not {"p1", "p2", "p3"} <= set(by_name):
                problems.append(f"the scan does not descend three levels: {sorted(by_name)}")
            if not (by_name.get("mirror") or {}).get("duplicates"):
                problems.append("a copy carrying the same project id was not flagged")
            if not scan["scanned"] or scan["skipped"]:
                problems.append(f"scan counters wrong: scanned={scan['scanned']} "
                                f"skipped={scan['skipped']}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    if problems:
        print("wiki-automation selftest FAILED:")
        for p in problems:
            print("  x", p)
        return 1
    print("wiki-automation selftest OK: root validation gate (no silent wrong answer) + automation "
          "folder resolution (env wins) + timezone normalization + the two axes labelled separately "
          "+ job ids from the settings + name/duration/error preview from a temporary run record + "
          "candidate scan (three levels, copy/mirror flagged, scan counters) + a checker reason "
          "keeping its raw text and carrying its provenance, and the wiki-job management: the "
          "engine's jobs.json gives the four roles; real disposable native jobs are inspected by the "
          "selected engine's role policy and installation journal before assigning read-only labels. "
          "Conflicting, stale, unrelated and foreign-project mappings fail closed without repair; "
          "owned native jobs retain custom schedules, delivery and IDs, use captured profile storage, "
          "and require exact-ID readbacks for labels. A job change without the page's reviewed "
          "record is refused without writing; missing jobs are created by the engine installer. "
          "The view carries the store's last run, result and late/missed dispatch flag, and /jobs/preview answers three next runs "
          "from the core's own computation or the store's refusal, without writing; the retired "
          "Task Scheduler task is no longer reported; and the candidates go through the engine "
          "script only: a strict <run>/<name> ref, a read-only legacy dry-run preview, legacy confirm "
          "flags refused before publication, a reject that needs its reason, and the script's own text kept on a refusal")
    return _health_selftest()


def _owner_router():
    import importlib.util
    path = Path(__file__).resolve().parent / 'owner_broker.py'
    spec = importlib.util.spec_from_file_location(__name__ + '._owner_broker', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = module.make_router(_owner_run, lambda: _owner_ready(), lambda: _owner_binding(), activation=_OwnerSetup())
    selected = APIRouter()
    import inspect
    for route in source.routes:
        endpoint = _selected_operation(route.endpoint)
        endpoint.__signature__ = inspect.signature(route.endpoint, eval_str=True)
        selected.add_api_route(route.path, endpoint, methods=route.methods)
    return selected


router.include_router(_owner_router(), prefix='/owner')


def _engine_router():
    import importlib.util
    path = Path(__file__).resolve().parent / 'engine_lifecycle.py'
    spec = importlib.util.spec_from_file_location(__name__ + '._engine_lifecycle', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    package = Path(__file__).resolve().parents[1]
    return module.make_router(lambda: package, lambda: json.loads((package / 'engine-release.json').read_bytes()))


router.include_router(_engine_router(), prefix='/engine')


if __name__ == "__main__" and "--selftest" in sys.argv:
    raise SystemExit(_selftest())

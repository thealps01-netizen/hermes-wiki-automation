"""Canary run for the static audit — one injected violation per rule, then a byte-exact revert.

Why: a rule that cannot fail is not a rule. Every ban in `audit_static.py` is checked here by
BREAKING a byte-exact isolated copy of the source:

    inject one violation  ->  audit must exit 1 with that rule's own message
    restore the file      ->  audit must exit 0 again, bytes identical, sha256 unchanged

Four rules carry their own lesson:

  * `panes` reads the RAW source, because a string-blanked projection would blank exactly the token
    it looks for and the rule could never fire. Its canary proves it fires on a real pane claim.
  * EXTERNAL CHECK TEXT is the largest rule. The panel prints what
    `~/.llmwiki-audit/wikiconfig.py` returns, and that checker answers in TURKISH. Five canaries
    prove the rule has teeth: a bare `reason` on a panel line (Turkish on screen), a `_TX_MAP`
    entry pointing at a key that is not in the bundle (the panel would print the key), a raw
    detail block that no longer shows the checker's own wording (the text was replaced, not kept
    beside its English reading), a raw text that stopped being the label of a `Tip`, and a
    `question` that stopped unpacking `msg.raw` (the wording dropped instead of shown beside its
    English reading). A sixth proves the BACKEND marks a checker reason with its provenance, so
    the panel can recognise it at all.
  * NATIVE TITLE is the rule this folder gained last. The panel used to carry a `tipProps(...)`
    helper that pushed its labels (and the checker's raw text) into a native `title=`: unstyled,
    ~500ms of OS delay, and like no tip the host shows. Every control is now the kit's `Tip` (and
    `aria-label` for a glyph-only button); the canary injects `title:` into a `jsx(Button, ...)`
    props object and proves the rule fires.
  * SCROLL FLOW is the rule this folder gained last. `.wa-root` is `display:grid` inside a pane of
    FIXED height, and a grid compresses its `auto` rows to fit a definite container: a short pane
    clipped every card inside its own row, `.wa-card{overflow:hidden}` cut them, and the root's
    scrollHeight stayed equal to its clientHeight — no scrollbar, and the bottom card was
    unreachable. The canary removes `grid-auto-rows:max-content` and the rule fires;
    `tests/scroll_check.cjs` measures the same promise in the app's engine (pre-fix: 3 defects and
    content cut off under the pane at every size; post-fix: 0 defects, 0 unreachable).

Running: python canary_audit.py            (exit code 0 = every rule fires and every revert is clean)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE / "audit_static.py"
JS = HERE.parent / "desktop" / "plugin.js"
API = HERE.parent / "dashboard" / "plugin_api.py"
MANIFEST = HERE.parent / "dashboard" / "manifest.json"

ID_LINE = "const PLUGIN_ID = 'wiki-automation'\n"
MANIFEST_VERSION = '"version": "%s"' % json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
ROUTE_LINE = "const ROUTE = '/wiki-automation'\n"


def _count(text: str) -> int:
    """How often a Metro anchor occurs in the panel: the canary breaks EVERY occurrence, so the rule
    cannot pass on a copy it did not see. A missing anchor counts 0 and the canary reports it."""
    return JS.read_text(encoding="utf-8").replace("\r\n", "\n").count(text)

# (rule, file, old text, new text, occurrences, expected audit output)
CANARIES: list[tuple[str, Path, str | None, str, int, str]] = [
    ("no comment in the panel", JS, ID_LINE, "// canary comment\n" + ID_LINE, 1,
     "a comment came back"),
    ("code lines stay within 120 characters", JS, ID_LINE,
     ID_LINE + f"const CANARY_{'x' * 110} = 1\n", 1, "code line is"),
    ("no trailing whitespace", JS, ROUTE_LINE, "const ROUTE = '/wiki-automation'   \n", 1,
     "trailing whitespace"),
    ("single-quoted strings only", JS, ROUTE_LINE, 'const ROUTE = "/wiki-automation"\n', 1,
     "a double-quoted JavaScript string"),
    ("loader import allow-list", JS, ID_LINE, ID_LINE + "import 'lodash'\n", 1,
     "the loader would reject this import"),
    ("exactly one bundle", JS, "const BUNDLES = {\n",
     "const BUNDLES = {\n  xx: {\n    wa: {\n      x: 'X'\n    },\n  },\n", 1,
     "exactly one 'en' bundle"),
    ("every t() key resolves", JS, "line2: t('wa.metroNoTimetable')", "line2: t('wa.metroNoTimetableCanary')", 1,
     "'wa.metroNoTimetableCanary' is missing from the bundle"),
    ("no raw key through a dynamic t()", JS, "t('wa.verify')", "t(WA_VERIFY)", 1,
     "t() is called without a literal key"),
    ("no dead bundle entry", JS, "      metroArrive: 'new drafts arrive here',\n",
     "      metroArrive: 'new drafts arrive here',\n      canaryUnused: 'x',\n", 1, "is never used"),
    ("no `lang` identifier", JS, ROUTE_LINE, ROUTE_LINE + "const lang = 'en'\n", 1,
     "a `lang` identifier is back"),
    ("no hardcoded language literal", JS, ROUTE_LINE, ROUTE_LINE + "const MODE = 'tr'\n", 1,
     "a hardcoded 'tr'/'en' literal"),
    ("no ?lang= parameter", JS, ROUTE_LINE, ROUTE_LINE + "const Q = '/x?lang=en'\n", 1,
     "a ?lang= query parameter"),
    ("no `panes` area (raw source)", JS, ROUTE_LINE, ROUTE_LINE + "const AREA_PANES = 'panes'\n",
     1, "claims the `panes` area"),
    ("never an uncloseable pane", JS, ROUTE_LINE,
     ROUTE_LINE + "const CANARY = { uncloseable: true }\n", 1, "'uncloseable' is back"),
    ("never revealOnPreset", JS, ROUTE_LINE,
     ROUTE_LINE + "const CANARY = { revealOnPreset: true }\n", 1, "'revealOnPreset' is back"),
    ("never revealPane(", JS, ROUTE_LINE, ROUTE_LINE + "const CANARY = revealPane('x')\n", 1,
     "'revealPane(' is back"),
    ("never paneVisibility(", JS, ROUTE_LINE, ROUTE_LINE + "const CANARY = paneVisibility('x')\n", 1,
     "'paneVisibility(' is back"),
    ("jsx third argument is a key", JS, "}, 'verify')", "}, ['verify'])", 1,
     "the third jsx() argument is a literal, not a key"),
    ("colors come from the theme", JS, "const MOTION = {",
     "const CANARY_COLOR = { background: '#ff0000' }\nconst MOTION = {", 1,
     "a fixed color is written"),
    ("jsx runtime is imported", JS, "'react/jsx-runtime'", "'react/jsx-dev-runtime'", 1,
     "`react/jsx-runtime` is not imported"),
    ("every CSS variable exists in the app", JS, ROUTE_LINE,
     ROUTE_LINE + "const CANARY_TONE = { color: 'var(--ui-canary-nope)' }\n", 1,
     "CSS variable --ui-canary-nope is not defined"),
    ("two-step undo stays two-step", JS, "save(true)", "save(false)", 1, "'save(true)' is missing"),
    ("unmapped external text is banned (panel)", JS,
     "    setMsg(seen ? { tone: 'bad', ...seen } : { tone: 'bad', text: t('wa.invalid') })\n",
     "    setMsg(seen ? { tone: 'bad', ...seen } : { tone: 'bad', text: t('wa.invalid') })\n"
     "  const canaryRaw = res => say('bad', res.reason)\n", 1,
     "`.reason` is read outside"),
    ("a `_TX_MAP` entry must exist in the bundle", JS, "'wa.reasonFolderMissing'",
     "'wa.reasonFolderCanary'", 1, "is not in the bundle"),
    ("the raw check text stays reachable", JS, "className: 'wa-raw'",
     "className: 'wa-raw-canary'", 4, "no longer reaches a tooltip/detail block"),
    ("no docstring in the backend", API, "def _reason_fields(payload: dict | None) -> dict:\n",
     "def _reason_fields(payload: dict | None) -> dict:\n    \"\"\"canary docstring\"\"\"\n", 1,
     "docstring of _reason_fields"),
    ("no undefined name", API,
     '    pairs = [f"project_root={root}"] + ([f"project_id={pid}"] if pid else [])\n',
     "    canary_probe = _canary_missing_name\n"
     '    pairs = [f"project_root={root}"] + ([f"project_id={pid}"] if pid else [])\n',
     1, "looks like an undefined name"),
    ("every _tx() key has a table entry", API, '_tx("auto_same_id")', '_tx("canary_key")', 1,
     "_tx('canary_key') has no entry in the message table"),
    ("the message table holds ONE language", API,
     "'auto_loud': 'with no root set the scripts do NOT stay silent — they alert',",
     "'auto_loud': ('with no root set the scripts do NOT stay silent — they alert', 'uyarır'),", 1,
     "the message table must hold exactly one language"),
    ("_tx placeholders are exact", API,
     "'auto_write_failed': 'the settings file could not be written',",
     "'auto_write_failed': 'the settings file could not be written ({path})',", 1,
     "needs 'path' and does not pass it"),
    ("a checker reason carries its provenance", API,
     'def automation_validate(payload: dict):\n',
     'def automation_validate(payload: dict):\n'
     '    canary_raw = (payload or {}).get("reason")\n', 1,
     "is read outside `_reason_fields`"),
    ("every checker payload is marked", API, "**_reason_fields(checked)", "**checked", 1,
     "is used at 6 place(s), expected 7"),
    ("the language route stays gone", API, '@router.get("/automation")',
     '@router.get("/settings")\nasync def canary_settings():\n    return {}\n\n\n'
     '@router.get("/automation")', 1, "is back"),
    ("every route the panel calls exists", API, '@router.get("/runs")',
     '@router.get("/runs-canary")', 1, "is missing — the panel calls it"),
    ("executions.db is opened read-only", API, "?mode=ro\", uri=True, timeout=5.0)",
     "?mode=rw\", uri=True, timeout=5.0)", 1,
     "no longer opened read-only"),
    ("the selftest entry point exists", API, '"--selftest" in sys.argv', '"--canary" in sys.argv',
     1, "the selftest entry point is gone"),
    ("no native title= on a control", JS, "loading: busy, disabled: busy, onClick: turnOn,",
     "loading: busy, disabled: busy, onClick: turnOn, title: t('wd.refresh'),", 1, "a native `title=` is written"),
    ("the raw check text stays a Tip label", JS, "label: question,", "label: questionCanary,", 2,
     "is not handed to a `Tip` as its label"),
    ("the raw check text is unpacked from msg.raw", JS,
     "const question = msg?.raw && msg.raw !== msg.text ? msg.raw : null",
     "const question = null", 1, "no longer unpacks `msg.raw`"),
    ("the pane, not the window, is measured", JS, "@container (max-width:620px){\n  .wa-job{",
     "@media (max-width:620px){\n  .wa-job{", 1, "a width `@media` query is back"),
    ("the panel is a query container", JS, "grid-auto-rows:max-content;container-type:inline-size}",
     "grid-auto-rows:max-content;container-size:inline-size}", 1, "`container-type:inline-size` is gone"),
    ("a failed read keeps the backend error", JS, "detail: jobs.error", "detail: null", 1,
     "'detail: jobs.error' is missing"),
    ("no class without a rule", JS, "className: 'wa-cand-pages'",
     "className: 'wa-msgbox wa-cand-pages'", 1, "'wa-msgbox' is back"),
    ("the job row keeps one name line", JS, ".wa-job-line{display:flex",
     ".wa-job-line{display:block", 1, "the job row's name line"),
    ("the job row has its own narrow breakpoint", JS, "@container (max-width:620px){\n  .wa-job{",
     "@media (max-width:620px){\n  .wa-job{", 1, "the `@container (max-width:620px)` block is gone"),
    ("the panel's own type stays above the floor", JS, ".wa-job-meta{font-size:12px",
     ".wa-job-meta{font-size:11px", 1, "is under the 12 px floor"),
    ("an empty live region takes a grid row", JS,
     ".wa-shell [aria-live]:empty{position:absolute;", ".wa-shell [aria-live]:empty{position:static;", 1,
     "an empty aria-live region takes a grid row again"),
    ("motion: a hand-timed entry in the panel stylesheet", JS, "const STYLE = `",
     "const STYLE = `\n.wa-metro-canary{animation:wa-canary 760ms cubic-bezier(0,0,.38,.9) backwards}", 1,
     "is written by hand (STYLE"),
    ("motion: the shared entry ignores reduced motion", JS,
     '  .wa-metro-wire[data-kind="line"][data-state="run"]{animation:none}\n',
     "", 1, "but is not switched off under prefers-reduced-motion"),
    ("the type table stays above the floor", JS, "const TYPE = { micro: 12,",
     "const TYPE = { micro: 10.5,", 1, "TYPE.micro is 10.5 px"),
    ("counters stay on the kit's chips", JS, "className: 'wa-cand-pages', variant: 'muted'",
     "className: 'wa-cand-pages', size: 'xs', variant: 'muted'", 1, "`xs` step (9.6 px)"),
    ("a status chip keeps its capital", JS, "ok: 'Verified'", "ok: 'verified'", 1,
     "reads as a sentence, not a label"),
    ("the panel root cannot compress its rows", JS,
     "  grid-auto-rows:max-content;container-type:inline-size}",
     "  container-type:inline-size}", 1, "grid-auto-rows:max-content"),
    ("secondary actions share one shape", JS,
     "onClick: verify, size: 'sm', variant: 'outline'", "onClick: verify, size: 'sm', variant: 'ghost'", 1,
     "a `ghost` Button is back"),
    ("source status is polled", JS, "const harvest = usePolling(api.harvestStatus, 60000)",
     "const harvest = usePolling(api.harvestStatus, 6000)", 1, "the source status poll is gone"),
    ("source failures keep their backend error", JS, "detail: harvest.error", "detail: null", 2,
     "the source status failure lost its backend error"),
    ("the obsolete KPI shell stays gone", JS, ID_LINE, ID_LINE + "const CANARY_SHELL = '.g-kpis{'\n", 1,
     "obsolete KPI/gauge shell is back"),
    ("the candidate filter is a real field", JS,
     "containerClassName: 'desktop-input-chrome wa-filter'", "containerClassName: 'wa-filter'", 1,
     "the candidate filter lost its field chrome"),
    ("the version agrees with the dashboard manifest", MANIFEST,
     MANIFEST_VERSION, '"version": "0.0.0"', 1, "version drift"),
    ("no async route runs a subprocess", API, 'def automation_derive(payload: dict):\n',
     'async def automation_derive(payload: dict):\n', 1,
     "is async and calls `_config_run`"),
    ("no job catalogue of the plugin's own", API, 'ENGINE_JOBS = "jobs.json"\n',
     'ENGINE_JOBS = "jobs.json"\nJOB_CATALOGUE_PATH = Path(__file__).resolve().parent / "job_catalogue.json"\n',
     1, "reads a job catalogue of its own again"),
    ("the job list is the engine's jobs.json", API, 'ENGINE_JOBS = "jobs.json"', 'ENGINE_JOBS = "catalogue.json"',
     1, "no longer comes from the engine's jobs.json"),
    ("job changes compare the reviewed record under the store lock", API,
     'if _role_map() != mapped or _job_bindings() != binding or cron.get_job(jid) != rec:',
     'if _role_map() != mapped or _job_bindings() != binding:', 1,
     "no longer re-reads and compares the reviewed record"),
    ("job changes stay bound to the page's facts", API,
     'if _job_facts(rec, cron) != {k: expected[k] for k in _JOB_FACTS}:', 'if False:', 1,
     "no longer re-reads and compares the reviewed record"),
    ("the panel never creates a native job itself", API,
     'return {"ok": False, "install": True, "reason": _tx("job_create_install")}',
     'cron.create_job(prompt="", schedule=expr)\n        return {"ok": False, "install": True, "reason": _tx("job_create_install")}', 1,
     "creates jobs outside the reviewed engine installation"),
    ("approve stays two-step (backend)", API, 'elif not body.get("confirm"):', 'elif False:', 1,
     "an approve no longer waits for its confirmation"),
    ("the unconfirmed approve is a dry run", API, '["approve", ref, "--dry-run"]', '["approve", ref]', 1,
     "the unconfirmed approve is no longer a dry run"),
    ("approve stays two-step (panel)", JS, "const act = async (ref, action, confirm = false)",
     "const act = async (ref, action, confirm = true)", 1, "the first Approve is no longer unconfirmed"),
    ("confirmed approve stays bound to its candidate", JS, "if (confirm && (armed?.ref !== ref || confirmation.current !== armed)) return",
     "if (false) return", 1, "confirmation is not bound to the selected candidate"),
    ("a stale or duplicate decision is refused", JS, "if (inFlight.current || !canAct(ref, action)",
     "if (false", 1, "a stale or duplicate decision can be sent"),
    ("invalid format blocks approval", JS, "!now.detail.format_problems.length", "true", 1,
     "invalid candidate format can be approved"),
    ("a reject needs its reason (backend)", API, 'return {**head, "reason": _tx("cand_no_reason")}',
     'why = why or "none"', 1, "a reject no longer needs a reason"),
    ("a reject needs its reason (panel)", JS, "disabled: !rejectable || !why.trim()", "disabled: !rejectable", 1,
     "a reject can be sent without a reason"),
    ("a candidate ref is validated", API, '    if not _CANDIDATE_REF.fullmatch(ref):\n        return {**head,',
     '    if False:\n        return {**head,', 1, "without the strict"),
    ("the backend never writes the wiki itself", API, "import os\n", "import os\nimport shutil\n", 1,
     "the backend touches the wiki's files itself"),
    ("the candidate routes exist", API, '@router.post("/candidates/act")', '@router.post("/candidates/do")', 1,
     "is missing — the panel calls it"),
    ("failed candidate reads keep the backend error on the review desk", JS, "detail: cands.error", "detail: null", 1,
     "'detail: cands.error' is missing"),
    ("the retired check stays retired", API, '"neutral", False),', '"warn", True),', 1,
     "not_indexed is presented as a live check again"),
    ("the Health routes live under /health/", API, '@router.get("/health/watchdog")', '@router.get("/watchdog")',
     1, "is back outside /health/"),
    ("the archive folder is kept", API, '"backups" / "wiki-watchdog"', '"backups" / "wiki-automation"', 2,
     "the archive folder is no longer"),
    ("one archive-clear keeps its 3000-key cap", API, "MAX_RUNS = 3000\n", "MAX_RUNS = 30000\n", 1,
     "the 3000-key cap on one archive-clear is gone"),
    ('health · layout: a job label column leaves the shared width', JS, '.pa-act-row{display:grid;grid-template-columns:${LABEL_W}px 1fr;', '.pa-act-row{display:grid;grid-template-columns:118px 1fr;', 1, 'does not read the shared label column'),
    ('health · motion: a transition written by hand', JS, "  transition:${move('drawer', 'transform, opacity')}}", '  transition:transform .32s ease, opacity .32s ease}', 1, 'is written by hand'),
    ('health · motion: a job nothing uses', JS, '  drawer: { ms: 320, ease: EASE.entrance }', '  drawer: { ms: 320, ease: EASE.entrance },\n  canaryjob: { ms: 99, ease: EASE.standard }', 1, 'is never used'),
    ('health · motion: reduced motion is not honoured for a selector', JS, '@media (prefers-reduced-motion: reduce){.pa-sel-ico{transition:none}}', '@media (prefers-reduced-motion: reduce){.pa-sel-ico-x{transition:none}}', 1, 'is not switched off under'),
    ('health · motion: the inline path loses its switch', JS, "const instantMove = (job, props) => (prefersReduced() ? 'none' : move(job, props))", 'const instantMove = (job, props) => move(job, props)', 1, 'goes through instantMove'),
    ('health · bundle: never reaches ctx.i18n.register', JS, 'ctx.i18n?.register?.(BUNDLES)', 'ctx.i18n?.register?.(BUNDLES2)', 1, 'never reaches `ctx.i18n.register`'),
    ('health · keys: a dead bundle entry nothing reads', JS, "children: t('wd.deletedNote')", "children: t('wd.noBody')", 1, "'wd.deletedNote' is never used"),
    ('health · keys: a dynamic t() key no audited map produces', JS, "meta: t('wd.chartFlowMeta', days),", 'meta: t(flowMetaKey, days),', 1, 't() is called without a literal key'),
    ('health · language: the React door is gone', JS, 'const t = usePluginI18n(PLUGIN_ID)', 'const t = key => key', JS.read_text(encoding='utf-8').count('const t = usePluginI18n(PLUGIN_ID)'), 'usePluginI18n is never called'),
    ('health · jsx: children passed as the third argument', JS, "jsx('span', { className: 'wa-label', children: t('wa.checkAsWritten') }, 'c'),", "jsx('span', { className: 'wa-label', children: t('wa.checkAsWritten') }, ['c']),", 4, 'the third jsx() argument is a literal, not a key'),
    ('health · style: a fixed hex color in a style object', JS, "const value = { fontSize: TYPE.body, lineHeight: 1.55, color: 'var(--ui-text-secondary)' }", "const value = { fontSize: TYPE.body, lineHeight: 1.55, color: '#ff0000' }", 1, 'a fixed color is written'),
    ('health · copy: a `(s)` plural on screen', JS, "      jobsN: n => wdPlural(n, 'job', 'jobs'),", '      jobsN: n => `${n} job(s)`,', 1, 'a `(s)` plural is written'),
    ("health · copy: the delta coloured by the arrow's direction", JS, '.pa-delta[data-dir="good"]>i{color:var(--ui-green)}', '.pa-delta[data-dir="up"]>i{color:var(--ui-green)}', 1, "the delta is coloured by the arrow's direction"),
    ('health · type: a size written at its call site', JS, 'fontSize: TYPE.body, lineHeight: 1.55', 'fontSize: 12, lineHeight: 1.55', 1, 'fontSize is written at its call site'),
    ('health · comment: a backend docstring came back', API, 'def _tx(key: str, **kw) -> str:', 'def _tx(key: str, **kw) -> str:\n    """Translates."""', 1, 'docstring of _tx'),
    ('health · clear: alerts.log is emptied without a confirm', API, '    if (body or {}).get("confirm") is not True:\n', '    if False:\n', 1, 'is not confirm-then-archive-first'),
    ('health · clear: alerts.log is emptied before its archive', API, '    original = log.read_bytes()\n', '    original = log.read_bytes()\n    os.replace(tmp, log)\n', 1, 'is not confirm-then-archive-first'),
    ('health · clear: alerts.log is emptied whole after its archive', API, '        rest = current[len(copied):]\n', '        rest = b""\n', 1, 'truncates the whole log'),
    ('health · clear: alerts.log is rewritten in place', API, '            tmp.write_bytes(rest)\n            os.replace(tmp, log)\n', '            log.write_bytes(rest)\n            os.replace(tmp, log)\n', 1, 'truncates the whole log'),
    ('health · clear: a log that changed after the archive is rewritten anyway', API, '        if not current.startswith(copied):\n', '        if False:\n', 1, 'is not confirm-then-archive-first'),
    ('health · clear: a running run can be removed', API, '                                     " and status not in (\'running\', \'claimed\')", chunk).rowcount', '                                     "", chunk).rowcount', 1, 'can delete a running or claimed run'),
    ('health · clear: an archive name is stamped to the second', API, '    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")', '    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")', 1, 'an archive name is not unique'),
    ('health · clear: an archive name can collide', API, '    while path.exists():', '    while False:', 1, 'an archive name is not unique'),
    ('health · css: a fixed white on the accent', JS, '  color:var(--dt-primary-foreground)}\n.pa-pop-sep', '  color:#fff}\n.pa-pop-sep', 1, "the CSS template writes '#fff'"),
    ('health · css: an rgba shadow on the tip', JS, 'line-height:1.45;box-shadow:var(--shadow-md);', 'line-height:1.45;box-shadow:0 6px 18px rgba(0,0,0,.35);', 1, "the CSS template writes 'rgba('"),
    ('health · css: the calendar forces a dark colour scheme', JS, '  box-shadow:var(--shadow-md)}\n.pa-cal-head', '  box-shadow:var(--shadow-md);color-scheme:dark}\n.pa-cal-head', 1, "the CSS template writes 'color-scheme:dark'"),
    ('health · page: painted with the sidebar background', JS, "background: 'transparent', color: 'var(--ui-text-primary)'", "background: 'var(--ui-bg-sidebar)', color: 'var(--ui-text-primary)'", 1, 'the page paints itself with the sidebar background'),
    ('health · page: CSS root painted with the sidebar background', JS, '.pa-root{container-type:inline-size;', '.pa-root{background:var(--ui-bg-sidebar);container-type:inline-size;', 1, 'the page paints itself with the sidebar background'),
    ('health · i18n: a bundle key missing from the panel map', JS, "const SORT_LABEL = { new: 'wd.sortNew', old: 'wd.sortOld', job: 'wd.sortJob', status: 'wd.sortStatus' }", "const SORT_LABEL = { new: 'wd.sortNew', old: 'wd.sortOld', job: 'wd.sortJob', status: 'wd.sortX' }", 1, "'wd.sortX' is missing from the bundle"),
    ('health · runtime: react/jsx-runtime is not imported', JS, "import { jsx, jsxs } from 'react/jsx-runtime'", "import { jsx, jsxs } from 'react'", 1, '`react/jsx-runtime` is not imported'),
    ('health · css: an undefined theme variable', JS, 'var(--ui-text-secondary);cursor:pointer;white-space:nowrap;font-variant', 'var(--ui-text-secondary-typo);cursor:pointer;white-space:nowrap;font-variant', 1, 'is not defined by the app'),
    ('health · backend: the table holds more than one language', API, "    'wd_detail_short': 'detail line',", "    'wd_detail_short': {'tr': 'ayrıntı satırı'},", 1, 'is not a plain string'),
    ('health · backend: _tx() with a key that is not in the table', API, None, '_MISSING = _tx("wd_nope")', 0, "_tx('wd_nope') has no entry in the message table"),
    ('health · backend: _tx() that forgets a placeholder', API, None, '_FORGOT = _tx("wd_cleared")', 0, "needs 'n' and does not pass it"),
    ('health · backend: a finding kind without its description row', API, '("wd_not_indexed_title", "wd_not_indexed_action"', '("wd_not_indexed_titel", "wd_not_indexed_action"', 1, "'wd_not_indexed_titel' (finding kind 'not_indexed') has no entry"),
    ('health · backend: a route the panel calls is gone', API, '@router.get("/health/jobs/run")', '@router.get("/health/jobs/runx")', 1, 'the route \'@router.get("/health/jobs/run")\' is missing'),
    ('health · backend: the db is no longer read-only', API, '?mode=ro', '?mode=rw', 5, 'executions.db is no longer opened read-only'),
    ('health · backend: the selftest entry point is gone', API, 'raise SystemExit(_selftest())', 'raise SystemExit(0)', 1, 'the selftest entry point is gone'),
    ('health · backend: an undefined name inside a function', API, '        return text.format(**kw)', '        return text.format(**kk)', 1, 'looks like an undefined name: kk'),
    ('health · mapping: an external finding line printed straight into the card', JS, "jsx('p', { className: 'pa-drawer-txt', children: findingEnglish(f, t) }, 'mapped'),", "jsx('p', { className: 'pa-drawer-txt', children: f.detail }, 'mapped'),", 1, 'an external finding line is printed straight into the panel'),
    ('health · mapping: a finding kind with no English mapping row', JS, "  drift: 'wd.map.drift', mirror: 'wd.map.mirror', identity: 'wd.map.identity',", "  drift: 'wd.map.drift', mirrorx: 'wd.map.mirror', identity: 'wd.map.identity',", 1, "the backend can emit a 'mirror' finding and FINDING_MAP has no row"),
    ('health · mapping: the mapping is never applied', JS, "children: findingEnglish(f, t) }, 'mapped'),", "children: f.what }, 'mapped'),", 1, 'the English finding mapping is never applied'),
    ('health · title: a native title passed to a DOM element', JS, None, "const leaked = jsx('span', { title: 'native' }, 'leak')", 0, 'a native title is passed to the DOM element'),
    ('health · title: the HTML spelling of a native title', JS, None, 'const html = \'<b title="native"></b>\'', 0, 'a native `title=` attribute is written'),
    ('health · kit: a kit component is imported and never rendered', JS, '      jsxs(PanelDetail, {', "      jsxs('div', {", 1, 'PanelDetail is imported and never rendered'),
    ('health · kit: a kit component is not imported at all', JS, 'PanelEmpty, PanelList,', 'PanelEmpty,', 1, 'the kit component PanelList is not imported'),
    ("the schedule preview never writes the store", API, "    runs, anchor = [], None\n",
     "    runs, anchor = [], None\n    cron.update_job(expr, {})\n", 1,
     "the schedule preview calls `update_job`"),
    ("the schedule preview never nudges the scheduler", API, "        anchor = str(nxt)\n",
     "        anchor = str(nxt)\n        _notify_scheduler()\n", 1, "the schedule preview calls `_notify_scheduler`"),
    ("the preview asks the core for its next runs", API, "nxt = cron.compute_next_run(parsed, anchor)",
     "nxt = None", 1, "no longer asks the core's own `compute_next_run`"),
    ("the preview is the one read-only POST", API, '@router.post("/jobs/preview")',
     '@router.post("/jobs/peek")', 1, "a write route came back: '/jobs/peek'"),
    ("Save schedule keeps its readable ink", JS,
     ".wa-root .wa-sched-save{font-weight:600;color:var(--ui-text-primary);",
     ".wa-root .wa-sched-save{font-weight:600;color:var(--ui-accent);", 1,
     "`.wa-sched-save` is inked with `--ui-accent` again"),
    ("a run result chip keeps its capital", JS, "runOk: 'OK'", "runOk: 'ok'", 1,
     "reads as a sentence, not a label"),
    ("a late/missed chip keeps its capital", JS, "runMissed: 'Missed'", "runMissed: 'missed'", 1,
     "reads as a sentence, not a label"),
    # ── Metro (2.5.0): the removed four-tab composition cannot crawl back ──────────────────────────
    ("removed: TAB_IDS", JS, None, "const TAB_IDS = ['metro']", 0, "TAB_IDS is back"),
    ("removed: the kit Tabs strip", JS, None, "const strip = jsx(TabsTrigger, { value: 'x' }, 'x')", 0,
     "the kit Tabs strip is back"),
    ("removed: a tab role", JS, None, "const tabRole = { role: 'tab' }", 0, "a tab role is back"),
    ("removed: the Nexus map", JS, None, "const mapNode = { className: 'nx-node' }", 0, "the Nexus map is back"),
    ("removed: the heartbeat strip", JS, None, "function HeartbeatStrip() { return null }", 0,
     "the heartbeat strip is back"),
    ("removed: a per-tab view", JS, None, "function ChronicleTab() { return null }", 0, "a per-tab view is back"),
    ("removed: tab navigation", JS, None, "const openJournal = () => setTab(0)", 0, "tab navigation is back"),
    ("removed: the Chronicle lower review queue", JS, None, "function ReviewQueue() { return null }", 0,
     "the Chronicle lower review queue is back"),
    ("removed: the second run list", JS, None, "const runRow = { className: 'wa-run' }", 0,
     "the second run list is back"),
    ("removed: a view name in the bundle", JS, "'Good service on the whole line'",
     "'Good service on the whole Nexus line'", _count("'Good service on the whole line'"),
     "the bundle names the removed view 'Nexus'"),
    # ── Metro (2.5.0): the DOM contract, the priority keys and the insert-only composer ────────────
    ("metro: the root is the query container", JS, ".wa-metro{", ".wa-metro-gone{", _count(".wa-metro{"),
     "`.wa-metro{...container-type:inline-size}` is gone"),
    ("metro: stations carry data-wa-station", JS, "'data-wa-station'", "'data-wa-stop'",
     _count("'data-wa-station'"), "the Metro attribute 'data-wa-station' is missing"),
    ("metro: branch lines carry data-wa-line", JS, "'data-wa-line'", "'data-wa-branch'",
     _count("'data-wa-line'"), "the Metro attribute 'data-wa-line' is missing"),
    ("metro: the header buttons carry data-wa-nav", JS, "'data-wa-nav'", "'data-wa-head'",
     _count("'data-wa-nav'"), "the Metro attribute 'data-wa-nav' is missing"),
    ("metro: the alert bar carries data-alert", JS, "'data-alert'", "'data-urgent'", _count("'data-alert'"),
     "the Metro attribute 'data-alert' is missing"),
    ("metro: the detail carries data-for", JS, "'data-for'", "'data-which'", _count("'data-for'"),
     "the Metro attribute 'data-for' is missing"),
    ("metro: the loading skeleton keeps its class", JS, "wa-metro-skeleton", "wa-metro-loading",
     _count("wa-metro-skeleton"), "the Metro class `wa-metro-skeleton` is missing"),
    ("metro: the segments are an SVG", JS, "wa-metro-wires", "wa-metro-rails", _count("wa-metro-wires"),
     "the Metro class `wa-metro-wires` is missing"),
    ("metro: every priority key exists (harvest-failed)", JS, "'harvest-failed'", "'harvest-broke'",
     _count("'harvest-failed'"), "the alert priority key 'harvest-failed' is missing"),
    ("metro: every priority key exists (read-failed)", JS, "'read-failed'", "'read-broke'",
     _count("'read-failed'"), "the alert priority key 'read-failed' is missing"),
    ("metro: good service has its words", JS, "'Good service on the whole line'", "'All fine'",
     _count("'Good service on the whole line'"), "the Metro copy 'Good service on the whole line' is missing"),
    ("metro: an engine update has its words", JS, "'Engine update ready'", "'Engine update waiting'",
     _count("'Engine update ready'"), "the Metro copy 'Engine update ready' is missing"),
    ("metro: a false insert has its note", JS, "'The chat box did not open. Start a new chat, then press again.'",
     "'Open a chat.'", _count("'The chat box did not open. Start a new chat, then press again.'"),
     "the Metro copy 'The chat box did not open. Start a new chat, then press again.' is missing"),
    ("metro: Ask Hermes opens a new chat", JS, "host.newChat()", "host.openChat()", _count("host.newChat()"),
     "no longer opens a new chat"),
    ("metro: Ask Hermes writes only into the new chat", JS, "put('new')", "put('active')", _count("put('new')"),
     "no longer opens a new chat"),
    ("metro: segments come from layout", JS, "ResizeObserver", "ResizeWatcher", _count("ResizeObserver"),
     "the line's segments are no longer computed from layout"),
    ("metro: Ask Hermes inserts into the composer", JS, "composer.insertText(address", "composer.insertLater(address",
     _count("composer.insertText(address"), "no longer opens a new chat"),
    ("metro: Ask Hermes never submits", JS, None, "const sendNow = () => host.composer.submit(null, 'x')", 0,
     "the panel calls 'composer.submit'"),
]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_audit() -> tuple[int, str]:
    done = subprocess.run([sys.executable, str(AUDIT)], capture_output=True, text=True,
                          cwd=str(HERE))
    return done.returncode, done.stdout + done.stderr


def _run_canaries() -> int:
    originals = {path: path.read_bytes() for path in (JS, API, MANIFEST)}
    digests = {path: _sha(blob) for path, blob in originals.items()}
    crlf = {path: b"\r\n" in blob for path, blob in originals.items()}

    def text_of(path: Path) -> str:
        return originals[path].decode("utf-8").replace("\r\n", "\n")

    def write_variant(path: Path, body: str) -> None:
        blob = body.replace("\n", "\r\n") if crlf[path] else body
        path.write_bytes(blob.encode("utf-8"))

    for path in (JS, API, MANIFEST):
        print(f"{path.name}: sha256 {digests[path][:16]}…")
    code, out = run_audit()
    if code != 0:
        print("AUDIT is already red — fix that first")
        print(out)
        return 1
    print("baseline: audit exit 0")

    failures = []
    for rule, path, old, new, count, expected in CANARIES:
        original = text_of(path)
        if old is None:
            old, new = original, original + "\n" + new + "\n"
        found = original.count(old)
        if found != count and not (old == original and count == 0):
            failures.append(f"{rule}: injection anchor found {found} times, expected {count}")
            print(f"FAIL {rule}: anchor found {found}x, expected {count}x")
            continue
        write_variant(path, original.replace(old, new))
        try:
            code, out = run_audit()
        finally:
            path.write_bytes(originals[path])
        restored = path.read_bytes() == originals[path]
        if code != 1:
            failures.append(f"{rule}: audit exit {code}, expected 1")
            print(f"FAIL {rule}: audit exit {code}")
        elif expected not in out:
            failures.append(f"{rule}: audit fired without the rule's message ({expected!r})")
            print(f"FAIL {rule}: wrong message")
        elif not restored:
            failures.append(f"{rule}: the file was not restored byte for byte")
            print(f"FAIL {rule}: revert not byte-exact")
        else:
            line = next((l.strip() for l in out.splitlines() if expected in l), "")
            print(f"OK   {rule}  ->  exit 1 · {line[:100]}")

    for path, blob in originals.items():
        if path.read_bytes() != blob:
            failures.append(f"{path.name} differs from the pre-canary file")
        if _sha(path.read_bytes()) != digests[path]:
            failures.append(f"{path.name}: sha256 changed by the canary run")
    code, out = run_audit()
    if code != 0:
        failures.append("audit did not come back green after the reverts")
    print(f"after reverts: audit exit {code} · both files byte-identical, sha256 unchanged")
    if failures:
        print("CANARY: problems found")
        for line in failures:
            print("  -", line)
        return 1
    print(f"CANARY clean — {len(CANARIES)} rules, each fires on its own injected violation and the "
          "source comes back byte for byte (sha256 unchanged)")
    return 0


@contextmanager
def isolated_sources():
    source_paths = (HERE / "audit_static.py", HERE / "canary_audit.py", HERE / "release_gate.py",
                    HERE / "env.py", HERE.parent / "desktop" / "plugin.js",
                    HERE.parent / "dashboard" / "plugin_api.py",
                    HERE.parent / "dashboard" / "manifest.json", HERE.parent / "plugin.yaml",
                    HERE.parent / "CHANGELOG.md")
    catalogue = HERE.parent / "dashboard" / "job_catalogue.json"
    if catalogue.exists():
        source_paths += (catalogue,)
    source_bytes = {path: path.read_bytes() for path in source_paths}
    with tempfile.TemporaryDirectory(prefix="wiki-audit-canary-", dir=os.environ.get("TMPDIR")) as folder:
        root = Path(folder)
        mapping = {path: root / path.relative_to(HERE.parent) for path in source_paths}
        for source, target in mapping.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        try:
            yield mapping
        finally:
            if any(path.read_bytes() != blob for path, blob in source_bytes.items()):
                raise RuntimeError("Working sources changed during isolated verification")


def main() -> int:
    global AUDIT, JS, API, MANIFEST, CANARIES
    with isolated_sources() as mapping:
        saved = AUDIT, JS, API, MANIFEST, CANARIES
        try:
            AUDIT, JS, API, MANIFEST = (mapping[path] for path in (AUDIT, JS, API, MANIFEST))
            CANARIES = [(rule, mapping[path], old, new, count, expected)
                        for rule, path, old, new, count, expected in CANARIES]
            return _run_canaries()
        finally:
            AUDIT, JS, API, MANIFEST, CANARIES = saved

if __name__ == "__main__":
    sys.exit(main())

"""Static audit — looks for the class of code that fails SILENTLY (Wiki Automation panel).

Why it exists: the quiet failures really happened in this panel.
  * A key missing from the message table left the panel printing a raw key or nothing at all.
  * `_tx("key", a=...)` that forgot a parameter made `.format` raise `KeyError`, the route answered
    500 and the page went blank — a whole endpoint taken down by one missing argument.
  * A dictionary key ending in `from` inside the panel matched the app's plugin-loader regex; the
    WHOLE plugin was rejected and the page disappeared with no error on screen.
  * A flat `wa.x` bundle registered through `ctx.i18n.register` is invisible to the app translator,
    which resolves keys by DOT-PATH — the panel then shows raw keys while the bundle looks correct.
  * A `reason` the external checker (`wikiconfig.py`) produced was printed as it arrived: the panel
    showed Turkish wording in an English UI. Every reason now passes `txReason(...)`, and the raw
    text is kept beside its English reading instead of being dropped.
Running: python audit_static.py            (exit code 0 = clean)
"""
from __future__ import annotations

import ast
import builtins
import io
import json
import re
import sys
import tokenize
from pathlib import Path

import env
import release_gate

HERE = Path(__file__).resolve().parent
API = HERE.parent / "dashboard" / "plugin_api.py"
JS = HERE.parent / "desktop" / "plugin.js"

# A checker reason may only be read as the first argument of the mapping helper, together with its
# provenance. `reason` on its own is the unmapped, Turkish wording on an English screen.
REASON_CALL_RE = re.compile(
    r"txReason\(\s*[A-Za-z_$][\w$.]*\.reason\b[^,]*,\s*[A-Za-z_$][\w$.]*\.reason_source\b")
TX_MAP_ENTRY_RE = re.compile(r"\[\s*'([^']*)'\s*,\s*'(wa\.[a-zA-Z0-9.]+)'\s*\]")
RAW_REASON_READ_RE = re.compile(r"""\.get\(\s*['"]reason['"]\s*\)|\[\s*['"]reason['"]\s*\]""")
REASON_SITES = 7

# The app's REAL rule, copied from its source:
#   apps/desktop/src/contrib/runtime-loader.ts:60
#   /(from\s*|import\s*\(\s*|import\s+)(['"])([^'"]+)\2/g
# NO WORD BOUNDARY: a quote right after a `from`/`import` token makes the matched text an "import",
# and anything outside the allow-list makes the loader reject the plugin as a whole. A dictionary key
# such as `t('wd.from')` is exactly that, so the rule is applied verbatim here as well.
LOADER_IMPORT_RE = re.compile(r"""(from\s*|import\s*\(\s*|import\s+)(['"])([^'"]+)\2""")
LOADER_ALLOWED = {"@hermes/plugin-sdk", "react", "react/jsx-runtime", "react/jsx-dev-runtime"}

# Literal writes of a language choice, or an identifier that reads one. There is exactly one language
# source (the app), so none of these may come back.
LANG_PATTERNS = (
    (re.compile(r"(?<![A-Za-z0-9_$])lang(?![A-Za-z0-9_$])", re.I), "a `lang` identifier"),
    (re.compile(r"explain_language|app_language|Accept-Language|display\.language", re.I),
     "a language setting reference"),
    (re.compile(r"['\"](tr|en)['\"]"), "a hardcoded 'tr'/'en' literal"),
    (re.compile(r"\?lang="), "a ?lang= query parameter"),
)

# Color literals are banned: the app flips themes through variables, so a fixed color yields an
# unreadable surface in the other theme. Only `var(--ui-*)` and `color-mix(...)` may carry color.
COLOR_PROP_RE = re.compile(
    r"\b(?:background|backgroundColor|border|borderTop|borderRight|borderBottom|borderLeft|color"
    r"|outline)\s*:\s*'([^']*)'")
COLOR_LITERAL_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")

# A native `title=` is not a tooltip: unstyled, ~500ms OS delay, and it clashes with the themed
# `Tip` the host uses everywhere (its own `no-native-title.test.ts` fails on any <button> carrying
# one). The FILE PICKER's `title` option is not a DOM attribute — it names the dialog window — so
# the arguments of a `ctx.os.pickOpenPath(...)` call are exempt.
NATIVE_TITLE_RE = re.compile(r"(?<![A-Za-z0-9_$])title(?![A-Za-z0-9_$])\s*:")
AUDITED_KEY_MAPS = ("SORT_LABEL", "STATUS_BADGE", "DELIVERY_BADGE", "WINDOW_LABEL", "LEGEND_KEYS",
                    "FINDING_MAP", "FINDING_SHORT", "TAB_LABEL", "SCHED_MODE_LABEL")
NATIVE_TITLE_WRITES = ("setAttribute('title'", '.title =', 'tipProps(')
CONTROL_TYPES = {
    'Button', 'RowButton', 'Input', 'Textarea', 'SearchField', 'SegmentedControl',
    'PanelAction', 'PanelAddButton', 'PanelRowMenu', 'Switch', 'Checkbox', 'SelectTrigger'
}

problems: list[str] = []


def _report(message: str) -> None:
    problems.append(message)


# ---------------------------------------------------------------------------
# Source projections
# ---------------------------------------------------------------------------
def scan_js(src: str, collapse: bool = False) -> tuple[str, list[tuple[int, str]]]:
    """Strip JavaScript to its CODE: comments removed, string/template bodies blanked (newlines kept).

    The projection is what structural checks run on, so a rule that mentions `lang` or `#fff` inside a
    string cannot trip the check that guards against it. Positions stay aligned with the source
    unless *collapse* asks for the bodies to be dropped instead of blanked — which is what the line
    length check wants (a long string is not a long line of code). Returns (code, comments by line).
    """
    out: list[str] = []
    comments: list[tuple[int, str]] = []
    line = 1
    i, n = 0, len(src)

    def blob(text: str) -> None:
        for c in text:
            out.append(c if c == "\n" else ("" if collapse else " "))

    while i < n:
        ch = src[i]
        if ch in "'\"":
            quote = ch
            out.append(quote)
            i += 1
            start = i
            while i < n:
                c = src[i]
                if c == "\\":
                    i += 2
                    continue
                if c == quote:
                    break
                if c == "\n":
                    line += 1
                i += 1
            blob(src[start:i])
            if i < n:
                out.append(quote)
                i += 1
            continue
        if ch == "`":
            out.append("`")
            i += 1
            start = i
            while i < n:
                c = src[i]
                if c == "\\":
                    i += 2
                    continue
                if c == "`":
                    break
                if c == "\n":
                    line += 1
                i += 1
            blob(src[start:i])
            if i < n:
                out.append("`")
                i += 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            end = src.find("\n", i)
            end = n if end < 0 else end
            comments.append((line, src[i:end]))
            out.append("" if collapse else " " * (end - i))
            i = end
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
            comments.append((line, src[i:end]))
            line += src.count("\n", i, end)
            blob(src[i:end])
            i = end
            continue
        if ch == "\n":
            line += 1
        out.append(ch)
        i += 1
    return "".join(out), comments


def split_args(code: str, open_paren: int) -> list[str]:
    """Top-level arguments of the call whose `(` sits at *open_paren* (strings are blanked already)."""
    depth = 0
    args: list[str] = []
    current: list[str] = []
    for i in range(open_paren, len(code)):
        ch = code[i]
        if ch in "([{":
            depth += 1
            if depth == 1:
                continue
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append("".join(current))
                return args
        elif ch == "," and depth == 1:
            args.append("".join(current))
            current = []
            continue
        current.append(ch)
    return args


# ---------------------------------------------------------------------------
# Panel (plugin.js)
# ---------------------------------------------------------------------------
def check_no_comments() -> None:
    """The panel and the backend carry no comments and no docstrings (the WHY lives in Docs/)."""
    src = JS.read_text(encoding="utf-8")
    _code, comments = scan_js(src)
    for line, body in comments:
        _report(f"plugin.js:{line}: a comment came back ({body.strip()[:50]!r}) — the reason belongs "
                "in Docs/wiki-automation-notes.md")
    py_src = API.read_text(encoding="utf-8")
    with tokenize.open(API) as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if token.type == tokenize.COMMENT:
                _report(f"plugin_api.py:{token.start[0]}: a comment came back "
                        f"({token.string.strip()[:50]!r}) — the reason belongs in "
                        "Docs/wiki-automation-notes.md")
    tree = ast.parse(py_src)
    docs = []
    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str)):
        docs.append((1, "module docstring"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docs.append((node.lineno, f"docstring of {node.name}"))
    for line, what in docs:
        _report(f"plugin_api.py:{line}: a {what} came back — the reason belongs in "
                "Docs/wiki-automation-notes.md")


def strip_py_strings(src: str) -> str:
    """Python source with string bodies blanked, so `#` inside a string stays data and a long message
    is not read as a long line of code. Offsets come from the tokenizer (ast reports BYTE columns)."""
    chars = list(src)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError):
        return src
    literal_types = {tokenize.STRING}
    if hasattr(tokenize, "FSTRING_MIDDLE"):
        literal_types.add(tokenize.FSTRING_MIDDLE)
    offsets = [0]
    for line in src.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    for token in tokens:
        if token.type not in literal_types:
            continue
        start = offsets[token.start[0] - 1] + token.start[1]
        end = offsets[token.end[0] - 1] + token.end[1]
        for i in range(start, min(end, len(chars))):
            if chars[i] != "\n":
                chars[i] = ""
    return "".join(chars)


def check_line_length() -> None:
    """No code line runs past 120 characters; a long string literal is exempt (its body is blanked)."""
    for name, src in (("plugin.js", JS.read_text(encoding="utf-8")),
                      ("plugin_api.py", API.read_text(encoding="utf-8"))):
        code, _ = scan_js(src, collapse=True) if name.endswith(".js") else (strip_py_strings(src), [])
        for number, line in enumerate(code.splitlines(), 1):
            if len(line) > 120:
                _report(f"{name}:{number}: code line is {len(line)} characters (limit 120) — "
                        "wrap it, one element per line")


def check_style_rules() -> None:
    """Layout rules that no runtime error can surface: no trailing whitespace, no tabs for
    indentation, and single-quoted JavaScript strings (the CSS inside the STYLE template keeps its own
    double quotes — they sit inside a template body and are blanked out of the code projection)."""
    for name, src in (("plugin.js", JS.read_text(encoding="utf-8")),
                      ("plugin_api.py", API.read_text(encoding="utf-8"))):
        for number, line in enumerate(src.splitlines(), 1):
            if line != line.rstrip():
                _report(f"{name}:{number}: trailing whitespace")
            if line.startswith("\t") or "\t " in line[:len(line) - len(line.lstrip())]:
                _report(f"{name}:{number}: indented with a tab")
    code, _ = scan_js(JS.read_text(encoding="utf-8"))
    if '"' in code:
        line = code.count("\n", 0, code.index('"')) + 1
        _report(f"plugin.js:{line}: a double-quoted JavaScript string — use single quotes")


def check_loader_imports() -> None:
    """The plugin source must pass the app's loader: no specifier outside the allow-list."""
    src = JS.read_text(encoding="utf-8")
    bad = {
        m.group(3)
        for m in LOADER_IMPORT_RE.finditer(src)
        if not m.group(3).startswith((".", "/"))
        and not re.match(r"^[a-z][a-z0-9+.-]*:", m.group(3), re.I)
        and m.group(3) not in LOADER_ALLOWED
    }
    for spec in sorted(bad):
        _report(f"plugin.js: the loader would reject this import: {spec!r} (the whole plugin is "
                "dropped). The cause is usually an identifier or React key that ends in `from`")


def bundle_tree() -> dict:
    """The registered bundle, flattened by indentation: {locale: {dotted key: value line}}."""
    src = JS.read_text(encoding="utf-8")
    code, _ = scan_js(src)
    start = code.index("const BUNDLES = {")
    depth = 0
    end = start
    for i in range(code.index("{", start), len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    block = src[start:end + 1]
    tree: dict[str, dict] = {}
    stack: list[tuple[int, str]] = []
    for number, line in enumerate(block.splitlines(), 1):
        m = re.match(r"^(\s*)([A-Za-z_$][\w$]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        indent = len(m.group(1))
        name, rest = m.group(2), m.group(3).strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([entry[1] for entry in stack] + [name])
        if rest.startswith("{"):
            stack.append((indent, name))
            continue
        parts = path.split(".")
        if len(parts) < 2:
            _report(f"plugin.js: bundle entry {path!r} is not inside a locale")
            continue
        tree.setdefault(parts[0], {})[".".join(parts[1:])] = line
    return tree


def check_single_bundle() -> dict:
    """Exactly ONE bundle ('en') is registered, and it reaches ctx.i18n.register."""
    tree = bundle_tree()
    locales = sorted(tree)
    if locales != ["en"]:
        _report(f"plugin.js: exactly one 'en' bundle must be registered, found {locales or 'none'}")
    src = JS.read_text(encoding="utf-8")
    if not re.search(r"i18n[^\n]*register[^\n]*\(\s*BUNDLES\s*\)", src):
        _report("plugin.js: the bundle never reaches `ctx.i18n.register` — the panel would print keys")
    return tree.get("en", {})


def check_panel_keys(table: dict) -> None:
    """Every key the panel asks for resolves; no raw key can reach the screen; no dead entry."""
    src = JS.read_text(encoding="utf-8")
    code, _ = scan_js(src)
    used = set(re.findall(r"\bt\??\.?\(\s*'([^']+)'", src))
    used |= set(re.findall(r"'((?:wa|wd)\.[a-zA-Z0-9_.]+)'", src))
    for key in sorted(used):
        if key not in table:
            _report(f"plugin.js: {key!r} is missing from the bundle — an unresolved key reaches the "
                    "screen as its own name")
    if table:
        for key in sorted(table):
            if not re.search(rf"\b{re.escape(key)}\b", src):
                _report(f"plugin.js: bundle entry {key!r} is never used — remove it or wire it up")
    for m in re.finditer(r"\bt\(([^)]*)\)", code):
        argument = m.group(1).strip()
        if argument.startswith("'") or argument == "key":
            continue
        if re.match(r"^(" + "|".join(AUDITED_KEY_MAPS) + r")\[", argument):
            continue
        line = code.count("\n", 0, m.start()) + 1
        _report(f"plugin.js:{line}: t() is called without a literal key ({argument[:40]!r}) — a "
                "dynamic key cannot be audited (only the `_TX_MAP` lookup may pass one)")


def check_no_language_selection() -> None:
    """No language switch survives: no picker, no `lang` state, no per-language message table."""
    src = JS.read_text(encoding="utf-8")
    code, _ = scan_js(src)
    for pattern, what in LANG_PATTERNS:
        for m in pattern.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            _report(f"plugin.js:{line}: {what} is back ({m.group(0)!r}) — the panel reads the app "
                    "language and nothing else")
    for pattern, what in LANG_PATTERNS:
        for m in pattern.finditer(code):
            line = code.count("\n", 0, m.start()) + 1
            _report(f"plugin.js:{line}: {what} is back ({m.group(0)!r})")
    py_src = API.read_text(encoding="utf-8")
    for pattern, what in LANG_PATTERNS:
        for m in pattern.finditer(py_src):
            line = py_src.count("\n", 0, m.start()) + 1
            _report(f"plugin_api.py:{line}: {what} is back ({m.group(0)!r}) — the backend answers in "
                    "one language behind _tx(...)")


def check_no_auto_pane() -> None:
    """The panel never claims a pane and never opens itself."""
    src = JS.read_text(encoding="utf-8")
    code, _ = scan_js(src)
    for needle, why in (("uncloseable", "the pane could no longer be closed"),
                        ("revealOnPreset", "the panel would reopen on every layout change"),
                        ("revealPane(", "the panel opens itself"),
                        ("paneVisibility(", "the panel drives pane visibility")):
        if needle in code:
            _report(f"plugin.js: {needle!r} is back — {why}")
    for m in re.finditer(r"AREA_PANES|['\"]panes['\"]", src):
        line = src.count("\n", 0, m.start()) + 1
        _report(f"plugin.js:{line}: the panel claims the `panes` area again ({m.group(0)!r}) — "
                "closing that tab disables the whole plugin")
    areas = set(re.findall(r"AREA_[A-Z_]+\s*=\s*'([^']+)'", src))
    if areas and areas != {"routes", "sidebar.nav"}:
        _report(f"plugin.js: the panel must contribute only a page and a sidebar entry: {sorted(areas)}")


def check_jsx_key_form() -> None:
    """`jsx(type, props, key)`: the third argument is the KEY (a literal or a dynamic string), never children.

    Children passed third render an EMPTY element without an error and without a console warning —
    that is how a run row once came out blank while every test on the data still passed.
    """
    src = JS.read_text(encoding="utf-8")
    code, _ = scan_js(src)
    for m in re.finditer(r"\bjsxs?\(", code):
        args = split_args(code, m.end() - 1)
        if len(args) >= 3 and args[2].lstrip()[:1] in ("[", "{"):
            line = code.count("\n", 0, m.start()) + 1
            _report(f"plugin.js:{line}: the third jsx() argument is a literal, not a key "
                    f"({args[2].strip()[:60]!r}) — children belong inside props")


def _arg_spans(code: str, open_paren: int) -> list[tuple[int, int]]:
    """The top-level argument spans of the call whose `(` sits at *open_paren*.

    Spans (not text): the jsx TYPE of a call is a string literal, and `scan_js` blanks string
    bodies, so the type can only be read back from the raw source at the same offsets.
    """
    spans: list[tuple[int, int]] = []
    depth = 0
    start = -1
    for i in range(open_paren, len(code)):
        ch = code[i]
        if ch in "([{":
            depth += 1
            if depth == 1:
                start = i + 1
                continue
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                spans.append((start, i))
                return spans
        elif ch == "," and depth == 1:
            spans.append((start, i))
            start = i + 1
    return spans


def check_no_native_title() -> None:
    """No CONTROL carries a native `title=`: use `Tip` (or `aria-label` for a glyph-only button).

    A native title is unstyled, opens after the OS delay (~500ms) and clashes with the themed
    `Tip` the host uses everywhere — the app's own `no-native-title.test.ts` fails on any button
    that carries one, so a plugin shipping one shows a look the host cannot explain. Every
    element (`'div'`, `'span'`, …) and every control component counts; a component that merely
    takes a `title` PROP for its own content (`EmptyState`, `ErrorState`) does not.
    """
    src = JS.read_text(encoding="utf-8")
    code, _ = scan_js(src)
    for m in re.finditer(r"\bjsxs?\(", code):
        args = _arg_spans(code, m.end() - 1)
        if len(args) < 2:
            continue
        kind = src[args[0][0]:args[0][1]].strip()
        if not (kind[:1].islower() or kind in CONTROL_TYPES):
            continue
        hit = NATIVE_TITLE_RE.search(src[args[1][0]:args[1][1]])
        if hit:
            line = code.count("\n", 0, m.start()) + 1
            _report(f"plugin.js:{line}: a native `title=` is written on {kind} ({hit.group(0)!r}) — "
                    "a tooltip is a `Tip` (a native one is unstyled and delayed) and a glyph-only "
                    "button keeps its `aria-label`")
    for needle in NATIVE_TITLE_WRITES:
        if needle in src:
            _report(f"plugin.js: {needle!r} is back — a native tooltip is unstyled, delayed and "
                    "clashes with the themed `Tip`")


def check_colors() -> None:
    """Colors come from the theme: only `var(--ui-*)` and `color-mix(...)`; no fixed color literal."""
    src = JS.read_text(encoding="utf-8")
    stripped = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    stripped = re.sub(r"//[^\n]*", " ", stripped)
    for m in COLOR_PROP_RE.finditer(stripped):
        if COLOR_LITERAL_RE.search(m.group(1)):
            line = stripped.count("\n", 0, m.start()) + 1
            _report(f"plugin.js:{line}: a fixed color is written ({m.group(0)[:60]!r}) — surfaces, "
                    "borders and text take their color from the theme variables")


def check_two_step_write() -> None:
    """The copy/mirror write is TWO-STEP: the backend refuses, the panel asks, only then force=true."""
    src = JS.read_text(encoding="utf-8")
    for needle, why in (("needs_force", "the panel no longer understands the backend's refusal"),
                        ("wa-confirm", "there is no confirmation surface"),
                        ("save(true)", "there is no confirmed second write"),
                        ("force: Boolean(force)", "the confirm flag does not reach the backend")):
        if needle not in src:
            _report(f"plugin.js: {needle!r} is missing — {why}")
    py_src = API.read_text(encoding="utf-8")
    for needle, why in (("needs_force", "the backend no longer asks for confirmation"),
                        ('(payload or {}).get("force")', "the backend ignores the confirmation")):
        if needle not in py_src:
            _report(f"plugin_api.py: {needle!r} is missing — {why}")


def check_engine_job_definition() -> None:
    """The job definition lives in the ENGINE (`<audit>/jobs.json`) and nowhere in this plugin.

    The panel used to keep `dashboard/job_catalogue.json`, a second copy of the engine's job list. Two
    copies drift: the engine gained a fourth job (Wiki Session Harvest) and the panel went on showing
    three. The panel is a view — it reads the engine's file, and an agent job, which the engine's
    installer creates, is never created by the panel.
    """
    src = API.read_text(encoding="utf-8").split("def _selftest", 1)[0]
    if (HERE.parent / "dashboard" / "job_catalogue.json").exists():
        _report("dashboard/job_catalogue.json is back — a second job catalogue beside the engine's "
                "jobs.json drifts from it (the panel showed three jobs while the engine ran four)")
    if "job_catalogue.json" in src or "JOB_CATALOGUE_PATH" in src:
        _report("plugin_api.py: the plugin reads a job catalogue of its own again — the job definition "
                "is the engine's <audit>/jobs.json")
    if 'ENGINE_JOBS = "jobs.json"' not in src or "_engine_file(ENGINE_JOBS)" not in src:
        _report("plugin_api.py: the job list no longer comes from the engine's jobs.json")
    action = next((node for node in ast.parse(src).body
                   if isinstance(node, ast.FunctionDef) and node.name == '_jobs_act'), None)
    body = ast.get_source_segment(src, action) if action is not None else ""
    lock_at = body.find("with cron._jobs_lock():")
    guards = ("cron.get_job(jid) != rec", "_job_bindings() != binding",
              "_job_facts(rec, cron) != {k: expected[k] for k in _JOB_FACTS}")
    mutators = [body.find(name) for name in ("cron.pause_job(", "cron.resume_job(",
                                              "cron.update_job(", "cron.remove_job(")]
    if (lock_at < 0 or any(body.find(guard) < lock_at for guard in guards)
            or any(at < lock_at or any(at < body.find(guard) for guard in guards) for at in mutators)
            or "cron.create_job(" in body):
        _report("plugin_api.py: a native job change no longer re-reads and compares the reviewed record "
                "inside the cron store lock before it writes (or the panel creates jobs outside the "
                "reviewed engine installation)")


def check_candidate_actions() -> None:
    """Candidates are listed, shown and acted on ONLY through the engine's `wiki_candidates.py`, and
    approving is TWO-STEP.

    An approve writes a source into the wiki's raw/sources and the app then ingests it, which costs
    model usage: one click must not do that. The first call only dry-runs and arms the confirmation, the
    panel asks, and only a second call with `confirm` writes. A reject needs its reason (the engine
    records it to measure the harvest), and a ref is validated before it reaches the script's argv.
    """
    src = API.read_text(encoding="utf-8")
    for needle, why in (('CANDIDATES_SCRIPT = "wiki_candidates.py"', "the candidates no longer go through "
                                                                      "the engine script"),
                        ('elif not body.get("confirm"):', "an approve no longer waits for its confirmation"),
                        ('"needs_confirm": True, "reason": _tx("cand_confirm")',
                         "the first approve no longer arms the confirmation"),
                        ('["approve", ref, "--dry-run"]', "the unconfirmed approve is no longer a dry run"),
                        ('return {**head, "reason": _tx("cand_no_reason")}', "a reject no longer needs a reason")):
        if needle not in src:
            _report(f"plugin_api.py: {needle!r} is missing — {why}")
    if src.count("_CANDIDATE_REF.fullmatch(ref)") < 2:
        _report("plugin_api.py: a candidate ref reaches the engine script without the strict "
                "<run>/<name> check")
    if "shutil" in src.split("def _selftest", 1)[0] or "raw/sources" in src.split("def _selftest", 1)[0] \
            .replace("raw/sources folder", ""):
        _report("plugin_api.py: the backend touches the wiki's files itself — only the engine script "
                "writes a candidate into raw/sources")
    js = JS.read_text(encoding="utf-8")
    for needle, why in (("const act = async (ref, action, confirm = false)",
                         "the first Approve is no longer unconfirmed"),
                        ("onConfirm: () => act(armed.ref, 'approve', true)", "there is no confirmed second approve"),
                        ("api.candAct(ref, action, confirm", "the decision no longer uses the selected ref and confirmation"),
                        ("res?.needs_confirm", "the panel no longer understands the backend's arming"),
                        ("disabled: !rejectable || !why.trim()", "a reject can be sent without a reason"),
                        ("if (confirm && (armed?.ref !== ref || confirmation.current !== armed)) return", "confirmation is not bound to the selected candidate"),
                        ("if (inFlight.current || !canAct(ref, action)", "a stale or duplicate decision can be sent"),
                        ("!now.detail.format_problems.length", "invalid candidate format can be approved")):
        if needle not in js:
            _report(f"plugin.js: {needle!r} is missing — {why}")


def check_layout_queries() -> None:
    """The panel lives in a PANE: its narrow rules must measure the pane, not the window.

    A width `@media` query answers a width the panel may not have — dragging the split narrow in a
    wide window kept the five-column runs grid and clipped the Duration column. `@container` (with
    `container-type: inline-size` on the panel root) is the query that can answer it.
    """
    src = JS.read_text(encoding="utf-8")
    if not re.search(r"\.wa-root\{[^}]*container-type:inline-size", src) \
            or ".pa-root{container-type:inline-size" not in src:
        _report("plugin.js: `container-type:inline-size` is gone — the panel's narrow rules would "
                "measure the WINDOW instead of the pane it lives in")
    if ".pa-c-time{display:none !important}" not in src or "@container (max-width: 360px)" not in src:
        _report("plugin.js: the run log's narrow `@container` blocks are gone — a narrow pane would "
                "keep the wide log grid and clip its columns")
    if "@container (max-width:620px){\n  .wa-job{" not in src:
        _report("plugin.js: the `@container (max-width:620px)` block is gone — the job row would "
                "keep its two-column form in a pane too narrow for it")
    if re.search(r"@media\s*\([^)]*width", src):
        _report("plugin.js: a width `@media` query is back — the panel lives in a pane, so the "
                "window width says nothing about the space it has (use `@container`)")
    if ".wa-job-line{display:flex" not in src or "className: 'wa-job-line'" not in src:
        _report("plugin.js: the job row's name line (`.wa-job-line`, the name with its state badge) "
                "is gone — the badge would drop onto a line of its own and every job row would grow "
                "a line")


def check_scroll_flow() -> None:
    """The panel root must not compress its own rows: every card has to stay reachable.

    `.wa-root` is `display:grid` inside a pane of FIXED height. A grid compresses its `auto` rows to
    fit a definite container, so a pane shorter than the panel made every card overflow its own row,
    `.wa-card{overflow:hidden}` clipped the content inside it, and the root ended up with
    scrollHeight == clientHeight: no scrollbar at all, and the bottom card unreachable.
    `grid-auto-rows:max-content` keeps each row its content's height, which is what turns the root's
    `overflow:auto` into a real scroll. Measured by `tests/scroll_check.cjs` in the app's engine:
    0 defects and 0 unreachable elements at pane heights 760/620/560/430/330/220 px and at 352/660 px
    wide panes (the pre-fix source fails that check with 3 defects).
    """
    src = JS.read_text(encoding="utf-8")
    found = re.search(r"\.wa-root\{([^}]*)\}", src)
    if not found:
        _report("plugin.js: the `.wa-root` rule is gone — the panel has no root to lay out")
        return
    rule = found.group(1)
    if "overflow:auto" not in rule:
        _report("plugin.js: `.wa-root` no longer scrolls (`overflow:auto` is gone) — content taller "
                "than the pane would have nowhere to go")
    if "grid-auto-rows:max-content" not in rule:
        _report("plugin.js: `.wa-root` lost `grid-auto-rows:max-content` — in a pane shorter than the "
                "panel the grid compresses its `auto` rows, every card is clipped by "
                "`.wa-card{overflow:hidden}` and the root reports no overflow at all, so the bottom "
                "card cannot be scrolled to (`tests/scroll_check.cjs` fails on it)")


def check_visual_hierarchy() -> None:
    """No obsolete KPI shell; retained actions keep their kit shape and field chrome.

    Until 2.4.x this rule also pinned the Nexus map (`nx-map`, nodes naming `wa-inspector`, the
    `nx-config` Project disclosure). Metro (2.5.0) removed that composition; `check_removed_composition`
    now forbids it and `check_metro_contract` pins the line that replaced it.
    """
    src = JS.read_text(encoding="utf-8")
    src = src[:src.find(HEALTH_MARK)] if HEALTH_MARK in src else src
    if re.search(r"jsx\(Button, \{[^}]*variant: 'ghost'", src):
        _report("plugin.js: a `ghost` Button is back — secondary actions share ONE secondary shape "
                "(`outline`) beside the one filled primary")
    for needle, message in (
        ("const harvest = usePolling(api.harvestStatus, 60000)", "the source status poll is gone"),
        ("detail: harvest.error", "the source status failure lost its backend error"),
    ):
        if needle not in src:
            _report(f"plugin.js: {message}")
    for gone in (".g-kpis{", ".g-gauge{", ".g-grid{"):
        if gone in src:
            _report(f"plugin.js: obsolete KPI/gauge shell is back: {gone}")
    if "containerClassName: 'desktop-input-chrome wa-filter'" not in src:
        _report("plugin.js: the candidate filter lost its field chrome — the SearchField needs "
                "`containerClassName: 'desktop-input-chrome wa-filter'`")


def check_type_floor() -> None:
    """The panel's own text has a floor, and its chips stay on the kit's own steps.

    A 9.5 px label and 9.6 px card titles survived every gate here: nothing measured a font size, so
    the smallest AND faintest text on the panel was its headings. The floor is the kit's default
    badge step (0.65rem = 10.4 px); anything under 11 px is too small for this panel to call a
    deliberate choice, and `size: 'xs'` (0.6rem = 9.6 px) is the kit's icon-corner step, not a step
    for status, delivery and count chips. Since 2.3.6 the floor is 12 px: the owner reported 10.5 and
    11 px text as unreadable on the panel, and the TYPE table's own steps obey the same floor.
    """
    src = JS.read_text(encoding="utf-8")
    for value in re.findall(r"font-size:([0-9.]+)px", src):
        if float(value) < 12:
            _report(f"plugin.js: a `font-size:{value}px` is under the 12 px floor — on a panel read at"
                    " a glance, nothing below the kit's own default step is a deliberate choice")
    table = re.search(r"^const TYPE = \{([^}]*)\}", src, re.M)
    for name, value in re.findall(r"(\w+): ([0-9.]+)", table.group(1) if table else ""):
        if float(value) < 12:
            _report(f"plugin.js: TYPE.{name} is {value} px, under the 12 px floor")
    if "size: 'xs'" in src:
        _report("plugin.js: a badge is back on the kit's `xs` step (9.6 px) — status, delivery and"
                " count chips belong on the kit's default step")


LABEL_KEYS = ("ok", "invalid", "jobLiveState", "jobPausedState", "verified", "runOk", "runFailed",
              "runDeliveryFailed", "runLate", "runMissed")


def check_label_case() -> None:
    """A status word is a LABEL, not a sentence — the chip and the kv value start with a capital.

    `verified` survived three passes because no rule looked at the CASE of a string: the panel printed
    a lower-case chip beside `Completed` / `Failed` chips on the same screen, which reads as a
    different kind of thing. Prose is exempt (`no job id`, `the entries that keep the watched folder
    current`) — those are sentences, and the bundle keeps them in sentence case.
    """
    src = JS.read_text(encoding="utf-8")
    for key in LABEL_KEYS:
        found = re.search(rf"^\s*{key}: (?:\([^)]*\)\s*=>\s*)?['\"`](.)", src, re.M)
        if found is None:
            _report(f"plugin.js: the status label `wa.{key}` is gone — a status word the panel "
                    "prints has to keep a capital")
        elif not found.group(1).isupper():
            _report(f"plugin.js: `wa.{key}` reads as a sentence, not a label — a status chip or a "
                    "status value is Capitalised (Verified · Live · Registered), because it sits "
                    "beside the kit's own `Completed` / `Failed` chips")


def check_failure_detail() -> None:
    """A failed read keeps the error the backend returned, beside its English sentence.

    Printing one generic sentence threw away the only string a bug report can search for; the caught
    error now travels into the failure card the same way a checker reason does.
    """
    src = JS.read_text(encoding="utf-8")
    for needle in ("detail: auto.error", "detail: jobs.error", "detail: runs.error", "detail: cands.error"):
        if needle not in src:
            _report(f"plugin.js: {needle!r} is missing — a failed read would print the generic "
                    "sentence and drop the error the backend actually returned")


def check_dead_class_names() -> None:
    """A class name with no CSS rule lays out as if it had never been written."""
    src = JS.read_text(encoding="utf-8")
    dead = "wa-msgbox"
    if dead in src:
        _report(f"plugin.js: the class {dead!r} is back — no rule defines it, so whatever it wraps "
                "loses the card treatment and renders as a bare line")


def check_jsx_runtime_import() -> None:
    """The panel builds elements with the runtime jsx helpers, not with a JSX transform."""
    src = JS.read_text(encoding="utf-8")
    if "react/jsx-runtime" not in src:
        _report("plugin.js: `react/jsx-runtime` is not imported — the panel cannot build elements")


def check_reason_mapping(table: dict) -> None:
    """No external check text reaches the screen unmapped, and no raw text is thrown away.

    The checker (`~/.llmwiki-audit/wikiconfig.py`) answers in Turkish. Every reason it produces must
    be read as `txReason(<x>.reason, <x>.reason_source, t)`, mapped through `_TX_MAP` to a sentence
    from the panel's own `en` bundle, and shown next to the raw text (a `Tip` label + a `PanelBlock`
    detail block — never a native `title=`). A bare
    `.reason` is that Turkish wording on an English screen; dropping the raw text loses the one thing
    a bug report needs.
    """
    src = JS.read_text(encoding="utf-8")
    code, _ = scan_js(src)
    if "const _TX_MAP = [" not in code:
        _report("plugin.js: the `_TX_MAP` mapping table is gone — an external check reason would be "
                "printed in the checker's own wording")
    if not re.search(r"\bfunction\s+txReason\s*\(", code):
        _report("plugin.js: `txReason(...)` is gone — the single door an external reason passes")
    for number, line in enumerate(code.splitlines(), 1):
        if re.search(r"\.reason\b", line) and not REASON_CALL_RE.search(line):
            _report(f"plugin.js:{number}: a `.reason` is read outside "
                    "`txReason(<x>.reason, <x>.reason_source, t)` — unmapped external text would "
                    "reach the screen")
    entries = TX_MAP_ENTRY_RE.findall(src)
    if not entries:
        _report("plugin.js: `_TX_MAP` holds no entry — every external reason would fall through to "
                "the neutral label")
    for prefix, key in entries:
        if key not in table:
            _report(f"plugin.js: `_TX_MAP` maps {prefix!r} to {key!r}, which is not in the bundle — "
                    "the panel would print the key itself")
    if "'wa.checkUnrecognized'" not in src:
        _report("plugin.js: the neutral label for an unrecognized reason is gone — an unknown check "
                "reason would be invented into English")
    if "className: 'wa-raw'" not in src:
        _report("plugin.js: the raw check text no longer reaches a tooltip/detail block — it was "
                "replaced instead of shown beside its English reading")
    if not re.search(r"question\s*=\s*msg\?\.raw\b", code):
        _report("plugin.js: `question` no longer unpacks `msg.raw` — the checker's own wording "
                "would be dropped instead of shown beside its English reading")
    if not re.search(r"label:\s*question\b", code):
        _report("plugin.js: the raw check text is not handed to a `Tip` as its label "
                "(`label: question`) — the wording would only be reachable in the detail block")


# ---------------------------------------------------------------------------
# Backend (plugin_api.py)
# ---------------------------------------------------------------------------
def check_undefined_names(path: Path) -> None:
    """Names read inside function bodies must exist in the module, a builtin or an outer scope."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_names = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                module_names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            module_names.add(node.id)

    def bound_in(fn: ast.AST) -> set[str]:
        names: set[str] = set()
        args = getattr(fn, "args", None)
        if args is not None:
            for a in (list(args.args) + list(args.posonlyargs) + list(args.kwonlyargs)
                      + ([args.vararg] if args.vararg else []) + ([args.kwarg] if args.kwarg else [])):
                names.add(a.arg)
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not fn:
                names.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                names.add(node.name)
            elif isinstance(node, ast.Global):
                names.update(node.names)
        return names

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def scope_chain(fn: ast.AST) -> set[str]:
        names = bound_in(fn)
        node = parents.get(fn)
        while node is not None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names |= bound_in(node)
            node = parents.get(node)
        return names

    def enclosing_fn(node: ast.AST) -> ast.AST | None:
        cur = parents.get(node)
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur
            cur = parents.get(cur)
        return None

    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        local = scope_chain(fn)
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and enclosing_fn(node) is fn:
                if node.id not in local and node.id not in module_names:
                    _report(f"{path.name}:{node.lineno} looks like an undefined name: {node.id}")


def explain_table() -> dict:
    src = API.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_EXPLAIN_TEXT":
            table = ast.literal_eval(node.value)
            for key, value in table.items():
                if not isinstance(value, str):
                    _report(f"plugin_api.py: _EXPLAIN_TEXT[{key!r}] is not a plain string — the "
                            "message table must hold exactly one language")
            return table
    _report("plugin_api.py: _EXPLAIN_TEXT not found — the single message table behind _tx is gone")
    return {}


def check_tx_keys(table: dict) -> None:
    """Every `_tx("key")` exists in the table (a missing key prints the key itself)."""
    src = API.read_text(encoding="utf-8")
    used = set(re.findall(r"_tx\(\s*['\"]([^'\"]+)", src))
    for key in sorted(used - set(table)):
        _report(f"plugin_api.py: _tx({key!r}) has no entry in the message table")
    if used and not table:
        _report("plugin_api.py: no message table to check against")


def check_tx_placeholders(src: str) -> None:
    """`_tx("key", a=..., b=...)` passes exactly the placeholders the message asks for.

    Why: a call that forgot `percent_before` made `.format` raise `KeyError`; the endpoint answered
    500 and the page went blank — the failure hit exactly when that message was meant to explain
    things. This catches a missing or extra argument in the source; `_tx` is the second line of defence.
    """
    tree = ast.parse(src)
    book = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_EXPLAIN_TEXT" for t in node.targets):
            try:
                book = ast.literal_eval(node.value)
            except ValueError:
                _report("warning: _EXPLAIN_TEXT is not a literal, placeholder check skipped")
                return
    if not isinstance(book, dict):
        _report("warning: _EXPLAIN_TEXT not found, placeholder check skipped")
        return

    def holders(text: str) -> set[str]:
        if not isinstance(text, str):
            return set()
        return set(re.findall(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})", text))

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_tx"):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        key = node.args[0].value
        passed = {kw.arg for kw in node.keywords if kw.arg}
        if any(kw.arg is None for kw in node.keywords):
            continue
        if key not in book:
            _report(f"line {node.lineno}: _tx({key!r}) has no entry in the message table")
            continue
        for missing in sorted(holders(book[key]) - passed):
            _report(f"line {node.lineno}: _tx({key!r}) needs {missing!r} and does not pass it")
        for extra in sorted(passed - holders(book[key])):
            _report(f"line {node.lineno}: _tx({key!r}) passes {extra!r}, unused by the message")


def check_reason_provenance() -> None:
    """A reason from the checker leaves the API with its raw text AND its provenance, or not at all.

    The panel can only map what it can recognise, so the backend marks every checker payload with
    `reason_source` through `_reason_fields(...)`. A route that forwards the checker's `reason` on its
    own hands the panel a string it must print as English — and it would print Turkish.
    """
    src = API.read_text(encoding="utf-8")
    tree = ast.parse(src)
    span = None
    test_span = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_reason_fields":
            span = (node.lineno, node.end_lineno or node.lineno)
        if isinstance(node, ast.FunctionDef) and node.name == "_selftest":
            test_span = (node.lineno, node.end_lineno or node.lineno)
    if span is None:
        _report("plugin_api.py: `_reason_fields(...)` is gone — a checker reason would reach the "
                "panel with no provenance and could not be mapped")
        return
    if "reason_source" not in src:
        _report("plugin_api.py: `reason_source` is never written — the panel cannot tell the "
                "checker's wording from the backend's own English")
    if not re.search(r"reason_source[\"']?\s*[:=]", src):
        _report("plugin_api.py: the provenance is never set on a payload")
    for number, line in enumerate(src.splitlines(), 1):
        if RAW_REASON_READ_RE.search(line) and not (span[0] <= number <= span[1]):
            _report(f"plugin_api.py:{number}: a checker `reason` is read outside `_reason_fields` — "
                    "the raw text must travel with its provenance")
    fields = (span, test_span)
    sites = sum(1 for number, line in enumerate(src.splitlines(), 1)
                if "_reason_fields(" in line
                and not any(a <= number <= b for a, b in fields if a))
    if sites < REASON_SITES:
        _report(f"plugin_api.py: `_reason_fields(...)` is used at {sites} place(s), expected "
                f"{REASON_SITES} (one per route that forwards a checker payload)")


def check_backend_routes() -> None:
    """The language route is gone; the routes the panel calls still exist."""
    src = API.read_text(encoding="utf-8")
    for gone in ('@router.get("/settings")', '@router.post("/settings")'):
        if gone in src:
            _report(f"plugin_api.py: {gone!r} is back — the panel no longer chooses a language")
    for route in ('@router.get("/automation")', '@router.post("/automation/validate")',
                  '@router.post("/automation/derive")', '@router.get("/automation/candidates")',
                  '@router.post("/automation/scan_root")', '@router.post("/automation/settings")',
                  '@router.get("/runs")', '@router.get("/candidates")', '@router.get("/candidates/show")',
                  '@router.post("/candidates/act")'):
        if route not in src:
            _report(f"plugin_api.py: the route {route!r} is missing — the panel calls it")
    modes = re.findall(r"\?mode=(\w+)\"", src)
    if len(modes) < 5 or any(mode != "ro" for mode in modes):
        _report("plugin_api.py: executions.db is no longer opened read-only")
    if "--selftest" not in src:
        _report("plugin_api.py: the selftest entry point is gone")


BLOCKING_CALLS = {"_run_json", "_run_json_ex", "_config_run", "_jobs_view", "_jobs_act", "_jobs_preview",
                  "_recent_runs", "run", "check_output", "Popen", "call"}


def check_no_blocking_async_route() -> None:
    """A route that runs a subprocess is a plain `def`, never `async def`.

    FastAPI runs a plain route in its threadpool; an `async def` route runs ON the event loop, so a
    `subprocess.run` inside it (timeouts up to 60 s here) freezes the whole dashboard server for every
    other request until the child exits.
    """
    tree = ast.parse(API.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        routed = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                     and isinstance(d.func.value, ast.Name) and d.func.value.id == "router"
                     for d in node.decorator_list)
        if not routed:
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            name = call.func.id if isinstance(call.func, ast.Name) else (
                call.func.attr if isinstance(call.func, ast.Attribute) else "")
            if name in BLOCKING_CALLS:
                _report(f"plugin_api.py:{node.lineno}: the route `{node.name}` is async and calls "
                        f"`{name}` - a blocking subprocess on the event loop freezes the server")
                break


def check_css_vars() -> None:
    """Every `var(--ui-*)` the panel uses must be DEFINED by the app (otherwise it silently styles
    nothing — a misspelled name is an invisible border or surface, not an error)."""
    used = sorted(set(re.findall(r"var\((--ui-[a-zA-Z0-9-]+)", JS.read_text(encoding="utf-8"))))
    if not used:
        return
    app_dir = env.desktop_app_dir()
    app_src = app_dir / "src" if app_dir else Path("<no core checkout: set HERMES_AGENT_DIR>")
    if not app_src.is_dir():
        print(f"note: application source not found ({app_src}) — CSS variable check skipped")
        return
    defined: set[str] = set()
    for path in app_src.rglob("*.css"):
        if path.stat().st_size > 900_000:
            continue
        defined.update(re.findall(r"(--ui-[a-zA-Z0-9-]+)\s*:", path.read_text(encoding="utf-8",
                                                                             errors="ignore")))
    for name in used:
        if name not in defined:
            _report(f"plugin.js: CSS variable {name} is not defined by the app")


def check_version_agreement() -> None:
    """`plugin.yaml` and the backend manifest carry the SAME version number.

    The inventory reads `plugin.yaml`; the plugin card reads `dashboard/manifest.json`. A bump that
    touches only one of them makes the plugin report two versions and the reader cannot tell which one
    is running — the same as having no version at all. Both move in the same change.
    """
    match = re.search(r"^version:\s*(\S+)\s*$", (HERE.parent / "plugin.yaml").read_text(encoding="utf-8"), re.M)
    yaml_version = match.group(1) if match else None
    try:
        manifest = json.loads((HERE.parent / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = None
    manifest_version = manifest.get("version") if isinstance(manifest, dict) else None
    if yaml_version is None:
        _report("plugin.yaml: `version:` is missing — the plugin would report no version")
    if manifest_version is None:
        _report("dashboard/manifest.json: `version` is missing — the card would report none")
    if yaml_version and manifest_version and yaml_version != manifest_version:
        _report(f"version drift: plugin.yaml says {yaml_version} while dashboard/manifest.json says ")
        _report(f"{manifest_version} — bump both in the same change, a plugin that reports two ")
        _report("versions has no version at all")


# ---------------------------------------------------------------------------
# The HEALTH tab (the former Wiki Watchdog panel, merged in 2.0.0)
# ---------------------------------------------------------------------------
# Every rule below comes from the Watchdog panel's own audit and is kept as it was, pointed at the
# merged source. The Health tab owns the part of plugin.js from HEALTH_MARK on; the rules that are
# about ITS design system (one TYPE scale, one MOTION table, one CSS template) read that part only, so
# the Automation tab keeps its own grammar (a literal font-size floor, `outline` secondary actions).
HEALTH_MARK = "const ACT_LANES = 24"
CSS_HOLE_RE = re.compile(r"\$\{[^{}]*\}")
NATIVE_TITLE_PROP_RE = re.compile(r"(?<![A-Za-z0-9_$])title\s*:")
HEALTH_KIT_COMPONENTS = ("Badge", "Button", "ErrorState", "Loader", "PanelBlock", "PanelDetail",
                         "PanelEmpty", "PanelList", "PanelListRow", "PanelMeta", "PanelSectionLabel",
                         "SegmentedControl")
# 2.5.0 dropped the `title` step with the per-view title it sized (contract § Removed).
TYPE_STEPS = ("micro", "caption", "body", "lead", "ring", "figure")
HEALTH_ROUTES = ('@router.get("/health/watchdog")', '@router.post("/health/watchdog/clear")',
                 '@router.get("/health/jobs")', '@router.get("/health/jobs/run")',
                 '@router.post("/health/runs/archive-clear")')
WRITE_ROUTES = {"/automation/validate", "/automation/derive", "/automation/scan_root", "/automation/settings",
                "/jobs/act", "/candidates/act", "/health/watchdog/clear", "/health/runs/archive-clear"}


READ_ONLY_POSTS = {"/jobs/preview"}
STORE_WRITES = ("update_job", "create_job", "remove_job", "pause_job", "resume_job", "save_jobs",
                "trigger_job", "_write_job_map", "_forget_job", "_notify_scheduler")


def check_schedule_save_ink() -> None:
    """`Save schedule` is inked in the primary text token, never in the accent.

    2.0.0 shipped it as `--ui-accent` text on the drawer: 4.22:1, under AA, and the one red contrast
    gate in the schedule preview. The fix inks it `--ui-text-primary` on an accent TINT (7.9:1, held to
    AA as a reading node). Painting the accent back as ink is the regression this rule names.
    """
    src = read(JS)
    rule = re.search(r"\.wa-root \.wa-sched-save\{([^}]*)\}", src)
    if not rule or "color:var(--ui-text-primary)" not in rule.group(1):
        _report("plugin.js: `.wa-sched-save` is no longer inked `--ui-text-primary` — the accent as text on "
                "the drawer measured 4.22:1, under AA")
    if re.search(r"\.wa-sched-save\{[^}]*color:var\(--ui-accent\)", src):
        _report("plugin.js: `.wa-sched-save` is inked with `--ui-accent` again — 4.22:1 on the drawer")
    if "className: 'wa-sched-save'" not in src:
        _report("plugin.js: the schedule Save no longer carries `wa-sched-save` — its ink rule reaches nothing")


def check_preview_read_only() -> None:
    """`POST /jobs/preview` answers a question and changes nothing.

    It is a POST only so the expression travels in a body; the schedule editor calls it on every
    change, so a write hidden in it would rewrite a live job while the user is still choosing. The
    route may only parse the expression and ask the core for the next runs: no store write, no job-map
    write, no scheduler nudge. The selftest proves the same from the outside (the store's bytes are
    unchanged after a preview).
    """
    tree = ast.parse(read(API))
    found = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for name in ("_jobs_preview", "jobs_preview_route"):
        fn = found.get(name)
        if fn is None:
            _report(f"plugin_api.py: `{name}` is gone — the schedule editor has no read-only preview")
            continue
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call):
                continue
            called = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
            if called in STORE_WRITES:
                _report(f"plugin_api.py:{call.lineno}: the schedule preview calls `{called}` — a preview "
                        "must never write the store (the editor asks on every keystroke)")
    if '"compute_next_run"' in read(API) or "cron.compute_next_run(" not in read(API):
        _report("plugin_api.py: the preview no longer asks the core's own `compute_next_run` — a "
                "copied next-run rule drifts from the scheduler that actually fires")


def health_source() -> str:
    """The Health tab's part of plugin.js (from HEALTH_MARK to the end)."""
    src = read(JS)
    at = src.find(HEALTH_MARK)
    if at < 0:
        _report(f"plugin.js: {HEALTH_MARK!r} is gone — the Health tab's section cannot be found")
        return ""
    return src[at:]


def css_source(src: str) -> str:
    """CSS with every `${…}` hole collapsed to `@`: a rule body is matched as the browser resolves it."""
    return CSS_HOLE_RE.sub("@", src)


def read(path: Path) -> str:
    """Source text with line endings normalised: a CRLF file once moved a block out of its slice and
    produced a fake failure. No check here is allowed to depend on the line ending."""
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")


def top_level_title(props: str) -> bool:
    """Is `title:` a key of THIS props object (not of a nested element's props)?

    `jsx('div', { children: jsx(SectionTitle, { title: … }) })` names a COMPONENT prop two levels
    down; only a key sitting directly inside the element's own props is the native attribute.
    """
    depth = 0
    index = 0
    while index < len(props):
        char = props[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 1 and NATIVE_TITLE_PROP_RE.match(props, index):
            return True
        index += 1
    return False


def module_dict(node: ast.Module, name: str) -> dict | None:
    for item in node.body:
        if isinstance(item, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in item.targets):
            try:
                return ast.literal_eval(item.value)
            except ValueError:
                return None
    return None


def check_tip_placement() -> None:
    """The tip layer is fixed-positioned, so its coordinates are viewport ones: a hardcoded clamp puts
    every tip in the same wrong place on a wider panel, and a tip that only ever opens downwards
    spills off the bottom on the lower rows (the user hit both)."""
    src = read(JS)
    if "Math.min(Math.max(tip.x, 8), 640)" in src:
        _report("plugin.js: the tip layer clamps to a hardcoded 640 — on a taller panel every tip "
                "drifts to that column instead of following its element")
    if "window.innerWidth" not in src or "window.innerHeight" not in src:
        _report("plugin.js: the tip layer does not clamp to the real viewport")
    if "'data-side': flip" not in src:
        _report("plugin.js: the tip layer never flips above its element — a tip on a lower row "
                "would open off the bottom of the window")


def check_ring_and_tone() -> None:
    """The ring's label must not wrap (92px, and "26 min ago" broke over two lines and spilled out),
    and the neutral tone must not be the dimmest text token: on the dark track it made the timeline
    look like it had drawn nothing at all."""
    src = read(JS)
    mid = re.search(r"\.pa-ring-mid b\{([^}]*)\}", css_source(src))
    if not mid or "nowrap" not in mid.group(1):
        _report("plugin.js: the ring's label can wrap — it has 92px and long ages spill past the "
                "circle")
    for rule in re.finditer(r'\.pa-tl-(bar|cell)\[data-tone="neutral"\]\{([^}]*)\}',
                            css_source(src)):
        if "--ui-text-quaternary" in rule.group(2):
            _report(f"plugin.js: the neutral {rule.group(1)} uses the dimmest text token, so an "
                    "on-time mark is nearly invisible on the track")


def check_plural_copy() -> None:
    """A `(s)` on screen is a plural the panel declines to write: "3 job(s) · 2 run(s) delivered" reads
    as a machine's guess, and the singular/plural pair was already available (`plural(n, one, many)`).
    """
    src = read(JS)
    for number, line in enumerate(src.splitlines(), 1):
        # Only inside copy: `Number(s)` is a function call, not a plural.
        if ("'" in line or '"' in line or "`" in line) and re.search(r"[A-Za-z]\(\s*s\s*\)", line):
            _report(f"plugin.js:{number}: a `(s)` plural is written — call plural(n, 'job', 'jobs') "
                    "so the sentence agrees with its number")


def check_delta_tone() -> None:
    """The delta's colour states what the move MEANS for that card, not which way the arrow points.

    Measured before this rule: "▲2" on Delivered was painted in the warning colour and a fall in the
    success colour — the arrow already carries the direction, so the colour was spending itself.
    """
    src = read(JS)
    css = css_source(src)
    if re.search(r'\.pa-delta\[data-dir="(?:up|down)"\]', css):
        _report("plugin.js: the delta is coloured by the arrow's direction — colour it by the "
                "goodness of the move (`data-dir=\"good\"` / `\"bad\"`), which the card declares")
    for tone in ("good", "bad"):
        if f'.pa-delta[data-dir="{tone}"]' not in css:
            _report(f"plugin.js: the delta has no `{tone}` state — one direction of every move is "
                    "left uncoloured")
    if "better: '" not in src:
        _report("plugin.js: no KPI card declares which direction is good, so the delta cannot know")


def check_type_scale() -> None:
    """ONE type scale (`TYPE`): every size names a step of it, and no step is dead.

    Measured before this rule: 13 different font sizes on one panel (8.5 · 9 · 9.5 · 10 · 10.5 · 11 ·
    11.5 · 12 · 12.5 · 13 · 15 · 22). A size written at its call site is invisible in a diff and
    obvious on the screen.
    """
    src = health_source()
    code = scan_js(src)[0]
    if "const TYPE =" not in code:
        _report("plugin.js: the TYPE table is gone — the panel is back to sizes written where they "
                "are used")
        return
    for name in TYPE_STEPS:
        if f"{name}:" not in code.split("const TYPE =")[1].split("}")[0]:
            _report(f"plugin.js: TYPE has no `{name}` step")
    for m in re.finditer(r"fontSize:\s*([^,}\n]+)", code):
        value = m.group(1).strip()
        if value.startswith("TYPE."):
            continue
        line = code.count("\n", 0, m.start()) + 1
        _report(f"plugin.js:{line}: fontSize is written at its call site ({value[:40]!r}) — every "
                "size names a step of the TYPE table")
    holes = re.sub(r"\$\{TYPE\.(?:%s)\}px" % "|".join(TYPE_STEPS), "@", src)
    for m in re.finditer(r"font-size:\s*[\d.]+px|font:\s*[\d.\s]*[\d.]+px", holes):
        line = holes.count("\n", 0, m.start()) + 1
        _report(f"plugin.js:{line}: a CSS font size is written literally ({m.group(0)!r}) — it must "
                "come from the TYPE table")
    for name in TYPE_STEPS:
        if f"${{TYPE.{name}}}" not in src and f"fontSize: TYPE.{name}" not in src:
            _report(f"plugin.js: the TYPE step `{name}` is defined and never used")


def check_drawer() -> None:
    """Two things the user felt: the detail panel must not scroll the page when it opens (a bare
    focus() scrolls the log out from under the pointer), and its monospaced run output must wrap —
    paths and JSON keys are long tokens and ran out of the card on the right."""
    src = read(JS)
    if "focus?.({ preventScroll: true })" not in src:
        _report("plugin.js: the drawer focuses itself without `preventScroll`, so opening a row "
                "scrolls the page and the log moves under the pointer")
    raw_rule = re.search(r"\.pa-raw\{([^}]*)\}", css_source(src))
    if not raw_rule or "overflow-wrap" not in raw_rule.group(1):
        _report("plugin.js: the run-output block does not wrap long tokens, so paths and JSON keys "
                "run out of the card")


def check_label_column() -> None:
    """Every per-job row starts its data at ONE label column, so a job name is cut at the same width
    everywhere and the rows line up."""
    src = read(JS)
    if not re.search(r"^const LABEL_W = \d+$", src, re.M):
        _report("plugin.js: the shared label column LABEL_W is not declared")
    for sel in (".pa-act-row", ".pa-act-axis"):
        rule = re.search(re.escape(sel) + r"\{[^\n]*?grid-template-columns:([^;]+);", src)
        if not rule or not rule.group(1).startswith("${LABEL_W}px"):
            _report(f"plugin.js: {sel} does not read the shared label column (${{LABEL_W}}px) — the "
                    "job names are cut at a different width per card")


def check_color_key() -> None:
    """The colour key is one vocabulary: every swatch shares one shape rule, and the key names no tone
    that no chart draws (a lateness tick survived its timeline once)."""
    src = read(JS)
    shared = re.search(r"\.pa-dot,\.pa-ck-dot\{([^}]*)\}", css_source(src))
    if not shared:
        _report("plugin.js: the tone marks have no shared shape rule (.pa-dot,.pa-ck-dot)")
        return
    if "width" not in shared.group(1) or "height" not in shared.group(1):
        _report("plugin.js: the shared mark rule declares no width/height, so the marks are not one "
                "shape")
    if "wd.ckLate" in src or 'data-tone="late"' in css_source(src):
        _report("plugin.js: the colour key names a lateness tone no chart draws")


def check_ui_kit() -> None:
    """The panel builds on the host UI kit: every kit component it names is imported from
    '@hermes/plugin-sdk' AND rendered at least once.

    A kit import that is never rendered (or a hand-rolled button/pill/empty state left beside it) is
    how a migrated surface drifts back into looking like a foreign body in the application — and the
    drift is invisible: the panel still works.
    """
    src = read(JS)
    block = re.search(r"import\s*\{([^}]*)\}\s*from\s*'@hermes/plugin-sdk'", src)
    if not block:
        _report("plugin.js: the '@hermes/plugin-sdk' import is gone — the panel must build on the "
                "host UI kit")
        return
    names = {name.strip() for name in block.group(1).split(",")}
    for name in HEALTH_KIT_COMPONENTS:
        if name not in names:
            _report(f"plugin.js: the kit component {name} is not imported from '@hermes/plugin-sdk' "
                    "— the panel is dropping back to a hand-rolled element")
            continue
        if len(re.findall(rf"\b{name}\b", src)) < 2:
            _report(f"plugin.js: {name} is imported and never rendered — the panel fell back to a "
                    "hand-rolled element")


def check_css_template_colors() -> None:
    """The CSS template takes its colours and shadows from the theme too: a `#fff` tick, an `rgba()`
    shadow or a forced `color-scheme:dark` looked right on the dark theme and wrong on every other."""
    css = css_source(health_source())
    for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|color-scheme\s*:\s*dark", css):
        _report(f"plugin.js: the CSS template writes {m.group(0)!r} — colours, shadows and the colour \
scheme come from the theme (var(--ui-*), var(--shadow-*), var(--dt-*))")
    roots = re.findall(r"(?m)^\.pa-(?:root|chronicle|health)\s*\{([^}]+)\}", css)
    roots += re.findall(r"className:[^\n]*\bpa-root\b[^\n]*\n\s*style:\s*\{([^}]+)\}", health_source())
    if any(re.search(r"(?<![-\w])background(?:-color|Color)?\s*:\s*['\"]?var\(\s*--ui-bg-sidebar\s*\)",
                     root) for root in roots):
        _report("plugin.js: the page paints itself with the sidebar background — a page is a surface "
                "(var(--ui-surface-background))")


def check_wd_kinds(tree: ast.Module, table: dict) -> None:
    """Every finding kind in `_WD_KINDS` has its title, action and description row in the table.

    The description keys are BUILT at runtime (`"wd_what_" + kind`), so only a static walk can see a
    missing one before a user reads the finding.
    """
    kinds = module_dict(tree, "_WD_KINDS")
    if not isinstance(kinds, dict) or not kinds:
        _report("plugin_api.py: _WD_KINDS is gone — the finding classifier has no table to read")
        return
    for kind, entry in kinds.items():
        if not (isinstance(entry, tuple) and len(entry) >= 2):
            _report(f"plugin_api.py: _WD_KINDS[{kind!r}] is not (title, action, tone, tail) ")
            continue
        title_key, action_key = entry[0], entry[1]
        for key in (title_key, action_key, f"wd_what_{kind}"):
            if key not in table:
                _report(f"plugin_api.py: {key!r} (finding kind {kind!r}) has no entry in the message "
                        "table — the panel would print the raw key")


def check_finding_mapping() -> None:
    """Every finding the panel prints is the ENGLISH MAPPING of an external checker line, and the
    checker's own line is kept beside it: the raw text is never swapped in for the panel's sentence
    and never quietly dropped.

    Three failures that leave no trace on screen:
      * an external (Turkish) line printed straight into the card body — the panel would present the
        checker's machine text as if it were its own English sentence;
      * a kind the backend can emit with NO row in the panel's mapping map — that class would reach
        the screen unmapped and nothing would say so;
      * the mapping never applied at all (a card without its English counterpart).
    The raw line may still be printed in the tooltip and in the raw output block: there it is
    labelled DATA, and the run body is the user's record.
    """
    src = health_source()
    code = scan_js(src)[0]
    for m in re.finditer(r"children:\s*[^\n,]*\b[A-Za-z_$][\w$]*\.(?:detail|raw)\b", code):
        line = code.count("\n", 0, m.start()) + 1
        _report(f"plugin.js:{line}: an external finding line is printed straight into the panel "
                f"({m.group(0).strip()[:60]!r}) — the checker's text is DATA: it goes through the "
                "English mapping and stays beside it as the labelled 'as written' line, it is never "
                "printed as the panel's own sentence")
    finding_cards = re.findall(r"jsx\('p',\s*\{\s*className:\s*'pa-drawer-txt',"
                               r"\s*children:\s*(.*?)\s*\},\s*'mapped'\)", src)
    if not finding_cards or any(not re.match(r"findingEnglish\(", card) for card in finding_cards):
        _report("plugin.js: the English finding mapping is never applied — a checker line would "
                "reach the screen without its English counterpart")
    block = re.search(r"const FINDING_MAP = \{(.*?)\n\}", src, re.S)
    if not block:
        _report("plugin.js: FINDING_MAP is gone — the finding kinds have no English mapping table")
        return
    mapped = dict(re.findall(r"([A-Za-z_][\w]*)\s*:\s*'(wd\.[A-Za-z0-9_.]+)'", block.group(1)))
    kinds = module_dict(ast.parse(read(API)), "_WD_KINDS") or {}
    if not kinds:
        _report("plugin_api.py: _WD_KINDS is gone — the mapped classes cannot be checked")
        return
    for kind in sorted(kinds):
        if kind not in mapped:
            _report(f"plugin.js: the backend can emit a {kind!r} finding and FINDING_MAP has no row "
                    "for it — that class would reach the screen without an English sentence")
    for kind in sorted(set(mapped) - set(kinds)):
        _report(f"plugin.js: FINDING_MAP maps {kind!r}, which the backend never emits — a stale row")
    # The Metro alert names each finding with a short phrase (FINDING_SHORT); it must cover the same kinds,
    # or a class would reach the alert bar as 'an unrecognized problem'.
    short = re.search(r"const FINDING_SHORT = \{(.*?)\n\}", src, re.S)
    short_kinds = set(re.findall(r"([A-Za-z_][\w]*)\s*:\s*'wa\.metroShort\.", short.group(1))) if short else set()
    if set(mapped) != short_kinds:
        _report("plugin.js: FINDING_SHORT does not name the same finding kinds as FINDING_MAP "
                f"(missing {sorted(set(mapped) - short_kinds)}, extra {sorted(short_kinds - set(mapped))}) — "
                "the alert bar would call a known problem 'an unrecognized problem'")


STYLE_BLOCKS = ("STYLE", "SHELL_STYLE", "WD_STYLE")


def style_blocks() -> list[tuple[str, str]]:
    """The panel's three stylesheets (Nexus and Folio, the shell, Chronicle and Health) by name."""
    js = read(JS)
    out = []
    for name in STYLE_BLOCKS:
        parts = js.split(f"const {name} = `", 1)
        if len(parts) != 2:
            _report(f"plugin.js: the {name} block is gone — its motion rules cannot be read")
            continue
        out.append((name, parts[1].split("`", 1)[0]))
    return out


def check_motion_table() -> None:
    """Every transition and animation reads its job from MOTION, and every job is used.

    The durations and curves used to be written at each site — two of them carried over from the
    Pending Approvals panel verbatim (`.34s`, `cubic-bezier(.2,.7,.3,1)`), so the panel's feel was
    edited by hunting for numbers. Until 2.3.8 the rule covered only Chronicle and Health: Nexus
    kept its own hand-timed entry (sections, wires, nodes arriving for 1.6 s) while Chronicle
    appeared at once, and the owner saw four views that "feed from different places". All three
    stylesheets are read now. A hand-written duration and a job nothing uses are both red here.
    """
    js = read(JS)
    for name, style in style_blocks():
        for number, line in enumerate(style.splitlines(), 1):
            if "transition:none" in line or "animation:none" in line:
                continue
            for prop, marker in (("transition:", "move("), ("animation:", "MOTION.")):
                if prop not in line or marker in line:
                    continue
                _report(f"plugin.js: a {prop[:-1]} is written by hand ({name} line {number}) — its job "
                        "belongs in MOTION, so the feel lives in one place")
    jobs = set(re.findall(r"^\s{2}(\w+): \{ ms:", js, re.M))
    if not jobs:
        _report("plugin.js: the MOTION table is gone — no job can be looked up")
        return
    for job in sorted(jobs):
        if (f"move('{job}'" not in js and f"instantMove('{job}'" not in js
                and f"MOTION.{job}." not in js):
            _report(f"plugin.js: the MOTION job {job!r} is never used — remove it or wire it up")


LIVE_HIDDEN = (".wa-shell [aria-live]:empty{position:absolute;width:1px;height:1px;overflow:hidden;"
               "clip-path:inset(50%);white-space:nowrap}")


def check_live_regions_take_no_room() -> None:
    """An empty live region leaves the layout until it has something to say.

    A screen-reader live region has to exist before its message arrives, so the panel keeps an empty
    `aria-live` box in Folio's review desk and in the Nexus engine and schedule cards. In a grid that
    empty box is still a row, and the row gap around it showed: Folio's notice band sat 36 px above
    its card where every other gap is 24 px, and the engine card ended 8 px lower than it should.
    The shell takes an empty live region out of the flow while keeping it readable; the rule leaves
    as soon as a message fills it.
    """
    if LIVE_HIDDEN not in read(JS):
        _report("plugin.js: an empty aria-live region takes a grid row again — the shell rule that takes "
                "it out of the flow until a message arrives is gone")


def check_motion_reduced() -> None:
    """Nothing moves for a reader who asked for less motion.

    Every selector a stylesheet gives a transition or an animation must also appear inside a
    `@media (prefers-reduced-motion: reduce)` block of the same stylesheet, and the one transition
    that lives in JS (an INLINE style no media query can reach) must go through `instantMove`. The
    caret is the case that proved why this rule exists: it kept turning while reduced motion was on.
    """
    js = read(JS)
    for name, style in style_blocks():
        reduced = ""
        for chunk in style.split("@media (prefers-reduced-motion: reduce)")[1:]:
            depth = 0
            collected: list[str] = []
            for char in chunk:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth <= 0:
                        break
                collected.append(char)
            reduced += " " + "".join(collected)
        head = ""
        for line in style.splitlines():
            for index, char in enumerate(line):
                if char == "{" and (index == 0 or line[index - 1] != "$"):
                    head = line[:index].strip()
                    break
            if line.strip() == "}":
                head = ""
            moving = (("transition:" in line and "move(" in line)
                      or ("animation:" in line and "MOTION." in line))
            if not moving:
                continue
            parts, depth, start = [], 0, 0
            for index, char in enumerate(head):
                depth += char == "("
                depth -= char == ")"
                if char == "," and depth == 0:
                    parts.append(head[start:index])
                    start = index + 1
            parts.append(head[start:])
            for selector in [part.strip() for part in parts if part.strip()]:
                if selector.startswith("@"):
                    continue
                if not re.search(re.escape(selector) + r"(?![\w-])", reduced):
                    _report(f"plugin.js: {selector} moves ({name}) but is not switched off under "
                            "prefers-reduced-motion")
                    break
    flat = " ".join(js.split())
    exact = "const instantMove = (job, props) => (prefersReduced() ? 'none' : move(job, props))"
    if exact not in flat:
        _report("plugin.js: an inline transition no longer goes through instantMove(<job>, <props>) "
                "asking prefersReduced — an inline style cannot be reached by a media query, so "
                "reduced motion would be ignored")
    if "usePluginI18n(PLUGIN_ID)" not in js.replace("usePluginI18n\n", ""):
        _report("plugin.js: usePluginI18n is never called — the React door to the app's i18n is gone")
    if "prefersReduced" not in js:
        _report("plugin.js: prefersReduced is gone — the JS motion path cannot be switched off")


NATIVE_TITLE_ATTR_RE = re.compile(r"\btitle\s*=\s*['\"]")


def check_no_native_title_dom() -> None:
    """No local `title=` attribute: the operating system draws that box, and it does not follow the
    theme. The application bans it on every button and the panel answers to the same rule.

    Two shapes, because the JSX runtime hides the second one: the HTML spelling (`title="…"`) and a
    `title` PROP on a DOM element — `jsx('span', { title: … })`. A component's own `title` PROP is a
    different thing entirely and stays legal: `jsx(SectionTitle, { title: … })` names a React prop,
    while a STRING tag (`jsx('span', …)`) is a real DOM element, where `title` is the OS box.
    """
    src = read(JS)
    for m in NATIVE_TITLE_ATTR_RE.finditer(src):
        line = src.count("\n", 0, m.start()) + 1
        _report(f"plugin.js:{line}: a native `title=` attribute is written — that box belongs to the "
                "operating system: it ignores the theme and opens after ~500 ms. The themed tip "
                "(`Tip`) plus an `aria-label` is the way to label a control here")
    code = scan_js(src)[0]
    for m in re.finditer(r"\bjsxs?\(", code):
        args = split_args(code, m.end() - 1)
        if len(args) < 2:
            continue
        tag = args[0].strip()
        if not re.fullmatch(r"'[^']*'", tag):
            continue
        if top_level_title(args[1]):
            line = code.count("\n", 0, m.start()) + 1
            _report(f"plugin.js:{line}: a native title is passed to the DOM element {tag} — the "
                    "operating system draws that box and it does not follow the theme; label the "
                    "control with `aria-label` and the themed tip (`Tip`)")


def check_health_text_table() -> None:
    """ONE English message table sits behind `_tx(...)`; the watchdog rows are plain strings too."""
    table = module_dict(ast.parse(read(API)), "_EXPLAIN_TEXT") or {}
    for key, value in table.items():
        if key.startswith(("wd_", "jb_")) and not isinstance(value, str):
            _report(f"plugin_api.py: _TEXT[{key!r}] is not a plain string — the table holds exactly one language")
    if "raise SystemExit(_selftest())" not in read(API):
        _report("plugin_api.py: the selftest entry point is gone — the backend gate would silently stop running")


METRO_KEYS = ("read-failed", "engine", "harvest-failed", "job-broken", "drafts", "problems", "paused",
              "running", "good")
METRO_ATTRS = ("'data-wa-nav'", "'data-wa-station'", "'data-wa-line'", "'data-alert'", "'data-tone'",
               "'data-for'", "'data-dir'", "'data-state'", "'aria-pressed'")
METRO_CLASSES = ("wa-metro-map", "wa-metro-wires", "wa-metro-bar", "wa-metro-detail", "wa-metro-skeleton")
METRO_COPY = ("Wiki line", "Good service on the whole line", "Ask Hermes to fix these",
              "The chat box did not open. Start a new chat, then press again.", "Your review", "History", "Settings",
              "Engine update ready")
# (pattern, what came back). The four-tab composition was removed in 2.5.0 (Docs/metro-contract.md
# § Removed); each of these is how it would crawl back.
METRO_REMOVED = (
    (r"\bTAB_IDS\b", "TAB_IDS"),
    (r"\bTabsTrigger\b|\bTabsList\b|\bjsxs?\(Tabs\b|(?<![\w.])Tabs,", "the kit Tabs strip"),
    (r"role:\s*'tab(?:list|panel)?'", "a tab role"),
    (r"\bNexus\b|['. ]nx-[a-z]", "the Nexus map"),
    (r"\bHeartbeatStrip\b|['. ]wa-hb-", "the heartbeat strip"),
    (r"\b(?:AutomationTab|ChronicleTab|FolioTab|HealthTab)\b", "a per-tab view"),
    (r"\bsetTab\(|\bopenRunLog\b|view === 'chronicle'", "tab navigation"),
    (r"['. ]nx-queue|\bLowerQueue\b|\bReviewQueue\b", "the Chronicle lower review queue"),
    (r"className: 'wa-run'|className: 'wa-runs-head'|\.wa-runs-head,\.wa-run\{", "the second run list"),
)


def check_removed_composition() -> None:
    """The four tabs, Nexus, the heartbeat strip and the lower review queue stay removed.

    2.3.x had four tabs (Nexus, Chronicle, Folio, Health) and no single answer to "does anything need
    me?". The owner rejected it; 2.5.0 is one Metro view. These names are how the old shape would come
    back, so any of them is red — in code, and as a view name on screen through the bundle.
    """
    src = read(JS)
    code = scan_js(src)[0]
    for pattern, what in METRO_REMOVED:
        m = re.search(pattern, code) or re.search(pattern, src)
        if m:
            line = src.count("\n", 0, m.start()) + 1 if re.search(pattern, src) else "?"
            _report(f"plugin.js:{line}: {what} is back ({m.group(0).strip()!r}) — the four-tab composition "
                    "was removed in 2.5.0; the panel is one Metro view (Docs/metro-contract.md § Removed)")
    block = re.search(r"^const BUNDLES = \{(.*?)^\}", src, re.S | re.M)
    for word in ("Nexus", "Chronicle", "Folio"):
        if block and re.search(rf"'[^'\n]*\b{word}\b[^'\n]*'", block.group(1)):
            _report(f"plugin.js: the bundle names the removed view {word!r} — the panel is one Metro view")


def check_metro_contract() -> None:
    """The Metro DOM contract the gates key on, the alert priority keys and the insert-only composer.

    `tests/render_metro.mjs` proves the behaviour; this rule keeps the vocabulary those checks select
    on, so a rename cannot silently turn every behavioural check into a missing-element skip.
    """
    src = read(JS)
    if not re.search(r"\.wa-metro\s*\{[^}]*container-type:\s*inline-size", src):
        _report("plugin.js: `.wa-metro{...container-type:inline-size}` is gone — the Metro root is the query "
                "container the narrow (vertical) line answers")
    for attr in METRO_ATTRS:
        if attr not in src:
            _report(f"plugin.js: the Metro attribute {attr} is missing — the DOM contract keys on it")
    for cls in METRO_CLASSES:
        if not re.search(rf"[' .]{cls}(?![\w-])", src):
            _report(f"plugin.js: the Metro class `{cls}` is missing — the DOM contract keys on it")
    for key in METRO_KEYS:
        if f"'{key}'" not in src:
            _report(f"plugin.js: the alert priority key '{key}' is missing — every contract state needs its key")
    for words in METRO_COPY:
        if f"'{words}'" not in src:
            _report(f"plugin.js: the Metro copy {words!r} is missing from the bundle")
    if "ResizeObserver" not in src or "getBoundingClientRect" not in src:
        _report("plugin.js: the line's segments are no longer computed from layout (ResizeObserver + "
                "getBoundingClientRect) — hand-typed segments drift from their stops")
    if (not re.search(r"composer\.insertText\(address, text, \{ mode: 'block' \}\)", src)
            or "put('new')" not in src or not re.search(r"host\.newChat\(\)", src)):
        _report("plugin.js: `Ask Hermes to fix these` no longer opens a new chat (host.newChat()) and inserts into "
                "it with host.composer.insertText('new', text, { mode: 'block' }) — the full-page panel has no chat "
                "box of its own")
    m = re.search(r"composer\??\.(?:submit|setDraft|send)\b", src)
    if m:
        _report(f"plugin.js: the panel calls {m.group(0)!r} — the request is inserted into the composer and "
                "never sent or replaced; the owner presses send")


def check_retired_finding() -> None:
    """`not_indexed` is a RETIRED check: still parsed (old alerts.log history), never presented as live.

    The engine's watchdog stopped emitting "index'te hiç görünmeyen sayfa (N)" once LLM Wiki v0.6.12
    made index.md a bounded Recently Updated list of 200 entries. The line lives on in old history, so
    the parser keeps recognising it — and labels it as retired, in a neutral tone, never as a warning
    with an action.
    """
    api = read(API)
    kinds = module_dict(ast.parse(api), "_WD_KINDS") or {}
    row = kinds.get("not_indexed")
    if not row:
        _report("plugin_api.py: the not_indexed class is gone — old alerts.log history would read as "
                "unrecognised lines")
    elif row[2] != "neutral" or row[3] is not False:
        _report("plugin_api.py: not_indexed is presented as a live check again (it must be neutral, with "
                "no action) — the engine retired it")
    if '_WD_RETIRED = frozenset({"not_indexed"})' not in api or '"retired": kind in _WD_RETIRED' not in api:
        _report("plugin_api.py: a finding no longer says it comes from a retired check")
    if "Retired check:" not in read(JS):
        _report("plugin.js: the not_indexed sentence no longer says it is a retired check")


def check_health_routes() -> None:
    """The Health routes live under /health/, READ-ONLY is intact, and the two writes keep their order.

    The Watchdog panel's routes (/watchdog, /jobs, /jobs/run, /runs/archive-clear) moved under
    /health/ so they cannot collide with Automation's own /jobs. Only the listed writes exist; the
    archive-then-clear is archive → read back → match → delete in one transaction, never touching a
    running or claimed run, and an archive name is never reused; the alerts.log clear is confirm →
    archive → verify → remove only the archived prefix, rewritten atomically.
    """
    src = read(API)
    for route in HEALTH_ROUTES:
        if route not in src:
            _report(f"plugin_api.py: the route {route!r} is missing — the Health tab calls it")
    for old in ('@router.get("/watchdog")', '@router.post("/watchdog/clear")', '@router.get("/jobs/run")',
                '@router.post("/runs/archive-clear")'):
        if old in src:
            _report(f"plugin_api.py: {old!r} is back outside /health/ — it collides with the Automation "
                    "routes")
    posts = sorted(set(re.findall(r"@router\.(?:post|put|patch|delete)\(\"([^\"]+)\"", src)))
    for path in posts:
        if path not in WRITE_ROUTES | READ_ONLY_POSTS:
            _report(f"plugin_api.py: a write route came back: {path!r} — every write is listed and justified")
    wrote = src.find("path.write_text(")
    readback = src.find("back = json.loads(path.read_text(")
    matched = src.find("if archived_ids != ")
    deleted = src.find("delete from executions where id in")
    rolled = src.find("w.rollback()")
    if min(wrote, readback, matched, deleted, rolled) < 0 or not (wrote < readback < matched < deleted):
        _report("plugin_api.py: the archive-then-clear order is broken — the archive must be written, "
                "read back and matched BEFORE anything is deleted")
    if "begin immediate" not in src:
        _report("plugin_api.py: the run-store removal is not one transaction")
    if "status not in ('running', 'claimed')" not in src:
        _report("plugin_api.py: the run-store removal can delete a running or claimed run the scheduler "
                "still owns")
    if not re.search(r"^MAX_RUNS = 3000$", src, re.M):
        _report("plugin_api.py: the 3000-key cap on one archive-clear is gone")
    stamps = re.findall(r"strftime\(\"(%Y%m%d-[^\"]*)\"\)", src)
    if not stamps or any("%f" not in stamp for stamp in stamps) or "def _fresh_path(" not in src \
            or "while path.exists()" not in src:
        _report("plugin_api.py: an archive name is not unique — two clears in one second would "
                "overwrite an archive whose records are already gone")
    if '"backups" / "wiki-watchdog"' not in src:
        _report("plugin_api.py: the archive folder is no longer <HERMES_HOME>/backups/wiki-watchdog/ — "
                "the archives written before 2.0.0 would be split from the new ones")
    start = src.find('@router.post("/health/watchdog/clear")')
    route = src[start:src.find("@router.", start + 1)] if start >= 0 else ""
    confirm = route.find('.get("confirm") is not True')
    archived = route.find("path.write_bytes(original)")
    verified = route.find("if copied != original")
    prefixed = route.find("if not current.startswith(copied)")
    emptied = route.find("os.replace(tmp, log)")
    if min(confirm, archived, verified, prefixed, emptied) < 0 or not (
            confirm < archived < verified < prefixed < emptied):
        _report("plugin_api.py: the alerts.log clear is not confirm-then-archive-first — the log must be "
                "copied to the backups, read back and matched BEFORE it is emptied, and only on an "
                "explicit confirm")
    whole = re.search(r"\blog\.(write_text|write_bytes|open)\(", route)
    if whole or "rest = current[len(copied):]" not in route:
        _report("plugin_api.py: the alerts.log clear truncates the whole log — it must remove only the "
                "archived bytes and keep what the watchdog appended after the read")
    if not isinstance(module_dict(ast.parse(src), "_JB_TEXT"), dict):
        _report("plugin_api.py: _JB_TEXT is gone — the status/delivery/body labels come from the backend "
                "and must not be re-invented in the panel")


def check_wiki_map() -> None:
    """The sphere (2.11.0) reads `GET /wiki/map` through the engine's own graph rule, its read never
    raises the alert bar, and its marks stay reachable: the canvas is an image with a label and each
    missing page is a pressable button."""
    api = read(API)
    js = read(JS)
    if '@router.get("/wiki/map")' not in api:
        _report("plugin_api.py: the route '/wiki/map' is missing — the sphere calls it")
    if '"app_graph_isolated.py"' not in api or "_graph_rule(paths.engine_dir)" not in api:
        _report("plugin_api.py: /wiki/map no longer reads the engine's graph rule (app_graph_isolated.py) — "
                "a second link rule would disagree with the app")
    start = js.find("function metroFailures(")
    body = js[start:js.find("\nfunction ", start + 1)] if start >= 0 else ""
    if not body or re.search(r"\bmap\b", body):
        _report("plugin.js: the sphere's read reaches metroFailures — a failed /wiki/map would raise the "
                "alert bar instead of staying inside its card")
    if "className: 'wa-globe-canvas', ref: canvasRef, role: 'img'" not in js or "t('wa.globeAria'" not in js:
        _report("plugin.js: the sphere's canvas is no longer an image with a label")
    if "className: 'wa-globe-miss', 'aria-pressed'" not in js:
        _report("plugin.js: a missing page is no longer a pressable button with aria-pressed")


def main() -> int:
    check_no_comments()
    check_line_length()
    check_style_rules()
    check_version_agreement()
    check_loader_imports()
    table = check_single_bundle()
    check_panel_keys(table)
    check_no_language_selection()
    check_no_auto_pane()
    check_jsx_key_form()
    check_no_native_title()
    check_colors()
    check_two_step_write()
    check_engine_job_definition()
    check_candidate_actions()
    check_layout_queries()
    check_scroll_flow()
    check_visual_hierarchy()
    check_type_floor()
    check_label_case()
    check_failure_detail()
    check_dead_class_names()
    check_jsx_runtime_import()
    check_reason_mapping(table)
    check_undefined_names(API)
    messages = explain_table()
    check_tx_keys(messages)
    check_tx_placeholders(API.read_text(encoding="utf-8"))
    check_reason_provenance()
    check_backend_routes()
    check_no_blocking_async_route()
    check_css_vars()
    check_removed_composition()
    check_metro_contract()
    check_wiki_map()
    check_no_native_title_dom()
    check_health_text_table()
    check_retired_finding()
    check_health_routes()
    check_preview_read_only()
    check_schedule_save_ink()
    check_tip_placement()
    check_ring_and_tone()
    check_plural_copy()
    check_delta_tone()
    check_type_scale()
    check_drawer()
    check_label_column()
    check_color_key()
    check_ui_kit()
    check_css_template_colors()
    check_wd_kinds(ast.parse(read(API)), messages)
    check_finding_mapping()
    check_motion_table()
    check_motion_reduced()
    check_live_regions_take_no_room()
    release_gate.check(_report)
    if problems:
        print("AUDIT: problems found")
        for p in problems:
            print("  -", p)
        return 1
    print("AUDIT clean — one 'en' bundle reaching ctx.i18n.register, every t() key resolves, no "
          "language switch left, no raw key on screen, no comment or docstring, no trailing "
          "whitespace or tab indent, single-quoted strings, loader imports allowed, jsx key form "
          "right, no pane claim, no native title= on a control, theme colors only, two-step write "
          "intact, _tx placeholders exact, every external check reason mapped (English on screen, "
          "raw text kept beside it), checker reasons carrying their provenance, no undefined name, "
          "pane-width layout through @container, every failed read keeping the backend's own error, "
          "no class without a rule, every font size above the floor, every status chip "
          "capitalised, the panel root keeping its rows and scrolling to its last card, one primary with "
          "one secondary shape, ONE Metro view (no tabs, no Nexus, no heartbeat strip, no lower queue) with its "
          "DOM contract, priority keys and an insert-only composer, "
          "source status polled with backend errors retained, a real filter field, "
          "no async route running a subprocess, and ONE "
          "version "
          "sits in plugin.yaml and the dashboard manifest; the job list is the engine's jobs.json with no "
          "catalogue of its own, and a candidate is approved in two steps through the engine script only")
    return 0


if __name__ == "__main__":
    sys.exit(main())

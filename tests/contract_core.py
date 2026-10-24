"""Core contract: every name and keyword the backend takes from `cron.jobs` / `cron.scheduler` exists.

Why: the backend imports the cron store lazily and catches the failure, so a renamed function or a
dropped keyword in the core does not break the plugin's import — it turns into a runtime error that
the panel shows as "the action failed" long after the core update. This gate reads the core's own
source with `ast` (it never imports it, so it also runs in CI against a sparse core checkout) and
checks the USES the backend makes against the DEFINITIONS the core ships.

Running:
  python contract_core.py             exit 0 = every use resolves; 1 = a drift, named
  python contract_core.py --selftest  proves the gate can fail: a renamed function, a dropped keyword
                                      and a missing module are each injected into a copy of the core
                                      signatures and must each be reported
Without a core checkout (HERMES_AGENT_DIR / <HERMES_HOME>/hermes-agent) it says so and exits 2.
"""
from __future__ import annotations

import ast
import copy
import sys
from pathlib import Path

import env

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "dashboard" / "plugin_api.py"

# name -> (module, positional args used, keywords used). Read off plugin_api.py; the gate re-derives
# the call sites from the backend below and fails when this table stops describing them.
USES: dict[str, tuple[str, int, tuple[str, ...]]] = {
    "get_job": ("cron.jobs", 1, ()),
    "use_cron_store": ("cron.jobs", 1, ()),
    "effective_job_state": ("cron.jobs", 1, ()),
    "parse_schedule": ("cron.jobs", 1, ()),
    "compute_next_run": ("cron.jobs", 2, ()),
    "update_job": ("cron.jobs", 2, ()),
    "_jobs_lock": ("cron.jobs", 0, ()),
    "remove_job": ("cron.jobs", 1, ()),
    "pause_job": ("cron.jobs", 1, ("reason",)),
    "resume_job": ("cron.jobs", 1, ()),
    "_notify_provider_jobs_changed": ("cron.scheduler", 0, ()),
}


def backend_calls() -> dict[str, tuple[int, set[str]]]:
    """Every `cron.<name>(...)` call and every `from cron.scheduler import <name>` in the backend."""
    tree = ast.parse(BACKEND.read_text(encoding="utf-8"))
    found: dict[str, tuple[int, set[str]]] = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "cron"):
            n, kws = found.get(node.func.attr, (0, set()))
            found[node.func.attr] = (max(n, len(node.args)), kws | {k.arg for k in node.keywords if k.arg})
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("cron."):
            for alias in node.names:
                found.setdefault(alias.name, (0, set()))
    return found


def core_signatures(core: Path) -> dict[str, dict[str, ast.arguments]]:
    out: dict[str, dict[str, ast.arguments]] = {}
    for module in sorted({m for m, _, _ in USES.values()}):
        path = core.joinpath(*module.split(".")).with_suffix(".py")
        if not path.is_file():
            out[module] = {}
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        out[module] = {n.name: n.args for n in tree.body if isinstance(n, ast.FunctionDef)}
    return out


def check(sigs: dict[str, dict[str, ast.arguments]]) -> list[str]:
    problems: list[str] = []
    calls = backend_calls()
    for name in sorted(set(calls) - set(USES)):
        problems.append(f"the backend calls cron `{name}` but USES does not describe it — add it here")
    for name, (n_used, kws_used) in calls.items():
        if name in USES:
            _, n_decl, kws_decl = USES[name]
            if n_used > n_decl or not kws_used <= set(kws_decl):
                problems.append(f"USES is stale for `{name}`: the backend passes {n_used} positional and "
                                f"{sorted(kws_used)} — update the table")
    for name, (module, n_pos, kws) in USES.items():
        defs = sigs.get(module)
        if not defs:
            problems.append(f"core module `{module}` is missing — the backend's import would fail")
            continue
        args = defs.get(name)
        if args is None:
            problems.append(f"core `{module}.{name}` no longer exists — the backend would fail at run time")
            continue
        positional = [a.arg for a in args.posonlyargs + args.args]
        if n_pos > len(positional) and args.vararg is None:
            problems.append(f"core `{module}.{name}` takes {len(positional)} positional argument(s); the "
                            f"backend passes {n_pos}")
        accepted = {a.arg for a in args.args + args.kwonlyargs}
        for kw in kws:
            if kw not in accepted and args.kwarg is None:
                problems.append(f"core `{module}.{name}` has no `{kw}` parameter; the backend passes it")
    return problems


def selftest(sigs: dict[str, dict[str, ast.arguments]]) -> int:
    cases = []
    renamed = copy.deepcopy(sigs)
    renamed["cron.jobs"]["_jobs_lock_v2"] = renamed["cron.jobs"].pop("_jobs_lock")
    cases.append(("renamed function", renamed, "_jobs_lock` no longer exists"))
    dropped = copy.deepcopy(sigs)
    args = dropped["cron.jobs"]["pause_job"]
    args.args = [a for a in args.args if a.arg != "reason"]
    args.kwonlyargs = [a for a in args.kwonlyargs if a.arg != "reason"]
    args.kwarg = None
    cases.append(("dropped keyword", dropped, "no `reason` parameter"))
    gone = copy.deepcopy(sigs)
    gone["cron.scheduler"] = {}
    cases.append(("missing module", gone, "`cron.scheduler` is missing"))
    failed = 0
    for label, mutated, fragment in cases:
        hit = any(fragment in p for p in check(mutated))
        print(f"{'OK  ' if hit else 'FAIL'} {label}  ->  {'reported' if hit else 'NOT reported'}")
        failed += not hit
    clean = check(sigs)
    print(f"{'OK  ' if not clean else 'FAIL'} unmodified core  ->  {len(clean)} problem(s)")
    return 1 if failed or clean else 0


def main() -> int:
    core = env.core_dir()
    if core is None or not (core / "cron" / "jobs.py").is_file():
        print("core checkout not found (set HERMES_AGENT_DIR) — the contract cannot be checked")
        return 2
    sigs = core_signatures(core)
    if "--selftest" in sys.argv:
        return selftest(sigs)
    problems = check(sigs)
    for p in problems:
        print(f"FAIL {p}")
    if problems:
        return 1
    print(f"core contract clean — {len(USES)} cron names checked against {core}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

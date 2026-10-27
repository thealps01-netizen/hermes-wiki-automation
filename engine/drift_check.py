"""Drift checker for the multi-agent setup on this machine.

Answers three questions in one pass:
  1. Do duplicated skills (same name in more than one tool's skill root) still say the same thing?
     A group is compared unless a copy names another author or sits in a vendor-managed folder
     (Claude's synced/, Codex's .system/): those are kept current by their own installer.
  2. Does any skill reference a local file that is missing?
  3. Do the pinned configuration values still hold (Hermes model routing, plugin scanning,
     any Codex config values named in `drift.expect`, wiki repo protection)?

Exit code 1 when drift is found, so it can be wired into a cron/watchdog job.
"""
import json, os, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wikiconfig  # tek ayar kaynağı (settings.json) — makineye özel yol KODDA YOK

try:
    import yaml
except ImportError:
    yaml = None

# Konumlar ORTAMDAN türetilir: kullanıcı evi, Hermes home ve wiki kökü taşınabilir olsun diye
# hiçbiri koda gömülmez (eskiden kullanıcının ev klasörü yazılıydı ve paket başka PC'de çalışmıyordu).
HOME = pathlib.Path.home()
try:
    _CFG = wikiconfig.load()
    HROOT = wikiconfig.hermes_home(_CFG)
except wikiconfig.ConfigError as _exc:  # bozuk ayar drift kontrolünü de durdurmasın
    _CFG, HROOT = {}, HOME / "AppData/Local/hermes"
    print(f"!! ayar okunamadı: {_exc}")

try:
    WIKI = wikiconfig.project_root(_CFG)
    WIKI_READY = True
except wikiconfig.ConfigError as _exc:
    WIKI, WIKI_READY = None, False
    print(f"!! proje kökü: {_exc} — wiki kontrolleri atlanıyor")

ROOTS = {
    "hermes": HROOT / "skills",
    "codex": HOME / ".agents/skills",
    "codex-native": HOME / ".codex/skills",
    "claude": HOME / ".claude/skills",
    "antigravity": HOME / ".gemini/config/skills",   # Antigravity 2.0 global skills (the only root it reads)
}
PLUGINS = HROOT / "plugins"

for _stream in ("stdout", "stderr"):        # cp1254 cannot encode the ✓/✗ marks
    try:
        getattr(sys, _stream).reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

drift: list[str] = []

# Which skill copies the reference check (section 2) reads. The user's own skills always are. A copy is
# skipped when it names another author or sits in a folder its vendor manages (Claude's synced/ holds
# claude.ai skills, Codex's .system/ its stock skills): those are updated by their own installer and
# never edited here, so checking them raised alerts nobody could act on. With no `drift.own_author` set
# no copy is skipped for its author: skipping every authored copy would silence the check unseen.
# Copies of one skill in several agents are NOT compared with each other: the owner retired that
# comparison because it raised a finding on every Hermes skill edit and the copies are not kept in step.
OWN_AUTHOR = str((_CFG.get("drift") or {}).get("own_author") or "")
VENDOR_DIRS = {"claude": "synced", "codex-native": ".system"}


def author_of(text: str) -> str:
    m = re.match(r"^---\s*?\n(.*?)\n---", text, re.S)
    a = re.search(r"^\s*author:\s*(.+?)\s*$", m.group(1), re.M) if m else None
    return a.group(1).strip("\"'") if a else ""


def vendor_managed(label: str, path: pathlib.Path) -> bool:
    top = VENDOR_DIRS.get(label)
    return bool(top) and path.relative_to(ROOTS[label]).parts[0] == top


def collect() -> dict[str, list[tuple[str, pathlib.Path]]]:
    found: dict[str, list[tuple[str, pathlib.Path]]] = {}
    for label, root in ROOTS.items():
        if not root.exists():
            continue
        for f in root.rglob("SKILL.md"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"^name:\s*(\S+)", text, re.M)
            name = (m.group(1).strip('"\'') if m else f.parent.name)
            found.setdefault(name, []).append((label, f))
    return found


skills = collect()
_text = {p: p.read_text(encoding="utf-8", errors="ignore") for copies in skills.values() for _, p in copies}


def excluded(label: str, p: pathlib.Path) -> str:
    """Why a copy is left out of the checks below ('' when it is checked)."""
    if vendor_managed(label, p):
        return f"{label}/{VENDOR_DIRS[label]}"
    a = author_of(_text[p])
    return f"{label}:{a}" if a and OWN_AUTHOR and a != OWN_AUTHOR else ""


print("\n== 2) eksik referanslı skill'ler ==")
# A link inside a fenced code block is an example, not a reference: skill-creator shows one
# (references/redlining.md) inside a markdown sample of how a skill routes to its detail files.
_FENCE = re.compile(r"^ *```.*?^ *``` *$|^ *~~~.*?^ *~~~ *$", re.S | re.M)
for name, copies in sorted(skills.items()):
    for label, p in copies:
        if excluded(label, p):
            continue
        body = _FENCE.sub("", "\n".join(_text[p].splitlines()))
        refs = set(re.findall(r"\((references/[^)]+|scripts/[^)]+|templates/[^)]+)\)", body))
        missing = [r for r in refs if not (p.parent / r).exists()]
        if missing:
            print(f"  {name:22} {label:13} eksik: {missing}")
            drift.append(f"eksik referans: {name} ({missing})")

print("\n== 3) sabitlenmiş yapılandırma değerleri ==")
checks: list[tuple[str, bool, str]] = []
# Beklentiler AYARDAN gelir (`drift.expect`): taşınan bir kurulumda bu değerler farklı olur ve koda
# gömülü bir beklenti yanlış alarm üretirdi. Anahtar tanımlı değilse ilgili kontrol ATLANIR.
_expect = ((_CFG.get("drift") or {}).get("expect") or {})

def _yaml_pythons() -> list[pathlib.Path]:
    """Interpreters that can parse Hermes' YAML when this one cannot: Hermes' own venv, which ships
    the parser Hermes itself reads its config with. DRIFT_CHECK_YAML_PYTHON replaces the list
    (tests point it at a stand-in)."""
    override = os.environ.get("DRIFT_CHECK_YAML_PYTHON")
    if override:
        return [pathlib.Path(override)]
    venv = HROOT / "hermes-agent" / "venv"
    return [venv / "Scripts" / "python.exe", venv / "bin" / "python"]


def read_hermes_config() -> tuple[dict | None, str]:
    """(config, problem). The scheduler runs this checker with Hermes' bundled Python, which has no
    PyYAML; parsing config.yaml as JSON then crashed the whole check before its verdict. Without
    PyYAML the file is parsed by Hermes' own interpreter; when that fails too the problem is
    returned and reported, and the checks that need the config are skipped."""
    for cand in ("config.yaml", "config.yml", "config.json"):
        f = HROOT / cand
        if not f.exists():
            continue
        try:
            if cand.endswith("json"):
                data = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
            elif yaml:
                data = yaml.safe_load(f.read_text(encoding="utf-8", errors="ignore"))
            else:
                exe = next((p for p in _yaml_pythons() if p.is_file()), None)
                if exe is None:
                    return None, (f"{cand} okunamadı: bu Python'da PyYAML yok ({sys.executable}) ve "
                                  f"Hermes'in kendi Python'u bulunamadı")
                import subprocess as _sp0
                proc = _sp0.run([str(exe), "-c", "import json,sys,yaml;print(json.dumps(yaml.safe_load("
                                 "open(sys.argv[1],encoding='utf-8')),default=str))", str(f)],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                if proc.returncode != 0:
                    err = [l for l in proc.stderr.splitlines() if l.strip()]
                    return None, f"{cand} okunamadı: {exe} hata verdi ({err[-1] if err else proc.returncode})"
                data = json.loads(proc.stdout)
        except Exception as exc:  # noqa: BLE001  (a broken config is a finding, not a crash)
            return None, f"{cand} okunamadı: {type(exc).__name__}: {exc}"
        if not isinstance(data, dict):
            return None, f"{cand} bir eşleme (mapping) değil"
        return data, ""
    return None, "config dosyası bulunamadı"


cfg, _cfg_problem = read_hermes_config()
HCFG_OK = isinstance(cfg, dict)
if not HCFG_OK:
    print(f"  (hermes config okunamadı — ona bağlı hermes kontrolleri atlandı: {_cfg_problem})")
if isinstance(cfg, dict):
    model = cfg.get("model") or {}
    plugins = cfg.get("plugins") or {}
    # Beklentiler AYARDAN gelir (`drift.expect`): taşınan kurulumda bu değerler farklıdır ve koda
    # gömülü bir beklenti yanlış alarm üretirdi. Anahtar tanımlı değilse ilgili kontrol ATLANIR.
    if "hermes_model_base_url" in _expect:
        checks.append(("hermes model.base_url beklentiyi tutuyor",
                       model.get("base_url") == _expect["hermes_model_base_url"], str(model.get("base_url"))))
    if _expect.get("hermes_model_extra_headers_empty"):
        checks.append(("hermes model.extra_headers boş", not model.get("extra_headers"), str(model.get("extra_headers"))))
    if _expect.get("hermes_plugins_scan_on_install"):
        checks.append(("hermes plugins.scan_on_install açık", plugins.get("scan_on_install") is True, str(plugins.get("scan_on_install"))))
    if not any(k.startswith("hermes_") for k in _expect):
        print("  (hermes beklentisi tanımlı değil — o kontroller atlandı)")
else:
    checks.append(("hermes config okunabildi", False, _cfg_problem))

cx = HOME / ".codex/config.toml"
txt = cx.read_text(encoding="utf-8", errors="ignore") if cx.exists() else ""
for _needle in (_expect.get("codex_config_contains") or []):
    checks.append((f"codex config içeriyor: {_needle[:44]}", _needle in txt, ""))
if not _expect.get("codex_config_contains"):
    print("  (codex beklentisi tanımlı değil — o kontroller atlandı)")

if WIKI_READY:
    git_cfg = (WIKI / ".git/config").read_text(encoding="utf-8", errors="ignore") if (WIKI / ".git/config").exists() else ""
    checks.append(("wiki remote 'onedrive' tanımlı", "onedrive" in git_cfg, ""))
    checks.append(("wiki remote 'github' tanımlı", "github" in git_cfg, ""))
    remotes = [l for l in git_cfg.splitlines() if "url = " in l]
    checks.append(("wiki 2 bağımsız uzak", len(remotes) >= 2, " | ".join(r.split("= ")[-1] for r in remotes)))
    checks.append(("wiki hooksPath = .githooks", "hooksPath = .githooks" in git_cfg.replace("\t", " "), ""))
    checks.append(("wiki pre-commit hook var", (WIKI / ".githooks/pre-commit").exists(), ""))
    ro = all(not ((WIKI / n).stat().st_mode & 0o200) for n in ("purpose.md", "schema.md") if (WIKI / n).exists())
    checks.append(("purpose.md/schema.md salt-okunur", ro, ""))
else:
    print("  (proje kökü seçilmemiş — wiki kontrolleri atlandı)")

for label, ok, detail in checks:
    print(f"  {'✓' if ok else '✗'} {label}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        drift.append(f"config sapması: {label} ({detail})")

print("\n== 4) bileşen eşitliği (hedef duruma göre) ==")

# Which tool is expected to have which component. Update TARGET when the intended parity
# changes; anything outside it is reported as drift. The shared writing-style plugin is honey,
# which replaced ponytail (no longer installed in any tool). Serena is deliberately absent: the owner
# removed it from every agent on 2026-10-24 (one call and no symbol query in Hermes' history), so a
# missing Serena is not drift. Do not restore it unless he installs Serena again.
TARGET = {
    "honey": {"codex", "claude", "hermes"},
    "llm-wiki-mcp": {"codex", "claude", "hermes"},
}
claude_json = (HOME / ".claude.json").read_text(encoding="utf-8", errors="ignore") \
    if (HOME / ".claude.json").exists() else ""
hermes_cfg = ""
for cand in ("config.yaml", "config.yml"):
    f = HROOT / cand
    if f.exists():
        hermes_cfg = f.read_text(encoding="utf-8", errors="ignore")
        break


def _load_json(path: pathlib.Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore")) if path.exists() else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


# Plugin ids carry their marketplace (honey@<marketplace>), so they are matched on the plugin name: a
# marketplace rename must not read as an uninstall. Present means installed AND enabled in that tool.
_cx_honey = re.search(r'^\[plugins\."honey@([^"]+)"\]\s*\nenabled\s*=\s*true', txt, re.M)
_cl_installed = _load_json(HOME / ".claude/plugins/installed_plugins.json").get("plugins") or {}
_cl_enabled_map = _load_json(HOME / ".claude/settings.json").get("enabledPlugins") or {}
_cl_honey_key = next((k for k in _cl_installed if k.split("@")[0] == "honey"), None)
_hm_enabled_plugins = set(((cfg.get("plugins") or {}).get("enabled") or []) if isinstance(cfg, dict) else [])


def presence(component: str, tool: str) -> bool:
    if component == "honey":
        if tool == "codex":
            return _cx_honey is not None
        if tool == "claude":
            return bool(_cl_honey_key and _cl_enabled_map.get(_cl_honey_key))
        return (HROOT / "plugins/honey").is_dir() and "honey" in _hm_enabled_plugins
    if component == "llm-wiki-mcp":
        if tool == "codex":
            return "[mcp_servers.llm-wiki]" in txt
        if tool == "claude":
            return '"llm-wiki"' in claude_json
        return "llm-wiki" in hermes_cfg
    return False


# Agent setups that exist on this installation (`drift.agents` in settings.json; default: all four).
# The owner leaves a tool out when he uninstalls it, so its missing components and skills are not
# reported as drift: on the owner's machine Claude Code and the Codex CLI were removed on 2026-10-16,
# and the hard-coded targets kept reporting eight "missing" items for tools that no longer exist.
AGENTS = set((_CFG.get("drift") or {}).get("agents") or ("codex", "claude", "hermes", "antigravity"))

for comp, expected in sorted(TARGET.items()):
    expected = expected & AGENTS
    row = {tool: presence(comp, tool) for tool in ("codex", "claude", "hermes")}
    marks = "  ".join(f"{tool}={'✓' if row[tool] else '✗'}" for tool in row)
    print(f"  {comp:10} {marks}")
    for tool, ok in row.items():
        if tool == "hermes" and not HCFG_OK:
            continue    # unknown, not missing: the unreadable config is reported in section 3
        if tool in expected and not ok:
            drift.append(f"bileşen eksik: {comp} -> {tool}")

print("\n== 5) sürüm pinleri (aynı bileşen her araçta aynı revizyonda olmalı) ==")
import json as _json
import shutil as _sh
import subprocess as _sp


def _git_rev(path: pathlib.Path) -> str:
    if not (path / ".git").exists():
        return "-"
    out = _sp.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip()[:12] if out.returncode == 0 else "-"


_cl_entry = _cl_installed.get(_cl_honey_key) if _cl_honey_key else None
if isinstance(_cl_entry, list):      # installed_plugins.json keeps one entry per install scope
    _cl_entry = _cl_entry[0] if _cl_entry else None
_cl_entry = _cl_entry if isinstance(_cl_entry, dict) else {}
_hm_honey_yaml = HROOT / "plugins/honey/plugin.yaml"
_hm_honey_text = _hm_honey_yaml.read_text(encoding="utf-8", errors="ignore") if _hm_honey_yaml.exists() else ""
_hm_ver = re.search(r"^version:\s*(\S+)", _hm_honey_text, re.M)
honey_pins = {
    "codex": _git_rev(HOME / ".codex/.tmp/marketplaces" / _cx_honey.group(1)) if _cx_honey else "-",
    "claude": str(_cl_entry.get("gitCommitSha") or "-")[:12],
    "hermes": f"v{_hm_ver.group(1)}" if _hm_ver else "-",
}
print("  honey:", "  ".join(f"{k}={v}" for k, v in honey_pins.items()))
# A version difference alone is not drift: Hermes installs honey from a release (plugin.yaml version,
# no git) while Codex and Claude install from the marketplace clone (a commit), and each tool's manifest
# carries its own version number. The pins are printed so a behaviour difference can be traced back;
# they raise no alert.

print("\n== 6) yapılandırılmış MCP komutları yolda mı ==")
cmds: set[str] = set()
for c in re.findall(r'\[mcp_servers\.[a-zA-Z0-9_\-]+\]\s*\ncommand\s*=\s*["\']([^"\']+)["\']', txt):
    cmds.add(c)
try:
    _clj = _json.loads(claude_json) if claude_json.strip() else {}
except Exception:
    _clj = {}
for _name, _cfg in (_clj.get("mcpServers") or {}).items():
    if isinstance(_cfg, dict) and _cfg.get("command"):
        cmds.add(_cfg["command"])
_mcp_block = re.search(r"(?ms)^mcp:.*?(?=^\S|\Z)", hermes_cfg)
if _mcp_block:
    for c in re.findall(r"(?m)^\s*(?:command|cmd):\s*[\"']?([^\s\"']+)", _mcp_block.group(0)):
        cmds.add(c)
missing_cmds = []
for c in sorted(cmds):
    p = pathlib.Path(c)
    ok = p.exists() if (p.is_absolute() or "/" in c or "\\" in c) else bool(_sh.which(c))
    print(f"  {'✓' if ok else '✗'} {c}")
    if not ok:
        missing_cmds.append(c)
if missing_cmds:
    drift.append(f"komut yolda değil: {missing_cmds}")

print("\n== 7) envanter ve talimat dosyaları ==")
inv = {label: (len(list(root.rglob("SKILL.md"))) if root.exists() else 0) for label, root in ROOTS.items()}
print("  skill sayısı:", "  ".join(f"{k}={v}" for k, v in inv.items()))
_wiki_ok = True
if WIKI_READY:
    _agents = WIKI / "AGENTS.md"
    _claude_md = WIKI / "CLAUDE.md"
    if not (_agents.exists() and _claude_md.exists()):
        _wiki_ok = False
    else:
        # Claude Code loads CLAUDE.md INSTEAD of AGENTS.md when both exist, so a mention is not enough:
        # only an `@AGENTS.md` import line brings the full rules into its context.
        _wiki_ok = re.search(r"^@AGENTS\.md\s*$", _claude_md.read_text(encoding="utf-8", errors="ignore"),
                             re.M) is not None
    print(f"  {'✓' if _wiki_ok else '✗'} wiki AGENTS.md + CLAUDE.md mevcut ve CLAUDE.md AGENTS.md'yi @AGENTS.md ile içe aktarıyor")
    if not _wiki_ok:
        drift.append("wiki talimat dosyaları eksik veya CLAUDE.md AGENTS.md'yi içe aktarmıyor (@AGENTS.md satırı yok)")
else:
    print("  (proje kökü seçilmemiş — wiki talimat kontrolü atlandı)")

print("\n== 8) hook eşitliği (kayıtlı ama güvenilmeyen hook sessizce çalışmaz) ==")

# Codex: a plugin hook runs only once its hash is trusted in config.toml. Honey's Codex manifest declares
# skills only, so there is nothing to trust today; this fires if a later version declares hooks that
# were never trusted.
_cx_manifests = sorted((HOME / ".codex/plugins/cache").glob("*/honey/*/.codex-plugin/plugin.json"))
_cx_declares_hooks = bool(_cx_manifests) and bool(_load_json(_cx_manifests[-1]).get("hooks"))
_cx_hooks = re.findall(r'\[hooks\.state\."honey@[^"]*"\]\s*\ntrusted_hash\s*=\s*"([^"]*)"', txt)
print(f"  codex     hook beyanı={'var' if _cx_declares_hooks else 'yok (yalnız skill)'}  güvenilen={sum(1 for h in _cx_hooks if h)}")
if _cx_declares_hooks and not (_cx_hooks and all(_cx_hooks)):
    drift.append("codex: honey hook beyan ediyor ama güvenilmiş (trusted_hash) hook yok — hook'lar çalışmaz")

# Claude: the installed plugin declares its hooks in hooks/hooks.json; they run only while it is enabled.
_cl_install_path = str(_cl_entry.get("installPath") or "")
_cl_hook_events = len(_load_json(pathlib.Path(_cl_install_path) / "hooks/hooks.json").get("hooks") or {}) \
    if _cl_install_path else 0
_cl_enabled = presence("honey", "claude")
print(f"  claude    hook={_cl_hook_events}  plugin={'✓ etkin' if _cl_enabled else '✗ kapalı'}")
if _cl_enabled and _cl_hook_events == 0:
    drift.append("claude: honey etkin ama hook beyanı bulunamadı (hooks/hooks.json)")
if _cl_hook_events and not _cl_enabled:
    drift.append("claude: honey hook'ları var ama plugin kapalı")

# Hermes: agent-level hooks declared in plugin.yaml (provides_hooks); without one the always-on directive
# is never injected. Not enabled at all is already reported by section 4.
_hm_hooks = re.findall(r"(?m)^\s*-\s*(pre_llm_call|pre_gateway_dispatch|pre_tool_call|post_tool_call)\s*$",
                       _hm_honey_text)
_hm_enabled = "honey" in _hm_enabled_plugins
print(f"  hermes    hook={len(_hm_hooks)}  plugin={'✓ etkin' if _hm_enabled else '✗ kapalı'}")
if _hm_enabled and not _hm_hooks:
    drift.append("hermes: honey etkin ama hook beyanı yok (plugin.yaml provides_hooks)")

print("\n== 9) skill hedef eşitliği ==")
SKILL_TARGET = {
    "session-to-document": {"hermes", "codex", "claude", "antigravity"},
    "llm-wiki-desktop": {"hermes"},  # folder ~/.agents/skills/llm-wiki; Hermes reads it via external_dirs
}


def _skill_names(root: pathlib.Path) -> set[str]:
    names = set()
    if root.exists():
        for f in root.rglob("SKILL.md"):
            m = re.search(r"^name:\s*(\S+)", f.read_text(encoding="utf-8", errors="ignore"), re.M)
            names.add(m.group(1).strip('"\'') if m else f.parent.name)
    return names


_have: dict[str, set[str]] = {label: _skill_names(root) for label, root in ROOTS.items()}
# Hermes also loads every folder in skills.external_dirs (config.yaml), so a skill that lives only in
# ~/.agents/skills is present for Hermes without a copy in its own root.
_ext = ((cfg.get("skills") or {}).get("external_dirs")) if isinstance(cfg, dict) else None
_ext_dirs = [_ext] if isinstance(_ext, str) else [d for d in (_ext or []) if isinstance(d, str)]
for _d in _ext_dirs:
    _have["hermes"] |= _skill_names(pathlib.Path(os.path.expandvars(os.path.expanduser(_d))))
if _ext_dirs:
    print(f"  (hermes = kendi kökü + skills.external_dirs: {', '.join(_ext_dirs)})")
for _skill, _tools in sorted(SKILL_TARGET.items()):
    _marks = "  ".join(f"{t}={'✓' if _skill in _have[t] else '✗'}" for t in ("hermes", "codex", "claude", "antigravity"))
    print(f"  {_skill:22} {_marks}")
    for _t in _tools & AGENTS:
        if _t == "hermes" and not HCFG_OK:
            continue    # external_dirs live in the unreadable config; reported in section 3
        if _skill not in _have[_t]:
            drift.append(f"skill eksik: {_skill} -> {_t}")

if "--deep" in sys.argv:
    print("\n== 10) canlı sağlık probu (--deep) ==")
    probes = [
        ("codex", "codex mcp list", ("enabled",), ("disabled",)),
        ("hermes", "hermes mcp list", ("enabled",), ("kapalı", "error")),
        ("claude", "claude mcp list", ("Connected",), ("Needs authentication", "Failed")),
    ]
    for _tool, _cmd, _good, _bad in probes:
        try:
            _out = _sp.run(_cmd, shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="ignore", timeout=240).stdout or ""
        except Exception as _exc:  # noqa: BLE001
            print(f"  {_tool:8} prob çalıştırılamadı: {_exc}")
            continue
        _g = sum(_out.count(w) for w in _good)
        _b = sum(_out.count(w) for w in _bad)
        print(f"  {_tool:8} sağlıklı={_g}  sorunlu={_b}")
        # No per-server Serena probe: Serena was removed from every agent (see TARGET).

print("\n== SONUÇ ==")
if drift:
    print(f"  {len(drift)} sapma:")
    for d in drift:
        print("   -", d)
    sys.exit(1)
print("  sapma yok")
sys.exit(0)

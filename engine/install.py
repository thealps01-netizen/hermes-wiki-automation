"""Tek komutla kurulum ve TAŞIMA — wiki otomasyonunu yeni bir PC'ye kurar.

NEDEN VAR: otomasyon (ingest watch · auto-commit · watchdog · panel) artık
makineye özel yol taşımıyor; bütün yollar `settings.json`ten geliyor. Bu script o dosyayı yazar,
parçaları Hermes klasörlerine kopyalar, zamanlanmış işleri kurar ve SONUNDA gerçekten koşarak
kurulumu doğrular. Yeni PC'de tek adım:

    python install.py --project-root "D:/Wiki/MyWiki"

Mevcut kurulumu onarmak/doğrulamak için argümansız çalıştırılır. Hiçbir şey yazmadan görmek için
`--dry-run`. Atlanacak adımlar: `--no-cron` (zamanlanmış işler), `--no-plugin` (panel).

Kurduğu parçalar:
  1. `settings.json`  — proje kökü (doğrulanır), otomasyon klasörü, Hermes home, kapılar, zamanlama
  2. `hermes/scripts/palantir_wiki_*.py` — cron giriş noktaları (bu paketin `launchers/` kopyasından)
  3. Paneller — Hermes'in sabitli Git kurulumu: `panels.json`daki depo ve commit
     (`hermes plugins install <depo> --ref <commit>`); masaüstü kopyasını uygulama kendisi alır
  4. Zamanlanmış işler (Hermes cron): auto-commit · ingest watch · watchdog
  5. DOĞRULAMA: scriptler gerçekten koşar, cron kayıtları okunur, `next_run_at` beklenen pencerede mi

Doğrulama başarısızsa script 1 ile çıkar ve hangi parçanın eksik olduğunu satır satır yazar.
"""
from __future__ import annotations

import argparse
import json
import importlib.util
import shutil
import stat
import subprocess
import sys
from pathlib import Path

# Bootstrap the standalone guard only after checking its original source path.
# No engine module from a redirected code root may execute during this step.
try:
    _bootstrap_path = Path(__file__).absolute().parent / 'launchers/_wiki_engine_bootstrap.py'
    for _source in (Path(__file__).absolute(), _bootstrap_path):
        for _component in [*reversed(_source.parents), _source]:
            _metadata = _component.lstat()
            if (stat.S_ISLNK(_metadata.st_mode)
                    or getattr(_metadata, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
                    or (stat.S_ISREG(_metadata.st_mode) and _metadata.st_nlink > 1)):
                raise ValueError('Linked installer source refused: ' + str(_component))
    _spec = importlib.util.spec_from_file_location('_installer_path_guard', _bootstrap_path)
    _guard = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_guard)
    unlinked_path = _guard.unlinked_path
    AUDIT = unlinked_path(__file__).resolve().parent
    unlinked_path(sys.executable)
    unlinked_path(AUDIT / 'wikiconfig.py')
except (OSError, ValueError) as exc:
    if __name__ != '__main__':
        raise
    print(json.dumps({'ok': False, 'state': 'refused', 'reason': str(exc)}))
    raise SystemExit(1)
sys.path.insert(0, str(AUDIT))
import wikiconfig  # tek ayar kaynağı
LAUNCHER_DIR = AUDIT / "launchers"
# Panels: each one is its own repository, installed by Hermes as a pinned Git install. panels.json
# names the repository and the exact commit this engine release was verified with; the engine keeps
# no copy of a panel. A new panel is one more entry there.
# `wiki-watchdog` was removed: wiki-automation 2.0.0 shows its run log as the Health tab (the
# `hermes-wiki-watchdog` repo keeps its history).
PANELS = json.loads((AUDIT / "panels.json").read_text(encoding="utf-8"))["panels"]
# Jobs come from ONE definition in this package (jobs.json); panels read the same file.
_JOB_DEFS = json.loads((AUDIT / "jobs.json").read_text(encoding="utf-8"))["jobs"]
LAUNCHERS = tuple(j["launcher"] for j in _JOB_DEFS.values())
# Script jobs. The name is the one already shown in the user's Jobs list ("Watch Dog"); a rename on
# migration would split the run history in two.
JOBS = tuple((k, j["name"], j["launcher"]) for k, j in _JOB_DEFS.items() if j["kind"] == "script")
# AGENT JOBS: a pre-run script gathers the input and gates the run ({"wakeAgent": false} = no model
# cost); the prompt file in this package is the agent's whole instruction. Created PAUSED on a new
# PC: the owner turns it on after checking it.
AGENT_JOBS = tuple((k, j["name"], j["launcher"], j["prompt_file"])
                   for k, j in _JOB_DEFS.items() if j["kind"] == "agent")

report: list[tuple[str, str]] = []


def note(ok: bool, text: str) -> None:
    report.append(("OK  " if ok else "EKSİK", text))
    print(f"  [{'✓' if ok else '×'}] {text}")


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                          timeout=timeout)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def hermes_cli(args: list[str]) -> tuple[int, str]:
    return run([sys.executable, "-B", "-m", "hermes_cli.main"] + args)


def read_jobs(hermes_home: Path) -> list[dict]:
    path = hermes_home / "cron" / "jobs.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    if isinstance(jobs, dict):
        jobs = list(jobs.values())
    return [j for j in jobs if isinstance(j, dict)]


def job_by_name(hermes_home: Path, name: str) -> dict | None:
    for job in read_jobs(hermes_home):
        if str(job.get("name") or "").strip().lower() == name.lower():
            return job
    return None


def write_location(hermes_home: Path, dry: bool) -> None:
    """Paketin YERİNİ Hermes home'a yaz: klasör taşınırsa panel buradan bulur.

    Neden: panel otomasyon klasörünü sırayla `LLMWIKI_AUDIT_DIR` → bu kayıt → `~/.llmwiki-audit`
    diye arar. Kayıt olmadan, taşınan bir paket "kurulu değil" görünüyordu (taşınabilirliğin asıl
    vaadi buydu). Kayıt KÜÇÜKTÜR ve yalnız yolu tutar; sır içermez.
    """
    target = hermes_home / "state" / "wiki-automation"
    if dry:
        note(True, f"konum kaydı yazılacaktı → {target / 'location.json'}")
        return
    try:
        target.mkdir(parents=True, exist_ok=True)
        record = {"audit_dir": str(AUDIT), "written_by": "install.py"}
        (target / "location.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    except OSError as exc:
        note(False, f"konum kaydı yazılamadı: {exc}")
        return
    note(True, f"konum kaydı → {target / 'location.json'}")


def copy_launchers(hermes_home: Path, dry: bool) -> int:
    """Cron giriş noktalarını Hermes scripts klasörüne kopyala. Kaynak: bu paketin `launchers/`."""
    target = hermes_home / "scripts"
    if not LAUNCHER_DIR.is_dir():
        note(False, f"launchers/ klasörü yok ({LAUNCHER_DIR}) — cron giriş noktaları kopyalanamadı")
        return 0
    if not dry:
        target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in LAUNCHERS:
        src = LAUNCHER_DIR / name
        if not src.exists():
            note(False, f"launcher eksik: {name}")
            continue
        if not dry:
            shutil.copy2(src, target / name)
        copied += 1
    note(copied == len(LAUNCHERS), f"{copied}/{len(LAUNCHERS)} cron giriş noktası → {target}")
    return copied


def install_panels(hermes_home: Path, dry: bool, force: bool = False) -> None:
    """Install each panel in panels.json as a pinned Git install at the commit named there.

    Hermes does the install (`hermes plugins install <repo> --ref <commit>`) and records it in
    plugins/.install-metadata.json; the desktop app copies the panel's desktop half itself. A panel that
    is present but not pinned at that commit is reported and left alone: it may be pinned elsewhere on
    purpose or hold work. `--force` moves it to the engine's commit, except a git checkout with
    uncommitted changes, which is never replaced.
    """
    meta = _install_metadata(hermes_home)
    for name, pin in PANELS.items():
        _install_one_panel(hermes_home, name, pin["repo"], pin["commit"], meta.get(name), dry, force)


def _install_metadata(hermes_home: Path) -> dict:
    path = hermes_home / "plugins" / ".install-metadata.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _uncommitted(live: Path) -> bool:
    if not (live / ".git").exists():
        return False
    proc = subprocess.run(["git", "-C", str(live), "status", "--porcelain"], capture_output=True,
                          text=True)
    return proc.returncode != 0 or bool(proc.stdout.strip())


def _install_one_panel(hermes_home: Path, name: str, repo: str, commit: str, row, dry: bool,
                       force: bool) -> None:
    live = hermes_home / "plugins" / name
    pinned = isinstance(row, dict) and row.get("pinned") is True
    if live.is_dir() and pinned and row.get("revision") == commit:
        note(True, f"{name}: {commit[:8]} commit'ine sabitli")
        return
    if live.is_dir() and not force:
        where = (f"{str(row.get('revision'))[:8]} commit'ine sabitli" if pinned
                 else "sabitlenmemiş bir kopya")
        note(True, f"{name}: {where}, motorun commit'i {commit[:8]} — dokunulmadı (taşımak için --force)")
        return
    if live.is_dir() and _uncommitted(live):
        note(False, f"{name}: canlı panelde commit edilmemiş değişiklik var — üzerine kurulmadı")
        return
    args = ["plugins", "install", repo, "--ref", commit, "--enable"] + (["--force"] if live.is_dir() else [])
    if dry:
        note(True, f"{name}: kurulacak → hermes {' '.join(args)}")
        return
    code, out = hermes_cli(args)
    row = _install_metadata(hermes_home).get(name)
    ok = (code == 0 and isinstance(row, dict) and row.get("pinned") is True
          and row.get("revision") == commit)
    note(ok, f"{name}: {repo} @ {commit[:8]} sabitli kuruldu" + ("" if ok else f" ({out.strip()[-160:]})"))


def install_wiki_hooks(root: Path, dry: bool) -> None:
    """Copy the engine's wiki-hooks/ into <wiki>/.githooks/ and point git at it.

    The engine owns the hooks; the wiki holds a generated copy. A hand edit in the wiki copy is
    overwritten here, which is the point: fix the hook in wiki-hooks/ and re-run install.py."""
    src = AUDIT / "wiki-hooks"
    dst = root / ".githooks"
    names = sorted(p.name for p in src.glob("*") if p.is_file()) if src.is_dir() else []
    if not names:
        note(False, f"wiki-hooks/ yok ya da boş ({src}) — commit kancaları kurulamadı")
        return
    if not dry:
        dst.mkdir(exist_ok=True)
        for n in names:
            (dst / n).write_bytes((src / n).read_bytes().replace(b"\r\n", b"\n"))
        subprocess.run(["git", "-C", str(root), "config", "core.hooksPath", ".githooks"],
                       capture_output=True, text=True)
    same = not dry and all((dst / n).read_bytes() == (src / n).read_bytes().replace(b"\r\n", b"\n")
                           for n in names)
    note(dry or same, f"commit kancaları ({', '.join(names)}) → {dst}")


def sync_jobs(cfg: dict, hermes_home: Path, dry: bool) -> dict:
    """Üç zamanlanmış işi kur/tazele. Var olan iş güncellenir (kopya üretilmez)."""
    ids = dict(cfg.get("jobs") or {})
    schedule = cfg.get("schedule") or {}
    deliver = cfg.get("deliver") or "local"
    for key, name, script in JOBS:
        sched = schedule.get(key) or _JOB_DEFS[key].get("default_schedule")
        desc = _JOB_DEFS[key].get("description") or ""
        if not sched:
            note(False, f"zamanlama tanımsız: schedule.{key}")
            continue
        existing = job_by_name(hermes_home, name)
        if existing:
            if not dry:
                code, out = hermes_cli(["cron", "edit", str(existing.get("id")), "--schedule", sched,
                                        "--script", script, "--no-agent", "--deliver", deliver,
                                        "--prompt", desc])
                if code != 0:
                    note(False, f"iş güncellenemedi: {name} ({out.strip()[:120]})")
                    continue
            ids[key] = existing.get("id")
            note(True, f"iş güncellendi: {name} ({sched})")
        else:
            if dry:
                note(True, f"iş kurulacak: {name} ({sched})")
                continue
            code, out = hermes_cli(["cron", "create", sched, desc, "--name", name, "--script", script,
                                    "--no-agent", "--deliver", deliver])
            created = job_by_name(hermes_home, name)
            if code != 0 or not created:
                note(False, f"iş kurulamadı: {name} ({out.strip()[:120]})")
                continue
            ids[key] = created.get("id")
            note(True, f"iş kuruldu: {name} ({sched})")
    if not dry and ids != (cfg.get("jobs") or {}):
        wikiconfig.save({"jobs": ids})
    return ids


def agent_prompt(prompt_file: str) -> str:
    """The job prompt: the package's instruction file with this PC's folders filled in, so the
    stored prompt never carries another machine's paths."""
    text = (AUDIT / prompt_file).read_text(encoding="utf-8")
    cfg = wikiconfig.load()
    header = (f"Automation folder: {AUDIT}\nWiki root: {wikiconfig.project_root(cfg)}\n"
              f"Python for the scripts: {sys.executable}\nThe run folder is in the job context "
              f"(`run_dir`).\n\n")
    return header + text


def sync_agent_jobs(cfg: dict, hermes_home: Path, dry: bool) -> None:
    schedule = cfg.get("schedule") or {}
    deliver = cfg.get("deliver") or "local"
    ids = dict(cfg.get("jobs") or {})
    for key, name, script, prompt_file in AGENT_JOBS:
        sched = schedule.get(key) or _JOB_DEFS[key].get("default_schedule")
        prompt = agent_prompt(prompt_file)
        existing = job_by_name(hermes_home, name)
        if dry:
            note(True, f"ajan işi {'güncellenecek' if existing else 'kurulacak (duraklatılmış)'}: {name} ({sched})")
            continue
        if existing:
            code, out = hermes_cli(["cron", "edit", str(existing.get("id")), "--schedule", sched,
                                    "--script", script, "--prompt", prompt, "--deliver", deliver])
            ok = code == 0
            ids[key] = existing.get("id")
            note(ok, f"ajan işi güncellendi: {name} ({sched})" + ("" if ok else f" ({out.strip()[:120]})"))
        else:
            code, out = hermes_cli(["cron", "create", sched, prompt, "--name", name, "--script", script,
                                    "--deliver", deliver, "--paused",
                                    "--paused-reason", "new install: turn on after checking the first run"])
            created = job_by_name(hermes_home, name)
            ok = code == 0 and created is not None
            if created:
                ids[key] = created.get("id")
            note(ok, f"ajan işi kuruldu (duraklatılmış): {name} ({sched})" + ("" if ok else f" ({out.strip()[:120]})"))
    if not dry and ids != (cfg.get("jobs") or {}):
        wikiconfig.save({"jobs": ids})


def verify(cfg: dict, hermes_home: Path, dry: bool) -> bool:
    """Kurulumu İDDİAYLA değil KOŞARAK doğrula: scriptler + cron kayıtları + sonraki koşu zamanı."""
    ok = True
    for label, script, args in (("auto-commit (dry-run)", "wiki_autocommit.py", ["--dry-run"]),
                                ("ingest watch", "wiki_ingest_watch.py", []),
                                ("watchdog", "watchdog.py", [])):
        target = AUDIT / script
        if not target.exists():
            note(False, f"{label}: script yok ({target})")
            ok = False
            continue
        if dry:
            note(True, f"{label}: koşulacak")
            continue
        try:
            code, out = run([sys.executable, "-B", str(target)] + args, timeout=300)
        except subprocess.TimeoutExpired:
            note(False, f"{label}: zaman aşımı")
            ok = False
            continue
        # 0 = temiz, 1 = bulgu var (uyarı yolu). 2+ = gerçek hata.
        note(code <= 1, f"{label}: çıkış {code}" + ("" if code <= 1 else f" ({out.strip()[:120]})"))
        ok = ok and code <= 1

    # Cron kayıtları: iş gerçekten var mı ve SONRAKİ KOŞU beklenen pencerede mi?
    for key, name, _ in JOBS:
        job = job_by_name(hermes_home, name)
        if not job:
            note(False, f"cron işi yok: {name}")
            ok = False
            continue
        sched = job.get("schedule") or {}
        display = sched.get("display") or sched.get("expr") or sched.get("kind")
        nxt = str(job.get("next_run_at") or "")
        if sched.get("kind") == "interval":
            note(False, f"{name}: zamanlama aralık olarak kayıtlı ({display}) — cron söz dizimi beklenirdi")
            ok = False
            continue
        note(True, f"{name}: {display} · sonraki {nxt[:16]}")
    return ok


def code_fingerprints(code: Path) -> dict:
    import hashlib
    from workflow_paths import checked_path
    sources = sorted([*code.glob('*.py'), *code.glob('launchers/*.py'),
        *[code / name for name in ('jobs.json', 'panels.json', 'harvest_prompt.md') if (code / name).is_file()]])
    return {path.relative_to(code).as_posix(): hashlib.sha256(
        checked_path(code, path.relative_to(code).as_posix()).read_bytes()).hexdigest() for path in sources}


def launcher_payloads(code: Path, definitions: dict) -> dict:
    from workflow_paths import checked_path
    payloads = {'_wiki_engine_bootstrap.py': checked_path(code, 'launchers/_wiki_engine_bootstrap.py').read_bytes().hex()}
    for spec in definitions.values():
        name, implementation = spec['launcher'], spec['impl']
        checked_path(code, 'launchers/' + name)
        checked_path(code, implementation)
        content = "from _wiki_engine_bootstrap import launch\nraise SystemExit(launch(" + repr(implementation) + "))\n"
        payloads[name] = content.encode('utf-8').hex()
    return payloads


def parse_native_jobs(raw: bytes | None) -> list[dict]:
    """One strict repair-free parser for capture, review, apply and panel inspection."""
    from cron.jobs import _normalize_job_record
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON field')
            result[key] = value
        return result
    try:
        if raw is None:
            return []
        document = json.loads(raw, object_pairs_hook=object_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
        if (not isinstance(document, dict) or set(document) - {'jobs', 'updated_at'}
                or not isinstance(document.get('jobs'), list)):
            raise ValueError('Unsupported job store')
        records, identifiers = [], set()
        for job in document['jobs']:
            if (not isinstance(job, dict) or not isinstance(job.get('id'), str) or not job['id']
                    or job['id'] in identifiers or type(job.get('no_agent')) is not bool
                    or ('enabled' in job and type(job['enabled']) is not bool)):
                raise ValueError('Unsupported native job identity')
            identifiers.add(job['id'])
            for key in ('name', 'prompt', 'script', 'skill', 'schedule_display', 'state', 'workdir', 'interpreter'):
                if job.get(key) is not None and not isinstance(job[key], str):
                    raise ValueError('Unsupported native job field')
            if job.get('skills') is not None and (not isinstance(job['skills'], list)
                    or any(not isinstance(value, str) for value in job['skills'])):
                raise ValueError('Unsupported native skills')
            schedule, repeat = job.get('schedule'), job.get('repeat')
            if (not isinstance(schedule, dict) or schedule.get('kind') not in ('cron', 'interval', 'once')
                    or (repeat is not None and (not isinstance(repeat, dict)
                        or type(repeat.get('completed', 0)) is not int or repeat.get('completed', 0) < 0
                        or (repeat.get('times') is not None and (type(repeat['times']) is not int or repeat['times'] <= 0))))):
                raise ValueError('Unsupported schedule or repeat record')
            if schedule.get('kind') == 'cron':
                if not isinstance(schedule.get('expr'), str) or not schedule['expr'].strip():
                    raise ValueError('Unsupported cron expression')
                from cron.jobs import parse_schedule
                if parse_schedule(schedule['expr']).get('kind') != 'cron':
                    raise ValueError('Unsupported cron expression')
            elif schedule.get('kind') == 'interval':
                if type(schedule.get('minutes')) is not int or schedule['minutes'] <= 0:
                    raise ValueError('Unsupported interval')
            else:
                from datetime import datetime
                if not isinstance(schedule.get('run_at'), str):
                    raise ValueError('Unsupported one-shot date')
                datetime.fromisoformat(schedule['run_at'])
            if schedule.get('display') is not None and not isinstance(schedule['display'], str):
                raise ValueError('Unsupported schedule display')
            if job.get('origin') is not None and not isinstance(job['origin'], dict):
                raise ValueError('Unsupported native origin')
            if job.get('enabled_toolsets') is not None and (not isinstance(job['enabled_toolsets'], list)
                    or any(not isinstance(value, str) for value in job['enabled_toolsets'])):
                raise ValueError('Unsupported native toolsets')
            records.append(_normalize_job_record(job))
        return records
    except (ValueError, TypeError, KeyError) as exc:
        raise wikiconfig.ConfigError('Native job store is unsupported; no repair is performed') from exc


def existing_job_snapshot(hermes_home: Path) -> dict:
    """Inspect the selected store without native load/get/list repair side effects."""
    import hashlib
    from workflow_paths import checked_path
    home = unlinked_path(hermes_home)
    path = checked_path(home, 'cron/jobs.json')
    raw = path.read_bytes() if path.exists() else None
    return {'jobs': parse_native_jobs(raw),
        'sha256': hashlib.sha256(raw).hexdigest() if raw is not None else None}


def build_plan(cfg: dict, hermes_home: Path, code_root: Path, data_root: Path) -> dict:
    """Build a repair-free, stable engine-owned preview; this function creates nothing."""
    import hashlib
    from owner_decisions import canonical
    from workflow_paths import checked_path
    home, code, data = (unlinked_path(path).resolve() for path in (hermes_home, code_root, data_root))
    if not home.is_dir() or not code.is_dir():
        raise wikiconfig.ConfigError('Existing selected profile and staged code roots are required')
    if cfg.get('hermes_home') and unlinked_path(cfg['hermes_home']).resolve() != home:
        raise wikiconfig.ConfigError('Install preview belongs to a different profile')
    info = wikiconfig.validate_project(cfg.get('project_root') or '')
    if not info['ok']:
        raise wikiconfig.ConfigError('Project identity must be verified before installation preview')
    if cfg.get('project_id') and cfg['project_id'] != info['id']:
        raise wikiconfig.ConfigError('Configured project identity changed')
    state_paths = {'settings': checked_path(data, 'settings.json'),
        'location': checked_path(home, 'state/wiki-automation/location.json'),
        'jobs': checked_path(home, 'cron/jobs.json')}
    before, captured, raw_state = {}, {}, {}
    for key, path in state_paths.items():
        if not path.exists():
            before[key], captured[key] = None, None
            continue
        raw = raw_state[key] = path.read_bytes()
        before[key] = hashlib.sha256(raw).hexdigest()
        try:
            captured[key] = json.loads(raw)
            if not isinstance(captured[key], dict):
                raise ValueError('Stored object is not a dictionary')
        except (ValueError, OSError) as exc:
            raise wikiconfig.ConfigError(f'Existing {key} is unreadable; no installation fallback is allowed') from exc
    if captured['location'] is not None:
        location_record = captured['location']
        for key in ('audit_dir', 'engine_dir'):
            if isinstance(location_record.get(key), str) and location_record[key]:
                unlinked_path(location_record[key])
        _previous_code, previous_data = wikiconfig.validate_location(captured['location'])
        if previous_data.resolve() != data:
            raise wikiconfig.ConfigError('Existing mutable data root must be retained; migration is not authorized')
    records = parse_native_jobs(raw_state.get('jobs'))
    settings = wikiconfig._merge(cfg, captured['settings'] or {})
    if 'install_options' in cfg:
        settings['install_options'] = dict(cfg['install_options'])
    settings.update(project_root=info['path'], project_id=info['id'], hermes_home=str(home),
        engine_dir=str(code), audit_dir=str(data))
    definitions = json.loads(checked_path(code, 'jobs.json').read_bytes())['jobs']
    if not isinstance(definitions, dict):
        raise wikiconfig.ConfigError('Engine job definitions are malformed')
    payloads = launcher_payloads(code, definitions)
    launcher_before = {}
    old_location = captured['location'] or {}
    adoptions = _legacy_adoptions(old_location, settings, records, definitions)
    for name, encoded in payloads.items():
        target = checked_path(home, 'scripts/' + name)
        existing = target.read_bytes() if target.exists() else None
        observed = hashlib.sha256(existing).hexdigest() if existing is not None else None
        launcher_before[name] = observed
        if existing is not None and existing != bytes.fromhex(encoded):
            owned_hash = (old_location.get('launcher_hashes') or {}).get(name)
            if owned_hash is None and old_location.get('written_by') == 'install.py' and old_location.get('audit_dir'):
                previous_source = checked_path(Path(old_location['audit_dir']), 'launchers/' + name)
                if previous_source.is_file():
                    owned_hash = hashlib.sha256(previous_source.read_bytes()).hexdigest()
            if owned_hash != observed:
                raise wikiconfig.ConfigError('Existing same-name launcher is customized or unowned; it was preserved')
    code_hashes = code_fingerprints(code)
    plan = {'schema': 1, 'hermes_home': str(home), 'engine_dir': str(code), 'audit_dir': str(data),
        'installer_interpreter': str(unlinked_path(sys.executable).resolve()),
        'project_id': info['id'], 'settings_path': str(state_paths['settings']), 'settings': settings,
        'before_hashes': before, 'existing_jobs': records, 'job_definitions': definitions,
        'code_hashes': code_hashes, 'launcher_payloads': payloads, 'launcher_before': launcher_before, 'location': {'schema': 2, 'engine_dir': str(code),
            'audit_dir': str(data), 'written_by': 'engine.install',
            'launcher_hashes': {name: hashlib.sha256(bytes.fromhex(content)).hexdigest() for name, content in payloads.items()}}}
    if adoptions:
        plan['legacy_adoptions'] = adoptions
    refresh = _job_refresh(old_location, settings, records, definitions, code, home, plan['installer_interpreter'])
    if refresh:
        plan['job_refresh'] = refresh
    if (settings.get('install_options') or {}).get('no_cron') is False:
        # Refuse at preview, before anything is journaled: every mapped job that is kept must
        # already be this engine's verified role, otherwise apply could only strand it.
        for role in definitions:
            job = next((row for row in records if row['id'] == (settings.get('jobs') or {}).get(role)), None)
            if job is not None and role not in adoptions:
                verify_job_role(job, role, plan)
    plan['digest'] = hashlib.sha256(canonical(plan)).hexdigest()
    return plan


# Fields the pre-panel install.py never set when it created jobs through `hermes cron create`.
_LEGACY_UNSET = ('origin', 'workdir', 'interpreter', 'skill', 'model', 'provider', 'base_url',
    'monitor_script', 'monitor_url', 'context_from')
# Scheduler-owned run bookkeeping; a scheduled run changing these is not an owner edit.
_RUNTIME_FIELDS = ('last_run_at', 'next_run_at', 'last_status', 'last_error', 'last_delivery_error',
    'last_delivery_unverified', 'last_dispatch', 'failure_streak', 'fire_claim', 'monitor_state',
    'pending_slot', 'quota_hold_until', 'last_failure', 'last_fire_error', 'preflight_alerted')
LEGACY_AGENT_PAUSED_REASON = 'Adopted from the earlier installer; owner activation required.'


def _legacy_adoptions(old_location: dict, settings: dict, records: list, definitions: dict) -> dict:
    """Mapped jobs that still have the exact shape the pre-panel install.py created, by role.

    Only a bare legacy location written by install.py qualifies. A customized or unmapped job
    is left out, so preview verification refuses it and nothing is written.
    """
    if old_location.get('written_by') != 'install.py' or 'schema' in old_location:
        return {}
    mapping, deliver = settings.get('jobs') or {}, settings.get('deliver') or 'local'
    adoptions = {}
    for role, spec in definitions.items():
        job = next((row for row in records if row['id'] == mapping.get(role)), None)
        agent = spec['kind'] == 'agent'
        if (job is not None and job.get('name') == spec['name'] and job.get('script') == spec['launcher']
                and job.get('no_agent') is (not agent) and job.get('deliver') == deliver
                and isinstance(job.get('repeat'), dict) and job['repeat'].get('times') is None
                and all(job.get(key) is None for key in _LEGACY_UNSET)
                and not job.get('enabled_toolsets') and not job.get('skills')):
            adoptions[role] = job['id']
    return adoptions


def legacy_adoption_updates(role: str, plan: dict) -> dict:
    """The only fields adoption writes. Script jobs keep schedule, on/off state and history; the
    drafting job keeps its ID, schedule and history but gets the new prompt and tools and is paused."""
    from workflow_paths import checked_path
    spec = plan['job_definitions'][role]
    updates = {'workdir': plan['settings']['project_root'],
        'origin': {'engine_installation': plan['digest'], 'engine_role': role}}
    if spec['kind'] != 'agent':
        return {**updates, 'interpreter': plan['installer_interpreter']}
    prompt = checked_path(unlinked_path(plan['engine_dir']), spec['prompt_file']).read_text(encoding='utf-8').strip()
    # next_run_at is cleared so turning the job on later schedules the next slot instead of a catch-up run.
    return {**updates, 'script': None, 'prompt': prompt, 'enabled_toolsets': ['wiki_draft', 'no_mcp'],
        'enabled': False, 'state': 'paused', 'paused_reason': LEGACY_AGENT_PAUSED_REASON, 'next_run_at': None}


def _legacy_adoption_state(job: dict, captured: dict | None, updates: dict) -> str | None:
    """'pending' = unchanged since preview, 'adopted' = only the adoption fields were written."""
    if captured is None:
        return None

    def rest(row):
        kept = {key: value for key, value in row.items() if key not in updates and key not in _RUNTIME_FIELDS}
        if isinstance(kept.get('repeat'), dict):
            kept['repeat'] = {key: value for key, value in kept['repeat'].items() if key != 'completed'}
        return kept
    if rest(job) != rest(captured):
        return None
    if all(job.get(key) == captured.get(key) for key in updates):
        return 'pending'
    return 'adopted' if job.get('origin') == updates['origin'] else None


def _sha_text(value) -> str:
    import hashlib
    return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()


def _prompt_text(code_dir, prompt_file: str) -> str | None:
    from workflow_paths import checked_path
    try:
        return checked_path(unlinked_path(code_dir), prompt_file).read_text(encoding='utf-8').strip()
    except (OSError, ValueError, wikiconfig.ConfigError):
        return None


def _same_path(a, b) -> bool:
    try:
        return unlinked_path(a).resolve() == unlinked_path(b).resolve()
    except (OSError, ValueError, TypeError, wikiconfig.ConfigError):
        return False


def _recorded_interpreters(home: Path) -> list:
    """Interpreters that applied installations of this engine wrote into this profile's jobs."""
    import sqlite3
    journal = home / 'state' / 'wiki-automation' / 'installation.sqlite'
    if not journal.is_file():
        return []
    try:
        db = sqlite3.connect(journal.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
        try:
            rows = db.execute("SELECT identity FROM operations WHERE state='applied'").fetchall()
        finally:
            db.close()
    except sqlite3.DatabaseError:
        return []
    found = []
    for (identity,) in rows:
        try:
            value = (json.loads(identity).get('plan') or {}).get('installer_interpreter')
        except (ValueError, AttributeError):
            continue
        if isinstance(value, str) and value and value not in found:
            found.append(value)
    return found


def _owned(job, role: str) -> bool:
    import re
    origin = job.get('origin') if isinstance(job, dict) else None
    return (isinstance(origin, dict) and set(origin) == {'engine_installation', 'engine_role'}
            and origin.get('engine_role') == role
            and re.fullmatch('[0-9a-f]{64}', str(origin.get('engine_installation'))) is not None)


def _job_refresh(old_location: dict, settings: dict, records: list, definitions: dict, code: Path,
                 home: Path, interpreter: str) -> dict:
    """Engine-written job fields that an update replaces, by role: {'job_id', 'field', 'from_sha256'}.

    Only this engine's own job (origin) with its exact role shape qualifies, and only when the old
    value is what an earlier installation wrote. Schedule, on/off state and history never change."""
    previous_code = old_location.get('engine_dir') if 'schema' in old_location else None
    mapping, recorded = settings.get('jobs') or {}, None
    refresh = {}
    for role, spec in definitions.items():
        job = next((row for row in records if row['id'] == mapping.get(role)), None)
        if job is None or not _owned(job, role) or job.get('name') != spec['name']:
            continue
        if spec.get('kind') == 'agent':
            old = _prompt_text(previous_code, spec['prompt_file']) if isinstance(previous_code, str) and previous_code else None
            new = _prompt_text(code, spec['prompt_file'])
            if (old is not None and new is not None and old != new and job.get('prompt') == old
                    and job.get('script') is None and job.get('no_agent') is False and job.get('interpreter') is None
                    and set(job.get('enabled_toolsets') or []) == {'wiki_draft', 'no_mcp'}):
                refresh[role] = {'job_id': job['id'], 'field': 'prompt', 'from_sha256': _sha_text(old)}
            continue
        current = job.get('interpreter')
        if (not isinstance(current, str) or not current or _same_path(current, interpreter)
                or job.get('no_agent') is not True or job.get('script') != spec['launcher']
                or job.get('enabled_toolsets') or job.get('skills')):
            continue
        recorded = _recorded_interpreters(home) if recorded is None else recorded
        if any(_same_path(current, value) or current == value for value in recorded):
            refresh[role] = {'job_id': job['id'], 'field': 'interpreter', 'from_sha256': _sha_text(current)}
    return refresh


def _refresh_value(role: str, plan: dict):
    entry = (plan.get('job_refresh') or {})[role]
    if entry['field'] == 'prompt':
        return _prompt_text(plan['engine_dir'], plan['job_definitions'][role]['prompt_file'])
    return plan['installer_interpreter']


def _refresh_allows(job: dict, role: str, plan: dict, field: str) -> bool:
    """The job still holds the previewed old value of a planned refresh of *field*."""
    entry = (plan.get('job_refresh') or {}).get(role) or {}
    return (entry.get('field') == field and entry.get('job_id') == job.get('id')
            and entry.get('from_sha256') == _sha_text(job.get(field)))


def _refresh_state(job: dict, captured: dict | None, role: str, plan: dict) -> str | None:
    """'pending' = as previewed, 'applied' = only the planned field now holds the new value,
    None = anything else changed (the owner's record is preserved)."""
    entry = (plan.get('job_refresh') or {}).get(role)
    if not entry or captured is None or not isinstance(job, dict) or job.get('id') != entry['job_id']:
        return None
    field = entry['field']

    def rest(row):
        kept = {key: value for key, value in row.items() if key != field and key not in _RUNTIME_FIELDS}
        if isinstance(kept.get('repeat'), dict):
            kept['repeat'] = {key: value for key, value in kept['repeat'].items() if key != 'completed'}
        return kept
    if rest(job) != rest(captured):
        return None
    if job.get(field) == captured.get(field) and _sha_text(job.get(field)) == entry['from_sha256']:
        return 'pending'
    return 'applied' if job.get(field) == _refresh_value(role, plan) else None


def _is_adopted(role: str, job: dict, plan: dict) -> bool:
    return isinstance(job, dict) and (plan.get('legacy_adoptions') or {}).get(role) == job.get('id')


class PlanStale(wikiconfig.ConfigError):
    """Refused before the installation journal was written; a fresh preview is the only next step."""


def verify_job_role(job: dict, role: str, plan: dict) -> None:
    import re
    from workflow_paths import checked_path
    spec = plan['job_definitions'][role]
    agent = spec['kind'] == 'agent'
    if (not isinstance(job, dict) or job.get('name') != spec['name']
            or job.get('no_agent') is not (not agent)
            or job.get('script') != (None if agent else spec['launcher'])
            or job.get('workdir') != plan['settings']['project_root']):
        raise wikiconfig.ConfigError('Mapped job is not the selected engine role; owner work was preserved')
    captured = next((row for row in plan['existing_jobs'] if row['id'] == job['id']), None)
    origin = captured.get('origin') if captured is not None and not _is_adopted(role, job, plan) else {
        'engine_installation': plan['digest'], 'engine_role': role}
    if (not isinstance(origin, dict) or set(origin) != {'engine_installation', 'engine_role'}
            or origin.get('engine_role') != role or not isinstance(origin.get('engine_installation'), str)
            or not re.fullmatch('[0-9a-f]{64}', origin['engine_installation']) or job.get('origin') != origin):
        raise wikiconfig.ConfigError('Native engine job origin changed or lacks original ownership')
    if agent:
        prompt = checked_path(unlinked_path(plan['engine_dir']), spec['prompt_file']).read_text(encoding='utf-8').strip()
        if (set(job.get('enabled_toolsets') or []) != {'wiki_draft', 'no_mcp'}
                or (job.get('prompt') != prompt and not _refresh_allows(job, role, plan, 'prompt'))
                or job.get('interpreter') is not None):
            raise wikiconfig.ConfigError('Legacy or customized drafting job requires a separate reviewed migration')
    else:
        expected = unlinked_path(plan.get('installer_interpreter') or sys.executable)
        selected = job.get('interpreter')
        if (not isinstance(selected, str) or not selected
                or (unlinked_path(selected).resolve() != expected.resolve()
                    and not _refresh_allows(job, role, plan, 'interpreter'))
                or job.get('enabled_toolsets') or job.get('skills')):
            raise wikiconfig.ConfigError('Native script interpreter or execution role changed; no repair attempted')


def _verify_new_installation_job(job, role, plan, recorded=None):
    """New paused records must still describe the exact engine-created operation."""
    from cron.jobs import parse_schedule
    from workflow_paths import checked_path
    spec = plan['job_definitions'][role]
    prompt = (checked_path(unlinked_path(plan['engine_dir']), spec['prompt_file']).read_text(encoding='utf-8').strip()
        if spec['kind'] == 'agent' else spec['description'].strip())
    schedule = parse_schedule((plan['settings'].get('schedule') or {}).get(role) or spec['default_schedule'])
    expected = {'prompt': prompt, 'schedule': schedule, 'repeat': {'times': None, 'completed': 0},
        'enabled': False, 'state': 'paused', 'deliver': plan['settings'].get('deliver') or 'local',
        'next_run_at': None, 'last_run_at': None,
        'paused_reason': 'Created by the verified engine installer; owner activation required.'}
    if any(job.get(key) != value for key, value in expected.items()):
        raise wikiconfig.ConfigError('New installation-owned paused job changed; owner record was preserved')
    if recorded is not None and recorded.get('job_snapshot') != job:
        raise wikiconfig.ConfigError('New installation-owned job differs from its exact journaled snapshot')


def register_paused_jobs(plan: dict, store) -> dict:
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from cron.jobs import use_cron_store, create_job, update_job
    from candidate_apply import _checkpoint
    home = Path(plan['hermes_home'])
    mapping = dict(plan['settings'].get('jobs') or {})
    token = set_hermes_home_override(home)
    try:
        with use_cron_store(home):
            def captured_row(job_id):
                return next((row for row in plan['existing_jobs'] if row['id'] == job_id), None)
            for role in plan['job_definitions']:
                previous = next((job for job in existing_job_snapshot(home)['jobs'] if job['id'] == mapping.get(role)), None)
                if previous is not None and _is_adopted(role, previous, plan):
                    if _legacy_adoption_state(previous, captured_row(previous['id']),
                            legacy_adoption_updates(role, plan)) is None:
                        raise wikiconfig.ConfigError('Legacy job changed after preview; owner record was preserved')
                elif previous is not None:
                    verify_job_role(previous, role, plan)
            for role, spec in plan['job_definitions'].items():
                marker = {'engine_installation': plan['digest'], 'engine_role': role}
                rows = existing_job_snapshot(home)['jobs']
                matches = [row for row in rows if row.get('origin') == marker]
                if len(matches) > 1:
                    raise wikiconfig.ConfigError('Ambiguous saved installation job; no duplicate was created')
                previous = next((row for row in rows if row['id'] == mapping.get(role)), None)
                if matches:
                    job = matches[0]
                elif previous is not None and _is_adopted(role, previous, plan):
                    updates = legacy_adoption_updates(role, plan)
                    state = _legacy_adoption_state(previous, captured_row(previous['id']), updates)
                    if state is None:
                        raise wikiconfig.ConfigError('Legacy job changed after preview; owner record was preserved')
                    job = previous if state == 'adopted' else update_job(previous['id'], updates)
                    _checkpoint('after-adopt-job:' + role)
                elif previous is not None and role in (plan.get('job_refresh') or {}):
                    state = _refresh_state(previous, captured_row(previous['id']), role, plan)
                    if state is None:
                        raise wikiconfig.ConfigError('Managed job changed after preview; customized record was preserved')
                    field = plan['job_refresh'][role]['field']
                    job = previous if state == 'applied' else update_job(previous['id'], {field: _refresh_value(role, plan)})
                    _checkpoint('after-job-refresh:' + role)
                elif previous is not None:

                    captured = next((row for row in plan['existing_jobs'] if row['id'] == previous['id']), None)
                    if captured != previous:
                        raise wikiconfig.ConfigError('Managed job changed after preview; customized record was preserved')
                    job = previous
                else:
                    if any(row.get('name') == spec['name'] for row in rows):
                        raise wikiconfig.ConfigError('Same-name job has no verified installation ownership; it was preserved')
                    agent = spec['kind'] == 'agent'
                    prompt = (Path(plan['engine_dir']) / spec['prompt_file']).read_text(encoding='utf-8') if agent else spec['description']
                    job = create_job(prompt=prompt,
                        schedule=(plan['settings'].get('schedule') or {}).get(role) or spec['default_schedule'],
                        name=spec['name'], repeat=None, deliver=plan['settings'].get('deliver') or 'local',
                        origin=marker, script=None if agent else spec['launcher'], no_agent=not agent,
                        enabled_toolsets=['wiki_draft', 'no_mcp'] if agent else [],
                        workdir=plan['settings']['project_root'], paused=True,
                        paused_reason='Created by the verified engine installer; owner activation required.',
                        interpreter=None if agent else sys.executable)
                    _checkpoint('after-create-job:' + role)
                verify_job_role(job, role, plan)
                saved = next((row for row in existing_job_snapshot(home)['jobs'] if row['id'] == job['id']), None)
                if saved != job:
                    raise wikiconfig.ConfigError('Native installation job readback disagreed')
                captured = next((row for row in plan['existing_jobs'] if row['id'] == job['id']), None)
                if captured is None:
                    steps = store.steps(plan['digest'])
                    recorded = next((entry['result'] for entry in steps if entry['step'] == 'job-' + role), None)
                    snapshot = next((entry['result'] for entry in steps if entry['step'] == 'job-snapshot-' + role), None)
                    _verify_new_installation_job(job, role, plan, snapshot if snapshot is not None else ({} if recorded is not None else None))
                    store.record_step(plan['digest'], 'job-snapshot-' + role, {'job_snapshot': job})
                mapping[role] = job['id']
                store.record_step(plan['digest'], 'job-' + role, {'job_id': job['id'], 'origin': job.get('origin')})
            return mapping
    finally:
        reset_hermes_home_override(token)


def _installation_projections(plan, settings):
    from owner_decisions import canonical
    from workflow_paths import checked_path
    home, data = Path(plan['hermes_home']), Path(plan['audit_dir'])
    writes = [('settings', checked_path(data, 'settings.json'), canonical(settings) + b'\n', plan['before_hashes']['settings'])]
    writes.extend(('launcher-' + name, checked_path(home, 'scripts/' + name), bytes.fromhex(content), plan['launcher_before'][name])
        for name, content in plan['launcher_payloads'].items())
    writes.append(('location', checked_path(home, 'state/wiki-automation/location.json'),
        canonical(plan['location']) + b'\n', plan['before_hashes']['location']))
    return writes


def validate_installation_recovery(plan: dict, expected_digest: str) -> dict:
    import sqlite3
    from workflow_store import WorkflowError
    try:
        return _validate_installation_recovery(plan, expected_digest)
    except (WorkflowError, sqlite3.DatabaseError) as exc:
        raise wikiconfig.ConfigError('Read-only installation or source journal unavailable or schema unsupported') from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise wikiconfig.ConfigError('Read-only installation state has unsupported JSON or record shape') from exc


def _validate_installation_recovery(plan: dict, expected_digest: str) -> dict:
    """Inspect original plan and native half-state without creating or repairing anything."""
    import hashlib
    from owner_decisions import canonical
    from workflow_paths import checked_path
    from workflow_store import WorkflowStore
    from candidate_apply import _retained_captures, _check_retained_captures, ApplyRefused
    unsigned = {key: value for key, value in plan.items() if key != 'digest'}
    if expected_digest != plan.get('digest') or hashlib.sha256(canonical(unsigned)).hexdigest() != expected_digest:
        raise wikiconfig.ConfigError('Recovery requires the exact original installation plan')
    home, code, data = map(unlinked_path, (plan['hermes_home'], plan['engine_dir'], plan['audit_dir']))
    project = wikiconfig.validate_project(plan['settings']['project_root'])
    if (not home.is_dir() or not code.is_dir() or not project['ok']
            or project['id'] != plan['project_id'] or project['path'] != plan['settings']['project_root']
            or plan.get('installer_interpreter') != str(unlinked_path(sys.executable).resolve())
            or code_fingerprints(code) != plan['code_hashes']):
        raise wikiconfig.ConfigError('Original profile, project or code identity changed')
    options = plan['settings'].get('install_options') or {}
    if options.get('no_plugin') is not True or type(options.get('no_cron')) is not bool:
        raise wikiconfig.ConfigError('Recovery is restricted to the original engine-only plan')
    meta = checked_path(home, 'state/wiki-automation')
    journal = checked_path(meta, 'installation.sqlite')
    operation, steps = None, []
    if journal.exists():
        with WorkflowStore(journal, read_only=True) as store:
            operation = store.get_operation(expected_digest)
            steps = store.steps(expected_digest)
    source = checked_path(data, 'workflow.sqlite')
    source_operations = []
    if source.exists():
        with WorkflowStore(source, read_only=True) as store:
            source_operations = [list(row) for row in store.db.execute('SELECT id,identity,state,result FROM operations ORDER BY id')]
            for row in source_operations:
                identity = json.loads(row[1])
                result = json.loads(row[3]) if row[3] is not None else None
                if (not isinstance(identity, dict) or identity.get('operation_id') != row[0]
                        or row[2] not in ('collected', 'drafted', 'prepared', 'awaiting_approval', 'applying', 'recovery_required', 'applied', 'rejected')
                        or (result is not None and not isinstance(result, dict))):
                    raise wikiconfig.ConfigError('Read-only source journal has unsupported records')
            if any(row[2] in ('applying', 'recovery_required') for row in source_operations):
                raise wikiconfig.ConfigError('Unfinished source application blocks installation recovery')
    if operation is None:
        if build_plan(plan['settings'], home, code, data)['digest'] != expected_digest:
            raise wikiconfig.ConfigError('Unstarted installation inputs changed')
    elif operation.get('plan') != plan or operation['state'] not in ('collected', 'prepared', 'applying', 'recovery_required', 'applied'):
        raise wikiconfig.ConfigError('Native original installation journal identity changed')
    jobs_path = checked_path(home, 'cron/jobs.json')
    jobs_raw = jobs_path.read_bytes() if jobs_path.exists() else None
    jobs = parse_native_jobs(jobs_raw)
    mapping = dict(plan['settings'].get('jobs') or {})
    for role, spec in plan['job_definitions'].items():
        matches = [job for job in jobs if job.get('origin') == {'engine_installation': expected_digest, 'engine_role': role}]
        previous = next((job for job in jobs if job['id'] == mapping.get(role)), None)
        captured = next((row for row in plan['existing_jobs'] if row['id'] == mapping.get(role)), None)
        recorded = next((step['result'] for step in steps if step['step'] == 'job-' + role), None)
        snapshot = next((step['result'] for step in steps if step['step'] == 'job-snapshot-' + role), None)
        if snapshot is not None:
            saved_job = snapshot['job_snapshot']
            if not any(job['id'] == saved_job['id'] and job.get('origin') == saved_job.get('origin') for job in jobs):
                raise wikiconfig.ConfigError('Snapshotted native installation job disappeared; recovery cannot repair it')
        if recorded is not None and not any(job['id'] == recorded['job_id'] and job.get('origin') == recorded.get('origin') for job in jobs):
            raise wikiconfig.ConfigError('Recorded native installation job disappeared; recovery cannot repair it')
        if captured is not None and previous is None:
            raise wikiconfig.ConfigError('Original captured owned job disappeared; recovery cannot repair it')
        if len(matches) > 1:
            raise wikiconfig.ConfigError('Ambiguous installation-owned job')
        job = matches[0] if matches else previous
        if job is not None and not matches and _is_adopted(role, job, plan):
            if _legacy_adoption_state(job, captured, legacy_adoption_updates(role, plan)) != 'pending':
                raise wikiconfig.ConfigError('Legacy job changed after preview; owner record was preserved')
            mapping[role] = job['id']
        elif job is not None:
            verify_job_role(job, role, plan)
            if matches and captured is None:
                _verify_new_installation_job(job, role, plan, snapshot if snapshot is not None else ({} if recorded is not None else None))
            captured_job = next((row for row in plan['existing_jobs'] if row['id'] == job['id']), None)
            if (not matches and captured_job != job
                    and _refresh_state(job, captured_job, role, plan) not in ('pending', 'applied')):
                raise wikiconfig.ConfigError('Existing managed job changed after original preview')
            mapping[role] = job['id']
        elif any(row.get('name') == spec['name'] for row in jobs):
            raise wikiconfig.ConfigError('Same-name job has no original installation ownership')
    settings = dict(plan['settings'])
    if options['no_cron'] is False:
        settings['jobs'] = mapping
    writes = _installation_projections(plan, settings)
    observed = {}
    for key, target, wanted, expected in writes:
        previous = target.read_bytes() if target.exists() else None
        digest = hashlib.sha256(previous).hexdigest() if previous is not None else None
        capture = checked_path(target.parent, f'.wiki-install-recovery/{expected_digest}/{key}/captured.bin')
        try:
            _check_retained_captures(capture, expected)
        except ApplyRefused as exc:
            raise wikiconfig.ConfigError('Original installation capture changed; no repair attempted') from exc
        retained = []
        for item in _retained_captures(capture):
            item = unlinked_path(item)
            if item != capture and not item.is_file():
                raise wikiconfig.ConfigError('Original installation recapture prefix is incomplete; no repair attempted')
            if item.exists():
                captured_hash = hashlib.sha256(item.read_bytes()).hexdigest()
                if captured_hash != expected:
                    raise wikiconfig.ConfigError('Original installation capture changed; no repair attempted')
                retained.append([str(item), captured_hash])
        if previous != wanted and digest != expected and not (previous is None and capture.is_file()):
            raise wikiconfig.ConfigError('Original installation projection drift preserved')
        if operation is not None and operation['state'] == 'applied' and previous != wanted:
            raise wikiconfig.ConfigError('Applied installation projection changed')
        observed[key] = [digest, retained]
    return {'ok': True, 'state': operation['state'] if operation is not None else 'unstarted', 'current_state_digest': hashlib.sha256(canonical(
        [plan, operation, steps, jobs_raw.hex() if jobs_raw is not None else None, observed, source_operations])).hexdigest()}


def apply_plan(plan: dict, expected_digest: str, *, expected_recovery_state=None) -> dict:
    """Apply the verified engine-only location slice; scheduler integration is separately gated."""
    import hashlib
    from contextlib import nullcontext, ExitStack
    from candidate_apply import operation_lock, publish_file, _check_retained_captures, _retained_capture_drift
    from owner_decisions import canonical
    from workflow_paths import checked_path
    from workflow_store import WorkflowStore
    unsigned = {key: value for key, value in plan.items() if key != 'digest'}
    if expected_digest != plan.get('digest') or hashlib.sha256(canonical(unsigned)).hexdigest() != expected_digest:
        raise wikiconfig.ConfigError('Installation confirmation does not match the exact preview')
    options = plan['settings'].get('install_options') or {}
    if options.get('no_plugin') is not True or type(options.get('no_cron')) is not bool:
        raise wikiconfig.ConfigError('Engine-only panel-free scope and explicit scheduler choice are required')
    home, code, data = map(unlinked_path, (plan['hermes_home'], plan['engine_dir'], plan['audit_dir']))
    # Refuse redirected projections before acquiring locks or creating metadata.
    for target in (data / 'settings.json', home / 'state/wiki-automation/location.json',
            home / 'cron/jobs.json', *[home / 'scripts' / name for name in plan['launcher_payloads']]):
        unlinked_path(target)
    project = wikiconfig.validate_project(plan['settings']['project_root'])
    if not project['ok'] or project['id'] != plan['project_id']:
        raise wikiconfig.ConfigError('Selected project identity changed; original confirmation is invalid')
    if code_fingerprints(code) != plan['code_hashes']:
        raise wikiconfig.ConfigError('Selected code release changed after preview; retry is refused')
    meta = checked_path(home, 'state/wiki-automation')
    # A retained data root may also hold installation metadata. Acquire its
    # canonical operation lock once, without moving or resetting owner data.
    if expected_recovery_state is not None:
        reviewed = validate_installation_recovery(plan, expected_digest)
        if reviewed['current_state_digest'] != expected_recovery_state:
            raise wikiconfig.ConfigError('Installation state changed after recovery review')
    data_lock = nullcontext() if data.resolve() == meta.resolve() else operation_lock(data)
    with operation_lock(meta), data_lock, ExitStack() as stack:
        if expected_recovery_state is not None:
            reviewed = validate_installation_recovery(plan, expected_digest)
            if reviewed['current_state_digest'] != expected_recovery_state:
                raise wikiconfig.ConfigError('Installation state changed after recovery review')
        store = stack.enter_context(WorkflowStore(checked_path(meta, 'installation.sqlite')))
        source_journal = checked_path(data, 'workflow.sqlite')
        if source_journal.exists():
            with WorkflowStore(source_journal, read_only=True) as workflow:
                if workflow.db.execute("SELECT 1 FROM operations WHERE state IN ('applying','recovery_required') LIMIT 1").fetchone():
                    raise wikiconfig.ConfigError('Unfinished source application must be recovered before installation')
        operation = store.get_operation(expected_digest)
        if operation is None:
            try:
                current = build_plan(plan['settings'], home, code, data)
            except wikiconfig.ConfigError as exc:
                raise PlanStale(str(exc)) from exc
            if current['digest'] != expected_digest:
                raise PlanStale('Installation inputs changed after preview; nothing was written')
            store.record_operation({'operation_id': expected_digest, 'type': 'installation', 'plan': plan})
        elif operation.get('plan') != plan:
            raise wikiconfig.ConfigError('Existing installation identity changed')
        operation = store.get_operation(expected_digest)
        captures = [('settings', checked_path(data, 'settings.json'), plan['before_hashes']['settings'])]
        captures.extend(('launcher-' + name, checked_path(home, 'scripts/' + name), plan['launcher_before'][name])
            for name in plan['launcher_payloads'])
        captures.append(('location', checked_path(home, 'state/wiki-automation/location.json'), plan['before_hashes']['location']))
        retained = [(checked_path(target.parent, f'.wiki-install-recovery/{expected_digest}/{key}/captured.bin'), expected)
            for key, target, expected in captures]
        if operation['state'] == 'applied':
            drift = False
            for capture, expected in retained:
                drift |= _retained_capture_drift(capture, expected)
            if drift:
                return {**operation['result'], 'later_drift': True}
        for capture, expected in retained:
            _check_retained_captures(capture, expected)
        if operation['state'] == 'collected':
            operation = store.transition(expected_digest, 'collected', 'prepared')
        if operation['state'] in ('prepared', 'recovery_required'):
            store.transition(expected_digest, operation['state'], 'applying')
        settings = dict(plan['settings'])
        if options['no_cron'] is False:
            settings['jobs'] = register_paused_jobs(plan, store)
        writes = _installation_projections(plan, settings)
        for key, target, wanted, expected_before in writes:
            capture = checked_path(target.parent, f'.wiki-install-recovery/{expected_digest}/{key}/captured.bin')
            _check_retained_captures(capture, expected_before)
            previous = target.read_bytes() if target.exists() else None
            if previous == wanted:
                continue
            observed = hashlib.sha256(previous).hexdigest() if previous is not None else None
            if observed != expected_before and not (previous is None and capture.exists()):
                raise wikiconfig.ConfigError(f'Existing {key} changed; nothing was overwritten')
            original = capture.read_bytes() if capture.exists() else previous
            store.record_step(expected_digest, 'before-' + key,
                {'path': str(target), 'bytes_hex': original.hex() if original is not None else None})
            publish_file(target, wanted, expected_before, capture)
            if target.read_bytes() != wanted:
                raise wikiconfig.ConfigError('Installed projection readback failed')
            store.record_step(expected_digest, 'written-' + key, {'sha256': hashlib.sha256(wanted).hexdigest()})
        for capture, expected in retained:
            _check_retained_captures(capture, expected)
        result = {'ok': True, 'state': 'location_recorded', 'installation_id': expected_digest}
        operation = store.get_operation(expected_digest)
        if operation['state'] == 'applying':
            store.transition(expected_digest, 'applying', 'applied', result)
        elif operation['state'] != 'applied' or operation['result'] != result:
            raise wikiconfig.ConfigError('Installation journal state is inconsistent')
        return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Wiki otomasyonu kurulumu / taşıma")
    parser.add_argument("--project-root", help="izlenecek LLM Wiki projesinin kökü")
    parser.add_argument("--hermes-home", help="Hermes kurulumu (varsayılan: otomatik bulunur)")
    parser.add_argument("--dry-run", action="store_true", help="hiçbir şey yazmadan ne yapılacağını yaz")
    parser.add_argument("--no-cron", action="store_true", help="zamanlanmış işleri kurma")
    parser.add_argument("--no-plugin", action="store_true", help="paneli kurma")
    parser.add_argument("--force", action="store_true",
                        help="başka bir commit'te duran paneli motorun commit'ine taşı")
    parser.add_argument('--data-root', help='Selected mutable engine data, separate from this code release')
    parser.add_argument('--plan-json', action='store_true')
    parser.add_argument('--apply-plan', help='Previously prepared private engine plan JSON')
    parser.add_argument('--expected-digest', help='Exact reviewed plan digest')
    parser.add_argument('--validate-recovery-plan', help='Read-only original installation recovery inspection')
    parser.add_argument('--expected-recovery-state', help='Exact native state reviewed for recovery')
    args = parser.parse_args(argv[1:])
    if args.data_root or args.plan_json or args.apply_plan or args.validate_recovery_plan:
        from candidate_apply import ApplyRefused
        from workflow_paths import PathRefused
        from workflow_store import WorkflowError
        import sqlite3
        try:
            if args.apply_plan or args.validate_recovery_plan:
                plan = json.loads(unlinked_path(args.apply_plan or args.validate_recovery_plan).read_bytes())
            else:
                home = unlinked_path(args.hermes_home if args.hermes_home else wikiconfig.hermes_home({'hermes_home': None}))
                data = unlinked_path(args.data_root if args.data_root else home / 'state/wiki-automation/data')
                settings = unlinked_path(data / 'settings.json')
                cfg = json.loads(settings.read_bytes()) if settings.exists() else {}
                if not isinstance(cfg, dict):
                    raise wikiconfig.ConfigError('Selected settings must be an object')
                cfg = {**cfg, 'hermes_home': str(home), 'audit_dir': str(data),
                    'project_root': args.project_root or cfg.get('project_root'),
                    'install_options': {'no_plugin': args.no_plugin, 'no_cron': args.no_cron}}
                plan = build_plan(cfg, home, AUDIT, data)
            if args.validate_recovery_plan:
                print(json.dumps(validate_installation_recovery(plan, args.expected_digest)))
                return 0
            if args.plan_json or args.dry_run:
                print(json.dumps(plan, ensure_ascii=False))
                return 0
            result = apply_plan(plan, args.expected_digest, expected_recovery_state=args.expected_recovery_state)
            print(json.dumps(result))
            return 0
        except (wikiconfig.ConfigError, ApplyRefused, PathRefused, WorkflowError, sqlite3.DatabaseError, OSError, ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, ValueError) and str(exc).startswith(('Linked path refused:', 'Hard-linked path refused:')):
                reason = 'Linked installation path refused; existing data was preserved'
            else:
                reason = (str(exc)[:240] if isinstance(exc, (wikiconfig.ConfigError, ApplyRefused, PathRefused, WorkflowError))
                    else 'Installation state is unreadable or unsupported; existing data was preserved')
            print(json.dumps({'ok': False, 'state': 'stale' if isinstance(exc, PlanStale) else 'refused', 'reason': reason}))
            return 1

    print(f"otomasyon klasörü: {AUDIT}")
    cfg = wikiconfig.load()

    # 1) AYAR: proje kökünü doğrula ve yaz
    root_arg = args.project_root or cfg.get("project_root")
    if not root_arg:
        print("!! proje kökü verilmedi: --project-root \"<wiki klasörü>\"")
        return 2
    info = wikiconfig.validate_project(root_arg)
    note(info["ok"], f"proje kökü: {info['path']}" + ("" if info["ok"] else f" — {info['reason']}"))
    if not info["ok"]:
        print("\nkurulum durdu: proje kökü doğrulanamadı (yanlış klasöre kurmak istemiyoruz)")
        return 2
    hermes_home = Path(args.hermes_home) if args.hermes_home else wikiconfig.hermes_home(cfg)
    patch = {"project_root": info["path"], "project_id": info["id"], "audit_dir": str(AUDIT),
             "hermes_home": str(hermes_home)}
    if args.dry_run:
        note(True, f"settings.json yazılacak: {wikiconfig.settings_path()}")
    else:
        cfg = wikiconfig.save(patch)
        note(True, f"settings.json yazıldı: {wikiconfig.settings_path()}")
    note(hermes_home.is_dir(), f"Hermes home: {hermes_home}")

    # 2) Cron giriş noktaları
    copy_launchers(hermes_home, args.dry_run)

    # 2b) Wiki commit kancaları (motorun wiki-hooks/ kopyasından)
    install_wiki_hooks(Path(info["path"]), args.dry_run)

    # 3) Panels: pinned Git installs (the desktop app copies their desktop half itself)
    if args.no_plugin:
        note(True, "panel adımı atlandı (--no-plugin)")
    else:
        install_panels(hermes_home, args.dry_run, force=args.force)
    write_location(hermes_home, args.dry_run)

    # 4) Zamanlanmış işler
    if args.no_cron:
        note(True, "cron adımı atlandı (--no-cron)")
    else:
        sync_jobs(cfg, hermes_home, args.dry_run)
        sync_agent_jobs(wikiconfig.load(), hermes_home, args.dry_run)

    # Watch Dog runs only as a Hermes cron job: Hermes runs a missed job once it is back up
    # (`cron.catch_up_missed`), so the Windows Task Scheduler twin and its popup were dropped.

    # 6) Doğrulama
    ok = verify(cfg, hermes_home, args.dry_run)

    print("\n== ÖZET ==")
    for status, text in report:
        print(f"  {status}  {text}")
    problems = [t for s, t in report if s != "OK  "]
    if problems or not ok:
        print(f"\n{len(problems)} eksik/hatalı adım var — yukarıdaki satırlara bak.")
        return 1
    print("\nkurulum tamam: scriptler koşuyor, işler kayıtlı, panel yerinde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

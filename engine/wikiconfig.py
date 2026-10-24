"""Tek ayar kaynağı — wiki otomasyonunun bütün yolları BURADAN gelir.

NEDEN: 2026-09-17'ye kadar her script kendi mutlak yolunu taşıyordu (wiki kökü,
otomasyon klasörü, venv python'u, ...). Bu, kurulumu o makineye bağlıyordu: klasörü
başka bir PC'ye kopyalayınca scriptler ya yanlış yere bakıyor ya da hiç çalışmıyordu. Artık
makineye özel TEK bir yol yok; hepsi `settings.json`ten okunur ve o dosya kullanıcı evinin altında
durur (`Path.home()` ile bulunur → her PC'de kendiliğinden doğru yer).

ÇÖZÜM SIRASI (tek yerde, bilinçli olarak bu kadar kısa):
  1. `LLMWIKI_SETTINGS` ortam değişkeni — yalnız TEST/taşıma provası için; üretimde kullanılmaz.
  2. `<kullanıcı evi>/.llmwiki-audit/settings.json` — normal durum.
  3. `<script klasörü>/settings.json` — paket kendi klasörüyle taşınıyorsa.
  4. Bunların hiçbiri yoksa: (2)'nin yolu kullanılır ve DOSYA YOKSAYILIR — yani `project_root`
     ayarsız kalır ve scriptler SESSİZ KALMAZ, "proje kökü seçilmemiş" diye alarm verir.
     Yanlış klasöre sessizce bakmak, hiç bakmamaktan kötüdür; bu yüzden varsayılan bir proje yolu
     ASLA gömülmez.

KOMUT SATIRI (panel ve kurulum aynı çözümleyiciyi kullansın diye):
    python wikiconfig.py show                     # çözülen ayarlar + doğrulama (JSON)
    python wikiconfig.py set project_root=<yol>   # tek alanı yaz (diğerleri korunur)
    python wikiconfig.py validate <yol>           # bir klasör wiki kökü mü?
    python wikiconfig.py derive <seçilen dosya>   # seçilen dosyadan proje kökünü türet
    python wikiconfig.py candidates [tarama kökü]   # altındaki wiki projeleri (kök verilmezse
                                                     # ayardaki scan_root → mevcut kökün üstü)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

SETTINGS_NAME = "settings.json"
AUDIT_DIR_NAME = ".llmwiki-audit"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_AUDIT_DIR = Path.home() / AUDIT_DIR_NAME
# Proje kökünü tanımanın tek yolu: uygulamanın kimlik dosyası. Yoksa o klasör wiki DEĞİLDİR.
IDENTITY = Path(".llm-wiki") / "project.json"
MAX_WALK_UP = 8      # seçilen dosyadan yukarı yürüme sınırı
# ADAY TARAMASI: derinlik PROJE köküne göre sayılır (kimlik dosyasının kendi derinliğine göre DEĞİL).
# Eski sabit kimlik dosyasını sayıyordu → "4" yazıyor ama gerçekte 2 seviye tarıyordu (ölçüldü).
MAX_SCAN_DEPTH = 3     # tarama köküne göre en fazla kaç seviye alt klasörde proje aranır
MAX_SCAN_DIRS = 20000  # güvenlik tavanı: bu kadar klasör gezilirse tarama KESİLİR ve bu bildirilir

DEFAULTS = {
    # İZLENEN PROJE — çakılı değil, seçilir. Boş bırakılırsa scriptler alarm verir.
    "project_root": None,
    # ADAY TARAMASININ başlayacağı klasör. Boş → mevcut kökün üst klasörü. Kök HENÜZ ayarsızken
    # (yeni PC, ilk kurulum) keşfin çalışabilmesi için ayrı bir alan: eskiden tarama kökü örtük
    # olarak mevcut kökten türetiliyordu ve tam da gerektiği anda (kök yokken) hiçbir şey taramıyordu.
    "scan_root": None,
    # Projenin beklenen kimliği (`.llm-wiki/project.json` → id). Kurulum yazar; boşsa kimlik
    # kontrolü ATLANIR (başka PC'de kimlik farklıdır, yanlış alarm üretilmez).
    "project_id": None,
    # Otomasyon klasörü (scriptler + durum dosyaları). Boş → script klasörü.
    "audit_dir": None,
    # Hermes kurulumu. Boş → HERMES_HOME ya da %LOCALAPPDATA%/hermes.
    "hermes_home": None,
    # LLM Wiki uygulamasının yerel API'si ve durum dosyası. Boş → platform varsayılanı.
    "api_base": "http://127.0.0.1:19828",
    "app_state": None,
    # Kapılar (dakika / sayı) — davranış ayarı, kod değil.
    "gates": {
        "quiet_minutes": 5,
        "tmp_max_minutes": 15,
        "lock_max_minutes": 30,
        "page_drop": 3,
        "isolated_alert": 1,
        "inflight_minutes": 10,
        "rescan_after_minutes": 0,
        "escalate_minutes": 45,
    },
    # Zamanlama: kurulum (install.py) bu değerlerle cron işlerini kurar.
    "schedule": {"autocommit": "0 9 * * *", "ingest_watch": "0 9 * * *", "watchdog": "0 9 * * *"},
    # Uyarı teslimi (cron `--deliver`): `local` = yalnız kayıt (panelin Health sekmesi gösterir);
    # ntfy / bot-chat / origin de verilebilir.
    "deliver": "local",
    # Kurulu işlerin kimlikleri — kurulum yazar, taşımada install.py günceller. Kodda kimlik YOKTUR:
    # başka bir kurulumun kimlikleri burada dururken panel var olmayan işleri sayıyordu.
    "jobs": {},
    # Yedek (ayna) olarak denetlenen git uzaklıkları. Boş (None) → wiki deposunun BÜTÜN uzaklıkları
    # (post-commit kancası da hepsine iter); [] → yedek denetimi yok; liste → yalnız o adlar.
    "mirrors": None,
    # drift_check'in kuruluma özel beklentileri. Boşsa watchdog ajan-kurulum denetimini (drift_check)
    # hiç ÇALIŞTIRMAZ: o denetim tek bir kurulumun skill/eklenti düzenini anlatır, herkesinkini değil.
    # İsteğe bağlı `drift.agents` (ör. ["hermes", "antigravity"]): bu makinede kurulu ajanlar; listede
    # olmayan bir aracın eksik bileşeni/skill'i sapma sayılmaz. Yoksa dört ajan da beklenir.
    "drift": {"expect": {}},
}


class ConfigError(RuntimeError):
    """Ayar eksik/geçersiz — scriptler bunu kullanıcıya alarm olarak basar."""


def settings_path() -> Path:
    """Ayar dosyasının yolu (çözüm sırası yukarıdaki docstring'de)."""
    env = os.environ.get("LLMWIKI_SETTINGS")
    if env:
        return Path(env)
    for cand in (DEFAULT_AUDIT_DIR / SETTINGS_NAME, SCRIPT_DIR / SETTINGS_NAME):
        if cand.exists():
            return cand
    return DEFAULT_AUDIT_DIR / SETTINGS_NAME


def _merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict:
    """Varsayılanlar ⊕ settings.json. Dosya yoksa varsayılanlar döner (project_root = None)."""
    cfg = json.loads(json.dumps(DEFAULTS))
    path = settings_path()
    if path.exists():
        try:
            cfg = _merge(cfg, json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise ConfigError(f"{path} okunamadı: {exc}") from exc
    return cfg


def save(patch: dict) -> dict:
    """Ayarları yerinde günceller (diğer alanlar korunur) ve yeni hâli döndürür."""
    path = settings_path()
    current = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ConfigError('Existing settings are unreadable; preserve them before attempting an update') from exc
    merged = _merge(current, patch or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return load()


def validate_location(record: dict) -> tuple[Path, Path]:
    if not isinstance(record, dict):
        raise ConfigError('Profile engine location must be an object')
    schema = record.get('schema', 1)
    if type(schema) is not int or schema not in (1, 2):
        raise ConfigError('Unsupported engine location schema; no reset is allowed')
    values = (record.get('engine_dir') if schema == 2 else record.get('audit_dir'), record.get('audit_dir'))
    if any(not isinstance(value, str) or not value or not Path(value).is_absolute() for value in values):
        raise ConfigError('Engine location must contain absolute code and data roots')
    code, data = map(Path, values)
    if not code.is_dir() or not data.is_dir():
        raise ConfigError('Existing selected code or data root is missing; no fallback is allowed')
    return code, data


def engine_dir(cfg: dict | None = None) -> Path:
    """Read this profile's selected code location without mutating its data root."""
    cfg = cfg or load()
    location = hermes_home(cfg) / 'state/wiki-automation/location.json'
    raw = None
    if location.exists():
        try:
            record = json.loads(location.read_bytes())
            if not isinstance(record, dict):
                raise ValueError('Location must be an object')
            schema = record.get('schema', 1)
            if type(schema) is not int or schema not in (1, 2):
                raise ValueError('Unsupported location schema')
            raw = record.get('engine_dir') if schema == 2 else record.get('audit_dir')
            if not isinstance(raw, str) or not raw:
                raise ValueError('Location has no selected code root')
        except (OSError, ValueError) as exc:
            raise ConfigError('Profile engine location is unreadable; no fallback is allowed') from exc
    else:
        raw = cfg.get('engine_dir')
    root = Path(raw) if raw else SCRIPT_DIR
    if not root.is_dir():
        raise ConfigError('Selected engine code root is absent')
    return root


def audit_dir(cfg: dict | None = None) -> Path:
    """Resolve configured mutable data; a missing configured root is never code fallback."""
    cfg = cfg or load()
    raw = cfg.get("audit_dir")
    if raw:
        if not Path(raw).is_dir():
            raise ConfigError('Configured automation data root is missing; select or restore it before running')
        return Path(raw)
    return SCRIPT_DIR


def hermes_home(cfg: dict | None = None) -> Path:
    cfg = cfg or load()
    raw = cfg.get("hermes_home")
    if raw:
        if not Path(raw).is_dir():
            raise ConfigError('Configured Hermes profile home is absent; no other profile may be substituted')
        return Path(raw)
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local and (Path(local) / "hermes").exists():
        return Path(local) / "hermes"
    return Path.home() / ".hermes"


def app_state(cfg: dict | None = None) -> Path:
    """LLM Wiki uygulamasının durum dosyası (uygulama ayarlarını orada tutar)."""
    cfg = cfg or load()
    raw = cfg.get("app_state")
    if raw and Path(raw).exists():
        return Path(raw)
    roaming = os.environ.get("APPDATA")
    base = Path(roaming) if roaming else Path.home() / "AppData" / "Roaming"
    candidate = base / "com.llmwiki.app" / "app-state.json"
    if candidate.exists():
        return candidate
    return Path(raw) if raw else candidate


def mirror_remotes(cfg: dict, root: Path) -> list[str]:
    """Yedek olarak denetlenecek git uzaklıkları: `mirrors` bir listeyse o liste ([] = denetim yok),
    değilse wiki deposunun tanımlı bütün uzaklıkları. Uzaklık adı koda gömülmez."""
    listed = cfg.get("mirrors")
    if isinstance(listed, list):
        return [str(name) for name in listed]
    out = subprocess.run(["git", "-C", str(root), "remote"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=30)
    return out.stdout.split() if out.returncode == 0 else []


def project_root(cfg: dict | None = None) -> Path:
    """İzlenen wiki kökü. AYARSIZSA/GEÇERSİZSE hata verir — sessiz varsayılan YOKTUR."""
    cfg = cfg or load()
    raw = cfg.get("project_root")
    if not raw:
        raise ConfigError(f"proje kökü seçilmemiş ({settings_path()})")
    root = Path(raw)
    if not root.exists():
        raise ConfigError(f"proje kökü bulunamadı: {root}")
    return root


def wiki_dir(cfg: dict | None = None) -> Path:
    return project_root(cfg) / "wiki"


def validate_project(path: str | Path) -> dict:
    """Bir klasörün wiki kökü olup olmadığını kanıtla: kimlik dosyası + beklenen klasörler."""
    root = Path(path)
    out = {"path": str(root), "ok": False, "reason": "", "id": None, "pages": 0}
    if not root.exists() or not root.is_dir():
        out["reason"] = "klasör yok"
        return out
    ident = root / IDENTITY
    if not ident.exists():
        out["reason"] = f".llm-wiki/project.json yok — bu klasör bir wiki kökü değil"
        return out
    try:
        out["id"] = json.loads(ident.read_text(encoding="utf-8")).get("id")
    except (OSError, ValueError):
        out["reason"] = ".llm-wiki/project.json okunamadı"
        return out
    if not (root / "wiki").is_dir():
        out["reason"] = "wiki/ klasörü yok"
        return out
    try:
        out["pages"] = sum(1 for _ in (root / "wiki").rglob("*.md"))
    except OSError:
        pass
    out["ok"] = bool(out["id"]) and out["pages"] > 0
    if not out["ok"]:
        out["reason"] = out["reason"] or "wiki/ boş ya da kimlik eksik"
    return out


def derive_root(picked: str | Path) -> Path | None:
    """Bir dosya seçildiğinde proje kökünü bul: seçilen yoldan yukarı yürüyüp kimliği arar.

    Klasör seçici her platformda yok (Hermes plugin SDK'sı yalnız tek DOSYA seçtirir), bu yüzden
    panel klasörün içinden bir dosya seçtirir ve kök burada türetilir."""
    path = Path(picked)
    start = path if path.is_dir() else path.parent
    for _ in range(MAX_WALK_UP):
        if (start / IDENTITY).exists():
            return start
        if start.parent == start:
            break
        start = start.parent
    return None


def scan_root(cfg: dict | None = None) -> Path | None:
    """Aday taramasının başlayacağı klasör: ayar (`scan_root`) → mevcut kökün ÜST klasörü.

    Kök ayarsızken de bir yer dönebilir (ayardan); ikisi de yoksa None → çağıran AÇIK hata verir.
    """
    cfg = cfg or load()
    explicit = cfg.get("scan_root")
    if explicit:
        return Path(explicit)
    root = cfg.get("project_root")
    if root:
        return Path(root).parent
    return None


def candidates(scan_root_arg: str | Path) -> dict:
    """Tarama kökünün altındaki wiki projelerini bul — KİMLİĞE GÖRE TEKİLLEŞTİREREK.

    Dönen sözlük: `{ok, root, found, scanned, skipped, truncated, depth_limit}`.
    `found` girdileri: `{root, id, pages, duplicates}` — `duplicates`, AYNI kimliği taşıyan başka
    yolların listesidir (yerel kopya + OneDrive aynası gibi). Bu alan olmadan ikinci kopya "başka
    proje" gibi görünüyordu ve kök oraya alındığında aynı-karşılaştırmalı yedek denetimi kendisiyle
    karşılaştırmaya dönerdi (sessiz anlamsızlaşma).

    Ölçüt `validate_project`tir: aday listesi ile KAYIT KAPISI aynı kuralı kullanır.
    Okunamayan klasörler SAYILIR (`skipped`) — "bulunamadı" ile "tarayamadım" karışmasın.
    """
    root = Path(scan_root_arg)
    out = {"ok": True, "root": str(root), "found": [], "scanned": 0, "skipped": 0,
           "truncated": False, "depth_limit": MAX_SCAN_DEPTH}
    if not root.exists() or not root.is_dir():
        return {**out, "ok": False, "reason": "tarama kökü yok: " + str(root)}
    hits: list[Path] = []
    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        if out["scanned"] >= MAX_SCAN_DIRS:
            out["truncated"] = True
            break
        try:
            entries = list(os.scandir(current))
        except OSError:
            out["skipped"] += 1
            continue
        out["scanned"] += 1
        if (current / IDENTITY).exists():
            hits.append(current)
            continue  # bir projenin İÇİNE inmeyiz: iç içe proje aramıyoruz
        if depth >= MAX_SCAN_DEPTH:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    queue.append((Path(entry.path), depth + 1))
            except OSError:
                out["skipped"] += 1
    projects: list[dict] = []
    for path in sorted(set(hits), key=lambda p: str(p).lower()):
        info = validate_project(path)
        if info["ok"]:
            projects.append({"root": info["path"], "id": info["id"], "pages": info["pages"]})
    by_id: dict = {}
    for item in projects:
        by_id.setdefault(item["id"], []).append(item["root"])
    for item in projects:
        item["duplicates"] = [r for r in by_id.get(item["id"], []) if r != item["root"]]
    out["found"] = projects
    return out


def snapshot(cfg: dict | None = None) -> dict:
    """Panel ve kurulum için özet: çözülen yollar + proje doğrulaması."""
    cfg = cfg or load()
    path = settings_path()
    raw = cfg.get("project_root")
    info = validate_project(raw) if raw else {"path": None, "ok": False, "reason": "proje kökü seçilmemiş",
                                              "id": None, "pages": 0}
    return {
        "settings_path": str(path),
        "settings_exists": path.exists(),
        "project_root": raw,
        "project": info,
        "project_id": cfg.get("project_id"),
        "audit_dir": str(audit_dir(cfg)),
        "hermes_home": str(hermes_home(cfg)),
        "app_state": str(app_state(cfg)),
        "api_base": cfg.get("api_base"),
        "gates": cfg.get("gates"),
        "schedule": cfg.get("schedule"),
        # İş kimlikleri: panel "kaç iş kayıtlı"yı ve işlerin son koşularını buradan bulur.
        # Bu alan `show` çıktısında yokken panel sayacı boş kalıyordu ("—", yaşandı).
        "jobs": cfg.get("jobs"),
        "scan_root": cfg.get("scan_root"),
    }


def _main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "show"
    if cmd == "show":
        print(json.dumps(snapshot(), indent=2, ensure_ascii=False))
        return 0
    if cmd == "set":
        patch: dict = {}
        for arg in argv[2:]:
            if "=" not in arg:
                print(json.dumps({"ok": False, "error": f"beklenen anahtar=değer: {arg}"}))
                return 2
            key, value = arg.split("=", 1)
            patch[key] = value or None
        merged = save(patch)
        print(json.dumps({"ok": True, "settings_path": str(settings_path()),
                          "project_root": merged.get("project_root")}, ensure_ascii=False))
        return 0
    if cmd == "validate":
        if len(argv) < 3:
            print(json.dumps({"ok": False, "reason": "yol gerekli", "error": "yol gerekli"}))
            return 2
        print(json.dumps(validate_project(argv[2]), ensure_ascii=False))
        return 0
    if cmd == "derive":
        if len(argv) < 3:
            print(json.dumps({"ok": False, "reason": "yol gerekli", "error": "yol gerekli"}))
            return 2
        root = derive_root(argv[2])
        if root is None:
            print(json.dumps({"ok": False,
                              "reason": "seçilen yolun üstünde .llm-wiki/project.json yok — wiki "
                                        "klasörünün İÇİNDEN bir dosya seç",
                              "error": "seçilen yolun üstünde .llm-wiki/project.json yok",
                              "picked": argv[2]}, ensure_ascii=False))
            return 1
        info = validate_project(root)
        print(json.dumps({"ok": info["ok"], "root": str(root), **info}, ensure_ascii=False))
        return 0 if info["ok"] else 1
    if cmd == "candidates":
        cfg = load()
        root = argv[2] if len(argv) > 2 else scan_root(cfg)
        if not root:
            print(json.dumps({"ok": False, "reason": "tarama kökü belirsiz — bir klasör seç",
                              "error": "tarama kökü gerekli"}, ensure_ascii=False))
            return 2
        print(json.dumps(candidates(root), ensure_ascii=False))
        return 0
    print(json.dumps({"ok": False, "error": f"bilinmeyen komut: {cmd}"}))
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))

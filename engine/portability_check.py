"""Taşınabilirlik kapısı — kodda makineye özel mutlak yol kalmış mı, ve ayar gerçekten okunuyor mu?

İKİ SORU:
  1. STATİK: otomasyon paketindeki kod (scriptler, launcher'lar, panel backend'i, `.cmd`) içinde
     `C:/...`, `C:\\...`, `/Users/...` gibi makineye bağlı bir yol var mı? Docstring ve yorumlar
     SAYILMAZ (açıklama metni zararsızdır); sayılan şey ÇALIŞAN koddaki metin sabitidir, çünkü
     taşındığında yanlış yere bakan yol odur. Doğru yer: `settings.json` (bkz. wikiconfig.py).
  2. PROVA (`--prove`): `LLMWIKI_SETTINGS` geçici bir ayar dosyasına çevrilip script GERÇEKTEN
     koşturulur. Ayar geçersizse (proje kökü yok) script SESSİZ KALMAMALI, açık hata verip
     sıfırdan farklı çıkmalıdır: "yanlış klasöre sessizce bakmak" bu paketin kabul etmediği hâldir.

Kullanım:
    python portability_check.py            # statik denetim (hızlı)
    python portability_check.py --prove    # statik + geçici ayarla gerçek koşum provası
Çıkış kodu 1 = taşınabilirlik bozuk.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

AUDIT = Path(__file__).resolve().parent
sys.path.insert(0, str(AUDIT))
import wikiconfig  # Hermes home'u taşınabilir şekilde çözmek için (panel dosyalarını taramak üzere)
# Kod sayılan dosyalar: paketin kendisi + Hermes tarafındaki panel backend'i.
# Every `.cmd` launcher is code: agents start the MCP server through `llm-wiki-mcp.cmd`, and when only
# `run_watchdog.cmd` was named here a user-specific path in the other launcher went unseen.
CODE_FILES = [*sorted(AUDIT.glob("*.py")), *sorted((AUDIT / "launchers").glob("*.py")),
              *sorted(AUDIT.glob("*.cmd"))]
# Panelin KENDİ kodu da taranır: orada bir kez sabit yol kaldı (`AUDIT_DIR = Path("C:/Users/…")`)
# ve taşınan pakette panel yanlış klasöre bakardı. Yol Hermes home'undan türetilir (taşınabilir).
# DİKKAT: burada `try/except` ile yutma YOK — ilk yazımda NameError yutulmuştu ve panel dosyaları
# sessizce hiç taranmamıştı (kapı yeşil görünüyordu). Panel bulunamazsa bu bir SORUNDUR, sessizlik değil.
# PANELLER: hepsi taranır. Tek bir panel adı sabitlenirse yeni bir panel sessizce taranmadan kalır
# (bu hata sınıfı yaşandı: panel dosyaları hiç taranmıyordu ve kapı yeşil görünüyordu).
_PLUGINS_DIR = wikiconfig.hermes_home() / "plugins"
for _dir in sorted(p for p in _PLUGINS_DIR.glob("*") if (p / "desktop" / "plugin.js").exists()):
    CODE_FILES += [*sorted((_dir / "dashboard").glob("*.py")), _dir / "desktop" / "plugin.js"]
# Desenler: sabit yol GERÇEKTEN yol gibi görünmeli. İki tuzak yaşandı ve düzeltildi:
#   - `^sources:\s*\[` gibi REGEX metinleri "s:\" olarak eşleşiyordu → sürücü harfinden önce
#     harf/rakam/iki nokta gelmemeli (`http://…` ve `\s` böyle elenir).
#   - `C:/` tek başına da yoldur; bu yüzden sabitin BAŞINDA olma hâli ayrıca aranır.
PATTERNS = (
    re.compile(r"^[A-Za-z]:[\\/]"),                                   # sabit yolun kendisi: "C:/", "D:\\..."
    re.compile(r"(?:^|[^A-Za-z0-9_:/\\])[A-Za-z]:[\\/][A-Za-z0-9_.\-]+(?:[\\/][A-Za-z0-9_.\- ]+)+"),
    re.compile(r"^/(?:Users|home)/"),                                 # POSIX karşılığı
)
# Bilinçli istisnalar: bu dosyalar makineye özel bir şey TANIMLAMAZ, yalnız örnek gösterir.
ALLOW = {
    "install.py",          # dokümantasyon örneği: --project-root "D:/Wiki/MyWiki"
    "portability_check.py",
    "drift_check.py",      # farklı araçların klasör adlarını (.codex, .claude) arar; yollar ev-göreli
}


def literals(path: Path) -> list[tuple[int, str]]:
    """Çalışan koddaki metin sabitleri (docstring'ler hariç). .py olmayanlar satır satır taranır."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix != ".py":
        out: list[tuple[int, str]] = []
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("rem", "#")):
                continue          # .cmd yorumları
            out.append((i, line))
        return out
    tree = ast.parse(text)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.append((getattr(node, "lineno", 0), node.value))
    return found


def scan() -> list[str]:
    problems: list[str] = []
    for path in CODE_FILES:
        if not path.exists() or path.name in ALLOW:
            continue
        for lineno, value in literals(path):
            if any(pat.search(value) for pat in PATTERNS):
                problems.append(f"{path.name}:{lineno}: {value.strip()[:90]}")
    return problems


def prove() -> list[str]:
    """Geçici ayarla gerçek koşum: ayar geçersizse script AÇIK hata vermeli (sessiz kalmamalı)."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="wiki-portability-") as tmp:
        bad = Path(tmp) / "settings.json"
        bad.write_text(json.dumps({"project_root": str(Path(tmp) / "olmayan-wiki")}), encoding="utf-8")
        env = dict(os.environ, LLMWIKI_SETTINGS=str(bad))
        for script, label in (("wiki_ingest_watch.py", "ingest watch"),
                              ("wiki_autocommit.py", "auto-commit"),
                              ("watchdog.py", "watchdog")):
            target = AUDIT / script
            proc = subprocess.run([sys.executable, "-B", str(target)], capture_output=True, text=True,
                                 encoding="utf-8", errors="ignore", env=env, timeout=180)
            out = (proc.stdout or "") + (proc.stderr or "")
            loud = "ayar sorunu" in out and "project_root" in out
            if proc.returncode == 0 or not loud:
                problems.append(f"{label}: geçersiz ayarla sessiz kaldı (çıkış {proc.returncode}) — "
                                f"yanlış klasöre bakma riski")
            else:
                print(f"  ✓ {label}: geçersiz ayarda açık hata verdi (çıkış {proc.returncode})")

        # İkinci prova: GEÇERLİ geçici ayar (var olan proje kökü) → scriptler normal çalışmalı.
        # Ayar dosyasının kendisi taşınabilirliğin kanıtıdır: kod değişmeden başka bir köke bakar.
        real = json.loads((AUDIT / "settings.json").read_text(encoding="utf-8"))
        if real.get("project_root"):
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps({"project_root": real["project_root"]}), encoding="utf-8")
            env2 = dict(os.environ, LLMWIKI_SETTINGS=str(good))
            proc = subprocess.run([sys.executable, "-B", str(AUDIT / "wiki_audit.py")], capture_output=True,
                                  text=True, encoding="utf-8", errors="ignore", env=env2, timeout=240)
            if proc.returncode != 0:
                problems.append(f"wiki_audit.py: geçici geçerli ayarla koşmadı (çıkış {proc.returncode}): "
                                f"{(proc.stdout or proc.stderr or '')[-160:]}")
            else:
                print("  ✓ wiki_audit: geçici GEÇERLİ ayarla okudu (kod değişmedi, kök ayardan geldi)")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Taşınabilirlik kapısı")
    parser.add_argument("--prove", action="store_true", help="geçici ayarla gerçek koşum provası da yap")
    args = parser.parse_args(argv[1:])

    print("== 1) statik: kodda makineye özel mutlak yol ==")
    problems = scan()
    if problems:
        for line in problems:
            print(f"  × {line}")
        print(f"  {len(problems)} satırda sabit yol var — settings.json'e taşı (wikiconfig.py)")
    else:
        print(f"  ✓ {len(CODE_FILES)} dosyada sabit yol yok (docstring/yorum hariç)")

    if args.prove:
        print("\n== 2) prova: geçici ayarla gerçek koşum ==")
        problems += prove()

    print("\n== SONUÇ ==")
    if problems:
        print(f"  {len(problems)} sorun — paket bu hâliyle başka bir PC'ye taşınamaz.")
        return 1
    print("  taşınabilir: kodda makineye özel yol yok, ayar okunuyor, geçersiz ayar açıkça hata veriyor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

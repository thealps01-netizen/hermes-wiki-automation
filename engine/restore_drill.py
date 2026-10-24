"""Restore drill: prove the OneDrive mirror can rebuild the wiki.

Clones the bare mirror into a temp dir, then compares it file-by-file against the live wiki
(sha256 of every tracked file), checks the commit history and the two control files.
Read-only with respect to both the mirror and the live wiki. Temp clone is removed at the end.
"""
import hashlib, pathlib, re as _re, shutil, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wikiconfig  # tek ayar kaynağı; proje ve yedek yolu koda gömülü DEĞİL

try:
    WIKI = wikiconfig.project_root()
except wikiconfig.ConfigError as exc:
    print(f"!! ayar sorunu: {exc}")
    raise SystemExit(2)


def mirror_url() -> str:
    """Ayna adresini PROJENİN kendi git yapılandırmasından oku (`onedrive` uzaklığı).

    Böylece yedek yolu da koda gömülmez: başka bir PC'de uzaklık neyi gösteriyorsa odur.
    Yoksa `settings.json` → `backup_mirror` kullanılır."""
    cfg_file = WIKI / ".git" / "config"
    if cfg_file.exists():
        text = cfg_file.read_text(encoding="utf-8", errors="ignore")
        # `(.+)` re.S ile dosyanın SONUNA kadar yakalıyordu (fetch satırını da alıp clone'u bozuyordu):
        # satır sonunda dur.
        m = _re.search(r'\[remote "onedrive"\][^\[]*?url\s*=\s*([^\n\r]+)', text, _re.S)
        if m:
            return m.group(1).strip()
    return str(wikiconfig.load().get("backup_mirror") or "")


MIRROR = mirror_url()
if not MIRROR:
    print("!! yedek ayna adresi yok: projede 'onedrive' uzaklığı tanımlı değil ve settings.json'da "
          "'backup_mirror' boş")
    raise SystemExit(2)
tmp = pathlib.Path(tempfile.mkdtemp(prefix="wiki-restore-drill-"))
clone = tmp / "restore"

def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="ignore")

r = run("git", "clone", "--quiet", MIRROR, str(clone))
print(f"klon: exit={r.returncode} {r.stderr.strip()[:120]}")

tracked = run("git", "-C", str(WIKI), "ls-files").stdout.split()
live_hashes = {}
for rel in tracked:
    p = WIKI / rel
    live_hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "EKSİK"

mismatch, missing = [], []
for rel, digest in live_hashes.items():
    p = clone / rel
    if not p.exists():
        missing.append(rel)
        continue
    if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
        mismatch.append(rel)

print(f"izlenen dosya (yerel): {len(tracked)}")
print(f"klonda eksik dosya : {len(missing)}")
print(f"içerik farklı      : {len(mismatch)}")
print("komut geçmişi      :", run('git', '-C', str(clone), 'log', '--oneline').stdout.count("\n"), "commit")
print("son commit         :", run('git', '-C', str(clone), 'log', '-1', '--oneline').stdout.strip())
for name in ("purpose.md", "schema.md"):
    a = hashlib.sha256((WIKI / name).read_bytes()).hexdigest()[:12]
    b = hashlib.sha256((clone / name).read_bytes()).hexdigest()[:12]
    print(f"  {name:12} yerel={a} klon={b} {'AYNI' if a == b else 'FARKLI'}")

ok = not missing and not mismatch
print("\nSONUÇ:", "geri yükleme ÇALIŞIYOR (yedek kullanılabilir)" if ok else "SORUN: yedek eksik/farklı")
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(0 if ok else 1)

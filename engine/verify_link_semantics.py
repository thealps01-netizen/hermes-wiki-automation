"""Prove the link-form normalization was semantics-preserving.

Builds the (source page -> target page) edge set twice:
  BEFORE = commit <base>, resolving targets the way the raw text reads (last path segment)
  AFTER  = working tree / HEAD, resolving targets by stem
Then compares the sets. Any difference is a real change of meaning.
"""
import re, subprocess, sys, collections, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wikiconfig  # tek ayar kaynağı; depo yolu koda gömülü DEĞİL

REPO = str(wikiconfig.project_root())
BASE = sys.argv[1] if len(sys.argv) > 1 else "9c51841"   # commit before normalization
RX = re.compile(r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\|[^\]]+?)?\]\]")


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="ignore").stdout


def file_list(rev):
    if rev == "WORKTREE":
        return sorted(p.relative_to(REPO).as_posix()
                      for p in pathlib.Path(REPO, "wiki").rglob("*.md"))
    return sorted(f for f in git("ls-tree", "-r", "--name-only", rev, "wiki/").split() if f.endswith(".md"))


def read(rev, path):
    if rev == "WORKTREE":
        return pathlib.Path(REPO, path).read_text(encoding="utf-8", errors="ignore")
    return git("show", f"{rev}:{path}")


def edges(rev, resolve):
    files = file_list(rev)
    stems = {pathlib.Path(f).stem for f in files}
    out = set()
    for f in files:
        src = pathlib.Path(f).stem
        for raw in RX.findall(read(rev, f)):
            t = raw.strip()
            t = t[:-3] if t.lower().endswith(".md") else t
            target = resolve(t, stems)
            if target and target != src:
                out.add((src, target))
    return out, len(files)


before, nb = edges(BASE, lambda t, s: t.split("/")[-1] if t.split("/")[-1] in s else None)
after, na = edges("WORKTREE", lambda t, s: t.split("/")[-1] if t.split("/")[-1] in s else None)

print(f"BEFORE ({BASE}): {nb} dosya, {len(before)} kenar (kaynak->hedef, tekilleştirilmiş)")
print(f"AFTER (çalışma alanı): {na} dosya, {len(after)} kenar")
lost = before - after
gained = after - before
print(f"\nkaybolan kenar: {len(lost)}")
for s, t in sorted(lost)[:15]:
    print(f"   {s} -> {t}")
print(f"yeni kenar: {len(gained)}")
for s, t in sorted(gained)[:15]:
    print(f"   {s} -> {t}")
print("\nSONUÇ:", "anlam korunmuş (kenar kümesi aynı)" if not lost and not gained else "FARK VAR - incele")

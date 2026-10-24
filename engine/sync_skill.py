"""Sync one skill between the agent skill roots on this machine, safely.

  python sync_skill.py <skill-name> --from hermes --to codex [--dry-run] [--force]

Roots:
  hermes      ~/AppData/Local/hermes/skills      (Hermes: rich frontmatter, category subdirs)
  codex       ~/.agents/skills                   (Codex: name + description + author only)
  claude      ~/.claude/skills                   (Claude Code: name + description + author only)
  antigravity ~/.gemini/config/skills            (Antigravity 2.0 global skills: name + description + author only;
                                                  the pre-2.0 ~/.gemini/antigravity/skills is no longer read)

Rules encoded here:
  - the target keeps ITS OWN frontmatter (so each tool's matcher keeps working); only the body
    and the supporting files (references/, scripts/, templates/, assets/) come from the source
  - a target that does not exist yet is created with the mirror form of the frontmatter
    (name + description + author), never with Hermes' rich frontmatter
  - the target's line-ending style is preserved
  - the target directory is backed up under ~/.llmwiki-audit/backups/ before any change
  - skills whose name is ambiguous (deliberately different per tool) refuse to sync without --force
  - verification: body hash of source vs target must match afterwards
"""
from __future__ import annotations
import argparse, datetime, hashlib, pathlib, re, shutil, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wikiconfig  # tek ayar kaynağı; kökler koda gömülü DEĞİL

HOME = pathlib.Path.home()
HROOT = wikiconfig.hermes_home()
ROOTS = {
    "hermes": HROOT / "skills",
    "codex": HOME / ".agents/skills",
    "claude": HOME / ".claude/skills",
    "antigravity": HOME / ".gemini/config/skills",
}
AMBIGUOUS = {"llm-wiki": "Hermes: yazım/yöntem skill'i | codex+claude: uygulamanın API skill'i"}
BACKUP_ROOT = HOME / ".llmwiki-audit/backups"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def frontmatter(text: str) -> str:
    m = re.match(r"^(---\r?\n.*?\r?\n---\r?\n)", text, re.S)
    return m.group(1) if m else ""


def body(text: str) -> str:
    return text[len(frontmatter(text)):]


def body_hash(text: str) -> str:
    norm = "\n".join(l.rstrip() for l in body(text).replace("\r\n", "\n").splitlines() if l.strip())
    return hashlib.sha256(norm.encode()).hexdigest()[:12]


def field(text: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", frontmatter(text), re.M)
    return m.group(1).strip().strip('"\'') if m else ""


def mirror_frontmatter(src_text: str, name: str, eol: str = "\n") -> str:
    """The narrow frontmatter the non-Hermes tools accept: name, description, author."""
    lines = [f"name: {name}", f"description: {field(src_text, 'description')}"]
    author = field(src_text, "author")
    if author:
        lines.append(f"author: {author}")
    return "---" + eol + eol.join(lines) + eol + "---" + eol


def find_skill(root: pathlib.Path, name: str) -> pathlib.Path | None:
    for f in root.rglob("SKILL.md"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"^name:\s*(\S+)", text, re.M)
        if (m.group(1).strip('"\'') if m else f.parent.name) == name:
            return f.parent
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--from", dest="src", required=True, choices=ROOTS)
    ap.add_argument("--to", dest="dst", required=True, choices=ROOTS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if a.src == a.dst:
        print("kaynak ve hedef aynı"); return 2
    if a.name in AMBIGUOUS and not a.force:
        print(f"'{a.name}' bilerek farklı: {AMBIGUOUS[a.name]}\nZorlamak için --force kullan."); return 2

    src_dir = find_skill(ROOTS[a.src], a.name)
    if not src_dir:
        print(f"kaynak bulunamadı: {a.name} ({a.src})"); return 2
    dst_dir = find_skill(ROOTS[a.dst], a.name) or (ROOTS[a.dst] / a.name)

    src_text = (src_dir / "SKILL.md").read_text(encoding="utf-8")
    dst_skill = dst_dir / "SKILL.md"
    if dst_skill.exists():
        dst_text = dst_skill.read_text(encoding="utf-8")
        new_fm = frontmatter(dst_text) or frontmatter(src_text)   # hedefin kendi frontmatter'ı
        eol = "\r\n" if dst_skill.read_bytes().count(b"\r\n") else "\n"
    else:
        eol = "\r\n" if b"\r\n" in (src_dir / "SKILL.md").read_bytes() else "\n"  # yeni hedef kaynağın satır sonu stilini alır
        new_fm = mirror_frontmatter(src_text, a.name, eol)

    new_text = (new_fm + body(src_text)).replace("\r\n", "\n").replace("\n", eol)
    extra_files = [p for p in src_dir.rglob("*") if p.is_file() and p.name != "SKILL.md"]

    print(f"kaynak : {src_dir}")
    print(f"hedef  : {dst_dir}  ({'var' if dst_skill.exists() else 'yeni'})")
    print(f"ek dosya: {len(extra_files)}")
    print(f"gövde hash: kaynak={body_hash(src_text)} hedef_mevcut="
          f"{body_hash(dst_text) if dst_skill.exists() else '-'}")

    if a.dry_run:
        print("dry-run: yazılmadı"); return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    if dst_dir.exists():
        bak = BACKUP_ROOT / f"sync-{a.name}-{a.dst}-{stamp}"
        shutil.copytree(dst_dir, bak)
        print(f"yedek  : {bak}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_skill.write_bytes(new_text.encode("utf-8"))
    for p in extra_files:
        target = dst_dir / p.relative_to(src_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)

    check = (dst_dir / "SKILL.md").read_text(encoding="utf-8")
    ok = body_hash(check) == body_hash(src_text)
    print(f"sonuç  : {'SENKRON (' + body_hash(check) + ')' if ok else 'HASH FARKLI - incele'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Hub-linkage audit v2: counts a page as hub-linked if it links to a project hub OR its own source page."""
import re, pathlib, collections, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wikiconfig  # tek ayar kaynağı; proje yolu koda gömülü DEĞİL

ROOT = wikiconfig.wiki_dir()
HUBS = {"the-azure-paradox", "codex-development-stack", "hermes", "agentic-3d-game-workflow"}

def body_links(body):
    out = set()
    for m in re.findall(r"\[\[([^\]]+)\]\]", body):
        t = m.split("|")[0].split("#")[0].strip().removesuffix(".md")
        out.add(t.replace("\\", "/").split("/")[-1])
    return out

no_hub = []
for p in ROOT.rglob("*.md"):
    if p.name in ("index.md", "log.md") or p.stem in HUBS:
        continue
    full = p.read_text(encoding="utf-8", errors="ignore")
    body = re.sub(r"^---.*?---", "", full, count=1, flags=re.S)
    links = body_links(body)
    sm = re.search(r"^sources:\s*\[(.*?)\]", full, re.M)
    src_ident = sm.group(1) if sm else ""
    src_stems = {s.strip().strip('"').removesuffix(".md") for s in src_ident.split(",") if s.strip()}
    if links & HUBS or links & src_stems:
        continue
    tm = re.search(r"^tags:\s*\[(.*?)\]", full, re.M)
    no_hub.append((p.relative_to(ROOT).as_posix(), (tm.group(1) if tm else "")[:35], len(body)))

print("hub'sız sayfa:", len(no_hub))
for rel, tags, n in sorted(no_hub):
    print(f"   {rel:66} {n:5}B tags=[{tags}]")

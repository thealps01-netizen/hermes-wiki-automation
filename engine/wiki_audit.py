"""Wiki audit: index drift, dangling body links, duplicate stems."""
import re, sys, pathlib, collections

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wikiconfig  # tek ayar kaynağı; argüman verilirse o kullanılır (taşınabilirlik provası)


def _root(arg: str | None) -> pathlib.Path:
    """Argüman verilirse onu (proje kökü ya da wiki/ klasörü), verilmezse SEÇİLİ projeyi kullan."""
    if not arg:
        return wikiconfig.wiki_dir()
    p = pathlib.Path(arg)
    return p / "wiki" if (p / "wiki").is_dir() else p


ROOT = _root(sys.argv[1] if len(sys.argv) > 1 else None)
pages = [p for p in ROOT.rglob("*.md") if p.name not in ("index.md", "log.md")]


def strip_code(text: str) -> str:
    """Drop fenced and inline code spans: documented `[[folder/page]]` examples are not links."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


stems = collections.defaultdict(list)
for p in pages:
    stems[p.stem].append(p.relative_to(ROOT).as_posix())

print("dosya:", len(pages), "| benzersiz stem:", len(stems))
dups = {k: v for k, v in stems.items() if len(v) > 1}
print("çift stem:", dups)

idx = (ROOT / "index.md").read_text(encoding="utf-8")
ilinks = set()
for m in re.findall(r"\[\[([^\]]+)\]\]", idx):
    ilinks.add(m.split("|")[0].split("#")[0].strip().removesuffix(".md"))

files = {p.relative_to(ROOT).with_suffix("").as_posix() for p in pages}
file_stems = {p.stem for p in pages}

extra = sorted(l for l in ilinks if l not in files and l.split("/")[-1] not in file_stems)
missing = sorted(f for f in files if f not in ilinks and f.split("/")[-1] not in ilinks)
print("\n[index] indexte olup dosyası olmayan:", len(extra))
for e in extra:
    print("   !", e)
print("[index] dosyada olup indexte olmayan:", len(missing))
for m in missing:
    print("   +", m)

dang = collections.Counter()
forms = collections.Counter()
for p in pages:
    body = re.sub(r"^---.*?---", "", strip_code(p.read_text(encoding="utf-8", errors="ignore")), count=1, flags=re.S)
    for t in re.findall(r"\[\[([^\]]+)\]\]", body):
        tt = t.split("|")[0].split("#")[0].strip().removesuffix(".md")
        if not tt:
            continue
        norm = tt.replace("\\", "/")
        stem = norm.split("/")[-1]
        if stem in file_stems:
            forms["path-form" if "/" in norm else "stem-form"] += 1
            if "/" in norm and norm not in files:
                dangling_path = norm
                dang[f"PATH:{dangling_path}"] += 1
            continue
        dang[tt] += 1

print("\nçözülen link biçimleri:", dict(forms))
print("kırık hedefler:", len(dang))
for k, v in dang.most_common(30):
    print(f"   {k} x{v}")

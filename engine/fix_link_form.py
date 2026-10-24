"""Convert path-form wikilinks ([[folder/stem]]) to the schema's stem form ([[stem]]).

The app's knowledge graph resolves targets only against file names, and schema.md mandates
`[[page-slug]]`, so path-form links create no graph edge and show up as isolated pages.

Newline safety: the original file's line-ending style is preserved. Earlier versions used
Path.write_text, which translated every \\n to \\r\\n on Windows and rewrote every line of
42 wiki files (5840-line churn for 373 link changes). Read/write bytes instead, and do the
regex work in LF space so a CRLF file is not rewritten just for its endings. A file with MIXED
endings (an agent appended \\n lines into a CRLF file - the usual way path-form links get in) is
normalized to its dominant style instead of being skipped, which is how index.md kept its
path-form block.
Aliases (|Display) and anchors (#section) are preserved; ambiguous stems are skipped.
"""
import pathlib, re, collections, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wikiconfig  # tek ayar kaynağı; proje yolu koda gömülü DEĞİL

# Usage: fix_link_form.py [<wiki dir>]                     rewrite every page
#        fix_link_form.py --files-from - [<wiki dir>]      rewrite only the pages listed on stdin
#                                                          (repo-relative paths, e.g. wiki/x.md);
#                                                          the commit hook uses this so it never
#                                                          touches files that are not staged
_args = sys.argv[1:]
ONLY: set[str] | None = None
if _args[:2] == ["--files-from", "-"]:
    ONLY = {l.strip().replace("\\", "/") for l in sys.stdin if l.strip()}
    _args = _args[2:]
WIKI = pathlib.Path(_args[0]) if _args else wikiconfig.wiki_dir()
RX = re.compile(r"\[\[([^\]|#]+)(#[^\]|]*)?(\|[^\]]*)?\]\]")


def ending_style(data: bytes) -> str:
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n")
    if crlf == 0:
        return "\n"
    if crlf == lf:
        return "\r\n"
    return "\r\n" if crlf >= lf - crlf else "\n"  # mixed: normalize to the dominant style


def main() -> int:
    files = [p for p in WIKI.rglob("*.md")]
    stems = collections.Counter(p.stem for p in files)
    dup = {s for s, c in stems.items() if c > 1}
    changed_files = changed_links = ambiguous = 0

    for p in files:
        if ONLY is not None and ("wiki/" + p.relative_to(WIKI).as_posix()) not in ONLY:
            continue
        raw = p.read_bytes()
        nl = ending_style(raw)
        text = raw.decode("utf-8").replace("\r\n", "\n")
        counter = {"n": 0}

        def repl(m):
            target, anchor, alias = m.group(1), m.group(2) or "", m.group(3) or ""
            t = target.strip()
            if "/" not in t:
                return m.group(0)
            stem = t.split("/")[-1].strip()
            if not stem or stem not in stems or stem in dup:
                if stem in dup:
                    nonlocal ambiguous
                    ambiguous += 1
                return m.group(0)
            counter["n"] += 1
            return f"[[{stem}{anchor}{alias}]]"

        new = RX.sub(repl, text)
        if new != text:
            p.write_bytes(new.replace("\n", nl).encode("utf-8"))  # style restored on write
            changed_files += 1
            changed_links += counter["n"]

    print(f"değişen dosya: {changed_files} | dönüştürülen link: {changed_links} | belirsiz atlanan: {ambiguous}")
    left = sum(1 for p in files for t in RX.findall(p.read_text(encoding="utf-8", errors="ignore")) if "/" in t[0])
    print(f"kalan yol biçimli link: {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

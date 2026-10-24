"""Replicate the LLM Wiki app's knowledge-graph rule and list isolated pages.

App rule (nashsu/llm_wiki v0.6.12, src/lib/wiki-graph.ts + graph-insights.ts):
  nodes = every wiki/**/*.md, id = file stem, type = frontmatter `type` (default "other"),
          nodes with type "query" are removed entirely
  links = the set union of the page's [[wikilinks]] (anywhere in the file) and its frontmatter
          `related:` list. `related:` counts since v0.6.12 (commit b726bd16); before that only
          [[wikilinks]] did, which is why a daily link-repair job used to add body links.
  edges = links whose target resolves by stem (exact, lowercase, spaces->hyphens), self excluded
  linkCount = per-link increments on both endpoints (inbound + outbound)
  isolated = linkCount <= 1, excluding type "overview" and ids index/log

watchdog.py imports `isolated_pages()` from here, so the rule lives in one place. When the app
changes its graph rule again, update this file and compare the count with the app's own graph API.

Run: python app_graph_isolated.py [wiki_dir]
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

WIKILINK = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]")
FRONTMATTER = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", re.S)


def _related(frontmatter: str) -> list[str]:
    """The `related:` list as the app reads it: flow ([a, "b"]) or block (- a) YAML list items,
    [[ ]] stripped, |alias and #heading dropped, folder prefix and .md removed."""
    m = re.search(r"(?m)^related:[ \t]*\[(.*?)\][ \t]*$", frontmatter)
    if m:
        items = m.group(1).split(",")
    else:
        m = re.search(r"(?m)^related:[ \t]*\r?\n((?:[ \t]*-[ \t]*.+\r?\n?)+)", frontmatter)
        items = [line.split("-", 1)[1] for line in m.group(1).splitlines()] if m else []
    out = []
    for value in items:
        value = value.strip().strip("\"'").strip()
        value = re.sub(r"^\[\[|\]\]$", "", value)
        value = value.split("|")[0].split("#")[0].replace("\\", "/").split("/")[-1]
        value = re.sub(r"\.md$", "", value, flags=re.I)
        if value:
            out.append(value)
    return out


def isolated_pages(root: pathlib.Path) -> tuple[int, int, list[tuple[str, int, str, pathlib.Path]]]:
    """(graph node count, hidden query pages, [(id, linkCount, type, path)] of isolated pages)."""
    nodes: dict[str, dict] = {}
    for p in sorted(root.rglob("*.md")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        m = FRONTMATTER.match(text)
        fm = m.group(1) if m else ""
        ty = "other"
        mm = re.search(r"^type:\s*(\S+)", fm, re.M)
        if mm:
            ty = mm.group(1).strip().strip("\"'").lower()
        links = {x.strip() for x in WIKILINK.findall(text)} | set(_related(fm))
        nodes[p.stem] = {"type": ty, "path": p, "links": links}

    graph = {k: v for k, v in nodes.items() if v["type"] != "query"}
    index = {i: i for i in graph}
    for i in graph:
        for alias in (i.lower(), re.sub(r"\s+", "-", i.lower())):
            index.setdefault(alias, i)

    counts: collections.Counter = collections.Counter({i: 0 for i in graph})
    for sid, node in graph.items():
        for raw in node["links"]:
            target = next((index[a] for a in (raw, raw.lower(), re.sub(r"\s+", "-", raw.lower()))
                           if a in index), None)
            if target is None or target == sid:
                continue
            counts[sid] += 1
            counts[target] += 1

    iso = [(i, counts[i], graph[i]["type"], graph[i]["path"]) for i in graph
           if counts[i] <= 1 and graph[i]["type"] != "overview" and i not in ("index", "log")]
    iso.sort(key=lambda x: (x[1], x[0]))
    return len(graph), len(nodes) - len(graph), iso


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import wikiconfig  # tek ayar kaynağı; argüman verilirse o (taşınabilirlik provası)

    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else wikiconfig.wiki_dir()
    n_graph, n_query, iso = isolated_pages(root)
    print(f"grafik düğümü: {n_graph} (query tipi {n_query} sayfa grafikte yok)")
    print(f"izole (derece<=1): {len(iso)}")
    for i, d, ty, path in iso:
        rel = path.as_posix().split("/wiki/")[-1]
        print(f"  derece={d}  {path.stat().st_size:>6}B  [{ty}]  wiki/{rel}")

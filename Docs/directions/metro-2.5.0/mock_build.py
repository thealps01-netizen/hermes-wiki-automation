"""Metro direction: every surface (states, opened stations, dialog, history, settings, narrow pane).

Real data from live.json where the caption says so; example data otherwise. Lines are computed from
getBoundingClientRect at load. Output: metro.html, shot by shoot.cjs (one PNG per [data-shot]).
"""
import datetime as dt, html as H, json
from pathlib import Path

HERE = Path(__file__).parent
head = (HERE / "after.html").read_text(encoding="utf-8").split("</head>")[0]
head = head[: head.rfind("<style>")]
live = json.loads((HERE / "live.json").read_text(encoding="utf-8"))
st = live["automation"]["settings"]
PROJECT, PAGES, ROOT = Path(st["project_root"]).name, st["project"]["pages"], st["project_root"]
AUDIT = st["audit_dir"]
SCRIPTS = live["automation"]["scripts"]
N_PROB = len(live["health_watchdog"]["runs"][0]["findings"])
N_WAIT = len(live["candidates"]["candidates"])
NOW = dt.datetime.now()
runs = live["health_jobs"]["runs"]
hv = next(r for r in runs if r["job_name"] == "Wiki Session Harvest")
HV_SECS = round((dt.datetime.fromisoformat(hv["finished_at"]) - dt.datetime.fromisoformat(hv["at"])).total_seconds())

def until(h, m):
    t = NOW.replace(hour=h, minute=m, second=0, microsecond=0)
    if t < NOW: t += dt.timedelta(days=1)
    mins = int((t - NOW).total_seconds() // 60)
    return f"in {mins // 60} h {mins % 60:02d} min"
IN_HARVEST, IN_CHECK = until(21, 30), until(9, 0)
PROBLEMS = [("Two pages share one name", "5 pairs, e.g. concepts/glossary.md and entities/glossary.md"),
            ("Links point to pages that do not exist", "8 missing pages, e.g. release-notes (7 links)"),
            ("An ingest output was not split into pages", "sources/2026-10-11-meeting-notes.md"),
            ("Agent setups differ", "The check gave no detail"),
            ("Evidence store has 1 problem", "2026-09-28-onboarding-checklist.md"),
            ("4 evidence passages are out of date", "They no longer match the installed version")]
assert len(PROBLEMS) == N_PROB
SRC = [("Hermes", "var(--ui-accent)"), ("Codex", "var(--ui-green)"), ("Claude Code", "var(--ui-purple)"), ("Antigravity", "var(--ui-cyan)")]
cursor = dt.datetime.fromisoformat(live["harvest_status"]["agents"][0]["cursor"]).strftime("%H:%M")

CSS = r"""
*,*::before,*::after{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--ui-surface-background);color:var(--ui-text-primary);font-size:13px}
.sheet{display:flex;flex-direction:column;gap:34px}
.cap{font-size:14px;color:var(--ui-text-secondary);margin:0 0 10px;max-width:1040px;line-height:1.5}
.cap b{color:var(--ui-text-primary);font-size:15px}
.frame{width:1040px;border:1px solid var(--ui-stroke-primary);border-radius:12px;overflow:hidden;position:relative;background:var(--ui-bg-card, var(--ui-surface-background))}
.frame.n{width:390px}
.top{display:flex;align-items:center;gap:10px;padding:14px 24px;border-bottom:1px solid var(--ui-stroke-tertiary)}
.top h1{font-size:14px;font-weight:600;margin:0}.top .r{margin-left:auto;display:flex;gap:6px;align-items:center}
.n .top{padding:12px 16px}
.hb{font:inherit;font-size:12.5px;display:inline-flex;gap:6px;align-items:center;padding:5px 10px;border-radius:7px;border:1px solid var(--ui-stroke-secondary);background:transparent;color:var(--ui-text-primary)}
.hb.on{border-color:var(--ui-accent);background:color-mix(in srgb,var(--ui-accent) 14%, transparent)}
.btn{font:inherit;font-size:13px;padding:8px 16px;border-radius:8px;border:1px solid var(--ui-stroke-primary);background:transparent;color:var(--ui-text-primary)}
.btn.pri{background:var(--ui-accent);border-color:var(--ui-accent);color:#fff;font-weight:600}
.btn.warn{background:var(--ui-orange);border-color:var(--ui-orange);color:#111;font-weight:600}
.btn.bad{background:var(--ui-red);border-color:var(--ui-red);color:#fff;font-weight:600}
.mut{color:var(--ui-text-secondary)}
.area{position:relative;padding:24px 36px 18px}
.n .area{padding:18px 16px 12px}
svg.wires{position:absolute;inset:0;pointer-events:none;overflow:visible;z-index:0}
.title{font-size:22px;font-weight:700}.title span{color:var(--ui-text-secondary);font-weight:500;font-size:14px;margin-left:10px}
.n .title{font-size:18px}.n .title span{display:block;margin:4px 0 0}
.map{position:relative;display:grid;grid-template-columns:330px 1fr 1fr 1fr;align-items:center;margin-top:22px;min-height:210px}
.branches{display:flex;flex-direction:column;gap:18px;position:relative;z-index:1}
.br{display:flex;align-items:center;gap:10px;font-weight:600}
.br .c{width:14px;height:14px;border-radius:50%;border:3px solid var(--c);background:var(--ui-bg-card, var(--ui-surface-background))}
.br .q{font-weight:500;font-size:12px;color:var(--ui-text-secondary)}
.br.missing .nm{color:var(--ui-text-secondary)}.br.missing .c{border-color:var(--ui-text-tertiary);border-style:dashed}
.stn{position:relative;display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;z-index:1}
.stop{width:30px;height:30px;border-radius:50%;border:5px solid var(--ui-text-primary);background:var(--ui-bg-card, var(--ui-surface-background));display:grid;place-items:center}
.stn .n{font-size:15px;font-weight:700}.stn .s{font-size:12.5px;color:var(--ui-text-secondary);line-height:1.45}
.stn.warn .stop{border-color:var(--ui-orange);box-shadow:0 0 0 6px color-mix(in srgb,var(--ui-orange) 22%, transparent)}
.stn.bad .stop{border-color:var(--ui-red);box-shadow:0 0 0 6px color-mix(in srgb,var(--ui-red) 22%, transparent)}
.stn.ask .stop{border-color:var(--ui-accent);box-shadow:0 0 0 6px color-mix(in srgb,var(--ui-accent) 25%, transparent)}
.stn.run .stop{border-color:var(--ui-accent);border-top-color:transparent}
.stn.sel .n{text-decoration:underline;text-underline-offset:5px;text-decoration-thickness:2px}
.stn.sel .stop{outline:2px solid var(--ui-text-primary);outline-offset:7px}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 10px;border-radius:12px;background:var(--ui-accent);color:#fff;white-space:nowrap}
.pill.ghost{visibility:hidden}.pill.bad{background:var(--ui-red)}.pill.warn{background:var(--ui-orange);color:#111}
.cnt{display:inline-grid;place-items:center;min-width:20px;height:20px;padding:0 6px;border-radius:10px;background:var(--ui-accent);color:#fff;font-size:12px;font-weight:700}
.bar{margin:4px 36px 22px;display:flex;gap:14px;align-items:center;padding:14px 18px;border-radius:10px}
.bar .t{font-weight:700}.bar .btn{margin-left:auto}
.bar.warn{background:color-mix(in srgb,var(--ui-orange) 12%, transparent);border-left:5px solid var(--ui-orange)}
.bar.bad{background:color-mix(in srgb,var(--ui-red) 12%, transparent);border-left:5px solid var(--ui-red)}
.bar.ok{background:color-mix(in srgb,var(--ui-green) 10%, transparent);border-left:5px solid var(--ui-green)}
.bar.ask{background:color-mix(in srgb,var(--ui-accent) 12%, transparent);border-left:5px solid var(--ui-accent)}
.bar .ic{font-size:20px}
.n .bar{margin:4px 16px 16px;flex-wrap:wrap}.n .bar .btn{margin-left:0;width:100%}
.detail{margin:0 36px 24px;border:1px solid var(--ui-stroke-secondary);border-radius:12px;overflow:hidden}
.n .detail{margin:0 16px 16px}
.dh{display:flex;align-items:center;gap:10px;padding:12px 18px;border-bottom:1px solid var(--ui-stroke-tertiary);background:color-mix(in srgb,var(--ui-bg-elevated) 60%, transparent)}
.dh .t{font-weight:700;font-size:14px}.dh .x{margin-left:auto;color:var(--ui-text-secondary)}
.db{padding:16px 18px;display:flex;flex-direction:column;gap:12px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:8px 16px}.kv span:nth-child(odd){color:var(--ui-text-secondary)}
.n .kv{grid-template-columns:1fr}.n .kv span:nth-child(even){margin-bottom:6px}
.li{display:grid;grid-template-columns:22px 1fr;gap:10px;padding:9px 0;border-top:1px solid var(--ui-stroke-tertiary)}
.li:first-child{border-top:0}.li .t{font-weight:600}.li .d{color:var(--ui-text-secondary);font-size:12px;margin-top:2px;overflow-wrap:anywhere}
.acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.note{font-size:12px;color:var(--ui-text-secondary);display:flex;gap:8px}
.mono{font-family:"Cascadia Mono",Consolas,monospace;font-size:12px;overflow-wrap:anywhere;color:var(--ui-text-secondary)}
.jobs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.n .jobs{grid-template-columns:1fr}
.job{border:1px solid var(--ui-stroke-tertiary);border-radius:10px;padding:10px 12px}
.job .h{display:flex;gap:8px;align-items:center;font-weight:600}.job .w{font-size:12px;color:var(--ui-text-secondary);margin-top:4px;line-height:1.45}
.dot{width:10px;height:10px;border-radius:50%;background:var(--ui-green)}.dot.o{background:var(--ui-orange)}.dot.r{background:var(--ui-red)}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:2px 8px;border-radius:6px;border:1px solid var(--ui-stroke-secondary)}
.steps{display:flex;gap:6px;align-items:center;margin-left:auto;color:var(--ui-text-secondary);font-size:12px}
.steps i{width:8px;height:8px;border-radius:50%;background:var(--ui-stroke-secondary);display:inline-block}.steps i.on{background:var(--ui-accent)}
.veil{position:absolute;inset:0;background:color-mix(in srgb,#000 55%, transparent);display:grid;place-items:center;z-index:5}
.dlg{width:460px;border-radius:12px;border:1px solid var(--ui-stroke-primary);padding:20px 22px;display:flex;flex-direction:column;gap:12px;
  background:linear-gradient(var(--ui-bg-tertiary),var(--ui-bg-tertiary)),var(--ui-surface-background);box-shadow:0 18px 40px color-mix(in srgb,#000 50%, transparent)}
.dlg h3{margin:0;font-size:16px}
.sk{border-radius:8px;background:color-mix(in srgb,var(--ui-text-primary) 8%, transparent)}
.hist{display:flex;flex-direction:column}
.hr{display:grid;grid-template-columns:110px 26px 1fr auto;gap:12px;align-items:center;padding:11px 0;border-top:1px solid var(--ui-stroke-tertiary)}
.hr:first-child{border-top:0}.hr .when{color:var(--ui-text-secondary);font-variant-numeric:tabular-nums}
.hr .what{font-weight:600}.hr .what span{display:block;font-weight:400;color:var(--ui-text-secondary);font-size:12px;margin-top:2px}
.n .hr{grid-template-columns:22px 1fr}.n .hr .when{grid-column:2;order:3}.n .hr .res{grid-column:2;order:4}
/* vertical (narrow) map */
.vmap{position:relative;margin-top:16px}
.vbr{display:flex;flex-direction:column;gap:12px;padding-left:52px;position:relative;z-index:1}
.vbr .br{font-size:12.5px}
.vst{display:flex;flex-direction:column;gap:30px;margin-top:30px;padding-left:4px;position:relative;z-index:1}
.vst .stn{flex-direction:row;align-items:flex-start;text-align:left;gap:14px}
.vst .stn .stop{flex:none}.vst .stn .txt{display:flex;flex-direction:column;gap:3px;padding-top:2px}
.vst .pill{align-self:flex-start;margin-top:4px}
"""

def esc(s): return H.escape(s)

def top(active=None, narrow=False):
    hist = f'<button class="hb{" on" if active == "history" else ""}"><i class="codicon codicon-history"></i>{"" if narrow else "History"}</button>'
    sett = f'<button class="hb{" on" if active == "settings" else ""}"><i class="codicon codicon-gear"></i>{"" if narrow else "Settings"}</button>'
    return f'<div class="top"><i class="codicon codicon-book"></i><h1>Wiki Automation</h1><span class="r">{hist}{sett}</span></div>'

def branches(state=None):
    state = state or {}
    out = []
    for name, c in SRC:
        s = state.get(name, "ok")
        q = {"ok": "", "missing": '<span class="q">folder not found</span>', "run": '<span class="q">reading</span>'}[s]
        out.append(f'<div class="br {s}" data-br="{s}" style="--c:{c}"><span class="c"></span><span class="nm">{name}</span>{q}</div>')
    return "".join(out)

def station(key, name, sub, cls="", pill="", narrow=False):
    pill_html = pill or '<span class="pill ghost">.</span>'
    if narrow:
        return (f'<div class="stn {cls}" data-stn="{key}"><span class="stop"></span><span class="txt"><span class="n">{name}</span>'
                f'<span class="s">{sub}</span>{pill or ""}</span></div>')
    return f'<div class="stn {cls}" data-stn="{key}">{pill_html}<span class="stop"></span><span class="n">{name}</span><span class="s">{sub}</span></div>'

def metro(S, narrow=False):
    """S: dict with harvest/review/wiki (name, sub, cls, pill), segs, src state."""
    stns = "".join(station(k, *S[k], narrow=narrow) for k in ("harvest", "review", "wiki"))
    segs = ",".join(S.get("segs", ["on", "on"]))
    if narrow:
        return (f'<div class="area" data-dir="v" data-segs="{segs}"><svg class="wires"></svg>'
                f'<div class="title">Wiki line<span>from your conversations to your wiki</span></div>'
                f'<div class="vmap"><div class="vbr">{branches(S.get("src"))}</div><div class="vst">{stns}</div></div></div>')
    return (f'<div class="area" data-dir="h" data-segs="{segs}"><svg class="wires"></svg>'
            f'<div class="title">Wiki line<span>from your conversations to your wiki</span></div>'
            f'<div class="map"><div class="branches">{branches(S.get("src"))}</div>{stns}</div></div>')

def bar(tone, icon, title, text, btn=None, btn_cls="warn"):
    b = f'<button class="btn {btn_cls}">{btn}</button>' if btn else ""
    color = {"warn": "var(--ui-orange)", "bad": "var(--ui-red)", "ok": "var(--ui-green)", "ask": "var(--ui-accent)"}[tone]
    return (f'<div class="bar {tone}"><i class="codicon codicon-{icon} ic" style="color:{color}"></i>'
            f'<div><div class="t">{title}</div><div class="mut">{text}</div></div>{b}</div>')

def detail(title, body, icon="info"):
    return (f'<div class="detail"><div class="dh"><i class="codicon codicon-{icon}"></i><span class="t">{title}</span>'
            f'<i class="codicon codicon-close x"></i></div><div class="db">{body}</div></div>')

def frame(inner, narrow=False, active=None, overlay=""):
    return f'<div class="frame{" n" if narrow else ""}">{top(active, narrow)}{inner}{overlay}</div>'

def shot(cap, html):
    return f'<section class="d-wrap"><p class="cap">{cap}</p><div data-shot>{html}</div></section>'

# ---------- shared states ----------
NEXT = f'<span class="pill"><i class="codicon codicon-clock"></i>next 21:30</span>'
TODAY = {
    "harvest": ("Harvest", f"turns conversations into drafts<br>{IN_HARVEST}", "", NEXT),
    "review": ("Your review", f"{N_WAIT} drafts waiting<br>you approve or reject", ""),
    "wiki": ("Wiki", f"{PAGES} pages<br>{N_PROB} problems", "warn"),
}
WIKI_ALERT = bar("warn", "warning", f"Service alert at Wiki: {N_PROB} problems since 11.10",
                 "Two pages share one name, 8 links lead nowhere, and 4 more.", f"Show the {N_PROB} problems")
def sel(S, key):
    S = {k: (v if not isinstance(v, tuple) else v) for k, v in S.items()}
    n, s, c, *p = S[key]
    S[key] = (n, s, (c + " sel").strip(), *p)
    return S

prob_list = "".join(f'<div class="li"><span class="mut">{i}</span><div><div class="t">{t}</div><div class="d">{esc(d)}</div></div></div>'
                    for i, (t, d) in enumerate(PROBLEMS, 1))
jobs_at_wiki = ('<div class="jobs">'
                f'<div class="job"><div class="h"><span class="dot o"></span>Daily check</div><div class="w">Looks for problems. Last yesterday 10:31: found {N_PROB}. Next 09:00.</div></div>'
                '<div class="job"><div class="h"><span class="dot"></span>New sources</div><div class="w">Lets LLM Wiki read new sources. Last yesterday 10:31: fine. Next 09:00.</div></div>'
                '<div class="job"><div class="h"><span class="dot"></span>Saving</div><div class="w">Saves every wiki change. Last yesterday 10:31: fine. Next 09:00.</div></div></div>')
WIKI_DETAIL = detail(f"Wiki station · {PAGES} pages",
    f'<div class="t" style="font-weight:700">{N_PROB} problems, the same every day since 11.10</div>{prob_list}'
    '<div class="acts"><button class="btn warn">Ask Hermes to fix these</button>'
    '<span class="note"><i class="codicon codicon-info"></i>Writes a request into the chat box. You read it and send it yourself.</span></div>'
    f'<div class="mut" style="font-weight:600;margin-top:4px">Work done at this station every morning</div>{jobs_at_wiki}', "book")

HARVEST_DETAIL = detail("Harvest station",
    '<div class="kv">'
    f'<span>What it does</span><span>Reads your Hermes, Codex, Claude Code and Antigravity conversations and writes drafts for you to review.</span>'
    f'<span>Timetable</span><span>Every day at 21:30</span>'
    f'<span>Next run</span><span>Today 21:30 · {IN_HARVEST}</span>'
    f'<span>Last run</span><span>Yesterday 23:04 · finished in {HV_SECS} seconds</span></div>'
    '<div class="acts"><button class="btn">Change time</button><button class="btn">Pause</button></div>', "sparkle")

HERMES_DETAIL = detail("Hermes line",
    '<div class="kv">'
    f'<span>What it brings</span><span>Your Hermes conversations</span>'
    f'<span>Collected up to</span><span>Yesterday {cursor}</span>'
    f'<span>Folder</span><span>Found</span></div>'
    '<div class="note"><i class="codicon codicon-info"></i>A found folder does not prove every conversation was read. The next harvest continues from yesterday ' + cursor + '.</div>',
    "comment-discussion")

# example: drafts waiting
WAIT = {
    "harvest": ("Harvest", "last run 23:04<br>wrote 3 drafts", "", NEXT),
    "review": ("Your review", "3 drafts waiting<br>you approve or reject", "ask sel",
               '<span class="pill"><i class="codicon codicon-inbox"></i>3 waiting</span>'),
    "wiki": ("Wiki", f"{PAGES} pages<br>no problems", ""),
    "segs": ["on", "dim"],
}
REVIEW_CARD = detail("Your review · draft 1 of 3",
    '<div class="acts"><span class="chip"><i class="codicon codicon-file-add"></i>New page</span>'
    '<span class="steps"><i class="on"></i><i></i><i></i>1 of 3</span></div>'
    '<div><div style="font-size:20px;font-weight:700">Team glossary</div>'
    '<div class="mut" style="margin-top:4px;font-size:13.5px">The terms every project page uses.</div></div>'
    '<div class="mono">Will be saved as raw/sources/2026-09-28-team-glossary.md</div>'
    '<div class="acts"><button class="btn pri">Approve</button><button class="btn">Reject</button><button class="btn">Later</button>'
    '<span class="note" style="margin-left:6px"><i class="codicon codicon-chevron-right"></i>Show the change and the evidence</span></div>', "inbox")

DIALOG = ('<div class="veil"><div class="dlg"><h3>Approve this draft?</h3>'
          '<div>“Team glossary” will be written to your wiki as</div>'
          '<div class="mono">raw/sources/2026-09-28-team-glossary.md</div>'
          '<div class="note"><i class="codicon codicon-warning" style="color:var(--ui-orange)"></i>LLM Wiki may then use model credits to read it.</div>'
          '<div class="acts" style="justify-content:flex-end"><button class="btn">Cancel</button><button class="btn pri">Approve and write</button></div></div></div>')

GOOD = {
    "harvest": ("Harvest", f"turns conversations into drafts<br>{IN_HARVEST}", "", NEXT),
    "review": ("Your review", "0 drafts waiting<br>you approve or reject", ""),
    "wiki": ("Wiki", f"{PAGES} pages<br>no problems", ""),
}
RUN = {
    "harvest": ("Harvest", "reading conversations<br>started 21:30, 1 min ago", "run sel",
                '<span class="pill"><i class="codicon codicon-sync"></i>collecting now</span>'),
    "review": ("Your review", "0 drafts waiting<br>new drafts arrive here", ""),
    "wiki": ("Wiki", f"{PAGES} pages<br>no problems", ""),
    "src": {n: "run" for n, _ in SRC}, "segs": ["dim", "dim"],
}
FAIL = {
    "harvest": ("Harvest", "stopped at 21:31<br>no drafts written", "bad",
                '<span class="pill bad"><i class="codicon codicon-error"></i>failed</span>'),
    "review": ("Your review", "0 drafts waiting<br>you approve or reject", ""),
    "wiki": ("Wiki", f"{PAGES} pages<br>no problems", ""),
    "segs": ["off", "on"],
}
MISSING = {
    "harvest": ("Harvest", f"reads 3 of 4 lines<br>{IN_HARVEST}", "", NEXT),
    "review": ("Your review", "0 drafts waiting<br>you approve or reject", ""),
    "wiki": ("Wiki", f"{PAGES} pages<br>no problems", ""),
    "src": {"Claude Code": "missing"},
}

LOADING = ('<div class="area"><div class="title">Wiki line<span>reading the timetable</span></div>'
           '<div style="display:grid;grid-template-columns:330px 1fr 1fr 1fr;gap:20px;margin-top:22px;align-items:center;min-height:210px">'
           '<div style="display:flex;flex-direction:column;gap:18px">' + '<div class="sk" style="height:16px;width:140px"></div>' * 4 + '</div>'
           + '<div style="display:flex;flex-direction:column;align-items:center;gap:10px"><div class="sk" style="width:30px;height:30px;border-radius:50%"></div><div class="sk" style="width:90px;height:14px"></div><div class="sk" style="width:140px;height:12px"></div></div>' * 3
           + '</div></div>')

HIST_ROWS = [
    ("Yesterday 23:04", "sparkle", "Harvest", "read your conversations", '<span class="dot"></span>', f"finished in {HV_SECS} s"),
    ("Yesterday 10:31", "eye", "Daily check", "looked for problems", '<span class="dot o"></span>', f"found {N_PROB} problems"),
    ("Yesterday 10:31", "inbox", "New sources", "let LLM Wiki read new sources", '<span class="dot"></span>', "finished"),
    ("Yesterday 10:31", "git-commit", "Saving", "saved wiki changes", '<span class="dot"></span>', "finished"),
]
def history(narrow=False):
    rows = "".join(f'<div class="hr"><span class="when">{w}</span><i class="codicon codicon-{ic}"></i>'
                   f'<span class="what">{n}<span>{d}</span></span><span class="res" style="display:flex;gap:8px;align-items:center">{dot}{r}</span></div>'
                   for w, ic, n, d, dot, r in HIST_ROWS)
    return detail("History · last 24 hours · 4 runs", f'<div class="hist">{rows}</div>'
                  '<div class="note"><i class="codicon codicon-info"></i>The morning jobs were due at 09:00 and ran at 10:31.</div>'
                  '<div class="acts"><button class="btn">Show older runs</button><button class="btn">Full technical log</button></div>', "history")

ok_scripts = sum(1 for v in SCRIPTS.values() if v)
def settings(narrow=False):
    return detail("Settings", '<div class="kv">'
        f'<span>Wiki folder</span><span><span class="mono" style="color:var(--ui-text-primary)">{esc(ROOT)}</span><br><span class="mut">{PAGES} pages · checked</span></span>'
        f'<span>Automation files</span><span>{ok_scripts} of {len(SCRIPTS)} in place</span>'
        f'<span>Working folder</span><span class="mono">{esc(AUDIT)}</span></div>'
        '<div class="acts"><button class="btn">Change wiki folder</button><button class="btn">Manage timetable</button></div>', "gear")

# ---------- sheet ----------
F = []
F.append(shot("<b>1 · Today, nothing selected</b> · real data", frame(metro(TODAY) + WIKI_ALERT)))
F.append(shot("<b>2 · Wiki station opened</b> (click on Wiki or on the alert button) · real data. One panel opens under the map; the map never moves.",
              frame(metro(sel(TODAY, "wiki")) + WIKI_DETAIL)))
F.append(shot("<b>3 · Harvest station opened</b> · real data", frame(metro(sel(TODAY, "harvest")) + WIKI_ALERT + HARVEST_DETAIL)))
F.append(shot("<b>4 · A branch line opened (Hermes)</b> · real data", frame(metro(TODAY) + HERMES_DETAIL)))
F.append(shot("<b>5 · Good service</b>, nothing needs you · example data", frame(metro(GOOD) + bar("ok", "pass", "Good service on the whole line", "Nothing needs you. Next harvest today at 21:30."))))
F.append(shot("<b>6 · Harvest running</b> · example data. The four branch lines light up while their conversations are read.",
              frame(metro(RUN) + bar("ask", "sync", "Harvest is reading your conversations", "New drafts will wait at Your review. You can keep working."))))
F.append(shot("<b>7 · Drafts waiting, Your review opened</b>, one draft at a time · example data",
              frame(metro(WAIT) + REVIEW_CARD)))
F.append(shot("<b>8 · Approve pressed:</b> the second step stays · example data",
              frame(metro(WAIT) + REVIEW_CARD, overlay=DIALOG)))
F.append(shot("<b>9 · Harvest failed</b> · example data", frame(metro(FAIL) + bar("bad", "error", "Harvest stopped at 21:31",
              "No drafts were written. Reason: the model did not answer in time.", "Try again now", "bad"))))
F.append(shot("<b>10 · A conversation folder is missing</b> · example data", frame(metro(MISSING) + bar("warn", "folder",
              "Claude Code line closed: folder not found", "The other three lines still run. Harvest skips Claude Code until the folder is back.", "Show where it looked"))))
F.append(shot("<b>11 · Loading</b>", frame(LOADING)))
F.append(shot("<b>12 · The panel cannot read the timetable</b> · example data", frame(
    '<div class="area"><div class="title">Wiki line<span>no timetable</span></div></div>' +
    bar("bad", "error", "The timetable could not be read", "Your wiki and its jobs are untouched. Press Show the error to see what went wrong.", "Try again", "bad") +
    '<div style="height:6px"></div>')))
F.append(shot("<b>13 · History</b> (button top right) · real data", frame(metro(TODAY) + history(), active="history")))
F.append(shot("<b>14 · Settings</b> (button top right) · real data", frame(metro(TODAY) + settings(), active="settings")))
F.append(shot("<b>15 · Narrow pane, 390 px</b> · real data. The line turns vertical.", frame(metro(TODAY, narrow=True) + WIKI_ALERT, narrow=True)))
F.append(shot("<b>16 · Narrow pane, Wiki opened</b> · real data", frame(metro(sel(TODAY, "wiki"), narrow=True) + WIKI_DETAIL, narrow=True)))

WIRES = r"""<script>
(() => {
  const ns = 'http://www.w3.org/2000/svg', rr = e => e.getBoundingClientRect()
  const col = { on: 'var(--ui-text-primary)', dim: 'var(--ui-text-tertiary)', off: 'var(--ui-red)' }
  for (const A of document.querySelectorAll('.area[data-dir]')) {
    const svg = A.querySelector('svg.wires'), R = rr(A)
    const p = (d, c, w, dash, op) => { const e = document.createElementNS(ns, 'path'); e.setAttribute('d', d); e.setAttribute('fill', 'none');
      e.setAttribute('stroke', c); e.setAttribute('stroke-width', w); e.setAttribute('stroke-linecap', 'round');
      if (dash) e.setAttribute('stroke-dasharray', dash); if (op) e.setAttribute('stroke-opacity', op); svg.appendChild(e) }
    const stops = [...A.querySelectorAll('[data-stn] .stop')].map(rr)
    const segs = A.dataset.segs.split(',')
    const brs = [...A.querySelectorAll('[data-br]')]
    if (A.dataset.dir === 'h') {
      const y = stops[0].top - R.top + stops[0].height / 2, x0 = stops[0].left - R.left + stops[0].width / 2
      for (const b of brs) {
        const st = b.dataset.br, c = st === 'missing' ? 'var(--ui-text-tertiary)' : getComputedStyle(b).getPropertyValue('--c')
        const lab = rr(b.querySelector(st === 'ok' ? '.nm' : '.q')), dot = rr(b.querySelector('.c'))
        const bx = lab.right - R.left + 12, by = dot.top - R.top + dot.height / 2, ex = x0 - 110, mx = bx + (ex - bx) * .5
        p(`M${bx},${by} C${mx},${by} ${mx},${y} ${ex},${y} L${x0 - 14},${y}`, c, st === 'run' ? 6 : 5, st === 'missing' ? '3 7' : (st === 'run' ? '14 6' : ''), st === 'missing' ? '.7' : '')
      }
      for (let i = 0; i < stops.length - 1; i++)
        p(`M${stops[i].right - R.left},${y} L${stops[i + 1].left - R.left},${y}`, col[segs[i]], 8, segs[i] === 'off' ? '2 12' : '', segs[i] === 'dim' ? '.55' : '')
    } else {
      const x = stops[0].left - R.left + stops[0].width / 2, y0 = stops[0].top - R.top
      brs.forEach((b, i) => {
        const st = b.dataset.br, c = st === 'missing' ? 'var(--ui-text-tertiary)' : getComputedStyle(b).getPropertyValue('--c')
        const dot = rr(b.querySelector('.c')), by = dot.top - R.top + dot.height / 2, lx = x - 9 + i * 6
        p(`M${dot.left - R.left - 3},${by} L${lx + 8},${by} Q${lx},${by} ${lx},${by + 8} L${lx},${y0 - 2}`, c, 4, st === 'missing' ? '3 7' : '')
      })
      for (let i = 0; i < stops.length - 1; i++)
        p(`M${x},${stops[i].bottom - R.top} L${x},${stops[i + 1].top - R.top}`, col[segs[i]], 8, segs[i] === 'off' ? '2 12' : '', segs[i] === 'dim' ? '.55' : '')
    }
  }
})()
</script>"""

html = f'{head}<style>{CSS}</style></head><body><div class="sheet">{"".join(F)}</div>{WIRES}</body></html>'
(HERE / "metro.html").write_text(html, encoding="utf-8")
print("metro.html frames", len(F), NOW.strftime("%H:%M"))

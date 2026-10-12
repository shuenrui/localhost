#!/usr/bin/env python3
"""Build the Qwen local-run directory into one self-contained HTML file.

Stdlib only, no build step at runtime, no backend. Reads data/*.json,
validates it, and writes site/index.html with the dataset inlined so the page
works from file:// as well as over http and makes no network request at all
after load.

The page source lives in site_src/ so it can be diffed and reviewed:

    site_src/shell.html   skeleton with __CSS__, __DATA__ and __APP__ slots
    site_src/app.css      design system, layouts, breakpoints, both themes
    site_src/app.js       router, state, views, filters, compare, hardware

Usage:
    python3 directory/build.py                 # validate + build
    python3 directory/build.py --skip-validate # build only
    python3 directory/build.py --out /tmp/x.html

Presentation contract (see docs/redesign-2026-09-10/):
  * Models are the homepage; the complete recipe directory remains at #/recipes.
  * A single-stream tok/s number always wins the headline; aggregate results
    are never promoted into that slot and always state their concurrency.
  * No fit verdict exists outside the My Hardware route, and no unconditional
    "fits" verdict exists anywhere.
  * Trust is four independent dimensions, never averaged into one badge.
  * Any string passed through esc() must use literal Unicode, never an HTML
    entity -- esc() escapes the ampersand and the entity would leak to the page.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import html
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SRC = os.path.join(HERE, "site_src")
DEFAULT_OUT = os.path.join(HERE, "site", "index.html")


def load_dir(rel: str) -> list[dict]:
    d = os.path.join(DATA, rel)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json") or name.startswith("_"):
            continue
        with open(os.path.join(d, name), encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def load_json(rel: str):
    with open(os.path.join(DATA, rel), encoding="utf-8") as fh:
        return json.load(fh)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def collect() -> dict:
    publishers = load_json("publishers.json")["publishers"]
    models = {m["id"]: m for m in load_dir("models")}
    hardware = {h["id"]: h for h in load_dir("hardware")}
    engines = {e["id"]: e for e in load_dir("engines")}
    setups = load_dir("setups")

    # Newest generation first, then biggest model, so shelves read top-down.
    def model_sort_key(m: dict):
        try:
            gen_num = float(str(m.get("generation") or "0"))
        except ValueError:
            gen_num = 0.0
        return (-gen_num, -(m.get("architecture", {}).get("params_total_b") or 0))

    ordered = sorted(models.values(), key=model_sort_key)

    return {
        "generated": datetime.date.today().isoformat(),
        "publishers": publishers,
        "models": {m["id"]: m for m in ordered},
        "model_order": [m["id"] for m in ordered],
        "hardware": hardware,
        "engines": engines,
        "setups": setups,
        "counts": {
            "setups": len(setups),
            "models": len(models),
            "hardware": len(hardware),
            "engines": len(engines),
            "publishers": len(publishers),
            "measured": sum(1 for s in setups if s.get("provenance_tier") == "box"),
        },
    }


def font_faces() -> str:
    """Emit @font-face rules for the System Sheet faces as base64 data URIs.

    site/index.html is a single self-contained file, so the woff2 payloads are
    inlined rather than referenced by path, and hotlinking a CDN is deliberately
    avoided: it would add a third-party runtime dependency and drop the design
    onto OS fallbacks whenever that CDN is blocked or slow. The faces, their
    source URL and their OFL license are recorded in site_src/fonts/manifest.json.
    """
    manifest = json.loads(read(os.path.join(SRC, "fonts", "manifest.json")))
    rules = []
    for face in manifest["faces"]:
        with open(os.path.join(SRC, "fonts", face["file"]), "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        rules.append(
            "@font-face{font-family:'%s';font-style:%s;font-weight:%s;"
            "font-display:swap;src:url(data:font/woff2;base64,%s) format('woff2')}"
            % (face["family"], face["style"], face["weight"], b64)
        )
    return "\n".join(rules) + "\n"


REPO_URL = "https://github.com/shuenrui/localhost"
RAW_URL = "https://raw.githubusercontent.com/shuenrui/localhost/main"


def agent_brief(data: dict) -> str:
    """Plain HTML for readers that do not run JavaScript (AI agents' web readers,
    crawlers). Browsers with JavaScript hide it (.js #agent-brief) and the app
    renders over it. Generated from the same data, so it cannot drift."""
    e = html.escape
    setups = data.get("setups") or []
    models = data.get("models") or {}
    order = data.get("model_order") or sorted(models)
    rows = []
    for mid in order:
        m = models.get(mid) or {}
        mine = [s for s in setups if s.get("model") == mid]
        if not mine:
            continue
        rows.append("<li><b>%s</b> (%d recipes)<ul>%s</ul></li>" % (
            e(m.get("name") or mid), len(mine), "".join(
                "<li>%s: <code>%s</code>, needs %s GB, engine %s. JSON: <a href=\"%s/directory/data/setups/%s.json\">%s.json</a></li>" % (
                    e(s.get("title") or s["id"]), e(s["id"]),
                    e(str((s.get("requirements") or {}).get("memory_gb"))),
                    e(str((s.get("engine") or {}).get("id"))), RAW_URL, e(s["id"]), e(s["id"]))
                for s in mine)))
    return """<section id="agent-brief">
<h1>localhost: run open AI models on your own machine</h1>
<p>A directory of %d source-backed recipes for running %d open model families locally. Each recipe gives the hardware it ran on, the memory it needs, measured speed with its source, and the exact commands. This page is an app; the text below is for readers that do not run JavaScript.</p>
<h2>For AI agents</h2>
<ul>
<li>Use the CLI: <code>pip install "git+%s.git#subdirectory=cli"</code>, then <code>localhost detect --json</code>, <code>localhost fit --json</code>, <code>localhost guide &lt;recipe-id&gt; --json</code>, <code>localhost check --json</code>, <code>localhost connect opencode --json</code>.</li>
<li>Read the agent guide: <a href="%s/llms.txt">llms.txt</a>.</li>
<li>Per-recipe JSON is linked below. The whole dataset is also embedded in this page as <code>&lt;script id="data" type="application/json"&gt;</code>.</li>
<li>Rules: copy only steps marked as commands (<code>"kind": "cmd"</code>), verbatim. Never invent commands. Say when the directory records nothing.</li>
</ul>
<h2>Recipes by model</h2>
<ul>%s</ul>
<p>Source: <a href="%s">%s</a></p>
</section>""" % (len(setups), len(rows), REPO_URL, RAW_URL, "".join(rows), REPO_URL, REPO_URL.replace("https://", ""))


def render(data: dict) -> str:
    shell = read(os.path.join(SRC, "shell.html"))
    css = font_faces() + read(os.path.join(SRC, "app.css"))
    app = read(os.path.join(SRC, "app.js"))

    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # The dataset sits in a <script type="application/json"> block, so the only
    # sequence that can break out of it is a literal closing script tag.
    blob = blob.replace("</", "<\\/")

    for token, value in (("__CSS__", css), ("__AGENT__", agent_brief(data)), ("__DATA__", blob), ("__APP__", app)):
        if token not in shell:
            raise SystemExit(f"site_src/shell.html is missing the {token} slot")
        shell = shell.replace(token, value)
    return shell


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--skip-validate", action="store_true")
    args = ap.parse_args()

    if not args.skip_validate:
        rc = subprocess.call([sys.executable, os.path.join(HERE, "validate.py")])
        if rc != 0:
            print("\nbuild aborted: validation failed", file=sys.stderr)
            return rc

    data = collect()
    html = render(data)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)

    c = data["counts"]
    print(
        f"wrote {args.out}  ({len(html):,} bytes)\n"
        f"  {c['setups']} setups, {c['models']} model families, "
        f"{c['hardware']} hardware classes, {c['engines']} engines, "
        f"{c['publishers']} publishers"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
